# -*- coding: utf-8 -*-
"""技能评估器 - 使用 LLM 评估远程技能的相关性和价值"""

import asyncio
from typing import List, Dict, Any
from dataclasses import dataclass
from .sources.base import SkillResult


@dataclass
class SkillEvaluation:
    """技能评估结果"""

    skill: SkillResult
    score: float  # 0-10 分
    recommendation: str  # 推荐理由
    concerns: List[str]  # 潜在问题
    should_install: bool  # 是否推荐安装


class SkillEvaluator:
    """
    使用 LLM 评估远程技能的相关性和价值

    评估维度：
    1. 相关性：技能与任务描述的匹配程度
    2. 实用性：技能是否能解决实际问题
    3. 安全性：技能是否存在潜在风险
    4. 完整性：技能文档和质量是否可靠
    """

    EVALUATION_PROMPT = """你是一个专业的 AI 技能评估专家。请评估以下技能是否适合解决用户的任务。

## 用户任务描述
{task_description}

## 待评估技能
- 名称：{skill_name}
- 描述：{skill_description}
- 来源平台：{platform}
- 作者：{author}
- 标签：{tags}
- 质量评分：{quality_score}/10
- 流行度（stars）：{popularity}

## 评估要求
请从以下维度进行评估（每项 0-10 分）：
1. **相关性**：技能与任务描述的匹配程度
2. **实用性**：技能是否能实际解决问题
3. **安全性**：技能是否存在潜在风险（如执行危险命令、访问敏感数据等）
4. **完整性**：技能文档是否完整、示例是否清晰

## 输出格式
请严格按照以下 JSON 格式输出：
{{
    "scores": {{
        "relevance": 0-10,
        "practicality": 0-10,
        "safety": 0-10,
        "completeness": 0-10
    }},
    "overall_score": 0-10,
    "recommendation": "一句话说明是否推荐安装及理由",
    "concerns": ["潜在问题列表，如无问题则为空数组"],
    "should_install": true/false
}}

## 评估标准
- overall_score >= 7.0 且 should_install = true：强烈推荐安装
- overall_score >= 5.0 且 < 7.0：可考虑安装
- overall_score < 5.0 或 safety < 6.0：不推荐安装

请开始评估："""

    def __init__(self, llm_client: Any, model: str = "default"):
        """
        参数:
            llm_client: LLM 客户端实例（需支持 chat/completions 接口）
            model: 使用的模型名称
        """
        self.llm_client = llm_client
        self.model = model

    async def evaluate_async(
        self, task_description: str, skill: SkillResult
    ) -> SkillEvaluation:
        """
        异步评估单个技能

        参数:
            task_description: 任务描述
            skill: 待评估的技能

        返回:
            SkillEvaluation 评估结果
        """
        try:
            # 构建评估 prompt
            prompt = self.EVALUATION_PROMPT.format(
                task_description=task_description,
                skill_name=skill.name,
                skill_description=skill.description or "无描述",
                platform=skill.platform,
                author=skill.author or "未知",
                tags=", ".join(skill.tags) if skill.tags else "无",
                quality_score=skill.quality_score,
                popularity=skill.popularity,
            )

            # 调用 LLM
            response = await self._call_llm(prompt)

            # 解析响应
            evaluation_data = self._parse_response(response)

            return SkillEvaluation(
                skill=skill,
                score=evaluation_data.get("overall_score", 0),
                recommendation=evaluation_data.get("recommendation", ""),
                concerns=evaluation_data.get("concerns", []),
                should_install=evaluation_data.get("should_install", False),
            )

        except Exception as e:
            # 失败时返回保守评估
            return SkillEvaluation(
                skill=skill,
                score=3.0,
                recommendation=f"评估失败：{str(e)}",
                concerns=["LLM 评估异常，建议人工审核"],
                should_install=False,
            )

    async def evaluate_batch_async(
        self, task_description: str, skills: List[SkillResult], max_concurrent: int = 3
    ) -> List[SkillEvaluation]:
        """
        批量评估技能（并发执行）

        参数:
            task_description: 任务描述
            skills: 待评估的技能列表
            max_concurrent: 最大并发数

        返回:
            评估结果列表（按分数降序排列）
        """
        # 限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def evaluate_with_semaphore(skill: SkillResult) -> SkillEvaluation:
            async with semaphore:
                return await self.evaluate_async(task_description, skill)

        tasks = [evaluate_with_semaphore(skill) for skill in skills]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤异常结果
        evaluations = [r for r in results if isinstance(r, SkillEvaluation)]

        # 按分数降序排序
        evaluations.sort(key=lambda e: e.score, reverse=True)

        return evaluations

    def evaluate(self, task_description: str, skill: SkillResult) -> SkillEvaluation:
        """同步评估包装器"""
        return asyncio.run(self.evaluate_async(task_description, skill))

    def evaluate_batch(
        self, task_description: str, skills: List[SkillResult], max_concurrent: int = 3
    ) -> List[SkillEvaluation]:
        """同步批量评估包装器"""
        return asyncio.run(
            self.evaluate_batch_async(task_description, skills, max_concurrent)
        )

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM 获取评估结果"""
        try:
            # 尝试标准的 OpenAI 风格接口
            if hasattr(self.llm_client, "chat") and hasattr(
                self.llm_client.chat, "completions"
            ):
                response = self.llm_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的 AI 技能评估专家，负责评估技能的相关性和价值。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,  # 降低随机性，提高一致性
                    max_tokens=500,
                )
                return response.choices[0].message.content

            # 尝试直接调用 create 方法
            elif hasattr(self.llm_client, "create"):
                response = self.llm_client.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "你是一个专业的 AI 技能评估专家。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=500,
                )
                return response.choices[0].message.content

            else:
                raise ValueError("LLM 客户端不支持的接口类型")

        except Exception as e:
            raise RuntimeError(f"LLM 调用失败：{str(e)}")

    def _parse_response(self, response: str) -> Dict:
        """解析 LLM 响应（支持 JSON 和自然语言）"""
        import json
        import re

        # 尝试提取 JSON
        json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 降级：尝试解析自然语言响应
        # 默认保守评估
        return {
            "overall_score": 5.0,
            "recommendation": response[:200] if response else "无法解析评估结果",
            "concerns": ["LLM 响应格式异常"],
            "should_install": False,
        }
