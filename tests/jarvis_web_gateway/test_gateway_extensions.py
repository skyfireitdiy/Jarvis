# -*- coding: utf-8 -*-
"""插件 gateway 扩展点单元测试（Issue #292）。

验证插件 config.yaml 声明的网关路由/中间件能被 GatewayExtensionRegistry
加载、挂载到 FastAPI app（含 token 认证、路径冲突保护），并在卸载时精确撤销。
"""

import os
import shutil
import tempfile
import time

import pytest
from fastapi import FastAPI
from fastapi import Request
from fastapi.testclient import TestClient

from jarvis.jarvis_tools.plugin_registry import PluginRegistry
from jarvis.jarvis_web_gateway.gateway_extensions import GatewayExtensionRegistry
from jarvis.jarvis_web_gateway.gateway_extensions import PluginBackgroundTaskManager

ROUTE_CODE = '''
def route_handler(request):
    return {"handled": True, "path": request.url.path}
'''

# 后台执行模式的 handler：耗时操作，返回结果
BACKGROUND_ROUTE_CODE = '''
import time

def route_handler(request):
    time.sleep(0.2)
    return {"handled": True, "background": True, "path": request.url.path}
'''

# 后台执行模式 + 抛异常的 handler
BACKGROUND_ERROR_ROUTE_CODE = '''
def route_handler(request):
    raise ValueError("boom")
'''

# async handler（不占线程池）
ASYNC_ROUTE_CODE = '''
async def route_handler(request):
    return {"handled": True, "async": True, "path": request.url.path}
'''

MIDDLEWARE_CODE = '''
async def middleware_handler(request, call_next):
    response = await call_next(request)
    response.headers["X-Plugin-Middleware"] = "active"
    return response
'''


@pytest.fixture()
def plugin_gateway_dirs():
    """创建临时插件网关实现目录（形如 <tmp>/plugins/<name>/gateway_*）。"""
    tmp = tempfile.mkdtemp()
    routes_dir = os.path.join(tmp, "plugins", "demo_plugin", "gateway_routes")
    middleware_dir = os.path.join(
        tmp, "plugins", "demo_plugin", "gateway_middleware"
    )
    os.makedirs(routes_dir, exist_ok=True)
    os.makedirs(middleware_dir, exist_ok=True)
    open(os.path.join(routes_dir, "__init__.py"), "w").close()
    open(os.path.join(middleware_dir, "__init__.py"), "w").close()
    with open(os.path.join(routes_dir, "webhook.py"), "w") as f:
        f.write(ROUTE_CODE)
    with open(os.path.join(middleware_dir, "audit.py"), "w") as f:
        f.write(MIDDLEWARE_CODE)
    yield {"routes": routes_dir, "middleware": middleware_dir, "tmp": tmp}
    shutil.rmtree(tmp)


@pytest.fixture()
def clean_registry():
    """隔离测试：清空 PluginRegistry 与 GatewayExtensionRegistry 登记。"""
    registry = PluginRegistry.instance()
    gateway_registry = GatewayExtensionRegistry.instance()
    registry.clear()
    gateway_registry.clear()
    yield registry
    registry.clear()
    gateway_registry.clear()


def _fake_verify_token(request: Request) -> dict:
    """测试用 token 认证依赖：X-Jarvis-Token 等于 test-token 才放行。"""
    from fastapi import HTTPException

    token = request.headers.get("X-Jarvis-Token") or ""
    if token != "test-token":
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"user_id": "test"}


def test_infer_source_plugin(plugin_gateway_dirs):
    """从插件网关实现目录路径反推来源插件名。"""
    source = GatewayExtensionRegistry._infer_source_plugin(
        plugin_gateway_dirs["routes"]
    )
    assert source == "demo_plugin"


def test_infer_source_plugin_non_plugin_dir():
    """非插件目录路径返回 None。"""
    assert GatewayExtensionRegistry._infer_source_plugin("/tmp/foo/bar") is None
    assert GatewayExtensionRegistry._infer_source_plugin("") is None


def test_register_and_unregister_route(clean_registry):
    """路由声明注册/查询/撤销闭环。"""
    gateway_registry = GatewayExtensionRegistry.instance()
    gateway_registry.register_route(
        "/api/plugins/x", "get", handler="/tmp/routes", plugin="demo_plugin"
    )
    route = gateway_registry.get_route("/api/plugins/x", "GET")
    assert route is not None
    assert route.method == "GET"  # 方法归一化为大写
    assert route.plugin == "demo_plugin"
    assert gateway_registry.get_plugin_routes("demo_plugin") == [
        "GET /api/plugins/x"
    ]

    assert gateway_registry.unregister_route("/api/plugins/x", "GET") is True
    assert gateway_registry.get_route("/api/plugins/x", "GET") is None
    assert gateway_registry.unregister_route("/api/plugins/x", "GET") is False


