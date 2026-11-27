# -*- coding: utf-8 -*-
"""测试 builtin_input_handler 中的工具函数"""

from jarvis.jarvis_agent.builtin_input_handler import (
    _detect_file_lang,
    _extract_file_path,
    extract_tags_from_text,
)


class TestExtractTagsFromText:
    """测试 extract_tags_from_text 函数"""

    def test_empty_input(self):
        """测试空输入"""
        assert extract_tags_from_text("") == []
        assert extract_tags_from_text(None) == []

    def test_no_tags(self):
        """测试无标签的纯文本"""
        text = "这是一个普通的用户输入，没有任何标签"
        assert extract_tags_from_text(text) == []

    def test_single_tag(self):
        """测试单个标签"""
        text = "请帮我分析代码 '<rule:python_best_practices>'"
        assert extract_tags_from_text(text) == ["rule:python_best_practices"]

    def test_multiple_tags(self):
        """测试多个标签"""
        text = "'<rule:code_style>' 和 '<rule:security>' 都很重要"
        assert extract_tags_from_text(text) == ["rule:code_style", "rule:security"]

    def test_multimodal_list_format(self):
        """测试多模态内容（列表格式）"""
        content = [
            {"type": "text", "text": "请加载规则 '<rule:test_rule>'"},
            {"type": "image", "url": "http://example.com/image.png"},
        ]
        assert extract_tags_from_text(content) == ["rule:test_rule"]

    def test_multimodal_multiple_text_blocks(self):
        """测试多模态内容中的多个文本块"""
        content = [
            {"type": "text", "text": "'<rule:first>'"},
            {"type": "text", "text": "和 '<rule:second>'"},
        ]
        assert extract_tags_from_text(content) == ["rule:first", "rule:second"]

    def test_multimodal_empty_list(self):
        """测试空列表输入"""
        assert extract_tags_from_text([]) == []

    def test_various_tag_types(self):
        """测试不同类型的标签"""
        text = "'<Pin>' '<SetConfig>' '<rule:custom_rule>' '<AddDir>'"
        assert extract_tags_from_text(text) == [
            "Pin",
            "SetConfig",
            "rule:custom_rule",
            "AddDir",
        ]

    def test_tag_without_quotes(self):
        """测试不带单引号的标签（不应被匹配）"""
        text = "这个 <rule:test> 不会被匹配，因为没有单引号"
        assert extract_tags_from_text(text) == []

    def test_incomplete_tag(self):
        """测试不完整的标签格式"""
        text = "'<rule:incomplete"  # 缺少闭合的 > 和 >'
        assert extract_tags_from_text(text) == []


class TestExtractFilePath:
    """测试 _extract_file_path 函数"""

    def test_sender_prefix_with_quoted_path(self):
        """测试带发送人前缀和引号的绝对路径（Bug 复现场景）"""
        raw = "Administrator：'/home/sky/REVERSA_原理分析报告.md'"
        assert _extract_file_path(raw) == "/home/sky/REVERSA_原理分析报告.md"

    def test_sender_prefix_with_double_quotes(self):
        """测试带发送人前缀和双引号的路径"""
        raw = 'Administrator:"/home/sky/a b.md"'
        assert _extract_file_path(raw) == "/home/sky/a b.md"

    def test_sender_prefix_plain_abs_path(self):
        """测试带发送人前缀的无引号绝对路径"""
        raw = "Administrator：/home/sky/file.md"
        assert _extract_file_path(raw) == "/home/sky/file.md"

    def test_sender_prefix_halfwidth_colon(self):
        """测试半角冒号前缀"""
        raw = "Admin:/home/sky/file.md"
        assert _extract_file_path(raw) == "/home/sky/file.md"

    def test_sender_prefix_home_path(self):
        """测试带前缀的 home 路径"""
        raw = "Administrator：~/file.md"
        assert _extract_file_path(raw) == "~/file.md"

    def test_sender_prefix_relative_path(self):
        """测试带前缀的相对路径"""
        raw = "Administrator：'./rel/file.md'"
        assert _extract_file_path(raw) == "./rel/file.md"

    def test_plain_abs_path_unchanged(self):
        """测试无前缀的绝对路径"""
        raw = "/home/sky/file.md"
        assert _extract_file_path(raw) == "/home/sky/file.md"

    def test_windows_drive_path(self):
        """测试 Windows 盘符路径"""
        raw = "C:\\path\\file.md"
        assert _extract_file_path(raw) == "C:\\path\\file.md"

    def test_empty_input(self):
        """测试空输入"""
        assert _extract_file_path("") == ""
        assert _extract_file_path("   ") == ""

    def test_quoted_path(self):
        """测试引号包裹的路径"""
        raw = "'/home/sky/file.md'"
        assert _extract_file_path(raw) == "/home/sky/file.md"

    def test_path_with_description(self):
        """测试带说明文字的输入"""
        raw = "请查看 /home/sky/file.md 这个文件"
        assert _extract_file_path(raw) == "/home/sky/file.md"


