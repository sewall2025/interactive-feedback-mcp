#!/bin/bash
# quick_version_update.sh - 一键更新版本号脚本
# 用法: ./quick_version_update.sh 1.2.7 "版本描述"

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }

# 检查参数
if [ $# -lt 1 ]; then
    print_error "用法: $0 <新版本号> [版本描述]"
    echo "示例: $0 1.2.7 \"修复重要bug\""
    exit 1
fi

NEW_VERSION="$1"
VERSION_DESC="${2:-版本更新}"

# 验证版本号格式
if ! echo "$NEW_VERSION" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$' > /dev/null; then
    print_error "版本号格式无效: $NEW_VERSION"
    print_info "正确格式: MAJOR.MINOR.PATCH 或 MAJOR.MINOR.PATCH.HOTFIX"
    exit 1
fi

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] || [ ! -d "interactive_feedback_mcp" ]; then
    print_error "请在项目根目录运行此脚本"
    exit 1
fi

print_info "开始更新版本号到: $NEW_VERSION"
echo

# 第一步：更新版本号文件
print_info "第一步：更新版本号文件"

print_info "更新 pyproject.toml..."
sed -i.bak "s/version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

print_info "更新 uv.lock..."
sed -i.bak "/name = \"interactive-feedback-mcp\"/,/version = / s/version = \".*\"/version = \"$NEW_VERSION\"/" uv.lock

print_info "更新备用版本号..."
sed -i.bak "s/return \".*\"/return \"$NEW_VERSION\"/" interactive_feedback_mcp/feedback_ui.py

print_success "版本号文件更新完成"
echo

# 第二步：验证版本号一致性
print_info "第二步：验证版本号一致性"
if ./version_check.sh > /dev/null 2>&1; then
    print_success "版本号一致性验证通过"
else
    print_error "版本号一致性验证失败"
    # 恢复备份
    mv pyproject.toml.bak pyproject.toml
    mv uv.lock.bak uv.lock
    mv interactive_feedback_mcp/feedback_ui.py.bak interactive_feedback_mcp/feedback_ui.py
    exit 1
fi
echo

# 第三步：提交版本号更新
print_info "第三步：提交版本号更新"

git add pyproject.toml uv.lock interactive_feedback_mcp/feedback_ui.py

COMMIT_MSG="升级版本到 v$NEW_VERSION

- 更新 pyproject.toml 版本号到 $NEW_VERSION
- 更新 uv.lock 版本号到 $NEW_VERSION  
- 更新备用版本号到 $NEW_VERSION

$VERSION_DESC"

git commit -m "$COMMIT_MSG"
print_success "版本号更新已提交"

git push origin main
print_success "版本号更新已推送到远程"
echo

# 第四步：重新安装包
print_info "第四步：重新安装包"
uv pip install -e .
print_success "包重新安装完成"
echo

# 第五步：验证运行时版本号
print_info "第五步：验证运行时版本号"
RUNTIME_VERSION=$(python -c "
import sys
sys.path.insert(0, 'interactive_feedback_mcp')
from feedback_ui import get_app_version
print(get_app_version())
")

if [ "$RUNTIME_VERSION" = "$NEW_VERSION" ]; then
    print_success "运行时版本号验证通过: $RUNTIME_VERSION"
else
    print_error "运行时版本号不匹配: 期望 $NEW_VERSION，实际 $RUNTIME_VERSION"
    exit 1
fi
echo

# 第六步：创建和推送 Git Tag
print_info "第六步：创建和推送 Git Tag"

TAG_MSG="v$NEW_VERSION - $VERSION_DESC

版本更新：
- 更新所有版本号文件到 $NEW_VERSION
- 验证版本号显示正确
- 包元数据已更新"

git tag -a "v$NEW_VERSION" -m "$TAG_MSG"
print_success "Git tag v$NEW_VERSION 已创建"

git push origin "v$NEW_VERSION"
print_success "Git tag 已推送到远程"
echo

# 清理备份文件
rm -f pyproject.toml.bak uv.lock.bak interactive_feedback_mcp/feedback_ui.py.bak

# 最终验证
print_info "最终验证"
./version_check.sh
echo

print_success "🎉 版本号更新完成！"
print_info "新版本: v$NEW_VERSION"
print_info "描述: $VERSION_DESC"
echo

print_info "📋 完成的操作："
echo "  ✅ 更新了 pyproject.toml"
echo "  ✅ 更新了 uv.lock"
echo "  ✅ 更新了备用版本号"
echo "  ✅ 提交并推送了代码"
echo "  ✅ 重新安装了包"
echo "  ✅ 验证了运行时版本号"
echo "  ✅ 创建并推送了 Git tag"
echo

print_info "🚀 版本 v$NEW_VERSION 已成功发布！"
