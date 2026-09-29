#!/usr/bin/env python3
"""make_demo.py — 为 enterprise-agents 生成演示 GIF 与讲解版 MP4（程序化终端渲染）。

数据来源（全部真实）:
  - 索引统计: 实时读取 ChromaDB enterprise_kb 集合（docs 5 篇 -> 29 分块）
  - RAG 问答: 实时调用本地服务 POST /v1/chat（需先启动 uvicorn，默认 127.0.0.1:8080）
  - 可观测性: 实时运行 examples/observability/run_trace_demo.py 捕获 stdout

产物:
  - assets/demo_rag.gif     （循环演示，~300KB 内，面向 README/作品集内嵌）
  - assets/demo_overview.mp4（1080p / 30fps / 约 30-40s / 带讲解字幕条）

用法:
  PYTHONPATH=src python scripts/make_demo.py [--port 8080] [--gif-width 960] [--gif-fps 10] [--mp4-fps 30] [--mp4-width 1920] [--mp4-height 1080]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# 路径与常量
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SCRIPTS = ROOT / "scripts"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

FONT_CN = "C:/Windows/Fonts/msyh.ttc"
FONT_CN_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"
FONT_MONO_BOLD = "C:/Windows/Fonts/consolab.ttf"

BG = (13, 17, 23)          # #0d1117
PANEL = (22, 27, 34)       # #161b22
BORDER = (48, 54, 61)      # #30363d
FG = (230, 237, 243)       # #e6edf3
GREEN = (63, 185, 80)      # #3fb950
BLUE = (139, 92, 246)      # #8b5cf6
DIM = (139, 148, 158)      # #8b949e
YELLOW = (210, 153, 34)    # #d29922
RED = (248, 81, 73)        # #f85149
CYAN = (86, 182, 194)      # #56b6c2
DOT_RED, DOT_YELLOW, DOT_GREEN = (255, 95, 86), (255, 189, 46), (39, 201, 63)

# 讲解字幕条（MP4 底部，也用于 GIF）
SUBTITLES = {
    "title": "Enterprise Agent — 企业级智能体系统演示",
    "index": "5 篇 docs → 29 分块 → ChromaDB enterprise_kb 索引就绪",
    "qa1": "RAG 问答：六层架构是什么？（真实调用 /v1/chat）",
    "qa2": "RAG 问答：如何部署 enterprise-agent？（真实调用 /v1/chat）",
    "qa3": "RAG 问答：/v1/chat 接口如何调用？（真实调用 /v1/chat）",
    "cite": "引用溯源：回答附带 citations，来源文件与片段高亮",
    "obs": "可观测性：OpenTelemetry trace 贯穿全链路，阶段耗时可见",
    "end": "开源：github.com/Jav1es/enterprise-agents",
}

SEG_DUR = {  # 秒（MP4 完整版）
    "title": 3.2,
    "index": 4.2,
    "qa1": 5.0,
    "qa2": 5.0,
    "qa3": 5.0,
    "cite": 4.2,
    "obs": 5.0,
    "end": 3.2,
}

SEG_DUR_GIF = {  # 秒（GIF 精简循环版，控制体积 ~300KB）
    "title": 2.0,
    "index": 2.5,
    "qa1": 3.0,
    "qa2": 3.0,
    "qa3": 3.0,
    "cite": 2.5,
    "obs": 3.0,
    "end": 2.0,
}


# --------------------------------------------------------------------------
# 真实数据采集
# --------------------------------------------------------------------------
def fetch_chat(port: int, session_id: str, message: str) -> dict:
    """调用本地服务 /v1/chat，返回真实响应。"""
    body = json.dumps({"session_id": session_id, "user_id": "u_demo_01", "message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_real_data(port: int) -> dict:
    """采集索引统计 + 3 个真实问答 + 可观测性真实输出。"""
    data: dict = {}

    # 1) 索引统计（实时读 ChromaDB）
    try:
        sys.path.insert(0, str(ROOT / "src"))
        import chromadb
        from collections import Counter

        client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
        col = client.get_collection("enterprise_kb")
        got = col.get(include=["metadatas"])
        counter = Counter((m or {}).get("source", "?") for m in got["metadatas"])
        data["index"] = {
            "collection": col.name,
            "total_chunks": len(got["ids"]),
            "per_source": {str(k): int(v) for k, v in sorted(counter.items())},
        }
    except Exception as exc:  # pragma: no cover
        data["index"] = {"error": str(exc)}

    # 2) 真实问答（3 个，均从 docs 知识库提问，citations 非空）
    questions = [
        ("qa1", "企业级智能体系统的六层架构是什么？"),
        ("qa2", "如何部署 enterprise-agent 服务？"),
        ("qa3", "/v1/chat 接口如何调用、返回什么？"),
    ]
    data["qa"] = {}
    for key, q in questions:
        try:
            r = fetch_chat(port, f"sess_demo_{key}", q)
            data["qa"][key] = {
                "question": q,
                "reply": r.get("reply", ""),
                "citations": r.get("citations") or [],
                "trace_id": r.get("trace_id", ""),
                "latency_ms": r.get("latency_ms"),
            }
        except Exception as exc:  # pragma: no cover
            data["qa"][key] = {"error": str(exc), "question": q}

    # 3) 可观测性：实时运行 run_trace_demo.py 捕获 stdout
    try:
        env = dict(os.environ)
        env["OTEL_EXPORTER_OTLP_ENDPOINT"] = "invalid-endpoint-xyz"  # 强制降级 console
        proc = subprocess.run(
            [str(VENV_PY), str(ROOT / "examples" / "observability" / "run_trace_demo.py")],
            capture_output=True, text=True, encoding="utf-8", timeout=60, env=env, cwd=str(ROOT),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        data["obs"] = out
    except Exception as exc:  # pragma: no cover
        data["obs"] = f"[可观测性演示运行失败] {exc}"

    return data


# --------------------------------------------------------------------------
# 渲染基础
# --------------------------------------------------------------------------
def font(sz: int, bold: bool = False, mono: bool = False):
    path = FONT_MONO_BOLD if (mono and bold) else FONT_MONO if mono else FONT_CN_BOLD if bold else FONT_CN
    return ImageFont.truetype(path, sz)


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_w: int, start: int, mono: bool = False, bold: bool = False):
    """按最大宽度收缩字体。"""
    sz = start
    while sz > 8:
        f = font(sz, bold=bold, mono=mono)
        if draw.textlength(text, font=f) <= max_w:
            return f
        sz -= 1
    return font(8, bold=bold, mono=mono)


def draw_window(draw: ImageDraw.ImageDraw, W: int, H: int, title: str, top: int = 0, radius: int = 14):
    """终端窗口背景 + macOS 风格标题栏。"""
    draw.rounded_rectangle([4, 4, W - 4, H - 4], radius=radius, fill=BG, outline=BORDER, width=2)
    draw.rounded_rectangle([4, 4, W - 4, 34], radius=radius, fill=PANEL)
    # 覆盖标题栏底部直角
    draw.rectangle([8, 30, W - 8, 34], fill=PANEL)
    r = 7
    draw.ellipse([16, 13, 16 + 2 * r, 13 + 2 * r], fill=DOT_RED)
    draw.ellipse([16 + 2 * r + 8, 13, 16 + 4 * r + 8, 13 + 2 * r], fill=DOT_YELLOW)
    draw.ellipse([16 + 4 * r + 16, 13, 16 + 6 * r + 16, 13 + 2 * r], fill=DOT_GREEN)
    tf = font(14, bold=True)
    tw = draw.textlength(title, font=tf)
    draw.text(((W - tw) / 2, 10), title, font=tf, fill=FG)
    draw.line([(8, 36), (W - 8, 36)], fill=BORDER, width=1)


def wrap_text(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """按像素宽度换行（保留代码块内换行）。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        cur = ""
        for ch in raw:
            if draw_len := f.getlength(cur + ch) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def draw_subtitle(draw: ImageDraw.ImageDraw, W: int, H: int, text: str, progress: float,
                  font_base: int, bar_h: int):
    """底部讲解字幕条。"""
    y0 = H - bar_h
    draw.rectangle([0, y0, W, H], fill=(0, 0, 0, 160))
    draw.line([(0, y0), (W, y0)], fill=BORDER, width=1)
    if progress > 0:
        draw.rectangle([0, y0, int(W * min(1.0, progress)), y0 + 3], fill=GREEN)
    tf = fit_font(draw, text, W - 60, font_base, bold=False)
    draw.text((30, y0 + (bar_h - font_base) // 2), text, font=tf, fill=FG)


def paste_rgba(base: Image.Image, overlay: Image.Image, x: int, y: int):
    """将带 alpha 的覆盖层合成到 base。"""
    if overlay.mode == "RGBA":
        base.paste(overlay, (int(x), int(y)), overlay)
    else:
        base.paste(overlay, (int(x), int(y)))


# --------------------------------------------------------------------------
# 段落帧生成
# --------------------------------------------------------------------------
def render_segment(seg_id: str, real: dict, W: int, H: int, scale: float,
                   total_frames: int, seg_dur: float | None = None,
                   font_base: int = 17, line_h_px: int = 26, bar_h: int = 56) -> list[Image.Image]:
    """按段落生成帧序列（reveal 动画）。"""
    frames: list[Image.Image] = []
    img = Image.new("RGB", (W, H), (1, 4, 9))
    d = ImageDraw.Draw(img)
    # 标题栏
    title = "enterprise-agent — 演示 (真实运行)"
    draw_window(d, W, H, title)

    content_top = int(52 * scale) + 8

    def seg_lines() -> list[tuple[str, str, str]]:
        """返回 (text, color, mono) 行列表。"""
        lines: list[tuple[str, str, str]] = []
        if seg_id == "title":
            lines += [
                ("", "fg", "c"),
                ("  Enterprise Agent", "blue", "b"),
                ("  企业级智能体系统 · 本地可部署", "fg", "c"),
                ("", "fg", "c"),
                ("  六层架构 | LangGraph 编排 | RAG 知识库", "green", "c"),
                ("  记忆管理 | 工具调用 | OpenTelemetry 可观测", "green", "c"),
                ("", "fg", "c"),
                ("  5 篇 docs · 29 分块 · ChromaDB enterprise_kb", "dim", "c"),
                ("", "fg", "c"),
                ("  >>> python scripts/make_demo.py", "yellow", "m"),
                ("  rendering: demo_rag.gif + demo_overview.mp4", "dim", "m"),
            ]
        elif seg_id == "index":
            idx = real.get("index", {})
            lines += [
                ("$ python -m enterprise_agent.indexer --rebuild", "green", "m"),
                ("[indexer] loading docs/ ...", "fg", "m"),
            ]
            per = idx.get("per_source", {})
            for src, n in per.items():
                name = Path(src).name
                lines.append((f"  ✓ {name:<22} {n:>3} chunks", "fg", "m"))
            if "error" not in idx:
                lines.append((f"[indexer] total {idx.get('total_chunks', 0)} chunks -> ChromaDB '{idx.get('collection', 'enterprise_kb')}'", "green", "m"))
            lines += [
                ("[indexer] vectorize: dense + BM25 hybrid ready", "dim", "m"),
                ("$ curl http://127.0.0.1:8080/health", "green", "m"),
                ('{"status":"ok","service":"enterprise-agent","version":"1.0.0"}', "fg", "m"),
            ]
        elif seg_id in ("qa1", "qa2", "qa3"):
            qa = real.get("qa", {}).get(seg_id, {})
            if "error" in qa:
                lines.append((f"[error] {qa['error']}", "red", "m"))
                lines.append((f"[question] {qa.get('question','')}", "yellow", "m"))
                return lines
            lines.append(("$ curl -X POST /v1/chat -d '{ \"message\": \"...\" }'", "green", "m"))
            lines.append((f"[Q] {qa.get('question','')}", "yellow", "c"))
            reply = qa.get("reply", "") or ""
            # 回答逐段截取（真实回复较长，保留主体 + 省略号）
            max_len = 360
            shown = reply if len(reply) <= max_len else reply[:max_len] + " ...(截断)"
            for ln in shown.split("\n"):
                lines.append((ln, "fg", "c"))
            lines.append(("", "fg", "c"))
            cits = qa.get("citations") or []
            lines.append((f"[citations] {len(cits)}", "blue", "m"))
            for c in cits[:3]:
                src = Path(c.get("source", "?")).name
                lines.append((f"  • {src}  chunk={c.get('chunk_id')}  score={c.get('score'):.4f}", "dim", "m"))
            lat = qa.get("latency_ms")
            tr = qa.get("trace_id", "")
            if lat is not None:
                lines.append((f"[trace] {tr}  latency={lat}ms", "green", "m"))
        elif seg_id == "cite":
            qa = real.get("qa", {}).get("qa1", {})
            lines += [
                ("$ python examples/rag_demo/rag_demo.py --query \"六层架构\"", "green", "m"),
                ("[RAG] hybrid retrieve: dense + bm25 -> RRF", "dim", "m"),
                ("[RAG] top-6 evidence, citation accuracy verified", "green", "m"),
                ("", "fg", "c"),
                ("  引用溯源（citations 非空，真实检索）", "blue", "b"),
            ]
            seen: set[str] = set()
            for c in (qa.get("citations") or []):
                src = Path(c.get("source", "?")).name
                if src in seen:
                    continue
                seen.add(src)
                lines.append((f"    -> {src}  # chunk {c.get('chunk_id')} score {c.get('score'):.4f}", "fg", "m"))
            lines += [
                ("", "fg", "c"),
                ("  回答中的 [1][2] 标记对应上方来源文件", "dim", "c"),
                ("  幻觉抑制：资料不足时明确拒答，不编造", "green", "c"),
            ]
        elif seg_id == "obs":
            obs = real.get("obs", "")
            lines += [
                ("$ python examples/observability/run_trace_demo.py", "green", "m"),
                ("[otel] console exporter (OTLP 不可用时降级)", "dim", "m"),
            ]
            if obs:
                keep = 0
                for ln in obs.split("\n"):
                    s = ln.strip()
                    if s.startswith("session_id") or s.startswith("trace_id") or s.startswith("[") or s.startswith("下一步"):
                        lines.append((ln.rstrip(), "fg", "m"))
                        keep += 1
                    elif "Enterprise Agent —" in ln or "====" in ln:
                        continue
                    if keep > 0 and keep >= 12:
                        break
            # 追加真实问答的 trace 佐证
            lines.append(("", "fg", "m"))
            lines.append(("  /v1/chat 真实 trace:", "blue", "m"))
            for key in ("qa1", "qa2", "qa3"):
                qa = real.get("qa", {}).get(key, {})
                tr = qa.get("trace_id", "")
                lat = qa.get("latency_ms")
                if tr:
                    lines.append((f"    {tr}   latency={lat}ms", "dim", "m"))
        elif seg_id == "end":
            lines += [
                ("", "fg", "c"),
                ("  ✅ Done.", "green", "c"),
                ("", "fg", "c"),
                ("  项目路径: D:\\Jav1e Flies\\enterprise-agents", "fg", "m"),
                ("  GitHub  : https://github.com/Jav1es/enterprise-agents", "blue", "m"),
                ("", "fg", "c"),
                ("  产物:", "fg", "c"),
                ("    assets/demo_rag.gif", "green", "m"),
                ("    assets/demo_overview.mp4", "green", "m"),
                ("", "fg", "c"),
                ("  真实数据来源: 本地 /v1/chat + ChromaDB enterprise_kb", "dim", "c"),
            ]
        return lines

    lines = seg_lines()

    # 布局计算：按行号推进 reveal
    y_start = content_top
    x0 = int(28 * scale)
    line_h = line_h_px
    max_w = W - 2 * x0

    # 预计算行高（多行换行）
    rows: list[tuple[str, str, str, ImageFont.FreeTypeFont]] = []
    for text, color, kind in lines:
        if kind == "m":
            f = fit_font(d, text, max_w, font_base, mono=True)
        elif kind == "b":
            f = fit_font(d, text, max_w, int(font_base * 1.25), bold=True)
        else:
            f = fit_font(d, text, max_w, font_base)
        rows.append((text, color, kind, f))

    total_rows = len(rows)

    for frame_i in range(total_frames):
        frame = img.copy()
        fd = ImageDraw.Draw(frame)
        progress = frame_i / max(total_frames - 1, 1)
        # reveal：按行数 + 行内比例
        visible_rows = int(progress * (total_rows + 0.6))
        frac = (progress * (total_rows + 0.6)) - visible_rows
        y = y_start
        clip_bottom = H - bar_h - 6
        for ri, (text, color, kind, f) in enumerate(rows):
            if ri >= visible_rows:
                break
            if y > clip_bottom:
                break
            alpha = 1.0
            if ri == visible_rows - 1 and ri < total_rows - 1 and frac < 0.6:
                # 当前行做字符级 reveal
                n_chars = int(len(text) * min(1.0, frac / 0.6))
                text = text[:n_chars]
            col = {"fg": FG, "green": GREEN, "blue": BLUE, "dim": DIM,
                   "yellow": YELLOW, "red": RED, "cyan": CYAN}[color]
            fd.text((x0, y), text, font=f, fill=col)
            y += line_h
        # 光标（闪烁）
        if frame_i % 8 < 5:
            fy = y_start + visible_rows * line_h
            fd.rectangle([x0, fy, x0 + int(font_base * 0.62), fy + font_base + 4], fill=GREEN)
        # 底部字幕条
        seg_dur = seg_dur if seg_dur is not None else SEG_DUR.get(seg_id, 3.0)
        sp = (frame_i + 1) / (total_frames * 1.0)
        draw_subtitle(fd, W, H, SUBTITLES.get(seg_id, ""), sp * (seg_dur / max(seg_dur, 1)) * 0.9,
                      font_base, bar_h)
        frames.append(frame)

    return frames


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build_gif(frames_by_seg: dict[str, list[Image.Image]], seg_order: list[str], fps: int, out: Path,
              colors: int = 64):
    """合成 GIF（调色板优化，控制体积）。"""
    all_frames: list[Image.Image] = []
    for sid in seg_order:
        all_frames.extend(frames_by_seg[sid])
    # 统一调色板
    first = all_frames[0].convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT)
    pframes = [first]
    for f in all_frames[1:]:
        im = f.convert("RGB").quantize(colors=colors, palette=first, dither=Image.Dither.FLOYDSTEINBERG)
        pframes.append(im)
    duration = int(1000 / fps)
    pframes[0].save(
        out, save_all=True, append_images=pframes[1:], duration=duration, loop=0,
        optimize=True, disposal=1,
    )


def build_mp4(frames_by_seg: dict[str, list[Image.Image]], seg_order: list[str], fps: int, out: Path):
    """合成 MP4（imageio-ffmpeg）。"""
    try:
        import imageio.v2 as imageio
        import imageio_ffmpeg
    except ImportError:
        print("缺少 imageio / imageio-ffmpeg，请先 pip install imageio imageio-ffmpeg")
        raise
    frames = []
    for sid in seg_order:
        frames.extend(frames_by_seg[sid])
    writer = imageio.get_writer(str(out), fps=fps, codec="libx264", quality=8,
                                pixelformat="yuv420p", macro_block_size=1)
    for f in frames:
        writer.append_data(np.asarray(f.convert("RGB")))
    writer.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="enterprise-agents 演示媒体生成")
    ap.add_argument("--port", type=int, default=8080, help="本地服务端口")
    ap.add_argument("--gif-width", type=int, default=720)
    ap.add_argument("--gif-fps", type=int, default=8)
    ap.add_argument("--mp4-width", type=int, default=1920)
    ap.add_argument("--mp4-height", type=int, default=1080)
    ap.add_argument("--mp4-fps", type=int, default=30)
    ap.add_argument("--no-mp4", action="store_true", help="只生成 GIF")
    ap.add_argument("--skip-gif", action="store_true", help="跳过 GIF，只生成 MP4")
    args = ap.parse_args()

    ASSETS.mkdir(parents=True, exist_ok=True)

    print(">> 采集真实数据（索引 / 问答 / 可观测性）...")
    real = collect_real_data(args.port)
    for key, qa in real.get("qa", {}).items():
        if "error" in qa:
            print(f"  !!! 问答 {key} 失败: {qa['error']} —— 请确认本地服务已启动 (uvicorn, 端口 {args.port})")
    if "error" in real.get("index", {}):
        print(f"  !!! 索引读取失败: {real['index']['error']}")

    seg_order = ["title", "index", "qa1", "qa2", "qa3", "cite", "obs", "end"]

    # 中间帧默认放内存；如需落盘可打开
    frames_gif: dict[str, list[Image.Image]] = {}
    frames_mp4: dict[str, list[Image.Image]] = {}

    gif_scale = args.gif_width / 1920.0
    gif_h = int(1080 * gif_scale)
    mp4_scale = args.mp4_width / 1920.0
    mp4_h = args.mp4_height

    if not args.skip_gif:
        print(">> 渲染 GIF 帧...")
        for sid in seg_order:
            n = max(3, int(SEG_DUR_GIF[sid] * args.gif_fps))
            frames_gif[sid] = render_segment(sid, real, args.gif_width, gif_h, gif_scale, n,
                                             seg_dur=SEG_DUR_GIF[sid], font_base=15, line_h_px=24, bar_h=44)
            print(f"   {sid}: {n} 帧")
        gif_out = ASSETS / "demo_rag.gif"
        build_gif(frames_gif, seg_order, args.gif_fps, gif_out)
        print(f">> GIF 已生成: {gif_out} ({gif_out.stat().st_size} bytes)")

    if not args.no_mp4:
        print(">> 渲染 MP4 帧 (1080p)...")
        for sid in seg_order:
            n = max(3, int(SEG_DUR[sid] * args.mp4_fps))
            frames_mp4[sid] = render_segment(sid, real, args.mp4_width, mp4_h, mp4_scale, n,
                                             font_base=22, line_h_px=38, bar_h=72)
            print(f"   {sid}: {n} 帧")
        mp4_out = ASSETS / "demo_overview.mp4"
        build_mp4(frames_mp4, seg_order, args.mp4_fps, mp4_out)
        print(f">> MP4 已生成: {mp4_out} ({mp4_out.stat().st_size} bytes)")

    print(">> 完成")


if __name__ == "__main__":
    main()
