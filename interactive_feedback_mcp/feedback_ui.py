# Interactive Feedback MCP UI
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import psutil
import argparse
import subprocess
import threading
import hashlib
import uuid
from datetime import datetime
from typing import Optional, TypedDict, List

# 导入历史记录管理模块
try:
    from .history_db import HistoryManager, ConversationRecord
    from .server import get_default_detail_level
    from .isolation_utils import IsolationUtils, IsolationSettingsManager
    from .timer_manager import TimerManager, ProcessMonitor, DebounceHelper, AutoSubmitTimer
except ImportError:
    # 当直接运行此文件时的回退导入
    from history_db import HistoryManager, ConversationRecord
    from server import get_default_detail_level
    from isolation_utils import IsolationUtils, IsolationSettingsManager
    from timer_manager import TimerManager, ProcessMonitor, DebounceHelper, AutoSubmitTimer

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QTextEdit, QGroupBox, QDialog, QListWidget, QDialogButtonBox, QComboBox, QFileDialog,
    QScrollArea, QFrame, QGridLayout, QMessageBox, QTabWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QSettings, QPoint, QSize, QByteArray, QBuffer, QIODevice, QEvent
from PySide6.QtGui import QTextCursor, QIcon, QKeyEvent, QFont, QFontDatabase, QPalette, QColor, QPixmap, QImage, QClipboard, QShortcut, QKeySequence

# 12个精选的窗口边框颜色
BORDER_COLORS = [
    # 经典色系（第一行）
    "#ffffff",  # 默认白色（实际显示为#e0e0e0）
    "#000000",  # 纯黑色
    "#7f8c8d",  # 银灰色
    "#bdc3c7",  # 浅灰色
    "#34495e",  # 深灰色
    "#2c3e50",  # 深蓝灰色
    
    # 彩色系（第二行）
    "#3498db",  # 清新蓝色
    "#e74c3c",  # 活力红色
    "#2ecc71",  # 自然绿色
    "#f39c12",  # 温暖橙色
    "#9b59b6",  # 优雅紫色
    "#1abc9c",  # 现代青色
]

# 颜色名称映射（用于工具提示）
COLOR_NAMES = {
    "#ffffff": "默认白色", "#000000": "黑色", "#7f8c8d": "灰色",
    "#bdc3c7": "浅灰", "#34495e": "深灰", "#2c3e50": "深蓝灰",
    "#3498db": "蓝色", "#e74c3c": "红色", "#2ecc71": "绿色", 
    "#f39c12": "橙色", "#9b59b6": "紫色", "#1abc9c": "青色"
}

class FeedbackResult(TypedDict):
    command_logs: str
    interactive_feedback: str
    uploaded_images: list[str]

class FeedbackConfig(TypedDict):
    run_command: str
    execute_automatically: bool

def generate_random_filename(extension: str = "jpg") -> str:
    """生成随机文件名，格式为：年月日_时分秒_uuid.扩展名"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_str = str(uuid.uuid4())[:8]  # 取UUID的前8位
    return f"{timestamp}_{random_str}.{extension}"

def ensure_temp_directory(base_dir: str) -> str:
    """确保temp目录存在，返回temp目录的完整路径"""
    temp_dir = os.path.join(base_dir, "temp")
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    return temp_dir

def kill_tree(process: subprocess.Popen):
    killed: list[psutil.Process] = []
    parent = psutil.Process(process.pid)
    for proc in parent.children(recursive=True):
        try:
            proc.kill()
            killed.append(proc)
        except psutil.Error:
            pass
    try:
        parent.kill()
    except psutil.Error:
        pass
    killed.append(parent)

    # Terminate any remaining processes
    for proc in killed:
        try:
            if proc.is_running():
                proc.terminate()
        except psutil.Error:
            pass

def get_user_environment() -> dict[str, str]:
    if sys.platform != "win32":
        return os.environ.copy()

    import ctypes
    from ctypes import wintypes

    # Load required DLLs
    advapi32 = ctypes.WinDLL("advapi32")
    userenv = ctypes.WinDLL("userenv")
    kernel32 = ctypes.WinDLL("kernel32")

    # Constants
    TOKEN_QUERY = 0x0008

    # Function prototypes
    OpenProcessToken = advapi32.OpenProcessToken
    OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    OpenProcessToken.restype = wintypes.BOOL

    CreateEnvironmentBlock = userenv.CreateEnvironmentBlock
    CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.BOOL]
    CreateEnvironmentBlock.restype = wintypes.BOOL

    DestroyEnvironmentBlock = userenv.DestroyEnvironmentBlock
    DestroyEnvironmentBlock.argtypes = [wintypes.LPVOID]
    DestroyEnvironmentBlock.restype = wintypes.BOOL

    GetCurrentProcess = kernel32.GetCurrentProcess
    GetCurrentProcess.argtypes = []
    GetCurrentProcess.restype = wintypes.HANDLE

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    # Get process token
    token = wintypes.HANDLE()
    if not OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        raise RuntimeError("Failed to open process token")

    try:
        # Create environment block
        environment = ctypes.c_void_p()
        if not CreateEnvironmentBlock(ctypes.byref(environment), token, False):
            raise RuntimeError("Failed to create environment block")

        try:
            # Convert environment block to list of strings
            result = {}
            env_ptr = ctypes.cast(environment, ctypes.POINTER(ctypes.c_wchar))
            offset = 0

            while True:
                # Get string at current offset
                current_string = ""
                while env_ptr[offset] != "\0":
                    current_string += env_ptr[offset]
                    offset += 1

                # Skip null terminator
                offset += 1

                # Break if we hit double null terminator
                if not current_string:
                    break

                equal_index = current_string.index("=")
                if equal_index == -1:
                    continue

                key = current_string[:equal_index]
                value = current_string[equal_index + 1:]
                result[key] = value

            return result

        finally:
            DestroyEnvironmentBlock(environment)

    finally:
        CloseHandle(token)

class FeedbackTextEdit(QTextEdit):
    def __init__(self, parent=None, feedback_ui=None):
        super().__init__(parent)
        self.setAcceptRichText(False)  # 禁用富文本粘贴，只允许纯文本
        self.feedback_ui = feedback_ui  # 保存对FeedbackUI实例的引用

        # 连接文本变化信号，当用户输入时停止自动提交倒计时
        self.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self):
        """当文本内容发生变化时停止自动提交倒计时"""
        if self.feedback_ui:
            # 只要用户开始编辑文本（无论是输入还是删除），都停止自动提交
            # 这样可以避免用户正在编辑时突然自动提交的情况
            self.feedback_ui._cancel_auto_submit()

    def keyPressEvent(self, event: QKeyEvent):
        # 检查是否按下Ctrl+Enter或Ctrl+Return
        is_enter = (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter)
        is_ctrl = (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier

        if is_enter and is_ctrl:
            # 尝试查找父FeedbackUI实例
            if self.feedback_ui:
                # 直接使用已保存的引用
                self.feedback_ui._submit_feedback()
            else:
                # 备用方法：通过parent()查找
                parent = self.parent()
                while parent and not isinstance(parent, FeedbackUI):
                    parent = parent.parent()
                if parent:
                    parent._submit_feedback()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        """当文本框获得焦点时停止自动提交倒计时"""
        super().focusInEvent(event)
        if self.feedback_ui:
            self.feedback_ui._cancel_auto_submit()

    def mousePressEvent(self, event):
        """当鼠标点击文本框时停止自动提交倒计时"""
        super().mousePressEvent(event)
        if self.feedback_ui:
            self.feedback_ui._cancel_auto_submit()
    
    def insertFromMimeData(self, source):
        """重写粘贴方法，支持粘贴图片"""
        if source.hasImage() and self.feedback_ui:
            # 剪贴板中有图片且有FeedbackUI引用时
            result = self.feedback_ui._get_clipboard_image(show_message=False)
            if not result:
                # 图片处理失败时，尝试粘贴为文本
                super().insertFromMimeData(source)
        else:
            # 没有图片或没有FeedbackUI引用时，按原方式处理
            super().insertFromMimeData(source)

class QuickReplyEditDialog(QDialog):
    """用于编辑快捷回复的对话框"""
    def __init__(self, parent=None, quick_replies=None):
        super().__init__(parent)
        self.setWindowTitle("编辑快捷回复")
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        # 初始化快捷回复列表
        self.quick_replies = quick_replies or []
        
        # 创建UI
        layout = QVBoxLayout(self)
        
        # 添加说明标签
        label = QLabel("编辑、添加或删除快捷回复项目:")
        layout.addWidget(label)
        
        # 创建列表显示当前快捷回复
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        # 添加现有快捷回复到列表
        for reply in self.quick_replies:
            self.list_widget.addItem(reply)
        layout.addWidget(self.list_widget)
        
        # 编辑区域
        edit_layout = QHBoxLayout()
        self.edit_input = QLineEdit()
        self.edit_input.setPlaceholderText("输入新的快捷回复...")
        edit_layout.addWidget(self.edit_input)
        
        # 添加按钮
        self.add_button = QPushButton("添加")
        self.add_button.clicked.connect(self._add_reply)
        edit_layout.addWidget(self.add_button)
        
        layout.addLayout(edit_layout)
        
        # 操作按钮行
        button_layout = QHBoxLayout()
        
        # 删除按钮
        self.delete_button = QPushButton("删除所选")
        self.delete_button.clicked.connect(self._delete_reply)
        button_layout.addWidget(self.delete_button)
        
        # 上移按钮
        self.move_up_button = QPushButton("上移")
        self.move_up_button.clicked.connect(self._move_up)
        button_layout.addWidget(self.move_up_button)
        
        # 下移按钮
        self.move_down_button = QPushButton("下移")
        self.move_down_button.clicked.connect(self._move_down)
        button_layout.addWidget(self.move_down_button)
        
        layout.addLayout(button_layout)
        
        # 底部按钮行（确定/取消）
        dialog_buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        dialog_buttons.accepted.connect(self.accept)
        dialog_buttons.rejected.connect(self.reject)
        layout.addWidget(dialog_buttons)
        
        # 连接列表项被选中的信号
        self.list_widget.itemSelectionChanged.connect(self._selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._edit_item)
        
        # 初始化按钮状态
        self._selection_changed()
    
    def _add_reply(self):
        """添加新的快捷回复"""
        text = self.edit_input.text().strip()
        if text:
            self.list_widget.addItem(text)
            self.edit_input.clear()
    
    def _delete_reply(self):
        """删除选中的快捷回复"""
        selected_items = self.list_widget.selectedItems()
        if selected_items:
            for item in selected_items:
                row = self.list_widget.row(item)
                self.list_widget.takeItem(row)
    
    def _move_up(self):
        """上移选中的项目"""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        current_row = self.list_widget.row(selected_items[0])
        if current_row > 0:
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row - 1, item)
            self.list_widget.setCurrentItem(item)
    
    def _move_down(self):
        """下移选中的项目"""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        current_row = self.list_widget.row(selected_items[0])
        if current_row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(current_row)
            self.list_widget.insertItem(current_row + 1, item)
            self.list_widget.setCurrentItem(item)
    
    def _selection_changed(self):
        """当列表选择变化时更新按钮状态"""
        has_selection = bool(self.list_widget.selectedItems())
        self.delete_button.setEnabled(has_selection)
        self.move_up_button.setEnabled(has_selection and self.list_widget.currentRow() > 0)
        self.move_down_button.setEnabled(has_selection and self.list_widget.currentRow() < self.list_widget.count() - 1)
    
    def _edit_item(self, item):
        """双击编辑项目"""
        self.edit_input.setText(item.text())
        self.list_widget.takeItem(self.list_widget.row(item))
    
    def get_quick_replies(self):
        """获取编辑后的快捷回复列表"""
        result = []
        for i in range(self.list_widget.count()):
            result.append(self.list_widget.item(i).text())
        return result

class LogSignals(QObject):
    append_log = Signal(str)

class PersonalizationManager:
    """个性化设置管理器（基于三层隔离）"""

    def __init__(self, isolation_key: str):
        self.isolation_key = isolation_key
        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")
        self.isolation_settings = IsolationSettingsManager(self.settings, isolation_key)

    def load_border_color(self) -> str:
        """加载边框颜色设置"""
        return self.isolation_settings.load_setting("window_border_color", "#4CAF50", str)

    def save_border_color(self, color: str):
        """保存边框颜色设置"""
        self.isolation_settings.save_setting("window_border_color", color)

    def apply_border_color(self, color: str, window: QMainWindow):
        """应用颜色到窗口底色 - 更自然的方式"""
        # 白色底色实际显示为浅灰色以保证可见性
        display_color = "#f5f5f5" if color == "#ffffff" else color

        # 设置窗口底色而不是边框
        window.setStyleSheet(f"""
            QMainWindow {{
                background-color: {display_color};
            }}
        """)

    def load_custom_title(self) -> str:
        """加载自定义标题"""
        return self.isolation_settings.load_setting("custom_title", "", str)

    def save_custom_title(self, title: str):
        """保存自定义标题"""
        self.isolation_settings.save_setting("custom_title", title)

    def load_title_mode(self) -> str:
        """加载标题模式"""
        return self.isolation_settings.load_setting("title_mode", "auto", str)

    def save_title_mode(self, mode: str):
        """保存标题模式"""
        self.isolation_settings.save_setting("title_mode", mode)

    def apply_window_title(self, title_mode: str, custom_title: str, window: QMainWindow, isolation_key: str):
        """应用窗口标题（支持动态和自定义模式）"""
        if title_mode == "dynamic":
            title = f"Interactive: {isolation_key}"
        else:  # custom mode
            if custom_title.strip():
                title = custom_title.strip()
            else:
                # 默认显示 key1+key2+key3 格式
                title = isolation_key

        window.setWindowTitle(title)

class ColorSelectionWidget(QWidget):
    """颜色选择控件"""
    color_changed = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.color_buttons = []
        self.selected_color = "#ffffff"
        self._create_color_buttons()
    
    def _create_color_buttons(self):
        """创建颜色选择按钮网格"""
        layout = QGridLayout(self)
        layout.setSpacing(5)
        
        # 创建2行6列的颜色按钮网格
        for i, color in enumerate(BORDER_COLORS):
            row = i // 6
            col = i % 6
            
            button = QPushButton()
            button.setFixedSize(40, 30)
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 2px solid #ccc;
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #666;
                }}
                QPushButton:checked {{
                    border: 3px solid #000;
                    border-radius: 4px;
                }}
            """)
            button.setCheckable(True)
            button.setToolTip(COLOR_NAMES[color])
            button.clicked.connect(lambda checked, c=color: self._on_color_selected(c))
            
            self.color_buttons.append(button)
            layout.addWidget(button, row, col)
        
        # 默认选中白色
        self.color_buttons[0].setChecked(True)
    
    def _on_color_selected(self, color: str):
        """处理颜色选择"""
        # 取消其他按钮的选中状态
        for button in self.color_buttons:
            button.setChecked(False)
        
        # 选中当前按钮
        color_index = BORDER_COLORS.index(color)
        self.color_buttons[color_index].setChecked(True)
        
        self.selected_color = color
        self.color_changed.emit(color)
    
    def set_selected_color(self, color: str):
        """设置选中的颜色"""
        if color in BORDER_COLORS:
            self.selected_color = color
            # 更新按钮状态
            for button in self.color_buttons:
                button.setChecked(False)
            color_index = BORDER_COLORS.index(color)
            self.color_buttons[color_index].setChecked(True)
    
    def get_selected_color(self) -> str:
        """获取当前选中的颜色"""
        return self.selected_color

