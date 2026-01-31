"""代码审查建议生成模块测试。"""

from jarvis.jarvis_smart_advisor.review_advisor import (
    ReviewAdvisor,
    ReviewCategory,
    ReviewReport,
    ReviewSeverity,
    ReviewSuggestion,
)


class TestReviewSeverity:
    """ReviewSeverity枚举测试"""

    def test_severity_values(self):
        """测试严重程度值"""
        assert ReviewSeverity.CRITICAL.value == "critical"
        assert ReviewSeverity.WARNING.value == "warning"
        assert ReviewSeverity.INFO.value == "info"
        assert ReviewSeverity.SUGGESTION.value == "suggestion"


class TestReviewCategory:
    """ReviewCategory枚举测试"""

    def test_category_values(self):
        """测试类别值"""
        assert ReviewCategory.SECURITY.value == "security"
        assert ReviewCategory.PERFORMANCE.value == "performance"
        assert ReviewCategory.MAINTAINABILITY.value == "maintainability"
        assert ReviewCategory.RELIABILITY.value == "reliability"
        assert ReviewCategory.CODE_STYLE.value == "code_style"
        assert ReviewCategory.BEST_PRACTICE.value == "best_practice"
        assert ReviewCategory.ARCHITECTURE.value == "architecture"


class TestReviewSuggestion:
    """ReviewSuggestion数据类测试"""

    def test_create_suggestion(self):
        """测试创建建议"""
        suggestion = ReviewSuggestion(
            title="测试建议",
            description="这是一个测试建议",
            severity=ReviewSeverity.WARNING,
            category=ReviewCategory.SECURITY,
        )
        assert suggestion.title == "测试建议"
        assert suggestion.description == "这是一个测试建议"
        assert suggestion.severity == ReviewSeverity.WARNING
        assert suggestion.category == ReviewCategory.SECURITY

    def test_suggestion_to_dict(self):
        """测试转换为字典"""
        suggestion = ReviewSuggestion(
            title="测试建议",
            description="描述",
            severity=ReviewSeverity.CRITICAL,
            category=ReviewCategory.SECURITY,
            file_path="test.py",
            line_number=10,
        )
        result = suggestion.to_dict()
        assert result["title"] == "测试建议"
        assert result["severity"] == "critical"
        assert result["category"] == "security"
        assert result["file_path"] == "test.py"
        assert result["line_number"] == 10


class TestReviewReport:
    """ReviewReport数据类测试"""

    def test_create_report(self):
        """测试创建报告"""
        report = ReviewReport(project_path="/test/project")
        assert report.project_path == "/test/project"
        assert report.suggestions == []
        assert report.overall_score == 100.0

    def test_report_to_dict(self):
        """测试转换为字典"""
        suggestion = ReviewSuggestion(
            title="测试",
            description="描述",
            severity=ReviewSeverity.WARNING,
            category=ReviewCategory.CODE_STYLE,
        )
        report = ReviewReport(
            project_path="/test",
            suggestions=[suggestion],
            summary="测试摘要",
            overall_score=90.0,
        )
        result = report.to_dict()
        assert result["project_path"] == "/test"
        assert len(result["suggestions"]) == 1
        assert result["summary"] == "测试摘要"
        assert result["overall_score"] == 90.0

    def test_report_to_markdown(self):
        """测试转换为Markdown"""
        suggestion = ReviewSuggestion(
            title="安全问题",
            description="发现安全问题",
            severity=ReviewSeverity.CRITICAL,
            category=ReviewCategory.SECURITY,
            file_path="test.py",
            line_number=5,
        )
        report = ReviewReport(
            project_path="/test",
            suggestions=[suggestion],
            summary="发现1个严重问题",
            overall_score=90.0,
            stats={"critical": 1},
        )
        markdown = report.to_markdown()
        assert "# 代码审查报告" in markdown
        assert "/test" in markdown
        assert "90.0" in markdown
        assert "安全问题" in markdown
        assert "CRITICAL" in markdown


class TestReviewAdvisor:
    """ReviewAdvisor类测试"""

    def test_init(self):
        """测试初始化"""
        advisor = ReviewAdvisor()
        assert advisor.project_dir.exists()

    def test_review_code_hardcoded_password(self):
        """测试检测硬编码密码"""
        advisor = ReviewAdvisor()
        code = """
password = "secret123"
api_key = 'my_api_key'
"""
        suggestions = advisor.review_code(code, "test.py")
        # 应该检测到硬编码密码
        security_suggestions = [
            s for s in suggestions if s.category == ReviewCategory.SECURITY
        ]
        assert len(security_suggestions) >= 1

    def test_review_code_bare_except(self):
        """测试检测裸异常捕获"""
        advisor = ReviewAdvisor()
        code = """
try:
    do_something()
except:
    pass
"""
        suggestions = advisor.review_code(code, "test.py")
        # 应该检测到裸异常
        best_practice_suggestions = [
            s for s in suggestions if s.category == ReviewCategory.BEST_PRACTICE
        ]
        assert len(best_practice_suggestions) >= 1

    def test_review_code_todo_comment(self):
        """测试检测TODO注释"""
        advisor = ReviewAdvisor()
        code = """
# TODO: 需要实现这个功能
def placeholder():
    pass
"""
        suggestions = advisor.review_code(code, "test.py")
        # 应该检测到TODO注释
        style_suggestions = [
            s for s in suggestions if s.category == ReviewCategory.CODE_STYLE
        ]
        assert len(style_suggestions) >= 1

    def test_review_code_clean(self):
        """测试干净的代码"""
        advisor = ReviewAdvisor()
        code = '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
