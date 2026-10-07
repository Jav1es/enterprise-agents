"""决定性实验：多 worker 变慢到底是「共享资源竞争」还是「单纯的分发开销」？

背景：worker_scaling 实测出现反常 —— 并发越高，多 worker 越慢
（100 并发：1 worker 112.93 req/s，2 worker 10.36，4 worker 4.15）。
可能的解释有两个，必须区分开：

  A. 共享资源竞争（Chroma PersistentClient / Redis / 事件循环外的锁）
  B. Locust 客户端本身成为瓶颈（所有 worker 都在抢同一个压测客户端的 CPU）

区分方法：**打一个完全不碰应用逻辑的端点**（/health），
且让压测客户端与服务端跑在同一台机器上必然互相抢 CPU —— 所以要对比两组：
  - 组1：压 /health（极轻，几乎无业务逻辑）
  - 组2：压 /v1/chat（走完整编排 + Chroma 检索 + 记忆）

若组1 也出现「多 worker 更慢」⇒ 是 B（压测侧瓶颈），与架构无关。
若组1 正常线性、组2 恶化 ⇒ 是 A（共享资源竞争），是真实的架构问题。

用法：
    python bench/isolate_contention.py --users 100 --duration 20
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
PY = sys.executable


def start_server(port: int, workers: int, offline: bool = True):
    import os
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"
    if offline:
        env["LLM_API_KEY"] = ""
        env.pop("OPENAI_API_KEY", None)
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
    return subprocess.Popen(
        [PY, "-X", "utf8", "-m", "uvicorn", "enterprise_agent.api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
         "--workers", str(workers)],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_ready(port: int, timeout: float = 90.0) -> bool:
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


def kill_port(port: int) -> None:
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
    except Exception:
        pass


def run_load(port: int, users: int, duration: int, tag: str) -> dict:
    """只压 /health：排除一切应用逻辑。"""
    prefix = BENCH / f"iso_{tag}"
    cmd = [PY, "-X", "utf8", "-m", "locust", "-f", str(BENCH / "health_only.py"),
           "--host", f"http://127.0.0.1:{port}", "--headless",
           "-u", str(users), "-r", "20", "-t", f"{duration}s",
           "--csv", str(prefix), "--only-summary", "--loglevel", "ERROR"]
    subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 120)
    stats = prefix.with_name(prefix.name + "_stats.csv")
    if not stats.exists():
        return {"error": "no stats"}
    with stats.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(_csv.DictReader(f, strict=False))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if not agg:
        return {"error": "no agg"}

    def num(k: str) -> float:
        try:
            return float((agg.get(k) or "0").strip() or 0)
        except ValueError:
            return 0.0

    total = int(num("Request Count"))
    return {"requests": total, "failures": int(num("Failure Count")),
            "rps": round(num("Requests/s"), 2), "p50_ms": int(num("50%")),
            "p95_ms": int(num("95%"))}


def main() -> None:
    ap = argparse.ArgumentParser(description="隔离实验：区分共享资源竞争 vs 压测侧瓶颈")
    ap.add_argument("--port", type=int, default=8097)
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--duration", type=int, default=20)
    ap.add_argument("--out", default=str(BENCH / "isolate_result.json"))
    args = ap.parse_args()

    rows = []
    for w in (1, 2, 4):
        kill_port(args.port)
        time.sleep(3)
        p = start_server(args.port, w)
        try:
            if not wait_ready(args.port):
                print(f"worker={w} 未就绪，跳过", flush=True)
                continue
            r = run_load(args.port, args.users, args.duration, f"h{w}")
            r.update({"workers": w, "target": "/health"})
            rows.append(r)
            print(f"  worker={w}  /health  {r.get('rps')} req/s  "
                  f"P50={r.get('p50_ms')}ms  P95={r.get('p95_ms')}ms  "
                  f"({r.get('requests')} 请求 / {r.get('failures')} 失败)", flush=True)
        finally:
            p.terminate()
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
            kill_port(args.port)
            time.sleep(4)

    Path(args.out).write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("\n" + "=" * 62)
    print("隔离实验结论（只压 /health，完全不碰应用逻辑）")
    print("=" * 62)
    base = next((r["rps"] for r in rows if r["workers"] == 1), None)
    for r in rows:
        eff = f"（相对 1worker {r['rps'] / base * 100:.0f}%）" if base else ""
        print(f"  {r['workers']} worker: {r['rps']:>8} req/s  "
              f"理想={r['workers']}×{base if base else 0:.0f}={r['workers'] * base if base else 0:.0f} {eff}")
    print("=" * 62)
    print("若 /health 也随 worker 增多而下降 ⇒ 瓶颈在压测客户端/本机调度，与架构无关")
    print("若 /health 保持线性 ⇒ 瓶颈在应用的共享资源（Chroma/Redis/编排）")
    for f in BENCH.glob("iso_*"):
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
