"""内存泄漏长稳监控：持续打流量 + 采样 RSS，做趋势判定。

为什么需要它：「100 并发 0 失败」只能证明**没有竞态**，不能证明**没有泄漏**。
内存泄漏的特征是慢性的 —— 单次压测看不出来，要跑够长时间才能看到 RSS 单调上升。

判定方法（比肉眼看曲线可靠）：
1. 采集 RSS 序列
2. 取前 20% 作为基线（预热期，JIT / 连接池 / 索引预热都还在涨）
3. 对「基线后」的部分做**最小二乘线性回归**，得到每小时漂移量
4. 判据：漂移率 < 1%/小时 且 末段 RSS < 基线均值 × 1.5 ⇒ 无明显泄漏

用法：
    # 监控一个已在运行的 uvicorn（--port 指服务端口）
    python bench/soak_monitor.py --port 8080 --users 20 --duration 7200
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent


def rss_mb(port: int) -> float | None:
    """取服务进程（含其 worker 子进程）的总 RSS，单位 MB。

    用 psutil 不可靠（Windows 下子进程归属复杂），改用 tasklist 按端口找 PID，
    再用 wmic/PowerShell 取 WorkingSet。优先读 uvicorn 记录的 pid 文件。
    """
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$c=(Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue)"
             f"| Select-Object -ExpandProperty OwningProcess -Unique;"
             "if($c){$p=Get-Process -Id $c -EA SilentlyContinue;"
             "[math]::Round((($p|Measure-Object WorkingSet64 -Sum).Sum/1MB),1)}"],
            capture_output=True, text=True, timeout=30)
        v = (out.stdout or "").strip()
        return float(v) if v and v != "0" else None
    except Exception:
        return None


def start_load(host: str, users: int, rate: int, duration: int, prefix: Path) -> subprocess.Popen:
    cmd = [sys.executable, "-X", "utf8", "-m", "locust", "-f", str(BENCH / "locustfile.py"),
           "--host", host, "--headless", "-u", str(users), "-r", str(rate),
           "-t", f"{duration}s", "--csv", str(prefix), "--only-summary",
           "--loglevel", "ERROR"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fetch_json(url: str) -> dict | None:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as r:
            if r.status == 200:
                return json.loads(r.read().decode("utf-8"))
    except Exception:
        pass
    return None


def health_ok(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def linreg_slope_per_hour(xs: list[float], ys: list[float]) -> float:
    """最小二乘斜率，换算成「每小时变化量」。"""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / denom
    return slope * 3600.0  # 每秒斜率 → 每小时


def main() -> None:
    ap = argparse.ArgumentParser(description="内存泄漏长稳监控")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rate", type=int, default=5)
    ap.add_argument("--duration", type=int, default=7200, help="秒，默认 2 小时")
    ap.add_argument("--interval", type=int, default=60, help="采样间隔秒")
    ap.add_argument("--allow-llm-cost", action="store_true",
                    help="⚠️ 允许对「挂着真实 LLM Key 的服务」跑长稳（会持续计费）。"
                         "默认关闭：检测到未武装预算时会拒绝启动。")
    ap.add_argument("--out", default=str(BENCH / "soak_result.json"))
    args = ap.parse_args()

    host = f"http://127.0.0.1:{args.port}"
    if not health_ok(host):
        print(f"服务 {host} 不可达，请先启动 uvicorn", file=sys.stderr)
        sys.exit(2)

    # ⚠️ 成本闸：本脚本不起服务，但会持续打流量。若被监控的服务带着真实 LLM Key，
    # 长稳测试会以「每分钟几十次」的速率持续计费 —— 实测踩过，心智负担很重。
    # 这里主动查 /health 的预算状态：未武装预算且 workflow 已就绪（说明可能挂着真 Key）
    # 就直接拒绝启动，要跑请先用 bench/safe_serve.py（默认离线）或设 BENCH_MAX_CALLS。
    if not args.allow_llm_cost:
        st = fetch_json(f"{host}/health")
        b = (st or {}).get("llm_budget") or {}
        wf = (st or {}).get("workflow")
        llm_mode = (st or {}).get("llm", {}).get("mode")
        # stub 模式零成本（llm.mode=stub），不拦
        if wf == "ready" and not b.get("enabled") and llm_mode != "stub":
            print("=" * 66)
            print("拒绝启动：检测到目标服务 workflow 就绪且未武装调用预算，")
            print("这意味着它很可能挂着真实 LLM Key，长稳测试会持续产生计费调用。")
            print("")
            print("  离线跑（零成本）：")
            print(f"    python bench/safe_serve.py --port {args.port} --workers 1")
            print(f"    python bench/soak_monitor.py --port {args.port}")
            print("  确要用真 Key，请显式加 --allow-llm-cost 并设置服务端 BENCH_MAX_CALLS")
            print("=" * 66)
            sys.exit(3)
        print(f"成本闸：通过（workflow={wf}, budget={b}）")

    prefix = BENCH / "soak"
    load = start_load(host, args.users, args.rate, args.duration, prefix)
    rows: list[dict] = []
    t0 = time.time()
    print(f"长稳监控启动：并发 {args.users} / 计划 {args.duration // 60} 分钟 / "
          f"每 {args.interval}s 采样一次", flush=True)

    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= args.duration:
                break
            rss = rss_mb(args.port)
            ok = health_ok(host)
            rows.append({"t": round(elapsed), "rss_mb": rss, "healthy": ok})
            if rss is not None:
                print(f"  t={elapsed/60:>6.1f}min  RSS={rss:>8.1f}MB  "
                      f"health={'OK' if ok else 'FAIL'}", flush=True)
            else:
                print(f"  t={elapsed/60:>6.1f}min  RSS=读取失败  "
                      f"health={'OK' if ok else 'FAIL'}", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n收到中断，提前结束")
    finally:
        load.terminate()
        try:
            load.wait(timeout=30)
        except subprocess.TimeoutExpired:
            load.kill()

    # ---- 趋势判定 ----
    good = [r for r in rows if r["rss_mb"] is not None]
    verdict: dict = {"samples": len(good), "healthy_all": all(r["healthy"] for r in rows)}
    if len(good) >= 6:
        warm = max(1, len(good) // 5)              # 前 20% 作预热基线
        base = good[:warm]
        rest = good[warm:]
        base_mean = statistics.mean(r["rss_mb"] for r in base)
        rest_mean = statistics.mean(r["rss_mb"] for r in rest)
        xs = [r["t"] for r in rest]
        ys = [r["rss_mb"] for r in rest]
        drift = linreg_slope_per_hour(xs, ys)
        peak = max(r["rss_mb"] for r in good)
        drift_pct = (drift / base_mean * 100) if base_mean else 0.0
        verdict.update({
            "baseline_mb": round(base_mean, 1),
            "after_warmup_mean_mb": round(rest_mean, 1),
            "peak_mb": round(peak, 1),
            "drift_mb_per_hour": round(drift, 2),
            "drift_pct_per_hour": round(drift_pct, 3),
            "ratio_peak_over_baseline": round(peak / base_mean, 2) if base_mean else None,
        })
        leak = abs(drift_pct) >= 1.0 or (base_mean and peak / base_mean >= 1.5)
        verdict["leak_suspected"] = bool(leak)
        verdict["conclusion"] = (
            f"内存泄漏嫌疑：漂移 {drift_pct:+.2f}%/h，峰值/基线 "
            f"{peak / base_mean:.2f}×" if leak else
            f"未见明显泄漏：漂移 {drift_pct:+.2f}%/h，峰值/基线 "
            f"{peak / base_mean:.2f}×（判据 <1%/h 且 <1.5×）"
        )

    Path(args.out).write_text(json.dumps(
        {"config": vars(args), "rows": rows, "verdict": verdict},
        ensure_ascii=False, indent=2), encoding="utf-8")

    with (BENCH / "soak_rss.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_sec", "rss_mb", "healthy"])
        for r in rows:
            w.writerow([r["t"], r["rss_mb"], r["healthy"]])

    print("\n" + "=" * 64)
    print("长稳测试结论")
    print("=" * 64)
    for k, v in verdict.items():
        print(f"  {k}: {v}")
    print(f"\n明细已写入 {args.out} 与 soak_rss.csv")


if __name__ == "__main__":
    main()
