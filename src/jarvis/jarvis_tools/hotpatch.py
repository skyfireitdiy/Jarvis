# -*- coding: utf-8 -*-
"""hotpatch 工具模块

提供任意代码热补丁能力：在运行中的 Jarvis 进程内热更新/注入任意
Python 模块/函数的代码，立即生效，无需重启进程。

支持两种使用方式：
1. 生效已修改代码（reload）：代码已通过 edit/write 写入磁盘后，热更新
   指定模块（支持批量多模块），reload 后自动把已有类实例重绑到新类，
   使新方法立即生效。
2. 临时注入代码（调试自身）：从内存注入任意语句/代码块/函数/全新模块，
   不落盘、不持久化，仅本次运行有效。命名空间注入 agent / sys / globals，
   可访问/修改 agent 内外的任意进程内对象。

实现原理：
- importlib.reload 重新执行已有模块代码；
- types.ModuleType + exec 从内存代码动态创建模块，注册进 sys.modules；
- gc.get_objects() 遍历堆，把旧类实例 __class__ 重绑到新类（自动切换新方法）；
- sys.modules 清理 + importlib.invalidate_caches 处理依赖与新增文件；
- 全部异常捕获并返回错误信息，绝不向 Agent 主流程抛出异常。
"""

import gc
import importlib
import os
import shutil
import sys
import types
from typing import Any, Dict, List

from jarvis.jarvis_utils.output import PrettyOutput


