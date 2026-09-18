"""search_web 工具的多源聚合与辅助函数单元测试。"""

import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from jarvis.jarvis_tools.search_web import SearchWebTool
from jarvis.jarvis_tools.search_web import _is_anti_spider_page
from jarvis.jarvis_tools.search_web import _normalize_url


class TestNormalizeUrl:
    """URL 归一化去重键测试。"""

    def test_strips_query_and_trailing_slash(self):
        assert _normalize_url("https://Example.com/a/b/?x=1") == _normalize_url(
            "https://example.com/a/b"
        )

    def test_empty_returns_empty(self):
        assert _normalize_url("") == ""

    def test_distinct_paths_differ(self):
        assert _normalize_url("https://a.com/x") != _normalize_url("https://a.com/y")


class TestAntiSpiderDetection:
    """反爬验证页识别测试。"""

    @pytest.mark.parametrize(
        "content",
        ["访问异常页面", "请输入验证码", "安全验证", "antispider"],
    )
    def test_detects_markers(self, content):
        assert _is_anti_spider_page(content) is True

    def test_normal_page_not_detected(self):
        assert _is_anti_spider_page("<html>正常搜索结果</html>") is False


class TestSearch360:
    """360 搜索源解析与容错测试。"""

    def test_parses_results(self):
        html = """
        <html><body>
          <li><h3><a href="https://example.com/1">Rust 所有权</a></h3>
              <p>摘要文本一</p></li>
          <li><h3><a href="https://example.com/2">Borrow Checker</a></h3>
              <p>摘要文本二</p></li>
        </body></html>
        """
        tool = SearchWebTool()
        with patch("jarvis.jarvis_tools.search_web.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                text=html, status_code=200, url="https://example.com/1"
            )
            mock_get.return_value.raise_for_status = MagicMock()
            results = tool._search_360("rust", limit=5)

        assert len(results) == 2
        assert results[0]["title"] == "Rust 所有权"
        assert results[0]["url"] == "https://example.com/1"
        assert results[0]["abstract"] == "摘要文本一"

    def test_returns_empty_on_anti_spider(self):
        tool = SearchWebTool()
        with patch("jarvis.jarvis_tools.search_web.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                text="访问异常页面 请输入验证码", status_code=200
            )
            mock_get.return_value.raise_for_status = MagicMock()
            assert tool._search_360("rust") == []

    def test_returns_empty_on_exception(self):
        tool = SearchWebTool()
        with patch(
            "jarvis.jarvis_tools.search_web.requests.get",
            side_effect=Exception("boom"),
        ):
            assert tool._search_360("rust") == []

    def test_respects_limit(self):
        html = (
            "<html><body>"
            + "".join(
                f'<li><h3><a href="https://e.com/{i}">T{i}</a></h3></li>'
                for i in range(10)
            )
            + "</body></html>"
        )
        tool = SearchWebTool()
        with patch("jarvis.jarvis_tools.search_web.requests.get") as mock_get:
            mock_get.return_value = MagicMock(text=html, status_code=200)
            mock_get.return_value.raise_for_status = MagicMock()
            assert len(tool._search_360("x", limit=3)) == 3


class TestDedupeResults:
    """聚合结果去重测试。"""

    def test_dedupes_same_normalized_url(self):
        results = [
            {"title": "A", "url": "https://x.com/p?u=1", "abstract": ""},
            {"title": "A2", "url": "https://x.com/p", "abstract": ""},
            {"title": "B", "url": "https://x.com/q", "abstract": ""},
        ]
        deduped = SearchWebTool._dedupe_results(results)
        assert len(deduped) == 2
        assert deduped[0]["title"] == "A"
        assert deduped[1]["title"] == "B"

    def test_skips_empty_url(self):
        results = [{"title": "A", "url": "", "abstract": ""}]
        assert SearchWebTool._dedupe_results(results) == []


class TestSearchMultiSource:
    """多源聚合调度测试。"""

    def test_merges_and_marks_sources(self):
        tool = SearchWebTool()
        with (
            patch.object(
                tool,
                "_search_stackoverflow",
                return_value=[
                    {"title": "SO", "url": "https://so.com/1", "abstract": ""}
                ],
            ),
            patch.object(
                tool,
                "_search_github",
                return_value=[
                    {"title": "GH", "url": "https://gh.com/1", "abstract": ""}
                ],
            ),
            patch.object(tool, "_search_360", return_value=[]),
        ):
            result = tool._search_multi_source("rust")

        assert result["success"] is True
        assert "SO" in result["stdout"]
        assert "GH" in result["stdout"]

    def test_single_source_failure_is_tolerated(self):
        tool = SearchWebTool()
        with (
            patch.object(tool, "_search_stackoverflow", side_effect=Exception("fail")),
            patch.object(
                tool,
                "_search_github",
                return_value=[
                    {"title": "GH", "url": "https://gh.com/1", "abstract": ""}
                ],
            ),
            patch.object(tool, "_search_360", return_value=[]),
        ):
            result = tool._search_multi_source("rust")

        assert result["success"] is True
        assert "GH" in result["stdout"]

    def test_results_ordered_by_source_priority(self):
        """结果顺序按源优先级（StackOverflow > GitHub > 360），不随完成先后变化。"""
        tool = SearchWebTool()

        def slow_so(*_args, **_kwargs):
            time.sleep(0.05)
            return [
                {
                    "title": "StackOverflow 结果",
                    "url": "https://so.com/1",
                    "abstract": "",
                }
            ]

        with (
            patch.object(tool, "_search_stackoverflow", side_effect=slow_so),
            patch.object(
                tool,
                "_search_github",
                return_value=[
                    {"title": "GitHub 结果", "url": "https://gh.com/1", "abstract": ""}
                ],
            ),
            patch.object(
                tool,
                "_search_360",
                return_value=[
                    {"title": "360 结果", "url": "https://360.com/1", "abstract": ""}
                ],
            ),
        ):
            result = tool._search_multi_source("rust")

        stdout = result["stdout"]
        assert stdout.index("StackOverflow 结果") < stdout.index("GitHub 结果")
        assert stdout.index("GitHub 结果") < stdout.index("360 结果")

    def test_all_sources_empty_returns_failure(self):
        tool = SearchWebTool()
        with (
            patch.object(tool, "_search_stackoverflow", return_value=[]),
            patch.object(tool, "_search_github", return_value=[]),
            patch.object(tool, "_search_360", return_value=[]),
        ):
            result = tool._search_multi_source("rust")

        assert result["success"] is False


class TestFallbackSearch:
    """ddgr 降级入口测试。"""

    def test_uses_aggregation_when_available(self):
        tool = SearchWebTool()
        with patch.object(
            tool,
            "_search_multi_source",
            return_value={"stdout": "聚合结果", "stderr": "", "success": True},
        ):
            result = tool._fallback_search("rust", agent=MagicMock())
        assert result["stdout"] == "聚合结果"

    def test_falls_back_to_bing_when_aggregation_empty(self):
        tool = SearchWebTool()
        with (
            patch.object(tool, "_search_multi_source", return_value={"success": False}),
            patch.object(
                tool,
                "_search_with_playwright",
                return_value={"stdout": "Bing结果", "stderr": "", "success": True},
            ) as mock_bing,
        ):
            result = tool._fallback_search("rust", agent=MagicMock())

        assert result["stdout"] == "Bing结果"
        mock_bing.assert_called_once()
