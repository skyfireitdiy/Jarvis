# -*- coding: utf-8 -*-
"""lint.py 单元测试"""
import os
import tempfile
from unittest.mock import patch, mock_open, MagicMock
import pytest
import yaml

from jarvis.jarvis_code_agent.lint import (
    load_lint_tools_config,
    get_lint_tools,
    LINT_TOOLS
)


class TestLintTools:
    """lint工具相关功能的测试"""
    
    def test_lint_tools_default_config(self):
        """测试默认的lint工具配置"""
        # 验证一些常见文件类型的配置
        assert ".py" in LINT_TOOLS
        assert "black" in LINT_TOOLS[".py"]
        assert "pylint" in LINT_TOOLS[".py"]
        assert "mypy" in LINT_TOOLS[".py"]
        
        assert ".js" in LINT_TOOLS
        assert "eslint" in LINT_TOOLS[".js"]
        
        assert ".go" in LINT_TOOLS
        assert "go vet" in LINT_TOOLS[".go"]
        
        assert "dockerfile" in LINT_TOOLS
        assert "hadolint" in LINT_TOOLS["dockerfile"]
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    def test_load_lint_tools_config_with_file(self, mock_yaml_load, mock_file, mock_exists):
        """测试从yaml文件加载配置"""
        mock_exists.return_value = True
        mock_yaml_load.return_value = {
            ".custom": ["custom-linter"],
            ".PY": ["additional-python-linter"],  # 测试大写转小写
            ".new": ["new-linter1", "new-linter2"]
        }
        
        result = load_lint_tools_config()
        
        # 验证结果
        assert result[".custom"] == ["custom-linter"]
        assert result[".py"] == ["additional-python-linter"]  # 应该转为小写
        assert result[".new"] == ["new-linter1", "new-linter2"]
        assert ".PY" not in result  # 大写版本不应存在
    
    @patch('os.path.exists')
    def test_load_lint_tools_config_no_file(self, mock_exists):
        """测试配置文件不存在的情况"""
        mock_exists.return_value = False
        
        result = load_lint_tools_config()
        
        assert result == {}
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    def test_load_lint_tools_config_empty_file(self, mock_yaml_load, mock_file, mock_exists):
        """测试空配置文件的情况"""
        mock_exists.return_value = True
        mock_yaml_load.return_value = None
        
        result = load_lint_tools_config()
        
        assert result == {}
    
    def test_get_lint_tools_by_extension(self):
        """测试通过文件扩展名获取lint工具"""
        # Python文件
        assert get_lint_tools("test.py") == ["black", "pylint", "mypy"]
        assert get_lint_tools("/path/to/file.py") == ["black", "pylint", "mypy"]
        assert get_lint_tools("file.PY") == ["black", "pylint", "mypy"]  # 测试大写扩展名
        
        # JavaScript文件
        assert get_lint_tools("app.js") == ["eslint"]
        assert get_lint_tools("./src/index.js") == ["eslint"]
        
        # Go文件
        assert get_lint_tools("main.go") == ["go vet"]
        
        # 未知扩展名
        assert get_lint_tools("unknown.xyz") == []
    
    def test_get_lint_tools_by_filename(self):
        """测试通过文件名获取lint工具"""
        # Dockerfile
        assert get_lint_tools("dockerfile") == ["hadolint"]
        assert get_lint_tools("Dockerfile") == ["hadolint"]  # 测试大小写
        assert get_lint_tools("/path/to/dockerfile") == ["hadolint"]
        
        # Makefile
        assert get_lint_tools("makefile") == ["checkmake"]
        assert get_lint_tools("Makefile") == ["checkmake"]
        
        # docker-compose文件
        assert get_lint_tools("docker-compose.yml") == ["hadolint"]
        assert get_lint_tools("docker-compose.yaml") == ["hadolint"]
    
    def test_get_lint_tools_priority(self):
        """测试文件名优先于扩展名的规则"""
        # 如果有同名文件在配置中，应该优先使用文件名匹配
        # 例如 .eslintrc 应该匹配到 eslint，而不是根据扩展名匹配
        assert get_lint_tools(".eslintrc") == ["eslint"]
        assert get_lint_tools(".prettierrc") == ["prettier"]
    
    def test_get_lint_tools_with_path(self):
        """测试带路径的文件名"""
        # 应该只使用基础文件名进行匹配
        assert get_lint_tools("/home/user/project/test.py") == ["black", "pylint", "mypy"]
        assert get_lint_tools("../src/main.go") == ["go vet"]
        assert get_lint_tools("/var/lib/docker/dockerfile") == ["hadolint"]
    
    def test_get_lint_tools_special_cases(self):
        """测试特殊情况"""
        # 没有扩展名的文件
        assert get_lint_tools("README") == []
        
        # 多个点的文件名
        assert get_lint_tools("test.spec.js") == ["eslint"]
        assert get_lint_tools("app.test.py") == ["black", "pylint", "mypy"]
        
        # 隐藏文件
        assert get_lint_tools(".bashrc") == ["shellcheck"]
        assert get_lint_tools(".gitignore") == ["git-lint"]
    
    @patch('jarvis.jarvis_code_agent.lint.get_data_dir')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    @patch('yaml.safe_load')
    def test_config_merge(self, mock_yaml_load, mock_file, mock_exists, mock_get_data_dir):
        """测试配置合并功能"""
        # 设置mock返回值
        mock_get_data_dir.return_value = "/mock/data/dir"
        mock_exists.return_value = True
        mock_yaml_load.return_value = {
            ".py": ["additional-linter"],  # 应该更新现有配置
            ".custom": ["custom-linter"]    # 应该添加新配置
        }
        
        # 由于LINT_TOOLS在模块导入时就已经初始化，我们直接测试load_lint_tools_config的返回值
        # 以及get_lint_tools的行为
        config = load_lint_tools_config()
        
        # 验证配置加载正确
        assert config[".py"] == ["additional-linter"]
        assert config[".custom"] == ["custom-linter"]
        
        # 创建一个新的LINT_TOOLS字典来模拟合并后的效果
        test_lint_tools = LINT_TOOLS.copy()
        test_lint_tools.update(config)
        
        # 验证合并后的效果
        assert test_lint_tools[".py"] == ["additional-linter"]  # 被覆盖
        assert test_lint_tools[".custom"] == ["custom-linter"]  # 新增
        assert test_lint_tools[".js"] == ["eslint"]  # 保持不变