class TestDetectFileLang:
    """测试 _detect_file_lang 函数（<Cat> 自动识别文件语言）"""

    def test_markdown_file(self):
        """markdown 文件识别为 markdown"""
        assert _detect_file_lang("/home/sky/report.md", "# 标题\n\n**加粗**") == "markdown"
        assert _detect_file_lang("/home/sky/README.markdown", "# 标题") == "markdown"

    def test_python_file(self):
        """python 文件识别为 python"""
        assert _detect_file_lang("/home/sky/app.py", 'def hello():\n    print("hi")') == "python"

    def test_common_code_files(self):
        """常见代码文件识别"""
        assert _detect_file_lang("/home/sky/main.go", 'package main\nimport "fmt"') == "go"
        assert _detect_file_lang("/home/sky/script.sh", "#!/bin/bash\necho hi") == "bash"
        assert _detect_file_lang("/home/sky/config.json", '{"name": "test"}') == "json"
        assert _detect_file_lang("/home/sky/data.yaml", "name: test") == "yaml"
        assert _detect_file_lang("/home/sky/app.js", "function hello() {}") == "javascript"
        assert _detect_file_lang("/home/sky/style.css", "body { color: red; }") == "css"
        assert _detect_file_lang("/home/sky/index.html", "<html><body>hi</body></html>") == "html"

    def test_plain_text_file(self):
        """纯文本文件识别为 text"""
        assert _detect_file_lang("/home/sky/notes.txt", "普通文本") == "text"

    def test_unknown_file(self):
        """无法识别的文件返回 None"""
        assert _detect_file_lang("/home/sky/unknown.xyz", "random content") is None

    def test_empty_content(self):
        """空内容也能按文件名识别"""
        assert _detect_file_lang("/home/sky/app.py", "") == "python"


class TestOsNameResolution:
    """回归测试：builtin_input_handler 内的 os 必须是模块级导入。

    历史 Bug：函数体内 OrganizeAgents / Cat 分支各有局部 ``import os``，
    使 ``os`` 成为整个函数的局部变量；先走这些分支再走 SubAgent 分支时，
    ``os.getcwd()`` 抛 UnboundLocalError（cannot access local variable 'os'）。
    """

    def test_os_is_module_level(self):
        """os 在模块级可用，且函数内无局部 os 变量"""
        import dis
        import types

        import importlib

        m = importlib.import_module("jarvis.jarvis_agent.builtin_input_handler")
        assert hasattr(m, "os")
        code = m.builtin_input_handler.__code__
        assert "os" not in code.co_varnames, "os 不应是函数局部变量"
        assert "os" not in code.co_cellvars
        assert "os" not in code.co_freevars

        # 递归检查所有嵌套代码块，除 _get_rule_content（独立函数）外不得有局部 os
        def walk(c):
            yield c
            for const in c.co_consts:
                if isinstance(const, types.CodeType):
                    yield from walk(const)

        for c in walk(code):
            if c.co_name == "_get_rule_content":
                continue
            assert "os" not in c.co_varnames, f"{c.co_name} 存在局部 os"

        # 函数内对 os 的引用必须是 LOAD_GLOBAL
        for ins in dis.get_instructions(code):
            if ins.argval == "os":
                assert ins.opname == "LOAD_GLOBAL", (
                    f"offset {ins.offset} 的 os 引用为 {ins.opname}"
                )

    def test_subagent_branch_uses_global_os(self, monkeypatch, tmp_path):
        """先走 Cat 分支再走 SubAgent 分支，不应抛 UnboundLocalError"""
        import importlib

        m = importlib.import_module("jarvis.jarvis_agent.builtin_input_handler")
        calls = []

        class _FakeSubAgentTool:
            def execute(self, params):
                calls.append(params)
                return {"success": True, "stdout": "ok"}

        monkeypatch.setattr(
            "jarvis.jarvis_tools.sub_agent.SubAgentTool", _FakeSubAgentTool
        )
        monkeypatch.setattr(m, "get_multiline_input", lambda *a, **k: "", raising=False)
        monkeypatch.setattr(
            "jarvis.jarvis_utils.input.get_multiline_input",
            lambda *a, **k: "做一个任务",
            raising=False,
        )
        monkeypatch.setattr(
            "jarvis.jarvis_utils.input.user_confirm", lambda *a, **k: False, raising=False
        )

        agent = type("A", (), {})()

        # 先触发 Cat 分支（历史上会 STORE_FAST os）
        target = tmp_path / "a.txt"
        target.write_text("hello", encoding="utf-8")
        m.builtin_input_handler(f"'<Cat>' {target}", agent)

        # 再触发 SubAgent 分支，此时 os.getcwd() 必须可用
        ret, done = m.builtin_input_handler("'<SubAgent>'", agent)
        assert done is True
        assert calls and "当前工作目录" in calls[0]["background"]
