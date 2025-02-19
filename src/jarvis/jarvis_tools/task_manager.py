import json
import os
from datetime import datetime
from typing import List, Dict, Optional
from .base import Tool
class TaskManager(Tool):
    """Task management tool for creating and querying tasks"""
    
    name = "task_manager"
    description = "Manage tasks with creation and querying capabilities"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["create", "query"],
                "description": "Operation to perform: 'create' or 'query'"
            },
            "owner": {
                "type": "string",
                "description": "Task owner/assignee"
            },
            "name": {
                "type": "string",
                "description": "Task name (required for create)"
            },
            "content": {
                "type": "string",
                "description": "Task description (required for create)"
            },
            "deadline": {
                "type": "string",
                "format": "date",
                "description": "Task deadline in YYYY-MM-DD format (required for create)"
            },
            "start_date": {
                "type": "string",
                "format": "date",
                "description": "Start date for query in YYYY-MM-DD format (required for query)"
            },
            "end_date": {
                "type": "string",
                "format": "date",
                "description": "End date for query in YYYY-MM-DD format (required for query)"
            }
        },
        "required": ["operation", "owner"]
    }
    
    def __init__(self):
        super().__init__()
        self.storage_path = os.path.expanduser("~/.jarvis/tasks.json")
        self._initialize_storage()
    
    def _initialize_storage(self):
        """Initialize task storage file if it doesn't exist"""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f:
                json.dump([], f)
    
    def execute(self, arguments: Dict) -> Dict:
        """
        Execute task manager operations
        
        Args:
            arguments: Dictionary containing operation parameters
            
        Returns:
            Dictionary with operation results
        """
        operation = arguments.get("operation")
        owner = arguments.get("owner")
        
        if operation == "create":
            return self._handle_create(arguments)
        elif operation == "query":
            return self._handle_query(arguments)
        else:
            return {
                "success": False,
                "stderr": f"Invalid operation: {operation}. Must be 'create' or 'query'"
            }
    
    def _handle_create(self, arguments: Dict) -> Dict:
        """Handle task creation"""
        try:
            task = self.create_task(
                owner=arguments["owner"],
                name=arguments["name"],
                content=arguments["content"],
                deadline=arguments["deadline"]
            )
            return {
                "success": True,
                "stdout": f"Task created successfully: {task}"
            }
        except Exception as e:
            return {
                "success": False,
                "stderr": str(e)
            }
    
    def _handle_query(self, arguments: Dict) -> Dict:
        """Handle task query"""
        try:
            tasks = self.query_tasks(
                owner=arguments["owner"],
                start_date=arguments["start_date"],
                end_date=arguments["end_date"]
            )
            return {
                "success": True,
                "stdout": json.dumps(tasks, indent=2)
            }
        except Exception as e:
            return {
                "success": False,
                "stderr": str(e)
            }
    
    def create_task(self, owner: str, name: str, content: str, deadline: str) -> Dict:
        """
        Create a new task with validation
        
        Args:
            owner: Task owner/assignee
            name: Task name
            content: Task description
            deadline: Task deadline in YYYY-MM-DD format
            
        Returns:
            Created task details
        """
        if not all([owner, name, content, deadline]):
            raise ValueError("All fields are required")
            
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d")
            if deadline_date < datetime.now():
                raise ValueError("Deadline cannot be in the past")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
            
        task = {
            "owner": owner,
            "name": name,
            "content": content,
            "deadline": deadline,
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
        
        tasks = self._load_tasks()
        tasks.append(task)
        self._save_tasks(tasks)
        
        return task
    
    def query_tasks(self, owner: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Query tasks by owner and date range
        
        Args:
            owner: Task owner to filter by
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of matching tasks
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if start > end:
                raise ValueError("Start date cannot be after end date")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
            
        tasks = self._load_tasks()
        return [
            task for task in tasks
            if task["owner"] == owner and
            start <= datetime.strptime(task["created_at"], "%Y-%m-%d") <= end
        ]
    
    def _load_tasks(self) -> List[Dict]:
        """Load tasks from storage"""
        with open(self.storage_path, 'r') as f:
            return json.load(f)
    
    def _save_tasks(self, tasks: List[Dict]):
        """Save tasks to storage"""
        with open(self.storage_path, 'w') as f:
            json.dump(tasks, f, indent=2)
