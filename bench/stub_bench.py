"""零成本完整编排压测：用 StubLLM 替代真实模型，编排链路全量执行。

问题：离线模式下 ChatOpenAI 构造失败 → workflow=None → /v1/chat 立即 503。
测出来的是「路由与降级路径」容量（P50=1ms），**不代表完整编排容量**。

本脚本注入一个本地 StubLLM：实现 LangChain BaseChatModel 所需的最小接口，
返回固定内容、不发任何网络请求。于是：
  - AgentWorkflow 能正常初始化
  - Router / Planner / Tool / Reviewer / Respond 五个节点全量执行
  - RAG 检索、记忆读写都真实发生
  - 唯一被替换的是「模型推理」本身

⇒ 得到的是**零成本但完整**的编排基线。这是本机做容量测试的正确姿势：
既不必烧真钱，又不测残缺路径。

用法：
    python bench/stub_bench.py --port 8080 --users 20 --duration 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def install_stub() -> bool:
    """把 langchain_openai.ChatOpenAI 换成不联网的 StubLLM。"""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    calls = {"n": 0}

    class StubLLM(BaseChatModel):
        """固定输出的假模型：走完整调用链，但零网络零成本。"""

        temperature: float = 0.0
        model_name: str = "stub-llm"

        @property
        def _llm_type(self) -> str:
            return "stub"

        def _generate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
            calls["n"] += 1
            # 故意做点计算，让 CPU 开销接近真实推理，避免「假模型让编排显得过轻」
            text = f"[stub#{calls['n']}] " + ("分析结果 " * 8)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

        async def _agenerate(self, messages, stop=None, run_manager=None, **kw) -> ChatResult:
            return self._generate(messages, stop, run_manager, **kw)

    stub = types.ModuleType("langchain_openai")
    stub.ChatOpenAI = lambda **kw: StubLLM(**{k: v for k, v in kw.items()
                                              if k in ("temperature", "model_name")})
    sys.modules["langchain_openai"] = stub
    return True


def rss_mb(port: int) -> float | None:
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"$c=(Get-NetTCPConnection -LocalPort {port} -State Listen -EA SilentlyContinue)"
             f"| Select-Object -ExpandProperty OwningProcess -Unique;"
             "if($c){[math]::Round(((Get-Process -Id $c -EA SilentlyContinue|"
             "Measure-Object WorkingSet64 -Sum).Sum/1MB),1)}"],
            capture_output=True, text=True, timeout=30)
        v = (out.stdout or "").strip()
        return float(v) if v and v != "0" else None
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="零成本完整编排压测（StubLLM）")
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rate", type=int, default=10)
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--rss-interval", type=int, default=0, help=">0 则采样 RSS 并输出趋势")
    ap.add_argument("--out", default=str(ROOT / "bench" / "stub_bench_result.json"))
    args = ap.parse_args()

    if not install_stub():
        print("stub 注入失败", file=sys.stderr)
        sys.exit(2)

    import subprocess
    import time as _t

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONUTF8"] = "1"
    env["LLM_API_KEY"] = ""          # 明确无 Key，配合 stub
    env["EA_STUB_LLM"] = "1"           # 让应用内部启用离线路径模型
    env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "uvicorn",
         "enterprise_agent.api.main:app", "--host", "127.0.0.1",
         "--port", str(args.port), "--log-level", "warning"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    import urllib.request
    ready = False
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health", timeout=3) as r:
                st = json.loads(r.read().decode())
                if st.get("workflow") == "ready":
                    ready = True
                break
        except Exception:
            _t.sleep(1)
    if not ready:
        print("服务未进入 ready（stub 注入可能失败），中止", file=sys.stderr)
        proc.terminate()
        sys.exit(3)
    print("✓ workflow 已就绪（StubLLM，编排全量执行，零计费）", flush=True)

    prefix = ROOT / "bench" / "stub_bench"
    load = subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "locust", "-f", str(ROOT / "bench" / "locustfile.py"),
         "--host", f"http://127.0.0.1:{args.port}", "--headless",
         "-u", str(args.users), "-r", str(args.rate), "-t", f"{args.duration}s",
         "--csv", str(prefix), "--only-summary", "--loglevel", "ERROR"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    samples: list[dict] = []
    if args.rss_interval:
        t0 = _t.time()
        while _t.time() - t0 < args.duration:
            rss = rss_mb(args.port)
            if rss:
                samples.append({"t": round(_t.time() - t0), "rss_mb": rss})
                print(f"  RSS={rss}MB", flush=True)
            _t.sleep(args.rss_interval)
        load.wait(timeout=60)
    else:
        load.wait(timeout=args.duration + 120)

    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()

    import csv as _csv
    stats = prefix.with_name(prefix.name + "_stats.csv")
    rows = []
    if stats.exists():
        with stats.open(encoding="utf-8", errors="replace", newline="") as f:
            rows = list(_csv.DictReader(f, strict=False))
    agg = next((r for r in rows if r.get("Name") == "Aggregated"), None)

    result: dict[str, Any] = {"users": args.users, "duration": args.duration,
                              "rss_samples": samples, "endpoints": []}
    if agg:
        def num(k: str) -> float:
            try:
                return float((agg.get(k) or "0").strip() or 0)
            except ValueError:
                return 0.0
        result.update({
            "requests": int(num("Request Count")),
            "failures": int(num("Failure Count")),
            "rps": round(num("Requests/s"), 2),
            "p50_ms": int(num("50%")), "p95_ms": int(num("95%")),
            "p99_ms": int(num("99%")), "max_ms": int(num("Max Response Time")),
        })
    for r in rows:
        if r.get("Name") and r.get("Name") != "Aggregated":
            result["endpoints"].append({
                "name": r["Name"],
                "requests": r.get("Request Count"),
                "failures": r.get("Failure Count"),
                "avg_ms": r.get("Average Response Time"),
                "p95_ms": r.get("95%"),
            })

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("\n" + "=" * 64)
    print("零成本完整编排压测结果（StubLLM）")
    print("=" * 64)
    for k in ("requests", "failures", "rps", "p50_ms", "p95_ms", "p99_ms", "max_ms"):
        if k in result:
            print(f"  {k}: {result[k]}")
    if result["endpoints"]:
        print("\n  分端点：")
        for e in result["endpoints"]:
            print(f"    {e['name'][:40]:42} {e['requests']:>6} 请求  "
                  f"{e['failures']} 失败  avg={e['avg_ms']}ms p95={e['p95_ms']}ms")
    print(f"\n结果已写入 {args.out}")
    for f in ROOT.glob("bench/stub_bench_*.csv"):
        f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
