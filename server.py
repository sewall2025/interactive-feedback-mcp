# Interactive Feedback MCP
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import tempfile
import subprocess
from PIL import Image as PILImage
import base64
from fastmcp import Image
from typing import List, Union
from typing import Annotated, Dict

from fastmcp import FastMCP
from pydantic import Field

# The log_level is necessary for Cline to work: https://github.com/jlowin/fastmcp/issues/81
mcp = FastMCP("Interactive Feedback MCP", log_level="ERROR")

def launch_feedback_ui(project_directory: str, summary: str) -> dict[str, str]:
    # Create a temporary file for the feedback result
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_file = tmp.name

    try:
        # Get the path to feedback_ui.py relative to this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        feedback_ui_path = os.path.join(script_dir, "feedback_ui.py")

        # Run feedback_ui.py as a separate process
        # NOTE: There appears to be a bug in uv, so we need
        # to pass a bunch of special flags to make this work
        args = [
            sys.executable,
            "-u",
            feedback_ui_path,
            "--project-directory", project_directory,
            "--prompt", summary,
            "--output-file", output_file
        ]
        result = subprocess.run(
            args,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True
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
) -> Dict[str, str]:
    """Request interactive feedback for a given project directory and summary"""
    
    result_dict = launch_feedback_ui(first_line(project_directory), first_line(summary))
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

def header_data(result_dict: dict) -> tuple:
    # print(result_dict)
    # {'logs': '', 'interactive_feedback': 'asdasdas', 'uploaded_images': ['/Users/ll/Desktop/2025/interactive-feedback-mcp/images/feedback.png']}

    logs = result_dict.get("logs", "")
    interactive_feedbacktxt = result_dict.get("interactive_feedback", "")
    uploaded_images = result_dict.get("uploaded_images", [])

    processed_content: List[Union[str, Image]] = []

    if logs and logs != "":
        processed_content.append("收集的日志: \n" + logs)
    
    if interactive_feedbacktxt and interactive_feedbacktxt != "":
        processed_content.append("用户反馈信息: \n" + interactive_feedbacktxt)
    
    for image_path in uploaded_images:
        image_data,img_format = compress_image(image_path)
        mcp_image = Image(data=image_data, format=img_format)
        processed_content.append(mcp_image)
        
    return tuple(processed_content)

if __name__ == "__main__":
    mcp.run(transport="stdio")

    # result_dict = launch_feedback_ui(first_line("/Users/ll/Desktop/2025/interactive-feedback-mcp"), first_line("测试交互式反馈功能"))
    # print(header_data(result_dict))