
# Interactive Feedback MCP

一个功能强大的 MCP (Model Context Protocol) 服务器，为 AI 辅助开发提供交互式用户反馈和命令执行功能。

## 🌟 主要功能

- **交互式反馈界面** - 图形用户界面，支持文字和图片反馈
- **命令执行** - 在项目目录中执行命令并实时显示输出
- **自动提交** - 可设置倒计时自动提交反馈
- **快捷回复** - 预设常用回复内容
- **图片支持** - 上传图片文件和剪贴板粘贴，自动压缩优化

## 📸 界面预览

![反馈界面](img.png)
![终端界面](img_1.png)
![设置界面](img_2.png)

## cursor配置
![设置界面](img_3.png)

## ⚡ MCP 配置

### 使用 uvx (推荐)

在 Cursor 或其他支持 MCP 的 AI 助手中添加以下配置：

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/duolabmeng6/interactive-feedback-mcp.git", "python", "server.py"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

### 使用 uv (本地安装)

如果您已经克隆了项目到本地：

```json
{
  "mcpServers": {
    "interactive-feedback-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/interactive-feedback-mcp", "python", "server.py"],
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
      "args": ["/path/to/interactive-feedback-mcp/server.py"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```



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

### 使用建议

- **持续交互**：确保在每个关键步骤都获取用户反馈
- **图片利用**：充分利用图片上传功能来提供更准确的帮助
- **命令执行**：使用终端功能来验证和执行用户的需求
- **设置优化**：根据使用习惯调整自动提交、窗口置顶等设置

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

如果这个项目对您有帮助，请给个 ⭐ Star！
