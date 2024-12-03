from typing import Dict, List, Optional
import requests
from config import (
    AGENT_A_PROMPT, 
    AGENT_B_PROMPT,
    CONVERSATIONS_DIR,
    OLLAMA_BASE_URL,
    AGENT_A_MODEL,
    AGENT_B_MODEL,
    MAX_MESSAGES
)
from protocol import Conversation, create_task_id
from utils import print_colored

def check_ollama_connection(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/api/tags")
        return response.status_code == 200
    except Exception:
        return False

class Agent:
    def __init__(self, role: str, system_prompt: str, model: str):
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        
        if not check_ollama_connection(OLLAMA_BASE_URL):
            raise ConnectionError(
                f"无法连接到Ollama服务 ({OLLAMA_BASE_URL})。\n"
                "请确保：\n"
                "1. 已经安装了Ollama\n"
                "2. Ollama服务正在运行\n"
                "3. 已经下载了所需的模型"
            )
    
    def generate_response(self, messages: List[Dict]) -> str:
        # 转换消息格式为Ollama chat API格式
        chat_messages = [
            {"role": "system", "content": self.system_prompt}
        ]
        
        for msg in messages:
            # 如果消息是自己发的，设为assistant
            # 如果是对方发的，设为user
            if msg["role"] == self.role:
                role = "assistant"
            else:
                role = "user"
            
            chat_messages.append({
                "role": role,
                "content": msg["content"]
            })
            
        data = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False
        }
        
        try:
            response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=data)
            response.raise_for_status()
            result = response.json()
            return result["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise ConnectionError("无法连接到Ollama服务。请确保服务正在运行。")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError(f"模型 '{self.model}' 未找到。请运行: ollama pull {self.model}")
            raise
        except Exception as e:
            print(f"Error generating response: {str(e)}")
            return "抱歉，生成响应时出现错误。"

class DialogueManager:
    def __init__(self):
        self.agent_a = Agent("A", AGENT_A_PROMPT, AGENT_A_MODEL)
        self.agent_b = Agent("B", AGENT_B_PROMPT, AGENT_B_MODEL)
        self.current_conversation: Optional[Conversation] = None
        
    def start_dialogue(self, initial_message: str) -> str:
        task_id = create_task_id()
        self.current_conversation = Conversation(task_id, save_dir=CONVERSATIONS_DIR)
        self.current_conversation.add_message("A", initial_message)
        return task_id
    
    def continue_dialogue(self) -> None:
        if not self.current_conversation:
            raise ValueError("No active conversation")
            
        while True:
            try:
                b_response = self.agent_b.generate_response(
                    self.current_conversation.messages
                )
                self.current_conversation.add_message("B", b_response)
                print_colored(f"\nB: {b_response}", "green")
                
                self._maintain_context_length()
                
                a_response = self.agent_a.generate_response(
                    self.current_conversation.messages
                )
                self.current_conversation.add_message("A", a_response)
                print_colored(f"\nA: {a_response}", "blue")
                
                self._maintain_context_length()
                self.current_conversation.save()
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print_colored(f"对话出现错误: {str(e)}", "red")
                continue
    
    def _maintain_context_length(self):
        """维护消息数量，确保不超过限制"""
        while len(self.current_conversation.messages) > MAX_MESSAGES:
            # 当消息数量超过限制时，移除最旧的消息
            self.current_conversation.messages.pop(0)