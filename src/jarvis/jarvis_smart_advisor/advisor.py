"""智能顾问主类

该模块提供智能顾问的统一接口，整合各种顾问能力。
"""

from pathlib import Path
from typing import List, Optional

from jarvis.jarvis_smart_advisor.qa_engine import Answer, QAEngine


class SmartAdvisor:
    """智能顾问主类

    整合各种顾问能力，提供统一的接口。

    功能：
    - 智能问答：回答项目相关问题
    - 代码审查建议：生成代码改进建议（待实现）
    - 架构决策辅助：提供架构设计建议（待实现）
    - 最佳实践推荐：推荐相关的规则和方法论（待实现）

    示例：
        advisor = SmartAdvisor()
        answer = advisor.ask("这个项目有哪些模块？")
        print(answer.text)
    """

    def __init__(self, project_dir: Optional[str] = None):
        """初始化智能顾问

        Args:
            project_dir: 项目目录路径，默认为当前目录
        """
        self.project_dir = Path(project_dir or ".")
        self._qa_engine: Optional[QAEngine] = None

    @property
    def qa_engine(self) -> QAEngine:
        """懒加载问答引擎"""
        if self._qa_engine is None:
            self._qa_engine = QAEngine(str(self.project_dir))
        return self._qa_engine

    def ask(self, question: str) -> Answer:
        """智能问答

        回答项目相关问题。

        Args:
            question: 问题文本

        Returns:
            答案对象，包含答案文本、置信度、来源等信息
        """
        return self.qa_engine.answer(question)

    def get_suggestions(self, question: str) -> List[str]:
        """获取问题的相关建议

        Args:
            question: 问题文本

        Returns:
            相关建议列表
        """
        answer = self.ask(question)
        suggestions = []

        # 添加相关知识作为建议
        for knowledge in answer.related_knowledge:
            suggestions.append(f"相关知识: {knowledge}")

        # 添加来源作为参考
        for source in answer.sources:
            suggestions.append(f"参考来源: {source}")

        return suggestions
