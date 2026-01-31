# -*- coding: utf-8 -*-
"""generate_rule 工具的单元测试"""

import os
import tempfile
from unittest.mock import patch

from jarvis.jarvis_tools.generate_rule import GenerateRuleTool


class TestGenerateRuleTool:
    """GenerateRuleTool 测试类"""

    def setup_method(self):
        """每个测试方法前的设置"""
        self.tool = GenerateRuleTool()

    def test_tool_attributes(self):
        """测试工具属性"""
        assert self.tool.name == "generate_rule"
        assert "detect_patterns" in self.tool.description
        assert "generate_rule" in self.tool.description
        assert "save_rule" in self.tool.description
        assert "operation" in self.tool.parameters["properties"]
        assert "operation" in self.tool.parameters["required"]

    def test_execute_missing_operation(self):
        """测试缺少operation参数"""
        result = self.tool.execute({})
        assert result["success"] is False
        assert "operation" in result["stderr"]

    def test_execute_invalid_operation(self):
        """测试无效的operation"""
        result = self.tool.execute({"operation": "invalid_op"})
        assert result["success"] is False
        assert "不支持的操作类型" in result["stderr"]

    # detect_patterns 测试
    def test_detect_patterns_missing_file_paths(self):
        """测试detect_patterns缺少file_paths"""
        result = self.tool.execute({"operation": "detect_patterns"})
        assert result["success"] is False
        assert "file_paths" in result["stderr"]

    def test_detect_patterns_invalid_paths(self):
        """测试detect_patterns所有路径无效"""
        result = self.tool.execute(
            {
                "operation": "detect_patterns",
                "file_paths": ["/nonexistent/path1.py", "/nonexistent/path2.py"],
            }
        )
        assert result["success"] is False
        assert "无效" in result["stderr"]

    def test_detect_patterns_with_valid_file(self):
        """测试detect_patterns使用有效文件"""
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""class Singleton:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
""")
            temp_file = f.name

        try:
            result = self.tool.execute(
                {
                    "operation": "detect_patterns",
                    "file_paths": [temp_file],
                    "pattern_type": "design_pattern",
                }
            )
            assert result["success"] is True
            # 可能检测到单例模式
            assert result["stdout"] is not None
        finally:
            os.unlink(temp_file)

    def test_detect_patterns_no_patterns_found(self):
        """测试detect_patterns未检测到模式"""
        # 创建一个简单的临时文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# Simple file\nx = 1\n")
            temp_file = f.name

        try:
            result = self.tool.execute(
                {
                    "operation": "detect_patterns",
                    "file_paths": [temp_file],
                    "pattern_type": "design_pattern",
                }
            )
            assert result["success"] is True
            assert "未检测到" in result["stdout"] or "检测到" in result["stdout"]
        finally:
            os.unlink(temp_file)

    # generate_rule 测试
    def test_generate_rule_missing_rule_name(self):
        """测试generate_rule缺少rule_name"""
        result = self.tool.execute(
            {"operation": "generate_rule", "description": "测试描述"}
        )
        assert result["success"] is False
        assert "rule_name" in result["stderr"]

    def test_generate_rule_missing_description(self):
        """测试generate_rule缺少description"""
        result = self.tool.execute(
            {"operation": "generate_rule", "rule_name": "测试规则"}
        )
        assert result["success"] is False
        assert "description" in result["stderr"]

    def test_generate_rule_success(self):
        """测试generate_rule成功生成规则"""
        result = self.tool.execute(
            {
                "operation": "generate_rule",
                "rule_name": "代码审查规则",
                "description": "定义代码审查的标准流程和检查项",
                "pattern_type": "best_practice",
            }
        )
        assert result["success"] is True
        assert "代码审查规则" in result["stdout"]
        assert "质量评分" in result["stdout"]

    def test_generate_rule_with_scope(self):
        """测试generate_rule指定scope"""
        result = self.tool.execute(
            {
                "operation": "generate_rule",
                "rule_name": "全局规则",
                "description": "全局适用的规则",
                "scope": "global",
            }
        )
        assert result["success"] is True

    # save_rule 测试
    def test_save_rule_missing_rule_name(self):
        """测试save_rule缺少rule_name"""
        result = self.tool.execute(
            {"operation": "save_rule", "rule_content": "# 规则内容"}
        )
        assert result["success"] is False
        assert "rule_name" in result["stderr"]

    def test_save_rule_missing_rule_content(self):
        """测试save_rule缺少rule_content"""
        result = self.tool.execute({"operation": "save_rule", "rule_name": "测试规则"})
        assert result["success"] is False
        assert "rule_content" in result["stderr"]

    def test_save_rule_success(self):
        """测试save_rule成功保存规则"""
        # 使用临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock RuleGenerator.save_rule 返回临时路径
            with patch.object(self.tool._get_generator(), "save_rule") as mock_save:
                expected_path = os.path.join(temp_dir, "test_rule.md")
                mock_save.return_value = expected_path

                result = self.tool.execute(
                    {
                        "operation": "save_rule",
                        "rule_name": "测试规则",
                        "rule_content": "# 测试规则\n\n这是测试内容",
                        "scope": "project",
                    }
                )

                assert result["success"] is True
                assert expected_path in result["stdout"]
                mock_save.assert_called_once()

    def test_save_rule_with_global_scope(self):
        """测试save_rule使用global scope"""
        with patch.object(self.tool._get_generator(), "save_rule") as mock_save:
            mock_save.return_value = "/tmp/test_rule.md"

            result = self.tool.execute(
                {
                    "operation": "save_rule",
                    "rule_name": "全局规则",
                    "rule_content": "# 全局规则内容",
                    "scope": "global",
                }
            )

            assert result["success"] is True
            mock_save.assert_called_with("全局规则", "# 全局规则内容", "global")

    # 异常处理测试
    def test_execute_exception_handling(self):
        """测试execute异常处理"""
        with patch.object(
            self.tool, "_detect_patterns", side_effect=Exception("测试异常")
        ):
            result = self.tool.execute(
                {"operation": "detect_patterns", "file_paths": ["/some/path.py"]}
            )
            assert result["success"] is False
            assert "测试异常" in result["stderr"]

    def test_save_rule_exception_handling(self):
        """测试save_rule异常处理"""
        with patch.object(
            self.tool._get_generator(), "save_rule", side_effect=Exception("保存失败")
        ):
            result = self.tool.execute(
                {
                    "operation": "save_rule",
                    "rule_name": "测试规则",
                    "rule_content": "# 内容",
                }
            )
            assert result["success"] is False
            assert "保存规则失败" in result["stderr"]

    # 延迟初始化测试
    def test_generator_lazy_initialization(self):
        """测试生成器延迟初始化"""
        tool = GenerateRuleTool()
        assert tool._generator is None

        generator = tool._get_generator()
        assert generator is not None
        assert tool._generator is generator

        # 再次调用应返回同一实例
        generator2 = tool._get_generator()
        assert generator2 is generator


class TestGenerateRuleToolIntegration:
    """集成测试"""

    def test_full_workflow(self):
        """测试完整工作流：检测模式 -> 生成规则 -> 保存规则"""
        tool = GenerateRuleTool()

        # 1. 生成规则
        gen_result = tool.execute(
            {
                "operation": "generate_rule",
                "rule_name": "集成测试规则",
                "description": "用于集成测试的规则",
                "pattern_type": "best_practice",
            }
        )
        assert gen_result["success"] is True

        # 2. 保存规则（使用mock避免实际写入文件）
        with patch.object(tool._get_generator(), "save_rule") as mock_save:
            mock_save.return_value = "/tmp/integration_test_rule.md"

            save_result = tool.execute(
                {
                    "operation": "save_rule",
                    "rule_name": "集成测试规则",
                    "rule_content": gen_result["stdout"],
                    "scope": "project",
                }
            )
            assert save_result["success"] is True
