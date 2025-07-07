#!/bin/bash
# version_check.sh - 验证版本号一致性脚本
# 用法: ./version_check.sh [新版本号]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数：打印带颜色的消息
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 函数：检查文件是否存在
check_file() {
    if [ ! -f "$1" ]; then
        print_error "文件不存在: $1"
        exit 1
    fi
}

# 函数：读取版本号
get_pyproject_version() {
    check_file "pyproject.toml"
    grep 'version = ' pyproject.toml | sed 's/.*version = "\(.*\)".*/\1/' | head -1
}

get_uvlock_version() {
    check_file "uv.lock"
    grep -A2 'name = "interactive-feedback-mcp"' uv.lock | grep 'version = ' | sed 's/.*version = "\(.*\)".*/\1/' | head -1
}

get_backup_version() {
    check_file "interactive_feedback_mcp/feedback_ui.py"
    grep 'return ".*"' interactive_feedback_mcp/feedback_ui.py | tail -1 | sed 's/.*return "\(.*\)".*/\1/'
}

get_package_version() {
    python -c "
try:
    from importlib import metadata
    print(metadata.version('interactive-feedback-mcp'))
except Exception as e:
    print('未安装')
" 2>/dev/null
}

get_runtime_version() {
    python -c "
import sys
import os
sys.path.insert(0, 'interactive_feedback_mcp')
try:
    from feedback_ui import get_app_version
    print(get_app_version())
except Exception as e:
    print(f'错误: {e}')
" 2>/dev/null
}

# 主函数：检查版本号一致性
check_versions() {
    print_info "检查版本号一致性..."
    echo

    # 读取各个来源的版本号
    PYPROJECT_VERSION=$(get_pyproject_version)
    UVLOCK_VERSION=$(get_uvlock_version)
    BACKUP_VERSION=$(get_backup_version)
    PACKAGE_VERSION=$(get_package_version)
    RUNTIME_VERSION=$(get_runtime_version)

    # 显示版本号
    echo "📄 pyproject.toml:     $PYPROJECT_VERSION"
    echo "🔒 uv.lock:           $UVLOCK_VERSION"
    echo "💾 备用版本号:         $BACKUP_VERSION"
    echo "📦 包元数据:          $PACKAGE_VERSION"
    echo "🏃 运行时版本:         $RUNTIME_VERSION"
    echo

    # 检查一致性
    local all_consistent=true
    local target_version="$PYPROJECT_VERSION"

    if [ "$PYPROJECT_VERSION" != "$UVLOCK_VERSION" ]; then
        print_error "pyproject.toml 和 uv.lock 版本号不一致"
        all_consistent=false
    fi

    if [ "$PYPROJECT_VERSION" != "$BACKUP_VERSION" ]; then
        print_error "pyproject.toml 和备用版本号不一致"
        all_consistent=false
    fi

    if [ "$PACKAGE_VERSION" != "未安装" ] && [ "$PYPROJECT_VERSION" != "$PACKAGE_VERSION" ]; then
        print_warning "包元数据版本号过时，需要重新安装包"
        print_info "运行: uv pip install -e ."
    fi

    if [ "$RUNTIME_VERSION" != "$PYPROJECT_VERSION" ]; then
        print_warning "运行时版本号与配置不一致"
    fi

    if [ "$all_consistent" = true ]; then
        print_success "配置文件版本号一致: $target_version"
        return 0
    else
        print_error "版本号不一致！"
        return 1
    fi
}

# 函数：更新版本号
update_version() {
    local new_version="$1"
    
    if [ -z "$new_version" ]; then
        print_error "请提供新版本号"
        echo "用法: $0 update 1.2.7"
        exit 1
    fi

    print_info "更新版本号到: $new_version"
    echo

    # 验证版本号格式
    if ! echo "$new_version" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$' > /dev/null; then
        print_error "版本号格式无效: $new_version"
        print_info "正确格式: MAJOR.MINOR.PATCH 或 MAJOR.MINOR.PATCH.HOTFIX"
        exit 1
    fi

    # 备份原文件
    print_info "备份原文件..."
    cp pyproject.toml pyproject.toml.bak
    cp uv.lock uv.lock.bak
    cp interactive_feedback_mcp/feedback_ui.py interactive_feedback_mcp/feedback_ui.py.bak

    # 更新版本号
    print_info "更新 pyproject.toml..."
    sed -i.tmp "s/version = \".*\"/version = \"$new_version\"/" pyproject.toml && rm pyproject.toml.tmp

    print_info "更新 uv.lock..."
    sed -i.tmp "/name = \"interactive-feedback-mcp\"/,/version = / s/version = \".*\"/version = \"$new_version\"/" uv.lock && rm uv.lock.tmp

    print_info "更新备用版本号..."
    sed -i.tmp "s/return \".*\"/return \"$new_version\"/" interactive_feedback_mcp/feedback_ui.py && rm interactive_feedback_mcp/feedback_ui.py.tmp

    print_success "版本号更新完成"
    echo

    # 验证更新结果
    print_info "验证更新结果..."
    if check_versions; then
        print_success "版本号更新成功！"
        echo
        print_info "下一步操作："
        echo "1. git add pyproject.toml uv.lock interactive_feedback_mcp/feedback_ui.py"
        echo "2. git commit -m \"升级版本到 v$new_version\""
        echo "3. git push origin main"
        echo "4. uv pip install -e ."
        echo "5. git tag -a v$new_version -m \"v$new_version - 版本更新\""
        echo "6. git push origin v$new_version"
    else
        print_error "版本号更新失败，恢复备份文件"
        mv pyproject.toml.bak pyproject.toml
        mv uv.lock.bak uv.lock
        mv interactive_feedback_mcp/feedback_ui.py.bak interactive_feedback_mcp/feedback_ui.py
        exit 1
    fi
}

# 函数：显示帮助信息
show_help() {
    echo "版本号管理工具"
    echo
    echo "用法:"
    echo "  $0                    - 检查版本号一致性"
    echo "  $0 check             - 检查版本号一致性"
    echo "  $0 update VERSION    - 更新版本号"
    echo "  $0 help              - 显示帮助信息"
    echo
    echo "示例:"
    echo "  $0                   - 检查当前版本号"
    echo "  $0 update 1.2.7      - 更新到版本 1.2.7"
    echo "  $0 update 1.2.6.2    - 更新到版本 1.2.6.2 (hotfix)"
}

# 主程序
main() {
    case "${1:-check}" in
        "check"|"")
            check_versions
            ;;
        "update")
            update_version "$2"
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

# 检查是否在正确的目录
if [ ! -f "pyproject.toml" ] || [ ! -d "interactive_feedback_mcp" ]; then
    print_error "请在项目根目录运行此脚本"
    exit 1
fi

# 运行主程序
main "$@"
