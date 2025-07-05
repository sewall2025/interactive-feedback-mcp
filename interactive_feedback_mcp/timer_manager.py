"""
定时器管理系统

为解决 feedback_ui.py 中定时器滥用问题而设计的统一定时器管理系统。
该系统提供集中化的定时器管理、进程监控和防抖功能。
"""

import time
import subprocess
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
from PySide6.QtCore import QTimer


@dataclass
class ProcessInfo:
    """进程信息数据类"""
    process: subprocess.Popen
    callback: Callable
    name: str
    start_time: float
    timeout: Optional[int] = None


class TimerManager:
    """统一的定时器管理器
    
    负责创建、管理和清理所有QTimer实例
    """
    
    def __init__(self):
        self.timers: Dict[str, QTimer] = {}
        self._cleanup_callbacks: List[Callable] = []
    
    def create_timer(self, name: str, interval: int, callback: Callable) -> QTimer:
        """创建或更新定时器
        
        Args:
            name: 定时器唯一标识
            interval: 触发间隔(毫秒)
            callback: 回调函数
            
        Returns:
            QTimer实例
        """
        if name in self.timers:
            self.timers[name].stop()
        
        timer = QTimer()
        timer.timeout.connect(callback)
        timer.start(interval)
        self.timers[name] = timer
        return timer
    
    def create_single_shot(self, name: str, delay: int, callback: Callable):
        """创建单次执行定时器"""
        # 如果已存在同名定时器，先停止它
        if name in self.timers:
            self.timers[name].stop()
        
        def execute_once():
            callback()
            self.remove_timer(name)
        
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(execute_once)
        timer.start(delay)
        self.timers[name] = timer
    
    def stop_timer(self, name: str) -> bool:
        """停止指定定时器"""
        if name in self.timers:
            self.timers[name].stop()
            return True
        return False
    
    def remove_timer(self, name: str) -> bool:
        """移除定时器"""
        if name in self.timers:
            self.timers[name].stop()
            del self.timers[name]
            return True
        return False
    
    def is_active(self, name: str) -> bool:
        """检查定时器是否活跃"""
        return name in self.timers and self.timers[name].isActive()
    
    def get_active_timers(self) -> List[str]:
        """获取所有活跃定时器名称"""
        return [name for name, timer in self.timers.items() if timer.isActive()]
    
    def add_cleanup_callback(self, callback: Callable):
        """添加清理回调"""
        self._cleanup_callbacks.append(callback)
    
    def cleanup(self):
        """清理所有定时器和资源"""
        # 执行清理回调
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Cleanup callback error: {e}")
        
        # 停止并清理所有定时器
        for timer in self.timers.values():
            timer.stop()
        self.timers.clear()
        self._cleanup_callbacks.clear()


