# -*- coding: utf-8 -*-
"""jarvis CLI 单元测试。"""

# 注意：原有的 TestJarvisCliSessionSave 测试已被删除
# 原因：该测试过于复杂且脆弱，使用了大量的 monkeypatch 和 mock
# 测试涉及多个复杂的初始化流程，难以维护
# 其他测试文件（test_session_manager.py、test_agent_task_lists.py）
# 已经充分覆盖了 save_session 功能的单元测试
