from typing import Dict, List, Tuple
import os
from openai import OpenAI
from jarvis.models.base import BasePlatform
from jarvis.utils import PrettyOutput, OutputType

class OpenAIModel(BasePlatform):
    platform_name = "openai"

    def upload_files(self, file_list: List[str]):
        """Upload files"""
        PrettyOutput.print("OpenAI does not support file upload", OutputType.WARNING)
    
    def __init__(self):
        """
        Initialize OpenAI model
        """
        super().__init__()
        self.system_message = ""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            PrettyOutput.print("\nNeed to set the following environment variables to use OpenAI model:", OutputType.INFO)
            PrettyOutput.print("  • OPENAI_API_KEY: API key", OutputType.INFO)
            PrettyOutput.print("  • OPENAI_API_BASE: (optional) API base address, default using https://api.openai.com/v1", OutputType.INFO)
            PrettyOutput.print("\nYou can set them in the following ways:", OutputType.INFO)
            PrettyOutput.print("1. Create or edit ~/.jarvis_env file:", OutputType.INFO)
            PrettyOutput.print("   OPENAI_API_KEY=your_api_key", OutputType.INFO)
            PrettyOutput.print("   OPENAI_API_BASE=your_api_base", OutputType.INFO)
            PrettyOutput.print("   OPENAI_MODEL_NAME=your_model_name", OutputType.INFO)
            PrettyOutput.print("\n2. Or set the environment variables directly:", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_API_KEY=your_api_key", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_API_BASE=your_api_base", OutputType.INFO)
            PrettyOutput.print("   export OPENAI_MODEL_NAME=your_model_name", OutputType.INFO)
            PrettyOutput.print("OPENAI_API_KEY is not set", OutputType.WARNING)
            
        self.base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model_name =  os.getenv("JARVIS_MODEL") or "gpt-4o"

            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.messages: List[Dict[str, str]] = []
        self.system_message = ""

    def get_model_list(self) -> List[Tuple[str, str]]:
        """Get model list"""
        return []

    def set_model_name(self, model_name: str):
        """Set model name"""

        self.model_name = model_name

    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message
        self.messages.append({"role": "system", "content": self.system_message})

    def chat(self, message: str) -> str:
        """Execute conversation"""
        try:
            
            # Add user message to history
            self.messages.append({"role": "user", "content": message})
            
            response = self.client.chat.completions.create(
                model=self.model_name,  # Use the configured model name
                messages=self.messages, # type: ignore
                stream=True
            ) # type: ignore
            
            full_response = ""
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    if not self.suppress_output:
                        PrettyOutput.print_stream(text)
                    full_response += text
                    
            if not self.suppress_output:
                PrettyOutput.print_stream_end()
            
            # Add assistant reply to history
            self.messages.append({"role": "assistant", "content": full_response})
            
            return full_response
            
        except Exception as e:
            PrettyOutput.print(f"Chat failed: {str(e)}", OutputType.ERROR)
            raise Exception(f"Chat failed: {str(e)}")

    def name(self) -> str:
        """Return model name"""
        return self.model_name

    def reset(self):
        """Reset model state"""
        # Clear conversation history, only keep system message
        if self.system_message:
            self.messages = [{"role": "system", "content": self.system_message}]
        else:
            self.messages = []

    def delete_chat(self)->bool:
        """Delete conversation"""
        self.reset()
        return True