class ProcessMonitor:
    """统一的进程监控器
    
    合并原来的 status_timer 和 git_status_timer 功能
    """
    
    def __init__(self, timer_manager: TimerManager):
        self.timer_manager = timer_manager
        self.processes: List[ProcessInfo] = []
        self.check_interval = 500  # 降低频率到500ms
    
    def add_process(self, process: subprocess.Popen, callback: Callable, 
                   name: str, timeout: Optional[int] = None):
        """添加进程监控
        
        Args:
            process: 要监控的进程
            callback: 进程结束时的回调
            name: 进程标识名称
            timeout: 超时时间(秒)，None表示无超时
        """
        process_info = ProcessInfo(
            process=process,
            callback=callback,
            name=name,
            start_time=time.time(),
            timeout=timeout
        )
        
        self.processes.append(process_info)
        self._start_monitoring()
    
    def remove_process(self, name: str) -> bool:
        """移除进程监控"""
        original_count = len(self.processes)
        self.processes = [p for p in self.processes if p.name != name]
        
        if not self.processes:
            self.timer_manager.stop_timer('process_monitor')
        
        return len(self.processes) < original_count
    
    def _start_monitoring(self):
        """开始监控（如果尚未开始）"""
        if not self.timer_manager.is_active('process_monitor'):
            self.timer_manager.create_timer(
                'process_monitor',
                self.check_interval,
                self._check_all_processes
            )
    
    def _check_all_processes(self):
        """检查所有进程状态"""
        current_time = time.time()
        finished_processes = []
        
        for process_info in self.processes:
            # 检查进程是否结束
            if process_info.process.poll() is not None:
                finished_processes.append(process_info)
                continue
            
            # 检查超时
            if (process_info.timeout and 
                current_time - process_info.start_time > process_info.timeout):
                try:
                    process_info.process.terminate()
                    finished_processes.append(process_info)
                except Exception as e:
                    print(f"Failed to terminate process {process_info.name}: {e}")
        
        # 处理结束的进程
        for process_info in finished_processes:
            try:
                process_info.callback(process_info.process.returncode)
            except Exception as e:
                print(f"Process callback error for {process_info.name}: {e}")
            
            self.processes.remove(process_info)
        
        # 如果没有进程需要监控，停止定时器
        if not self.processes:
            self.timer_manager.stop_timer('process_monitor')


class DebounceHelper:
    """防抖辅助工具
    
    替代原来的 resize_event_timer 和 move_event_timer
    """
    
    def __init__(self, timer_manager: TimerManager):
        self.timer_manager = timer_manager
        self.default_delays = {
            'resize': 300,
            'move': 500,
            'input': 300,
            'scroll': 100
        }
    
    def debounce(self, name: str, callback: Callable, delay: Optional[int] = None):
        """防抖执行
        
        Args:
            name: 防抖操作名称
            callback: 要执行的回调函数
            delay: 延迟时间(毫秒)，None时使用默认值
        """
        if delay is None:
            delay = self.default_delays.get(name, 300)
        
        timer_name = f'debounce_{name}'
        
        # 停止之前的定时器
        self.timer_manager.stop_timer(timer_name)
        
        # 创建新的延迟执行
        self.timer_manager.create_single_shot(timer_name, delay, callback)
    
    def set_default_delay(self, operation: str, delay: int):
        """设置默认延迟时间"""
        self.default_delays[operation] = delay
    
    def cancel_debounce(self, name: str):
        """取消防抖操作"""
        timer_name = f'debounce_{name}'
        self.timer_manager.remove_timer(timer_name)


class AutoSubmitTimer:
    """自动提交定时器
    
    专门处理自动提交倒计时功能
    """
    
    def __init__(self, timer_manager: TimerManager):
        self.timer_manager = timer_manager
        self.countdown_remaining = 0
        self.original_text = ""
        self.submit_callback = None
        self.update_callback = None
    
    def start_countdown(self, wait_time: int, submit_callback: Callable,
                       update_callback: Optional[Callable] = None):
        """开始倒计时
        
        Args:
            wait_time: 等待时间(秒)
            submit_callback: 倒计时结束时的提交回调
            update_callback: 每秒更新时的回调(用于更新UI)
        """
        self.countdown_remaining = wait_time
        self.submit_callback = submit_callback
        self.update_callback = update_callback
        
        self.timer_manager.create_timer(
            'auto_submit',
            1000,  # 每秒更新
            self._update_countdown
        )
        
        # 立即更新一次
        self._update_countdown()
    
    def stop_countdown(self):
        """停止倒计时"""
        self.timer_manager.stop_timer('auto_submit')
        if self.update_callback:
            self.update_callback(None)  # 恢复原始状态
    
    def _update_countdown(self):
        """更新倒计时"""
        if self.countdown_remaining <= 0:
            self.timer_manager.stop_timer('auto_submit')
            if self.submit_callback:
                self.submit_callback()
            return
        
        # 更新UI显示
        if self.update_callback:
            self.update_callback(self.countdown_remaining)
        
        self.countdown_remaining -= 1