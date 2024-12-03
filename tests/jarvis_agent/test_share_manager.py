# -*- coding: utf-8 -*-
"""share_manager 单元测试（主要测试 parse_selection）"""

from jarvis.jarvis_agent.share_manager import parse_selection


class TestParseSelection:
    """parse_selection 的测试"""

    def test_basic_range_and_values(self):
        assert parse_selection("1,2,3,4-6,20", 25) == [1, 2, 3, 4, 5, 6, 20]

    def test_out_of_bounds_ignored(self):
        # 0 和 26 超界；5-30 因 end 超界被整体忽略；保留 3
        assert parse_selection("0,26,5-30,3", 25) == [3]

    def test_invalid_inputs(self):
        # 非法项被忽略；有效范围 2-3 被解析
        assert parse_selection("a,b,1-?,2-3", 10) == [2, 3]

    def test_spaces_around_hyphen_and_commas(self):
        assert parse_selection(" 2 - 4 , 6 ", 10) == [2, 3, 4, 6]

    def test_duplicates_removed(self):
        assert parse_selection("1,1,2,2,2,3-4,4-5", 10) == [1, 2, 3, 4, 5]

    def test_reverse_range_ignored(self):
        # 5-3 在实现中会生成空范围，被忽略
        assert parse_selection("1,5-3", 10) == [1]
