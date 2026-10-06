"""阶梯压测：并发 10 → 20 → 50 → 100 逐级加压，找吞吐饱和拐点。

为什么用阶梯而不是单点：单点压测只能得到「某个并发下的表现」，
阶梯压测能画出 **吞吐-并发曲线**，从而回答「系统在哪个并发点不再线性收益」——
这正是 Helm HPA maxReplicas 该设多少的依据。

用法：
    python bench/staircase.py --host http://127.0.0.1:8080 --levels 10,20,50,100 --duration 30
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
LOCUST = [sys.executable, "-m", "locust"]


def run_level(host: str, users: int, rate: int, duration: int, csv_prefix: Path) -> dict:
    """跑一级阶梯，返回解析后的统计（读 locust 产出的 *_stats.csv）。"""
    cmd = LOCUST + [
        "-f", str(BENCH / "locustfile.py"),
        "--host", host, "--headless",
        "-u", str(users), "-r", str(rate), "-t", f"{duration}s",
        "--csv", str(csv_prefix), "--only-summary", "--loglevel", "ERROR",
    ]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    wall = time.perf_counter() - t0
    if proc.returncode not in (0, 1):  # locust 用 1 表示有失败请求
        return {"users": users, "error": (proc.stderr or proc.stdout)[-400:]}

    stats_csv = csv_prefix.with_name(csv_prefix.name + "_stats.csv")
    if not stats_csv.exists():
        return {"users": users, "error": "locust 未产出 stats.csv", "wall_seconds": round(wall, 1)}

    import csv as _csv
    with stats_csv.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(_csv.DictReader(f))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)
    if not agg:
        return {"users": users, "error": "stats.csv 无 Aggregated 行"}

    def num(k: str) -> float | None:
        v = (agg.get(k) or "").strip()
        try:
            return float(v)
        except ValueError:
            return None

    total = int(num("Request Count") or 0)
    fails = int(num("Failure Count") or 0)
    return {
        "users": users,
        "requests": total,
        "failures": fails,
        "failure_rate": round(fails / total, 4) if total else None,
        "rps": round(num("Requests/s") or 0, 2),
        "p50_ms": int(num("50%") or 0),
        "p95_ms": int(num("95%") or 0),
        "p99_ms": int(num("99%") or 0),
        "max_ms": int(num("Max Response Time") or 0),
        "wall_seconds": round(wall, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="阶梯压测：找吞吐饱和拐点")
    ap.add_argument("--host", default="http://127.0.0.1:8080")
    ap.add_argument("--levels", default="10,20,50,100")
    ap.add_argument("--duration", type=int, default=30, help="每级持续秒数")
    ap.add_argument("--rate", type=int, default=10, help="每秒拉起用户数")
    ap.add_argument("--out", default=str(BENCH / "staircase_result.json"))
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",")]
    print(f"阶梯压测 {args.host}  级别={levels}  每级 {args.duration}s\n", flush=True)

    results = []
    for u in levels:
        print(f"── 并发 {u} ──", flush=True)
        prefix = BENCH / f"stair_{u}"
        r = run_level(args.host, u, args.rate, args.duration, prefix)
        results.append(r)
        if "error" in r:
            print(f"   失败: {r['error'][:200]}", flush=True)
        else:
            print(f"   {r['requests']} 请求 / {r['failures']} 失败 "
                  f"({(r['failure_rate'] or 0) * 100:.2f}%)  "
                  f"{r['rps']} req/s  P50={r['p50_ms']}ms  "
                  f"P95={r['p95_ms']}ms  P99={r['p99_ms']}ms", flush=True)
        time.sleep(3)  # 级间冷却，避免上一级残留影响下一级

    Path(args.out).write_text(json.dumps({
        "host": args.host, "duration_per_level": args.duration,
        "results": results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 74)
    print("阶梯压测汇总")
    print("=" * 74)
    print(f"{'并发':>6}{'请求数':>9}{'失败率':>9}{'req/s':>9}{'P50':>9}{'P95':>9}{'P99':>9}")
    print("-" * 74)
    for r in results:
        if "error" in r:
            print(f"{r['users']:>6}   错误")
            continue
        print(f"{r['users']:>6}{r['requests']:>9}{(r['failure_rate'] or 0) * 100:>8.2f}%"
              f"{r['rps']:>9}{r['p50_ms']:>9}{r['p95_ms']:>9}{r['p99_ms']:>9}")
    print("=" * 74)
    print(f"\n结果已写入 {args.out}")

    # 自动判定饱和拐点：req/s 相对上一级增幅 < 15% 即视为饱和
    print("\n饱和拐点分析（每级相对上一级的吞吐增幅）:")
    for prev, cur in zip(results, results[1:], strict=False):
        if "error" in prev or "error" in cur or not prev.get("rps"):
            continue
        gain = (cur["rps"] - prev["rps"]) / prev["rps"] * 100
        mark = "  ← 饱和" if gain < 15 else ""
        print(f"  {prev['users']:>3} → {cur['users']:<3} : {prev['rps']:>6} → {cur['rps']:<6} "
              f"req/s  ({gain:+.1f}%){mark}")


if __name__ == "__main__":
    main()
