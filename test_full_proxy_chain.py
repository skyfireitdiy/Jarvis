#!/usr/bin/env python3
"""测试完整的代理链路：模拟 Agent → Master → zte-pc → LLM"""

import asyncio
import httpx
import json


async def test_full_chain():
    import os

    # 配置
    MASTER_URL = "http://jvs-ai.cn:8000"  # Master 节点
    PROXY_NODE = "zte-pc"
    LLM_BASE_URL = "https://nebulacoder-maas.zte.com.cn/v1"  # 目标 LLM
    API_KEY = "604d32a2-c691-4373-a3e2-e3b6ea97f924"
    AUTH_TOKEN = os.environ.get(
        "JARVIS_AUTH_TOKEN", "c08f00c0-8155-4e6a-ad8e-2b67aa1dc81d"
    )

    # 构建代理 URL（与 openai.py 中的转换逻辑一致）
    proxy_url = (
        f"{MASTER_URL}/api/node/{PROXY_NODE}/http_proxy/{LLM_BASE_URL}/chat/completions"
    )

    print("=" * 60)
    print("测试完整代理链路")
    print("=" * 60)
    print(f"代理 URL: {proxy_url}")
    print(f"目标 LLM: {LLM_BASE_URL}")
    print()

    payload = {
        "model": "nebulacoder-v8.0",
        "messages": [{"role": "user", "content": "Hello, please respond briefly."}],
        "max_tokens": 20,
        "stream": False,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",  # LLM API Key (OpenAI SDK 格式)
        "X-Jarvis-Token": AUTH_TOKEN,  # Master 节点认证 token
    }

    try:
        print("正在发送请求...")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(proxy_url, json=payload, headers=headers)

            print(f"\n响应状态码：{response.status_code}")
            print(f"响应头：{dict(response.headers)}")
            print("\n响应体:")

            if response.status_code == 200:
                data = response.json()
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(response.text)

    except httpx.ConnectError as e:
        print(f"\n❌ 连接错误：{e}")
        print("可能原因：")
        print("  1. Master 节点 (jvs-ai.cn:8000) 无法访问")
        print("  2. Master 节点与 zte-pc 之间的 WebSocket 连接断开")
        print("  3. zte-pc 节点服务未运行")
    except httpx.TimeoutException as e:
        print(f"\n❌ 请求超时：{e}")
        print("可能原因：")
        print("  1. 网络延迟高")
        print("  2. zte-pc 处理请求慢")
        print("  3. LLM 响应慢")
    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP 错误：{e}")
        print(f"响应内容：{e.response.text}")
    except Exception as e:
        print(f"\n❌ 未知错误：{type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print("诊断建议:")
    print("=" * 60)
    print("1. 确认 Master 节点服务是否运行：curl http://jvs-ai.cn:8000/api/node/status")
    print("2. 确认 zte-pc 节点是否连接到 Master")
    print("3. 检查 Master 和 zte-pc 的日志")


if __name__ == "__main__":
    asyncio.run(test_full_chain())
