"""
对话历史记录数据库管理模块

实现基于三层隔离键的对话历史持久化存储，支持多维度数据访问。
"""

import os
import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path

# 导入隔离工具
try:
    from .isolation_utils import IsolationUtils
except ImportError:
    # 当直接运行此文件时的回退导入
    from isolation_utils import IsolationUtils


@dataclass
class ConversationRecord:
    """对话记录数据模型"""
    id: Optional[int] = None
    session_id: str = ""
    isolation_key: str = ""
    client_name: str = ""
    worker: str = ""
    project_name: str = ""
    project_directory: str = ""
    ai_prompt: str = ""
    user_feedback: str = ""
    command_logs: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ConversationImage:
    """对话图片数据模型"""
    id: Optional[int] = None
    conversation_id: int = 0
    image_path: str = ""
    image_name: str = ""
    image_data: Optional[bytes] = None
    created_at: Optional[datetime] = None


class ThreeLayerHistoryDB:
    """三层隔离的历史数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径，默认为 ~/.interactive-feedback-mcp/interactive-feedback-mcp.db
        """
        if db_path is None:
            # 使用统一的数据库文件路径：~/.interactive-feedback-mcp/interactive-feedback-mcp.db
            config_dir = os.path.expanduser('~/.interactive-feedback-mcp')
            os.makedirs(config_dir, exist_ok=True)
            db_path = os.path.join(config_dir, 'interactive-feedback-mcp.db')
        
        self.db_path = db_path
        
        # 数据库连接（单一连接，因为现在只有一个数据库文件）
        self._connection: Optional[sqlite3.Connection] = None
    

    
    def _get_connection(self) -> sqlite3.Connection:
        """获取或创建数据库连接"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row  # 启用字典式访问
            self._initialize_database(self._connection)
        
        return self._connection
    
    def _initialize_database(self, conn: sqlite3.Connection):
        """初始化数据库表结构"""
        cursor = conn.cursor()
        
        # 创建对话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                isolation_key TEXT NOT NULL,
                client_name TEXT NOT NULL,
                worker TEXT NOT NULL,
                project_name TEXT NOT NULL,
                project_directory TEXT NOT NULL,
                ai_prompt TEXT NOT NULL,
                user_feedback TEXT,
                command_logs TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建图片表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversation_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                image_path TEXT NOT NULL,
                image_name TEXT NOT NULL,
                image_data BLOB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        ''')
        
        # 创建性能索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_isolation_key ON conversations(isolation_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_client_name ON conversations(client_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_worker ON conversations(worker)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_conversations_project_name ON conversations(project_name)')
        
        conn.commit()
    
    def save_conversation(self, record: ConversationRecord, images: List[ConversationImage] = None) -> int:
        """
        保存对话记录
        
        Args:
            record: 对话记录
            images: 关联的图片列表
            
        Returns:
            保存的对话记录ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 生成会话ID（如果没有）
            if not record.session_id:
                record.session_id = self._generate_session_id(record)
            
            # 设置时间戳
            now = datetime.now()
            if not record.created_at:
                record.created_at = now
            record.updated_at = now
            
            # 插入对话记录
            cursor.execute('''
                INSERT OR REPLACE INTO conversations 
                (session_id, isolation_key, client_name, worker, project_name, 
                 project_directory, ai_prompt, user_feedback, command_logs, 
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.session_id, record.isolation_key, record.client_name,
                record.worker, record.project_name, record.project_directory,
                record.ai_prompt, record.user_feedback, record.command_logs,
                record.created_at, record.updated_at
            ))
            
            conversation_id = cursor.lastrowid
            
            # 保存关联图片
            if images:
                for image in images:
                    image.conversation_id = conversation_id
                    if not image.created_at:
                        image.created_at = now
                    
                    cursor.execute('''
                        INSERT INTO conversation_images 
                        (conversation_id, image_path, image_name, image_data, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        image.conversation_id, image.image_path, image.image_name,
                        image.image_data, image.created_at
                    ))
            
            conn.commit()
            return conversation_id
            
        except Exception as e:
            conn.rollback()
            raise e
    
    def get_conversations(self, isolation_key: str, limit: int = 100, offset: int = 0) -> List[ConversationRecord]:
        """
        获取指定隔离键的对话记录
        
        Args:
            isolation_key: 隔离键
            limit: 返回记录数限制
            offset: 偏移量
            
        Returns:
            对话记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversations 
            WHERE isolation_key = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (isolation_key, limit, offset))
        
        rows = cursor.fetchall()
        return [self._row_to_conversation_record(row) for row in rows]
    
    def get_conversation_images(self, conversation_id: int, isolation_key: str) -> List[ConversationImage]:
        """获取对话关联的图片"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ci.* FROM conversation_images ci
            JOIN conversations c ON ci.conversation_id = c.id
            WHERE ci.conversation_id = ? AND c.isolation_key = ?
        ''', (conversation_id, isolation_key))
        
        rows = cursor.fetchall()
        return [self._row_to_conversation_image(row) for row in rows]
    
    def search_conversations(self, isolation_key: str, query: str, limit: int = 100) -> List[ConversationRecord]:
        """
        搜索对话记录
        
        Args:
            isolation_key: 隔离键
            query: 搜索查询
            limit: 返回记录数限制
            
        Returns:
            匹配的对话记录列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversations 
            WHERE isolation_key = ? AND (
                ai_prompt LIKE ? OR 
                user_feedback LIKE ? OR 
                command_logs LIKE ?
            )
            ORDER BY created_at DESC
            LIMIT ?
        ''', (isolation_key, f'%{query}%', f'%{query}%', f'%{query}%', limit))
        
        rows = cursor.fetchall()
        return [self._row_to_conversation_record(row) for row in rows]
    
    def delete_conversation(self, session_id: str, isolation_key: str) -> bool:
        """删除对话记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取对话ID
            cursor.execute('SELECT id FROM conversations WHERE session_id = ? AND isolation_key = ?', 
                         (session_id, isolation_key))
            row = cursor.fetchone()
            if not row:
                return False
            
            conversation_id = row[0]
            
            # 删除关联图片
            cursor.execute('DELETE FROM conversation_images WHERE conversation_id = ?', (conversation_id,))
            
            # 删除对话记录
            cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            raise e
    
    def get_isolation_keys(self) -> List[str]:
        """获取所有存在的隔离键"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT isolation_key FROM conversations ORDER BY isolation_key')
        rows = cursor.fetchall()
        
        return [row[0] for row in rows]
    
    def _generate_session_id(self, record: ConversationRecord) -> str:
        """生成会话ID"""
        content = f"{record.isolation_key}_{record.ai_prompt}_{datetime.now().isoformat()}"
        return IsolationUtils.generate_hash(content)
    
    def _row_to_conversation_record(self, row: sqlite3.Row) -> ConversationRecord:
        """将数据库行转换为对话记录对象"""
        return ConversationRecord(
            id=row['id'],
            session_id=row['session_id'],
            isolation_key=row['isolation_key'],
            client_name=row['client_name'],
            worker=row['worker'],
            project_name=row['project_name'],
            project_directory=row['project_directory'],
            ai_prompt=row['ai_prompt'],
            user_feedback=row['user_feedback'],
            command_logs=row['command_logs'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
            updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
        )
    
    def _row_to_conversation_image(self, row: sqlite3.Row) -> ConversationImage:
        """将数据库行转换为图片对象"""
        return ConversationImage(
            id=row['id'],
            conversation_id=row['conversation_id'],
            image_path=row['image_path'],
            image_name=row['image_name'],
            image_data=row['image_data'],
            created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        )
    
    def close_connection(self):
        """关闭数据库连接"""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def __del__(self):
        """析构函数，确保连接关闭"""
        self.close_connection()


class HistoryManager:
    """历史记录管理器 - 业务逻辑层"""
    
    def __init__(self, db: ThreeLayerHistoryDB = None):
        """
        初始化历史记录管理器
        
        Args:
            db: 数据库管理器实例，如果为None则创建新实例
        """
        self.db = db or ThreeLayerHistoryDB()
    
    def save_feedback_session(self, client_name: str, worker: str, project_directory: str,
                            ai_prompt: str, user_feedback: str, command_logs: str = "",
                            images: List[Tuple[str, str, bytes]] = None) -> str:
        """
        保存反馈会话
        
        Args:
            client_name: AI应用名称
            worker: 工作者环境标识
            project_directory: 项目目录
            ai_prompt: AI提示
            user_feedback: 用户反馈
            command_logs: 命令日志
            images: 图片列表 [(路径, 名称, 数据), ...]
            
        Returns:
            会话ID
        """
        # 生成隔离键
        isolation_key = IsolationUtils.generate_isolation_key(client_name, worker, project_directory)
        project_name = os.path.basename(project_directory.rstrip("/\\"))
        
        # 创建对话记录
        record = ConversationRecord(
            isolation_key=isolation_key,
            client_name=client_name,
            worker=worker,
            project_name=project_name,
            project_directory=project_directory,
            ai_prompt=ai_prompt,
            user_feedback=user_feedback,
            command_logs=command_logs
        )
        
        # 处理图片
        conversation_images = []
        if images:
            for image_path, image_name, image_data in images:
                conversation_images.append(ConversationImage(
                    image_path=image_path,
                    image_name=image_name,
                    image_data=image_data
                ))
        
        # 保存到数据库
        conversation_id = self.db.save_conversation(record, conversation_images)
        return record.session_id
    
    def get_current_isolation_history(self, client_name: str, worker: str, project_directory: str,
                                    limit: int = 100, offset: int = 0) -> List[ConversationRecord]:
        """获取当前隔离组合的历史记录"""
        isolation_key = IsolationUtils.generate_isolation_key(client_name, worker, project_directory)
        return self.db.get_conversations(isolation_key, limit, offset)
    
    def search_current_isolation(self, client_name: str, worker: str, project_directory: str,
                               query: str, limit: int = 100) -> List[ConversationRecord]:
        """搜索当前隔离组合的历史记录"""
        isolation_key = IsolationUtils.generate_isolation_key(client_name, worker, project_directory)
        return self.db.search_conversations(isolation_key, query, limit)

    
    def get_project_browsing_history(self, client_name: str, worker: str, 
                                   limit: int = 100, offset: int = 0) -> List[ConversationRecord]:
        """获取项目浏览模式的历史记录（当前AI应用+环境下所有项目）"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversations 
            WHERE client_name = ? AND worker = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (client_name, worker, limit, offset))
        
        rows = cursor.fetchall()
        return [self.db._row_to_conversation_record(row) for row in rows]
    
    def get_environment_browsing_history(self, client_name: str, 
                                       limit: int = 100, offset: int = 0) -> List[ConversationRecord]:
        """获取环境浏览模式的历史记录（当前AI应用下所有环境）"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversations 
            WHERE client_name = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (client_name, limit, offset))
        
        rows = cursor.fetchall()
        return [self.db._row_to_conversation_record(row) for row in rows]
    
    def get_global_browsing_history(self, limit: int = 100, offset: int = 0) -> List[ConversationRecord]:
        """获取全局浏览模式的历史记录（所有AI应用、环境、项目）"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM conversations 
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        
        rows = cursor.fetchall()
        return [self.db._row_to_conversation_record(row) for row in rows]
    
    def get_available_clients(self) -> List[str]:
        """获取所有可用的AI应用"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT DISTINCT client_name FROM conversations ORDER BY client_name')
        rows = cursor.fetchall()
        
        return [row[0] for row in rows]
    
    def get_available_workers(self, client_name: str = None) -> List[str]:
        """获取所有可用的工作者环境"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        if client_name:
            cursor.execute('SELECT DISTINCT worker FROM conversations WHERE client_name = ? ORDER BY worker', (client_name,))
        else:
            cursor.execute('SELECT DISTINCT worker FROM conversations ORDER BY worker')
        
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    
    def get_available_projects(self, client_name: str = None, worker: str = None) -> List[str]:
        """获取所有可用的项目"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        if client_name and worker:
            cursor.execute('SELECT DISTINCT project_name FROM conversations WHERE client_name = ? AND worker = ? ORDER BY project_name', (client_name, worker))
        elif client_name:
            cursor.execute('SELECT DISTINCT project_name FROM conversations WHERE client_name = ? ORDER BY project_name', (client_name,))
        else:
            cursor.execute('SELECT DISTINCT project_name FROM conversations ORDER BY project_name')
        
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    
    def search_conversations_by_filters(self, query: str = "", client_name: str = None, 
                                      worker: str = None, project_name: str = None,
                                      limit: int = 100) -> List[ConversationRecord]:
        """根据过滤条件搜索对话"""
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        if query:
            conditions.append("(ai_prompt LIKE ? OR user_feedback LIKE ? OR command_logs LIKE ?)")
            params.extend([f'%{query}%', f'%{query}%', f'%{query}%'])
        
        if client_name:
            conditions.append("client_name = ?")
            params.append(client_name)
        
        if worker:
            conditions.append("worker = ?")
            params.append(worker)
        
        if project_name:
            conditions.append("project_name = ?")
            params.append(project_name)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        cursor.execute(f'''
            SELECT * FROM conversations 
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
        ''', params + [limit])
        
        rows = cursor.fetchall()
        return [self.db._row_to_conversation_record(row) for row in rows]

    
    def export_conversations_to_json(self, conversations: List[ConversationRecord], file_path: str):
        """导出对话记录到JSON格式"""
        export_data = []
        for conv in conversations:
            conv_data = {
                'session_id': conv.session_id,
                'isolation_key': conv.isolation_key,
                'client_name': conv.client_name,
                'worker': conv.worker,
                'project_name': conv.project_name,
                'project_directory': conv.project_directory,
                'ai_prompt': conv.ai_prompt,
                'user_feedback': conv.user_feedback,
                'command_logs': conv.command_logs,
                'created_at': conv.created_at.isoformat() if conv.created_at else None,
                'updated_at': conv.updated_at.isoformat() if conv.updated_at else None
            }
            
            # 获取关联的图片
            images = self.db.get_conversation_images(conv.id, conv.isolation_key)
            if images:
                conv_data['images'] = [
                    {
                        'image_path': img.image_path,
                        'image_name': img.image_name,
                        'created_at': img.created_at.isoformat() if img.created_at else None
                    }
                    for img in images
                ]
            
            export_data.append(conv_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    def export_conversations_to_csv(self, conversations: List[ConversationRecord], file_path: str):
        """导出对话记录到CSV格式"""
        import csv
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写入标题行
            writer.writerow([
                '会话ID', '隔离键', 'AI应用', '环境', '项目名称', '项目路径',
                'AI提示', '用户反馈', '命令日志', '创建时间', '更新时间'
            ])
            
            # 写入数据行
            for conv in conversations:
                writer.writerow([
                    conv.session_id,
                    conv.isolation_key,
                    conv.client_name,
                    conv.worker,
                    conv.project_name,
                    conv.project_directory,
                    conv.ai_prompt,
                    conv.user_feedback or '',
                    conv.command_logs or '',
                    conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else '',
                    conv.updated_at.strftime('%Y-%m-%d %H:%M:%S') if conv.updated_at else ''
                ])
    
    def export_conversations_to_markdown(self, conversations: List[ConversationRecord], file_path: str):
        """导出对话记录到Markdown格式"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# 对话历史记录导出\n\n")
            f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"总计对话数: {len(conversations)}\n\n")
            
            for i, conv in enumerate(conversations, 1):
                f.write(f"## 对话 {i}\n\n")
                f.write(f"**会话ID**: {conv.session_id}\n")
                f.write(f"**AI应用**: {conv.client_name}\n")
                f.write(f"**环境**: {conv.worker}\n")
                f.write(f"**项目**: {conv.project_name}\n")
                f.write(f"**项目路径**: {conv.project_directory}\n")
                f.write(f"**创建时间**: {conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else '未知'}\n\n")
                
                f.write("### AI提示\n\n")
                f.write(f"```\n{conv.ai_prompt}\n```\n\n")
                
                f.write("### 用户反馈\n\n")
                f.write(f"```\n{conv.user_feedback or '无用户反馈'}\n```\n\n")
                
                if conv.command_logs:
                    f.write("### 命令日志\n\n")
                    f.write(f"```\n{conv.command_logs}\n```\n\n")
                
                # 获取关联的图片
                images = self.db.get_conversation_images(conv.id, conv.isolation_key)
                if images:
                    f.write("### 关联图片\n\n")
                    for img in images:
                        f.write(f"- {img.image_name} ({img.image_path})\n")
                    f.write("\n")
                
                f.write("---\n\n")
    
    