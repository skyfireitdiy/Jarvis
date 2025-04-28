import os
from jarvis.jarvis_platform.registry import PlatformRegistry
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

from jarvis.jarvis_utils.input import get_multiline_input
from jarvis.jarvis_utils.output import OutputType, PrettyOutput
from jarvis.jarvis_utils.utils import init_env

def list_platforms():
    """List all supported platforms and models"""
    registry = PlatformRegistry.get_global_platform_registry()
    platforms = registry.get_available_platforms()

    PrettyOutput.section("Supported platforms and models", OutputType.SUCCESS)

    for platform_name in platforms:
        # Create platform instance
        platform = registry.create_platform(platform_name)
        if not platform:
            continue

        # Get the list of models supported by the platform
        try:
            models = platform.get_model_list()

            # Print platform name
            PrettyOutput.section(f"{platform_name}", OutputType.SUCCESS)

            output = ""
            # Print model list
            if models:
                for model_name, description in models:
                    if description:
                        output += f"  • {model_name} - {description}\n"
                    else:
                        output += f"  • {model_name}\n"
                PrettyOutput.print(output, OutputType.SUCCESS, lang="markdown")
            else:
                PrettyOutput.print("  • 没有可用的模型信息", OutputType.WARNING)

        except Exception as e:
            PrettyOutput.print(f"获取 {platform_name} 的模型列表失败: {str(e)}", OutputType.WARNING)

