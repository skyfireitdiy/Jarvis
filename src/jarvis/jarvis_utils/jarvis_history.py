import glob
import os
from datetime import datetime
from typing import Dict, List, Optional, Union

import yaml


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

    def save_history(self, filename: str) -> None:
        """Save recorded messages to YAML file"""

        # Skip saving if records is empty
        if not self.records:
            return

        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, "w") as f:
            yaml.safe_dump({"conversation": self.records}, f, allow_unicode=True)

    def stop_record(self) -> None:
        """Stop recording session and save messages"""
        if not self.current_file:
            raise RuntimeError("No recording session to stop.")

        self.save_history(self.current_file)
        self.current_file = None
        self.records = []

    @staticmethod
    def export_history_to_markdown(
        input_dir: str, output_file: str, max_files: Optional[int] = None
    ) -> None:
        """
        Export all history files in the directory to a single markdown file

        Args:
            input_dir: Directory containing history YAML files
            output_file: Path to output markdown file
            max_files: Maximum number of history files to export (None for all)
        """
        # Find all history files in the directory
        history_files = glob.glob(os.path.join(input_dir, "history_*.yaml"))

        if not history_files:
            raise FileNotFoundError(f"No history files found in {input_dir}")

        # Sort files by modification time (newest first) and limit to max_files
        history_files.sort(key=os.path.getmtime, reverse=True)
        if max_files is not None:
            history_files = history_files[:max_files]

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as md_file:
            md_file.write("# Jarvis Conversation History\n\n")

            for history_file in sorted(history_files):
                # Read YAML file
                with open(history_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or "conversation" not in data:
                    continue

                # Write file header with timestamp from filename
                timestamp = os.path.basename(history_file)[
                    8:-5
                ]  # Extract timestamp from "history_YYYYMMDD_HHMMSS.yaml"
                md_file.write(
                    f"## Conversation at {timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]} "
                    f"{timestamp[9:11]}:{timestamp[11:13]}:{timestamp[13:15]}\n\n"
                )

                # Write conversation messages
                for msg in data["conversation"]:
                    md_file.write(f"**{msg['role']}**: {msg['message']}\n\n")

                md_file.write("\n---\n\n")
