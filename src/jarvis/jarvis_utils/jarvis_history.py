import os
import yaml
from datetime import datetime
from typing import List, Dict, Optional

class JarvisHistory:
    def __init__(self):
        self.records: List[Dict[str, str]] = []
        self.current_file: Optional[str] = None

    def start_record(self, data_dir: str) -> None:
        """Start a new recording session with timestamped filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.current_file = os.path.join(data_dir, f"history_{timestamp}.yaml")
        self.records = []

    def append_msg(self, role: str, msg: str) -> None:
        """Append a message to current recording session"""
        if not self.current_file:
            raise RuntimeError("Recording not started. Call start_record first.")
        self.records.append({"role": role, "message": msg})

    def stop_record(self) -> None:
        """Save recorded messages to YAML file"""
        if not self.current_file:
            raise RuntimeError("No recording session to stop.")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.current_file), exist_ok=True)
        
        with open(self.current_file, 'w') as f:
            yaml.safe_dump({"conversation": self.records}, f)
        
        self.current_file = None
        self.records = []
