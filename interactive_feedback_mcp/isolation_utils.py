import os
import re
import hashlib
from typing import Optional
from PySide6.QtCore import QSettings

class IsolationUtils:
    """三层项目隔离工具类 - 统一管理所有隔离相关逻辑"""
    
    @staticmethod
    def generate_isolation_key(client_name: str, worker: str, project_directory: str) -> str:
        """生成三层隔离键 - 统一实现
        
        Args:
            client_name: MCP客户端名称
            worker: 工作环境标识符
            project_directory: 项目目录路径
            
        Returns:
            格式化的隔离键字符串
        """
        # Key1: Client name from MCP clientInfo
        key1 = re.sub(r'[^\w]', '_', client_name.lower())

        # Key2: Worker identifier
        key2 = re.sub(r'[^\w]', '_', worker.lower())

        # Key3: Project name
        project_name = os.path.basename(project_directory.rstrip(os.sep + "/\\"))
        key3 = re.sub(r'[^\w]', '_', project_name.lower())
        
        # 组合三层键，限制总长度
        isolation_key = f"{key1}_{key2}_{key3}"
        if len(isolation_key) > 100:
            hash_suffix = IsolationUtils.generate_hash(isolation_key, 8)
            isolation_key = f"{key1[:20]}_{key2[:20]}_{key3[:20]}_{hash_suffix}"
        
        return isolation_key
    
    @staticmethod
    def generate_settings_group_name(isolation_key: str) -> str:
        """生成设置组名
        
        Args:
            isolation_key: 隔离键
            
        Returns:
            设置组名称
        """
        return f"ThreeLayer_{isolation_key}"
    
    @staticmethod
    def generate_hash(content: str, length: Optional[int] = None) -> str:
        """生成MD5哈希
        
        Args:
            content: 要哈希的内容
            length: 截取长度，None表示完整哈希
            
        Returns:
            MD5哈希字符串
        """
        hash_value = hashlib.md5(content.encode()).hexdigest()
        return hash_value[:length] if length else hash_value

class IsolationSettingsManager:
    """三层隔离设置管理器 - 统一管理设置保存/加载"""
    
    def __init__(self, settings: QSettings, isolation_key: str):
        """初始化设置管理器
        
        Args:
            settings: QSettings实例
            isolation_key: 隔离键
        """
        self.settings = settings
        self.group_name = IsolationUtils.generate_settings_group_name(isolation_key)
    
    def save_setting(self, key: str, value) -> None:
        """保存设置
        
        Args:
            key: 设置键名
            value: 设置值
        """
        self.settings.beginGroup(self.group_name)
        self.settings.setValue(key, value)
        self.settings.endGroup()
        self.settings.sync()
    
    def load_setting(self, key: str, default=None, type_hint=None):
        """加载设置
        
        Args:
            key: 设置键名
            default: 默认值
            type_hint: 类型提示
            
        Returns:
            设置值
        """
        self.settings.beginGroup(self.group_name)
        value = self.settings.value(key, default, type=type_hint)
        self.settings.endGroup()
        return value
    
    def remove_setting(self, key: str) -> None:
        """删除设置
        
        Args:
            key: 设置键名
        """
        self.settings.beginGroup(self.group_name)
        self.settings.remove(key)
        self.settings.endGroup()
        self.settings.sync()
    
    def load_multiple_settings(self, settings_config: dict) -> dict:
        """批量加载设置
        
        Args:
            settings_config: 设置配置字典 {key: (default, type)}
            
        Returns:
            设置值字典
        """
        self.settings.beginGroup(self.group_name)
        result = {}
        for key, (default, type_hint) in settings_config.items():
            result[key] = self.settings.value(key, default, type=type_hint)
        self.settings.endGroup()
        return result
    
    def save_multiple_settings(self, settings_dict: dict) -> None:
        """批量保存设置
        
        Args:
            settings_dict: 设置字典 {key: value}
        """
        self.settings.beginGroup(self.group_name)
        for key, value in settings_dict.items():
            self.settings.setValue(key, value)
        self.settings.endGroup()
        self.settings.sync()