class HotpatchTool:
    """运行时热补丁工具：热更新/注入任意 Python 代码并立即生效"""

    name = "hotpatch"
    description = (
        "任意代码热补丁：在运行中的 Jarvis 进程内热更新/注入任意 Python 代码并立即生效，"
        "无需重启进程。两种方式：1) module_name 热更新已有模块（支持逗号分隔批量多模块，"
        "reload 后自动重绑已有类实例到新类）；2) code 临时注入任意语句/代码块/函数/全新模块"
        "（不落盘、不持久化，命名空间注入 agent/sys/globals，可访问 agent 内外任意对象）。"
        "适合自进化场景下运行时调整自身行为。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "module_name": {
                "type": "string",
                "description": "方式①：要热更新的已有模块名（如 jarvis.jarvis_tools.load_rule），"
                "支持逗号分隔批量多模块，如 'a,b,c'。与 new_module_name 二选一",
            },
            "file_path": {
                "type": "string",
                "description": "方式①：模块文件路径，据此推导模块名（与 module_name 二选一）",
            },
            "new_module_name": {
                "type": "string",
                "description": "方式②：要注入的全新模块名（如 my_plugin），与 code 配合从内存"
                "创建新模块，注册进 sys.modules 后立即可 import",
            },
            "code": {
                "type": "string",
                "description": "方式②：要注入的代码。可为任意语句/代码块（如 print(agent.data)）、"
                "函数定义（def f(): ...）或配合 new_module_name 作为新模块源码。命名空间注入"
                "agent/sys/globals，可访问运行时对象",
            },
            "clear_cache": {
                "type": "boolean",
                "description": "方式①：是否从 sys.modules 清除模块缓存后重新导入，"
                "默认 false（用 importlib.reload）。当模块有依赖方需强制刷新时设 true",
            },
            "rebind_instances": {
                "type": "boolean",
                "description": "方式①：是否自动把已有类实例的 __class__ 重绑到新类，"
                "使新方法立即生效。默认 true",
            },
        },
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行热补丁

        参数:
            args (Dict): 包含 module_name / file_path / new_module_name / code /
                         clear_cache / rebind_instances 的字典

        返回:
            Dict[str, Any]: 包含成功状态、补丁结果或错误信息的字典
        """
        try:
            module_name = (args.get("module_name") or "").strip()
            new_module_name = (args.get("new_module_name") or "").strip()
            file_path = (args.get("file_path") or "").strip()
            code = args.get("code")
            clear_cache = bool(args.get("clear_cache", False))
            rebind_instances = bool(args.get("rebind_instances", True))

            # 方式②：注入全新模块（new_module_name + code）
            if new_module_name:
                if not code:
                    return self._err("注入全新模块时必须提供 code")
                return self._inject_new_module(new_module_name, code)

            # 方式②：执行任意语句/代码块（仅 code，无 module_name/new_module_name）
            if code is not None and not module_name and not file_path:
                return self._execute_statement(code, args)

            # 方式①：热更新已有模块（可批量）
            if not module_name and file_path:
                module_name = self._derive_module_name(file_path)
            if not module_name:
                return self._err("必须提供 module_name、new_module_name 或 code 之一")

            return self._apply_patch(module_name, clear_cache, rebind_instances)
        except Exception as e:
            return self._err(f"热补丁失败: {str(e)}")

    # ------------------------------------------------------------------
    # 方式②：注入全新模块
    # ------------------------------------------------------------------
    def _inject_new_module(self, module_name: str, code: str) -> Dict[str, Any]:
        """从内存代码注入全新模块，注册进 sys.modules 后立即可 import。"""
        try:
            module = types.ModuleType(module_name)
            exec(compile(code, f"<hotpatch:{module_name}>", "exec"), module.__dict__)
            sys.modules[module_name] = module
            PrettyOutput.auto_print(f"🧩 注入全新模块: {module_name}")
            return {
                "success": True,
                "module": module_name,
                "mode": "new_module",
                "error": "",
            }
        except Exception as e:
            return {
                "success": False,
                "module": module_name,
                "mode": "new_module",
                "error": f"注入全新模块 {module_name} 失败: {str(e)}",
            }

    # ------------------------------------------------------------------
    # 方式②：执行任意语句/代码块（含 agent 上下文）
    # ------------------------------------------------------------------
    def _execute_statement(self, code: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行任意语句/代码块，命名空间注入 agent/sys/globals。

        支持任意多行语句/代码块（如 print(agent.data)），不限于函数/模块定义。
        """
        try:
            agent = args.get("agent")
            namespace: Dict[str, Any] = {
                "agent": agent,
                "sys": sys,
                "globals": globals,
                "__builtins__": __builtins__,
            }
            exec(compile(code, "<hotpatch:statement>", "exec"), namespace)

            # 若代码定义了可调用对象，注入到本模块命名空间便于后续引用
            func_names = [
                k
                for k, v in namespace.items()
                if callable(v) and not k.startswith("__")
            ]
            if func_names:
                for fn in func_names:
                    globals()[fn] = namespace[fn]
            PrettyOutput.auto_print("⚡ 已执行注入代码块")
            return {
                "success": True,
                "mode": "statement",
                "defined": func_names,
                "error": "",
            }
        except Exception as e:
            return {
                "success": False,
                "mode": "statement",
                "defined": [],
                "error": f"执行注入代码失败: {str(e)}",
            }

    # ------------------------------------------------------------------
    # 方式①：热更新已有模块（可批量 + 实例重绑）
    # ------------------------------------------------------------------
    def _apply_patch(
        self, module_name: str, clear_cache: bool, rebind_instances: bool
    ) -> Dict[str, Any]:
        """对指定模块执行热更新，支持逗号分隔批量多模块。

        返回 dict：{"success": bool, "module": str, "mode": "reload",
                    "reloaded": [...], "rebound": int, "error": str}
        """
        names = [n.strip() for n in module_name.split(",") if n.strip()]
        if not names:
            return self._err("module_name 为空")
        reloaded: List[str] = []
        rebound_total = 0
        errors: List[str] = []
        for name in names:
            try:
                rebound = self._reload_one(name, clear_cache, rebind_instances)
                reloaded.append(name)
                rebound_total += rebound
            except Exception as e:
                errors.append(f"{name}: {str(e)}")
        success = not errors
        result: Dict[str, Any] = {
            "success": success,
            "module": module_name,
            "mode": "reload",
            "reloaded": reloaded,
            "rebound": rebound_total,
            "error": "; ".join(errors),
        }
        if success:
            PrettyOutput.auto_print(
                f"🔧 热补丁成功: {module_name} (reload {len(reloaded)} 个, 重绑实例 {rebound_total} 个)"
            )
        return result

    def _reload_one(
        self, module_name: str, clear_cache: bool, rebind_instances: bool
    ) -> int:
        """reload 单个模块，返回重绑的实例数。"""
        importlib.invalidate_caches()
        old_classes: Dict[str, type] = {}
        if rebind_instances and module_name in sys.modules:
            old_classes = self._collect_classes(sys.modules[module_name], module_name)

        if clear_cache:
            sys.modules.pop(module_name, None)
            module = importlib.import_module(module_name)
        else:
            if module_name in sys.modules:
                # 清理 pyc 缓存，避免 reload 复用过期字节码（源码已改但 pyc 未失效）
                self._clear_pycache(module_name)
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

        if rebind_instances and old_classes:
            return self._rebind_instances(module, module_name, old_classes)
        return 0

    @staticmethod
    def _clear_pycache(module_name: str) -> None:
        """删除模块 __file__ 对应目录下的 __pycache__，强制 reload 重新编译源码。"""
        module = sys.modules.get(module_name)
        if module is None:
            return
        file_path = getattr(module, "__file__", None)
        if not file_path:
            return
        pycache = os.path.join(os.path.dirname(file_path), "__pycache__")
        if os.path.isdir(pycache):
            try:
                shutil.rmtree(pycache)
            except OSError:
                pass

    @staticmethod
    def _collect_classes(module: types.ModuleType, module_name: str) -> Dict[str, type]:
        """收集模块内定义的类（name -> 类对象）。"""
        return {
            name: cls
            for name, cls in module.__dict__.items()
            if isinstance(cls, type) and getattr(cls, "__module__", None) == module_name
        }

    def _rebind_instances(
        self,
        module: types.ModuleType,
        module_name: str,
        old_classes: Dict[str, type],
    ) -> int:
        """把旧类实例的 __class__ 重绑到新类，使新方法立即生效。"""
        new_classes = self._collect_classes(module, module_name)
        if not new_classes:
            return 0
        rebound = 0
        for obj in gc.get_objects():
            cls = type(obj)
            if cls.__module__ != module_name:
                continue
            for name, new_cls in new_classes.items():
                old_cls = old_classes.get(name)
                # 精确匹配旧类（不含子类），且新旧确实是不同对象
                if old_cls is not None and cls is old_cls and cls is not new_cls:
                    try:
                        obj.__class__ = new_cls
                        rebound += 1
                    except TypeError:
                        pass  # __slots__ / C 类型无法重绑，跳过
                    break
        return rebound

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _derive_module_name(self, file_path: str) -> str:
        """从文件路径推导模块名。

        优先按 jarvis 包内路径推导（如 src/jarvis/jarvis_tools/x.py →
        jarvis.jarvis_tools.x），否则用文件 stem 作为模块名。
        """
        try:
            p = os.path.abspath(os.path.expanduser(file_path))
            parts = p.replace(os.sep, "/").split("/")
            for i in range(len(parts) - 1, -1, -1):
                if parts[i] == "jarvis" and i + 1 < len(parts):
                    sub = parts[i + 1 :]
                    if sub[-1].endswith(".py"):
                        sub[-1] = sub[-1][:-3]
                    return ".".join(sub)
            return os.path.splitext(os.path.basename(p))[0]
        except Exception:
            return os.path.splitext(os.path.basename(file_path))[0]

    @staticmethod
    def _err(msg: str) -> Dict[str, Any]:
        return {"success": False, "stdout": "", "stderr": msg}
