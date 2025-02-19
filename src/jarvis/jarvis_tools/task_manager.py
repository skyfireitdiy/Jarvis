from datetime import datetime
from typing import List, Dict, Optional
from jarvis.jarvis_tools.file_operation import FileOperationTool
from jarvis.utils import OutputType, PrettyOutput
import json

class Task:
    """任务数据模型"""
    def __init__(self, owner: str, name: str, content: str, due_date: str):
        self.owner = owner
        self.name = name
        self.content = content
        self.due_date = datetime.fromisoformat(due_date)  # 强制ISO8601格式

class TaskManager:
    """任务管理核心类"""
    _TASK_FILE = "tasks.json"
    
    def __init__(self):
        self.file_tool = FileOperationTool()
        
    def _load_tasks(self) -> List[Dict]:
        """加载所有任务"""
        result = self.file_tool.execute({
            "operation": "read",
            "filepath": self._TASK_FILE
        })
        if not result["success"]:
            return []
        return json.loads(result["stdout"])
    
    def create_task(self, owner: str, name: str, content: str, due_date: str) -> Dict:
        """创建新任务"""
        # 验证日期格式
        try:
            datetime.fromisoformat(due_date)
        except ValueError:
            return {"success": False, "error": "日期格式必须为YYYY-MM-DD"}
            
        new_task = {
            "owner": owner,
            "name": name,
            "content": content,
            "due_date": due_date,
            "created_at": datetime.now().isoformat()
        }
        
        # 读取现有任务并追加
        tasks = self._load_tasks()
        tasks.append(new_task)
        
        # 写入文件
        save_result = self.file_tool.execute({
            "operation": "write",
            "filepath": self._TASK_FILE,
            "content": json.dumps(tasks, ensure_ascii=False)
        })
        
        return {
            "success": save_result["success"],
            "task_id": len(tasks) - 1,
            "error": save_result.get("stderr", "")
        }
    
    def query_tasks(self, owner: str, start_date: str, end_date: str) -> List[Dict]:
        """查询任务"""
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
        except ValueError:
            return []
            
        all_tasks = self._load_tasks()
        return [
            task for task in all_tasks
            if task["owner"] == owner
            and start <= datetime.fromisoformat(task["due_date"]) <= end
        ]
