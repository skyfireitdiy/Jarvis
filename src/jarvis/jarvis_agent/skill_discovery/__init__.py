# -*- coding: utf-8 -*-
"""技能发现模块

提供对全球 AI Skill 生态的按需自动发现、评估与安装能力。

核心组件:
   - SkillSearchEngine: 多源搜索引擎
   - SkillEvaluator: LLM 技能评估器
   - SkillInstaller: Git Clone 安装器
   - ISkillSource: 发现源抽象接口
   - SkillResult: 统一结果模型

使用示例:
   >>> from jarvis.jarvis_agent.skill_discovery import SkillSearchEngine, SkillEvaluator, SkillInstaller
   >>>
   >>> # 搜索技能
   >>> engine = SkillSearchEngine()
   >>> results = engine.search("PDF reader")
   >>>
   >>> # 使用 LLM 评估技能
   >>> evaluator = SkillEvaluator(llm_client=llm_client)
   >>> evaluations = evaluator.evaluate_batch("我需要读取 PDF 文件", results)
   >>>
   >>> # 安装推荐的技能
   >>> installer = SkillInstaller(rules_manager=rules_manager)
   >>> for eval_result in evaluations:
   ...     if eval_result.should_install:
   ...         installer.install(eval_result.skill)
"""

from .search_engine import SkillSearchEngine
from .installer import SkillInstaller
from .skill_evaluator import SkillEvaluator, SkillEvaluation
from .sources.base import ISkillSource, SkillResult

__all__ = [
    "SkillSearchEngine",
    "SkillEvaluator",
    "SkillEvaluation",
    "SkillInstaller",
    "ISkillSource",
    "SkillResult",
]
