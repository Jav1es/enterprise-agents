"""OpenTelemetry 全链路可观测性模块。

能力:
- init_telemetry(): 初始化 TracerProvider + OTLP(HTTP/protobuf) 导出器，可同时输出到控制台
- get_tracer(): 获取全局 Tracer，供各业务模块创建 span
- traced_node(): 装饰器，为编排节点（router/planner/tool/reviewer 等）自动打点
- OTEL 环境变量约定（与 docker-compose 对齐）:
    OTEL_EXPORTER_OTLP_ENDPOINT   OTLP 上报地址，默认 http://localhost:4318
    OTEL_SERVICE_NAME             服务名，默认 enterprise-agent

trace_id 贯穿机制:
    一次完整会话请求在最外层创建根 span（agent.workflow.invoke）；
    编排节点 span（agent.node.router / planner / tool_call / reviewer ...）
    通过 Context 自动继承根 span 的 trace_id，形成父子层级；
    Jaeger UI 按 trace_id 聚合展示整条链路的阶段耗时。

示例:
    from enterprise_agent.observability.telemetry import init_telemetry, get_tracer
    init_telemetry()
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.workflow.invoke"):
        ...
"""

from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

DEFAULT_OTLP_ENDPOINT = "http://localhost:4318/v1/traces"

_telemetry_initialized = False


def _build_provider(service_name: str, otlp_endpoint: str | None, console: bool) -> TracerProvider:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    endpoint = otlp_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or DEFAULT_OTLP_ENDPOINT
    try:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        logger.info("OTLP span exporter 已启用: %s", endpoint)
    except Exception as exc:  # pragma: no cover - 导出器初始化失败不应阻断业务
        logger.warning("OTLP span exporter 初始化失败(%s)，降级为控制台输出", exc)
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    return provider


def init_telemetry(
    service_name: str | None = None,
    otlp_endpoint: str | None = None,
    console: bool = False,
) -> TracerProvider:
    """初始化 OpenTelemetry（幂等，重复调用只保留首次 provider）。

    Args:
        service_name: 服务名，默认读 OTEL_SERVICE_NAME 或 enterprise-agent
        otlp_endpoint: OTLP HTTP 上报地址（含 /v1/traces），默认 http://localhost:4318/v1/traces
        console: 是否同时输出到控制台（便于本地调试无 Jaeger 场景）
    """
    global _telemetry_initialized
    if _telemetry_initialized:
        current = trace.get_tracer_provider()
        if isinstance(current, TracerProvider):
            return current

    provider = _build_provider(
        service_name=service_name or os.environ.get("OTEL_SERVICE_NAME") or "enterprise-agent",
        otlp_endpoint=otlp_endpoint,
        console=console,
    )
    _telemetry_initialized = True
    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry 初始化完成: service=%s", service_name or "enterprise-agent")
    return provider


def get_tracer() -> trace.Tracer:
    """获取全局 Tracer。未初始化时自动以默认参数初始化。"""
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        init_telemetry()
    return trace.get_tracer(__name__)


def traced_node(span_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """编排节点打点装饰器。

    为节点函数创建独立 span，自动记录:
        - agent.node.duration_ms  阶段耗时（毫秒）
        - agent.node.step         当前步骤号
        - agent.session_id        会话标识（如存在）
        - 异常时记录 exception + ERROR 状态
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            start = time.perf_counter()
            span = tracer.start_span(
                span_name,
                attributes={
                    "agent.node.step": int((state or {}).get("step_number", 0) or 0),
                    "agent.session_id": str((state or {}).get("session_id", "") or ""),
                },
            )
            try:
                with trace.use_span(span, end_on_exit=False):
                    result = await fn(state, *args, **kwargs)
                span.set_attribute("agent.node.duration_ms", round((time.perf_counter() - start) * 1000, 3))
                return result
            except Exception as exc:  # noqa: BLE001 - 观测层统一兜底
                span.record_exception(exc)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)[:200]))
                raise
            finally:
                span.end()

        return wrapper

    return decorator
