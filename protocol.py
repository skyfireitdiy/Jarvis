import time
from pathlib import Path
from typing import Dict, List, Optional

class Conversation:
    def __init__(self, task_id: str, save_dir: Path = None):
        self.task_id = task_id
        self.messages: List[Dict] = []
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.status = "ongoing"  # ongoing, completed, interrupted
        self.save_dir = save_dir
        
    def add_message(self, role: str, content: str):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time()
        })
    
    def complete(self, status: str = "completed"):
        self.end_time = time.time()
        self.status = status
        
    def save(self, save_dir: Optional[Path] = None):
        """保存对话记录到文本文件"""
        if save_dir is None:
            save_dir = self.save_dir
            
        if save_dir is None:
            raise ValueError("No save directory specified")
            
        file_path = save_dir / f"task_{self.task_id}.txt"
        
        with open(file_path, "w", encoding="utf-8") as f:
            # 写入基本信息
            f.write(f"对话ID: {self.task_id}\n")
            f.write(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time))}\n")
            if self.end_time:
                f.write(f"结束时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.end_time))}\n")
            f.write(f"状态: {self.status}\n")
            f.write("\n=== 对话内容 ===\n\n")
            
            # 写入对话内容
            for msg in self.messages:
                timestamp = time.strftime('%H:%M:%S', time.localtime(msg["timestamp"]))
                f.write(f"[{timestamp}] {msg['role']}: {msg['content']}\n\n")
        
        return file_path

def create_task_id() -> str:
    """创建基于时间戳的任务ID"""
    return str(int(time.time()))