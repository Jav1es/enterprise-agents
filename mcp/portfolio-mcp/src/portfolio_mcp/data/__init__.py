"""data 包：作品集数据加载与检索。

- loader.py：加载模块数据（优先 portfolio_data.json，缺失/解析失败降级内置示例数据）
- search.py：关键词检索实现
- portfolio_data.json：初始示例数据（可替换为用户自己的作品集数据）
"""

from portfolio_mcp.data.loader import load_portfolio_data

__all__ = ["load_portfolio_data"]
