#!/bin/bash
# =============================================================
# init_db.sh — 初始化长期记忆数据库表结构（PostgreSQL）
# 用法: bash scripts/init_db.sh
# 说明: 依赖 DATABASE_URL 环境变量（或 .env）
# =============================================================

set -euo pipefail

# 加载 .env（若存在）
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

: "${DATABASE_URL:?请设置 DATABASE_URL 环境变量，例如 postgresql+asyncpg://agent:YOUR_DB_PASSWORD@localhost:5432/agent}"

echo "正在初始化数据库表结构 (mem_facts)..."
# TODO: 替换为 uv run python -m enterprise_agent.memory.migrations
psql "${DATABASE_URL/postgresql+asyncpg:/postgresql:}" <<'SQL'
CREATE TABLE IF NOT EXISTS mem_facts (
    id            BIGSERIAL PRIMARY KEY,
    session_id    TEXT NOT NULL,
    user_id       TEXT NOT NULL DEFAULT '',
    subject       TEXT NOT NULL,
    predicate     TEXT NOT NULL,
    object        TEXT NOT NULL,
    confidence    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    access_count  INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expired_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_mem_facts_entity ON mem_facts (subject, predicate);
CREATE INDEX IF NOT EXISTS idx_mem_facts_user ON mem_facts (user_id);
SQL

echo "✅ 数据库初始化完成"
