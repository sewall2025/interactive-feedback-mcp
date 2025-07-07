# Interactive Feedback MCP
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import tempfile
import subprocess
from PIL import Image as PILImage

from fastmcp import Image
from typing import List, Union, Literal
from typing import Annotated, Dict

from fastmcp import FastMCP, Context
from pydantic import Field

# The log_level is necessary for Cline to work: https://github.com/jlowin/fastmcp/issues/81
mcp = FastMCP("Interactive Feedback MCP", log_level="ERROR")

# 缓存环境变量值，确保在整个运行过程中保持一致
_cached_detail_level = None

def get_default_detail_level() -> str:
    """Get the default detail level from environment variable AI_summary_detail_level

    使用缓存机制确保在整个运行过程中 detail_level 保持一致，
    避免环境变量在运行时被修改导致的值变化问题。
    """
    global _cached_detail_level

    # 如果已经缓存了值，直接返回
    if _cached_detail_level is not None:
        return _cached_detail_level

    # 首次读取环境变量并缓存
    detail_level = os.environ.get('AI_summary_detail_level', 'brief')

    # Validate the detail level value
    valid_levels = ['brief', 'detailed', 'comprehensive']
    if detail_level not in valid_levels:
        # If invalid value, fallback to default
        detail_level = 'brief'

    # 缓存有效值
    _cached_detail_level = detail_level
    return detail_level

def reset_detail_level_cache():
    """重置 detail_level 缓存，用于测试或特殊情况"""
    global _cached_detail_level
    _cached_detail_level = None

def launch_feedback_ui(project_directory: str, summary: str, worker: str = "default", client_name: str = "unknown-client", detail_level: str = None) -> dict[str, str]:
    # If detail_level is not provided, get it from environment variable
    if detail_level is None:
        detail_level = get_default_detail_level()



    # Create a temporary file for the feedback result
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_file = tmp.name

    try:
        # Get the path to feedback_ui.py relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        feedback_ui_path = os.path.join(script_dir, "feedback_ui.py")

        # Run feedback_ui.py as a separate process with isolation parameters
        args = [
            sys.executable,
            "-u",
            feedback_ui_path,
            "--project-directory", project_directory,
            "--prompt", summary,
            "--output-file", output_file,
            "--worker", worker,
            "--client-name", client_name,
            "--detail-level", detail_level
        ]
        # 确保子进程继承环境变量，特别是 AI_summary_detail_level
        env = os.environ.copy()

        result = subprocess.run(
            args,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            env=env  # 显式传递环境变量
        )
        if result.returncode != 0:
            raise Exception(f"Failed to launch feedback UI: {result.returncode}")

        # Read the result from the temporary file
        with open(output_file, 'r') as f:
            result = json.load(f)
        os.unlink(output_file)
        return result
    except Exception as e:
        if os.path.exists(output_file):
            os.unlink(output_file)
        raise e

def first_line(text: str) -> str:
    return text.split("\n")[0].strip()

@mcp.tool()
def interactive_feedback(
    project_directory: Annotated[str, Field(description="Full path to the project directory")],
    summary: Annotated[str, Field(description="Short, one-line summary of the changes")],
    ctx: Context,
    detail_level: Annotated[
        Literal["brief", "detailed", "comprehensive"], 
        Field(description="Level of detail for the summary: brief (one-line), detailed (multi-line with key points), comprehensive (full description with background and technical details)")
    ] = None
) -> Dict[str, Union[str, List]]:
    """Request interactive feedback for a given project directory and summary"""
    
    # 从环境变量获取worker参数，默认为'default'
    worker = os.environ.get('worker', 'default')
    
    # 验证worker参数长度限制（最多40字符）
    if len(worker) > 40:
        raise ValueError(f"Worker identifier too long: {len(worker)} chars (max 40)")
    
    # 从MCP上下文获取真实的客户端信息
    client_name = 'unknown-client'
    try:
        # 尝试从session.client_params.clientInfo获取客户端名称
        if hasattr(ctx, 'session') and hasattr(ctx.session, 'client_params'):
            client_params = ctx.session.client_params
            if hasattr(client_params, 'clientInfo') and client_params.clientInfo:
                client_info = client_params.clientInfo
                if hasattr(client_info, 'name') and client_info.name:
                    client_name = client_info.name
                elif isinstance(client_info, dict) and 'name' in client_info:
                    client_name = client_info['name']
    except Exception:
        # 如果获取失败，使用默认值
        pass
    
    result_dict = launch_feedback_ui(
        first_line(project_directory), 
        first_line(summary),
        worker=worker,
        client_name=client_name,
        detail_level=detail_level
    )
    return header_data(result_dict)

