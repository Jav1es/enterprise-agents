"""完整编排路径下的多 worker 横向对比（零成本）。

与 worker_scaling.py 的区别：那个测的是降级路径（503 快速返回），
结论无效。本脚本启用 StubLLM + 依赖 mini-redis，让五个编排节点全量执行，
测的是「真实架构能否横向扩展」。

用法：
    # 终端 1
    python bench/mini_redis.py --port 6379
    # 终端 2
    python bench/stub_worker_scaling.py --users 20,50 --workers 1,2,4 --duration 20
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import os
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


def kill_port(port: int) -> int:
    killed = 0
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$c=Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue"
             f"| Select-Object -ExpandProperty OwningProcess -Unique; $c"],
            capture_output=True, text=True, timeout=30)
        for tok in (out.stdout or "").split():
            if tok.strip().isdigit():
                subprocess.run(["taskkill", "/PID", tok.strip(), "/T", "/F"],
                               capture_output=True, timeout=30)
                killed += 1
    except Exception:
        pass
    return killed


def start(port: int, workers: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"
    env["EA_STUB_LLM"] = "1"      # 零成本：离线路径模型
    env["LLM_API_KEY"] = ""       # 明确无 Key
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    env["BENCH_OFFLINE"] = "1"
    cmd = [PY, "-X", "utf8", "-m", "uvicorn", "enterprise_agent.api.main:app",
           "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    if workers > 1:
        cmd += ["--workers", str(workers)]
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_ready(port: int, timeout: float = 90.0) -> bool:
    import urllib.request
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                import json as _j
                st = _j.loads(r.read().decode())
                if st.get("workflow") == "ready":
                    return True
        except Exception:
            time.sleep(1)
    return False


def load(port: int, users: int, duration: int, tag: str) -> dict:
    prefix = BENCH / f"sws_{tag}"
    subprocess.run(
        [PY, "-X", "utf8", "-m", "locust", "-f", str(BENCH / "locustfile.py"),
         "--host", f"http://127.0.0.1:{port}", "--headless",
         "-u", str(users), "-r", "10", "-t", f"{duration}s",
         "--csv", str(prefix), "--only-summary", "--loglevel", "ERROR"],
        capture_output=True, text=True, timeout=duration + 120)
    stats = prefix.with_name(prefix.name + "_stats.csv")
    if not stats.exists():
        return {"error": "no stats"}
    with stats.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(_csv.DictReader(f, strict=False))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    chat = next((r for r in rows if r.get("Name") == "POST /v1/chat"), None)
    if not agg:
        return {"error": "no agg"}

    def num(row, k: str) -> float:
        try:
            return float((row.get(k) or "0").strip() or 0)
        except ValueError:
            return 0.0

    return {
        "requests": int(num(agg, "Request Count")),
        "failures": int(num(agg, "Failure Count")),
        "rps": round(num(agg, "Requests/s"), 2),
        "p50_ms": int(num(agg, "50%")),
        "p95_ms": int(num(agg, "95%")),
        "chat_avg_ms": round(num(chat, "Average Response Time"), 1) if chat else None,
        "chat_p95_ms": int(num(chat, "95%")) if chat else None,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="完整编排路径多 worker 对比（零成本）")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--users", default="20,50")
    ap.add_argument("--workers", default="1,2,4")
    ap.add_argument("--duration", type=int, default=20)
    ap.add_argument("--out", default=str(BENCH / "stub_worker_scaling_result.json"))
    args = ap.parse_args()

    levels = [int(x) for x in args.users.split(",")]
    ws = [int(x) for x in args.workers.split(",")]

    print("前置检查：Redis 6379 是否可达", flush=True)
    import socket as sk
    try:
        with sk.create_connection(("127.0.0.1", 6379), timeout=3):
            print("  Redis OK", flush=True)
    except Exception:
        print("  ✗ Redis 未运行，请先 python bench/mini_redis.py --port 6379", file=sys.stderr)
        sys.exit(2)

    rows = []
    for w in ws:
        print(f"\n=== worker = {w} ===", flush=True)
        kill_port(args.port)
        time.sleep(3)
        p = start(args.port, w)
        try:
            if not wait_ready(args.port):
                print("  未就绪，跳过", flush=True)
                continue
            for u in levels:
                r = load(args.port, u, args.duration, f"{w}_{u}")
                if "error" in r:
                    print(f"  并发 {u}: {r['error']}", flush=True)
                    continue
                r.update({"workers": w, "users": u})
                rows.append(r)
                print(f"  并发 {u:>3}: {r['requests']:>4} 请求 / {r['failures']} 失败 "
                      f"{r['rps']:>6} req/s  P50={r['p50_ms']}ms P95={r['p95_ms']}ms  "
                      f"| chat avg={r['chat_avg_ms']}ms p95={r['chat_p95_ms']}ms", flush=True)
                time.sleep(3)
        finally:
            p.terminate()
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
            kill_port(args.port)
            time.sleep(4)

    Path(args.out).write_text(json.dumps({"results": rows}, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print(f"\n{'=' * 76}\n完整编排路径 · 多 worker 对比（StubLLM，零成本）\n{'=' * 76}")
    print(f"{'并发':>6}{'1w':>10}{'2w':>10}{'4w':>10}   扩展效率(4w)")
    print("-" * 76)
    for u in levels:
        vals = []
        for w in ws:
            r = next((x for x in rows if x["users"] == u and x["workers"] == w), None)
            vals.append(r["rps"] if r else None)
        base = vals[0] if vals and vals[0] else None
        eff = f"{(vals[-1] / (base * ws[-1]) * 100):.0f}%" if base and vals[-1] else "-"
        cells = "".join(f"{(str(v) if v else '-'):>10}" for v in vals)
        print(f"{u:>6}{cells}   {eff}")
    print("=" * 76)
    print("\n分端点（chat 平均 / p95，ms）：")
    for r in rows:
        print(f"  worker={r['workers']} 并发={r['users']:>3}  "
              f"chat avg={r['chat_avg_ms']}ms  p95={r['chat_p95_ms']}ms")
    print(f"\n结果已写入 {args.out}")
    for f in BENCH.glob("sws_*"):
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
