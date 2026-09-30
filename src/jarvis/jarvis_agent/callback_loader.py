# -*- coding: utf-8 -*-
"""回调/事件加载职责模块

从 Agent 类中抽离的「回调/事件加载」职责簇。
设计说明：
- 遵循 jarvis_agent 包既有拆分范式（如 MemoryManager(self)、HistoryCompressor(self)）：
  本模块持有 agent 引用，方法体内通过 self.agent.xxx 访问 Agent 的其它能力。
- Agent 侧保留同名薄委托方法，保证对外接口完全不变。
- 循环依赖通过 TYPE_CHECKING 处理。
"""

import subprocess
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import List

from jarvis.jarvis_agent.events import AFTER_SUMMARY
from jarvis.jarvis_agent.events import AFTER_TOOL_CALL
from jarvis.jarvis_agent.events import BEFORE_MODEL_CALL
from jarvis.jarvis_agent.events import BEFORE_SUMMARY
from jarvis.jarvis_agent.events import BEFORE_TOOL_CALL
from jarvis.jarvis_utils.config import get_after_tool_call_cb_dirs
from jarvis.jarvis_utils.config import get_before_model_call_cb_dirs
from jarvis.jarvis_utils.config import get_before_tool_call_cb_dirs
from jarvis.jarvis_utils.config import get_summary_cb_dirs
from jarvis.jarvis_utils.exception_utils import save_exception
from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_agent import Agent


