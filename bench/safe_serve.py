"""压测安全闸：起压测服务前强制走这里，杜绝「顺手就用真 Key」。

背景（真实踩坑）：多轮压测里，服务默认继承 .env 的真实 LLM Key，
于是每次并发 100 都在打真实计费调用；期间还因 429 重试白烧一轮。
根子在于「起服务」和「花钱」之间没有任何闸门。

本脚本把这道闸门显式化：
- 默认 offline=True：清空所有 LLM/OTel 环境变量，服务走本地降级路径，零计费
- 要用真 Key 必须显式传 --allow-llm-cost，并打印本次预计调用量与成本估算
- 额外支持 --max-calls 硬上限，超了就自杀（给 Locust 的 stop 事件用）

用法：
    # 零成本（默认，容量测试用这个）
    python bench/safe_serve.py --port 8080 --workers 1

    # 真 Key（会花钱，会先打印成本预估）
    python bench/safe_serve.py --port 8080 --allow-llm-cost --max-calls 50
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# deepseek 官方价格（美元 / 百万 token），仅用于给用户一个量级感知
PRICE_IN_PER_MTOK = 0.14
PRICE_OUT_PER_MTOK = 0.28


def estimate_cost(calls: int, in_tokens: int = 800, out_tokens: int = 300) -> float:
    return calls * (in_tokens / 1e6 * PRICE_IN_PER_MTOK
                    + out_tokens / 1e6 * PRICE_OUT_PER_MTOK)


def main() -> None:
    ap = argparse.ArgumentParser(description="压测服务安全闸")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--allow-llm-cost", action="store_true",
                    help="⚠️ 显式允许使用真实 LLM Key（会产生真实计费）")
    ap.add_argument("--max-calls", type=int, default=0,
                    help="调用数上限，0 表示不限制（仅在 --allow-llm-cost 时有意义）")
    ap.add_argument("--print-off", action="store_true", help="仅打印环境决策，不启动服务")
    args = ap.parse_args()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"

    if not args.allow_llm_cost:
        for k in ("LLM_API_KEY", "OPENAI_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
                  "OTEL_EXPORTER_OTLP_ENDPOINT"):
            env.pop(k, None)
        env["LLM_API_KEY"] = ""          # 空串触发应用内降级分支（已修复）
        env["BENCH_OFFLINE"] = "1"
        print("=" * 66)
        print("压测模式：离线（零计费）")
        print("  已清空 LLM_API_KEY / OPENAI_API_KEY / LLM_BASE_URL / OTel 端点")
        print("  服务将走本地降级链路，容量数字代表「无 LLM」场景")
        print("=" * 66)
    else:
        print("=" * 66)
        print("⚠️ 压测模式：真实 LLM（会产生真实计费）")
        if args.max_calls:
            print(f"  调用数硬上限：{args.max_calls} 次")
        else:
            print("  ⚠️ 未设置调用上限！建议同时用 --max-calls 限制")
        print("  按每次约 800 in / 300 out token 估算：")
        for n in (50, 200, 1000):
            print(f"    {n:>5} 次调用 ≈ ${estimate_cost(n):.4f}")
        print("  提醒：并发越高打满上游限流越快，429 重试会产生额外调用")
        print("=" * 66)

    if args.print_off:
        return

    cmd = [sys.executable, "-X", "utf8", "-m", "uvicorn",
           "enterprise_agent.api.main:app",
           "--host", args.host, "--port", str(args.port),
           "--log-level", "warning"]
    if args.workers > 1:
        cmd += ["--workers", str(args.workers)]
    if args.max_calls:
        env["BENCH_MAX_CALLS"] = str(args.max_calls)

    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    print(f"服务已启动 PID={proc.pid}（Ctrl+C 停止）")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


if __name__ == "__main__":
    main()