class TitleCustomizationWidget(QWidget):
    """标题自定义控件（支持动态和自定义模式）"""
    title_changed = Signal(str)
    title_mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode_selector = QComboBox()  # 动态/自定义模式选择
        self.title_input = QLineEdit()
        self.preview_label = QLabel()
        self._setup_ui()

    def _setup_ui(self):
        """设置UI布局"""
        layout = QVBoxLayout(self)
        
        # 模式选择
        mode_layout = QHBoxLayout()
        mode_label = QLabel("标题模式:")
        self.mode_selector.addItem("动态模式", "dynamic")
        self.mode_selector.addItem("自定义模式", "custom")
        self.mode_selector.currentTextChanged.connect(self._on_mode_changed)
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_selector)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # 自定义标题输入
        input_layout = QHBoxLayout()
        input_label = QLabel("自定义内容:")
        self.title_input.setMaxLength(50)  # 限制50个字符
        self.title_input.setPlaceholderText("最多50个字符")
        self.title_input.textChanged.connect(self._on_title_changed)
        
        input_layout.addWidget(input_label)
        input_layout.addWidget(self.title_input)
        layout.addLayout(input_layout)
        
        # 预览标签
        preview_layout = QHBoxLayout()
        preview_title_label = QLabel("预览:")
        self.preview_label.setStyleSheet("color: #666; font-style: italic;")
        self.preview_label.setWordWrap(True)
        
        preview_layout.addWidget(preview_title_label)
        preview_layout.addWidget(self.preview_label)
        layout.addLayout(preview_layout)
        
        # 初始化预览
        self._update_preview()
    
    def _on_mode_changed(self):
        """模式变化处理"""
        mode = self.get_title_mode()
        self.title_input.setEnabled(mode == "custom")
        self._update_preview()
        self.title_mode_changed.emit(mode)
    
    def _on_title_changed(self):
        """标题内容变化处理"""
        self._update_preview()
        self.title_changed.emit(self.get_custom_title())
    
    def _update_preview(self):
        """更新预览显示"""
        mode = self.get_title_mode()
        if mode == "dynamic":
            self.preview_label.setText("Interactive: {client}_{worker}_{project}")
        else:
            custom_title = self.get_custom_title()
            if custom_title.strip():
                self.preview_label.setText(custom_title.strip())
            else:
                # 默认显示 key1+key2+key3 格式
                self.preview_label.setText("{client}_{worker}_{project}")

    def set_title_mode(self, mode: str):
        """设置标题模式（dynamic/custom）"""
        index = 0 if mode == "dynamic" else 1
        self.mode_selector.setCurrentIndex(index)
        self._on_mode_changed()

    def get_title_mode(self) -> str:
        """获取标题模式"""
        return self.mode_selector.currentData()

    def set_custom_title(self, title: str):
        """设置自定义标题"""
        self.title_input.setText(title[:50])  # 确保不超过50个字符
        self._update_preview()

    def get_custom_title(self) -> str:
        """获取自定义标题"""
        return self.title_input.text()

    def update_preview_with_isolation_key(self, isolation_key: str):
        """使用隔离键更新动态模式预览"""
        mode = self.get_title_mode()
        if mode == "dynamic":
            self.preview_label.setText(f"Interactive: {isolation_key}")

