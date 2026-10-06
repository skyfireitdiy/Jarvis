# -*- coding: utf-8 -*-
"""hotpatch 工具单元测试

覆盖两种使用方式 + 多模块 + 已有类实例自动切换。
"""

import importlib
import importlib.util
import sys
import types

import pytest

from jarvis.jarvis_tools.hotpatch import HotpatchTool


@pytest.fixture
def tool():
    """创建 HotpatchTool 实例（避免完整初始化）。"""
    return object.__new__(HotpatchTool)


def _load_module(name: str, path) -> types.ModuleType:
    """把模块目录加入 sys.path 并从文件加载模块。

    目录加入 sys.path 后 reload 才能通过 import 系统找到模块
    （与真实 jarvis 模块位于 sys.path 的场景一致）。
    """
    importlib.util.spec_from_file_location  # 确保 importlib.util 已导入
    sys.path.insert(0, str(path.parent))
    module = importlib.import_module(name)
    return module


# ------------------------------------------------------------------
# 方式①：热更新已有模块（reload）
# ------------------------------------------------------------------
def test_reload_module_effective(tool, tmp_path):
    """修改模块文件后 reload，新代码立即生效。"""
    mod_file = tmp_path / "demo_mod.py"
    mod_file.write_text("VALUE = 1\n", encoding="utf-8")

    # 动态加载模块
    module = _load_module("demo_mod", mod_file)
    assert module.VALUE == 1

    # 修改磁盘文件
    mod_file.write_text("VALUE = 42\n", encoding="utf-8")

    # reload 生效
    result = tool._apply_patch("demo_mod", clear_cache=False, rebind_instances=True)
    assert result["success"] is True
    assert "demo_mod" in result["reloaded"]
    assert sys.modules["demo_mod"].VALUE == 42

    sys.modules.pop("demo_mod", None)


def test_reload_batch_multiple_modules(tool, tmp_path):
    """批量多模块 reload，单个失败不影响其他。"""
    mod_a = tmp_path / "batch_a.py"
    mod_b = tmp_path / "batch_b.py"
    mod_a.write_text("A = 1\n", encoding="utf-8")
    mod_b.write_text("B = 1\n", encoding="utf-8")

    for name, path in (("batch_a", mod_a), ("batch_b", mod_b)):
        _load_module(name, path)

    mod_a.write_text("A = 100\n", encoding="utf-8")
    mod_b.write_text("B = 200\n", encoding="utf-8")

    result = tool._apply_patch(
        "batch_a,batch_b", clear_cache=False, rebind_instances=True
    )
    assert result["success"] is True
    assert set(result["reloaded"]) == {"batch_a", "batch_b"}
    assert sys.modules["batch_a"].A == 100
    assert sys.modules["batch_b"].B == 200

    sys.modules.pop("batch_a", None)
    sys.modules.pop("batch_b", None)


def test_reload_rebind_existing_instance(tool, tmp_path):
    """已有类实例自动切换新方法（核心能力）。"""
    mod_file = tmp_path / "demo_cls.py"
    mod_file.write_text(
        "class Greeter:\n    def greet(self):\n        return 'old'\n",
        encoding="utf-8",
    )

    module = _load_module("demo_cls", mod_file)

    inst = module.Greeter()
    assert inst.greet() == "old"

    # 修改类方法
    mod_file.write_text(
        "class Greeter:\n    def greet(self):\n        return 'new'\n",
        encoding="utf-8",
    )

    result = tool._apply_patch("demo_cls", clear_cache=False, rebind_instances=True)
    assert result["success"] is True
    assert result["rebound"] >= 1
    # 旧实例自动切换新方法
    assert inst.greet() == "new"

    sys.modules.pop("demo_cls", None)


