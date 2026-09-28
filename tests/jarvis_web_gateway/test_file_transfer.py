# -*- coding: utf-8 -*-
"""节点文件直传（file-transfer）端点的单元测试。

覆盖：
1. 路径收敛：绝对路径去根、相对路径、.. 穿越拒绝；
2. 上传分块：单块写入、多块拼接内容正确、offset 越界；
3. 下载分块：offset/length 分块读取、eof 判定、目录 tar 打包。

测试直接调用 create_app() 内部注册到 node_connection_manager 的
_node_http_dispatcher，从而走真实的 /file-transfer/* 分派逻辑。
"""

import base64
import hashlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

os.environ.setdefault("JARVIS_SKIP_INTERACTIVE_CONFIG", "1")


@pytest.fixture()
def dispatcher(monkeypatch, tmp_path):
    """构造一个把 transfers 根目录指向临时目录的 dispatcher。

    通过 monkeypatch get_data_dir，使 ~/.jarvis 落到 tmp_path，
    避免污染真实用户目录。
    """
    import jarvis.jarvis_utils.config as config_mod

    monkeypatch.setattr(config_mod, "get_data_dir", lambda: str(tmp_path))

    from jarvis.jarvis_web_gateway.app import create_app

    app = create_app()
    # create_app 会把 dispatcher 注入 app.state.node_connection_manager
    manager = app.state.node_connection_manager
    disp = manager._node_http_dispatcher
    assert disp is not None
    return disp, tmp_path


def _call(disp, path: str, payload: dict):
    import asyncio
    import json

    async def _inner():
        return await disp(
            method="POST",
            path=path,
            query="",
            headers={"content-type": "application/json"},
            body=json.dumps(payload),
            user_info=None,
            trusted_proxy=True,
        )

    return asyncio.new_event_loop().run_until_complete(_inner())


def _body(result: dict) -> dict:
    import json

    return json.loads(result["body"])


# ----------------------------------------------------------------------
# 路径收敛
# ----------------------------------------------------------------------
def test_absolute_path_is_re_rooted_under_transfers(dispatcher):
    """绝对路径 /tmp/x.txt 应落到 <data_dir>/transfers/tmp/x.txt。"""
    disp, tmp_path = dispatcher
    data = base64.b64encode(b"hello").decode()
    result = _call(
        disp,
        "/file-transfer/upload",
        {"path": "/tmp/x.txt", "data": data, "offset": 0, "truncate": True},
    )
    body = _body(result)
    assert body["success"] is True
    expected = tmp_path / "transfers" / "tmp" / "x.txt"
    assert expected.exists()
    assert expected.read_bytes() == b"hello"
    assert body["data"]["path"] == str(expected)


def test_relative_path_is_directly_joined(dispatcher):
    """相对路径 a/b.txt 应落到 <data_dir>/transfers/a/b.txt。"""
    disp, tmp_path = dispatcher
    data = base64.b64encode(b"rel").decode()
    result = _call(
        disp,
        "/file-transfer/upload",
        {"path": "a/b.txt", "data": data, "offset": 0, "truncate": True},
    )
    body = _body(result)
    assert body["success"] is True
    expected = tmp_path / "transfers" / "a" / "b.txt"
    assert expected.read_bytes() == b"rel"


@pytest.mark.parametrize(
    "evil",
    ["../../etc/passwd", "/../../etc/passwd", "a/../../../etc/passwd"],
)
def test_path_traversal_is_rejected(dispatcher, evil):
    """任何逃出 transfers 根的路径都必须被拒绝。"""
    disp, _ = dispatcher
    data = base64.b64encode(b"x").decode()
    result = _call(
        disp,
        "/file-transfer/upload",
        {"path": evil, "data": data, "offset": 0, "truncate": True},
    )
    body = _body(result)
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_PATH"


