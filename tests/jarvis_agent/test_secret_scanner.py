# -*- coding: utf-8 -*-
"""share_secret_scanner.extract_secrets 完整敏感值提取单元测试。

与 test_share_secret_scanner.py 同源：样本以「片段拼接」方式在运行时构造，
源码中不出现完整的敏感字面量，避免被 pre-commit 钩子/分享闸门误拦。
"""

from jarvis.jarvis_agent.share_secret_scanner import extract_secrets

# ---------------------------------------------------------------------------
# 运行时构造的测试样本
# ---------------------------------------------------------------------------
FAKE_SECRET = "".join(["Super", "Secret", "1234567890", "abc"])  # 通用长口令样本
FAKE_AWS_KEY = "".join(["AKIA", "ZZ7XKQ2MNP4RSTUV"])  # AWS Access Key 形态
FAKE_GH_TOKEN = "".join(["ghp_", "ABCDEFGH", "IJKLMNOP", "QRSTUVWX", "YZabcdefghij"])
FAKE_SK_KEY = "".join(["sk-", "A1B2C3D4E5F6G7H8", "I9J0K1L2M3N4O5P6", "Q7R8S9T0"])
FAKE_HEX_KEY = "".join(["8f2a9c1b7e4d6f3a", "0b5c8e2d9f1a4b7c"])  # 高熵十六进制形态

# 私钥块头/尾行（拼接构造，避免源码中出现完整私钥字面量被 Gitleaks 拦截）
_PRIV_BEGIN = "".join(["-----BEGIN ", "RSA PRIVATE KEY-----"])
_PRIV_END = "".join(["-----END ", "RSA PRIVATE KEY-----"])


def _priv_block() -> str:
    """构造一个完整私钥块（含头尾行）。"""
    return "\n".join(
        [
            _PRIV_BEGIN,
            "MIIEowIBAAKCAQEA7d2eLx9vC3q0J5k8mN4pR6sT1uW2yX4aB7cD9fG0hJ",
            "zK1lM2nO3pQ4rS5tU6vW7xY8zA9bC0dE1fG2hI3jK4lM5nO6pQ7rS8tU9vW",
            _PRIV_END,
        ]
    )


class TestExtractSecrets:
    """extract_secrets 的完整值提取行为。"""

    def test_extracts_assignment_values(self):
        """赋值型密钥提取引号内实际值，而非含变量名的整行。"""
        text = f'password = "{FAKE_SECRET}"'
        secrets = extract_secrets(text)
        assert secrets == [FAKE_SECRET]

    def test_extracts_known_token_shapes(self):
        """各已知凭据形态返回完整原始值。"""
        text = (
            f'aws_access_key_id = "{FAKE_AWS_KEY}"\n'
            f'token = "{FAKE_GH_TOKEN}"\n'
            f'api_key = "{FAKE_HEX_KEY}"\n'
            f'openai_key = "{FAKE_SK_KEY}"'
        )
        secrets = extract_secrets(text)
        assert FAKE_AWS_KEY in secrets
        assert FAKE_GH_TOKEN in secrets
        assert FAKE_HEX_KEY in secrets
        assert FAKE_SK_KEY in secrets

    def test_private_key_block_extracted_whole(self):
        """私钥块从 BEGIN 行到 END 行整体作为一条敏感值。"""
        block = _priv_block()
        secrets = extract_secrets(block)
        assert secrets == [block]

    def test_private_key_block_embedded_in_text(self):
        """私钥块嵌入在文本中时仍整体提取，且不影响前后行普通值。"""
        block = _priv_block()
        text = f"配置如下：\n{block}\n之后是口令 password = \"{FAKE_SECRET}\""
        secrets = extract_secrets(text)
        assert block in secrets
        assert FAKE_SECRET in secrets

    def test_deduplicates_keeping_order(self):
        """同一敏感值多次出现只保留一次，且保持首次出现顺序。"""
        text = (
            f'password = "{FAKE_SECRET}"\n'
            f'again password = "{FAKE_SECRET}"\n'
            f'token = "{FAKE_GH_TOKEN}"'
        )
        secrets = extract_secrets(text)
        assert secrets == [FAKE_SECRET, FAKE_GH_TOKEN]

    def test_whitelisted_lines_skipped(self):
        """白名单行（环境变量/占位符）不提取。"""
        text = (
            'password = os.environ["DB_PASSWORD"]\n'
            'password = "${DB_PASSWORD}"\n'
            'api_key = "<YOUR_API_KEY>"\n'
            'password = "your-password-here"'
        )
        assert extract_secrets(text) == []

    def test_plain_text_without_secrets_empty(self):
        """无敏感值文本返回空列表。"""
        assert extract_secrets("你好，这是普通文本。") == []
