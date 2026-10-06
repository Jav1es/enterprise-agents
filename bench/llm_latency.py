"""LLM 延迟分解：把「一次对话的总延迟」拆成首 token 与生成两段。

为什么需要这个：降级模式（无 LLM Key）下编排链路约 2.4 秒，那全部是本地编排成本。
接上真实 LLM 后总延迟由两部分构成 —— 首 token（网络 + 模型排队）与后续生成。
不知道这个比例，就无法判断瓶颈在「模型」还是「我的编排代码」，
也才知道该优化哪一侧。

用法（需 .env 里配好 LLM_API_KEY）：
    python bench/llm_latency.py --n 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_dotenv(path: Path) -> None:
    """极简 .env 读取（避免额外依赖）。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def one_call(url: str, model: str, key: str, prompt: str) -> dict:
    """发一次 chat/completions，测 TTFT 与总时长。"""
    import httpx

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "stream": True,  # 必须流式才能测首 token
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    t0 = time.perf_counter()
    ttft = None
    chunks = 0
    total_text = []
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{url}/chat/completions",
                                 headers=headers, json=payload) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    chunks += 1
                    total_text.append(content)
    total = time.perf_counter() - t0
    return {
        "ttft_ms": round((ttft or total) * 1000, 1),
        "total_ms": round(total * 1000, 1),
        "chunks": chunks,
        "gen_chars": len("".join(total_text)),
    }


async def main() -> None:
    ap = argparse.ArgumentParser(description="LLM 首 token 延迟分解")
    ap.add_argument("--n", type=int, default=5, help="调用次数（每条都是计费调用，默认保守取值）")
    ap.add_argument("--prompt", default="用三句话说明什么是 RAG。")
    ap.add_argument("--out", default=str(ROOT / "bench" / "llm_latency.json"))
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.environ.get("LLM_API_KEY", "")
    url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("LLM_MODEL", "")
    if not key or not url:
        print("未配置 LLM_API_KEY / LLM_BASE_URL，跳过（不报错退出）")
        return

    print(f"模型: {model}  端点: {url}  次数: {args.n}\n")
    rows = []
    for i in range(args.n):
        try:
            r = await one_call(url, model, key, args.prompt)
            rows.append(r)
            print(f"  #{i+1}  首 token {r['ttft_ms']:>8.1f} ms   "
                  f"总耗时 {r['total_ms']:>8.1f} ms   {r['chunks']} 块 / {r['gen_chars']} 字")
        except Exception as exc:
            print(f"  #{i+1}  失败: {type(exc).__name__}: {exc}")
        await asyncio.sleep(1)

    if not rows:
        print("\n无成功样本，不产出报告")
        return

    ttf = [r["ttft_ms"] for r in rows]
    tot = [r["total_ms"] for r in rows]
    ratio = statistics.mean(ttf) / statistics.mean(tot) * 100 if tot else 0

    print("\n" + "=" * 62)
    print("LLM 延迟分解（真实计费调用）")
    print("=" * 62)
    print(f"  样本数        : {len(rows)}")
    print(f"  首 token 中位 : {statistics.median(ttf):.1f} ms")
    print(f"  首 token 均值 : {statistics.mean(ttf):.1f} ms")
    print(f"  总耗时中位    : {statistics.median(tot):.1f} ms")
    print(f"  总耗时均值    : {statistics.mean(tot):.1f} ms")
    print(f"  首 token 占比 : {ratio:.1f}%  ← 占总延迟的比例")
    print("=" * 62)

    # 写盘是阻塞 IO，放进线程避免阻塞事件循环（ruff ASYNC240）
    payload = json.dumps({
        "model": model, "endpoint": url, "samples": len(rows),
        "ttft_ms_median": statistics.median(ttf), "ttft_ms_mean": round(statistics.mean(ttf), 1),
        "total_ms_median": statistics.median(tot), "total_ms_mean": round(statistics.mean(tot), 1),
        "ttft_share_pct": round(ratio, 1), "raw": rows,
    }, ensure_ascii=False, indent=2)
    await asyncio.to_thread(
        Path(args.out).write_text, payload, encoding="utf-8")
    print(f"\n结果已写入 {args.out}")
    print("\n对比：降级模式（无 LLM）下本地编排基线 P95 ≈ 2400 ms。")


if __name__ == "__main__":
    asyncio.run(main())
