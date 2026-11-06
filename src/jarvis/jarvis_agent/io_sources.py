# -*- coding: utf-8 -*-
"""输入源 / 输出源扩展点（NLSpec: io-sources）。

为插件系统提供两个正交的扩展点：

- **输入源（input_sources）**：插件通过 ``input_source_cb`` 回调向 Agent 注入
  外部输入（如监听外部消息、定时拉取等）。回调签名 ``input_source_cb(agent, **kwargs)``，
  加载后立即以 ``agent`` 调用一次以启动后台监听；回调可通过 ``globals.add_input_buffer``
  把外部消息写入全局输入缓冲区，由 Agent 主循环消费。
- **输出源（output_sources）**：插件通过 ``output_source_cb`` 回调消费 Agent 的
  最终文本回复（如推送到外部系统、日志、通知等）。回调签名
  ``output_source_cb(message, agent, **kwargs)``，其中 ``message`` 为
  :class:`OutputMessage`。Agent 完成任务（``_complete_task``）时通过
  :func:`broadcast_output_message` 异步广播，不阻塞主流程。

加载约定（与 callback_loader.py 一致）：
- 扫描目录下所有 ``.py`` 文件（跳过 ``__init__.py``）。
- 模块级回调：``input_source_cb`` / ``output_source_cb``，需带 ``source_name`` 属性。
- 工厂方法（任一命中）：``get_input_source_cb()`` / ``register_input_source_cb()``，
  ``get_output_source_cb()`` / ``register_output_source_cb()``，返回单个或列表回调。
- 文件头部 ``# requirements: pkg1 pkg2`` 注释声明依赖，加载前自动安装。
- 缺少 ``source_name`` 的回调被跳过（不启动、不登记）。

可逆效应：加载时登记到 PluginRegistry（``register_input_source(s)`` /
``register_output_source(s)``）；卸载时 :func:`stop_input_sources` 对每个已登记
输入源调用其 ``stop()`` 钩子并撤销登记，输出源仅撤销登记。
"""
import importlib.util
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from jarvis.jarvis_tools.plugin_registry import PluginRegistry
from jarvis.jarvis_utils.output import PrettyOutput

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
# source_name -> 回调对象（供 stop() 钩子与广播使用）
_registered_input_sources: Dict[str, Callable[..., Any]] = {}
_registered_output_sources: Dict[str, Callable[..., Any]] = {}

# 输出广播线程池（守护线程，不阻塞主流程；进程退出自动终止）
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    """获取模块级输出广播线程池（惰性创建，守护线程）。"""
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="io-sources-broadcast",
            )
        return _executor


# ---------------------------------------------------------------------------
# OutputMessage
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OutputMessage:
    """Agent 最终文本回复的不可变消息对象。

    字段:
        text: 最终文本回复内容
        agent_name: 产生回复的 Agent 名
        model_name: 产生回复的模型名
        timestamp: 产生时间（epoch 秒）
        extra: 附加元数据（默认空 dict）
    """

    text: str
    agent_name: str
    model_name: str
    timestamp: float
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 依赖安装
# ---------------------------------------------------------------------------
def _install_requirements(file_path: Path, requirements: List[str]) -> None:
    """按文件头部 ``# requirements:`` 注释安装依赖（失败仅告警，不阻断加载）。"""
    if not requirements:
        return
    PrettyOutput.auto_print(
        f"🔧 正在安装输入/输出源依赖 [{file_path.name}]: {', '.join(requirements)}"
    )
    try:
        result = subprocess.run(
            ["uv", "pip", "install"] + requirements,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            PrettyOutput.auto_print(f"✅ 依赖安装成功 [{file_path.name}]")
        else:
            PrettyOutput.auto_print(
                f"❌ 依赖安装失败 [{file_path.name}]: {result.stderr.strip()}"
            )
    except subprocess.TimeoutExpired:
        PrettyOutput.auto_print(
            f"❌ 依赖安装超时 [{file_path.name}] (超过 120 秒)"
        )
    except Exception as e:
        PrettyOutput.auto_print(f"❌ 依赖安装异常 [{file_path.name}]: {e}")


def _read_requirements(file_path: Path) -> List[str]:
    """读取文件头部 ``# requirements:`` 注释声明的依赖列表。"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# requirements:"):
                    deps_str = line[len("# requirements:") :].strip()
                    return deps_str.split() if deps_str else []
                if line and not line.startswith("#"):
                    # 只扫描文件头部的注释块
                    break
    except Exception as e:
        PrettyOutput.auto_print(
            f"⚠️ 读取输入/输出源依赖声明失败 [{file_path.name}]: {e}"
        )
    return []


def _unique_module_name(plugin_name: str, file_path: Path) -> str:
    """为源文件构造唯一模块名，避免跨插件/跨目录同名文件缓存碰撞。

    形如 ``jarvis_io_sources_<plugin>_<stem>``，其中插件名与文件名中的非
    标识符字符统一替换为 ``_``，保证不同插件目录下的同名 ``.py`` 文件可
    独立加载（互不覆盖 sys.modules 缓存）。
    """
    safe_plugin = re.sub(r"\W+", "_", plugin_name or "plugin")
    safe_stem = re.sub(r"\W+", "_", file_path.stem or "source")
    return f"jarvis_io_sources_{safe_plugin}_{safe_stem}"


def _load_module_from_file(file_path: Path, module_name: str) -> Any:
    """从文件路径加载 Python 模块（不依赖 sys.path / 顶层模块名）。

    使用 ``importlib.util.spec_from_file_location`` 直接按文件加载，模块名
    唯一（见 :func:`_unique_module_name`），从根源避免同名文件跨目录加载时
    的 ``sys.modules`` 缓存碰撞。
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {file_path} 创建模块 spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------
def _collect_candidates(module: Any, direct_name: str, factory_names: List[str]) -> List[Callable[..., Any]]:
    """按约定收集模块中的回调候选。

    优先级：
    1) 模块级直接导出（``input_source_cb`` / ``output_source_cb``）
    2) 工厂方法（``get_*_cb()`` / ``register_*_cb()``），返回单个或列表
    """
    candidates: List[Callable[..., Any]] = []
    if hasattr(module, direct_name):
        obj = getattr(module, direct_name)
        if callable(obj):
            candidates.append(obj)
    for factory_name in factory_names:
        if hasattr(module, factory_name):
            factory = getattr(module, factory_name)
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
                        f"⚠️ 工厂方法 {factory_name} 执行错误 [{type(e).__name__}]: {e}"
                    )
    return candidates