def test_register_and_unregister_middleware(clean_registry):
    """中间件声明注册/查询/撤销闭环。"""
    gateway_registry = GatewayExtensionRegistry.instance()
    gateway_registry.register_middleware(
        "audit_middleware", handler="/tmp/middleware", plugin="demo_plugin"
    )
    listed = gateway_registry.list_middleware()
    assert listed == [
        {
            "name": "audit_middleware",
            "handler": "/tmp/middleware",
            "plugin": "demo_plugin",
        }
    ]
    assert gateway_registry.get_plugin_middleware("demo_plugin") == [
        "audit_middleware"
    ]

    assert gateway_registry.unregister_middleware("audit_middleware") is True
    assert gateway_registry.list_middleware() == []
    assert gateway_registry.unregister_middleware("audit_middleware") is False


def test_load_plugin_gateway(plugin_gateway_dirs, clean_registry, monkeypatch):
    """插件网关实现目录加载并登记到 PluginRegistry。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "POST",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ],
                "middleware": [
                    {
                        "name": "audit_middleware",
                        "handler": plugin_gateway_dirs["middleware"],
                    }
                ],
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    gateway_registry.load_plugin_gateway(None, _fake_verify_token)

    routes = gateway_registry.list_routes()
    assert len(routes) == 1
    assert routes[0]["path"] == "/api/plugins/dhttp/webhook"
    assert routes[0]["method"] == "POST"
    assert routes[0]["plugin"] == "demo_plugin"
    middleware = gateway_registry.list_middleware()
    assert len(middleware) == 1
    assert middleware[0]["name"] == "audit_middleware"
    assert middleware[0]["plugin"] == "demo_plugin"
    assert clean_registry.get_plugin_gateway_routes("demo_plugin") == [
        "POST /api/plugins/dhttp/webhook"
    ]
    assert clean_registry.get_plugin_gateway_middleware("demo_plugin") == [
        "audit_middleware"
    ]


def test_mount_route_with_auth(plugin_gateway_dirs, clean_registry, monkeypatch):
    """插件路由挂载到 app，默认带 token 认证。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    app = FastAPI()
    gateway_registry.load_plugin_gateway(app, _fake_verify_token)

    client = TestClient(app)
    # 无 token：401
    resp = client.get("/api/plugins/dhttp/webhook")
    assert resp.status_code == 401
    # 有效 token：200
    resp = client.get(
        "/api/plugins/dhttp/webhook", headers={"X-Jarvis-Token": "test-token"}
    )
    assert resp.status_code == 200
    assert resp.json()["handled"] is True