def test_reload_rebind_disabled(tool, tmp_path):
    """rebind_instances=False 时不重绑实例。"""
    mod_file = tmp_path / "demo_norebind.py"
    mod_file.write_text(
        "class G:\n    def v(self):\n        return 'old'\n",
        encoding="utf-8",
    )
    module = _load_module("demo_norebind", mod_file)
    inst = module.G()

    mod_file.write_text(
        "class G:\n    def v(self):\n        return 'new'\n",
        encoding="utf-8",
    )
    result = tool._apply_patch(
        "demo_norebind", clear_cache=False, rebind_instances=False
    )
    assert result["success"] is True
    assert result["rebound"] == 0
    # 未重绑，仍用旧类
    assert inst.v() == "old"

    sys.modules.pop("demo_norebind", None)


# ------------------------------------------------------------------
# 方式②：注入全新模块
# ------------------------------------------------------------------
def test_inject_new_module(tool):
    """注入全新模块立即可 import。"""
    result = tool._inject_new_module("my_probe", "def f():\n    return 'probe'\n")
    assert result["success"] is True
    assert "my_probe" in sys.modules
    my_probe = sys.modules["my_probe"]

    assert my_probe.f() == "probe"
    sys.modules.pop("my_probe", None)


# ------------------------------------------------------------------
# 方式②：执行任意语句/代码块
# ------------------------------------------------------------------
def test_execute_statement_access_agent(tool):
    """执行任意语句并访问 agent 上下文。"""

    class FakeAgent:
        data = {"key": "value"}

    agent = FakeAgent()
    result = tool._execute_statement(
        "print(agent.data['key'])",
        {"agent": agent},
    )
    assert result["success"] is True


def test_execute_statement_access_external_object(tool):
    """访问/修改 agent 之外的对象（sys.modules 全局状态）。"""
    # 造一个外部模块
    ext = types.ModuleType("ext_target")
    setattr(ext, "STATE", 0)
    sys.modules["ext_target"] = ext

    result = tool._execute_statement(
        "sys.modules['ext_target'].STATE = 99",
        {"agent": None},
    )
    assert result["success"] is True
    assert sys.modules["ext_target"].STATE == 99
    sys.modules.pop("ext_target", None)


def test_execute_statement_define_function(tool):
    """执行代码块定义函数并注入 hotpatch 模块命名空间。"""
    result = tool._execute_statement(
        "def debug_hook():\n    return 123\n", {"agent": None}
    )
    assert result["success"] is True
    assert "debug_hook" in result["defined"]
    hp_module = sys.modules["jarvis.jarvis_tools.hotpatch"]
    assert hp_module.debug_hook() == 123
    # 清理注入的函数，避免污染
    del hp_module.debug_hook


# ------------------------------------------------------------------
# 异常与参数校验
# ------------------------------------------------------------------
def test_invalid_args_no_throw(tool):
    """无效参数返回错误，不抛异常。"""
    result = tool.execute({})
    assert result["success"] is False
    assert "stderr" in result


def test_inject_new_module_requires_code(tool):
    """new_module_name 无 code 返回错误。"""
    result = tool.execute({"new_module_name": "x"})
    assert result["success"] is False


def test_statement_exception_captured(tool):
    """语句执行异常被捕获，不抛异常。"""
    result = tool._execute_statement("raise ValueError('boom')", {"agent": None})
    assert result["success"] is False
    assert "boom" in result["error"]


def test_reload_does_not_affect_other_modules(tool, tmp_path):
    """reload 不影响其他模块。"""
    mod_a = tmp_path / "iso_a.py"
    mod_b = tmp_path / "iso_b.py"
    mod_a.write_text("A = 1\n", encoding="utf-8")
    mod_b.write_text("B = 1\n", encoding="utf-8")
    for name, path in (("iso_a", mod_a), ("iso_b", mod_b)):
        _load_module(name, path)
    # iso_b 不受影响
    assert sys.modules["iso_b"].B == 1

    sys.modules.pop("iso_a", None)
    sys.modules.pop("iso_b", None)
