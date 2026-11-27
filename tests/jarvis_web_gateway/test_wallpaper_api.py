# -*- coding: utf-8 -*-
"""工作区壁纸接口测试。

覆盖：
1. 上传 png 壁纸后返回 /uploads/wallpaper/xxx，且该 URL 可被静态服务访问
2. GET /api/wallpaper 返回壁纸库（wallpapers 列表 + 最近上传的 url），清空后为空
3. 非图片内容被拒（INVALID_IMAGE）
4. 超过 8MB 的图片被拒（FILE_TOO_LARGE）
5. 多张壁纸共存：上传多张后目录内保留多份，列表按最近上传优先
6. 删除单张（?url=）只删该张，且拒绝路径穿越
7. 壁纸库数量上限（TOO_MANY_WALLPAPERS）
8. 未携带 Token 时返回 401

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


def _upload(client, headers, raw: bytes):
    return client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": "data:image/png;base64," + _b64(raw)},
    )


def test_upload_and_fetch_wallpaper(wallpaper_client):
    """上传 png 壁纸后可通过 /uploads 静态 URL 访问。"""
    client, headers, wallpaper_dir = wallpaper_client
    resp = _upload(client, headers, PNG_HEADER + b"0" * 100)
    body = resp.json()
    assert body["success"] is True, body
    url = body["url"]
    assert url.startswith("/uploads/wallpaper/wallpaper_")
    assert url.endswith(".png")
    assert os.path.isfile(os.path.join(wallpaper_dir, os.path.basename(url)))

    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.content.startswith(PNG_HEADER)

    resp = client.get("/api/wallpaper", headers=headers)
    data = resp.json()
    assert data["success"] is True
    assert data["url"] == url
    assert [item["url"] for item in data["wallpapers"]] == [url]


def test_delete_all_wallpapers(wallpaper_client):
    """不带 url 的 DELETE 清空整个壁纸库。"""
    client, headers, wallpaper_dir = wallpaper_client
    _upload(client, headers, PNG_HEADER + b"0" * 10)
    _upload(client, headers, PNG_HEADER + b"1" * 10)
    assert len(os.listdir(wallpaper_dir)) == 2

    resp = client.delete("/api/wallpaper", headers=headers)
    body = resp.json()
    assert body["success"] is True
    assert body["removed"] is True
    assert body["wallpapers"] == []
    assert os.listdir(wallpaper_dir) == []

    resp = client.get("/api/wallpaper", headers=headers)
    assert resp.json() == {"success": True, "url": None, "wallpapers": []}


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


def test_multiple_wallpapers_kept_and_sorted(wallpaper_client):
    """多张壁纸共存，列表按最近上传优先，且支持不同格式。"""
    client, headers, wallpaper_dir = wallpaper_client
    first = _upload(client, headers, PNG_HEADER + b"0" * 10).json()["url"]
    second = client.post(
        "/api/wallpaper/upload",
        headers=headers,
        json={"data": _b64(JPG_HEADER + b"1" * 10)},
    ).json()["url"]

    assert first != second
    assert second.endswith(".jpg")
    assert len(os.listdir(wallpaper_dir)) == 2

    data = client.get("/api/wallpaper", headers=headers).json()
    urls = [item["url"] for item in data["wallpapers"]]
    assert urls == [second, first]
    assert data["url"] == second


def test_delete_single_wallpaper(wallpaper_client):
    """带 ?url= 的 DELETE 只删除指定那张。"""
    client, headers, wallpaper_dir = wallpaper_client
    first = _upload(client, headers, PNG_HEADER + b"0" * 10).json()["url"]
    second = _upload(client, headers, PNG_HEADER + b"1" * 10).json()["url"]

    resp = client.delete("/api/wallpaper", headers=headers, params={"url": first})
    body = resp.json()
    assert body["success"] is True
    assert body["removed"] is True
    assert [item["url"] for item in body["wallpapers"]] == [second]
    assert body["url"] == second
    assert os.listdir(wallpaper_dir) == [os.path.basename(second)]


def test_delete_rejects_path_traversal(wallpaper_client):
    """删除接口只接受壁纸库内的合法文件名，拒绝路径穿越。"""
    client, headers, _ = wallpaper_client
    resp = client.delete(
        "/api/wallpaper",
        headers=headers,
        params={"url": "/uploads/wallpaper/../../app.py"},
    )
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "WALLPAPER_NOT_FOUND"


def test_wallpaper_count_limit(wallpaper_client):
    """壁纸库达到上限后拒绝继续上传。"""
    client, headers, _ = wallpaper_client

    # 上限是 create_app 内的闭包常量（默认 20），这里上传到上限后校验下一张被拒
    limit = 20
    for index in range(limit):
        body = _upload(client, headers, PNG_HEADER + bytes([index]) * 10).json()
        assert body["success"] is True, body

    resp = _upload(client, headers, PNG_HEADER + b"x" * 10)
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "TOO_MANY_WALLPAPERS"


def test_requires_auth(wallpaper_client):
    """未携带 Token 时返回 401。"""
    client, _, _ = wallpaper_client
    assert client.get("/api/wallpaper").status_code == 401
