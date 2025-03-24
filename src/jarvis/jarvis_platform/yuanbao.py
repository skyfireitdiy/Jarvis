from typing import List, Tuple
import requests
import json
import os
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import while_success

class HunyuanModel(BasePlatform):
    """Hunyuan model implementation"""

    platform_name = "yuanbao"

    def get_model_list(self) -> List[Tuple[str, str]]:
        """获取支持的模型列表"""
        return [("deep_seek", "DeepSeek-R1"), ("deep_seek_v3", "DeepSeek-v3"), ("hunyuan_gpt_175B_0404", "Tencent Hunyuan"), ("hunyuan_t1", "Tencent Hunyuan-T1")]
    
    def __init__(self):
        """
        初始化Hunyuan模型
        """
        super().__init__()
        self.conversation_id = ""  # 会话ID，用于标识当前对话
        # 从环境变量中获取必要参数
        self.cookies = os.getenv("YUANBAO_COOKIES")  # 认证cookies
        self.agent_id = os.getenv("YUANBAO_AGENT_ID")  # 代理ID
        
        if not self.cookies:
            message = (
                "需要设置 YUANBAO_COOKIES 和 YUANBAO_AGENT_ID 才能使用 Jarvis 的元宝功能。请按照以下步骤操作：\n"
                "1. 获取元宝 API 参数:\n"
                "   • 访问元宝平台: https://yuanbao.tencent.com\n"
                "   • 登录您的账户\n" 
                "   • 打开浏览器开发者工具 (F12 或右键 -> 检查)\n"
                "   • 切换到网络标签\n"
                "   • 发送任意消息\n"
                "   • 在请求中找到 X-Uskey 和 T-UserID 头部值\n"
                "2. 设置环境变量:\n"
                "   • 方法 1: 创建或编辑 ~/.jarvis/env 文件:\n"
                "   echo 'YUANBAO_COOKIES=your_cookies_here' >> ~/.jarvis/env\n"
                "   echo 'YUANBAO_AGENT_ID=your_agent_id_here' >> ~/.jarvis/env\n"
                "   • 方法 2: 直接设置环境变量:\n"
                "   export YUANBAO_COOKIES=your_cookies_here\n"
                "   export YUANBAO_AGENT_ID=your_agent_id_here\n"
                "设置后，重新运行 Jarvis。"
            )
            PrettyOutput.print(message, OutputType.INFO)
            PrettyOutput.print("YUANBAO_COOKIES 未设置", OutputType.WARNING)
        
        self.system_message = ""  # 系统消息，用于初始化对话
        self.first_chat = True  # 标识是否为第一次对话
        self.model_name = "deep_seek_v3"  # 默认模型名称，使用下划线保持一致

    def set_system_message(self, message: str):
        """Set system message"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        # 模型映射表，可以根据需要扩展
        model_mapping = [m[0] for m in self.get_model_list()]
        
        if model_name in model_mapping:
            self.model_name = model_name
        else:
            PrettyOutput.print(f"错误：不支持的模型: {model_name}", OutputType.ERROR)
        self.reset()

    def _get_base_headers(self):
        """Get base headers for API requests"""
        return {
            'Host': 'yuanbao.tencent.com',
            'X-Language': 'zh-CN', 
            'X-Requested-With': 'XMLHttpRequest',
            'chat_version': 'v1',
            'X-Instance-ID': '5',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'sec-ch-ua-mobile': '?0',
            'Origin': 'https://yuanbao.tencent.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0',
            'Referer': f'https://yuanbao.tencent.com/chat/{self.agent_id}',
            'X-Source': 'web',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept': '*/*',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Dest': 'empty',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'Cookie': self.cookies
        }

    def _create_conversation(self) -> bool:
        """Create a new conversation session"""
        url = "https://yuanbao.tencent.com/api/user/agent/conversation/create"
        
        headers = self._get_base_headers()
        
        payload = json.dumps({
            "agentId": self.agent_id
        })
        
        try:
            response = while_success(lambda: requests.post(url, headers=headers, data=payload), sleep_time=5)
            response_json = response.json()
            
            if "id" in response_json:
                self.conversation_id = response_json["id"]
                return True
            else:
                PrettyOutput.print(f"错误：创建会话失败，响应: {response_json}", OutputType.ERROR)
                return False
        except Exception as e:
            PrettyOutput.print(f"错误：创建会话失败：{e}", OutputType.ERROR)
            return False

    def chat(self, message: str) -> str:
        """Send message and get response"""
        if not self.conversation_id:
            if not self._create_conversation():
                raise Exception("Failed to create conversation session")
        
        url = f"https://yuanbao.tencent.com/api/chat/{self.conversation_id}"
        
        headers = self._get_base_headers()
        
        # 准备消息内容
        payload = {
            "model": "gpt_175B_0404",
            "prompt": message,
            "plugin": "Adaptive",
            "displayPrompt": message,
            "displayPromptType": 1,
            "options": {
                "imageIntention": {
                    "needIntentionModel": True,
                    "backendUpdateFlag": 2,
                    "intentionStatus": True
                }
            },
            "multimedia": [],
            "agentId": self.agent_id,
            "supportHint": 1,
            "version": "v2",
            "supportFunctions": ["supportInternetSearch"],
            "chatModelId": self.model_name,
        }

        
        
        # 添加系统消息（如果是第一次对话）
        if self.first_chat and self.system_message:
            payload["prompt"] = f"{self.system_message}\n\n{message}"
            payload["displayPrompt"] = payload["prompt"]
            self.first_chat = False
        
        try:            
            # 发送消息请求，获取流式响应
            response = while_success(
                lambda: requests.post(url, headers=headers, json=payload, stream=True),
                sleep_time=5
            )
            
            # 检查响应状态
            if response.status_code != 200:
                error_msg = f"发送消息失败，状态码: {response.status_code}"
                if hasattr(response, 'text'):
                    error_msg += f", 响应: {response.text}"
                raise Exception(error_msg)
            
            full_response = ""
            is_text_block = False
            
            # 处理SSE流响应
            for line in response.iter_lines():
                if not line:
                    continue
                
                line_str = line.decode('utf-8')
                
                # SSE格式的行通常以"data: "开头
                if line_str.startswith("data: "):
                    try:
                        data_str = line_str[6:]  # 移除"data: "前缀
                        data = json.loads(data_str)
                        
                        # 处理文本类型的消息
                        if data.get("type") == "text":
                            is_text_block = True
                            msg = data.get("msg", "")
                            if msg:
                                if not self.suppress_output:
                                    PrettyOutput.print_stream(msg)
                                full_response += msg
                        
                        # 处理思考中的消息（可选展示）
                        elif data.get("type") == "think" and not self.suppress_output:
                            think_content = data.get("content", "")
                            # 可以选择性地显示思考过程，但不加入最终响应
                            PrettyOutput.print_stream(f"{think_content}", is_thinking=True)
                            pass
                            
                    except json.JSONDecodeError:
                        pass
                
                # 检测结束标志
                elif line_str == "data: [DONE]":
                    break
            
            if not self.suppress_output:
                PrettyOutput.print_stream_end()
                
            return full_response
            
        except Exception as e:
            raise Exception(f"对话失败: {str(e)}")

    def reset(self):
        """Reset chat"""
        self.conversation_id = ""
        self.first_chat = True

    def delete_chat(self) -> bool:
        """Delete current session"""
        if not self.conversation_id:
            return True  # 如果没有会话ID，视为删除成功
            
        # Hunyuan使用专门的clear API来清除会话
        url = "https://yuanbao.tencent.com/api/user/agent/conversation/v1/clear"
        
        # 为这个请求获取基础头部
        headers = self._get_base_headers()
        
        # 更新X-AgentID头部，需要包含会话ID
        headers.update({
            'X-AgentID': f"{self.agent_id}/{self.conversation_id}"
        })
        
        # 创建请求体，包含要删除的会话ID
        payload = {
            "conversationIds": [self.conversation_id]
        }
        
        try:
            response = while_success(lambda: requests.post(url, headers=headers, json=payload), sleep_time=5)
            
            if response.status_code == 200:
                self.reset()
                return True
            else:
                PrettyOutput.print(f"删除会话失败: HTTP {response.status_code}", OutputType.WARNING)
                if hasattr(response, 'text'):
                    PrettyOutput.print(f"响应: {response.text}", OutputType.WARNING)
                return False
        except Exception as e:
            PrettyOutput.print(f"删除会话时发生错误: {str(e)}", OutputType.ERROR)
            return False

    def name(self) -> str:
        """Model name"""
        return "yuanbao"
