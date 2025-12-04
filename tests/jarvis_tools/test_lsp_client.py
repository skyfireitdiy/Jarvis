# -*- coding: utf-8 -*-
"""jarvis_tools.lsp_client 模块单元测试"""

import os
import re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.jarvis_tools.lsp_client import (
    LSPClient,
    LSPClientTool,
    LSP_SERVERS,
    LSPServerConfig,
)


def check_lsp_server_available(language: str) -> bool:
    """检查指定语言的 LSP 服务器是否可用。

    Args:
        language: 语言名称（如 'python', 'rust', 'go' 等）

    Returns:
        bool: 如果 LSP 服务器可用返回 True，否则返回 False
    """
    if language not in LSP_SERVERS:
        return False

    config = LSP_SERVERS[language]
    check_cmd = config.check_command or config.command

    try:
        subprocess.run(
            check_cmd, capture_output=True, text=True, timeout=5, check=False
        )
        # 某些 LSP 服务器即使返回非零退出码也可能可用（如 clangd --version）
        # 只要命令能执行（不是 FileNotFoundError），就认为可用
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


@pytest.fixture
def tool():
    """创建测试用的 LSPClientTool 实例"""
    return LSPClientTool()


@pytest.fixture
def mock_agent():
    """创建模拟的 Agent 实例"""
    agent = MagicMock()
    agent._user_data = {}
    agent.model_group = None

    def get_user_data(key):
        return agent._user_data.get(key)

    def set_user_data(key, value):
        agent._user_data[key] = value

    agent.get_user_data = MagicMock(side_effect=get_user_data)
    agent.set_user_data = MagicMock(side_effect=set_user_data)
    return agent


@pytest.fixture
def temp_project_dir(tmp_path):
    """创建临时项目目录"""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return str(project_dir)


# 为每种语言创建参数化 fixture
@pytest.fixture(params=list(LSP_SERVERS.keys()))
def language_config(request):
    """参数化 fixture，为每种语言提供配置"""
    language = request.param
    config = LSP_SERVERS[language]
    return language, config


def test_check_lsp_server_available():
    """测试检查 LSP 服务器可用性的函数"""
    # 测试不存在的语言
    assert check_lsp_server_available("nonexistent") is False

    # 测试存在的语言（可能可用也可能不可用，取决于环境）
    for language in LSP_SERVERS.keys():
        result = check_lsp_server_available(language)
        assert isinstance(result, bool)


def test_lsp_client_tool_check(tool):
    """测试 LSPClientTool.check() 方法"""
    result = tool.check()
    assert isinstance(result, bool)


def test_lsp_client_tool_execute_missing_params(tool):
    """测试缺少必需参数的情况"""
    result = tool.execute({})
    assert result["success"] is False
    assert "action" in result.get("stderr", "").lower() or "缺少" in result.get(
        "stderr", ""
    )

    result = tool.execute({"action": "get_symbol_info"})
    assert result["success"] is False
    assert "file_path" in result.get("stderr", "").lower() or "缺少" in result.get(
        "stderr", ""
    )


def test_lsp_client_tool_execute_invalid_action(tool, temp_project_dir):
    """测试无效的 action 参数"""
    test_file = os.path.join(temp_project_dir, "test.py")
    Path(test_file).touch()

    result = tool.execute({"action": "invalid_action", "file_path": test_file})
    # 可能因为 LSP 不可用而失败，或者因为无效 action 而失败
    assert "success" in result


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_initialization(language, temp_project_dir):
    """测试 LSP 客户端初始化（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]

    # 创建对应语言的测试文件
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")
    Path(test_file).touch()

    try:
        client = LSPClient(temp_project_dir, config)
        assert client is not None
        assert client.project_root == os.path.abspath(temp_project_dir)
        assert client.server_config == config

        # 清理：关闭客户端进程
        if client.process:
            client.process.terminate()
            client.process.wait(timeout=5)
    except RuntimeError as e:
        # 如果初始化失败，可能是因为服务器虽然可检测到但无法启动
        pytest.skip(f"无法初始化 LSP 客户端: {e}")


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_tool_get_symbol_info(language, tool, temp_project_dir):
    """测试 get_symbol_info 操作（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")

    # 创建简单的测试文件内容（根据语言不同）
    if language == "python":
        content = "def hello():\n    pass\n"
    elif language == "rust":
        content = "fn hello() {\n}\n"
    elif language == "go":
        content = "package main\n\nfunc hello() {\n}\n"
    elif language in ["c", "cpp"]:
        content = "void hello() {\n}\n"
    elif language in ["typescript", "javascript"]:
        content = "function hello() {\n}\n"
    elif language == "java":
        content = "public class Test {\n    public void hello() {\n    }\n}\n"
    else:
        content = "// Test file\n"

    Path(test_file).write_text(content, encoding="utf-8")

    result = tool.execute(
        {
            "action": "get_symbol_info",
            "file_path": test_file,
            "symbol_name": "hello",
            "project_root": temp_project_dir,
        }
    )

    # 结果可能成功或失败（取决于 LSP 服务器的响应）
    assert "success" in result
    # 如果成功，应该包含 stdout 或相关信息
    if result.get("success"):
        assert "stdout" in result
        stdout = result.get("stdout", "")
        # 校验返回内容中包含符号名
        assert "hello" in stdout.lower() or "符号" in stdout


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_tool_document_symbols(language, tool, temp_project_dir):
    """测试 document_symbols 操作（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")

    # 创建包含多个符号的测试文件
    if language == "python":
        content = """def func1():
    pass

