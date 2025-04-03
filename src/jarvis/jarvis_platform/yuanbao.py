from typing import Dict, List, Tuple
import requests
import json
import os
import hmac
import hashlib
import time
import urllib.parse
from pathlib import Path
from PIL import Image
from yaspin import yaspin
from yaspin.spinners import Spinners
from yaspin.api import Yaspin
from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import while_success

class YuanbaoPlatform(BasePlatform):
    """Hunyuan模型实现"""

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
        self.web = os.getenv("YUANBAO_WEB", "false") == "true"  # 是否启用网页功能

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
        self.multimedia = []

    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message

    def set_model_name(self, model_name: str):
        # 模型映射表，可以根据需要扩展
        model_mapping = [m[0] for m in self.get_model_list()]

        if model_name in model_mapping:
            self.model_name = model_name
        else:
            PrettyOutput.print(f"错误：不支持的模型: {model_name}", OutputType.ERROR)

    def _get_base_headers(self):
        """获取API请求的基础头部信息"""
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
        """创建一个新的对话会话"""
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

    def upload_files(self, file_list: List[str]) -> bool:
        """上传文件到元宝平台
        
        参数:
            file_list: 要上传的文件路径列表
            
        返回:
            用于聊天消息的文件元数据字典列表
        """
        if not self.cookies:
            PrettyOutput.print("未设置YUANBAO_COOKIES，无法上传文件", OutputType.ERROR)
            return False
            
        uploaded_files = []
        
        for file_path in file_list:
            file_name = os.path.basename(file_path)
            with yaspin(Spinners.dots, text=f"上传文件 {file_name}") as spinner:
                try:
                
                    # 1. Prepare the file information
                    spinner.text = f"准备文件信息: {file_name}"
                    file_size = os.path.getsize(file_path)
                    file_extension = os.path.splitext(file_path)[1].lower().lstrip('.')
                    
                    # Determine file_type using file extension
                    file_type = "txt"  # Default type
                    
                    # Image types
                    if file_extension in ['jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif']:
                        file_type = "image"
                    # PDF type
                    elif file_extension == 'pdf':
                        file_type = "pdf"
                    # Spreadsheet types
                    elif file_extension in ['xls', 'xlsx']:
                        file_type = "excel"
                    # Presentation types 
                    elif file_extension in ['ppt', 'pptx']:
                        file_type = "ppt"
                    # Document types
                    elif file_extension in ['doc', 'docx']:
                        file_type = "doc"
                    # Code file types
                    elif file_extension in ['bat', 'c', 'cpp', 'cs', 'css', 'go', 'h', 'hpp', 'ini',
                         'java', 'js', 'json', 'log', 'lua', 'php', 'pl', 'py', 'rb', 
                         'sh', 'sql', 'swift', 'tex', 'toml', 'vue', 'yaml', 'yml', 'rs']:
                        file_type = "code"
                    
                    # 2. Generate upload information
                    spinner.text = f"获取上传信息: {file_name}"
                    upload_info = self._generate_upload_info(file_name)
                    if not upload_info:
                        spinner.text = f"无法获取文件 {file_name} 的上传信息"
                        spinner.fail("❌")
                        return False
                        
                    # 3. Upload the file to COS
                    spinner.text = f"上传文件到云存储: {file_name}"
                    upload_success = self._upload_file_to_cos(file_path, upload_info, spinner)
                    if not upload_success:
                        spinner.text = f"上传文件 {file_name} 失败"
                        spinner.fail("❌")
                        return False
                        
                    # 4. Create file metadata for chat
                    spinner.text = f"生成文件元数据: {file_name}"
                    file_metadata = {
                        "type": file_type,
                        "docType": file_extension if file_extension else file_type,
                        "url": upload_info.get("resourceUrl", ""),
                        "fileName": file_name,
                        "size": file_size,
                        "width": 0,
                        "height": 0
                    }
                    
                    # Get image dimensions if it's an image file
                    if file_type == "image":
                        try:
                            with Image.open(file_path) as img:
                                file_metadata["width"] = img.width
                                file_metadata["height"] = img.height
                        except Exception as e:
                            spinner.write(f"⚠️ 无法获取图片 {file_name} 的尺寸: {str(e)}")
                    
                    uploaded_files.append(file_metadata)
                    spinner.text = f"文件 {file_name} 上传成功"
                    spinner.ok("✅")
                
                except Exception as e:
                    spinner.text = f"上传文件 {file_path} 时出错: {str(e)}"
                    spinner.fail("❌")
                    return False
        
        self.multimedia = uploaded_files
        return True
        
    def _generate_upload_info(self, file_name: str) -> Dict:
        """从元宝API生成上传信息
        
        参数:
            file_name: 要上传的文件名
            
        返回:
            包含上传信息的字典，如果失败则返回空字典
        """
        url = "https://yuanbao.tencent.com/api/resource/genUploadInfo"
        
        headers = self._get_base_headers()
        
        payload = {
            "fileName": file_name,
            "docFrom": "localDoc",
            "docOpenId": ""
        }
        
        try:
            response = while_success(
                lambda: requests.post(url, headers=headers, json=payload), 
                sleep_time=5
            )
            
            if response.status_code != 200:
                PrettyOutput.print(f"获取上传信息失败，状态码: {response.status_code}", OutputType.ERROR)
                if hasattr(response, 'text'):
                    PrettyOutput.print(f"响应: {response.text}", OutputType.ERROR)
                return {}
                
            upload_info = response.json()
            return upload_info
            
        except Exception as e:
            PrettyOutput.print(f"获取上传信息时出错: {str(e)}", OutputType.ERROR)
            return {}
            
    def _upload_file_to_cos(self, file_path: str, upload_info: Dict, spinner: Yaspin) -> bool:
        """使用提供的上传信息将文件上传到腾讯COS
        
        参数:
            file_path: 要上传的文件路径
            upload_info: 从generate_upload_info获取的上传信息
            
        返回:
            布尔值表示成功或失败
        """
        try:
            # Extract required information from upload_info
            bucket_url = f"https://{upload_info['bucketName']}.{upload_info.get('accelerateDomain', 'cos.accelerate.myqcloud.com')}"
            object_path = upload_info.get('location', '')
            url = f"{bucket_url}{object_path}"
            
            # Security credentials
            tmp_secret_id = upload_info.get('encryptTmpSecretId', '')
            tmp_secret_key = upload_info.get('encryptTmpSecretKey', '')
            token = upload_info.get('encryptToken', '')
            start_time = upload_info.get('startTime', int(time.time()))
            expired_time = upload_info.get('expiredTime', start_time + 600)
            key_time = f"{start_time};{expired_time}"
            
            # Read file content
            with open(file_path, 'rb') as file:
                file_content = file.read()

            spinner.write(f"ℹ️ 上传文件大小: {len(file_content)}")
                
            # Prepare headers for PUT request
            host = f"{upload_info['bucketName']}.{upload_info.get('accelerateDomain', 'cos.accelerate.myqcloud.com')}"
            headers = {
                'Host': host,
                'Content-Length': str(len(file_content)),
                'Content-Type': 'application/octet-stream',
                'x-cos-security-token': token
            }
            
            # Generate signature for COS request (per Tencent Cloud documentation)
            signature = self._generate_cos_signature(
                secret_key=tmp_secret_key,
                method="PUT",
                path=urllib.parse.quote(object_path),
                params={},
                headers={'host': host, 'content-length': headers['Content-Length']},
                key_time=key_time
            )
            
            # Add Authorization header with signature
            headers['Authorization'] = (
                f"q-sign-algorithm=sha1&q-ak={tmp_secret_id}&q-sign-time={key_time}&"
                f"q-key-time={key_time}&q-header-list=content-length;host&"
                f"q-url-param-list=&q-signature={signature}"
            )
            
            # Upload the file
            response = requests.put(url, headers=headers, data=file_content)
            
            if response.status_code not in [200, 204]:
                PrettyOutput.print(f"文件上传到COS失败，状态码: {response.status_code}", OutputType.ERROR)
                if hasattr(response, 'text'):
                    PrettyOutput.print(f"响应: {response.text}", OutputType.ERROR)
                return False
                
            return True
            
        except Exception as e:
            PrettyOutput.print(f"上传文件到COS时出错: {str(e)}", OutputType.ERROR)
            return False
    
    def _generate_cos_signature(self, secret_key: str, method: str, path: str, 
                              params: Dict, headers: Dict, key_time: str) -> str:
        """根据腾讯云COS文档生成COS签名
        
        参数:
            secret_key: 临时密钥
            method: HTTP方法(GET, PUT等)
            path: 对象路径
            params: URL参数
            headers: HTTP头部
            key_time: 签名时间范围
            
        返回:
            签名字符串
        """
        try:
            # 1. Generate SignKey
            sign_key = hmac.new(
                secret_key.encode('utf-8'),
                key_time.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()
            
            # 2. Format parameters and headers
            formatted_params = '&'.join([f"{k.lower()}={urllib.parse.quote(str(v), safe='')}" 
                               for k, v in sorted(params.items())])
            
            formatted_headers = '&'.join([f"{k.lower()}={urllib.parse.quote(str(v), safe='')}" 
                                for k, v in sorted(headers.items())])
            
            # 3. Generate HttpString
            http_string = f"{method.lower()}\n{path}\n{formatted_params}\n{formatted_headers}\n"
            
            # 4. Generate StringToSign
            string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
            
            # 5. Generate Signature
            signature = hmac.new(
                sign_key.encode('utf-8'),
                string_to_sign.encode('utf-8'),
                hashlib.sha1
            ).hexdigest()
            
            return signature
            
        except Exception as e:
            PrettyOutput.print(f"生成签名时出错: {str(e)}", OutputType.ERROR)
            raise e

    def chat(self, message: str) -> str:
        """发送消息并获取响应，可选文件附件
        
        参数:
            message: 要发送的消息文本
            file_list: 可选的上传和附加文件路径列表
            
        返回:
            模型的响应
        """
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
            "multimedia": self.multimedia,
            "agentId": self.agent_id,
            "supportHint": 1,
            "version": "v2",
            "supportFunctions": [],
            "chatModelId": self.model_name,
        }

        self.multimedia = []

        if self.web:
            payload["supportFunctions"] = ["supportInternetSearch"]

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

    def delete_chat(self) -> bool:
        """删除当前会话"""
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
                self.conversation_id = ""
                self.first_chat = True
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
        """模型名称"""
        return self.model_name