# ----------------------------------------------------------------------
# 上传分块
# ----------------------------------------------------------------------
def test_upload_multiple_chunks_concatenate(dispatcher):
    """多块按 offset 拼接后内容应与源一致。"""
    disp, tmp_path = dispatcher
    part1 = b"A" * 100
    part2 = b"B" * 50
    r1 = _call(
        disp,
        "/file-transfer/upload",
        {
            "path": "multi.bin",
            "data": base64.b64encode(part1).decode(),
            "offset": 0,
            "truncate": True,
        },
    )
    assert _body(r1)["success"] is True
    r2 = _call(
        disp,
        "/file-transfer/upload",
        {
            "path": "multi.bin",
            "data": base64.b64encode(part2).decode(),
            "offset": len(part1),
            "truncate": False,
        },
    )
    assert _body(r2)["success"] is True
    expected = tmp_path / "transfers" / "multi.bin"
    assert expected.read_bytes() == part1 + part2


def test_upload_chunk_sha256_returned(dispatcher):
    """返回的 sha256 应与该分块一致。"""
    disp, _ = dispatcher
    chunk = b"hash-me"
    result = _call(
        disp,
        "/file-transfer/upload",
        {
            "path": "h.bin",
            "data": base64.b64encode(chunk).decode(),
            "offset": 0,
            "truncate": True,
        },
    )
    body = _body(result)
    assert body["data"]["sha256"] == hashlib.sha256(chunk).hexdigest()


# ----------------------------------------------------------------------
# 下载分块
# ----------------------------------------------------------------------
def test_download_chunks_and_eof(dispatcher):
    """下载应按 offset/length 分块，最后一块 eof=True。"""
    disp, tmp_path = dispatcher
    content = b"0123456789"
    target = tmp_path / "transfers" / "d.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    r1 = _call(
        disp,
        "/file-transfer/download",
        {"path": "d.bin", "offset": 0, "length": 4},
    )
    b1 = _body(r1)
    assert b1["success"] is True
    assert base64.b64decode(b1["data"]["data"]) == b"0123"
    assert b1["data"]["eof"] is False
    assert b1["data"]["size"] == 10

    r2 = _call(
        disp,
        "/file-transfer/download",
        {"path": "d.bin", "offset": 8, "length": 4},
    )
    b2 = _body(r2)
    assert base64.b64decode(b2["data"]["data"]) == b"89"
    assert b2["data"]["eof"] is True


def test_download_offset_beyond_eof_returns_empty(dispatcher):
    """offset 越界时应返回空块且 eof=True。"""
    disp, tmp_path = dispatcher
    target = tmp_path / "transfers" / "e.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"abc")
    result = _call(
        disp,
        "/file-transfer/download",
        {"path": "e.bin", "offset": 100, "length": 10},
    )
    body = _body(result)
    assert body["success"] is True
    assert base64.b64decode(body["data"]["data"]) == b""
    assert body["data"]["eof"] is True


def test_download_directory_packs_tar(dispatcher):
    """mode=dir 时应把目录打包为 tar 返回。"""
    import io
    import tarfile

    disp, tmp_path = dispatcher
    src = tmp_path / "transfers" / "mydir"
    src.mkdir(parents=True, exist_ok=True)
    (src / "inner.txt").write_bytes(b"inner-content")

    result = _call(
        disp,
        "/file-transfer/download",
        {"path": "mydir", "offset": 0, "length": 8 * 1024 * 1024, "mode": "dir"},
    )
    body = _body(result)
    assert body["success"] is True
    tar_bytes = base64.b64decode(body["data"]["data"])
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
        names = tar.getnames()
    assert any(n.endswith("inner.txt") for n in names)