class FeedbackUI(QMainWindow):
    def __init__(self, project_directory: str, prompt: str, worker: str = "default", client_name: str = "unknown-client", detail_level: str = None):
        super().__init__()
        
        # If detail_level is not provided, get it from environment variable
        if detail_level is None:
            detail_level = get_default_detail_level()
        
        self.project_directory = project_directory
        self.prompt = prompt
        self.worker = worker
        self.client_name = client_name
        self.detail_level = detail_level
        
        # 生成三层隔离键
        self.isolation_key = IsolationUtils.generate_isolation_key(client_name, worker, project_directory)
        
        # 初始化个性化管理器
        self.personalization_manager = PersonalizationManager(self.isolation_key)
        
        # 初始化历史记录管理器
        self.history_manager = HistoryManager()
        
        # 初始化定时器管理系统
        self.timer_manager = TimerManager()
        self.process_monitor = ProcessMonitor(self.timer_manager)
        self.debounce_helper = DebounceHelper(self.timer_manager)
        self.auto_submit_timer = AutoSubmitTimer(self.timer_manager)

        # 设置统一的自动提交取消监听
        self._setup_auto_submit_cancellation()

        # 设置应用程序使用Fusion样式，这是一个跨平台的样式，最接近原生外观
        QApplication.setStyle("Fusion")
        
        self.process: Optional[subprocess.Popen] = None
        self.log_buffer = []
        self.feedback_result = None
        self.log_signals = LogSignals()
        self.log_signals.append_log.connect(self._append_log)
        
        # 初始化上传图片路径列表
        self.uploaded_images = []
        
        # 窗口状态记录（用于记录显示/隐藏终端时的窗口状态）
        self.window_state_with_terminal = None  # 存储终端显示时的窗口大小和位置
        self.window_state_without_terminal = None  # 存储终端隐藏时的窗口大小和位置
        
        # 确保temp目录存在
        self.temp_dir = ensure_temp_directory(self.project_directory)
        
        # 图片预览相关
        self.image_previews = []  # 存储图片预览控件的列表
        self.image_labels = []    # 存储图片标签控件的列表

        # 自动提交相关
        self.auto_submit_enabled = False  # 是否启用自动提交
        self.auto_submit_wait_time = 60   # 等待时间（秒）

        self.countdown_remaining = 0      # 剩余倒计时时间
        self.original_submit_text = ""    # 原始提交按钮文本
        self.auto_fill_first_reply = True # 自动提交时如果反馈为空，是否自动填入第一条预设回复
        
        # 末尾自动附加内容相关
        self.auto_append_enabled = True  # 是否启用末尾自动附加内容
        self.auto_append_content = ""  # 将在设置加载时设置默认值

        # 窗口大小设置 - 修复窗口过大问题
        self.default_size = (460, 360)
        self.size_multiplier = 1
        self.size_states = [1, 1.5, 2]  # 窗口大小倍数状态，降低最大倍数

        # 应用保存的个性化设置
        # 加载并应用边框颜色
        saved_border_color = self.personalization_manager.load_border_color()
        self.personalization_manager.apply_border_color(saved_border_color, self)
        
        # 加载并应用窗口标题
        saved_title_mode = self.personalization_manager.load_title_mode()
        saved_custom_title = self.personalization_manager.load_custom_title()
        self.personalization_manager.apply_window_title(saved_title_mode, saved_custom_title, self, self.isolation_key)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "images", "feedback.png")
        self.setWindowIcon(QIcon(icon_path))

        # 设置默认窗口大小
        self.resize(*self.default_size)

        self.settings = QSettings("InteractiveFeedbackMCP", "InteractiveFeedbackMCP")
        
        # 初始化设置管理器
        self.isolation_settings = IsolationSettingsManager(self.settings, self.isolation_key)

        # 从三层隔离设置中加载窗口置顶设置
        stay_on_top_enabled = self.isolation_settings.load_setting("stay_on_top_enabled", True, bool)

        if stay_on_top_enabled:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        
        # Load general UI settings for the main window (geometry, state)
        self.settings.beginGroup("MainWindow_General")
        geometry = self.settings.value("geometry")
        state = self.settings.value("windowState")
        self.settings.endGroup()
        
        # 先恢复几何信息（但不包括位置，位置将在后面单独处理）
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
            
        # 从三层隔离设置中加载窗口大小设置
        window_settings = self.isolation_settings.load_multiple_settings({
            "custom_width": (-1, int),
            "custom_height": (-1, int),
            "use_custom_position": (False, bool),
            "custom_position_x": (None, int),
            "custom_position_y": (None, int)
        })
        
        custom_width = window_settings["custom_width"]
        custom_height = window_settings["custom_height"]
        if custom_width > 0 and custom_height > 0:
            self.resize(custom_width, custom_height)
        else:
            # 仅在没有自定义大小设置时使用默认大小
            self.resize(*self.default_size)
            
        # 检查是否有用户保存的自定义位置
        self.use_custom_position = window_settings["use_custom_position"]
        custom_x = window_settings["custom_position_x"]
        custom_y = window_settings["custom_position_y"]
        self.custom_position = None
        if custom_x is not None and custom_y is not None:
            from PySide6.QtCore import QPoint
            self.custom_position = QPoint(custom_x, custom_y)
        
        # 立即应用自定义位置（如果有的话），覆盖restoreGeometry的位置设置
        if self.use_custom_position and self.custom_position:
            if self._is_position_valid(self.custom_position):
                # 位置有效，直接应用
                self.move(self.custom_position)
            else:
                # 位置可能无效（如显示器配置改变），尝试智能修复
                fixed_position = self._fix_invalid_position(self.custom_position)
                if fixed_position:
                    # 修复成功，使用修复后的位置
                    self.move(fixed_position)
                    # 更新保存的位置
                    self.custom_position = fixed_position
                    self.isolation_settings.save_multiple_settings({
                        "custom_position_x": fixed_position.x(),
                        "custom_position_y": fixed_position.y()
                    })
                else:
                    # 无法修复，重置为默认位置
                    self.use_custom_position = False
                    self.custom_position = None
                    self.isolation_settings.save_setting("use_custom_position", False)
                    self.isolation_settings.remove_setting("custom_position_x")
                    self.isolation_settings.remove_setting("custom_position_y")
            
        # 从三层隔离设置中加载快捷回复设置
        app_settings = self.isolation_settings.load_multiple_settings({
            "quick_replies": ([], list),
            "auto_append_enabled": (True, bool),
            "auto_append_content": ("继续，请务必完成后，必须call MCP tool `interactive_feedback` 询问我的反馈。", str),
            "run_command": ("", str),
            "execute_automatically": (False, bool)
        })
        
        self.quick_replies = app_settings["quick_replies"]
        # 如果没有保存的快捷回复，使用默认值
        if not self.quick_replies:
            self.quick_replies = ["继续", "结束对话","使用MODE: RESEARCH重新开始"]
        
        # 加载末尾自动附加内容设置
        self.auto_append_enabled = app_settings["auto_append_enabled"]
        self.auto_append_content = app_settings["auto_append_content"]
        
        # Load settings from three-layer isolation (command, auto-execute, selected tab index)
        loaded_run_command = app_settings["run_command"]
        loaded_execute_auto = app_settings["execute_automatically"]
        
        self.config: FeedbackConfig = {
            "run_command": loaded_run_command,
            "execute_automatically": loaded_execute_auto
        }

        self._create_ui() # self.config is used here to set initial values
        
        # 确保窗口位于正确位置（仅在没有自定义位置时）
        if not (self.use_custom_position and self.custom_position):
            QTimer.singleShot(0, self._position_window_bottom_right)
        
        # 初始化图片预览
        QTimer.singleShot(100, self._update_image_preview)

        if self.config.get("execute_automatically", False):
            self._run_command()

    
    

    def _position_window_bottom_right(self):
        """将窗口定位在屏幕右下角或用户自定义位置"""
        # 如果有用户保存的自定义位置，优先使用
        if hasattr(self, 'use_custom_position') and self.use_custom_position and self.custom_position:
            # 验证保存的位置是否在当前可用的屏幕范围内
            if self._is_position_valid(self.custom_position):
                self.move(self.custom_position)
                return
            else:
                # 如果保存的位置无效（比如屏幕配置改变），重置为默认位置
                self.use_custom_position = False
                self.custom_position = None
                # 清除无效的保存位置
                self.isolation_settings.save_setting("use_custom_position", False)
                self.isolation_settings.remove_setting("custom_position_x")
                self.isolation_settings.remove_setting("custom_position_y")
            
        # 使用默认的右下角位置
        current_width = self.width()
        current_height = self.height()
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = screen_geometry.width() - current_width - 20  # 右边距20像素
        y = screen_geometry.height() - current_height - 40  # 下边距40像素
        self.move(x, y)

    def _is_position_valid(self, position):
        """检查给定位置是否在当前可用的屏幕范围内"""
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QPoint, QRect
            
            if not position or not isinstance(position, QPoint):
                return False
            
            # 获取所有屏幕的几何信息
            screens = QApplication.screens()
            if not screens:
                return False
            
            # 使用默认窗口大小进行验证，避免依赖当前窗口大小
            default_width, default_height = self.default_size
            
            for screen in screens:
                screen_geometry = screen.availableGeometry()
                
                # 检查位置是否在这个屏幕的范围内
                # 只需要确保窗口的左上角在屏幕范围内，或者窗口与屏幕有重叠
                pos_x, pos_y = position.x(), position.y()
                
                # 方法1：检查左上角是否在屏幕内
                if screen_geometry.contains(position):
                    return True
                
                # 方法2：检查窗口是否与屏幕有重叠（更宽松的验证）
                window_rect = QRect(pos_x, pos_y, default_width, default_height)
                if screen_geometry.intersects(window_rect):
                    # 确保至少有一部分标题栏可见（只需要50像素宽度）
                    title_bar_rect = QRect(pos_x, pos_y, min(default_width, 50), 30)
                    if screen_geometry.intersects(title_bar_rect):
                        return True
            
            return False
        except Exception:
            # 如果检查过程中出现任何错误，返回False以使用默认位置
            return False

    def _fix_invalid_position(self, position):
        """尝试修复无效的窗口位置，将其移动到最近的有效屏幕"""
        try:
            from PySide6.QtWidgets import QApplication
            from PySide6.QtCore import QPoint
            
            if not position:
                return None
            
            screens = QApplication.screens()
            if not screens:
                return None
            
            pos_x, pos_y = position.x(), position.y()
            best_screen = None
            min_distance = float('inf')
            
            # 找到距离原位置最近的屏幕
            for screen in screens:
                screen_geometry = screen.availableGeometry()
                
                # 计算位置到屏幕中心的距离
                screen_center_x = screen_geometry.x() + screen_geometry.width() // 2
                screen_center_y = screen_geometry.y() + screen_geometry.height() // 2
                distance = ((pos_x - screen_center_x) ** 2 + (pos_y - screen_center_y) ** 2) ** 0.5
                
                if distance < min_distance:
                    min_distance = distance
                    best_screen = screen_geometry
            
            if best_screen:
                # 将位置调整到最近屏幕的可用区域内
                default_width, default_height = self.default_size
                
                # 确保窗口完全在屏幕内
                new_x = max(best_screen.x(), 
                           min(pos_x, best_screen.x() + best_screen.width() - default_width))
                new_y = max(best_screen.y(), 
                           min(pos_y, best_screen.y() + best_screen.height() - default_height))
                
                # 如果调整后的位置与原位置差距太大，说明原位置确实无效
                if abs(new_x - pos_x) > best_screen.width() or abs(new_y - pos_y) > best_screen.height():
                    # 位置差距太大，放在屏幕的右下角
                    new_x = best_screen.x() + best_screen.width() - default_width - 20
                    new_y = best_screen.y() + best_screen.height() - default_height - 40
                
                return QPoint(new_x, new_y)
            
            return None
        except Exception:
            return None

    def _format_windows_path(self, path: str) -> str:
        if sys.platform == "win32":
            # Convert forward slashes to backslashes
            path = path.replace("/", "\\")
            # Capitalize drive letter if path starts with x:\
            if len(path) >= 2 and path[1] == ":" and path[0].isalpha():
                path = path[0].upper() + path[1:]
        return path

    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 创建选项卡控件
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)
        
        # 准备"反馈"、"终端"和"设置"选项卡的内容
        
        # Command section - 将作为"终端"选项卡的内容
        self.command_group = QGroupBox()  # 不再需要标题，因为选项卡有标签
        command_layout = QVBoxLayout(self.command_group)

        # Working directory label
        formatted_path = self._format_windows_path(self.project_directory)
        working_dir_label = QLabel(f"工作目录: {formatted_path}")
        command_layout.addWidget(working_dir_label)

        # Command input row
        command_input_layout = QHBoxLayout()
        self.command_entry = QLineEdit()
        self.command_entry.setText(self.config["run_command"])
        self.command_entry.returnPressed.connect(self._run_command)
        self.command_entry.textChanged.connect(self._update_config)
        self.run_button = QPushButton("运行(&R)")
        self.run_button.clicked.connect(self._run_command)
        self.run_button.setMinimumWidth(80)
        self.run_button.setMinimumHeight(30)
        self.run_button.setAutoFillBackground(True)  # 设置自动填充背景

        command_input_layout.addWidget(self.command_entry)
        command_input_layout.addWidget(self.run_button)
        command_layout.addLayout(command_input_layout)

        # Auto-execute and save config row
        auto_layout = QHBoxLayout()
        self.auto_check = QCheckBox("下次自动执行（打开此应用时自动运行命令）")
        self.auto_check.setChecked(self.config.get("execute_automatically", False))
        self.auto_check.stateChanged.connect(self._update_config)

        save_button = QPushButton("保存命令(&S)")
        save_button.clicked.connect(self._save_config)
        save_button.setMinimumWidth(100)
        save_button.setMinimumHeight(30)
        save_button.setAutoFillBackground(True)  # 设置自动填充背景

        auto_layout.addWidget(self.auto_check)
        auto_layout.addStretch()
        auto_layout.addWidget(save_button)
        command_layout.addLayout(auto_layout)

        # Console section (now part of command_group)
        console_group = QGroupBox("控制台")
        console_layout_internal = QVBoxLayout(console_group)
        console_group.setMinimumHeight(200)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(False)  # 设置为可编辑
        font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        font.setPointSize(9)
        self.log_text.setFont(font)
        console_layout_internal.addWidget(self.log_text)

        # Control buttons
        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("清除(&C)")
        self.clear_button.clicked.connect(self.clear_logs)
        self.clear_button.setMinimumWidth(80)
        self.clear_button.setMinimumHeight(30)
        self.clear_button.setAutoFillBackground(True)  # 设置自动填充背景
        
        button_layout.addStretch()
        button_layout.addWidget(self.clear_button)
        console_layout_internal.addLayout(button_layout)
        
        command_layout.addWidget(console_group)

        # Feedback section - 将作为"反馈"选项卡的内容
        self.feedback_group = QGroupBox()  # 不再需要标题，因为选项卡有标签
        feedback_layout = QVBoxLayout(self.feedback_group)

        # Short description label (from self.prompt)
        self.description_label = QLabel(self.prompt)
        self.description_label.setWordWrap(True)
        feedback_layout.addWidget(self.description_label)
        
        # Detail level information
        detail_level_text = {
            "brief": "简短模式 - 提供一行总结",
            "detailed": "详细模式 - 提供多行描述，包含主要变更点",
            "comprehensive": "全面模式 - 提供完整描述，包含背景和技术细节"
        }
        self.detail_level_label = QLabel(f"📝 {detail_level_text.get(self.detail_level, '未知模式')}")
        self.detail_level_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        feedback_layout.addWidget(self.detail_level_label)

        self.feedback_text = FeedbackTextEdit(feedback_ui=self)
        font_metrics = self.feedback_text.fontMetrics()
        row_height = font_metrics.height()
        # Calculate height for 5 lines + some padding for margins
        padding = self.feedback_text.contentsMargins().top() + self.feedback_text.contentsMargins().bottom() + 5 # 5 is extra vertical padding
        self.feedback_text.setMinimumHeight(5 * row_height + padding)

        self.feedback_text.setPlaceholderText("在此输入您的反馈 (按Ctrl+Enter提交)")
        
        # 根据系统类型设置快捷键提示
        if sys.platform == "darwin":  # macOS
            submit_button_text = "发送反馈(&S) (Cmd+Enter)"
            shortcut_text = "Cmd+Enter"
        else:  # Windows, Linux等其他系统
            submit_button_text = "发送反馈(&S) (Ctrl+Enter)"
            shortcut_text = "Ctrl+Enter"
        
        # 更新占位符文本
        self.feedback_text.setPlaceholderText(f"在此输入您的反馈 (按{shortcut_text}提交)")
        
        # 为文本框添加全局快捷键支持
        submit_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        submit_shortcut.activated.connect(self._submit_feedback)
        
        # 在Windows上额外添加Ctrl+Enter快捷键
        if sys.platform == "win32":
            enter_shortcut = QShortcut(QKeySequence("Ctrl+Enter"), self)
            enter_shortcut.activated.connect(self._submit_feedback)
        
        submit_button = QPushButton(submit_button_text)
        submit_button.setAutoFillBackground(True)
        submit_button.clicked.connect(self._submit_feedback)
        submit_button.setMinimumWidth(200)
        submit_button.setMinimumHeight(60)
        # 设置大小策略为自适应
        submit_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 保存按钮引用和原始文本，用于自动提交倒计时
        self.submit_button = submit_button
        self.original_submit_text = submit_button_text
        
        # 创建水平布局来包含提交按钮和末尾自动附加内容功能区域
        submit_layout = QHBoxLayout()
        
        # 发送反馈按钮（保持Expanding）
        submit_layout.addWidget(submit_button)
        
        # 添加竖线分隔符
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("color: #cccccc;")
        submit_layout.addWidget(separator)
        
        # 末尾自动附加内容功能区域
        auto_append_widget = QWidget()
        auto_append_layout = QVBoxLayout(auto_append_widget)
        auto_append_layout.setContentsMargins(10, 5, 10, 5)
        auto_append_layout.setSpacing(5)
        
        # 勾选框
        self.auto_append_check = QCheckBox("末尾自动附加内容")
        self.auto_append_check.setChecked(self.auto_append_enabled)
        self.auto_append_check.stateChanged.connect(self._update_auto_append_settings)
        auto_append_layout.addWidget(self.auto_append_check)
        
        # 自定义内容输入框
        self.auto_append_input = QLineEdit()
        self.auto_append_input.setText(self.auto_append_content)
        self.auto_append_input.setPlaceholderText("输入要自动附加的内容...")
        self.auto_append_input.textChanged.connect(self._update_auto_append_settings)
        auto_append_layout.addWidget(self.auto_append_input)
        
        submit_layout.addWidget(auto_append_widget)
        
        feedback_layout.addWidget(self.feedback_text)
        
        # 第一行：开始实施和快捷回复相关按钮
        quick_reply_layout = QHBoxLayout()
        
        # 开始实施按钮 - 放在最左侧
        start_button = QPushButton("开始实施")
        start_button.clicked.connect(lambda: self._insert_quick_reply("开始实施"))
        start_button.setMinimumHeight(30)
        start_button.setMinimumWidth(100)  # 设置最小宽度
        start_button.setAutoFillBackground(True)
        # 设置大小策略为Expanding，允许按钮水平方向扩展
        start_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        quick_reply_layout.addWidget(start_button, 1)  # 设置拉伸因子为1
        
        # 快捷回复组合框 - 放在中间
        self.quick_reply_combo = QComboBox()
        self.quick_reply_combo.setMinimumHeight(30)
        self.quick_reply_combo.setMinimumWidth(180)
        # 设置大小策略为Expanding，允许组合框水平方向扩展
        self.quick_reply_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 添加快捷回复选项
        for reply in self.quick_replies:
            self.quick_reply_combo.addItem(reply)
        # 连接信号：当选择变更时自动填入文本框
        self.quick_reply_combo.activated.connect(self._apply_selected_quick_reply)
        quick_reply_layout.addWidget(self.quick_reply_combo, 2)  # 设置拉伸因子为2，使其比其他按钮占更多空间
        
        # 编辑快捷回复按钮 - 放在最右侧
        edit_replies_button = QPushButton("编辑快捷回复")
        edit_replies_button.clicked.connect(self._edit_quick_replies)
        edit_replies_button.setMinimumHeight(30)
        edit_replies_button.setMinimumWidth(120)  # 设置最小宽度
        edit_replies_button.setAutoFillBackground(True)
        # 设置大小策略为Expanding，允许按钮水平方向扩展
        edit_replies_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        quick_reply_layout.addWidget(edit_replies_button, 1)  # 设置拉伸因子为1
        
        # 设置布局的间距，让按钮之间有适当的空间
        quick_reply_layout.setSpacing(10)
        
        feedback_layout.addLayout(quick_reply_layout)
        
        # 第二行：图片相关按钮
        image_buttons_layout = QHBoxLayout()
        
        # 上传图片按钮
        upload_image_button = QPushButton("上传图片")
        upload_image_button.clicked.connect(self._upload_image)
        upload_image_button.setMinimumHeight(30)
        upload_image_button.setMinimumWidth(100)  # 设置最小宽度
        upload_image_button.setAutoFillBackground(True)
        # 设置大小策略为Expanding，允许按钮水平方向扩展
        upload_image_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        image_buttons_layout.addWidget(upload_image_button, 1)  # 设置拉伸因子为1
        
        # 从剪贴板获取图片按钮
        clipboard_image_button = QPushButton("从剪贴板获取图片")
        clipboard_image_button.clicked.connect(self._get_clipboard_image)
        clipboard_image_button.setMinimumHeight(30)
        clipboard_image_button.setMinimumWidth(150)  # 设置最小宽度
        clipboard_image_button.setAutoFillBackground(True)
        # 设置大小策略为Expanding，允许按钮水平方向扩展
        clipboard_image_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        image_buttons_layout.addWidget(clipboard_image_button, 1)  # 设置拉伸因子为1
        
        # 添加弹性空间，使按钮能够在窗口调整大小时适当拉伸
        image_buttons_layout.addStretch(0.5)
        
        # 设置布局的间距，让按钮之间有适当的空间
        image_buttons_layout.setSpacing(10)
        
        feedback_layout.addLayout(image_buttons_layout)
        
        # 添加图片预览区域
        preview_group = QGroupBox("图片预览")
        self.preview_group = preview_group  # 保存为类成员变量
        preview_layout = QVBoxLayout(preview_group)
        
        # 创建滚动区域用于图片预览
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMinimumHeight(100)
        self.preview_scroll.setMaximumHeight(200)
        
        # 创建图片预览的容器
        self.preview_container = QWidget()
        self.preview_grid = QGridLayout(self.preview_container)
        self.preview_grid.setSpacing(10)
        self.preview_scroll.setWidget(self.preview_container)
        
        preview_layout.addWidget(self.preview_scroll)
        feedback_layout.addWidget(preview_group)
        
        # 初始化图片预览状态
        self._update_image_preview()
        
        feedback_layout.addLayout(submit_layout)

        # 设置feedback_group的最小高度
        self.feedback_group.setMinimumHeight(self.description_label.sizeHint().height() + 
                                            self.feedback_text.minimumHeight() + 
                                            start_button.sizeHint().height() + 
                                            edit_replies_button.sizeHint().height() + 
                                            upload_image_button.sizeHint().height() + 
                                            clipboard_image_button.sizeHint().height() + 
                                            submit_button.sizeHint().height() + 30) # 增加额外间距

        # 将内容添加到选项卡
        self.tab_widget.addTab(self.feedback_group, "反馈")
        self.tab_widget.addTab(self.command_group, "终端")
        
        # 创建设置选项卡 - 重新设计为3个功能区域
        self.settings_group = QGroupBox()
        settings_layout = QVBoxLayout(self.settings_group)
        
        # ==================== 窗口设置区域 ====================
        window_settings_group = QGroupBox("窗口设置")
        window_settings_layout = QHBoxLayout(window_settings_group)  # 改为水平布局

        # 左列：窗口大小
        size_column = QVBoxLayout()
        size_label = QLabel("窗口大小")
        size_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        size_column.addWidget(size_label)

        self.size_info_label = QLabel(f"当前: {self.width()} x {self.height()}")
        self.size_info_label.setStyleSheet("color: gray; font-size: 11px;")
        size_column.addWidget(self.size_info_label)

        self.resize_button = QPushButton("调整窗口大小")
        self.resize_button.clicked.connect(self._cycle_window_size)
        self.resize_button.setMinimumHeight(25)
        size_column.addWidget(self.resize_button)

        # 中列：窗口位置
        position_column = QVBoxLayout()
        position_label = QLabel("窗口位置")
        position_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        position_column.addWidget(position_label)
        
        self.auto_save_position_check = QCheckBox("自动保存位置")
        self.auto_save_position_check.setChecked(True)
        position_column.addWidget(self.auto_save_position_check)

        # 从三层隔离设置中读取自动保存窗口位置的选项
        auto_save_position = self.isolation_settings.load_setting("auto_save_position", True, bool)
        self.auto_save_position_check.setChecked(auto_save_position)

        # 连接状态变化信号
        self.auto_save_position_check.stateChanged.connect(self._update_auto_save_position)

        reset_position_button = QPushButton("重置位置")
        reset_position_button.clicked.connect(self._reset_window_position)
        reset_position_button.setMinimumHeight(25)
        position_column.addWidget(reset_position_button)

        # 右列：窗口置顶
        stay_on_top_column = QVBoxLayout()
        stay_on_top_label = QLabel("窗口置顶")
        stay_on_top_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        stay_on_top_column.addWidget(stay_on_top_label)
        
        self.stay_on_top_check = QCheckBox("启动时置顶")
        # 从三层隔离设置中读取置顶选项
        stay_on_top_enabled = self.isolation_settings.load_setting("stay_on_top_enabled", True, bool)
        self.stay_on_top_check.setChecked(stay_on_top_enabled)

        self.stay_on_top_check.stateChanged.connect(self._update_stay_on_top_setting)
        stay_on_top_column.addWidget(self.stay_on_top_check)

        toggle_top_button = QPushButton("切换置顶")
        toggle_top_button.clicked.connect(self._toggle_stay_on_top)
        toggle_top_button.setMinimumHeight(25)
        stay_on_top_column.addWidget(toggle_top_button)

        # 将三列添加到窗口设置布局，并添加竖线分隔
        window_settings_layout.addLayout(size_column)
        
        # 添加第一条竖线分隔
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setFrameShadow(QFrame.Sunken)
        separator1.setStyleSheet("color: #cccccc;")
        window_settings_layout.addWidget(separator1)
        
        window_settings_layout.addLayout(position_column)
        
        # 添加第二条竖线分隔
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.VLine)
        separator2.setFrameShadow(QFrame.Sunken)
        separator2.setStyleSheet("color: #cccccc;")
        window_settings_layout.addWidget(separator2)
        
        window_settings_layout.addLayout(stay_on_top_column)
        
        settings_layout.addWidget(window_settings_group)
        
        # ==================== 自动提交设置和标题自定义区域 ====================
        # 创建水平布局来放置两个设置区域
        auto_title_layout = QHBoxLayout()

        # 左侧：自动提交设置
        auto_submit_settings_group = QGroupBox("自动提交设置")
        auto_submit_settings_layout = QVBoxLayout(auto_submit_settings_group)

        # 从三层隔离设置中读取自动提交设置
        auto_submit_settings = self.isolation_settings.load_multiple_settings({
            "auto_submit_enabled": (False, bool),
            "auto_submit_wait_time": (60, int),
            "auto_fill_first_reply": (True, bool)
        })
        self.auto_submit_enabled = auto_submit_settings["auto_submit_enabled"]
        self.auto_submit_wait_time = auto_submit_settings["auto_submit_wait_time"]
        self.auto_fill_first_reply = auto_submit_settings["auto_fill_first_reply"]

        # 启用自动提交的勾选框
        self.auto_submit_check = QCheckBox("启用自动提交")
        self.auto_submit_check.setChecked(self.auto_submit_enabled)
        self.auto_submit_check.stateChanged.connect(self._update_auto_submit_settings)
        auto_submit_settings_layout.addWidget(self.auto_submit_check)

        # 自动填入第一条预设回复的勾选框
        self.auto_fill_first_reply_check = QCheckBox("空时自动填入预设")
        self.auto_fill_first_reply_check.setChecked(self.auto_fill_first_reply)
        self.auto_fill_first_reply_check.stateChanged.connect(self._update_auto_submit_settings)
        auto_submit_settings_layout.addWidget(self.auto_fill_first_reply_check)

        # 等待时间设置
        time_layout = QHBoxLayout()
        time_label = QLabel("等待时间:")
        self.auto_submit_time_input = QLineEdit()
        self.auto_submit_time_input.setText(str(self.auto_submit_wait_time))
        self.auto_submit_time_input.setMaximumWidth(60)
        self.auto_submit_time_input.textChanged.connect(self._update_auto_submit_settings)
        time_unit_label = QLabel("秒")

        time_layout.addWidget(time_label)
        time_layout.addWidget(self.auto_submit_time_input)
        time_layout.addWidget(time_unit_label)
        time_layout.addStretch()
        auto_submit_settings_layout.addLayout(time_layout)

        # 右侧：标题自定义
        title_group = QGroupBox("标题自定义")
        title_layout = QVBoxLayout(title_group)

        # 创建标题自定义控件
        self.title_customization_widget = TitleCustomizationWidget()
        self.title_customization_widget.title_changed.connect(self._on_custom_title_changed)
        self.title_customization_widget.title_mode_changed.connect(self._on_title_mode_changed)

        # 设置当前的标题模式和内容
        current_title_mode = self.personalization_manager.load_title_mode()
        current_custom_title = self.personalization_manager.load_custom_title()
        self.title_customization_widget.set_title_mode(current_title_mode)
        self.title_customization_widget.set_custom_title(current_custom_title)
        self.title_customization_widget.update_preview_with_isolation_key(self.isolation_key)

        title_layout.addWidget(self.title_customization_widget)

        # 将两个组添加到水平布局
        auto_title_layout.addWidget(auto_submit_settings_group)
        auto_title_layout.addWidget(title_group)

        settings_layout.addLayout(auto_title_layout)
        
        # ==================== 个性化设置区域 ====================
        personalization_group = QGroupBox("个性化设置")
        personalization_layout = QVBoxLayout(personalization_group)

        # 窗口底色选择
        color_group = QGroupBox("窗口底色")
        color_layout = QVBoxLayout(color_group)

        # 创建颜色选择控件
        self.color_selection_widget = ColorSelectionWidget()
        self.color_selection_widget.color_changed.connect(self._on_border_color_changed)

        # 设置当前选中的颜色
        current_color = self.personalization_manager.load_border_color()
        self.color_selection_widget.set_selected_color(current_color)

        color_layout.addWidget(self.color_selection_widget)

        # 颜色重置按钮
        reset_color_button = QPushButton("重置为默认白色")
        reset_color_button.clicked.connect(lambda: self._on_border_color_changed("#ffffff"))
        reset_color_button.setMinimumHeight(30)
        color_layout.addWidget(reset_color_button)

        personalization_layout.addWidget(color_group)

        settings_layout.addWidget(personalization_group)
        
        # 添加弹性空间
        settings_layout.addStretch()
        
        # 添加设置选项卡
        self.tab_widget.addTab(self.settings_group, "设置")

        # 创建工具选项卡
        self.tools_group = QGroupBox()
        tools_layout = QVBoxLayout(self.tools_group)

        # Git AI Commit GUI 工具部分
        git_commit_group = QGroupBox("Git 提交工具")
        git_commit_layout = QVBoxLayout(git_commit_group)

        # 说明文字
        git_commit_info = QLabel("使用 AI 辅助生成 Git 提交信息")
        git_commit_info.setWordWrap(True)
        git_commit_info.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 10px;")
        git_commit_layout.addWidget(git_commit_info)

        # Git AI Commit GUI 按钮
        self.git_commit_button = QPushButton("运行 Git AI Commit GUI")
        self.git_commit_button.clicked.connect(self._run_git_ai_commit_gui)
        self.git_commit_button.setMinimumWidth(200)
        self.git_commit_button.setMinimumHeight(50)
        self.git_commit_button.setAutoFillBackground(True)
        self.git_commit_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        git_commit_layout.addWidget(self.git_commit_button)

        # 添加到工具布局
        tools_layout.addWidget(git_commit_group)
        tools_layout.addStretch()

        # 添加工具选项卡
        self.tab_widget.addTab(self.tools_group, "工具")
        
        # 创建历史记录选项卡（放在最后）
        self._create_history_tab()

        # 从三层隔离设置中加载选项卡索引
        selected_tab_index = self.isolation_settings.load_setting("selectedTabIndex", 0, int)
        self.tab_widget.setCurrentIndex(selected_tab_index)
        
        # 连接选项卡切换信号，保存当前选中的选项卡
        self.tab_widget.currentChanged.connect(self._tab_changed)
        
        # 将选项卡控件添加到主布局
        layout.addWidget(self.tab_widget)

    def _create_history_tab(self):
        """创建历史记录选项卡"""
        self.history_group = QGroupBox()
        history_layout = QVBoxLayout(self.history_group)
        
        # 顶部控制区域（紧凑布局）
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        control_layout.setContentsMargins(5, 5, 5, 5)
        control_layout.setSpacing(5)
        
        # 查看模式和搜索在同一行
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("查看模式:"))
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems([
            "当前隔离模式",
            "项目浏览模式", 
            "环境浏览模式",
            "全局浏览模式"
        ])
        self.view_mode_combo.currentTextChanged.connect(self._on_view_mode_changed)
        top_row.addWidget(self.view_mode_combo)
        
        top_row.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索对话内容...")
        self.search_input.returnPressed.connect(self._search_conversations)
        top_row.addWidget(self.search_input)
        
        search_button = QPushButton("搜索")
        search_button.clicked.connect(self._search_conversations)
        top_row.addWidget(search_button)
        
        control_layout.addLayout(top_row)
        
        # 过滤器行（紧凑布局）
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("AI应用:"))
        self.client_filter = QComboBox()
        self.client_filter.addItem("所有AI应用")
        filter_row.addWidget(self.client_filter)
        
        filter_row.addWidget(QLabel("环境:"))
        self.worker_filter = QComboBox()
        self.worker_filter.addItem("所有环境")
        filter_row.addWidget(self.worker_filter)
        
        filter_row.addWidget(QLabel("项目:"))
        self.project_filter = QComboBox()
        self.project_filter.addItem("所有项目")
        filter_row.addWidget(self.project_filter)
        
        filter_row.addStretch()
        control_layout.addLayout(filter_row)
        
        # 设置控制区域的最大高度
        control_widget.setMaximumHeight(80)
        history_layout.addWidget(control_widget)
        
        # 对话列表（占用大部分空间）
        self.conversation_list = QListWidget()
        self.conversation_list.itemDoubleClicked.connect(self._show_conversation_detail)
        # 设置列表项的样式
        self.conversation_list.setAlternatingRowColors(True)
        self.conversation_list.setSpacing(2)
        # 启用多选
        from PySide6.QtWidgets import QAbstractItemView
        self.conversation_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        history_layout.addWidget(self.conversation_list)
        
        # 底部操作按钮（紧凑布局）
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(5, 5, 5, 5)
        
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self._refresh_conversations)
        export_button = QPushButton("导出")
        export_button.clicked.connect(self._export_conversations)
        delete_button = QPushButton("删除选中")
        delete_button.clicked.connect(self._delete_selected_conversation)
        
        button_layout.addWidget(refresh_button)
        button_layout.addWidget(export_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        
        button_widget.setMaximumHeight(40)
        history_layout.addWidget(button_widget)
        
        # 添加历史记录选项卡
        self.tab_widget.addTab(self.history_group, "历史记录")
        
        # 初始化历史记录数据
        QTimer.singleShot(100, self._load_conversations)
        # 初始化过滤器选项
        QTimer.singleShot(150, self._update_filter_options)
    
    def _on_view_mode_changed(self, mode: str):
        """查看模式变更处理"""
        print(f"View mode changed to: {mode}")
        # 更新过滤器选项
        self._update_filter_options()
        self._load_conversations()

    
    def _update_filter_options(self):
        """根据当前查看模式更新过滤器选项"""
        try:
            mode = self.view_mode_combo.currentText()
            
            # 清空现有选项
            self.client_filter.clear()
            self.worker_filter.clear()
            self.project_filter.clear()
            
            # 根据模式添加相应的过滤选项
            if mode == "当前隔离模式":
                # 当前隔离模式下，过滤器显示当前值但不可选择
                self.client_filter.addItem(f"当前: {self.client_name}")
                self.worker_filter.addItem(f"当前: {self.worker}")
                project_name = os.path.basename(self.project_directory.rstrip(os.sep))
                self.project_filter.addItem(f"当前: {project_name}")
                
                # 禁用过滤器
                self.client_filter.setEnabled(False)
                self.worker_filter.setEnabled(False)
                self.project_filter.setEnabled(False)
                
            elif mode == "项目浏览模式":
                # 项目浏览模式：固定AI应用和环境，可选择项目
                self.client_filter.addItem(f"当前: {self.client_name}")
                self.worker_filter.addItem(f"当前: {self.worker}")
                
                self.project_filter.addItem("所有项目")
                projects = self.history_manager.get_available_projects(self.client_name, self.worker)
                for project in projects:
                    self.project_filter.addItem(project)
                
                self.client_filter.setEnabled(False)
                self.worker_filter.setEnabled(False)
                self.project_filter.setEnabled(True)
                
            elif mode == "环境浏览模式":
                # 环境浏览模式：固定AI应用，可选择环境和项目
                self.client_filter.addItem(f"当前: {self.client_name}")
                
                self.worker_filter.addItem("所有环境")
                workers = self.history_manager.get_available_workers(self.client_name)
                for worker in workers:
                    self.worker_filter.addItem(worker)
                
                self.project_filter.addItem("所有项目")
                projects = self.history_manager.get_available_projects(self.client_name)
                for project in projects:
                    self.project_filter.addItem(project)
                
                self.client_filter.setEnabled(False)
                self.worker_filter.setEnabled(True)
                self.project_filter.setEnabled(True)
                
            elif mode == "全局浏览模式":
                # 全局浏览模式：可选择所有维度
                self.client_filter.addItem("所有AI应用")
                clients = self.history_manager.get_available_clients()
                for client in clients:
                    self.client_filter.addItem(client)
                
                self.worker_filter.addItem("所有环境")
                workers = self.history_manager.get_available_workers()
                for worker in workers:
                    self.worker_filter.addItem(worker)
                
                self.project_filter.addItem("所有项目")
                projects = self.history_manager.get_available_projects()
                for project in projects:
                    self.project_filter.addItem(project)
                
                self.client_filter.setEnabled(True)
                self.worker_filter.setEnabled(True)
                self.project_filter.setEnabled(True)
            
            # 连接过滤器变化信号
            self.client_filter.currentTextChanged.connect(self._on_filter_changed)
            self.worker_filter.currentTextChanged.connect(self._on_filter_changed)
            self.project_filter.currentTextChanged.connect(self._on_filter_changed)
            
        except Exception as e:
            print(f"Failed to update filter options: {e}")
    
    def _on_filter_changed(self):
        """过滤器变化处理"""
        self._load_conversations()
    
    def _search_conversations(self):
        """搜索对话"""
        query = self.search_input.text().strip()
        
        try:
            # 获取过滤器值
            client_filter = self.client_filter.currentText()
            worker_filter = self.worker_filter.currentText()
            project_filter = self.project_filter.currentText()
            
            # 处理过滤器值
            client_name = None if client_filter.startswith("所有") or client_filter.startswith("当前:") else client_filter
            worker = None if worker_filter.startswith("所有") or worker_filter.startswith("当前:") else worker_filter
            project_name = None if project_filter.startswith("所有") or project_filter.startswith("当前:") else project_filter
            
            # 如果是当前隔离模式，使用当前值
            mode = self.view_mode_combo.currentText()
            if mode == "当前隔离模式":
                client_name = self.client_name
                worker = self.worker
                project_name = os.path.basename(self.project_directory.rstrip(os.sep))
            
            conversations = self.history_manager.search_conversations_by_filters(
                query=query,
                client_name=client_name,
                worker=worker,
                project_name=project_name
            )
            self._populate_conversation_list(conversations)
        except Exception as e:
            print(f"Search failed: {e}")
    
    def _load_conversations(self):
        """加载对话列表"""
        try:
            mode = self.view_mode_combo.currentText()
            if mode == "当前隔离模式":
                conversations = self.history_manager.get_current_isolation_history(
                    self.client_name, self.worker, self.project_directory
                )
            elif mode == "项目浏览模式":
                conversations = self.history_manager.get_project_browsing_history(
                    self.client_name, self.worker
                )
            elif mode == "环境浏览模式":
                conversations = self.history_manager.get_environment_browsing_history(
                    self.client_name
                )
            elif mode == "全局浏览模式":
                conversations = self.history_manager.get_global_browsing_history()
            else:
                conversations = []
            
            self._populate_conversation_list(conversations)
        except Exception as e:
            print(f"Failed to load conversations: {e}")
    
    def _populate_conversation_list(self, conversations: List[ConversationRecord]):
        """填充对话列表"""
        self.conversation_list.clear()
        
        for conv in conversations:
            # 创建美观的列表项
            created_time = conv.created_at.strftime("%Y-%m-%d %H:%M:%S") if conv.created_at else "未知时间"
            
            # AI提示预览（显示更多内容）
            ai_prompt_preview = conv.ai_prompt[:150] + "..." if len(conv.ai_prompt) > 150 else conv.ai_prompt
            
            # 用户反馈预览（显示更多内容）
            user_feedback = conv.user_feedback or "无用户反馈"
            feedback_preview = user_feedback[:120] + "..." if len(user_feedback) > 120 else user_feedback
            
            # 创建简洁的显示格式
            line1 = f"{created_time} | {conv.client_name} | {conv.worker} | {conv.project_name}"
            line2 = f"AI助手: {ai_prompt_preview}"
            line3 = f"用户: {feedback_preview}"
            separator = "─" * 80
            item_text = line1 + chr(10) + line2 + chr(10) + line3 + chr(10) + separator
            
            from PySide6.QtWidgets import QListWidgetItem
            from PySide6.QtCore import QSize
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, conv)  # 存储完整的对话记录
            
            # 设置项目高度以容纳多行文本和分隔线
            item.setSizeHint(QSize(0, 100))
            
            self.conversation_list.addItem(item)
    def _show_conversation_detail(self, item):
        """显示对话详情"""
        conv = item.data(Qt.UserRole)
        if conv:
            self._show_conversation_detail_dialog(conv)
    
    def _show_conversation_detail_dialog(self, conv: ConversationRecord):
        """显示对话详情对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"对话详情 - {conv.session_id[:8]}")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 基本信息
        info_text = f"""
