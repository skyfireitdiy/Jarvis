# -*- coding: utf-8 -*-
"""工作区壁纸接口测试。

覆盖：
1. 上传 png 壁纸后返回 /uploads/wallpaper/wallpaper.png，且该 URL 可被静态服务访问
2. GET /api/wallpaper 返回当前壁纸 URL，删除后返回 None
3. 非图片内容被拒（INVALID_IMAGE）
4. 超过 8MB 的图片被拒（FILE_TOO_LARGE）
5. 换格式上传（png -> jpg）会清理旧文件，目录内只保留一份壁纸
6. 未携带 Token 时返回 401
依赖 conftest.py 的 isolated_data_dir fixture 隔离数据目录。
"""

import base64
import os

# 必须在导入 jarvis 模块之前设置环境变量，避免触发交互式配置
os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"

import pytest
from fastapi.testclient import TestClient

PNG_HEADER = b"\x89PNG\r\n\x1a\n"
JPG_HEADER = b"\xff\xd8\xff"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


@pytest.fixture
def wallpaper_client(monkeypatch):
    """创建 admin 已登录的 TestClient，并返回壁纸目录路径。"""
    monkeypatch.setenv("JARVIS_ADMIN_PASSWORD", "AdminStrongPass1!")
    from jarvis.jarvis_utils.config import get_data_dir
    from jarvis.jarvis_web_gateway.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "AdminStrongPass1!"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True, body
    headers = {"Authorization": f"Bearer {body['data']['token']}"}
    return client, headers, os.path.join(get_data_dir(), "uploads", "wallpaper")


def test_upload_and_fetch_wallpaper(wallpaper_client):
    """上传 png 壁纸后可通过 /uploads 静态 URL 访问。"""
    client, headers, wallpaper_dir = wallpaper_client
    resp = client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": "data:image/png;base64," + _b64(PNG_HEADER + b"0" * 100)},
    )
    body = resp.json()
    assert body["success"] is True, body
    assert body["url"] == "/uploads/wallpaper/wallpaper.png"
    assert os.path.isfile(os.path.join(wallpaper_dir, "wallpaper.png"))

    resp = client.get(body["url"])
    assert resp.status_code == 200
    assert resp.content.startswith(PNG_HEADER)

    resp = client.get("/api/wallpaper", headers=headers)
    assert resp.json() == {"success": True, "url": "/uploads/wallpaper/wallpaper.png"}


def test_delete_wallpaper(wallpaper_client):
    """删除壁纸后 GET 返回 None。"""
    client, headers, wallpaper_dir = wallpaper_client
    client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": _b64(PNG_HEADER + b"0" * 10)},
    )
    resp = client.delete("/api/wallpaper", headers=headers)
    assert resp.json() == {"success": True, "removed": True}
    assert not os.path.exists(os.path.join(wallpaper_dir, "wallpaper.png"))

    resp = client.get("/api/wallpaper", headers=headers)
    assert resp.json() == {"success": True, "url": None}


def test_reject_non_image(wallpaper_client):
    """非图片内容被拒。"""
    client, headers, _ = wallpaper_client
    resp = client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": _b64(b"definitely not an image")},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_IMAGE"


def test_reject_oversized_image(wallpaper_client):
    """超过 8MB 的图片被拒。"""
    client, headers, _ = wallpaper_client
    oversized = PNG_HEADER + b"0" * (8 * 1024 * 1024 + 1)
    resp = client.post(
        "/api/wallpaper/upload", headers=headers, json={"data": _b64(oversized)}
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "FILE_TOO_LARGE"


def test_format_switch_cleans_old_file(wallpaper_client):
    """换格式上传后目录内只保留新格式文件。"""
    client, headers, wallpaper_dir = wallpaper_client
    client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": _b64(PNG_HEADER + b"0" * 10)},
    )
    resp = client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": _b64(JPG_HEADER + b"1" * 10)},
    )
    assert resp.json()["url"] == "/uploads/wallpaper/wallpaper.jpg"
    assert sorted(os.listdir(wallpaper_dir)) == ["wallpaper.jpg"]


def test_requires_auth(wallpaper_client):
    """未携带 Token 时返回 401。"""
    client, _, _ = wallpaper_client
    assert client.get("/api/wallpaper").status_code == 401
