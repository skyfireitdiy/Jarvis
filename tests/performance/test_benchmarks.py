# -*- coding: utf-8 -*-
"""性能基准测试"""

import pytest


class TestPerformanceBenchmarks:
    """性能基准测试"""

    @pytest.mark.performance
    def test_import_performance(self, benchmark):
        """测试模块导入性能"""

        def import_jarvis():
            __import__("jarvis")

        benchmark(import_jarvis)

    @pytest.mark.performance
    def test_string_operations_performance(self, benchmark):
        """测试字符串操作性能"""
        test_data = "Hello, Jarvis!" * 100

        def string_split():
            return test_data.split(", ")

        result = benchmark(string_split)
        assert len(result) == 101  # 100个'Jarvis!' + 1个开头的'Hello'
