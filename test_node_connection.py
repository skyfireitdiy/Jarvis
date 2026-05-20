#!/usr/bin/env python3
"""检查 master 节点上的节点连接状态。"""

import asyncio
import httpx


async def check_node_connections():
    """检查 master 节点上有哪些节点已连接。"""
    master_url = "http://127.0.0.1:8000"

    # 尝试调用节点状态 API（如果存在）
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 尝试获取节点状态
            response = await client.get(f"{master_url}/api/node/status")
            print(f"节点状态 API 响应：{response.status_code}")
            if response.status_code == 200:
                print(f"响应内容：{response.json()}")
    except Exception as e:
        print(f"无法连接到 master 节点：{e}")

    print("\n请手动检查以下内容：")
    print("1. 在 master 节点的日志中搜索 'node connection' 或 'zte-pc'")
    print("2. 确认 zte-pc 节点是否已启动并连接到 master")
    print("3. 检查 zte-pc 节点配置中的 master URL 是否正确")


if __name__ == "__main__":
    asyncio.run(check_node_connections())
