#!/usr/bin/env python3
"""
历史记录功能测试脚本

测试三层隔离历史记录功能的核心组件
"""

import os
import sys
import tempfile
import shutil
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from interactive_feedback_mcp.history_db import HistoryManager, ConversationRecord


def test_basic_functionality():
    """测试基本功能"""
    print("🧪 测试基本功能...")
    
    # 创建临时数据库
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test.db')
    
    try:
        # 初始化历史管理器
        history_manager = HistoryManager()
        history_manager.db.db_path = db_path
        history_manager.db._connection = None  # 重置连接
        
        # 测试保存对话
        session_id = history_manager.save_feedback_session(
            client_name="test-client",
            worker="test-worker",
            project_directory="/test/project",
            ai_prompt="测试AI提示",
            user_feedback="测试用户反馈",
            command_logs="测试命令日志"
        )
        
        print(f"✅ 保存对话成功，会话ID: {session_id}")
        
        # 测试获取对话
        conversations = history_manager.get_current_isolation_history(
            "test-client", "test-worker", "/test/project"
        )
        
        assert len(conversations) == 1, f"期望1条对话，实际{len(conversations)}条"
        conv = conversations[0]
        assert conv.ai_prompt == "测试AI提示"
        assert conv.user_feedback == "测试用户反馈"
        
        print("✅ 获取对话成功")
        
        # 测试搜索功能
        search_results = history_manager.search_current_isolation(
            "test-client", "test-worker", "/test/project", "测试"
        )
        
        assert len(search_results) == 1, f"期望搜索到1条对话，实际{len(search_results)}条"
        print("✅ 搜索功能正常")
        
        # 测试多维度查看
        project_conversations = history_manager.get_project_browsing_history(
            "test-client", "test-worker"
        )
        assert len(project_conversations) == 1
        print("✅ 项目浏览模式正常")
        
        env_conversations = history_manager.get_environment_browsing_history("test-client")
        assert len(env_conversations) == 1
        print("✅ 环境浏览模式正常")
        
        global_conversations = history_manager.get_global_browsing_history()
        assert len(global_conversations) == 1
        print("✅ 全局浏览模式正常")
        
        print("🎉 基本功能测试通过！")
        
    finally:
        # 清理临时文件
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_export_functionality():
    """测试导出功能"""
    print("\n🧪 测试导出功能...")
    
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test.db')
    
    try:
        history_manager = HistoryManager()
        history_manager.db.db_path = db_path
        history_manager.db._connection = None
        
        # 创建测试数据
        for i in range(3):
            history_manager.save_feedback_session(
                client_name=f"client-{i}",
                worker=f"worker-{i}",
                project_directory=f"/test/project-{i}",
                ai_prompt=f"测试AI提示 {i}",
                user_feedback=f"测试用户反馈 {i}",
                command_logs=f"测试命令日志 {i}"
            )
        
        # 获取所有对话
        conversations = history_manager.get_global_browsing_history()
        assert len(conversations) == 3
        
        # 测试JSON导出
        json_file = os.path.join(temp_dir, 'test.json')
        history_manager.export_conversations_to_json(conversations, json_file)
        assert os.path.exists(json_file)
        print("✅ JSON导出成功")
        
        # 测试CSV导出
        csv_file = os.path.join(temp_dir, 'test.csv')
        history_manager.export_conversations_to_csv(conversations, csv_file)
        assert os.path.exists(csv_file)
        print("✅ CSV导出成功")
        
        # 测试Markdown导出
        md_file = os.path.join(temp_dir, 'test.md')
        history_manager.export_conversations_to_markdown(conversations, md_file)
        assert os.path.exists(md_file)
        print("✅ Markdown导出成功")
        
        print("🎉 导出功能测试通过！")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def test_isolation_integrity():
    """测试隔离完整性"""
    print("\n🧪 测试隔离完整性...")
    
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test.db')
    
    try:
        history_manager = HistoryManager()
        history_manager.db.db_path = db_path
        history_manager.db._connection = None
        
        # 创建不同隔离层级的数据
        test_data = [
            ("client1", "worker1", "/project1", "提示1", "反馈1"),
            ("client1", "worker1", "/project2", "提示2", "反馈2"),
            ("client1", "worker2", "/project1", "提示3", "反馈3"),
            ("client2", "worker1", "/project1", "提示4", "反馈4"),
        ]
        
        for client, worker, project, prompt, feedback in test_data:
            history_manager.save_feedback_session(
                client_name=client,
                worker=worker,
                project_directory=project,
                ai_prompt=prompt,
                user_feedback=feedback
            )
        
        # 测试当前隔离模式
        current_conversations = history_manager.get_current_isolation_history(
            "client1", "worker1", "/project1"
        )
        assert len(current_conversations) == 1
        assert current_conversations[0].ai_prompt == "提示1"
        print("✅ 当前隔离模式正确")
        
        # 测试项目浏览模式
        project_conversations = history_manager.get_project_browsing_history(
            "client1", "worker1"
        )
        assert len(project_conversations) == 2  # project1 和 project2
        print("✅ 项目浏览模式正确")
        
        # 测试环境浏览模式
        env_conversations = history_manager.get_environment_browsing_history("client1")
        assert len(env_conversations) == 3  # worker1的2个 + worker2的1个
        print("✅ 环境浏览模式正确")
        
        # 测试全局浏览模式
        global_conversations = history_manager.get_global_browsing_history()
        assert len(global_conversations) == 4  # 所有4个
        print("✅ 全局浏览模式正确")
        
        print("🎉 隔离完整性测试通过！")
        
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def main():
    """运行所有测试"""
    print("🚀 开始历史记录功能测试\n")
    
    try:
        test_basic_functionality()
        test_export_functionality()
        test_isolation_integrity()
        
        print("\n🎊 所有测试通过！历史记录功能正常工作。")
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)