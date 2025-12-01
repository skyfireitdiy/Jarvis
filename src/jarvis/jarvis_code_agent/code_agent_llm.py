# -*- coding: utf-8 -*-
"""CodeAgent LLM 询问模块"""

from typing import Any, Dict


class LLMManager:
    """LLM 询问管理器"""

    def __init__(self, model: Any):
        self.model = model

    def ask_llm_about_large_deletion(
        self, detection_result: Dict[str, int], preview: str
    ) -> bool:
        """询问大模型大量代码删除是否合理

        参数:
            detection_result: 检测结果字典，包含 'insertions', 'deletions', 'net_deletions'
            preview: 补丁预览内容

        返回:
            bool: 如果大模型认为合理返回True，否则返回False
        """
        if not self.model:
            # 如果没有模型，默认认为合理
            return True

        insertions = detection_result["insertions"]
        deletions = detection_result["deletions"]
        net_deletions = detection_result["net_deletions"]

        prompt = f"""检测到大量代码删除，请判断是否合理：

统计信息：
- 新增行数: {insertions}
- 删除行数: {deletions}
- 净删除行数: {net_deletions}

补丁预览：
{preview}

请仔细分析以上代码变更，判断这些大量代码删除是否合理。可能的情况包括：
1. 重构代码，删除冗余或过时的代码
2. 简化实现，用更简洁的代码替换复杂的实现
3. 删除未使用的代码或功能
4. 错误地删除了重要代码

请使用以下协议回答（必须包含且仅包含以下标记之一）：
- 如果认为这些删除是合理的，回答: <!!!YES!!!>
- 如果认为这些删除不合理或存在风险，回答: <!!!NO!!!>

请严格按照协议格式回答，不要添加其他内容。
"""

        try:
            print("🤖 正在询问大模型判断大量代码删除是否合理...")
            response = self.model.chat_until_success(prompt)  # type: ignore

            # 使用确定的协议标记解析回答
            if "<!!!YES!!!>" in response:
                print("✅ 大模型确认：代码删除合理")
                return True
            elif "<!!!NO!!!>" in response:
                print("⚠️ 大模型确认：代码删除不合理")
                return False
            else:
                # 如果无法找到协议标记，默认认为不合理（保守策略）
                print(f"⚠️ 无法找到协议标记，默认认为不合理。回答内容: {response[:200]}")
                return False
        except Exception as e:
            # 如果询问失败，默认认为不合理（保守策略）
            print(f"⚠️ 询问大模型失败: {str(e)}，默认认为不合理")
            return False