def test_route_conflict_skipped(plugin_gateway_dirs, clean_registry, monkeypatch):
    """插件路由与内置路由冲突时不挂载（不覆盖内置）。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/health",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    app = FastAPI()

    @app.get("/api/health")
    def builtin_health():
        return {"builtin": True}

    gateway_registry.load_plugin_gateway(app, _fake_verify_token)

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"builtin": True}  # 内置路由仍生效


def test_middleware_mounted(plugin_gateway_dirs, clean_registry, monkeypatch):
    """插件中间件挂载到 app 并对请求生效。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "middleware": [
                    {
                        "name": "audit_middleware",
                        "handler": plugin_gateway_dirs["middleware"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    gateway_registry.load_plugin_gateway(app, _fake_verify_token)

    client = TestClient(app)
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.headers.get("X-Plugin-Middleware") == "active"


def test_unmount_removes_plugin_routes_and_middleware(
    plugin_gateway_dirs, clean_registry, monkeypatch
):
    """卸载时从 app 移除插件路由/中间件，内置路由保留。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ],
                "middleware": [
                    {
                        "name": "audit_middleware",
                        "handler": plugin_gateway_dirs["middleware"],
                    }
                ],
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    app = FastAPI()

    @app.get("/api/health")
    def builtin_health():
        return {"builtin": True}

    gateway_registry.load_plugin_gateway(app, _fake_verify_token)
    gateway_registry.unmount(app)

    client = TestClient(app)
    # 插件路由已移除：404
    resp = client.get(
        "/api/plugins/dhttp/webhook", headers={"X-Jarvis-Token": "test-token"}
    )
    assert resp.status_code == 404
    # 内置路由保留
    resp = client.get("/api/health")
    assert resp.status_code == 200
    # 中间件已移除
    resp = client.get("/api/health")
    assert resp.headers.get("X-Plugin-Middleware") is None


def test_unregister_by_plugin(plugin_gateway_dirs, clean_registry, monkeypatch):
    """按插件撤销网关扩展并清理登记。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    app = FastAPI()
    gateway_registry.load_plugin_gateway(app, _fake_verify_token)

    count = gateway_registry.unregister_by_plugin("demo_plugin")
    assert count == 1
    assert gateway_registry.list_routes() == []
    assert clean_registry.get_plugin_gateway_routes("demo_plugin") == []
    assert not clean_registry.has_plugin("demo_plugin")

    client = TestClient(app)
    resp = client.get(
        "/api/plugins/dhttp/webhook", headers={"X-Jarvis-Token": "test-token"}
    )
    assert resp.status_code == 404


def test_reload_plugin_gateway(plugin_gateway_dirs, clean_registry, monkeypatch):
    """reload 撤销旧声明并按最新配置重新加载。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    gateway_registry.load_plugin_gateway(None, _fake_verify_token)
    assert len(gateway_registry.list_routes()) == 1

    # 清空配置后 reload：旧路由被撤销
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {"gateway": {"routes": [], "middleware": []}},
    )
    gateway_registry.reload_plugin_gateway()
    assert gateway_registry.list_routes() == []
    assert not clean_registry.has_plugin("demo_plugin")


def test_revoke_plugin_integration(plugin_gateway_dirs, clean_registry, monkeypatch):
    """PluginRegistry.revoke_plugin 经 gateway revoker 撤销网关扩展。"""
    monkeypatch.setattr(
        "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
        {
            "gateway": {
                "routes": [
                    {
                        "path": "/api/plugins/dhttp/webhook",
                        "method": "GET",
                        "handler": plugin_gateway_dirs["routes"],
                    }
                ]
            }
        },
    )
    gateway_registry = GatewayExtensionRegistry.instance()
    gateway_registry.load_plugin_gateway(None, _fake_verify_token)
    clean_registry.set_gateway_revoker(gateway_registry.unregister_by_plugin)

    result = clean_registry.revoke_plugin("demo_plugin")
    assert result["gateway_routes"] == 1
    assert result["gateway_middleware"] == 0
    assert gateway_registry.list_routes() == []
    assert not clean_registry.has_plugin("demo_plugin")


# ---------------------------------------------------------------------------
# Issue #353：插件网关路由后台执行模式 / async handler
# ---------------------------------------------------------------------------


def _make_route_dir(tmp, plugin_name, code):
    """创建单个插件路由实现目录并写入 handler 代码，返回目录路径。"""
    routes_dir = os.path.join(tmp, "plugins", plugin_name, "gateway_routes")
    os.makedirs(routes_dir, exist_ok=True)
    open(os.path.join(routes_dir, "__init__.py"), "w").close()
    with open(os.path.join(routes_dir, "webhook.py"), "w") as f:
        f.write(code)
    return routes_dir


def test_background_task_manager_submit_and_status(clean_registry):
    """PluginBackgroundTaskManager 提交任务并查询状态（含结果）。"""
    manager = PluginBackgroundTaskManager.instance()
    manager.clear()

    def slow_handler(request):
        return {"done": True, "received": request is not None}

    task_id = manager.submit(slow_handler, request=None, plugin="demo_plugin")
    assert task_id
    # 轮询等待完成
    status = None
    for _ in range(50):
        status = manager.get_status(task_id)
        if status and status["status"] in (
            PluginBackgroundTaskManager.STATUS_COMPLETED,
            PluginBackgroundTaskManager.STATUS_FAILED,
        ):
            break
        time.sleep(0.05)
    assert status is not None
    assert status["status"] == PluginBackgroundTaskManager.STATUS_COMPLETED
    assert status["result"] == {"done": True, "received": False}
    assert status["plugin"] == "demo_plugin"
    manager.clear()


def test_background_task_manager_error_status(clean_registry):
    """后台任务异常时状态为 failed 且记录错误。"""
    manager = PluginBackgroundTaskManager.instance()
    manager.clear()

    def failing_handler(request):
        raise ValueError("boom")

    task_id = manager.submit(failing_handler, request=None)
    status = None
    for _ in range(50):
        status = manager.get_status(task_id)
        if status and status["status"] in (
            PluginBackgroundTaskManager.STATUS_COMPLETED,
            PluginBackgroundTaskManager.STATUS_FAILED,
        ):
            break
        time.sleep(0.05)
    assert status is not None
    assert status["status"] == PluginBackgroundTaskManager.STATUS_FAILED
    assert "ValueError" in status["error"]
    manager.clear()


def test_background_task_manager_unknown_task(clean_registry):
    """查询不存在的任务返回 None。"""
    manager = PluginBackgroundTaskManager.instance()
    manager.clear()
    assert manager.get_status("no-such-task") is None
    manager.clear()


def test_background_route_returns_202_and_queryable(clean_registry, monkeypatch):
    """background:true 路由调用返回 202 + task_id，后台执行后可查询结果。"""
    tmp = tempfile.mkdtemp()
    try:
        routes_dir = _make_route_dir(tmp, "bg_plugin", BACKGROUND_ROUTE_CODE)
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {
                "gateway": {
                    "routes": [
                        {
                            "path": "/api/plugins/bg/slow",
                            "method": "POST",
                            "handler": routes_dir,
                            "background": True,
                        }
                    ]
                }
            },
        )
        gateway_registry = GatewayExtensionRegistry.instance()
        app = FastAPI()
        gateway_registry.load_plugin_gateway(app, _fake_verify_token)

        # 确认路由声明带 background 标记
        routes = gateway_registry.list_routes()
        assert len(routes) == 1
        assert routes[0]["background"] is True

        client = TestClient(app)
        # 调用立即返回 202 + task_id
        resp = client.post(
            "/api/plugins/bg/slow", headers={"X-Jarvis-Token": "test-token"}
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "task_id" in body
        task_id = body["task_id"]

        # 轮询任务状态接口直到完成
        result = None
        for _ in range(50):
            r = client.get(
                f"/api/plugins/tasks/{task_id}",
                headers={"X-Jarvis-Token": "test-token"},
            )
            assert r.status_code == 200
            data = r.json()
            if data["status"] == PluginBackgroundTaskManager.STATUS_COMPLETED:
                result = data
                break
            time.sleep(0.05)
        assert result is not None
        assert result["result"]["background"] is True
    finally:
        shutil.rmtree(tmp)


def test_background_route_error_queryable(clean_registry, monkeypatch):
    """background 路由 handler 异常时任务状态为 failed 且可查询错误。"""
    tmp = tempfile.mkdtemp()
    try:
        routes_dir = _make_route_dir(tmp, "bg_plugin", BACKGROUND_ERROR_ROUTE_CODE)
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {
                "gateway": {
                    "routes": [
                        {
                            "path": "/api/plugins/bg/error",
                            "method": "POST",
                            "handler": routes_dir,
                            "background": True,
                        }
                    ]
                }
            },
        )
        gateway_registry = GatewayExtensionRegistry.instance()
        app = FastAPI()
        gateway_registry.load_plugin_gateway(app, _fake_verify_token)

        client = TestClient(app)
        resp = client.post(
            "/api/plugins/bg/error", headers={"X-Jarvis-Token": "test-token"}
        )
        assert resp.status_code == 202
        task_id = resp.json()["task_id"]

        status = None
        for _ in range(50):
            r = client.get(
                f"/api/plugins/tasks/{task_id}",
                headers={"X-Jarvis-Token": "test-token"},
            )
            data = r.json()
            if data["status"] == PluginBackgroundTaskManager.STATUS_FAILED:
                status = data
                break
            time.sleep(0.05)
        assert status is not None
        assert "ValueError" in status["error"]
    finally:
        shutil.rmtree(tmp)


def test_task_status_route_requires_auth(clean_registry, monkeypatch):
    """任务状态查询接口默认带 token 认证。"""
    tmp = tempfile.mkdtemp()
    try:
        routes_dir = _make_route_dir(tmp, "bg_plugin", BACKGROUND_ROUTE_CODE)
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {
                "gateway": {
                    "routes": [
                        {
                            "path": "/api/plugins/bg/slow",
                            "method": "POST",
                            "handler": routes_dir,
                            "background": True,
                        }
                    ]
                }
            },
        )
        gateway_registry = GatewayExtensionRegistry.instance()
        app = FastAPI()
        gateway_registry.load_plugin_gateway(app, _fake_verify_token)

        client = TestClient(app)
        # 无 token：401
        resp = client.get("/api/plugins/tasks/whatever")
        assert resp.status_code == 401
        # 有效 token + 不存在任务：404
        resp = client.get(
            "/api/plugins/tasks/whatever", headers={"X-Jarvis-Token": "test-token"}
        )
        assert resp.status_code == 404
    finally:
        shutil.rmtree(tmp)


def test_async_route_handler(clean_registry, monkeypatch):
    """async route_handler 直接作为 FastAPI async 端点，正常工作。"""
    tmp = tempfile.mkdtemp()
    try:
        routes_dir = _make_route_dir(tmp, "async_plugin", ASYNC_ROUTE_CODE)
        monkeypatch.setattr(
            "jarvis.jarvis_utils.config.GLOBAL_CONFIG_DATA",
            {
                "gateway": {
                    "routes": [
                        {
                            "path": "/api/plugins/async/echo",
                            "method": "GET",
                            "handler": routes_dir,
                        }
                    ]
                }
            },
        )
        gateway_registry = GatewayExtensionRegistry.instance()
        app = FastAPI()
        gateway_registry.load_plugin_gateway(app, _fake_verify_token)

        client = TestClient(app)
        resp = client.get(
            "/api/plugins/async/echo", headers={"X-Jarvis-Token": "test-token"}
        )
        assert resp.status_code == 200
        assert resp.json()["async"] is True
    finally:
        shutil.rmtree(tmp)
