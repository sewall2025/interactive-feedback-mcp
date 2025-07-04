
# Interactive Feedback MCP

一个功能强大的 MCP (Model Context Protocol) 服务器，为 AI 辅助开发提供交互式用户反馈和命令执行功能。

## 🌟 主要功能

- **交互式反馈界面** - 图形用户界面，支持文字和图片反馈
- **命令执行** - 在项目目录中执行命令并实时显示输出
- **三层项目隔离** - 基于客户端、工作环境和项目的完全隔离设置管理
- **自动提交** - 可设置倒计时自动提交反馈
- **快捷回复** - 预设常用回复内容
- **图片支持** - 上传图片文件和剪贴板粘贴，自动压缩优化

## 📸 界面预览

![反馈界面](img.png)
![终端界面](img_1.png)
![设置界面](img_2.png)

## cursor配置
![设置界面](img_3.png)

## 🚀 快速开始

### 直接使用（推荐）

无需安装，直接运行：

```bash
# 从 GitHub 运行最新版本
uvx --from git+https://github.com/sewall2025/interactive-feedback-mcp.git interactive-feedback-mcp
```

### 本地开发

如果您已经克隆了项目：

```bash
# 进入项目目录
cd interactive-feedback-mcp

# 使用 uv 运行
uv run interactive-feedback-mcp

# 或者直接运行 Python 脚本
uv run python interactive_feedback_mcp/server.py
```

### 参数说明

工具启动后会等待 MCP 协议的输入。通常情况下，您不需要手动运行这些命令，而是通过 AI 助手的 MCP 配置来使用。

## ⚡ MCP 配置

### 使用 uvx (推荐)

在 Cursor 或其他支持 MCP 的 AI 助手中添加以下配置：

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sewall2025/interactive-feedback-mcp.git", "interactive-feedback-mcp"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"],
      "env": {
        "worker": "work"
      }
    }
  }
}
```

> **注意**：使用 `uvx interactive-feedback-mcp` 而不是 `uvx run interactive-feedback-mcp`。uvx 是 uv tool run 的别名，直接指定工具名即可。

### 使用 uv (本地安装)

如果您已经克隆了项目到本地：

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/interactive-feedback-mcp", "interactive-feedback-mcp"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

或者使用传统方式：

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/interactive-feedback-mcp", "python", "interactive_feedback_mcp/server.py"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

### 使用 Python (本地安装)

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "python",
      "args": ["/path/to/interactive-feedback-mcp/interactive_feedback_mcp/server.py"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

## 🔒 三层项目隔离

Interactive Feedback MCP 提供了基于**客户端**、**工作环境**和**项目目录**的三层隔离功能，确保不同使用场景的设置完全独立。

### 隔离层级

1. **客户端隔离** - 自动从 MCP 协议获取客户端信息（如 `cursor`、`claude-desktop`、`cline`）
2. **工作环境隔离** - 通过 `worker` 环境变量区分不同工作环境（如 `work`、`personal`、`testing`）
3. **项目隔离** - 基于项目目录自动区分不同项目

### 配置示例

```json
{
  "mcpServers": {
    "interactive-feedback-work": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/sewall2025/interactive-feedback-mcp.git", "interactive-feedback-mcp"],
      "env": {
        "worker": "work"
      }
    },
    "interactive-feedback-personal": {
      "command": "uvx", 
      "args": ["--from", "git+https://github.com/sewall2025/interactive-feedback-mcp.git", "interactive-feedback-mcp"],
      "env": {
        "worker": "personal"
      }
    }
  }
}
```

### 隔离效果

- **窗口标题**: 动态显示当前隔离上下文，如 `Interactive: cursor_work_my-project`
- **独立设置**: 每个组合都有独立的窗口位置、自动提交设置、快捷回复等
- **完全隔离**: 不同环境的配置互不干扰

详细文档请参考：[三层项目隔离功能说明](docs/three-layer-isolation.md)

## 🎯 提示工程规则

为了获得最佳的交互体验，建议在您的 AI 助手中添加以下规则：

### MCP Interactive Feedback 使用规则

```
# MCP Interactive Feedback 规则

1. 在任何流程、任务、对话进行时，无论是询问、回复、或完成阶段性任务，皆必须调用 MCP interactive-feedback-mcp。

2. 每当收到用户反馈，若反馈内容非空，必须再次调用 MCP interactive-feedback-mcp，并根据反馈内容调整行为。

