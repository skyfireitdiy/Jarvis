# -*- coding: utf-8 -*-
"""Jarvis Platform Manager Service Module.

This module provides an OpenAI-compatible API service for the Jarvis platform.
"""
import asyncio
import json
import os
import time
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, Response

from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_utils.output import OutputType, PrettyOutput


class ChatMessage(BaseModel):
    """Represents a chat message with role and content."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """Request model for chat completion."""

    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    """Represents a choice in chat completion response."""

    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    """Response model for chat completion."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Dict[str, int] = Field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )


def start_service(
    host: str,
    port: int,
    default_platform: Optional[str] = None,
    default_model: Optional[str] = None,
) -> None:
    """Start OpenAI-compatible API server."""
    # Create logs directory if it doesn't exist
    # Prefer environment variable, then user directory, fall back to CWD
    logs_dir = os.environ.get("JARVIS_LOG_DIR")
    if not logs_dir:
        logs_dir = os.path.join(os.path.expanduser("~"), ".jarvis", "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except Exception:
        # As a last resort, use current working directory
        logs_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(logs_dir, exist_ok=True)

    app = FastAPI(title="Jarvis API Server")

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    registry = PlatformRegistry.get_global_platform_registry()

    PrettyOutput.print(
        f"Starting Jarvis API server on {host}:{port}", OutputType.SUCCESS
    )
    PrettyOutput.print("This server provides an OpenAI-compatible API", OutputType.INFO)

    if default_platform and default_model:
        PrettyOutput.print(
            f"Default platform: {default_platform}, model: {default_model}",
            OutputType.INFO,
        )

    # Platform and model cache
    platform_instances: Dict[str, Any] = {}

    # Chat history storage
    chat_histories: Dict[str, Dict[str, Any]] = {}

    def get_platform_instance(platform_name: str, model_name: str) -> Any:
        """Get or create a platform instance."""
        key = f"{platform_name}:{model_name}"
        if key not in platform_instances:
            platform = registry.create_platform(platform_name)
            if not platform:
                raise HTTPException(
                    status_code=400, detail=f"Platform {platform_name} not found"
                )

            platform.set_model_name(model_name)
            platform_instances[key] = platform

        return platform_instances[key]

    def log_conversation(
        conversation_id: str,
        messages: List[Dict[str, str]],
        model: str,
        response: Optional[str] = None,
    ) -> None:
        """Log conversation to file in plain text format."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = os.path.join(
            logs_dir, f"conversation_{conversation_id}_{timestamp}.txt"
        )

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
    async def list_models() -> Dict[str, Any]:
        """List available models for the specified platform in OpenAI-compatible format."""
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
                            model_list.append(
                                {
                                    "id": full_name,
                                    "object": "model",
                                    "created": int(time.time()),
                                    "owned_by": default_platform,
                                }
                            )
            except Exception as exc:
                PrettyOutput.print(
                    f"Error getting models for {default_platform}: {str(exc)}",
                    OutputType.ERROR,
                )

        # Return model list
        return {"object": "list", "data": model_list}

    @app.post("/v1/chat/completions", response_model=None)
    @app.options("/v1/chat/completions")
    async def create_chat_completion(
        request: ChatCompletionRequest,
    ) -> Response:
        """Create a chat completion in OpenAI-compatible format.

        Returns:
            Response: Either a JSONResponse or StreamingResponse depending on the request.
        """
        model = request.model
        messages = request.messages
        stream = request.stream

        # Generate a conversation ID if this is a new conversation
        conversation_id = str(uuid.uuid4())

        # Extract platform and model name
        if "/" in model:
            platform_name, model_name = model.split("/", 1)
        else:
            # Use default platform if not specified in the model name
            if default_platform:
                platform_name = default_platform
                model_name = model
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Model name must be in 'platform/model_name' format "
                    "or a default platform must be set.",
                )

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
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

        # Logging moved to post-response to avoid duplicates

        if stream:
            # Return streaming response
            return StreamingResponse(
                stream_chat_response(platform, message_text, model),  # type: ignore
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        # Get chat response
        try:
            # Run potentially blocking call in a thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            response_text = await loop.run_in_executor(
                None, lambda: platform.chat_until_success(message_text)
            )

            # Create response in OpenAI format
            completion_id = f"chatcmpl-{str(uuid.uuid4())}"

            # Update chat history with response
            if conversation_id in chat_histories:
                chat_histories[conversation_id]["messages"].append(
                    {"role": "assistant", "content": response_text}
                )

            # Log the conversation with response
            log_conversation(
                conversation_id,
                chat_histories[conversation_id]["messages"],
                model,
                response_text,
            )

            return JSONResponse(
                {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": response_text},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": len(message_text) // 4,
                        "completion_tokens": len(response_text) // 4,
                        "total_tokens": (len(message_text) + len(response_text)) // 4,
                    },
                }
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    async def stream_chat_response(platform: Any, message: str, model_name: str) -> Any:
        """Stream chat response in OpenAI-compatible format without blocking the event loop."""
        completion_id = f"chatcmpl-{str(uuid.uuid4())}"
        created_time = int(time.time())
        conversation_id = str(uuid.uuid4())

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        SENTINEL = object()

        def producer() -> None:
            try:
                for chunk in platform.chat(message):
                    if chunk:
                        asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
            except Exception as exc:
                # Use a special dict to pass error across thread boundary
                asyncio.run_coroutine_threadsafe(
                    queue.put({"__error__": str(exc)}), loop
                )
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(SENTINEL), loop)

        # Start producer thread
        threading.Thread(target=producer, daemon=True).start()

        # Send the initial chunk with the role
        initial_data = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        }
        yield f"data: {json.dumps(initial_data)}\n\n"

        full_response = ""
        has_content = False

        while True:
            item = await queue.get()
            if item is SENTINEL:
                break

            if isinstance(item, dict) and "__error__" in item:
                error_msg = f"Error during streaming: {item['__error__']}"
                PrettyOutput.print(error_msg, OutputType.ERROR)

                # Send error information in the stream
                error_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_time,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": error_msg},
                            "finish_reason": "stop",
                        }
                    ],
                }
                yield f"data: {json.dumps(error_chunk)}\n\n"
                yield "data: [DONE]\n\n"

                # Log the error
                log_conversation(
                    conversation_id,
                    [{"role": "user", "content": message}],
                    model_name,
                    response=f"ERROR: {error_msg}",
                )
                return

            # Normal chunk
            chunk = item
            has_content = True
            full_response += chunk
            chunk_data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"

        if not has_content:
            no_response_message = "No response from model."
            chunk_data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created_time,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": no_response_message},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk_data)}\n\n"
            full_response = no_response_message

        # Send the final chunk with finish_reason
        final_data = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created_time,
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_data)}\n\n"

        # Send the [DONE] marker
        yield "data: [DONE]\n\n"

        # Log the full conversation
        log_conversation(
            conversation_id,
            [{"role": "user", "content": message}],
            model_name,
            full_response,
        )

    # Run the server
    uvicorn.run(app, host=host, port=port)