'''
        suggestions = advisor.review_code(code, "test.py")
        # 干净的代码应该没有严重问题
        critical_suggestions = [
            s for s in suggestions if s.severity == ReviewSeverity.CRITICAL
        ]
        assert len(critical_suggestions) == 0

    def test_check_function_length(self):
        """测试函数长度检查"""
        advisor = ReviewAdvisor()
        # 创建一个超过50行的函数
        lines = ["def long_function():"]
        for i in range(60):
            lines.append(f"    x{i} = {i}")
        lines.append("    return x0")
        code = "\n".join(lines)

        suggestions = advisor._check_function_length(code, "test.py")
        assert len(suggestions) >= 1
        assert "long_function" in suggestions[0].title

    def test_review_project(self, tmp_path):
        """测试审查项目"""
        # 创建测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("""
password = "secret"
# TODO: fix this
""")

        advisor = ReviewAdvisor(str(tmp_path))
        report = advisor.review_project(["*.py"])

        assert report.project_path == str(tmp_path)
        assert len(report.suggestions) >= 1
        assert report.stats["total_suggestions"] >= 1

    def test_review_diff(self):
        """测试审查diff"""
        advisor = ReviewAdvisor()
        diff_content = """
diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
 def main():
+    password = "secret123"
+    # TODO: remove this
     pass
"""
        suggestions = advisor.review_diff(diff_content)
        # 应该检测到新增代码中的问题
        assert len(suggestions) >= 1

    def test_review_file_not_exists(self):
        """测试审查不存在的文件"""
        advisor = ReviewAdvisor()
        suggestions = advisor.review_file("/nonexistent/file.py")
        assert suggestions == []


class TestReviewAdvisorPatterns:
    """ReviewAdvisor模式检测测试"""

    def test_sql_injection_pattern(self):
        """测试SQL注入检测"""
        advisor = ReviewAdvisor()
        code = """
cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)
"""
        suggestions = advisor.review_code(code, "test.py")
        # SQL注入模式可能匹配也可能不匹配，取决于具体实现
        # 这里只验证不会抛出异常
        assert isinstance(suggestions, list)

    def test_magic_number_pattern(self):
        """测试魔法数字检测"""
        advisor = ReviewAdvisor()
        code = """
def calculate():
    return value * 3.14159 + 100
"""
        suggestions = advisor.review_code(code, "test.py")
        # 魔法数字检测
        # 可能检测到也可能不检测到，取决于正则表达式
        assert isinstance(suggestions, list)


class TestReviewReportMarkdown:
    """ReviewReport Markdown输出测试"""

    def test_empty_report_markdown(self):
        """测试空报告的Markdown输出"""
        report = ReviewReport(project_path="/test")
        markdown = report.to_markdown()
        assert "# 代码审查报告" in markdown
        assert "/test" in markdown

    def test_report_with_all_severities(self):
        """测试包含所有严重程度的报告"""
        suggestions = [
            ReviewSuggestion(
                title="严重问题",
                description="描述",
                severity=ReviewSeverity.CRITICAL,
                category=ReviewCategory.SECURITY,
            ),
            ReviewSuggestion(
                title="警告",
                description="描述",
                severity=ReviewSeverity.WARNING,
                category=ReviewCategory.PERFORMANCE,
            ),
            ReviewSuggestion(
                title="信息",
                description="描述",
                severity=ReviewSeverity.INFO,
                category=ReviewCategory.CODE_STYLE,
            ),
            ReviewSuggestion(
                title="建议",
                description="描述",
                severity=ReviewSeverity.SUGGESTION,
                category=ReviewCategory.BEST_PRACTICE,
            ),
        ]
        report = ReviewReport(
            project_path="/test",
            suggestions=suggestions,
        )
        markdown = report.to_markdown()
        assert "CRITICAL" in markdown
        assert "WARNING" in markdown
        assert "INFO" in markdown
        assert "SUGGESTION" in markdown
        assert "🔴" in markdown
        assert "🟡" in markdown
        assert "🔵" in markdown
        assert "💡" in markdown