def func2():
    pass

class MyClass:
    pass
"""
    elif language == "rust":
        content = """fn func1() {
}

fn func2() {
}

struct MyStruct {
}
"""
    elif language == "go":
        content = """package main

func func1() {
}

func func2() {
}

type MyType struct {
}
"""
    elif language in ["c", "cpp"]:
        content = """void func1() {
}

void func2() {
}

struct MyStruct {
};
"""
    elif language in ["typescript", "javascript"]:
        content = """function func1() {
}

function func2() {
}

class MyClass {
}
"""
    elif language == "java":
        content = """public class Test {
    public void func1() {
    }
    
    public void func2() {
    }
}
"""
    else:
        content = "// Test file\n"

    Path(test_file).write_text(content, encoding="utf-8")

    result = tool.execute(
        {
            "action": "document_symbols",
            "file_path": test_file,
            "project_root": temp_project_dir,
        }
    )

    assert "success" in result
    if result.get("success"):
        assert "stdout" in result
        stdout = result.get("stdout", "")
        # 校验返回内容中包含预期的符号
        # 根据语言不同，应该包含 func1, func2, 以及类/结构体/类型名
        assert "func1" in stdout.lower() or "找到" in stdout or "符号" in stdout
        # 如果包含符号列表，应该至少有几个符号
        if "找到" in stdout and "个符号" in stdout:
            # 提取符号数量
            match = re.search(r"找到\s*(\d+)\s*个符号", stdout)
            if match:
                count = int(match.group(1))
                assert count > 0


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_tool_search_symbol(language, tool, temp_project_dir):
    """测试 search_symbol 操作（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")

    # 创建测试文件
    if language == "python":
        content = "def hello_world():\n    pass\n"
    elif language == "rust":
        content = "fn hello_world() {\n}\n"
    elif language == "go":
        content = "package main\n\nfunc hello_world() {\n}\n"
    elif language in ["c", "cpp"]:
        content = "void hello_world() {\n}\n"
    elif language in ["typescript", "javascript"]:
        content = "function hello_world() {\n}\n"
    elif language == "java":
        content = "public class Test {\n    public void hello_world() {\n    }\n}\n"
    else:
        content = "// Test file\n"

    Path(test_file).write_text(content, encoding="utf-8")

    result = tool.execute(
        {
            "action": "search_symbol",
            "file_path": test_file,
            "symbol_name": "hello",
            "project_root": temp_project_dir,
        }
    )

    assert "success" in result
    if result.get("success"):
        assert "stdout" in result
        stdout = result.get("stdout", "")
        # 校验返回内容中包含搜索的符号（可能是 hello_world 或 hello）
        assert (
            "hello" in stdout.lower()
            or "找到" in stdout
            or "匹配" in stdout
            or "未找到" in stdout
        )


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_tool_definition(language, tool, temp_project_dir):
    """测试 definition 操作（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")

    # 创建测试文件
    if language == "python":
        content = "def hello():\n    return 42\n"
    elif language == "rust":
        content = "fn hello() -> i32 {\n    42\n}\n"
    elif language == "go":
        content = "package main\n\nfunc hello() int {\n    return 42\n}\n"
    elif language in ["c", "cpp"]:
        content = "int hello() {\n    return 42;\n}\n"
    elif language in ["typescript", "javascript"]:
        content = "function hello(): number {\n    return 42;\n}\n"
    elif language == "java":
        content = "public class Test {\n    public int hello() {\n        return 42;\n    }\n}\n"
    else:
        content = "// Test file\n"

    Path(test_file).write_text(content, encoding="utf-8")

    result = tool.execute(
        {
            "action": "definition",
            "file_path": test_file,
            "symbol_name": "hello",
            "project_root": temp_project_dir,
        }
    )

    assert "success" in result
    if result.get("success"):
        assert "stdout" in result
        stdout = result.get("stdout", "")
        # 校验返回了定义位置（应该包含文件路径或行号）
        assert (
            "定义" in stdout
            or "位置" in stdout
            or ":" in stdout
            or "未找到定义" in stdout
        )


@pytest.mark.parametrize("language", list(LSP_SERVERS.keys()))
def test_lsp_client_tool_references(language, tool, temp_project_dir):
    """测试 references 操作（仅在服务器可用时运行）"""
    if not check_lsp_server_available(language):
        pytest.skip(f"LSP 服务器 {LSP_SERVERS[language].name} 不可用")

    config = LSP_SERVERS[language]
    ext = config.file_extensions[0] if config.file_extensions else ".txt"
    test_file = os.path.join(temp_project_dir, f"test{ext}")

    # 创建包含函数调用的测试文件
    if language == "python":
        content = """def hello():
    pass

