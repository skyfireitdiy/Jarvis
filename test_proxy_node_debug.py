#!/usr/bin/env python3
"""调试 proxy_node 链路问题。"""

import asyncio
import httpx


async def test_master_to_zte_pc_proxy():
    """测试从 master 到 zte-pc 的代理链路。"""
    master_url = "http://127.0.0.1:8000"
    target_llm_url = (
        "http://your-internal-llm-url/v1/chat/completions"  # 请替换为实际的内网 LLM URL
    )

    # 构建代理 URL
    proxy_url = f"{master_url}/api/node/zte-pc/http_proxy/{target_llm_url}"

    print(f"测试代理 URL: {proxy_url}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                proxy_url,
                json={
                    "model": "test",
                    "messages": [{"role": "user", "content": "hello"}],
                },
                headers={"Content-Type": "application/json"},
            )
            print(f"响应状态码：{response.status_code}")
            print(f"响应内容：{response.text[:500]}")
    except httpx.ConnectError as e:
        print(f"连接错误：{e}")
        print("可能原因：master 节点无法连接到 zte-pc 节点的 WebSocket")
    except httpx.TimeoutException as e:
        print(f"请求超时：{e}")
    except Exception as e:
        print(f"其他错误：{type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(test_master_to_zte_pc_proxy())
