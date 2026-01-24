# -*- coding: utf-8 -*-
"""滑动窗口压缩功能测试"""

from unittest.mock import Mock
import pytest

from jarvis.jarvis_agent import Agent


class TestSlidingWindowCompression:
    """滑动窗口压缩功能测试"""

    @pytest.fixture
    def mock_model(self):
        """创建模拟的模型对象"""
        model = Mock()
        model.messages = []
        model.get_messages = Mock(return_value=[])
        model.get_remaining_token_count = Mock(return_value=1000)
        model.chat_until_success = Mock(return_value="压缩后的摘要内容")

        # 添加 set_messages 方法，让它真正修改 messages 属性
        def set_messages_impl(messages):
            model.messages = messages

        model.set_messages = Mock(side_effect=set_messages_impl)

        return model

    @pytest.fixture
    def agent(self, mock_model):
        """创建Agent实例"""
        # 使用Mock创建Agent，避免复杂的初始化
        ag = Mock(spec=Agent)
        ag.model = mock_model
        ag.pin_content = ""
        ag.original_user_input = ""
        ag.recent_memories = []
        ag.task_list_manager = Mock()
        ag.task_list_manager.task_lists = {}
        ag.task_list_manager.get_task_list_summary = Mock(return_value=None)
        ag._agent_run_loop = None
        ag.start_commit = None

        # Mock _create_temp_model方法
        temp_model = Mock()
        temp_model.chat_until_success = Mock(return_value="压缩后的摘要内容")
        ag._create_temp_model = Mock(return_value=temp_model)

        # Mock _format_compressed_summary方法
        ag._format_compressed_summary = Mock(side_effect=lambda x: f"[历史摘要] {x}")

        # 将实际的_sliding_window_compression方法绑定到mock对象
        from jarvis.jarvis_agent import Agent as RealAgent

        ag._sliding_window_compression = RealAgent._sliding_window_compression.__get__(
            ag, Mock
        )

        return ag

    def _create_messages(
        self, user_count: int, assistant_count: int, system_count: int = 1
    ):
        """创建测试消息列表"""
        messages = []

        # 添加系统消息
        for i in range(system_count):
            messages.append({"role": "system", "content": f"系统提示词{i}"})

        # 添加交替的用户和助手消息
        for i in range(max(user_count, assistant_count)):
            if i < user_count:
                messages.append({"role": "user", "content": f"user{i + 1}的内容"})
            if i < assistant_count:
                messages.append(
                    {"role": "assistant", "content": f"assistant{i + 1}的内容"}
                )

        return messages

    def test_compression_basic(self, agent, mock_model):
        """测试基本压缩功能：21条消息压缩后变为11条（1 system + 1 压缩摘要 + 9 最近消息）"""
        # 准备消息：1 system + 10 user + 10 assistant = 21条
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        # 验证结果：压缩后应该是 1 system + 1 压缩摘要 + 9 最近消息 = 11条
        assert result is True
        assert len(mock_model.messages) == 11  # 1 system + 1 压缩摘要 + 9 最近消息

        # 验证系统消息保留
        assert mock_model.messages[0]["role"] == "system"

        # 验证压缩摘要插入
        assert mock_model.messages[1]["role"] == "user"
        assert "[历史摘要]" in mock_model.messages[1]["content"]

        # 验证最近9条消息保留（从assistant6到assistant10）
        recent_messages = mock_model.messages[2:]
        assert len(recent_messages) == 9

        # 验证消息顺序：assistant6, user7, assistant7, ..., user10, assistant10
        assert recent_messages[0]["role"] == "assistant"
        assert recent_messages[0]["content"] == "assistant6的内容"
        assert recent_messages[-1]["role"] == "assistant"
        assert recent_messages[-1]["content"] == "assistant10的内容"

    def test_compression_no_consecutive_user(self, agent, mock_model):
        """测试压缩后不会出现连续的两个user消息"""
        # 准备消息：1 system + 10 user + 10 assistant = 21条
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True

        # 验证压缩摘要后面不是user消息（应该是assistant）
        compressed_msg = mock_model.messages[1]
        first_recent_msg = mock_model.messages[2]

        assert compressed_msg["role"] == "user"
        assert first_recent_msg["role"] == "assistant"  # 应该是assistant6，不是user7

    def test_compression_insufficient_messages(self, agent, mock_model):
        """测试消息数量不足时不执行压缩"""
        # 准备消息：1 system + 5 user + 5 assistant = 11条（other_messages=10条，少于window_size=9）
        messages = self._create_messages(
            user_count=5, assistant_count=5, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        # 应该返回False，因为other_messages只有10条，少于window_size=9
        assert result is False
        assert len(mock_model.messages) == 11  # 消息未改变

    def test_compression_exact_window_size(self, agent, mock_model):
        """测试消息数量刚好等于窗口大小的2倍时不执行压缩"""
        # 准备消息：1 system + 9 user + 9 assistant = 19条（other_messages=18条，刚好是9的2倍）
        messages = self._create_messages(
            user_count=9, assistant_count=9, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        # 应该返回False，因为other_messages=18条，刚好等于window_size*2=18（条件：<= window_size * 2）
        assert result is False
        assert len(mock_model.messages) == 19  # 消息未改变

    def test_compression_multiple_system_messages(self, agent, mock_model):
        """测试多个系统消息时都保留"""
        # 准备消息：3 system + 10 user + 10 assistant = 23条
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=3
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True

        # 验证所有系统消息都保留
        system_messages = [
            msg for msg in mock_model.messages if msg["role"] == "system"
        ]
        assert len(system_messages) == 3

    def test_compression_with_tool_messages(self, agent, mock_model):
        """测试包含tool消息的情况"""
        # 准备消息：1 system + 10 user + 10 assistant + 1 tool = 22条
        # other_messages有21条（10 user + 10 assistant + 1 tool）
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        messages.append({"role": "tool", "content": "tool返回的内容"})
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True

        # 验证tool消息是否在保留的9条消息中
        recent_messages = mock_model.messages[2:]  # 跳过system和压缩摘要
        assert len(recent_messages) == 9

        # tool消息是最后一条，应该在保留的9条中
        assert recent_messages[-1]["role"] == "tool"
        assert recent_messages[-1]["content"] == "tool返回的内容"

    def test_compression_message_order(self, agent, mock_model):
        """测试压缩后消息顺序正确"""
        # 准备消息：1 system + 10 user + 10 assistant = 21条
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True

        # 验证消息顺序：system -> 压缩摘要 -> 最近9条消息
        assert mock_model.messages[0]["role"] == "system"
        assert mock_model.messages[1]["role"] == "user"
        assert "[历史摘要]" in mock_model.messages[1]["content"]

        # 验证最近9条消息的顺序
        recent_messages = mock_model.messages[2:]
        # 应该是：assistant6, user7, assistant7, user8, assistant8, user9, assistant9, user10, assistant10
        assert recent_messages[0]["role"] == "assistant"
        assert recent_messages[0]["content"] == "assistant6的内容"
        assert recent_messages[1]["role"] == "user"
        assert recent_messages[1]["content"] == "user7的内容"
        assert recent_messages[-1]["role"] == "assistant"
        assert recent_messages[-1]["content"] == "assistant10的内容"

    def test_compression_old_messages_count(self, agent, mock_model):
        """测试压缩的消息数量正确：21条压缩后变为11条"""
        # 准备消息：1 system + 10 user + 10 assistant = 21条
        # other_messages有20条（索引0-19）
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True

        # 验证压缩的消息数量
        # other_messages有20条，保留最后9条（索引11-19），压缩前11条（索引0-10）
        # 压缩的应该是：user1, assistant1, user2, assistant2, user3, assistant3, user4, assistant4, user5, assistant5, user6（11条）
        # 保留的应该是：assistant6, user7, assistant7, user8, assistant8, user9, assistant9, user10, assistant10（9条）

        # 验证最终消息数量：压缩前21条 -> 压缩后 1 system + 1 压缩摘要 + 9 最近消息 = 11条
        assert len(mock_model.messages) == 11

    def test_compression_empty_summary(self, agent, mock_model):
        """测试压缩摘要为空时返回False"""
        # 准备消息
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 模拟临时模型返回空摘要
        temp_model = agent._create_temp_model.return_value
        temp_model.chat_until_success.return_value = ""

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        # 应该返回False
        assert result is False
        assert len(mock_model.messages) == 21  # 消息未改变

    def test_compression_custom_window_size(self, agent, mock_model):
        """测试自定义窗口大小"""
        # 准备消息：1 system + 15 user + 15 assistant = 31条
        messages = self._create_messages(
            user_count=15, assistant_count=15, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩，使用自定义窗口大小5
        result = agent._sliding_window_compression(window_size=5)

        assert result is True

        # 验证保留的消息数量
        recent_messages = mock_model.messages[2:]  # 跳过system和压缩摘要
        assert len(recent_messages) == 5

    def test_compression_uses_temp_model(self, agent, mock_model):
        """测试压缩使用临时模型"""
        # 准备消息
        messages = self._create_messages(
            user_count=10, assistant_count=10, system_count=1
        )
        mock_model.get_messages.return_value = messages
        mock_model.messages = messages.copy()

        # 执行压缩
        result = agent._sliding_window_compression(window_size=9)

        assert result is True
        # 验证使用了临时模型
        agent._create_temp_model.assert_called_once()
        temp_model = agent._create_temp_model.return_value
        temp_model.chat_until_success.assert_called_once()

    def _is_alternating_roles(self, messages: list) -> bool:
        """验证消息列表的 role 是否交叉

        交叉模式定义：
        - system 可以在开头（多个system也可以）
        - 之后必须是 user 和 assistant 交替出现
        - 不能有连续相同的 role（system 除外）
        """
        if not messages:
            return True

        roles = [msg.get("role", "").lower() for msg in messages]

        # 找到第一个非 system 消息的索引
        first_non_system = 0
        for i, role in enumerate(roles):
            if role != "system":
                first_non_system = i
                break
        else:
            return True

        # 检查非 system 消息是否交叉
        non_system_roles = roles[first_non_system:]

        for i in range(len(non_system_roles) - 1):
            current_role = non_system_roles[i]
            next_role = non_system_roles[i + 1]

            if current_role == next_role:
                return False

            if current_role not in ["user", "assistant"]:
                return False
            if next_role not in ["user", "assistant"]:
                return False

        return True

    def _simulate_compression_slice(self, messages: list, window_size: int) -> dict:
        """模拟滑动窗口压缩的切片逻辑"""
        # 找到系统消息的结束位置
        system_end_idx = 0
        for i, msg in enumerate(messages):
            if msg.get("role", "").lower() != "system":
                system_end_idx = i
                break
        else:
            return {
                "system_messages": messages,
                "old_messages": [],
                "recent_messages": [],
            }

        # 分离系统消息和非系统消息
        system_messages = messages[:system_end_idx]
        non_system_messages = messages[system_end_idx:]

        # 截取最近的消息
        recent_messages = non_system_messages[-window_size:]

        # 分离更早的消息（多截取一条）
        old_messages = non_system_messages[: -window_size + 1]

        return {
            "system_messages": system_messages,
            "old_messages": old_messages,
            "recent_messages": recent_messages,
        }

    def test_first_set_messages_alternating_roles(self):
        """验证第一次 set_messages 调用（system_messages + old_messages）满足交叉模式"""
        for window_size in [3, 5, 7, 9]:
            messages = self._create_messages(
                user_count=20, assistant_count=20, system_count=1
            )
            slices = self._simulate_compression_slice(messages, window_size)
            first_set_messages = slices["system_messages"] + slices["old_messages"]
            assert self._is_alternating_roles(first_set_messages), (
                f"window_size={window_size}: 第一次 set_messages 不满足交叉模式\n"
                f"roles: {[msg['role'] for msg in first_set_messages]}"
            )

    def test_second_set_messages_alternating_roles(self):
        """验证第二次 set_messages 调用（system_messages + compressed_msg + recent_messages）满足交叉模式"""
        for window_size in [3, 5, 7, 9]:
            messages = self._create_messages(
                user_count=20, assistant_count=20, system_count=1
            )
            slices = self._simulate_compression_slice(messages, window_size)
            compressed_msg = {"role": "user", "content": "[压缩摘要]"}
            second_set_messages = (
                slices["system_messages"] + [compressed_msg] + slices["recent_messages"]
            )
            assert self._is_alternating_roles(second_set_messages), (
                f"window_size={window_size}: 第二次 set_messages 不满足交叉模式\n"
                f"roles: {[msg['role'] for msg in second_set_messages]}"
            )

    def test_compressed_msg_not_consecutive_with_recent(self):
        """验证 compressed_msg（role=user）和 recent_messages[0] 不会连续"""
        for window_size in [3, 5, 7, 9]:
            messages = self._create_messages(
                user_count=20, assistant_count=20, system_count=1
            )
            slices = self._simulate_compression_slice(messages, window_size)
            if slices["recent_messages"]:
                first_recent_role = slices["recent_messages"][0]["role"]
                assert first_recent_role == "assistant", (
                    f"window_size={window_size}: recent_messages[0] 应该是 assistant，"
                    f"实际是 {first_recent_role}"
                )

    def test_multiple_system_messages_alternating_roles(self):
        """验证多个系统消息时，set_messages 调用仍然满足交叉模式"""
        for window_size in [3, 5, 7, 9]:
            for system_count in [1, 2, 3]:
                messages = self._create_messages(
                    user_count=20, assistant_count=20, system_count=system_count
                )
                slices = self._simulate_compression_slice(messages, window_size)

                # 第一次 set_messages
                first_set_messages = slices["system_messages"] + slices["old_messages"]
                assert self._is_alternating_roles(first_set_messages), (
                    f"system_count={system_count}, window_size={window_size}: "
                    f"第一次 set_messages 不满足交叉模式"
                )

                # 第二次 set_messages
                compressed_msg = {"role": "user", "content": "[压缩摘要]"}
                second_set_messages = (
                    slices["system_messages"]
                    + [compressed_msg]
                    + slices["recent_messages"]
                )
                assert self._is_alternating_roles(second_set_messages), (
                    f"system_count={system_count}, window_size={window_size}: "
                    f"第二次 set_messages 不满足交叉模式"
                )
