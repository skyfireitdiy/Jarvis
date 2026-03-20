# -*- coding: utf-8 -*-
"""jarvis_web_gateway app API tests."""

import os
from fastapi.testclient import TestClient

from jarvis.jarvis_web_gateway.app import MAX_FILE_SIZE_BYTES
from jarvis.jarvis_web_gateway.app import create_app


def create_test_client() -> TestClient:
    # 在测试环境中跳过交互式配置
    os.environ["JARVIS_SKIP_INTERACTIVE_CONFIG"] = "1"
    app = create_app()
    return TestClient(app)


def test_post_file_content_success(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello jarvis", encoding="utf-8")
    client = create_test_client()

    response = client.post("/api/file-content", json={"path": str(test_file.resolve())})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["path"] == str(test_file.resolve())
    assert payload["data"]["content"] == "hello jarvis"


def test_post_file_content_rejects_relative_path(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("hello jarvis", encoding="utf-8")
    client = create_test_client()

    response = client.post("/api/file-content", json={"path": test_file.name})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_PATH"


def test_post_file_content_rejects_directory(tmp_path):
    client = create_test_client()

    response = client.post("/api/file-content", json={"path": str(tmp_path.resolve())})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "NOT_A_FILE"


def test_post_file_content_rejects_large_file(tmp_path):
    test_file = tmp_path / "large.txt"
    test_file.write_text("a" * (MAX_FILE_SIZE_BYTES + 1), encoding="utf-8")
    client = create_test_client()

    response = client.post("/api/file-content", json={"path": str(test_file.resolve())})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FILE_TOO_LARGE"


def test_post_file_content_rejects_binary_file(tmp_path):
    test_file = tmp_path / "binary.bin"
    test_file.write_bytes(b"\x00\x01\x02jarvis")
    client = create_test_client()

    response = client.post("/api/file-content", json={"path": str(test_file.resolve())})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "BINARY_FILE_NOT_SUPPORTED"


def test_post_file_write_success(tmp_path):
    test_file = tmp_path / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(test_file.resolve()), "content": "hello write"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["path"] == str(test_file.resolve())
    assert payload["data"]["bytes_written"] == len("hello write".encode("utf-8"))
    assert test_file.read_text(encoding="utf-8") == "hello write"


def test_post_file_write_rejects_relative_path(tmp_path):
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": "relative.txt", "content": "hello"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_PATH"


def test_post_file_write_rejects_missing_parent_directory(tmp_path):
    missing_file = tmp_path / "missing" / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(missing_file.resolve(strict=False)), "content": "hello"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "PARENT_DIRECTORY_NOT_FOUND"


def test_post_file_write_rejects_non_string_content(tmp_path):
    test_file = tmp_path / "write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={"path": str(test_file.resolve()), "content": 123},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_CONTENT"


def test_post_file_write_rejects_large_content(tmp_path):
    test_file = tmp_path / "large-write.txt"
    client = create_test_client()

    response = client.post(
        "/api/file-write",
        json={
            "path": str(test_file.resolve()),
            "content": "a" * (MAX_FILE_SIZE_BYTES + 1),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "FILE_TOO_LARGE"