def test_upload_directory_unpacks_tar(dispatcher):
    """mode=dir 且 final=True 时应解包 tar 到目标目录。"""
    import io
    import tarfile

    disp, tmp_path = dispatcher
    # 构造一个含单个文件的 tar
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="packed/hello.txt")
        payload = b"packed-content"
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    tar_bytes = buf.getvalue()

    result = _call(
        disp,
        "/file-transfer/upload",
        {
            "path": "unpacked",
            "data": base64.b64encode(tar_bytes).decode(),
            "offset": 0,
            "mode": "dir",
            "truncate": True,
            "final": True,
        },
    )
    body = _body(result)
    assert body["success"] is True
    assert (
        tmp_path / "transfers" / "unpacked" / "packed" / "hello.txt"
    ).read_bytes() == b"packed-content"


def test_unknown_transfer_path_returns_404(dispatcher):
    """未知的 file-transfer 子路径应返回 404。"""
    disp, _ = dispatcher
    result = _call(disp, "/file-transfer/unknown", {})
    assert result["status_code"] == 404


def test_upload_truncate_with_nonzero_offset_writes_at_offset(dispatcher):
    """truncate=True 且 offset>0 时应写在 offset 处，而不是文件开头。"""
    disp, tmp_path = dispatcher
    result = _call(
        disp,
        "/file-transfer/upload",
        {
            "path": "trunc.bin",
            "data": base64.b64encode(b"XYZ").decode(),
            "offset": 4,
            "truncate": True,
        },
    )
    assert _body(result)["success"] is True
    expected = tmp_path / "transfers" / "trunc.bin"
    # offset=4 之前由空洞（\x00）填充
    assert expected.read_bytes() == b"\x00\x00\x00\x00XYZ"


def test_download_directory_packs_once_and_cleans_tar(dispatcher):
    """dir 模式多分块下载：tar 只打包一次（缓存复用），读完后清理临时 tar。"""
    import io
    import tarfile

    disp, tmp_path = dispatcher
    src = tmp_path / "transfers" / "bigdir"
    src.mkdir(parents=True, exist_ok=True)
    (src / "a.txt").write_bytes(b"A" * 200)
    (src / "b.txt").write_bytes(b"B" * 200)

    tar_path = tmp_path / "transfers" / "bigdir.outgoing.tar"

    # 第一块：小 length，必然 eof=False，tar 应保留
    r1 = _call(
        disp,
        "/file-transfer/download",
        {"path": "bigdir", "offset": 0, "length": 64, "mode": "dir"},
    )
    b1 = _body(r1)
    assert b1["success"] is True
    assert b1["data"]["eof"] is False
    assert tar_path.exists(), "分块未读完时临时 tar 应保留以便复用"
    first_mtime = tar_path.stat().st_mtime_ns
    total = b1["data"]["size"]

    # 第二块：继续读，命中缓存（mtime 不变，未重新打包）
    r2 = _call(
        disp,
        "/file-transfer/download",
        {"path": "bigdir", "offset": 64, "length": 64, "mode": "dir"},
    )
    b2 = _body(r2)
    assert b2["success"] is True
    assert tar_path.stat().st_mtime_ns == first_mtime, "缓存命中时不应重新打包"
    assert b2["data"]["size"] == total

    # 读到最后一块：eof=True，临时 tar 应被清理
    r3 = _call(
        disp,
        "/file-transfer/download",
        {"path": "bigdir", "offset": total - 1, "length": 64, "mode": "dir"},
    )
    b3 = _body(r3)
    assert b3["success"] is True
    assert b3["data"]["eof"] is True
    assert not tar_path.exists(), "读完后应删除临时 tar"

    # 清理后再次请求应重新打包并成功（缓存已失效，无残留）
    r4 = _call(
        disp,
        "/file-transfer/download",
        {"path": "bigdir", "offset": 0, "length": 8 * 1024 * 1024, "mode": "dir"},
    )
    b4 = _body(r4)
    assert b4["success"] is True
    tar_bytes = base64.b64decode(b4["data"]["data"])
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
        names = tar.getnames()
    assert any(n.endswith("a.txt") for n in names)
    assert any(n.endswith("b.txt") for n in names)
