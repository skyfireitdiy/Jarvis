# -*- coding: utf-8 -*-
"""pipeline_events（流水线进度事件总线）测试。

覆盖：
1. PipelineEventBus 基本读写：emit/drain 保序、drain 清空、has_events；
2. 有界性：超出 maxlen 丢弃最旧事件；
3. 非法输入：非 dict 事件被忽略；
4. 线程安全：多线程并发 emit 不丢事件、不报错；
5. get_event_bus 单例语义。
"""

import threading
from typing import Any
from typing import cast

from jarvis.jarvis_tools.pipeline_events import PipelineEventBus
from jarvis.jarvis_tools.pipeline_events import get_event_bus


class TestPipelineEventBus:
    def test_emit_drain_order(self):
        """emit 后 drain 按写入顺序返回全部事件，并清空队列。"""
        bus = PipelineEventBus()
        bus.emit({"id": 1})
        bus.emit({"id": 2})
        bus.emit({"id": 3})
        assert bus.drain() == [{"id": 1}, {"id": 2}, {"id": 3}]
        assert bus.drain() == []

    def test_has_events(self):
        """has_events 反映队列是否有未消费事件。"""
        bus = PipelineEventBus()
        assert bus.has_events() is False
        bus.emit({"id": 1})
        assert bus.has_events() is True
        bus.drain()
        assert bus.has_events() is False

    def test_bounded_drops_oldest(self):
        """超过 maxlen 时丢弃最旧事件，只保留最新 N 条。"""
        bus = PipelineEventBus(max_events=3)
        for i in range(5):
            bus.emit({"id": i})
        assert bus.drain() == [{"id": 2}, {"id": 3}, {"id": 4}]

    def test_non_dict_ignored(self):
        """非 dict 事件被静默忽略，不影响后续事件。"""
        bus = PipelineEventBus()
        bus.emit(cast(Any, "not-a-dict"))
        bus.emit(cast(Any, None))
        bus.emit({"id": 1})
        assert bus.drain() == [{"id": 1}]

    def test_thread_safety(self):
        """多线程并发 emit 不丢事件、不抛异常。"""
        bus = PipelineEventBus(max_events=10000)
        threads = []
        per_thread = 200

        def worker(tid: int) -> None:
            for i in range(per_thread):
                bus.emit({"tid": tid, "i": i})

        for t in range(8):
            th = threading.Thread(target=worker, args=(t,))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()

        events = bus.drain()
        assert len(events) == 8 * per_thread
        # 每条事件都完整（未被并发写坏）
        assert all(isinstance(e.get("tid"), int) for e in events)


class TestGetEventBus:
    def test_singleton(self):
        """get_event_bus 返回同一实例。"""
        assert get_event_bus() is get_event_bus()