def _load_sources_from_dirs(
    dirs: List[str],
    plugin_name: str,
    agent: Any,
    *,
    kind: str,
    direct_name: str,
    factory_names: List[str],
    register_fn: Callable[[str, str], None],
    register_batch_fn: Callable[[str, List[str]], None],
    cache: Dict[str, Callable[..., Any]],
    start_cb: bool,
) -> List[str]:
    """扫描目录加载输入/输出源回调并登记到 PluginRegistry。

    返回: 本次成功登记（含已缓存去重）的 source_name 列表。
    """
    registered: List[str] = []
    for d in dirs:
        p_dir = Path(d)
        if not p_dir.exists() or not p_dir.is_dir():
            continue
        for file_path in p_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue
            try:
                # 安装依赖
                requirements = _read_requirements(file_path)
                if requirements:
                    _install_requirements(file_path, requirements)

                # 从文件路径加载模块（唯一模块名，避免同名文件缓存碰撞）
                module_name = _unique_module_name(plugin_name, file_path)
                module = _load_module_from_file(file_path, module_name)
                PrettyOutput.auto_print(
                    f"📦 从配置文件加载{kind}文件：{file_path}"
                )

                candidates = _collect_candidates(module, direct_name, factory_names)
                for cb in candidates:
                    source_name = getattr(cb, "source_name", None)
                    if not source_name:
                        # 缺少 source_name 的回调被跳过（不启动、不登记）
                        PrettyOutput.auto_print(
                            f"⚠️ {file_path.name} 的回调缺少 source_name 属性，已跳过"
                        )
                        continue
                    source_name = str(source_name)
                    if start_cb:
                        # 输入源：先启动成功再登记（启动失败不登记，异常隔离）
                        try:
                            cb(agent)
                        except Exception as e:
                            PrettyOutput.auto_print(
                                f"⚠️ 输入源 {source_name} 启动失败 [{type(e).__name__}]: {e}"
                            )
                            continue
                    cache[source_name] = cb
                    register_fn(plugin_name, source_name)
                    if source_name not in registered:
                        registered.append(source_name)
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 从 {file_path} 加载{kind}失败: {e}")
    if registered:
        register_batch_fn(plugin_name, registered)
    return registered


def load_input_sources(dirs: List[str], plugin_name: str, agent: Any) -> List[str]:
    """加载输入源回调并启动后台监听。

    参数:
        dirs: 输入源脚本目录列表
        plugin_name: 来源插件名（用于 PluginRegistry 登记）
        agent: Agent 实例（传给回调启动监听）

    返回:
        List[str]: 本次登记（含去重）的输入源名列表
    """
    return _load_sources_from_dirs(
        dirs,
        plugin_name,
        agent,
        kind="输入源",
        direct_name="input_source_cb",
        factory_names=["get_input_source_cb", "register_input_source_cb"],
        register_fn=lambda p, s: PluginRegistry.instance().register_input_source(p, s),
        register_batch_fn=lambda p, s: PluginRegistry.instance().register_input_sources(p, s),
        cache=_registered_input_sources,
        start_cb=True,
    )


