"""YAML 配置模板加载器（支持 ${ENV} 占位符替换）。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _resolve_env(match: re.Match) -> str:
    """解析 ${VAR} 或 ${VAR:-default} 占位符。"""
    name, default = match.group(1), match.group(2)
    value = os.getenv(name)
    return value if value is not None else (default or "")


class YamlConfigLoader:
    """加载 config.yaml 并替换环境变量占位符。"""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or "config.yaml"

    def load(self) -> dict[str, Any]:
        """加载配置。"""
        if not Path(self.path).exists():
            return {}
        with open(self.path, encoding="utf-8") as f:
            raw = f.read()
        resolved = _ENV_PATTERN.sub(_resolve_env, raw)
        return yaml.safe_load(resolved) or {}
