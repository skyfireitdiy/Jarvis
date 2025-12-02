# -*- coding: utf-8 -*-
"""jarvis_utils.git_utils 模块单元测试"""

from unittest.mock import patch, MagicMock

from jarvis.jarvis_utils.git_utils import (
    detect_large_code_deletion,
    get_modified_line_ranges,
    is_file_in_git_repo,
)


class TestDetectLargeCodeDeletion:
    """测试 detect_large_code_deletion 函数"""

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_no_large_deletion(self, mock_run):
        """测试没有大量删除的情况"""
        # 模拟 git diff 输出：少量删除
        mock_run.return_value = MagicMock(
            returncode=0, stdout=" 5 files changed, 10 insertions(+), 5 deletions(-)"
        )

        result = detect_large_code_deletion(threshold=200)
        assert result is None

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_large_deletion_detected(self, mock_run):
        """测试检测到大量删除"""
        # 模拟 git diff 输出：大量删除
        mock_run.return_value = MagicMock(
            returncode=0, stdout=" 10 files changed, 50 insertions(+), 300 deletions(-)"
        )

        result = detect_large_code_deletion(threshold=200)
        assert result is not None
        assert result["insertions"] == 50
        assert result["deletions"] == 300
        assert result["net_deletions"] == 250

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_custom_threshold(self, mock_run):
        """测试自定义阈值"""
        # 模拟 git diff 输出：中等删除
        mock_run.return_value = MagicMock(
            returncode=0, stdout=" 5 files changed, 10 insertions(+), 150 deletions(-)"
        )

        # 使用较小的阈值
        result = detect_large_code_deletion(threshold=100)
        assert result is not None
        assert result["net_deletions"] == 140

        # 使用较大的阈值
        result = detect_large_code_deletion(threshold=200)
        assert result is None

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_no_changes(self, mock_run):
        """测试没有变更的情况"""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = detect_large_code_deletion()
        assert result is None

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_exception_handling(self, mock_run):
        """测试异常处理"""
        mock_run.side_effect = Exception("Git error")

        result = detect_large_code_deletion()
        assert result is None


class TestGetModifiedLineRanges:
    """测试 get_modified_line_ranges 函数"""

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_single_file_single_range(self, mock_run):
        """测试单个文件的单个范围"""
        diff_output = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -10,5 +10,7 @@
 line 10
+new line 1
+new line 2
 line 11
"""
        mock_run.return_value = MagicMock(returncode=0, stdout=diff_output)

        result = get_modified_line_ranges()
        assert "test.py" in result
        assert len(result["test.py"]) == 1
        # @@ -10,5 +10,7 @@ 表示从第10行开始，新增7行，所以结束行是 10 + 7 - 1 = 16
        assert result["test.py"][0] == (10, 16)

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_multiple_files_multiple_ranges(self, mock_run):
        """测试多个文件的多个范围"""
        diff_output = """diff --git a/file1.py b/file1.py
+++ b/file1.py
@@ -5,3 +5,5 @@
 line 5
+new line
 line 6
diff --git a/file2.py b/file2.py
+++ b/file2.py
@@ -20,2 +20,4 @@
 line 20
+new line
"""
        mock_run.return_value = MagicMock(returncode=0, stdout=diff_output)

        result = get_modified_line_ranges()
        assert "file1.py" in result
        assert "file2.py" in result
        assert len(result["file1.py"]) >= 1
        assert len(result["file2.py"]) >= 1

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_no_changes(self, mock_run):
        """测试没有变更的情况"""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        result = get_modified_line_ranges()
        assert result == {}


class TestIsFileInGitRepo:
    """测试 is_file_in_git_repo 函数"""

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_file_in_repo(self, mock_run):
        """测试文件在仓库中"""
        mock_run.return_value = MagicMock(returncode=0, stdout="/path/to/repo\n")

        with patch(
            "jarvis.jarvis_utils.git_utils.os.path.abspath",
            return_value="/path/to/repo/file.py",
        ):
            result = is_file_in_git_repo("file.py")
            assert result is True

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_file_not_in_repo(self, mock_run):
        """测试文件不在仓库中"""
        mock_run.return_value = MagicMock(returncode=0, stdout="/path/to/repo\n")

        # 模拟文件路径不在仓库根目录下
        with patch("jarvis.jarvis_utils.git_utils.os.path.abspath") as mock_abspath:

            def abspath_side_effect(path):
                if path == "file.py":
                    return "/other/path/file.py"
                elif path == "/path/to/repo":
                    return "/path/to/repo"
                return path

            mock_abspath.side_effect = abspath_side_effect

            result = is_file_in_git_repo("file.py")
            assert result is False

    @patch("jarvis.jarvis_utils.git_utils.subprocess.run")
    def test_exception_handling(self, mock_run):
        """测试异常处理"""
        mock_run.side_effect = Exception("Git error")

        result = is_file_in_git_repo("file.py")
        assert result is False