def chat_with_model(platform_name: str, model_name: str):
    """Chat with specified platform and model"""
    registry = PlatformRegistry.get_global_platform_registry()

    # Create platform instance
    platform = registry.create_platform(platform_name)
    if not platform:
        PrettyOutput.print(f"创建平台 {platform_name} 失败", OutputType.WARNING)
        return

    try:
        # Set model
        platform.set_model_name(model_name)
        platform.set_suppress_output(False)
        PrettyOutput.print(f"连接到 {platform_name} 平台 {model_name} 模型", OutputType.SUCCESS)
        PrettyOutput.print("可用命令: /bye - 退出聊天, /clear - 清除会话, /upload - 上传文件, /shell - 执行shell命令", OutputType.INFO)

        # Start conversation loop
        while True:
            # Get user input
            user_input = get_multiline_input("")

            # Check if input is cancelled
            if user_input.strip() == "/bye":
                PrettyOutput.print("再见!", OutputType.SUCCESS)
                break

            # Check if input is empty
            if not user_input.strip():
                continue

            # Check if it is a clear session command
            if user_input.strip() == "/clear":
                try:
                    platform.reset()
                    platform.set_model_name(model_name)  # Reinitialize session
                    PrettyOutput.print("会话已清除", OutputType.SUCCESS)
                except Exception as e:
                    PrettyOutput.print(f"清除会话失败: {str(e)}", OutputType.ERROR)
                continue

            # Check if it is an upload command
            if user_input.strip().startswith("/upload"):
                try:
                    file_path = user_input.strip()[8:].strip()
                    if not file_path:
                        PrettyOutput.print("请指定要上传的文件路径，例如: /upload /path/to/file 或 /upload \"/path/with spaces/file\"", OutputType.WARNING)
                        continue
                    
                    # Remove quotes if present
                    if (file_path.startswith('"') and file_path.endswith('"')) or (file_path.startswith("'") and file_path.endswith("'")):
                        file_path = file_path[1:-1]
                    
                    PrettyOutput.print(f"正在上传文件: {file_path}", OutputType.INFO)
                    if platform.upload_files([file_path]):
                        PrettyOutput.print("文件上传成功", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print("文件上传失败", OutputType.ERROR)
                except Exception as e:
                    PrettyOutput.print(f"上传文件失败: {str(e)}", OutputType.ERROR)
                continue

            # Check if it is a shell command
            if user_input.strip().startswith("/shell"):
                try:
                    command = user_input.strip()[6:].strip()
                    if not command:
                        PrettyOutput.print("请指定要执行的shell命令，例如: /shell ls -l", OutputType.WARNING)
                        continue
                    
                    PrettyOutput.print(f"执行命令: {command}", OutputType.INFO)
                    return_code = os.system(command)
                    if return_code == 0:
                        PrettyOutput.print("命令执行完成", OutputType.SUCCESS)
                    else:
                        PrettyOutput.print(f"命令执行失败(返回码: {return_code})", OutputType.ERROR)
                except Exception as ex:
                    PrettyOutput.print(f"执行命令失败: {str(ex)}", OutputType.ERROR)
                continue

            try:
                # Send to model and get reply
                response = platform.chat_until_success(user_input)
                if not response:
                    PrettyOutput.print("没有有效的回复", OutputType.WARNING)

            except Exception as e:
                PrettyOutput.print(f"聊天失败: {str(e)}", OutputType.ERROR)

    except Exception as e:
        PrettyOutput.print(f"初始化会话失败: {str(e)}", OutputType.ERROR)
    finally:
        # Clean up resources
        try:
            platform.reset()
        except:
            pass

# Helper function for platform and model validation
def validate_platform_model(args):
    if not args.platform or not args.model:
        PrettyOutput.print("请指定平台和模型。使用 'jarvis info' 查看可用平台和模型。", OutputType.WARNING)
        return False
    return True

def chat_command(args):
    """Process chat subcommand"""
    if not validate_platform_model(args):
        return
    chat_with_model(args.platform, args.model)

def info_command(args):
    """Process info subcommand"""
    list_platforms()

# New models for OpenAI-compatible API
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

def service_command(args):
    """Process service subcommand - start OpenAI-compatible API server"""
    import time
    import uuid
    import json
    import os
    from datetime import datetime

    host = args.host
    port = args.port
    default_platform = args.platform
    default_model = args.model

    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    app = FastAPI(title="Jarvis API Server")

    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许所有来源，生产环境应更严格
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有方法
        allow_headers=["*"],  # 允许所有头
    )

    registry = PlatformRegistry.get_global_platform_registry()

    PrettyOutput.print(f"Starting Jarvis API server on {host}:{port}", OutputType.SUCCESS)
    PrettyOutput.print("This server provides an OpenAI-compatible API", OutputType.INFO)

    if default_platform and default_model:
        PrettyOutput.print(f"Default platform: {default_platform}, model: {default_model}", OutputType.INFO)

    PrettyOutput.print("Available platforms:", OutputType.INFO)

    # Print available platforms and models
    platforms = registry.get_available_platforms()
    list_platforms()

    # Platform and model cache
    platform_instances = {}

    # Chat history storage
    chat_histories = {}

    def get_platform_instance(platform_name: str, model_name: str):
        """Get or create a platform instance"""
        key = f"{platform_name}:{model_name}"
        if key not in platform_instances:
            platform = registry.create_platform(platform_name)
            if not platform:
                raise HTTPException(status_code=400, detail=f"Platform {platform_name} not found")

            platform.set_model_name(model_name)
            platform_instances[key] = platform

        return platform_instances[key]

    def log_conversation(conversation_id, messages, model, response=None):
        """Log conversation to file in plain text format."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(logs_dir, f"conversation_{conversation_id}_{timestamp}.txt")

        with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
            f.write(f"Conversation ID: {conversation_id}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Model: {model}\n\n")
            f.write("Messages:\n")
            for message in messages:
                f.write(f"{message['role']}: {message['content']}\n")
            if response:
                f.write(f"\nResponse:\n{response}\n")

        PrettyOutput.print(f"Conversation logged to {log_file}", OutputType.INFO)

    @app.get("/v1/models")
    async def list_models():
        """List available models for the specified platform in OpenAI-compatible format"""
        model_list = []

        # Only get models for the currently set platform
        if default_platform:
            try:
                platform = registry.create_platform(default_platform)
                if platform:
                    models = platform.get_model_list()
                    if models:
                        for model_name, _ in models:
                            full_name = f"{default_platform}/{model_name}"
                            model_list.append({
                                "id": full_name,
                                "object": "model",
                                "created": int(time.time()),
                                "owned_by": default_platform
                            })
            except Exception as e:
                print(f"Error getting models for {default_platform}: {str(e)}")

        # Return model list
        return {"object": "list", "data": model_list}

    @app.post("/v1/chat/completions")
    @app.options("/v1/chat/completions")  # 添加 OPTIONS 方法支持
    async def create_chat_completion(request: ChatCompletionRequest):
        """Create a chat completion in OpenAI-compatible format"""
        model = request.model
        messages = request.messages
        stream = request.stream

        # Generate a conversation ID if this is a new conversation
        conversation_id = str(uuid.uuid4())

        # Extract platform and model name
        if "/" in model:
            platform_name, model_name = model.split("/", 1)
        else:
            # Use default platform and model if not specified
            if default_platform and default_model:
                platform_name, model_name = default_platform, default_model
            else:
                platform_name, model_name = "oyi", model  # Default to OYI platform

        # Get platform instance
        platform = get_platform_instance(platform_name, model_name)

        # Convert messages to text format for the platform
        message_text = ""
        for msg in messages:
            role = msg.role
            content = msg.content

            if role == "system":
                message_text += f"System: {content}\n\n"
            elif role == "user":
                message_text += f"User: {content}\n\n"
            elif role == "assistant":
                message_text += f"Assistant: {content}\n\n"

        # Store messages in chat history
        chat_histories[conversation_id] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages]
        }

        # Log the conversation
        log_conversation(conversation_id,
                         [{"role": m.role, "content": m.content} for m in messages],
                         model)

        if stream:
            # Return streaming response
            return StreamingResponse(
                stream_chat_response(platform, message_text, model),
                media_type="text/event-stream"
            )
        else:
            # Get chat response
            try:
                response_text = platform.chat_until_success(message_text)

                # Create response in OpenAI format
                completion_id = f"chatcmpl-{str(uuid.uuid4())}"

                # Update chat history with response
                if conversation_id in chat_histories:
                    chat_histories[conversation_id]["messages"].append({
                        "role": "assistant",
                        "content": response_text
                    })

                # Log the conversation with response
                log_conversation(conversation_id,
                                 chat_histories[conversation_id]["messages"],
                                 model,
                                 response_text)

                return {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": response_text
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": len(message_text) // 4,  # Rough estimate
                        "completion_tokens": len(response_text) // 4,  # Rough estimate
                        "total_tokens": (len(message_text) + len(response_text)) // 4  # Rough estimate
                    }
                }
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    async def stream_chat_response(platform, message, model_name):
        """Stream chat response in OpenAI-compatible format"""
        import time
        import json
        import uuid
        from datetime import datetime
        import os

        completion_id = f"chatcmpl-{str(uuid.uuid4())}"
        created_time = int(time.time())
        conversation_id = str(uuid.uuid4())

        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # 修改第一个yield语句的格式
        initial_data = {
            'id': completion_id,
            'object': 'chat.completion.chunk',
            'created': created_time,
            'model': model_name,
            'choices': [{
                'index': 0,
                'delta': {'role': 'assistant'},
                'finish_reason': None
            }]
        }
        res = json.dumps(initial_data)
        yield f"data: {res}\n\n"

        try:
            # 直接获取聊天响应，而不是尝试捕获stdout
            response = platform.chat_until_success(message)

            # 记录完整响应
            full_response = ""

            # 如果有响应，将其分块发送
            if response:
                # 分成小块以获得更好的流式体验
                chunk_size = 4  # 每个块的字符数
                for i in range(0, len(response), chunk_size):
                    chunk = response[i:i+chunk_size]
                    full_response += chunk

                    # 创建并发送块
                    chunk_data = {
                        'id': completion_id,
                        'object': 'chat.completion.chunk',
                        'created': created_time,
                        'model': model_name,
                        'choices': [{
                            'index': 0,
                            'delta': {'content': chunk},
                            'finish_reason': None
                        }]
                    }

                    yield f"data: {json.dumps(chunk_data)}\n\n"

                    # 小延迟以模拟流式传输
                    await asyncio.sleep(0.01)
            else:
                # 如果没有输出，发送一个空内容块
                chunk_data = {
                    'id': completion_id,
                    'object': 'chat.completion.chunk',
                    'created': created_time,
                    'model': model_name,
                    'choices': [{
                        'index': 0,
                        'delta': {'content': "No response from model."},
                        'finish_reason': None
                    }]
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"
                full_response = "No response from model."

            # 修改最终yield语句的格式
            final_data = {
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created_time,
                'model': model_name,
                'choices': [{
                    'index': 0,
                    'delta': {},
                    'finish_reason': 'stop'
                }]
            }
            yield f"data: {json.dumps(final_data)}\n\n"

            # 发送[DONE]标记
            yield "data: [DONE]\n\n"

            # 记录对话到文件
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = os.path.join(logs_dir, f"stream_conversation_{conversation_id}_{timestamp}.json")

            log_data = {
                "conversation_id": conversation_id,
                "timestamp": timestamp,
                "model": model_name,
                "message": message,
                "response": full_response
            }

            with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            PrettyOutput.print(f"Stream conversation logged to {log_file}", OutputType.INFO)

        except Exception as e:
            # 发送错误消息
            error_msg = f"Error: {str(e)}"
            print(f"Streaming error: {error_msg}")

            res = json.dumps({
                'id': completion_id,
                'object': 'chat.completion.chunk',
                'created': created_time,
                'model': model_name,
                'choices': [{
                    'index': 0,
                    'delta': {'content': error_msg},
                    'finish_reason': 'stop'
                }]
            })
            yield f"data: {res}\n\n"
            yield f"data: {json.dumps({'error': {'message': error_msg, 'type': 'server_error'}})}\n\n"
            yield "data: [DONE]\n\n"

            # 记录错误到文件
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_file = os.path.join(logs_dir, f"stream_error_{conversation_id}_{timestamp}.json")

            log_data = {
                "conversation_id": conversation_id,
                "timestamp": timestamp,
                "model": model_name,
                "message": message,
                "error": error_msg
            }

            with open(log_file, "w", encoding="utf-8", errors="ignore") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            PrettyOutput.print(f"Stream error logged to {log_file}", OutputType.ERROR)

    # Run the server
    uvicorn.run(app, host=host, port=port)

def main():
    """Main function"""
    import argparse

    init_env()

    parser = argparse.ArgumentParser(description='Jarvis AI 平台')
    subparsers = parser.add_subparsers(dest='command', help='可用子命令')

    # info subcommand
    info_parser = subparsers.add_parser('info', help='显示支持的平台和模型信息')

    # chat subcommand
    chat_parser = subparsers.add_parser('chat', help='与指定平台和模型聊天')
    chat_parser.add_argument('--platform', '-p', help='指定要使用的平台')
    chat_parser.add_argument('--model', '-m', help='指定要使用的模型')

    # service subcommand
    service_parser = subparsers.add_parser('service', help='启动OpenAI兼容的API服务')
    service_parser.add_argument('--host', default='127.0.0.1', help='服务主机地址 (默认: 127.0.0.1)')
    service_parser.add_argument('--port', type=int, default=8000, help='服务端口 (默认: 8000)')
    service_parser.add_argument('--platform', '-p', help='指定默认平台，当客户端未指定平台时使用')
    service_parser.add_argument('--model', '-m', help='指定默认模型，当客户端未指定模型时使用')

    args = parser.parse_args()

    if args.command == 'info':
        info_command(args)
    elif args.command == 'chat':
        chat_command(args)
    elif args.command == 'service':
        service_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()