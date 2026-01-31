# -*- coding: utf-8 -*-
# mypy: disable-error-code="union-attr"
"""智能顾问工具

将智能顾问能力暴露给Agent使用，支持智能问答、代码审查、架构决策、最佳实践推荐。
"""

from typing import Any, Dict, Optional


class smart_advisor_tool:
    """智能顾问工具"""

    name = "smart_advisor_tool"
    description = """智能顾问工具，提供智能问答、代码审查、架构决策、最佳实践推荐。"""

    parameters = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "ask",
                    "review_code",
                    "architecture_advice",
                    "recommend_practice",
                ],
                "description": "操作类型",
            },
            "question": {"type": "string", "description": "问题内容"},
            "code": {"type": "string", "description": "要审查的代码"},
            "file_path": {"type": "string", "description": "代码文件路径"},
            "context": {"type": "string", "description": "决策上下文"},
            "task_context": {"type": "string", "description": "任务上下文"},
            "category": {"type": "string", "description": "实践类别"},
        },
        "required": ["operation"],
    }

    def __init__(self) -> None:
        self._qa_engine: Optional[Any] = None
        self._review_advisor: Optional[Any] = None
        self._arch_advisor: Optional[Any] = None
        self._practice_advisor: Optional[Any] = None

    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行智能顾问操作"""
        operation = kwargs.get("operation")
        if operation == "ask":
            return self._handle_ask(kwargs)
        elif operation == "review_code":
            return self._handle_review_code(kwargs)
        elif operation == "architecture_advice":
            return self._handle_architecture_advice(kwargs)
        elif operation == "recommend_practice":
            return self._handle_recommend_practice(kwargs)
        return {"success": False, "error": f"未知操作: {operation}"}

    def _handle_ask(self, kwargs: Dict) -> Dict[str, Any]:
        question = kwargs.get("question")
        if not question:
            return {"success": False, "error": "问题不能为空"}
        try:
            from jarvis.jarvis_smart_advisor import QAEngine

            if self._qa_engine is None:
                self._qa_engine = QAEngine()
            qa = self._qa_engine
            answer = qa.answer(question)
            return {
                "success": True,
                "answer": answer.answer,
                "confidence": answer.confidence,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_review_code(self, kwargs: Dict) -> Dict[str, Any]:
        code = kwargs.get("code")
        if not code:
            return {"success": False, "error": "代码不能为空"}
        try:
            from jarvis.jarvis_smart_advisor import ReviewAdvisor

            if self._review_advisor is None:
                self._review_advisor = ReviewAdvisor()
            reviewer = self._review_advisor
            result = reviewer.review(code, kwargs.get("file_path", "unknown.py"))
            return {
                "success": True,
                "summary": result.summary,
                "score": result.overall_score,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_architecture_advice(self, kwargs: Dict) -> Dict[str, Any]:
        context = kwargs.get("context")
        if not context:
            return {"success": False, "error": "决策上下文不能为空"}
        try:
            from jarvis.jarvis_smart_advisor import ArchitectureAdvisor

            if self._arch_advisor is None:
                self._arch_advisor = ArchitectureAdvisor()
            advisor = self._arch_advisor
            result = advisor.advise(context)
            return {"success": True, "summary": result.summary}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_recommend_practice(self, kwargs: Dict) -> Dict[str, Any]:
        task_context = kwargs.get("task_context")
        if not task_context:
            return {"success": False, "error": "任务上下文不能为空"}
        try:
            from jarvis.jarvis_smart_advisor import PracticeAdvisor

            if self._practice_advisor is None:
                self._practice_advisor = PracticeAdvisor()
            practice = self._practice_advisor
            result = practice.recommend(task_context, kwargs.get("category"))
            return {"success": True, "summary": result.summary}
        except Exception as e:
            return {"success": False, "error": str(e)}
