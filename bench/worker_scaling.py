"""多 worker 横向对比：单 worker 是不是真的瓶颈？

背景：阶梯压测（单 worker）显示饱和拐点在 50→100 并发之间，且吞吐增幅骤降。
但那可能不是「架构到顶」，而是**单进程被 GIL / 单核 CPU 限制**。
如果是后者，那么横向扩 worker 应当近似线性提升吞吐 —— 这直接决定
「该继续纵向优化，还是该直接横向扩容」。

做法：依次起 1 / 2 / 4 worker，各跑同一组并发，取聚合吞吐对比。
每个配置独立起停服务，避免端口与状态残留互相污染。

⚠️ Windows 注意：uvicorn --workers 用 spawn 起子进程，必须有 if __name__ 保护，
否则子进程会重复执行模块级代码。本脚本只做进程编排，不 import 应用，安全。

用法：
    python bench/worker_scaling.py --levels 20,50,100 --workers 1,2,4 --duration 30
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
PY = sys.executable


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False




def kill_stale_on_port(port: int) -> int:
    """清理占用该端口的残留 uvicorn（只杀监听进程，不误伤其它 python）。

    ⚠️ 踩坑记录：不能按 python.exe 全局清理 —— 本机 python 多为宿主工具链在用
    （Marvis runtime），误杀会直接断掉当前会话的 shell。必须按「监听该端口的进程」
    精确定位，否则多轮测试的残留 worker 会互相抢 CPU，把结果搅成噪声。
    """
    killed = 0
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue"
             f" | Select-Object -ExpandProperty OwningProcess -Unique; $c"],
            capture_output=True, text=True, timeout=30)
        for token in (out.stdout or "").split():
            if token.strip().isdigit():
                try:
                    subprocess.run(["taskkill", "/PID", token.strip(), "/T", "/F"],
                                   capture_output=True, timeout=30)
                    killed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return killed

def wait_ready(port: int, timeout: float = 60.0) -> bool:
    import urllib.request
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def run_locust(host: str, users: int, duration: int, rate: int, prefix: Path) -> dict:
    import csv as _csv
    cmd = [PY, "-m", "locust", "-f", str(BENCH / "locustfile.py"),
           "--host", host, "--headless", "-u", str(users), "-r", str(rate),
           "-t", f"{duration}s", "--csv", str(prefix), "--only-summary",
           "--loglevel", "ERROR"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    stats = prefix.with_name(prefix.name + "_stats.csv")
    if not stats.exists():
        return {"error": (proc.stderr or "no stats")[-200:]}
    with stats.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(_csv.DictReader(f, strict=False))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if not agg:
        return {"error": "no aggregated row"}

    def num(k: str) -> float:
        try:
            return float((agg.get(k) or "0").strip() or 0)
        except ValueError:
            return 0.0

    total = int(num("Request Count"))
    fails = int(num("Failure Count"))
    return {
        "requests": total,
        "failures": fails,
        "failure_rate": round(fails / total, 4) if total else None,
        "rps": round(num("Requests/s"), 2),
        "p50_ms": int(num("50%")),
        "p95_ms": int(num("95%")),
        "p99_ms": int(num("99%")),
    }


def start_server(port: int, workers: int, log: Path, offline: bool = True) -> subprocess.Popen:
    """起服务。offline=True 时强制清空 LLM 配置，隔离上游限流对架构测量的污染。

    ⚠️ 踩坑记录：首版脚本继承了 .env 里的真实 LLM Key，多 worker 把并发打上去后
    触发上游 429（实测并发上限 16 based on balance），请求转入重试/降级，
    反而让「多 worker 看起来更慢」—— 那是限流假象，不是架构结论。
    测架构扩展性必须先把上游变量摘干净。
    """
    env = dict(**__import__("os").environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"
    env["BENCH_OFFLINE"] = "1"   # 压测统一离线，杜绝继承 .env 真 Key
    if offline:
        for k in ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            env.pop(k, None)
        env["LLM_API_KEY"] = ""          # 空串触发应用内降级分支
        env.pop("OPENAI_API_KEY", None)
        # OTel 未部署时每批 span 都会重试连接，徒增噪声与延迟
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    return subprocess.Popen(
        [PY, "-X", "utf8", "-m", "uvicorn", "enterprise_agent.api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
         "--workers", str(workers)],
        cwd=str(ROOT), env=env,
        stdout=log.open("w", encoding="utf-8"), stderr=subprocess.STDOUT,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="多 worker 横向扩展对比")
    ap.add_argument("--levels", default="20,50,100")
    ap.add_argument("--workers", default="1,2,4")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--rate", type=int, default=10)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--out", default=str(BENCH / "worker_scaling_result.json"))
    ap.add_argument("--with-llm", action="store_true",
                    help="⚠️ 会用真实 LLM Key 打真实计费流量。上游并发上限低（实测 16），"
                         "高并发必然触发 429，测出来的是限流不是架构。默认关闭。")
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",")]
    worker_list = [int(x) for x in args.workers.split(",")]
    host = f"http://127.0.0.1:{args.port}"
    log = BENCH / "worker_scaling_server.log"

    all_rows = []
    for w in worker_list:
        print(f"\n{'=' * 66}\nworker = {w}\n{'=' * 66}", flush=True)
        killed = kill_stale_on_port(args.port)
        if killed:
            print(f"  已清理端口 {args.port} 上的 {killed} 个残留进程")
            time.sleep(2)
        if not port_free(args.port):
            print(f"  端口 {args.port} 仍被占用，跳过该配置")
            continue
        proc = start_server(args.port, w, log, offline=not args.with_llm)
        if not args.with_llm:
            print("  （离线模式：已清空 LLM 配置，避免上游限流污染架构测量）")
        try:
            if not wait_ready(args.port, timeout=90):
                print("  服务未就绪，日志尾部：")
                print("  " + log.read_text(encoding="utf-8", errors="replace")[-500:])
                continue
            for u in levels:
                r = run_locust(host, u, args.duration, args.rate, BENCH / f"ws_{w}_{u}")
                if "error" in r:
                    print(f"  并发 {u:>3}: 失败 {r['error'][:80]}")
                    continue
                r.update({"workers": w, "users": u})
                all_rows.append(r)
                print(f"  并发 {u:>3}: {r['requests']:>5} 请求 / {r['failures']} 失败 "
                      f"({(r['failure_rate'] or 0) * 100:>5.2f}%)  {r['rps']:>6} req/s  "
                      f"P50={r['p50_ms']}ms  P95={r['p95_ms']}ms", flush=True)
                time.sleep(3)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
            kill_stale_on_port(args.port)
            time.sleep(4)

    Path(args.out).write_text(json.dumps({
        "levels": levels, "workers": worker_list, "results": all_rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 汇总表 ----
    print(f"\n{'=' * 74}\n多 worker 横向对比汇总\n{'=' * 74}")
    print(f"{'并发':>6}{'1 worker':>12}{'2 workers':>12}{'4 workers':>12}   扩展效率")
    print("-" * 74)
    for u in levels:
        cells = []
        base = None
        for w in worker_list:
            row = next((r for r in all_rows if r["users"] == u and r["workers"] == w), None)
            v = row["rps"] if row else None
            cells.append(v)
            if w == worker_list[0]:
                base = v
        if base and cells[-1]:
            eff = cells[-1] / base / worker_list[-1] * 100
            eff_s = f"{eff:.0f}%"
        else:
            eff_s = "-"
        cs = "".join(f"{(str(c) if c else '-'):>12}" for c in cells)
        print(f"{u:>6}{cs}   {eff_s}")
    print("=" * 74)
    print(f"\n结果已写入 {args.out}")
    print("扩展效率 = 4worker 吞吐 / (1worker 吞吐 × 4)；100% 表示完全线性，<100% 表示存在串行瓶颈")

    # 清理中间 CSV；日志文件可能被 uvicorn 子进程仍持有句柄，删不掉不算失败
    for f in BENCH.glob("ws_*"):
        f.unlink(missing_ok=True)
    try:
        log.unlink()
    except OSError:
        print(f"（提示：服务日志 {log.name} 仍被占用，留待下次运行覆盖）")


if __name__ == "__main__":
    main()
