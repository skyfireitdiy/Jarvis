# -*- coding: utf-8 -*-
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict

from jarvis.jarvis_utils.config import get_data_dir
from jarvis.jarvis_utils.globals import add_short_term_memory
from jarvis.jarvis_utils.output import PrettyOutput


class SaveMemoryTool:
    """保存记忆工具，用于将信息保存到长短期记忆系统"""

    name = "save_memory"
    description = "保存信息到长短期记忆系统。支持批量保存，记忆类型：project_long_term（项目长期）、global_long_term（全局长期）、short_term（短期）。"

    parameters = {
        "type": "object",
        "properties": {
            "memories": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_type": {
                            "type": "string",
                            "enum": [
                                "project_long_term",
                                "global_long_term",
                                "short_term",
                            ],
                            "description": "记忆类型",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "用于索引记忆的标签列表",
                        },
                        "content": {
                            "type": "string",
                            "description": "要保存的记忆内容",
                        },
                    },
                    "required": ["memory_type", "tags", "content"],
                },
                "description": "要保存的记忆列表",
            }
        },
        "required": ["memories"],
    }

    def __init__(self) -> None:
        """初始化保存记忆工具"""
        self.project_memory_dir = Path(".jarvis/memory")
        self.global_memory_dir = Path(get_data_dir()) / "memory"

    def _get_memory_dir(self, memory_type: str) -> Path:
        """根据记忆类型获取存储目录"""
        if memory_type == "project_long_term":
            return Path(self.project_memory_dir)
        elif memory_type in ["global_long_term", "short_term"]:
            return Path(self.global_memory_dir) / memory_type
        else:
            raise ValueError(f"未知的记忆类型: {memory_type}")

    def _generate_memory_id(self) -> str:
        """生成唯一的记忆ID"""
        # 添加微秒级时间戳确保唯一性
        time.sleep(0.001)  # 确保不同记忆有不同的时间戳
        return datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    def _save_single_memory(
        self, memory_data: Dict[str, Any], agent: Any = None
    ) -> Dict[str, Any]:
        """保存单条记忆"""
        memory_type = memory_data["memory_type"]
        tags = memory_data.get("tags", [])
        content = memory_data.get("content", "")

        # 生成记忆ID
        memory_id = self._generate_memory_id()

        # 创建记忆对象
        memory_obj = {
            "id": memory_id,
            "type": memory_type,
            "tags": tags,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        if memory_type == "short_term":
            # 短期记忆保存到全局变量
            add_short_term_memory(memory_obj)

            # 将内容添加到agent的recent_memories列表
            if agent and hasattr(agent, "recent_memories"):
                # 过滤空内容
                if content and content.strip():
                    agent.recent_memories.append(content.strip())
                    # 维护最大10条限制
                    if len(agent.recent_memories) > agent.MAX_RECENT_MEMORIES:
                        agent.recent_memories.pop(0)

            # 旧的pin_content逻辑（已废弃，保留用于向后兼容）
            # if agent and hasattr(agent, "pin_content"):
            #     if agent.pin_content:
            #         agent.pin_content += "\n" + content
            #     else:
            #         agent.pin_content = content

            result = {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "tags": tags,
                "storage": "memory",
                "message": f"短期记忆已成功保存到内存，ID: {memory_id}",
            }
        else:
            # 长期记忆保存到文件
            # 获取存储目录并确保存在
            memory_dir = self._get_memory_dir(memory_type)
            memory_dir.mkdir(parents=True, exist_ok=True)

            # 保存记忆文件
            memory_file = memory_dir / f"{memory_id}.json"
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memory_obj, f, ensure_ascii=False, indent=2)

            # 将内容添加到agent的recent_memories列表
            if agent and hasattr(agent, "recent_memories"):
                # 过滤空内容
                if content and content.strip():
                    agent.recent_memories.append(content.strip())
                    # 维护最大10条限制
                    if len(agent.recent_memories) > agent.MAX_RECENT_MEMORIES:
                        agent.recent_memories.pop(0)

            # 旧的pin_content逻辑（已废弃，保留用于向后兼容）
            # if agent and hasattr(agent, "pin_content"):
            #     if agent.pin_content:
            #         agent.pin_content += "\n" + content
            #     else:
            #         agent.pin_content = content

            result = {
                "memory_id": memory_id,
                "memory_type": memory_type,
                "tags": tags,
                "file_path": str(memory_file),
                "message": f"记忆已成功保存，ID: {memory_id}",
            }

        return result

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行保存记忆操作"""
        try:
            # 获取agent实例（v1.0协议通过arguments注入）
            agent = args.get("agent")
            memories = args.get("memories", [])

            if not memories:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "没有提供要保存的记忆",
                }

            results = []
            success_count = 0
            failed_count = 0

            # 保存每条记忆
            for i, memory_data in enumerate(memories):
                try:
                    result = self._save_single_memory(memory_data, agent)
                    results.append(result)
                    success_count += 1

                    # 打印单条记忆保存信息
                    memory_data["memory_type"]
                    memory_data.get("tags", [])

                except Exception as e:
                    failed_count += 1
                    error_msg = f"保存第 {i + 1} 条记忆失败: {str(e)}"
                    PrettyOutput.auto_print(f"❌ {error_msg}")
                    results.append(
                        {
                            "error": error_msg,
                            "memory_type": memory_data.get("memory_type", "unknown"),
                            "tags": memory_data.get("tags", []),
                        }
                    )

            # 统一打印固定到pin_content的汇总信息
            if (
                agent
                and hasattr(agent, "pin_content")
                and agent.pin_content
                and success_count > 0
            ):
                PrettyOutput.auto_print(f"📌 已固定 {success_count} 条记忆内容")

            # 生成总结报告

            # 构建返回结果
            output = {
                "total": len(memories),
                "success": success_count,
                "failed": failed_count,
                "results": results,
            }

            return {
                "success": True,
                "stdout": json.dumps(output, ensure_ascii=False, indent=2),
                "stderr": "",
            }

        except Exception as e:
            error_msg = f"保存记忆失败: {str(e)}"
            PrettyOutput.auto_print(f"❌ {error_msg}")
            return {"success": False, "stdout": "", "stderr": error_msg}
