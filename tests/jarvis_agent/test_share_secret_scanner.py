# -*- coding: utf-8 -*-
"""分享前敏感信息扫描（share_secret_scanner + ShareManager 闸门）单元测试。

注意：本文件是「凭据扫描器」自身的测试，样本必须形似真实凭据才能验证命中。
为避免测试文件本身被 pre-commit 钩子/分享闸门误拦，所有敏感样本均以
「片段拼接」方式在运行时构造，源码中不出现完整的敏感字面量。
"""

import subprocess

from jarvis.jarvis_agent.share_manager import ShareManager
from jarvis.jarvis_agent.share_secret_scanner import (
    Finding,
    format_findings,
    is_whitelisted,
    mask,
    scan_files,
    scan_text,
)

# ---------------------------------------------------------------------------
# 运行时构造的测试样本（源码中不出现完整敏感字面量，避免被扫描器自我拦截）
# ---------------------------------------------------------------------------
FAKE_SECRET = "".join(["Super", "Secret", "1234567890", "abc"])  # 通用长口令样本
FAKE_AWS_KEY = "".join(["AKIA", "ZZ7XKQ2MNP4RSTUV"])  # AWS Access Key 形态
FAKE_GH_TOKEN = "".join(["ghp_", "ABCDEFGH", "IJKLMNOP", "QRSTUVWX", "YZabcdefghij"])
FAKE_HEX_KEY = "".join(["8f2a9c1b7e4d6f3a", "0b5c8e2d9f1a4b7c"])  # 高熵十六进制形态
FAKE_PRIVATE_KEY_HEADER = "".join(["-----BEGIN ", "RSA PRIVATE KEY-----"])


class TestScanText:
    """scan_text 的规则命中/白名单/脱敏行为。"""

    def test_plaintext_password_variants_detected(self):
        # 下划线/大写前缀命名必须命中（曾因 \b 词边界漏检）
        for line in (
            f'password = "{FAKE_SECRET}"',
            f'db_password = "{FAKE_SECRET}"',
            f'DB_PASSWORD="{FAKE_SECRET}"',
            f'db_password="{FAKE_SECRET}"',
        ):
            assert scan_text(line, "x"), f"应命中但未命中: {line}"

    def test_known_token_shapes_detected(self):
        lines = [
            f'aws_access_key_id = "{FAKE_AWS_KEY}"',
            f'token = "{FAKE_GH_TOKEN}"',
            FAKE_PRIVATE_KEY_HEADER,
            f'api_key = "{FAKE_HEX_KEY}"',
        ]
        for line in lines:
            assert scan_text(line, "x"), f"应命中但未命中: {line}"

    def test_safe_lines_not_detected(self):
        lines = [
            'password = os.environ["DB_PASSWORD"]',
            'password = "${DB_PASSWORD}"',
            'api_key = "<YOUR_API_KEY>"',
            'password = "your-password-here"',
            'password = "placeholder"',
            "def add(a, b):\n    return a + b",
            'xpassword = "abcdefghijklmnopqrstuvwxyz"',
        ]
        for line in lines:
            assert not scan_text(line, "x"), f"不应命中但命中: {line}"

    def test_line_number_is_one_based(self):
        text = "safe line\n" + f'db_password = "{FAKE_SECRET}"\n'
        findings = scan_text(text, "f.txt")
        assert len(findings) == 1
        assert findings[0].line_no == 2
        assert findings[0].file == "f.txt"

    def test_snippet_is_masked(self):
        findings = scan_text(f'db_password = "{FAKE_SECRET}"', "f.txt")
        assert findings
        masked = findings[0].masked_snippet
        # 不得出现完整凭据
        assert FAKE_SECRET not in masked
        assert "..." in masked


class TestMaskAndWhitelist:
    """脱敏与白名单辅助函数。"""

    def test_mask_short_value_all_stars(self):
        assert mask("abc") == "***"

    def test_mask_keeps_only_edges(self):
        out = mask(FAKE_SECRET)
        assert out.startswith("Supe")
        assert "0abc" in out  # 保留尾部 4 字符
        assert f"(len={len(FAKE_SECRET)})" in out
        assert FAKE_SECRET not in out

    def test_is_whitelisted(self):
        assert is_whitelisted('api_key = "<YOUR_API_KEY>"')
        assert is_whitelisted('password = os.environ["X"]')
        assert not is_whitelisted(f'db_password = "{FAKE_SECRET}"')


