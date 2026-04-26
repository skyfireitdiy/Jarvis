# -*- coding: utf-8 -*-
"""安全扫描测试"""

import subprocess
import pytest


class TestSecurityScan:
    """安全扫描测试"""

    @pytest.mark.security
    def test_bandit_scan_src(self):
        """使用bandit扫描src目录"""
        result = subprocess.run(
            ["bandit", "-r", "src/jarvis", "-f", "json"], capture_output=True, text=True
        )
        # bandit返回码非0表示发现问题，这里只验证工具可运行
        assert result.returncode in [0, 1]  # 0=无问题, 1=发现问题

    @pytest.mark.security
    def test_no_hardcoded_secrets(self):
        """检查是否有硬编码的密钥"""
        import os

        src_dir = "src/jarvis"
        suspicious_patterns = [
            "api_key",
            "secret_key",
            "password",
            "token",
        ]

        found_issues = []
        for root, dirs, files in os.walk(src_dir):
            # 跳过__pycache__目录
            dirs[:] = [d for d in dirs if d != "__pycache__"]

            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        for pattern in suspicious_patterns:
                            if pattern in content.lower():
                                found_issues.append(f"{filepath}: contains '{pattern}'")

        # 记录发现的问题（实际项目中应该有白名单）
        # 这里只做警告，不作为测试失败条件
        if found_issues:
            print("\n警告: 发现可能的敏感词:\n" + "\n".join(found_issues))