def load_output_sources(dirs: List[str], plugin_name: str, agent: Any) -> List[str]:
    """加载输出源回调并登记。

    参数:
        dirs: 输出源脚本目录列表
        plugin_name: 来源插件名（用于 PluginRegistry 登记）
        agent: Agent 实例（当前仅用于日志上下文，不触发调用）

    返回:
        List[str]: 本次登记（含去重）的输出源名列表
    """
    return _load_sources_from_dirs(
        dirs,
        plugin_name,
        agent,
        kind="输出源",
        direct_name="output_source_cb",
        factory_names=["get_output_source_cb", "register_output_source_cb"],
        register_fn=lambda p, s: PluginRegistry.instance().register_output_source(p, s),
        register_batch_fn=lambda p, s: PluginRegistry.instance().register_output_sources(p, s),
        cache=_registered_output_sources,
        start_cb=False,
    )


def stop_input_sources(plugin_name: str) -> None:
    """停止并撤销指定插件的全部输入源。

    对每个已登记输入源调用其 ``stop()`` 钩子（若回调对象或其模块提供），
    随后从 PluginRegistry 撤销登记并清空全局缓存。
    """
    from jarvis.jarvis_tools.plugin_registry import PluginRegistry

    registry = PluginRegistry.instance()
    source_names = registry.get_plugin_input_sources(plugin_name)
    for source_name in source_names:
        cb = _registered_input_sources.pop(source_name, None)
        if cb is None:
            continue
        stop_fn = getattr(cb, "stop", None)
        if not callable(stop_fn):
            # 回退：模块级 stop() 函数（回调所在模块）
            module = getattr(cb, "__module__", None)
            if module:
                stop_fn = getattr(sys.modules.get(module), "stop", None)
        if callable(stop_fn):
            try:
                stop_fn()
            except Exception as e:
                PrettyOutput.auto_print(
                    f"⚠️ 输入源 {source_name} stop() 钩子执行失败 [{type(e).__name__}]: {e}"
                )
    registry.clear_input_sources(plugin_name)


def stop_output_sources(plugin_name: str) -> None:
    """撤销指定插件的全部输出源登记并清空缓存。"""
    from jarvis.jarvis_tools.plugin_registry import PluginRegistry

    registry = PluginRegistry.instance()
    source_names = registry.get_plugin_output_sources(plugin_name)
    for source_name in source_names:
        _registered_output_sources.pop(source_name, None)
    registry.clear_output_sources(plugin_name)


# ---------------------------------------------------------------------------
# 输出广播
# ---------------------------------------------------------------------------
def broadcast_output_message(agent: Any, text: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """把 Agent 的最终文本回复异步广播给所有已注册输出源。

    构造 :class:`OutputMessage` 后，用模块级线程池为每个输出源提交一个任务，
    立即返回（不阻塞主流程）。单个输出源异常被隔离，不影响其他输出源。

    参数:
        agent: Agent 实例（提供 name 与 model.model_name）
        text: 最终文本回复
        extra: 附加元数据（可选）
    """
    if not _registered_output_sources:
        return
    try:
        agent_name = getattr(agent, "name", "") or ""
        model_name = ""
        model = getattr(agent, "model", None)
        if model is not None:
            model_name = getattr(model, "model_name", "") or ""
        message = OutputMessage(
            text=text,
            agent_name=agent_name,
            model_name=model_name,
            timestamp=time.time(),
            extra=dict(extra or {}),
        )
    except Exception as e:
        PrettyOutput.auto_print(f"⚠️ 构造 OutputMessage 失败: {e}")
        return

    sources = list(_registered_output_sources.items())
    executor = _get_executor()
    for source_name, cb in sources:
        try:
            executor.submit(_deliver_output, source_name, cb, message, agent)
        except Exception as e:
            PrettyOutput.auto_print(
                f"⚠️ 提交输出源 {source_name} 广播任务失败: {e}"
            )


def _deliver_output(
    source_name: str,
    cb: Callable[..., Any],
    message: OutputMessage,
    agent: Any,
) -> None:
    """在线程池中执行单个输出源回调（异常隔离）。"""
    try:
        cb(message, agent)
    except Exception as e:
        PrettyOutput.auto_print(
            f"⚠️ 输出源 {source_name} 处理失败 [{type(e).__name__}]: {e}"
        )


def shutdown() -> None:
    """关闭输出广播线程池（进程退出时调用，幂等）。"""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False)
            _executor = None


__all__ = [
    "OutputMessage",
    "load_input_sources",
    "load_output_sources",
    "stop_input_sources",
    "stop_output_sources",
    "broadcast_output_message",
    "shutdown",
]