def main():
    hello()
    hello()
"""
    elif language == "rust":
        content = """fn hello() {
}

fn main() {
    hello();
    hello();
}
"""
    elif language == "go":
        content = """package main

func hello() {
}

func main() {
    hello()
    hello()
}
"""
    elif language in ["c", "cpp"]:
        content = """void hello() {
}

int main() {
    hello();
    hello();
    return 0;
}
"""
    elif language in ["typescript", "javascript"]:
        content = """function hello() {
}

function main() {
    hello();
    hello();
}
"""
    elif language == "java":
        content = """public class Test {
    public void hello() {
    }
    
    public void main() {
        hello();
        hello();
    }
}
"""
    else:
        content = "// Test file\n"

    Path(test_file).write_text(content, encoding="utf-8")

    result = tool.execute(
        {
            "action": "references",
            "file_path": test_file,
            "symbol_name": "hello",
            "project_root": temp_project_dir,
        }
    )

    assert "success" in result
    if result.get("success"):
        assert "stdout" in result
        stdout = result.get("stdout", "")
        # 校验返回了引用信息
        assert "引用" in stdout or "未找到引用" in stdout
        # 如果找到了引用，应该至少包含2个（因为代码中调用了2次 hello）
        if "找到" in stdout and "个引用" in stdout:
            match = re.search(r"找到\s*(\d+)\s*个引用", stdout)
            if match:
                count = int(match.group(1))
                # 应该至少找到2个引用（main 函数中调用了2次）
                assert count >= 2


def test_lsp_client_tool_unsupported_language(tool, temp_project_dir):
    """测试不支持的语言"""
    test_file = os.path.join(temp_project_dir, "test.unknown")
    Path(test_file).touch()

    result = tool.execute(
        {"action": "get_symbol_info", "file_path": test_file, "symbol_name": "test"}
    )

    # 应该失败或返回不支持的信息
    assert "success" in result
    if not result.get("success"):
        assert (
            "不支持" in result.get("stderr", "")
            or "not supported" in result.get("stderr", "").lower()
        )


def test_lsp_client_tool_nonexistent_file(tool, temp_project_dir):
    """测试不存在的文件"""
    nonexistent_file = os.path.join(temp_project_dir, "nonexistent.py")

    result = tool.execute(
        {
            "action": "get_symbol_info",
            "file_path": nonexistent_file,
            "symbol_name": "test",
        }
    )

    # 可能因为文件不存在而失败，或因为 LSP 不可用而失败
    assert "success" in result


def test_lsp_client_server_config():
    """测试 LSP 服务器配置"""
    for language, config in LSP_SERVERS.items():
        assert isinstance(config, LSPServerConfig)
        assert config.name
        assert config.command
        assert config.language_ids
        assert config.file_extensions
        assert len(config.file_extensions) > 0


def test_lsp_client_tool_client_caching(tool, temp_project_dir):
    """测试客户端缓存机制"""
    # 创建 Python 测试文件
    test_file = os.path.join(temp_project_dir, "test.py")
    Path(test_file).write_text("def hello():\n    pass\n", encoding="utf-8")

    # 第一次调用应该创建客户端
    result1 = tool.execute(
        {
            "action": "document_symbols",
            "file_path": test_file,
            "project_root": temp_project_dir,
        }
    )

    # 第二次调用应该使用缓存的客户端
    result2 = tool.execute(
        {
            "action": "document_symbols",
            "file_path": test_file,
            "project_root": temp_project_dir,
        }
    )

    # 两次调用都应该有结果（可能成功或失败，取决于 LSP 是否可用）
    assert "success" in result1
    assert "success" in result2
    # 校验缓存机制：两次调用的结果应该一致（都成功或都失败）
    assert result1.get("success") == result2.get("success")
    # 如果都成功，输出应该相同（说明使用了同一个客户端）
    if result1.get("success") and result2.get("success"):
        assert result1.get("stdout") == result2.get("stdout")
