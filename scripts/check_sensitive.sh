#!/bin/bash
# =============================================================
# check_sensitive.sh — 扫描仓库中的硬编码密钥
# 用法: bash scripts/check_sensitive.sh
# 退出码: 0=未发现风险  1=发现可疑硬编码
# =============================================================

set -euo pipefail

echo "=============================================="
echo "[1/3] 检查待提交的敏感文件 (git ls-files)"
echo "=============================================="

# 检查敏感文件是否被 git 跟踪（.env / config.yaml / 密钥文件）
SENSITIVE_FILES=$(git ls-files | grep -E '(^|/)(\.env|config\.yaml)$|\.(key|pem|p12|pfx|jks)$' || true)
if [ -n "$SENSITIVE_FILES" ]; then
    echo "❌ 检测到敏感文件已被 Git 跟踪，请立即移除："
    echo "$SENSITIVE_FILES"
    echo "处理: git rm --cached <file> 并加入 .gitignore"
    exit 1
fi
echo "✅ 无敏感文件被跟踪"

echo ""
echo "=============================================="
echo "[2/3] 扫描硬编码密钥模式"
echo "=============================================="

# 扫描源码/配置/文档中的疑似硬编码密钥
HITS=$(git grep -n -i -E \
    '(api[_-]?key|api[_-]?secret|password|passwd|secret|token|private[_-]?key)\s*[:=]\s*["'"'"']?[A-Za-z0-9_\-]{16,}' \
    -- "*.py" "*.yaml" "*.yml" "*.toml" "*.md" 2>/dev/null \
    | grep -v -E 'YOUR_|example|placeholder|TODO|FIXME|xxx|XXXX' || true)

if [ -n "$HITS" ]; then
    echo "⚠️ 发现疑似硬编码密钥，请逐条确认并替换为环境变量："
    echo "$HITS"
    echo ""
    echo "处理建议:"
    echo "  1. 将真实密钥移入 .env（已被 gitignore 排除）"
    echo "  2. 使用 os.environ / pydantic-settings 读取"
    echo "  3. 如需清除历史提交中的密钥，使用:"
    echo "     pip install git-filter-repo"
    echo "     git filter-repo --replace-text <(echo 'sk-REALKEY==>YOUR_API_KEY')"
    exit 1
fi
echo "✅ 未发现硬编码密钥"

echo ""
echo "=============================================="
echo "[3/3] 检查 .env / config.yaml 是否被忽略"
echo "=============================================="
for f in .env config.yaml; do
    if git check-ignore -q "$f" 2>/dev/null; then
        echo "✅ $f 已被 .gitignore 忽略"
    else
        echo "⚠️ $f 未被忽略，请确认加入 .gitignore"
    fi
done

echo ""
echo "✅ 敏感信息检查完成"