class TestScanFiles:
    """scan_files 的文件级行为与健壮性。"""

    def test_scan_files_detects_and_skips_missing(self, tmp_path):
        leak = tmp_path / "leak.py"
        leak.write_text(f'db_password = "{FAKE_SECRET}"\n', encoding="utf-8")
        clean = tmp_path / "clean.py"
        clean.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        findings = scan_files([str(leak), str(clean), str(tmp_path / "nope.py")])
        assert len(findings) == 1
        assert findings[0].file == str(leak)

    def test_scan_files_skips_binary_suffix(self, tmp_path):
        blob = tmp_path / "img.png"
        blob.write_text(f'db_password = "{FAKE_SECRET}"\n', encoding="utf-8")
        assert scan_files([str(blob)]) == []

    def test_scan_files_tolerates_decode_errors(self, tmp_path):
        f = tmp_path / "bin.dat"
        f.write_bytes(b'\xff\xfe\x00db_password = "' + FAKE_SECRET.encode() + b'"\n')
        # 不应抛异常
        scan_files([str(f)])

    def test_format_findings_masked(self):
        findings = [Finding("f.py", 3, "规则", "pass...abc(len=37)")]
        out = format_findings(findings)
        assert "f.py:3" in out
        assert "pass...abc(len=37)" in out


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, *args], capture_output=True, text=True, check=True
    )


class _DummyShare(ShareManager):
    """最小可实例化的 ShareManager，用于测试 commit_and_push 闸门。"""

    def __init__(self, repo_path, bare_path):
        self.central_repo_url = bare_path
        self.repo_name = "dummy"
        self.repo_path = repo_path

    def get_resource_type(self):
        return "测试资源"

    def format_resource_display(self, resource):
        return ""

    def get_existing_resources(self):
        return set()

    def get_local_resources(self):
        return []

    def share_resources(self, resources):
        return []


def _init_repo(tmp_path):
    """建一个 bare origin + clone 出的工作区，返回 (work, bare)。"""
    bare = tmp_path / "central.git"
    work = tmp_path / "central_work"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True)
    _git(str(work), "config", "user.email", "t@t")
    _git(str(work), "config", "user.name", "t")
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(str(work), "add", ".")
    _git(str(work), "commit", "-q", "-m", "init")
    branch = _git(str(work), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    _git(str(work), "push", "-q", "-u", "origin", branch)
    return work, bare


def _head(work):
    return _git(str(work), "rev-parse", "HEAD").stdout.strip()


def _remote_head(bare):
    return subprocess.run(
        ["git", "--git-dir", str(bare), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


class TestCommitAndPushGate:
    """分享闸门：命中中止、干净放行、绕过生效。"""

    def test_blocks_secret_and_does_not_commit_or_push(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_ALLOW_SECRETS", raising=False)
        work, bare = _init_repo(tmp_path)
        (work / "leak.py").write_text(
            f'db_password = "{FAKE_SECRET}"\n', encoding="utf-8"
        )
        before_head, before_remote = _head(work), _remote_head(bare)

        mgr = _DummyShare(str(work), str(bare))
        try:
            mgr.commit_and_push(1)
            raise AssertionError("应中止但未中止")
        except RuntimeError:
            pass

        assert _head(work) == before_head
        assert _remote_head(bare) == before_remote

    def test_clean_content_commits_and_pushes(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JARVIS_ALLOW_SECRETS", raising=False)
        work, bare = _init_repo(tmp_path)
        (work / "clean.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8"
        )
        before_head = _head(work)

        mgr = _DummyShare(str(work), str(bare))
        mgr.commit_and_push(1)

        after_head = _head(work)
        assert after_head != before_head
        assert _remote_head(bare) == after_head

    def test_bypass_env_allows_secret(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_ALLOW_SECRETS", "1")
        work, bare = _init_repo(tmp_path)
        (work / "leak.py").write_text(
            f'db_password = "{FAKE_SECRET}"\n', encoding="utf-8"
        )
        before_head = _head(work)

        mgr = _DummyShare(str(work), str(bare))
        mgr.commit_and_push(1)

        assert _head(work) != before_head