# 友好计算文件大小
def friendly_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f}KB"
    else:
        return f"{size / 1024 / 1024:.2f}MB"

# 压缩图像函数处理超过800kb的图片文件 最大程度的压缩减小大小 压缩后如果还是大于800kb 缩放到512*512
def compress_image(image_path: str):
    pil_img = PILImage.open(image_path)
    img_format = (pil_img.format or "PNG").lower()
    temp_image_path = image_path + ".temp.jpg"
    if os.path.getsize(image_path) > 800 * 1024:
        img_format = (pil_img.format or "jpg").lower()

        pil_img.save(temp_image_path, optimize=True, quality=50)
        # 输出现在的尺寸
        # print(f"压缩前大小: {friendly_size(os.path.getsize(image_path))}")
        # print(f"压缩后大小: {friendly_size(os.path.getsize(temp_image_path))}")
        if os.path.getsize(temp_image_path) > 800 * 1024:
            pil_img.thumbnail((512, 512))
            pil_img.save(temp_image_path, optimize=True, quality=50)
            # print(f"缩放后大小: {friendly_size(os.path.getsize(temp_image_path))}")
            # print(f"缩放后大小: {friendly_size(os.path.getsize(temp_image_path))}")
        with open(temp_image_path, "rb") as f:
            image_data = f.read()
        os.unlink(temp_image_path)
        return image_data,img_format
    else:
        with open(image_path, "rb") as f:
            image_data = f.read()
        return image_data, img_format

def header_data(result_dict: dict) -> Dict[str, Union[str, List]]:
    # print(result_dict)
    # {'logs': '', 'interactive_feedback': 'asdasdas', 'uploaded_images': ['/Users/ll/Desktop/2025/interactive-feedback-mcp/images/feedback.png']}

    logs = result_dict.get("command_logs", "") or result_dict.get("logs", "")
    interactive_feedbacktxt = result_dict.get("interactive_feedback", "")
    uploaded_images = result_dict.get("uploaded_images", [])

    # 构建返回的字典结构
    response_data = {}

    # 添加文本内容
    text_content = []
    if logs and logs.strip():
        text_content.append(f"收集的日志:\n{logs}")

    if interactive_feedbacktxt and interactive_feedbacktxt.strip():
        text_content.append(f"用户反馈信息:\n{interactive_feedbacktxt}")

    if text_content:
        response_data["text"] = "\n\n".join(text_content)

    # 处理图片
    if uploaded_images:
        images_data = []
        for image_path in uploaded_images:
            try:
                image_data, img_format = compress_image(image_path)
                # 将图片数据编码为base64字符串
                import base64
                image_b64 = base64.b64encode(image_data).decode('utf-8')
                images_data.append({
                    "format": img_format,
                    "data": image_b64,
                    "path": image_path
                })
            except Exception as e:
                print(f"处理图片失败 {image_path}: {e}")

        if images_data:
            response_data["images"] = images_data

    # 如果没有任何内容，返回默认消息
    if not response_data:
        response_data["text"] = "未收到任何反馈内容"

    return response_data

def main():
    """Main entry point for the interactive feedback MCP server."""
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

    # result_dict = launch_feedback_ui(first_line("/Users/ll/Desktop/2025/interactive-feedback-mcp"), first_line("测试交互式反馈功能"))
    # print(header_data(result_dict))