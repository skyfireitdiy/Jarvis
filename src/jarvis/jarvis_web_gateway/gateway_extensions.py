# -*- coding: utf-8 -*-
"""插件网关扩展注册表（gateway 扩展点）。

插件 config.yaml 通过 ``gateway`` 字段声明自带的网关扩展：自定义 API 端点
（routes）与网关中间件（middleware），安装后自动挂载到网关，使插件能主动
接收外部事件（webhook、回调、IoT 上报），从「工具集」升级为「独立服务」：

    gateway:
      routes:
        - path: "/api/plugins/dhttp/webhook"
          method: "POST"
          handler: "{{plugin_dir}}/gateway_routes"
      middleware:
        - name: "audit_middleware"
          handler: "{{plugin_dir}}/gateway_middleware"

- 路由 handler 目录内 .py 文件导出 ``route_handler(request)`` 函数
  （可带 ``ROUTE_PATH`` / ``ROUTE_METHOD`` 常量覆盖 config 声明）；
- 中间件 handler 目录内 .py 文件导出 ``middleware_handler(request,
  call_next)`` 函数。

安全：插件注册的路由默认携带 token 认证（``verify_token`` 依赖），避免
未授权访问。路径冲突：插件路由与内置路由冲突时不挂载并告警，不覆盖内置。

与其它扩展点一样遵循可逆效应：加载时登记到 PluginRegistry，卸载时精确撤销。
"""

from __future__ import annotations

import importlib
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from fastapi import Depends
from fastapi import Request


@dataclass
class GatewayRoute:
    """插件注册的网关路由定义。"""

    path: str
    method: str
    handler: Optional[str]
    plugin: Optional[str]
    function: Optional[Callable[..., Any]]
    # 后台执行模式：True 时调用立即返回 202 + task_id，handler 在后台线程池执行
    background: bool = False


@dataclass
class GatewayMiddleware:
    """插件注册的网关中间件定义。"""

    name: str
    handler: Optional[str]
    plugin: Optional[str]
    function: Optional[Callable[..., Any]]


class PluginBackgroundTaskManager:
    """插件后台任务管理器（进程内全局单例）。

    为插件网关路由提供「后台执行」能力：调用方提交耗时 handler 后立即返回
    task_id，handler 在独立线程池中执行，不占用 FastAPI 默认线程池，从而
    避免耗时操作阻塞网关其他正常请求与流程（Issue #353）。

    特性：
    - 独立 ``ThreadPoolExecutor``（默认 4 线程），与 FastAPI 默认线程池隔离；
    - 任务状态机：pending -> running -> completed / failed；
    - 任务结果/错误可查询，结果带过期清理（默认 1 小时）；
    - 线程安全（内部锁保护任务字典）。
    """

    _instance: Optional["PluginBackgroundTaskManager"] = None

    # 任务状态
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    # 任务结果保留时长（秒），超时后清理
    DEFAULT_TTL = 3600

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="plugin-bg-task"
        )
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    @classmethod
    def instance(cls) -> "PluginBackgroundTaskManager":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = PluginBackgroundTaskManager()
        return cls._instance

    def submit(
        self,
        fn: Callable[[Any], Any],
        request: Any,
        plugin: Optional[str] = None,
        route_path: str = "",
    ) -> str:
        """提交一个后台任务，立即返回 task_id。

        参数:
            fn: 要后台执行的 handler（接收 request 参数）
            request: 传给 handler 的请求对象
            plugin: 来源插件名（用于追踪）
            route_path: 触发任务的路由路径

        返回:
            task_id（uuid 字符串）
        """
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "task_id": task_id,
                "plugin": plugin,
                "route": route_path,
                "status": self.STATUS_PENDING,
                "created_at": time.time(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }
        self._executor.submit(self._run, task_id, fn, request)
        return task_id

    def _run(self, task_id: str, fn: Callable[[Any], Any], request: Any) -> None:
        """在线程池中执行 handler 并更新任务状态。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = self.STATUS_RUNNING
            task["started_at"] = time.time()
        try:
            result = fn(request)
            with self._lock:
                task = self._tasks.get(task_id)
                if task is not None:
                    task["status"] = self.STATUS_COMPLETED
                    task["finished_at"] = time.time()
                    task["result"] = result
        except Exception as e:  # noqa: BLE001 - 后台任务异常需完整捕获并记录
            with self._lock:
                task = self._tasks.get(task_id)
                if task is not None:
                    task["status"] = self.STATUS_FAILED
                    task["finished_at"] = time.time()
                    task["error"] = f"{type(e).__name__}: {e}"

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查询任务状态（含结果/错误），任务不存在返回 None。

        返回的 dict 为可序列化副本（去掉内部时间戳等非必要字段）。
        """
        self._cleanup()
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            return {
                "task_id": task["task_id"],
                "plugin": task["plugin"],
                "route": task["route"],
                "status": task["status"],
                "created_at": task["created_at"],
                "started_at": task["started_at"],
                "finished_at": task["finished_at"],
                "result": task["result"],
                "error": task["error"],
            }

    def _cleanup(self) -> None:
        """清理超过 TTL 的已完成/失败任务，避免内存无限增长。"""
        now = time.time()
        with self._lock:
            expired = [
                tid
                for tid, t in self._tasks.items()
                if t["status"] in (self.STATUS_COMPLETED, self.STATUS_FAILED)
                and now - (t["finished_at"] or now) > self.DEFAULT_TTL
            ]
            for tid in expired:
                self._tasks.pop(tid, None)

    def clear(self) -> None:
        """清空全部任务登记（主要用于测试隔离）。"""
        with self._lock:
            self._tasks.clear()

    def shutdown(self) -> None:
        """关闭线程池（进程退出时调用）。"""
        self._executor.shutdown(wait=False, cancel_futures=True)


