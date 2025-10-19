#!/usr/bin/env python3
"""Utility to run the MCP server inside a Python venv named 'interactive'."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_ROOT / "interactive"
PYPROJECT_TOML = PROJECT_ROOT / "pyproject.toml"
HASH_SENTINEL = VENV_DIR / ".pyproject.hash"


def _is_windows() -> bool:
    return os.name == "nt"


def _env_python() -> Path:
    return VENV_DIR / ("Scripts" if _is_windows() else "bin") / ("python.exe" if _is_windows() else "python")


def ensure_virtualenv() -> None:
    if not VENV_DIR.exists():
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(VENV_DIR)
    elif not _env_python().exists():
        raise RuntimeError(f"虚拟环境目录 {VENV_DIR} 已存在但缺少 Python 可执行文件，请清理后重试。")


def _current_pyproject_hash() -> str:
    contents = PYPROJECT_TOML.read_bytes()
    return hashlib.sha256(contents).hexdigest()


def install_dependencies_if_needed() -> None:
    expected_hash = _current_pyproject_hash()

    if HASH_SENTINEL.exists():
        recorded_hash = HASH_SENTINEL.read_text(encoding="utf-8").strip()
        if recorded_hash == expected_hash:
            return

    python_exe = _env_python()
    try:
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([str(python_exe), "-m", "pip", "install", "-e", str(PROJECT_ROOT)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("安装项目依赖失败，请检查网络连接或手动在 interactive 虚拟环境中安装依赖。") from exc
    HASH_SENTINEL.write_text(expected_hash, encoding="utf-8")


def run_server(server_args: list[str]) -> int:
    python_exe = _env_python()
    server_script = PROJECT_ROOT / "interactive_feedback_mcp" / "server.py"
    cmd = [str(python_exe), str(server_script), *server_args]
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="在名为 interactive 的原生 Python 虚拟环境中运行 MCP 服务器。"
    )
    parser.add_argument(
        "--install-only",
        action="store_true",
        help="仅创建/更新虚拟环境及依赖，不启动服务器。",
    )
    parser.add_argument(
        "server_args",
        nargs=argparse.REMAINDER,
        help="将后续参数透传给 interactive_feedback_mcp/server.py。",
    )

    args = parser.parse_args(argv)

    ensure_virtualenv()
    install_dependencies_if_needed()

    if args.install_only:
        return 0

    # argparse.REMAINDER 保留了可能的领先 '--'，需要过滤一次
    passthrough = args.server_args
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]

    return run_server(passthrough)


if __name__ == "__main__":
    sys.exit(main())
