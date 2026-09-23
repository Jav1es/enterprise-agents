# ===== Enterprise Agent 镜像构建 =====
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 系统依赖（psycopg2 / 向量库所需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先拷贝依赖清单，利用层缓存
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 拷贝源码
COPY src/ ./src/
COPY config.example.yaml ./

# 非 root 用户运行
RUN useradd --create-home --shell /bin/bash agent && chown -R agent:agent /app
USER agent

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "enterprise_agent.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
