"""测试复杂度分析器。"""

from __future__ import annotations

import pytest

from jarvis.jarvis_arch_analyzer.complexity import (
    ComplexityAnalyzer,
    ComplexityReport,
    FunctionComplexity,
)


class TestFunctionComplexity:
    """测试FunctionComplexity数据类。"""

    def test_create_function_complexity(self) -> None:
        """测试创建函数复杂度对象。"""
        func = FunctionComplexity(
            file_path="test.py",
            function_name="test_func",
            line_no=10,
            cyclomatic=5,
            cognitive=3,
            is_high_complexity=False,
        )
        assert func.file_path == "test.py"
        assert func.function_name == "test_func"
        assert func.line_no == 10
        assert func.cyclomatic == 5
        assert func.cognitive == 3
        assert func.is_high_complexity is False

    def test_to_dict(self) -> None:
        """测试转换为字典。"""
        func = FunctionComplexity(
            file_path="test.py",
            function_name="test_func",
            line_no=10,
            cyclomatic=5,
            cognitive=3,
        )
        result = func.to_dict()
        assert result["file_path"] == "test.py"
        assert result["function_name"] == "test_func"
        assert result["line_no"] == 10
        assert result["cyclomatic"] == 5
        assert result["cognitive"] == 3


class TestComplexityAnalyzer:
    """测试ComplexityAnalyzer类。"""

    def test_analyze_simple_function(self) -> None:
        """测试分析简单函数。"""
        code = """
def simple_function(x):
    return x + 1
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        assert functions[0].function_name == "simple_function"
        assert functions[0].cyclomatic == 1  # 基础复杂度

    def test_analyze_if_function(self) -> None:
        """测试分析包含if语句的函数。"""
        code = """
def if_function(x):
    if x > 0:
        return 1
    else:
        return -1
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        assert functions[0].cyclomatic == 2  # 基础1 + if1

    def test_analyze_nested_function(self) -> None:
        """测试分析嵌套控制流的函数。"""
        code = """
def nested_function(x):
    if x > 0:
        for i in range(10):
            if i > 5:
                return i
    return 0
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        assert functions[0].cyclomatic >= 3  # 基础1 + if1 + for1

    def test_analyze_high_complexity(self) -> None:
        """测试高复杂度函数识别。"""
        code = """
def complex_function(x):
    if x > 0:
        if x > 10:
            if x > 100:
                for i in range(10):
                    if i > 5:
                        while i < 20:
                            i += 1
                            if i == 15:
                                return i
                            if i == 18:
                                return i
    return 0
"""
        analyzer = ComplexityAnalyzer(high_complexity_threshold=5)
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        assert functions[0].is_high_complexity is True

    def test_analyze_boolean_operators(self) -> None:
        """测试布尔运算符的复杂度计算。"""
        code = """
def boolean_function(x, y, z):
    if x > 0 and y > 0 and z > 0:
        return True
    return False
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        # 基础1 + if1 + and(2个运算符)
        assert functions[0].cyclomatic >= 2

    def test_analyze_empty_code(self) -> None:
        """测试空代码。"""
        code = """# Empty file
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 0

    def test_analyze_syntax_error(self) -> None:
        """测试语法错误处理。"""
        code = """
def broken_function(
    # Missing closing parenthesis
"""
        analyzer = ComplexityAnalyzer()
        with pytest.raises(ValueError, match="语法错误"):
            analyzer.analyze_code(code)

    def test_generate_report(self) -> None:
        """测试生成复杂度报告。"""
        code = """
def func1(x):
    return x + 1

def func2(x):
    if x > 0:
        return 1
    return -1
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        report = analyzer._generate_report(functions)

        assert isinstance(report, ComplexityReport)
        assert report.total_functions == 2
        assert report.average_cyclomatic > 0
        assert report.max_cyclomatic >= 1

    def test_cognitive_complexity(self) -> None:
        """测试认知复杂度计算。"""
        code = """
def nested_function(x):
    if x > 0:
        if x > 10:
            return 1
    return 0
"""
        analyzer = ComplexityAnalyzer()
        functions = analyzer.analyze_code(code)
        assert len(functions) == 1
        # 认知复杂度应该大于0（嵌套增加了认知负担）
        assert functions[0].cognitive > 0

    def test_analyze_directory(self) -> None:
        """测试分析目录。"""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件（使用非test开头的文件名）
            test_file = Path(tmpdir) / "example_module.py"
            test_file.write_text("""
def example_func(x):
    return x + 1
""")

            analyzer = ComplexityAnalyzer()
            report = analyzer.analyze_directory(tmpdir)

            assert report.total_functions >= 1
            assert report.average_cyclomatic > 0
