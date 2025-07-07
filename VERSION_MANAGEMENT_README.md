# 版本号管理工具使用指南

## 📋 概述

本项目提供了一套完整的版本号管理工具，确保所有相关文件中的版本号保持一致，避免版本号不匹配的问题。

## 🛠️ 工具列表

### 1. `version_check.sh` - 版本号检查工具
检查和验证项目中所有版本号的一致性。

**用法：**
```bash
# 检查版本号一致性
./version_check.sh

# 或者
./version_check.sh check

# 更新版本号（交互式）
./version_check.sh update 1.2.7

# 显示帮助
./version_check.sh help
```

**功能：**
- ✅ 检查 `pyproject.toml` 中的版本号
- ✅ 检查 `uv.lock` 中的版本号
- ✅ 检查代码中的备用版本号
- ✅ 检查已安装包的元数据版本号
- ✅ 检查运行时获取的版本号
- ✅ 提供版本号更新功能

### 2. `quick_version_update.sh` - 一键版本号更新工具
自动化完成整个版本号更新流程。

**用法：**
```bash
# 更新版本号
./quick_version_update.sh 1.2.7 "修复重要bug"

# 只提供版本号（使用默认描述）
./quick_version_update.sh 1.2.7
```

**自动执行的操作：**
1. ✅ 更新所有版本号文件
2. ✅ 验证版本号一致性
3. ✅ 提交并推送代码
4. ✅ 重新安装包更新元数据
5. ✅ 验证运行时版本号
6. ✅ 创建并推送 Git tag
7. ✅ 清理临时文件

### 3. `版本号更新标准流程.md` - 详细文档
包含完整的版本号管理规范和手动操作指南。

## 🚀 快速开始

### 检查当前版本号状态
```bash
./version_check.sh
```

输出示例：
```
ℹ️  检查版本号一致性...

📄 pyproject.toml:     1.2.6.1
🔒 uv.lock:           1.2.6.1
💾 备用版本号:         1.2.6.1
📦 包元数据:          1.2.6.1
🏃 运行时版本:         1.2.6.1

✅ 配置文件版本号一致: 1.2.6.1
```

### 发布新版本
```bash
# 发布补丁版本
./quick_version_update.sh 1.2.7 "修复 AI_summary_detail_level bug"

# 发布热修复版本
./quick_version_update.sh 1.2.6.2 "紧急修复界面显示问题"

# 发布次要版本
./quick_version_update.sh 1.3.0 "添加新功能：自动保存用户设置"
```

## 📝 版本号格式

采用语义化版本控制 (Semantic Versioning)：

- **MAJOR.MINOR.PATCH** - 标准格式 (如 1.2.6)
- **MAJOR.MINOR.PATCH.HOTFIX** - 热修复格式 (如 1.2.6.1)

### 版本号含义
- **MAJOR**: 重大变更，不向后兼容
- **MINOR**: 新功能，向后兼容  
- **PATCH**: Bug修复，向后兼容
- **HOTFIX**: 紧急修复（可选）

## 🔍 涉及的文件

版本号管理工具会自动更新以下文件：

1. **`pyproject.toml`** - 项目配置文件
   ```toml
   [project]
   version = "1.2.6.1"
   ```

2. **`uv.lock`** - 依赖锁定文件
   ```toml
   [[package]]
   name = "interactive-feedback-mcp"
   version = "1.2.6.1"
   ```

3. **`interactive_feedback_mcp/feedback_ui.py`** - 备用版本号
   ```python
   def get_app_version() -> str:
       # 最终备用值
       return "1.2.6.1"
   ```

## ⚠️ 注意事项

### 使用前检查
- 确保在项目根目录运行脚本
- 确保有 Git 提交权限
- 确保工作目录是干净的（没有未提交的更改）

### 版本号格式验证
工具会自动验证版本号格式：
- ✅ `1.2.6` - 有效
- ✅ `1.2.6.1` - 有效
- ❌ `v1.2.6` - 无效（不要包含 v 前缀）
- ❌ `1.2` - 无效（缺少补丁版本号）

### 错误处理
- 如果版本号格式无效，脚本会停止执行
- 如果版本号一致性检查失败，会自动恢复备份文件
- 如果 Git 操作失败，会显示详细错误信息

## 🐛 故障排除

### 问题1：版本号不一致
```bash
# 检查具体哪个文件的版本号不匹配
./version_check.sh

# 手动修复或使用更新工具
./version_check.sh update 1.2.6.1
```

### 问题2：包元数据版本号过时
```bash
# 重新安装包
uv pip install -e .

# 再次检查
./version_check.sh
```

### 问题3：运行时版本号不匹配
通常是因为包没有重新安装，运行：
```bash
uv pip install -e .
```

### 问题4：Git tag 已存在
```bash
# 删除本地 tag
git tag -d v1.2.7

# 删除远程 tag
git push --delete origin v1.2.7

# 重新创建 tag
./quick_version_update.sh 1.2.7 "重新发布"
```

## 📚 相关文档

- [版本号更新标准流程.md](版本号更新标准流程.md) - 详细的手动操作指南
- [pyproject.toml](pyproject.toml) - 项目配置文件
- [uv.lock](uv.lock) - 依赖锁定文件

## 🎯 最佳实践

1. **发布前检查**：始终先运行 `./version_check.sh` 检查当前状态
2. **使用语义化版本**：根据变更类型选择合适的版本号
3. **提供有意义的描述**：在版本描述中说明主要变更
4. **测试验证**：发布后验证界面显示的版本号是否正确
5. **保持一致性**：使用工具而不是手动修改，避免遗漏

## 💡 示例工作流

```bash
# 1. 检查当前状态
./version_check.sh

# 2. 开发和测试新功能
# ... 编码和测试 ...

# 3. 发布新版本
./quick_version_update.sh 1.2.7 "添加用户设置持久化功能"

# 4. 验证发布结果
./version_check.sh
```

---

**提示**：这些工具旨在简化版本管理流程，减少人为错误。如果遇到问题，请参考详细文档或检查脚本输出的错误信息。
