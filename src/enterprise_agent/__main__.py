"""模块入口: python -m enterprise_agent 启动 FastAPI 服务。"""

from __future__ import annotations

import uvicorn

from enterprise_agent.config.settings import get_settings


def main() -> None:
    """启动 API 服务。"""
    settings = get_settings()
    uvicorn.run(
        "enterprise_agent.api.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