class CallbackLoader:
    """回调/事件加载职责实现

    所有方法等价于原先 Agent 类上的同名方法，仅把 self.xxx 改为 self.agent.xxx。
    """

    def __init__(self, agent: "Agent") -> None:
        self.agent = agent

    def load_after_tool_callbacks(self) -> None:
        """
        扫描 after_tool_call_cb_dirs 中的 Python 文件并动态注册回调。
        约定优先级（任一命中即注册）：
        - 模块级可调用对象: after_tool_call_cb
        - 工厂方法返回单个或多个可调用对象: get_after_tool_call_cb(), register_after_tool_call_cb()
        """
        try:
            dirs = get_after_tool_call_cb_dirs()
            if not dirs:
                return
            for d in dirs:
                p_dir = Path(d)
                if not p_dir.exists() or not p_dir.is_dir():
                    continue
                for file_path in p_dir.glob("*.py"):
                    if file_path.name == "__init__.py":
                        continue
                    parent_dir = str(file_path.parent)
                    added_path = False
                    try:
                        if parent_dir not in sys.path:
                            sys.path.insert(0, parent_dir)
                            added_path = True
                        module_name = file_path.stem

                        # 解析文件头部的 requirements 注释
                        requirements: List[str] = []
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line.startswith("# requirements:"):
                                        deps_str = line[
                                            len("# requirements:") :
                                        ].strip()
                                        if deps_str:
                                            requirements = deps_str.split()
                                        break
                        except Exception as e:
                            PrettyOutput.auto_print(
                                f"⚠️ 读取回调文件依赖声明失败 [{file_path.name}]: {e}"
                            )

                        # 安装依赖
                        if requirements:
                            PrettyOutput.auto_print(
                                f"🔧 正在安装回调文件依赖 [{file_path.name}]: {', '.join(requirements)}"
                            )
                            try:
                                result = subprocess.run(
                                    ["uv", "pip", "install"] + requirements,
                                    capture_output=True,
                                    text=True,
                                    timeout=120,
                                )
                                if result.returncode == 0:
                                    PrettyOutput.auto_print(
                                        f"✅ 依赖安装成功 [{file_path.name}]"
                                    )
                                else:
                                    PrettyOutput.auto_print(
                                        f"❌ 依赖安装失败 [{file_path.name}]: {result.stderr.strip()}"
                                    )
                            except subprocess.TimeoutExpired:
                                PrettyOutput.auto_print(
                                    f"❌ 依赖安装超时 [{file_path.name}] (超过 120 秒)"
                                )
                            except Exception as e:
                                PrettyOutput.auto_print(
                                    f"❌ 依赖安装异常 [{file_path.name}]: {e}"
                                )

                        module = __import__(module_name)
                        PrettyOutput.auto_print(
                            f"📦 从配置文件加载回调文件：{file_path}"
                        )

                        candidates: List[Callable[[Any], None]] = []

                        # 1) 直接导出的回调
                        if hasattr(module, "after_tool_call_cb"):
                            obj = getattr(module, "after_tool_call_cb")
                            if callable(obj):
                                candidates.append(obj)

                        # 2) 工厂方法：get_after_tool_call_cb()
                        if hasattr(module, "get_after_tool_call_cb"):
                            factory = getattr(module, "get_after_tool_call_cb")
                            if callable(factory):
                                try:
                                    ret = factory()
                                    if callable(ret):
                                        candidates.append(ret)
                                    elif isinstance(ret, (list, tuple)):
                                        for c in ret:
                                            if callable(c):
                                                candidates.append(c)
                                except Exception as e:
                                    PrettyOutput.auto_print(
                                        f"⚠️ 回调工厂方法 get_after_tool_call_cb 执行错误 [{type(e).__name__}]: {e}"
                                    )

                        # 3) 工厂方法：register_after_tool_call_cb()
                        if hasattr(module, "register_after_tool_call_cb"):
                            factory2 = getattr(module, "register_after_tool_call_cb")
                            if callable(factory2):
                                try:
                                    ret2 = factory2()
                                    if callable(ret2):
                                        candidates.append(ret2)
                                    elif isinstance(ret2, (list, tuple)):
                                        for c in ret2:
                                            if callable(c):
                                                candidates.append(c)
                                except Exception as e:
                                    PrettyOutput.auto_print(
                                        f"⚠️ 回调工厂方法 register_after_tool_call_cb 执行错误 [{type(e).__name__}]: {e}"
                                    )

                        for cb in candidates:
                            try:

                                def _make_wrapper(
                                    callback: Callable[[Any], None],
                                ) -> Callable[..., None]:
                                    def _wrapper(**kwargs: Any) -> None:
                                        try:
                                            agent = kwargs.get("agent")
                                            callback(agent)
                                        except Exception as e:
                                            PrettyOutput.auto_print(
                                                f"⚠️ 回调函数执行错误 [{type(e).__name__}]: {e}"
                                            )

                                    return _wrapper

                                self.agent.event_bus.subscribe(
                                    AFTER_TOOL_CALL, _make_wrapper(cb)
                                )
                            except Exception as e:
                                PrettyOutput.auto_print(
                                    f"⚠️ 回调函数订阅错误 [{type(e).__name__}]: {e}"
                                )

                    except Exception as e:
                        PrettyOutput.auto_print(f"⚠️ 从 {file_path} 加载回调失败: {e}")
                    finally:
                        if added_path:
                            try:
                                sys.path.remove(parent_dir)
                            except ValueError:
                                pass
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 加载回调目录时发生错误: {e}")

    def load_event_callbacks(
        self,
        event_name: str,
        config_getter: Callable[[], List[str]],
        callback_names: List[str],
        target: str = "event_bus",
    ) -> None:
        """
        通用的回调加载方法，支持从配置目录扫描并注册回调。

        参数:
            event_name: 事件名称（如 BEFORE_TOOL_CALL）
            config_getter: 配置目录获取函数（如 get_before_tool_call_cb_dirs）
            callback_names: 回调函数名称列表（优先级从高到低）
                           例如: ["before_tool_call_cb", "get_before_tool_call_cb", "register_before_tool_call_cb"]
            target: 回调注册目标，决定回调存储位置：
                - "event_bus": 注册到 EventBus（通知型，默认）
                - "hook": 注册到 hooks 列表（拦截型，返回 False 拦截）
                - "modifier": 注册到 modifiers 列表（修改型，返回修改后的值）
        """
        try:
            dirs = config_getter()
            if not dirs:
                return
            for d in dirs:
                p_dir = Path(d)
                if not p_dir.exists() or not p_dir.is_dir():
                    continue
                for file_path in p_dir.glob("*.py"):
                    if file_path.name == "__init__.py":
                        continue
                    parent_dir = str(file_path.parent)
                    added_path = False
                    try:
                        if parent_dir not in sys.path:
                            sys.path.insert(0, parent_dir)
                            added_path = True
                        module_name = file_path.stem

                        # 解析文件头部的 requirements 注释
                        requirements: List[str] = []
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line.startswith("# requirements:"):
                                        deps_str = line[
                                            len("# requirements:") :
                                        ].strip()
                                        if deps_str:
                                            requirements = deps_str.split()
                                        break
                        except Exception as e:
                            PrettyOutput.auto_print(
                                f"⚠️ 解析回调文件依赖失败 [{file_path.name}]: {e}"
                            )

                        # 安装依赖
                        if requirements:
                            PrettyOutput.auto_print(
                                f"🔧 正在安装回调文件依赖 [{file_path.name}]: {', '.join(requirements)}"
                            )
                            try:
                                result = subprocess.run(
                                    ["uv", "pip", "install"] + requirements,
                                    capture_output=True,
                                    text=True,
                                    timeout=120,
                                )
                                if result.returncode == 0:
                                    PrettyOutput.auto_print(
                                        f"✅ 依赖安装成功 [{file_path.name}]"
                                    )
                                else:
                                    PrettyOutput.auto_print(
                                        f"❌ 依赖安装失败 [{file_path.name}]: {result.stderr.strip()}"
                                    )
                            except subprocess.TimeoutExpired:
                                PrettyOutput.auto_print(
                                    f"❌ 依赖安装超时 [{file_path.name}] (超过 120 秒)"
                                )
                            except Exception as e:
                                PrettyOutput.auto_print(
                                    f"❌ 依赖安装异常 [{file_path.name}]: {e}"
                                )

                        module = __import__(module_name)
                        PrettyOutput.auto_print(
                            f"📦 从配置文件加载回调文件：{file_path}"
                        )

                        candidates: List[Callable] = []

                        # 按优先级尝试获取回调
                        for callback_name in callback_names:
                            if hasattr(module, callback_name):
                                obj = getattr(module, callback_name)
                                if callable(obj):
                                    try:
                                        ret = (
                                            obj()
                                            if callback_name.startswith(
                                                ("get_", "register_")
                                            )
                                            else obj
                                        )
                                        if callable(ret):
                                            candidates.append(ret)
                                        elif isinstance(ret, (list, tuple)):
                                            for c in ret:
                                                if callable(c):
                                                    candidates.append(c)
                                    except Exception as e:
                                        PrettyOutput.auto_print(
                                            f"⚠️ 调用工厂方法 {callback_name}() 失败 [{file_path.name}]: {e}"
                                        )

                        # 根据目标类型注册回调
                        for cb in candidates:
                            try:
                                if target == "hook":
                                    # Hook：拦截型，注册到 hooks 列表
                                    if event_name == BEFORE_TOOL_CALL:
                                        self.agent._before_tool_call_hooks.append(cb)
                                    # 同时注册到 EventBus 作为通知
                                    self.agent.event_bus.subscribe(event_name, cb)
                                elif target == "modifier":
                                    # Modifier：修改型，注册到 modifiers 列表
                                    if event_name == BEFORE_MODEL_CALL:
                                        self.agent._before_model_call_modifiers.append(
                                            cb
                                        )
                                    elif event_name == BEFORE_SUMMARY:
                                        self.agent._before_summary_modifiers.append(cb)
                                else:
                                    # Event：通知型，注册到 EventBus
                                    self.agent.event_bus.subscribe(event_name, cb)
                            except Exception as e:
                                PrettyOutput.auto_print(
                                    f"⚠️ 注册回调失败 [{file_path.name}]: {e}\n{traceback.format_exc()}"
                                )

                    except Exception as e:
                        PrettyOutput.auto_print(
                            f"⚠️ 加载回调文件失败 [{file_path}]: {e}\n{traceback.format_exc()}"
                        )
                    finally:
                        if added_path:
                            try:
                                sys.path.remove(parent_dir)
                            except ValueError:
                                pass
        except Exception as e:
            PrettyOutput.auto_print(
                f"⚠️ 加载 {event_name} 回调目录失败: {e}\n{traceback.format_exc()}"
            )

    def load_all_event_callbacks(self) -> None:
        """
        加载所有事件回调（包括 before_tool_call、before_model_call、summary 等）。
        """
        # 加载 before_tool_call 回调（Hook：拦截型 + Event 通知）
        self.agent._load_event_callbacks(
            event_name=BEFORE_TOOL_CALL,
            config_getter=get_before_tool_call_cb_dirs,
            callback_names=[
                "before_tool_call_cb",
                "get_before_tool_call_cb",
                "register_before_tool_call_cb",
            ],
            target="hook",
        )

        # 加载 before_model_call 回调（Modifier：修改型）
        self.agent._load_event_callbacks(
            event_name=BEFORE_MODEL_CALL,
            config_getter=get_before_model_call_cb_dirs,
            callback_names=[
                "before_model_call_cb",
                "get_before_model_call_cb",
                "register_before_model_call_cb",
            ],
            target="modifier",
        )

        # 加载 before_summary 回调（Modifier：修改型）
        self.agent._load_event_callbacks(
            event_name=BEFORE_SUMMARY,
            config_getter=get_summary_cb_dirs,
            callback_names=[
                "before_summary_cb",
                "get_before_summary_cb",
                "register_before_summary_cb",
            ],
            target="modifier",
        )

        # 加载 after_summary 回调（Event：通知型）
        self.agent._load_event_callbacks(
            event_name=AFTER_SUMMARY,
            config_getter=get_summary_cb_dirs,
            callback_names=[
                "after_summary_cb",
                "get_after_summary_cb",
                "register_after_summary_cb",
            ],
        )

    def fire_after_tool_call(self) -> None:
        """触发 AFTER_TOOL_CALL：emit 会按优先级调用所有订阅回调。

        （此前先手动遍历 _listeners 再 emit，导致同一批回调被派发两次）
        """
        try:
            self.agent.event_bus.emit(
                AFTER_TOOL_CALL,
                agent=self.agent,
                current_response="",
                need_return=False,
                tool_prompt="",
            )
        except Exception as e:
            save_exception(
                e, module="jarvis_agent.__init__", function="_fire_after_tool_call"
            )
            pass
