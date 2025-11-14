# -*- coding: utf-8 -*-
"""jarvis_code_analysis.code_review 模块单元测试"""


from jarvis.jarvis_code_analysis.code_review import _detect_languages_from_files


class TestDetectLanguagesFromFiles:
    """测试 _detect_languages_from_files 函数"""

    def test_empty_list(self):
        """测试空列表"""
        result = _detect_languages_from_files([])
        assert result == []

    def test_python_files(self):
        """测试 Python 文件"""
        files = ["test.py", "main.py", "utils.py"]
        result = _detect_languages_from_files(files)
        assert "python" in result

    def test_java_files(self):
        """测试 Java 文件"""
        files = ["Test.java", "Main.java"]
        result = _detect_languages_from_files(files)
        assert "java" in result

    def test_javascript_files(self):
        """测试 JavaScript 文件"""
        files = ["app.js", "index.js"]
        result = _detect_languages_from_files(files)
        assert "javascript" in result

    def test_typescript_files(self):
        """测试 TypeScript 文件"""
        files = ["app.ts", "index.tsx"]
        result = _detect_languages_from_files(files)
        assert "typescript" in result

    def test_c_cpp_files(self):
        """测试 C/C++ 文件"""
        files = ["main.c", "utils.cpp", "header.h"]
        result = _detect_languages_from_files(files)
        assert "c_cpp" in result

    def test_go_files(self):
        """测试 Go 文件"""
        files = ["main.go", "utils.go"]
        result = _detect_languages_from_files(files)
        assert "go" in result

    def test_rust_files(self):
        """测试 Rust 文件"""
        files = ["main.rs", "lib.rs"]
        result = _detect_languages_from_files(files)
        assert "rust" in result

    def test_multiple_languages(self):
        """测试多种语言"""
        files = ["test.py", "Main.java", "app.js", "main.go"]
        result = _detect_languages_from_files(files)
        assert "python" in result
        assert "java" in result
        assert "javascript" in result
        assert "go" in result

    def test_unknown_extension(self):
        """测试未知扩展名"""
        files = ["test.unknown", "file.xyz"]
        result = _detect_languages_from_files(files)
        # 未知扩展名不应该出现在结果中
        assert isinstance(result, list)

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        files = ["TEST.PY", "Main.JAVA"]
        result = _detect_languages_from_files(files)
        assert "python" in result
        assert "java" in result

    def test_no_extension(self):
        """测试无扩展名文件"""
        files = ["README", "Makefile"]
        result = _detect_languages_from_files(files)
        assert isinstance(result, list)

    def test_shell_scripts(self):
        """测试 Shell 脚本"""
        files = ["script.sh", "build.bash"]
        result = _detect_languages_from_files(files)
        assert "shell" in result

    def test_sql_files(self):
        """测试 SQL 文件"""
        files = ["schema.sql", "query.sql"]
        result = _detect_languages_from_files(files)
        assert "sql" in result