时间: {conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else '未知'}
AI应用: {conv.client_name}
环境: {conv.worker}
项目: {conv.project_name}
项目路径: {conv.project_directory}
        """.strip()
        
        info_label = QLabel(info_text)
        layout.addWidget(info_label)
        
        # AI提示
        layout.addWidget(QLabel("AI提示:"))
        ai_prompt_text = QTextEdit()
        ai_prompt_text.setPlainText(conv.ai_prompt)
        ai_prompt_text.setReadOnly(True)
        ai_prompt_text.setMaximumHeight(100)
        layout.addWidget(ai_prompt_text)
        
        # 用户反馈
        layout.addWidget(QLabel("用户反馈:"))
        feedback_text = QTextEdit()
        feedback_text.setPlainText(conv.user_feedback or "无用户反馈")
        feedback_text.setReadOnly(True)
        feedback_text.setMaximumHeight(100)
        layout.addWidget(feedback_text)
        
        # 命令日志
        if conv.command_logs:
            layout.addWidget(QLabel("命令日志:"))
            logs_text = QTextEdit()
            logs_text.setPlainText(conv.command_logs)
            logs_text.setReadOnly(True)
            logs_text.setMaximumHeight(150)
            layout.addWidget(logs_text)
        
        # 关闭按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec()
    
    def _refresh_conversations(self):
        """刷新对话列表"""
        self._load_conversations()
    
    def _export_conversations(self):
        """导出对话"""
        try:
            # 获取当前显示的对话列表
            conversations = []
            for i in range(self.conversation_list.count()):
                item = self.conversation_list.item(i)
                conv = item.data(Qt.UserRole)
                if conv:
                    conversations.append(conv)
            
            if not conversations:
                QMessageBox.information(self, "导出", "没有可导出的对话记录")
                return
            
            # 让用户选择导出格式和位置
            from PySide6.QtWidgets import QFileDialog
            file_path, selected_filter = QFileDialog.getSaveFileName(
                self,
                "导出对话记录",
                f"conversations_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "JSON文件 (*.json);;CSV文件 (*.csv);;Markdown文件 (*.md)"
            )
            
            if file_path:
                # 根据选择的格式导出
                if selected_filter.startswith("JSON"):
                    if not file_path.endswith('.json'):
                        file_path += '.json'
                    self.history_manager.export_conversations_to_json(conversations, file_path)
                elif selected_filter.startswith("CSV"):
                    if not file_path.endswith('.csv'):
                        file_path += '.csv'
                    self.history_manager.export_conversations_to_csv(conversations, file_path)
                elif selected_filter.startswith("Markdown"):
                    if not file_path.endswith('.md'):
                        file_path += '.md'
                    self.history_manager.export_conversations_to_markdown(conversations, file_path)
                
                QMessageBox.information(self, "导出成功", f"已导出 {len(conversations)} 条对话记录到: {file_path}")
                
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出对话记录时出错: {e}")
    
    def _delete_selected_conversation(self):
        """删除选中的对话"""
        selected_items = self.conversation_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "删除", "请先选择要删除的对话记录")
            return
        
        # 支持多选删除
        conversations_to_delete = []
        for item in selected_items:
            conv = item.data(Qt.UserRole)
            if conv:
                conversations_to_delete.append(conv)
        
        if not conversations_to_delete:
            return
        
        # 确认删除
        if len(conversations_to_delete) == 1:
            conv = conversations_to_delete[0]
            message = f"确定要删除这条对话记录吗？时间: {conv.created_at.strftime('%Y-%m-%d %H:%M:%S') if conv.created_at else '未知'}"
        else:
            message = f"确定要删除选中的 {len(conversations_to_delete)} 条对话记录吗？"
        
        reply = QMessageBox.question(
            self, "确认删除", message,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                deleted_count = 0
                for conv in conversations_to_delete:
                    success = self.history_manager.db.delete_conversation(conv.session_id, conv.isolation_key)
                    if success:
                        deleted_count += 1
                
                self._load_conversations()
                QMessageBox.information(self, "删除成功", f"已删除 {deleted_count} 条对话记录")
                
            except Exception as e:
                QMessageBox.critical(self, "删除失败", f"删除对话记录时出错: {e}")

    def _cycle_window_size(self):
        """循环调整窗口大小：默认 -> x2 -> x3 -> 默认"""
        # 获取当前倍数索引
        current_index = self.size_states.index(self.size_multiplier)
        # 计算下一个倍数索引（循环）
        next_index = (current_index + 1) % len(self.size_states)
        # 设置新的倍数
        self.size_multiplier = self.size_states[next_index]
        
        # 获取当前窗口实际大小
        current_width = self.width()
        current_height = self.height()
        
        # 使用当前窗口大小作为基准，而不是默认大小
        new_width = int(current_width * self.size_multiplier / self.size_states[current_index])
        new_height = int(current_height * self.size_multiplier / self.size_states[current_index])
        
        # 调整窗口大小
        self.resize(new_width, new_height)
        
        # 如果使用自定义位置，保持当前位置
        if hasattr(self, 'use_custom_position') and self.use_custom_position and self.custom_position:
            # 不移动窗口，保持当前位置
            pass
        else:
            # 重新计算窗口位置，保持在屏幕右下角
            screen_geometry = QApplication.primaryScreen().availableGeometry()
            x = screen_geometry.width() - new_width - 20  # 右边距20像素
            y = screen_geometry.height() - new_height - 40  # 下边距40像素
            self.move(x, y)
        
        # 更新按钮文本和大小信息标签
        if self.size_multiplier == 1:
            self.resize_button.setText("调整窗口大小")
        else:
            self.resize_button.setText(f"窗口大小 x{self.size_multiplier}")
            
        # 更新大小信息标签
        if hasattr(self, 'size_info_label'):
            self.size_info_label.setText(f"当前窗口大小: {new_width} x {new_height}")
            
    def _tab_changed(self, index):
        """处理选项卡切换事件"""
        # 保存当前选中的选项卡索引到三层隔离设置
        self.isolation_settings.save_setting("selectedTabIndex", index)
        
    def _update_config(self):
        self.config["run_command"] = self.command_entry.text()
        self.config["execute_automatically"] = self.auto_check.isChecked()

    def _append_log(self, text: str):
        self.log_buffer.append(text)
        self.log_text.append(text.rstrip())
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)



    def _run_command(self):
        if self.process:
            kill_tree(self.process)
            self.process = None
            self.run_button.setText("运行(&R)")
            return

        # Clear the log buffer but keep UI logs visible
        self.log_buffer = []

        command = self.command_entry.text()
        if not command:
            return

        self._append_log(f"$ {command}\n")
        self.run_button.setText("停止(&p)")

        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(
                target=read_output,
                args=(self.process.stdout,),
                daemon=True
            ).start()

            threading.Thread(
                target=read_output,
                args=(self.process.stderr,),
                daemon=True
            ).start()

            # 使用新的进程监控器替代原来的status_timer
            self.process_monitor.add_process(
                self.process, 
                self._on_command_finished,
                'main_command'
            )

        except Exception as e:
            self._append_log(f"运行命令时出错: {str(e)}\n")
            self.run_button.setText("运行(&R)")
    
    def _on_command_finished(self, return_code):
        """命令执行完成的回调"""
        self.process = None
        self.run_button.setText("运行(&R)")
        self.process_monitor.remove_process('main_command')

    def _submit_feedback(self):
        # 获取反馈内容
        user_feedback = self.feedback_text.toPlainText().strip()
        
        # 检查是否需要自动附加内容
        if self.auto_append_enabled and self.auto_append_content:
            # 如果启用了自动附加且有自定义内容，则在末尾附加
            if user_feedback:
                user_feedback += "\n" + self.auto_append_content
            else:
                user_feedback = self.auto_append_content
            # 更新文本框显示最终内容
            self.feedback_text.setText(user_feedback)
        
        command_logs = "".join(self.log_buffer)
        
        # 准备图片数据
        images = []
        for image_path in self.uploaded_images:
            try:
                with open(image_path, 'rb') as f:
                    image_data = f.read()
                image_name = os.path.basename(image_path)
                images.append((image_path, image_name, image_data))
            except Exception as e:
                print(f"Failed to read image {image_path}: {e}")
        
        # 保存历史记录
        try:
            session_id = self.history_manager.save_feedback_session(
                client_name=self.client_name,
                worker=self.worker,
                project_directory=self.project_directory,
                ai_prompt=self.prompt,
                user_feedback=user_feedback,
                command_logs=command_logs,
                images=images
            )
            print(f"Conversation saved with session ID: {session_id}")
        except Exception as e:
            print(f"Failed to save conversation history: {e}")
        
        # 设置反馈结果
        self.feedback_result = {
            "command_logs": command_logs,
            "interactive_feedback": user_feedback,
            "uploaded_images": self.uploaded_images
        }
        
        self.close()
        
    def _insert_quick_reply(self, text: str):
        """将预设文本插入到反馈文本框中"""
        self.feedback_text.setText(text)
        self.feedback_text.setFocus()
        # 如果是 开始实施 的话，直接发送反馈
        if text == "开始实施":
            self._submit_feedback()
        
    def _apply_selected_quick_reply(self):
        """应用当前在组合框中选择的快捷回复"""
        selected_text = self.quick_reply_combo.currentText()
        if selected_text:
            self._insert_quick_reply(selected_text)
            
    def _edit_quick_replies(self):
        """打开编辑快捷回复对话框"""
        dialog = QuickReplyEditDialog(self, self.quick_replies)
        if dialog.exec():
            # 用户点击了确定，保存编辑后的快捷回复
            self.quick_replies = dialog.get_quick_replies()
            
            # 更新组合框内容
            self.quick_reply_combo.clear()
            for reply in self.quick_replies:
                self.quick_reply_combo.addItem(reply)
                
            # 保存到三层隔离设置
            self.isolation_settings.save_setting("quick_replies", self.quick_replies)
           
    def _upload_image(self):
        """上传图片"""
        try:
            # 打开文件选择对话框，限制为图片文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图片",
                "",
                "图片文件 (*.png *.jpg *.jpeg *.gif *.bmp)"
            )
            if file_path:
                # 检查文件是否存在
                if not os.path.exists(file_path):
                    QMessageBox.warning(self, "错误", "选择的文件不存在")
                    return
                
                # 复制图片到temp目录
                extension = os.path.splitext(file_path)[1][1:].lower()
                if not extension:
                    extension = "png"  # 默认扩展名
                new_filename = generate_random_filename(extension)
                new_filepath = os.path.join(self.temp_dir, new_filename)
                
                # 读取原图片并保存到新位置
                pixmap = QPixmap(file_path)
                if pixmap.isNull():
                    QMessageBox.warning(self, "错误", "无法加载选择的图片文件")
                    return
                
                if pixmap.save(new_filepath):
                    # 添加到上传列表
                    self.uploaded_images.append(new_filepath)
                    
                    # 更新预览
                    self._update_image_preview()
                else:
                    QMessageBox.warning(self, "错误", "保存图片到临时目录失败")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"上传图片时发生错误: {str(e)}")
            print(f"Upload image error: {e}")
            import traceback
            traceback.print_exc()
    
    def _get_clipboard_image(self, show_message=True):
        """从剪贴板获取图片
        
        Args:
            show_message: 是否显示消息框提示
            
        Returns:
            bool: 是否成功获取并处理了图片
        """
        try:
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            
            if mime_data.hasImage():
                # 从剪贴板获取图片
                image = QImage(clipboard.image())
                if not image.isNull():
                    # 保存图片到临时目录
                    filename = generate_random_filename()
                    filepath = os.path.join(self.temp_dir, filename)
                    
                    # 保存图片
                    if image.save(filepath):
                        self.uploaded_images.append(filepath)
                        self._update_image_preview()
                        if show_message:
                            QMessageBox.information(self, "成功", "已从剪贴板获取图片")
                        return True
                    else:
                        if show_message:
                            QMessageBox.warning(self, "错误", "保存图片失败")
                        return False
                else:
                    if show_message:
                        QMessageBox.warning(self, "错误", "剪贴板中的图片无效")
                    return False
            else:
                if show_message:
                    QMessageBox.warning(self, "错误", "剪贴板中没有图片")
                return False
        except Exception as e:
            if show_message:
                QMessageBox.critical(self, "错误", f"从剪贴板获取图片时发生错误: {str(e)}")
            print(f"Clipboard image error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _update_image_preview(self):
        """更新图片预览区域"""
        try:
            # 设置预览区域的可见性：有图片才显示
            has_images = bool(self.uploaded_images)
            self.preview_group.setVisible(has_images)
            
            # 清除现有预览
            for widget in self.image_previews:
                widget.deleteLater()
            self.image_previews = []
            self.image_labels = []
            
            # 如果没有图片，显示提示
            if not self.uploaded_images:
                label = QLabel("暂无图片")
                label.setAlignment(Qt.AlignCenter)
                self.preview_grid.addWidget(label, 0, 0)
                self.image_previews.append(label)
                return
            
            # 添加新的预览
            row, col = 0, 0
            max_cols = 3  # 每行最多显示3张图片
            
            for idx, image_path in enumerate(self.uploaded_images):
                # 检查图片文件是否存在
                if not os.path.exists(image_path):
                    print(f"Warning: Image file not found: {image_path}")
                    continue
                
                # 创建图片容器
                frame = QFrame()
                frame.setFrameShape(QFrame.StyledPanel)
                frame.setFixedSize(100, 130)  # 固定大小
                frame_layout = QVBoxLayout(frame)
                frame_layout.setContentsMargins(5, 5, 5, 5)
                
                # 创建图片标签
                image_label = QLabel()
                image_label.setAlignment(Qt.AlignCenter)
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    image_label.setPixmap(pixmap)
                    image_label.setToolTip(image_path)
                    
                    # 设置点击事件
                    image_label.mousePressEvent = lambda event, path=image_path: self._preview_image(path)
                else:
                    image_label.setText("加载失败")
                
                frame_layout.addWidget(image_label)
                self.image_labels.append(image_label)
                
                # 添加删除按钮
                delete_button = QPushButton("删除")
                delete_button.setProperty("image_index", idx)
                delete_button.clicked.connect(lambda checked, idx=idx: self._delete_image(idx))
                delete_button.setAutoFillBackground(True)  # 设置自动填充背景
                frame_layout.addWidget(delete_button)
                
                # 添加到网格布局
                self.preview_grid.addWidget(frame, row, col)
                self.image_previews.append(frame)
                
                # 更新行列位置
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            
            # 确保预览组在有图片时可见
            if self.uploaded_images:
                self.preview_group.setVisible(True)
                self.preview_group.show()
                
        except Exception as e:
            print(f"Error updating image preview: {e}")
            import traceback
            traceback.print_exc()

    
    def _debug_image_functionality(self):
        """调试图片功能状态"""
        print("=== Image Functionality Debug Info ===")
        print(f"Temp directory: {self.temp_dir}")
        print(f"Temp directory exists: {os.path.exists(self.temp_dir)}")
        print(f"Uploaded images count: {len(self.uploaded_images)}")
        print(f"Uploaded images: {self.uploaded_images}")
        print(f"Preview group visible: {self.preview_group.isVisible()}")
        print(f"Preview group parent visible: {self.preview_group.parent().isVisible() if self.preview_group.parent() else 'No parent'}")
        print(f"Image previews count: {len(self.image_previews)}")
        print(f"Image labels count: {len(self.image_labels)}")
        
        # 检查按钮状态
        upload_buttons = self.findChildren(QPushButton)
        for button in upload_buttons:
            if button.text() == "上传图片":
                print(f"Upload button visible: {button.isVisible()}, enabled: {button.isEnabled()}")
            elif button.text() == "从剪贴板获取图片":
                print(f"Clipboard button visible: {button.isVisible()}, enabled: {button.isEnabled()}")
        
        print("=== End Debug Info ===")
    
    def _preview_image(self, image_path):
        """在对话框中预览大图"""
        dialog = QDialog(self)
        dialog.setWindowTitle("图片预览")
        dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(dialog)
        
        # 创建图片标签
        label = QLabel()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # 缩放图片以适应对话框
            pixmap = pixmap.scaled(480, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
        else:
            label.setText("无法加载图片")
        
        layout.addWidget(label)
        
        # 添加关闭按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec()
    
    def _delete_image(self, index):
        """删除指定索引的图片"""
        if 0 <= index < len(self.uploaded_images):
            image_path = self.uploaded_images[index]
            
            # 从列表中移除
            self.uploaded_images.pop(index)
            
            # 尝试从磁盘删除
            try:
                os.remove(image_path)
            except Exception as e:
                print(f"删除文件失败: {e}")
            
            # 更新预览
            self._update_image_preview()
            
    def clear_logs(self):
        self.log_buffer = []
        self.log_text.clear()
        
    def _save_config(self):
        # Save run_command and execute_automatically to QSettings under three-layer isolation
        self.isolation_settings.save_multiple_settings({
            "run_command": self.config["run_command"],
            "execute_automatically": self.config["execute_automatically"]
        })
        
    def _save_window_position(self):
        """保存当前窗口位置到用户设置"""
        # 保存窗口位置到三层隔离设置组
        pos = self.pos()
        self.isolation_settings.save_multiple_settings({
            "custom_position_x": pos.x(),
            "custom_position_y": pos.y(),
            "use_custom_position": True
        })
        
        # 更新内部状态
        self.use_custom_position = True
        self.custom_position = pos
        
        # 显示状态消息
        self._show_status_message(f"已保存窗口位置 ({pos.x()}, {pos.y()})")

    def closeEvent(self, event):
        # Save global UI settings (only Qt system-level settings)
        self.settings.beginGroup("MainWindow_General")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.endGroup()
        # 强制同步到磁盘，确保数据持久化
        self.settings.sync()
        
        # Save three-layer isolation settings
        close_settings = {
            "custom_width": self.width(),
            "custom_height": self.height(),
            "selectedTabIndex": self.tab_widget.currentIndex(),
            "run_command": self.config["run_command"],
            "execute_automatically": self.config["execute_automatically"],
            "auto_submit_enabled": self.auto_submit_enabled,
            "auto_submit_wait_time": self.auto_submit_wait_time,
            "auto_fill_first_reply": self.auto_fill_first_reply
        }
        
        # 根据设置决定是否自动保存窗口位置
        auto_save_position = self.isolation_settings.load_setting("auto_save_position", True, bool)
        if auto_save_position:
            # 自动保存窗口位置
            pos = self.pos()
            close_settings.update({
                "custom_position_x": pos.x(),
                "custom_position_y": pos.y(),
                "use_custom_position": True
            })

        # 保存窗口置顶设置
        if hasattr(self, 'stay_on_top_check'):
            close_settings["stay_on_top_enabled"] = self.stay_on_top_check.isChecked()
        
        # 批量保存所有设置
        self.isolation_settings.save_multiple_settings(close_settings)

        if self.process:
            kill_tree(self.process)
            
        # 清理未使用的临时图片
        self._cleanup_temp_images()
        
        # 清理所有定时器
        self.timer_manager.cleanup()
            
        super().closeEvent(event)

    def _cleanup_temp_images(self):
        """清理临时目录中未使用的图片文件"""
        if not os.path.exists(self.temp_dir):
            return
            
        # 获取当前已上传图片的文件名集合
        uploaded_filenames = set(os.path.basename(path) for path in self.uploaded_images)
        
        # 遍历临时目录中的所有文件
        for filename in os.listdir(self.temp_dir):
            filepath = os.path.join(self.temp_dir, filename)
            # 如果是文件且不在已上传列表中，则删除
            if os.path.isfile(filepath) and filename not in uploaded_filenames:
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"清理临时文件失败: {e}")

    def _update_auto_save_position(self, state):
        """更新自动保存窗口位置的设置"""
        is_checked = (state == Qt.Checked)
        self.isolation_settings.save_setting("auto_save_position", is_checked)

        # 显示状态更改提示
        status_message = "已启用自动保存窗口位置" if is_checked else "已禁用自动保存窗口位置"
        self._show_status_message(status_message)

    def _update_auto_submit_settings(self):
        """更新自动提交设置"""
        # 更新启用状态
        self.auto_submit_enabled = self.auto_submit_check.isChecked()

        # 更新自动填入第一条预设回复的设置
        if hasattr(self, 'auto_fill_first_reply_check'):
            self.auto_fill_first_reply = self.auto_fill_first_reply_check.isChecked()

        # 更新等待时间
        try:
            wait_time = int(self.auto_submit_time_input.text())
            if wait_time > 0:
                self.auto_submit_wait_time = wait_time
            else:
                # 如果输入无效，恢复默认值
                self.auto_submit_wait_time = 60
                self.auto_submit_time_input.setText("60")
        except ValueError:
            # 如果输入无效，恢复默认值
            self.auto_submit_wait_time = 60
            self.auto_submit_time_input.setText("60")

        # 保存设置到三层隔离
        self.isolation_settings.save_multiple_settings({
            "auto_submit_enabled": self.auto_submit_enabled,
            "auto_submit_wait_time": self.auto_submit_wait_time,
            "auto_fill_first_reply": self.auto_fill_first_reply
        })

    def _update_auto_append_settings(self):
        """更新末尾自动附加内容设置"""
        self.auto_append_enabled = self.auto_append_check.isChecked()
        self.auto_append_content = self.auto_append_input.text()
        
        # 保存到三层隔离设置
        self.isolation_settings.save_multiple_settings({
            "auto_append_enabled": self.auto_append_enabled,
            "auto_append_content": self.auto_append_content
        })

    def _start_auto_submit_countdown(self):
        """启动自动提交倒计时"""
        if not self.auto_submit_enabled:
            return

        # 使用新的自动提交定时器
        self.auto_submit_timer.start_countdown(
            self.auto_submit_wait_time,
            self._auto_submit_timeout,
            self._update_submit_button_text
        )

    def _stop_auto_submit_countdown(self):
        """停止自动提交倒计时"""
        self.auto_submit_timer.stop_countdown()
        # 恢复原始按钮文本
        if hasattr(self, 'submit_button') and self.original_submit_text:
            self.submit_button.setText(self.original_submit_text)

    def _cancel_auto_submit(self):
        """统一的取消自动提交方法"""
        self._stop_auto_submit_countdown()

    def _setup_auto_submit_cancellation(self):
        """设置自动提交取消的统一监听"""
        # 延迟设置，确保UI完全初始化后再设置监听
        QTimer.singleShot(100, self._setup_auto_submit_cancellation_delayed)

    def _setup_auto_submit_cancellation_delayed(self):
        """延迟设置自动提交取消监听"""
        try:
            # 安装事件过滤器到主窗口
            self.installEventFilter(self)

            # 文本框多信号监听（如果文本框已创建）
            if hasattr(self, 'feedback_text') and self.feedback_text:
                text_edit = self.feedback_text
                text_edit.cursorPositionChanged.connect(self._cancel_auto_submit)
                text_edit.selectionChanged.connect(self._cancel_auto_submit)

            # 所有按钮点击
            for button in self.findChildren(QPushButton):
                if button and not button.signalsBlocked():
                    button.clicked.connect(self._cancel_auto_submit)

            # 所有下拉框变化
            for combo in self.findChildren(QComboBox):
                if combo and not combo.signalsBlocked():
                    combo.currentTextChanged.connect(self._cancel_auto_submit)

            # 所有输入框变化
            for line_edit in self.findChildren(QLineEdit):
                if line_edit and not line_edit.signalsBlocked():
                    line_edit.textChanged.connect(self._cancel_auto_submit)

        except Exception as e:
            # 静默处理错误，避免影响UI初始化
            print(f"Warning: Failed to setup auto-submit cancellation: {e}")

    def eventFilter(self, obj, event):
        """统一事件过滤器 - 捕获用户交互事件"""
        try:
            if event.type() in [
                QEvent.MouseButtonPress,    # 鼠标点击
                QEvent.KeyPress,           # 键盘按键
                QEvent.InputMethod,        # 输入法事件
                QEvent.FocusIn            # 获得焦点
            ]:
                self._cancel_auto_submit()
        except Exception as e:
            # 静默处理错误，避免影响事件处理
            pass
        return super().eventFilter(obj, event)

    def _update_submit_button_text(self, remaining_time):
        """更新提交按钮文本"""
        if remaining_time is None:
            # 恢复原始文本
            if hasattr(self, 'submit_button') and self.original_submit_text:
                self.submit_button.setText(self.original_submit_text)
        else:
            # 显示倒计时
            countdown_text = f"{self.original_submit_text} ({remaining_time}秒)"
            self.submit_button.setText(countdown_text)



    def _auto_submit_timeout(self):
        """自动提交超时处理"""
        # 停止倒计时
        self._stop_auto_submit_countdown()

        # 检查反馈文本框是否为空，并且启用了自动填入功能
        current_feedback = self.feedback_text.toPlainText().strip()
        if not current_feedback and self.auto_fill_first_reply:
            # 如果反馈为空且启用了自动填入，使用预设信息的第一条
            if self.quick_replies and len(self.quick_replies) > 0:
                first_quick_reply = self.quick_replies[0]
                self.feedback_text.setText(first_quick_reply)
                # 显示一个简短的提示信息
                self._show_status_message(f"自动填入预设回复: {first_quick_reply}")

        # 执行提交
        self._submit_feedback()

    def _update_stay_on_top_setting(self, state):
        """更新窗口置顶设置"""
        is_checked = (state == Qt.Checked)
        self.isolation_settings.save_setting("stay_on_top_enabled", is_checked)

        # 显示状态更改提示
        status_message = "已启用启动时窗口置顶" if is_checked else "已禁用启动时窗口置顶"
        self._show_status_message(status_message)

    def _toggle_stay_on_top(self):
        """切换窗口置顶状态"""
        current_flags = self.windowFlags()
        if current_flags & Qt.WindowStaysOnTopHint:
            # 当前是置顶状态，取消置顶
            new_flags = current_flags & ~Qt.WindowStaysOnTopHint
            self.setWindowFlags(new_flags)
            self._show_status_message("已取消窗口置顶")
        else:
            # 当前不是置顶状态，设置置顶
            new_flags = current_flags | Qt.WindowStaysOnTopHint
            self.setWindowFlags(new_flags)
            self._show_status_message("已设置窗口置顶")

        # 重新显示窗口（setWindowFlags会隐藏窗口）
        self.show()
    
    def _reset_window_position(self):
        """重置窗口位置到屏幕右下角"""
        self.use_custom_position = False
        self.custom_position = None
        
        # 更新设置
        self.isolation_settings.save_setting("use_custom_position", False)
        self.isolation_settings.remove_setting("custom_position_x")
        self.isolation_settings.remove_setting("custom_position_y")
        
        # 重新定位窗口
        self._position_window_bottom_right()
        
        # 显示状态消息
        self._show_status_message("已重置窗口位置到屏幕右下角")
        
    def _show_status_message(self, message):
        """显示状态消息"""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtCore import QTimer
        
        status_label = QLabel(message, self)
        status_label.adjustSize()
        
        # 放置在窗口底部中央
        label_x = (self.width() - status_label.width()) // 2
        label_y = self.height() - status_label.height() - 10
        status_label.move(label_x, label_y)
        status_label.show()
        
        # 3秒后自动隐藏
        QTimer.singleShot(3000, status_label.deleteLater)

    def _update_size_info(self):
        """更新大小信息标签"""
        self.size_info_label.setText(f"当前窗口大小: {self.width()} x {self.height()}")

    def _run_git_ai_commit_gui(self):
        """运行 Git AI Commit GUI 工具"""
        # 检查是否已有进程在运行
        if self.process:
            QMessageBox.warning(self, "警告", "已有命令在运行中，请先停止当前命令")
            return

        # 切换到终端选项卡以显示输出
        self.tab_widget.setCurrentIndex(1)  # 终端选项卡是索引1

        # 清空日志缓冲区
        self.log_buffer = []

        command = "uvx git-ai-commit-gui"
        self._append_log(f"$ {command}\n")
        self.git_commit_button.setText("正在运行...")
        self.git_commit_button.setEnabled(False)

        try:
            self.process = subprocess.Popen(
                command,
                shell=True,
                cwd=self.project_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=get_user_environment(),
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="ignore",
                close_fds=True,
            )

            def read_output(pipe):
                for line in iter(pipe.readline, ""):
                    self.log_signals.append_log.emit(line)

            threading.Thread(
                target=read_output,
                args=(self.process.stdout,),
                daemon=True
            ).start()

            threading.Thread(
                target=read_output,
                args=(self.process.stderr,),
                daemon=True
            ).start()

            # 使用新的进程监控器替代原来的git_status_timer
            self.process_monitor.add_process(
                self.process,
                self._on_git_command_finished, 
                'git_command'
            )

        except Exception as e:
            self._append_log(f"运行 Git AI Commit GUI 时出错: {str(e)}\n")
            self.git_commit_button.setText("运行 Git AI Commit GUI")
            self.git_commit_button.setEnabled(True)
    
    def _on_git_command_finished(self, return_code):
        """Git命令执行完成的回调"""
        self.process = None
        self.git_commit_button.setText("运行 Git AI Commit GUI")
        self.git_commit_button.setEnabled(True)
        self.process_monitor.remove_process('git_command')



    def _on_border_color_changed(self, color: str):
        """处理边框颜色变化"""
        # 保存颜色设置
        self.personalization_manager.save_border_color(color)
        # 应用颜色到当前窗口
        self.personalization_manager.apply_border_color(color, self)
        # 更新颜色选择控件的状态
        self.color_selection_widget.set_selected_color(color)

    def _on_custom_title_changed(self, title: str):
        """处理自定义标题变化"""
        # 保存标题设置
        self.personalization_manager.save_custom_title(title)
        # 应用标题到当前窗口
        title_mode = self.personalization_manager.load_title_mode()
        self.personalization_manager.apply_window_title(title_mode, title, self, self.isolation_key)

    def _on_title_mode_changed(self, mode: str):
        """处理标题模式变化"""
        # 保存模式设置
        self.personalization_manager.save_title_mode(mode)
        # 应用标题到当前窗口
        custom_title = self.personalization_manager.load_custom_title()
        self.personalization_manager.apply_window_title(mode, custom_title, self, self.isolation_key)

    def _reset_title_settings(self):
        """重置标题设置为默认值"""
        # 重置为动态模式和空自定义标题
        self.personalization_manager.save_title_mode("dynamic")
        self.personalization_manager.save_custom_title("")
        
        # 更新UI控件
        self.title_customization_widget.set_title_mode("dynamic")
        self.title_customization_widget.set_custom_title("")
        
        # 应用到窗口
        self.personalization_manager.apply_window_title("dynamic", "", self, self.isolation_key)

    def resizeEvent(self, event):
        """重写resize事件，在窗口大小变化时更新大小信息标签"""
        super().resizeEvent(event)
        # 使用防抖辅助器替代原来的resize_event_timer
        self.debounce_helper.debounce('resize', self._update_size_info)  # 200毫秒后更新

    def moveEvent(self, event):
        """重写move事件，在窗口位置变化时自动保存位置（如果启用了自动保存）"""
        super().moveEvent(event)
        
        # 检查是否启用了自动保存位置功能
        if hasattr(self, 'isolation_settings'):
            auto_save_position = self.isolation_settings.load_setting("auto_save_position", True, bool)
            
            if auto_save_position:
                # 使用防抖辅助器替代原来的move_event_timer
                self.debounce_helper.debounce('move', self._save_position_from_move)  # 500毫秒后保存位置
    
    def _save_position_from_move(self):
        """从移动事件中保存窗口位置"""
        try:
            pos = self.pos()
            self.isolation_settings.save_multiple_settings({
                "custom_position_x": pos.x(),
                "custom_position_y": pos.y(),
                "use_custom_position": True
            })
            
            # 更新内部状态
            self.use_custom_position = True
            self.custom_position = pos
            
        except Exception as e:
            # 静默处理错误，避免影响用户体验
            pass

    def run(self) -> FeedbackResult:
        self.show()

        # 如果启用自动提交，则启动倒计时
        if self.auto_submit_enabled:
            # 使用QTimer延迟启动，确保窗口完全显示后再开始倒计时
            QTimer.singleShot(500, self._start_auto_submit_countdown)

        QApplication.instance().exec()

        if self.process:
            kill_tree(self.process)

        if not self.feedback_result:
            return FeedbackResult(
                command_logs="".join(self.log_buffer),
                interactive_feedback="",
                uploaded_images=[]
            )

        # 将字典转换为FeedbackResult对象
        if isinstance(self.feedback_result, dict):
            return FeedbackResult(
                command_logs=self.feedback_result.get("command_logs", ""),
                interactive_feedback=self.feedback_result.get("interactive_feedback", ""),
                uploaded_images=self.feedback_result.get("uploaded_images", [])
            )

        return self.feedback_result



def feedback_ui(project_directory: str, prompt: str, output_file: Optional[str] = None, worker: str = "default", client_name: str = "unknown-client", detail_level: str = None) -> Optional[FeedbackResult]:
    # If detail_level is not provided, get it from environment variable
    if detail_level is None:
        detail_level = get_default_detail_level()
    
    app = QApplication.instance() or QApplication()
    
    # 在提示文本中添加AI助手信息
    ai_prompt = f"AI助手: {prompt}"
    
    ui = FeedbackUI(project_directory, ai_prompt, worker=worker, client_name=client_name, detail_level=detail_level)
    result = ui.run()

    if output_file and result:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        # Save the result to the output file
        with open(output_file, "w") as f:
            json.dump(result, f)
        return None

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行反馈用户界面")
    parser.add_argument("--project-directory", default=os.getcwd(), help="The project directory to run the command in")
    parser.add_argument("--prompt", default="I implemented the changes you requested.", help="The prompt to show to the user")
    parser.add_argument("--output-file", help="Path to save the feedback result as JSON")
    parser.add_argument("--worker", default="default", help="Worker environment identifier (max 40 chars)")
    parser.add_argument("--client-name", default="unknown-client", help="MCP client name for isolation")
    parser.add_argument("--detail-level", default=get_default_detail_level(), choices=["brief", "detailed", "comprehensive"], help="Level of detail for the summary")
    args = parser.parse_args()

    result = feedback_ui(args.project_directory, args.prompt, args.output_file, args.worker, args.client_name, args.detail_level)
    if result:
        feedback_result = {
            "command_logs": result['command_logs'],
            "interactive_feedback": result['interactive_feedback'],
            "uploaded_images": result['uploaded_images']
        }
        print(json.dumps(feedback_result, indent=4))
    sys.exit(0)