class GatewayExtensionRegistry:
    """插件网关扩展注册表（进程内全局单例）。

    维护插件声明的路由/中间件定义，并提供挂载（mount）到 FastAPI app 与
    卸载（unmount）能力。路由挂到独立 APIRouter，中间件通过
    ``add_middleware`` 挂载；卸载时从 app 精确移除。
    """

    _instance: Optional["GatewayExtensionRegistry"] = None

    # 插件中间件动态子类名前缀（用于从 app.user_middleware 识别/移除）
    _PLUGIN_MIDDLEWARE_PREFIX = "PluginMiddleware_"

    def __init__(self) -> None:
        self._routes: Dict[str, GatewayRoute] = {}
        self._middleware: Dict[str, GatewayMiddleware] = {}
        # 当前已挂载的 app 引用与认证依赖（供 install/uninstall 免重启重载）
        self._mounted_app: Optional[Any] = None
        self._verify_token: Optional[Callable] = None
        # 后台任务状态查询接口是否已挂载（幂等标记）
        self._task_status_mounted: bool = False

    @classmethod
    def instance(cls) -> "GatewayExtensionRegistry":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = GatewayExtensionRegistry()
        return cls._instance

    # ------------------------------------------------------------------
    # 注册 / 撤销（声明层）
    # ------------------------------------------------------------------
    def register_route(
        self,
        path: str,
        method: str,
        handler: Optional[str] = None,
        plugin: Optional[str] = None,
        function: Optional[Callable[..., Any]] = None,
        background: bool = False,
    ) -> None:
        """注册单个网关路由声明。

        参数:
            path: 路由路径（如 /api/plugins/dhttp/webhook）
            method: HTTP 方法（GET/POST/PUT/DELETE/PATCH，大小写不敏感）
            handler: 实现目录路径（目录内 .py 导出 route_handler）
            plugin: 来源插件名（可逆效应来源追踪）
            function: 已加载的路由处理函数（可选，优先于 handler 目录加载）
            background: 后台执行模式。True 时调用立即返回 202 + task_id，
                handler 在后台线程池执行，避免耗时操作阻塞网关其他请求。
        """
        method = (method or "GET").upper()
        key = f"{method} {path}"
        self._routes[key] = GatewayRoute(
            path=path,
            method=method,
            handler=handler,
            plugin=plugin,
            function=function,
            background=bool(background),
        )

    def unregister_route(self, path: str, method: str) -> bool:
        """撤销单个网关路由声明。"""
        method = (method or "GET").upper()
        key = f"{method} {path}"
        if key not in self._routes:
            return False
        del self._routes[key]
        return True

    def register_middleware(
        self,
        name: str,
        handler: Optional[str] = None,
        plugin: Optional[str] = None,
        function: Optional[Callable[..., Any]] = None,
    ) -> None:
        """注册单个网关中间件声明。

        参数:
            name: 中间件名（唯一标识）
            handler: 实现目录路径（目录内 .py 导出 middleware_handler）
            plugin: 来源插件名（可逆效应来源追踪）
            function: 已加载的中间件处理函数（可选，优先于 handler 目录加载）
        """
        self._middleware[name] = GatewayMiddleware(
            name=name,
            handler=handler,
            plugin=plugin,
            function=function,
        )

    def unregister_middleware(self, name: str) -> bool:
        """撤销单个网关中间件声明。"""
        if name not in self._middleware:
            return False
        del self._middleware[name]
        return True

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_route(self, path: str, method: str) -> Optional[GatewayRoute]:
        """按路径与方法查询路由。"""
        method = (method or "GET").upper()
        return self._routes.get(f"{method} {path}")

    def list_routes(self) -> List[Dict[str, Any]]:
        """列出全部已注册路由的可序列化信息。"""
        return [
            {
                "path": route.path,
                "method": route.method,
                "handler": route.handler,
                "plugin": route.plugin,
                "background": route.background,
            }
            for route in sorted(self._routes.values(), key=lambda r: (r.path, r.method))
        ]

    def list_middleware(self) -> List[Dict[str, Any]]:
        """列出全部已注册中间件的可序列化信息。"""
        return [
            {
                "name": middleware.name,
                "handler": middleware.handler,
                "plugin": middleware.plugin,
            }
            for middleware in sorted(self._middleware.values(), key=lambda m: m.name)
        ]

    def get_plugin_routes(self, plugin: str) -> List[str]:
        """返回指定插件注册的路由键列表（"METHOD path"）。"""
        return sorted(
            key for key, route in self._routes.items() if route.plugin == plugin
        )

    def get_plugin_middleware(self, plugin: str) -> List[str]:
        """返回指定插件注册的中间件名列表。"""
        return sorted(
            name
            for name, middleware in self._middleware.items()
            if middleware.plugin == plugin
        )

    # ------------------------------------------------------------------
    # 目录加载（gateway 扩展点）
    # ------------------------------------------------------------------
    @staticmethod
    def _infer_source_plugin(directory: str) -> Optional[str]:
        """从实现目录路径反推来源插件名（可逆效应来源追踪）。

        当目录路径形如 <...>/plugins/<plugin_name>/<subdir> 时返回插件名，
        否则返回 None（表示非插件来源的实现目录）。
        """
        try:
            normalized = directory.replace("\\", "/")
            marker = "/plugins/"
            if marker in normalized:
                return normalized.split(marker, 1)[1].split("/", 1)[0]
        except Exception:
            pass
        return None

    def _load_handler_function(
        self, directory: str, expected_attr: str, display_name: str
    ) -> Optional[Callable[..., Any]]:
        """从实现目录加载处理函数（目录内 .py 导出指定函数）。

        目录内每个 .py 文件（跳过 __init__.py）加载，取第一个导出
        ``expected_attr`` 函数的模块。加载失败仅告警。
        """
        from jarvis.jarvis_utils.output import PrettyOutput

        if (
            not directory
            or not os.path.exists(directory)
            or not os.path.isdir(directory)
        ):
            return None
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".py") or filename.startswith("__"):
                continue
            module_path = os.path.join(directory, filename)
            module_name = filename[:-3]
            try:
                # 按文件路径加载，避免裸模块名与 sys.modules 缓存冲突
                # （同名模块可能已被其它插件/测试加载，import_module 会返回缓存）。
                spec = importlib.util.spec_from_file_location(
                    f"jarvis_plugin_gateway_{module_name}", module_path
                )
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                function = getattr(module, expected_attr, None)
                if callable(function):
                    return function
            except Exception as e:
                PrettyOutput.auto_print(f"⚠️ 加载{display_name} {module_name} 失败: {e}")
        return None

    def load_plugin_gateway(self, app: Any, verify_token: Callable) -> None:
        """从插件声明的 gateway 配置加载并挂载到 app（gateway 扩展点）。

        插件 config.yaml 通过 ``gateway`` 字段声明路由（path/method/handler）
        与中间件（name/handler），handler 为实现目录（目录内 .py 导出
        ``route_handler(request)`` / ``middleware_handler(request, call_next)``）。
        路由默认带 token 认证；与内置路由冲突时不挂载并告警。

        加载成功后登记到 PluginRegistry（可逆效应），供卸载时精确撤销。
        """
        from jarvis.jarvis_utils.config import get_plugin_gateway_config
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        gateway_config = get_plugin_gateway_config()
        registry = PluginRegistry.instance()

        # 加载路由声明
        for entry in gateway_config.get("routes", []):
            path = str(entry.get("path") or "").strip()
            method = str(entry.get("method") or "GET").strip().upper()
            handler = str(entry.get("handler") or "").strip()
            if not path or not handler:
                continue
            # 后台执行模式：background: true 时调用立即返回 202 + task_id
            background = bool(entry.get("background") or False)
            source_plugin = self._infer_source_plugin(handler)
            function = self._load_handler_function(
                handler, "route_handler", f"路由 {method} {path}"
            )
            if function is None:
                PrettyOutput.auto_print(
                    f"⚠️ 路由 {method} {path} 实现目录 {handler} 未找到 "
                    f"route_handler 函数，已跳过"
                )
                continue
            self.register_route(
                path,
                method,
                handler=handler,
                plugin=source_plugin,
                function=function,
                background=background,
            )
            if source_plugin:
                registry.register_gateway_route(source_plugin, path, method, handler)

        # 加载中间件声明
        for entry in gateway_config.get("middleware", []):
            name = str(entry.get("name") or "").strip()
            handler = str(entry.get("handler") or "").strip()
            if not name or not handler:
                continue
            source_plugin = self._infer_source_plugin(handler)
            function = self._load_handler_function(
                handler, "middleware_handler", f"中间件 {name}"
            )
            if function is None:
                PrettyOutput.auto_print(
                    f"⚠️ 中间件 {name} 实现目录 {handler} 未找到 "
                    f"middleware_handler 函数，已跳过"
                )
                continue
            self.register_middleware(
                name, handler=handler, plugin=source_plugin, function=function
            )
            if source_plugin:
                registry.register_gateway_middleware(source_plugin, name, handler)

        # 挂载到 app
        if app is not None:
            self.mount(app, verify_token)

    # ------------------------------------------------------------------
    # 挂载 / 卸载（app 层）
    # ------------------------------------------------------------------
    def mount(self, app: Any, verify_token: Callable) -> None:
        """把已注册的插件路由/中间件挂载到 FastAPI app。

        幂等：重复调用不会重复挂载。路由挂到独立 APIRouter 后 include 到 app；
        中间件通过 add_middleware 挂载。
        """
        from fastapi import APIRouter
        from starlette.middleware.base import BaseHTTPMiddleware

        self._mounted_app = app
        self._verify_token = verify_token

        # 挂载路由：先移除旧插件路由（幂等），再重新挂载
        self._remove_plugin_routes_from_app(app)
        if self._routes:
            router = APIRouter()
            for route in self._routes.values():
                function = route.function
                if function is None:
                    continue
                # 路径冲突检查：内置路由已存在时跳过（不覆盖内置）
                if self._builtin_route_exists(app, route.path, route.method):
                    from jarvis.jarvis_utils.output import PrettyOutput

                    PrettyOutput.auto_print(
                        f"⚠️ 插件路由 {route.method} {route.path} 与内置路由冲突，"
                        f"已跳过（不覆盖内置）"
                    )
                    continue

                # 包装插件路由函数：插件实现导出 route_handler(request)（无需
                # FastAPI 类型注解），此处注入 Request 对象再调用。
                #
                # 支持三种模式：
                # 1. background=True：调用立即返回 202 + task_id，handler 在
                #    后台线程池执行，避免耗时操作阻塞网关其他请求（Issue #353）；
                # 2. async handler（async def route_handler）：直接作为 FastAPI
                #    async 端点，不占用线程池；
                # 3. 同步 handler：FastAPI 用线程池执行（向后兼容默认行为）。
                def _make_route_wrapper(
                    handler: Callable[..., Any],
                    background: bool,
                    route_path: str,
                    route_plugin: Optional[str],
                ) -> Callable[..., Any]:
                    import inspect

                    from fastapi.responses import JSONResponse

                    if background:
                        task_manager = PluginBackgroundTaskManager.instance()

                        def _bg_wrapper(request: Request) -> Any:
                            task_id = task_manager.submit(
                                handler, request, plugin=route_plugin, route_path=route_path
                            )
                            return JSONResponse(
                                status_code=202,
                                content={
                                    "task_id": task_id,
                                    "status": PluginBackgroundTaskManager.STATUS_PENDING,
                                    "message": "任务已提交，后台执行中",
                                },
                            )

                        return _bg_wrapper

                    if inspect.iscoroutinefunction(handler):

                        async def _async_wrapper(request: Request) -> Any:
                            return await handler(request)

                        return _async_wrapper

                    def _wrapper(request: Request) -> Any:
                        return handler(request)

                    return _wrapper

                router.add_api_route(
                    route.path,
                    _make_route_wrapper(
                        function, route.background, route.path, route.plugin
                    ),
                    methods=[route.method],
                    dependencies=[Depends(verify_token)],
                    name=f"plugin_{route.method}_{route.path}",
                )
            app.include_router(router)

        # 挂载插件后台任务状态查询接口（GET /api/plugins/tasks/{task_id}）。
        # 供 background 模式路由提交的任务查询进度/结果。
        self._mount_task_status_route(app, verify_token)

        # 挂载中间件：先移除旧插件中间件（幂等，暂不重建栈），再重新挂载，
        # 最后统一重建中间件栈使新增中间件生效。
        self._remove_plugin_middleware_from_app(app, rebuild=False)
        for middleware in self._middleware.values():
            function = middleware.function
            if function is None:
                continue
            middleware_cls = type(
                f"{self._PLUGIN_MIDDLEWARE_PREFIX}{middleware.name}",
                (BaseHTTPMiddleware,),
                {},
            )
            app.add_middleware(middleware_cls, dispatch=function)
        app.middleware_stack = app.build_middleware_stack()

    def _mount_task_status_route(self, app: Any, verify_token: Callable) -> None:
        """挂载插件后台任务状态查询接口（GET /api/plugins/tasks/{task_id}）。

        幂等：重复调用不会重复挂载。任务不存在返回 404；任务存在返回其
        状态（pending/running/completed/failed）与结果/错误。
        """
        from fastapi import APIRouter
        from fastapi import HTTPException

        # 幂等：若已挂载过则跳过
        if self._task_status_mounted:
            return

        task_manager = PluginBackgroundTaskManager.instance()

        router = APIRouter()

        @router.get("/api/plugins/tasks/{task_id}")
        async def get_task_status(task_id: str) -> Dict[str, Any]:
            status = task_manager.get_status(task_id)
            if status is None:
                raise HTTPException(status_code=404, detail="task not found")
            return status

        app.include_router(router, dependencies=[Depends(verify_token)])
        self._task_status_mounted = True

    def unmount(self, app: Any) -> None:
        """从 app 移除全部插件路由/中间件（可逆效应）。"""
        self._remove_plugin_routes_from_app(app)
        self._remove_plugin_middleware_from_app(app)
        # 移除后台任务状态查询接口（可逆效应）
        app.router.routes = [
            r
            for r in app.router.routes
            if not (
                getattr(r, "path", None) == "/api/plugins/tasks/{task_id}"
                and "GET" in {m.upper() for m in (getattr(r, "methods", None) or set())}
            )
        ]
        self._task_status_mounted = False
        if self._mounted_app is app:
            self._mounted_app = None

    @staticmethod
    def _builtin_route_exists(app: Any, path: str, method: str) -> bool:
        """判断内置路由是否已存在（路径+方法匹配）。"""
        method = method.upper()
        for route in app.router.routes:
            route_path = getattr(route, "path", None)
            if route_path != path:
                continue
            methods = getattr(route, "methods", None) or set()
            if method in {m.upper() for m in methods}:
                return True
        return False

    @staticmethod
    def _remove_plugin_routes_from_app(app: Any) -> None:
        """从 app 移除插件挂载的路由（按 name 前缀过滤，保留内置路由）。

        插件路由通过独立 APIRouter include 到 app，route 对象会被复制，
        无法按对象 id 精确移除，因此按 ``plugin_`` 命名前缀过滤。
        """
        app.router.routes = [
            r
            for r in app.router.routes
            if not str(getattr(r, "name", "")).startswith("plugin_")
        ]

    @classmethod
    def _remove_plugin_middleware_from_app(cls, app: Any, rebuild: bool = True) -> None:
        """从 app 移除插件挂载的中间件（按类名前缀过滤 + 重建中间件栈）。

        仅移除 ``PluginMiddleware_`` 前缀的动态子类，保留 CORS 等内置中间件。
        rebuild=False 时仅更新 user_middleware 列表，不重建栈（供挂载流程
        先移除再统一重建，避免中途 add_middleware 触发 "application has
        started" 报错）。
        """
        app.user_middleware = [
            m
            for m in app.user_middleware
            if not str(getattr(m.cls, "__name__", "")).startswith(
                cls._PLUGIN_MIDDLEWARE_PREFIX
            )
        ]
        if rebuild:
            app.middleware_stack = app.build_middleware_stack()

    # ------------------------------------------------------------------
    # 插件变更重载
    # ------------------------------------------------------------------
    def unregister_by_plugin(self, plugin: str) -> int:
        """撤销指定插件注册的全部网关路由/中间件（可逆效应）。

        返回被撤销的路由+中间件数量。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry

        registry = PluginRegistry.instance()
        route_keys = self.get_plugin_routes(plugin)
        middleware_names = self.get_plugin_middleware(plugin)
        count = 0
        for key in route_keys:
            method, _, path = key.partition(" ")
            if self.unregister_route(path, method):
                count += 1
        for name in middleware_names:
            if self.unregister_middleware(name):
                count += 1
        # 若已挂载到 app，同步从 app 移除并重挂载剩余路由
        if self._mounted_app is not None and self._verify_token is not None:
            self.mount(self._mounted_app, self._verify_token)
        registry.clear_gateway_routes(plugin)
        registry.clear_gateway_middleware(plugin)
        return count

    def reload_plugin_gateway(self) -> None:
        """插件变更后免重启重载插件网关扩展（gateway 扩展点）。

        先撤销当前已注册的全部插件路由/中间件，再按最新配置重新加载并挂载，
        使插件安装/卸载/升级后的网关声明立即生效。若网关未启动（无已挂载
        app），仅更新声明，下次启动自动挂载。失败仅告警，不阻断调用方。
        """
        from jarvis.jarvis_tools.plugin_registry import PluginRegistry
        from jarvis.jarvis_utils.output import PrettyOutput

        registry = PluginRegistry.instance()
        app = self._mounted_app
        verify_token = self._verify_token
        # 撤销当前已注册的全部插件路由/中间件（按来源插件名逐个撤销）
        for plugin_name in list(registry.registered_plugins()):
            if registry.get_plugin_gateway_routes(
                plugin_name
            ) or registry.get_plugin_gateway_middleware(plugin_name):
                try:
                    self.unregister_by_plugin(plugin_name)
                except Exception as e:
                    PrettyOutput.auto_print(
                        f"⚠️ 撤销插件 '{plugin_name}' 网关扩展失败: {e}"
                    )
        # 重新加载插件网关扩展
        try:
            if app is not None and verify_token is not None:
                self.load_plugin_gateway(app, verify_token)
            else:
                self.load_plugin_gateway(None, _NOOP_VERIFY)
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 重载插件网关扩展失败: {e}")

    def clear(self) -> None:
        """清空全部登记（主要用于测试隔离）。"""
        self._routes.clear()
        self._middleware.clear()
        self._mounted_app = None
        self._verify_token = None
        self._task_status_mounted = False


def _noop_verify(request: Any) -> Dict[str, Any]:
    """无认证依赖占位（reload 场景无 app 时使用）。"""
    return {"user_id": "system"}


_NOOP_VERIFY = _noop_verify


__all__ = [
    "GatewayExtensionRegistry",
    "GatewayRoute",
    "GatewayMiddleware",
    "PluginBackgroundTaskManager",
]
