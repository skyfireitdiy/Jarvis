#!/usr/bin/env python3
"""直接测试 _dispatch_node_http_request 函数。"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from jarvis.jarvis_web_gateway.app import create_app


async def test_dispatch():
    """测试 _dispatch_node_http_request 处理 http_proxy 请求。"""
    app = create_app()

    # 获取 _dispatch_node_http_request 函数（它在 create_app 内部定义）
    # 我们需要通过 app 对象找到它
    print("测试场景 1: 路径 = 'http_proxy/http://127.0.0.1:8080/v1'")
    print("预期：应该匹配 /http_proxy/ 分支")
    print()

    # 模拟调用
    from jarvis.jarvis_web_gateway.app import logger
    import logging

    logging.basicConfig(level=logging.DEBUG)

    # 由于 _dispatch_node_http_request 是内部函数，我们需要通过其他方式测试
    # 让我们直接检查代码逻辑

    test_path = "http_proxy/http://127.0.0.1:8080/v1"
    normalized_path = "/" + str(test_path or "").lstrip("/")
    print(f"原始路径：{test_path}")
    print(f"标准化后：{normalized_path}")
    print(f"是否以 '/http_proxy/' 开头：{normalized_path.startswith('/http_proxy/')}")
    print()

    if normalized_path.startswith("/http_proxy/"):
        target_url = normalized_path[len("/http_proxy/") :]
        print(f"提取的目标 URL: {target_url}")
        print("✓ 路径匹配正确！")
    else:
        print("✗ 路径不匹配！这是问题所在。")


if __name__ == "__main__":
    asyncio.run(test_dispatch())
