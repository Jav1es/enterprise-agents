"""可观测性模块：OpenTelemetry 全链路打点。

公开 API:
    init_telemetry / get_tracer / traced_node
"""

from .telemetry import get_tracer, init_telemetry, traced_node

__all__ = ["get_tracer", "init_telemetry", "traced_node"]
