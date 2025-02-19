import json
import os
from datetime import datetime
from typing import List, Dict, Optional
class TaskManager:
    """Task management tool for creating and querying tasks"""
    
    def __init__(self):
        self.storage_path = os.path.expanduser("~/.jarvis/tasks.json")
        self._initialize_storage()
    
    def _initialize_storage(self):
        """Initialize task storage file if it doesn't exist"""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, 'w') as f:
                json.dump([], f)
    
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
        # Validate inputs
        if not all([owner, name, content, deadline]):
            raise ValueError("All fields are required")
            
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d")
            if deadline_date < datetime.now():
                raise ValueError("Deadline cannot be in the past")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
            
        # Create task object
        task = {
            "owner": owner,
            "name": name,
            "content": content,
            "deadline": deadline,
            "created_at": datetime.now().strftime("%Y-%m-%d")
        }
        
        # Save task
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
        # Validate date format
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            if start > end:
                raise ValueError("Start date cannot be after end date")
        except ValueError:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
            
        # Load and filter tasks
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