3. 仅当用户明确表示「结束」或「不再需要交互」时，才可停止调用 MCP interactive-feedback-mcp，流程才算结束。

4. 除非收到结束指令，否则所有步骤都必须重复调用 MCP interactive-feedback-mcp。

5. 完成任务前，必须使用 MCP interactive-feedback-mcp 工具向用户询问反馈。

6. 当用户提供图片时，要仔细分析图片内容并在后续交互中参考图片信息。

7. 利用终端功能执行必要的命令来验证或实施用户的需求。
```
## 另外一份提示词

```
你是Cursor IDE的AI编程助手，遵循核心工作流（研究->构思->计划->执行->评审）用中文协助用户，面向专业程序员，交互应简洁专业，避免不必要解释。

[沟通守则]

1. 响应以模式标签 `[模式：X]` 开始，初始为 `[模式：研究]`。
2. 核心工作流严格按 `研究->构思->计划->执行->评审` 顺序流转，用户可指令跳转。

[核心工作流详解]

1. `[模式：研究]`：理解需求。
2. `[模式：构思]`：提供至少两种可行方案及评估（例如：`方案1：描述`）。
3. `[模式：计划]`：将选定方案细化为详尽、有序、可执行的步骤清单（含原子操作：文件、函数/类、逻辑概要；预期结果；新库用`Context7`查询）。不写完整代码。完成后用`interactive-feedback`请求用户批准。
4. `[模式：执行]`：必须用户批准方可执行。严格按计划编码执行。计划简要（含上下文和计划）存入`./issues/任务名.md`。关键步骤后及完成时用`interactive-feedback`反馈。
5. `[模式：评审]`：对照计划评估执行结果，报告问题与建议。完成后用`interactive-feedback`请求用户确认。

[快速模式]
`[模式：快速]`：跳过核心工作流，快速响应。完成后用`interactive-feedback`请求用户确认。

[主动反馈与MCP服务]

* **通用反馈**：研究/构思遇疑问时，使用 `interactive_feedback` 征询意见。任务完成（对话结束）前也需征询。
* **MCP服务**：
  * `interactive_feedback`: 用户反馈。
  * `Context7`: 查询最新库文档/示例。
  * 优先使用MCP服务。
```

## ❓ 常见问题

### Q: 如何直接测试工具是否正常工作？
A: 运行 `uvx interactive-feedback-mcp`，工具会启动并等待 MCP 协议输入。如果没有错误信息，说明工具正常工作。

### Q: 运行 `uvx run interactive-feedback-mcp` 时提示错误怎么办？
A: 正确的命令是 `uvx interactive-feedback-mcp`（不需要 `run`）。如果看到提示询问是否要执行正确命令，输入 `y` 确认即可。

### Q: uvx、uv run、uv tool run 有什么区别？
A:
- `uvx` = `uv tool run`：用于运行独立工具，工具会安装在临时隔离环境中
- `uv run`：在项目环境中运行命令，适用于项目内的脚本和工具

### Q: 工具启动后没有界面怎么办？
A: 这是正常的！工具启动后会等待 MCP 协议的输入。只有当 AI 助手调用 `interactive_feedback` 功能时，才会弹出图形界面。

### Q: 窗口标题显示 "unknown-client" 怎么办？
A: 这通常表示客户端信息获取有问题。检查以下几点：
- 确保使用真实的 MCP 客户端（如 Cursor、Claude Desktop）而不是测试工具
- 检查客户端是否正确发送了 `clientInfo` 信息
- 参考 [客户端信息排查指南](docs/client-info-troubleshooting.md) 进行详细调试

### Q: 三层隔离功能不工作怎么办？
A: 检查以下配置：
- 确认 `worker` 环境变量已正确设置
- 验证客户端信息是否正确获取（窗口标题应显示具体的客户端名称）
- 确保项目目录路径有效
- 运行测试：`uv run python tests/test_three_layer_isolation.py`

### 使用建议

- **持续交互**：确保在每个关键步骤都获取用户反馈
- **图片利用**：充分利用图片上传功能来提供更准确的帮助
- **命令执行**：使用终端功能来验证和执行用户的需求
- **设置优化**：根据使用习惯调整自动提交、窗口置顶等设置

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

如果这个项目对您有帮助，请给个 ⭐ Star！
# 打赏
![img_4.png](img_4.png)