"""
统计模块测试脚本
"""

from datetime import datetime, timedelta
import random
import time

from jarvis.jarvis_stats.stats import StatsManager


def test_basic_functionality():
    """测试基本功能"""
    print("=== 测试基本功能 ===\n")

    # 创建统计管理器
    stats = StatsManager()

    # 添加一些测试数据
    print("1. 添加测试数据...")

    # API调用次数
    for i in range(50):
        stats.increment("api_calls", tags={"endpoint": f"/api/v{random.randint(1,3)}"})
        time.sleep(0.01)

    # 响应时间
    for i in range(30):
        response_time = random.uniform(0.1, 2.0)
        stats.increment(
            "response_time",
            amount=response_time,
            unit="seconds",
            tags={"status": random.choice(["200", "404", "500"])},
        )
        time.sleep(0.01)

    # 错误计数
    for i in range(10):
        stats.increment(
            "error_count", tags={"type": random.choice(["timeout", "404", "500"])}
        )
        time.sleep(0.01)

    print("✓ 数据添加完成\n")

    # 显示所有指标摘要
    print("2. 显示所有指标摘要:")
    stats.show()

    # 显示具体指标的表格数据
    print("\n3. 显示 response_time 表格数据:")
    stats.show("response_time", last_hours=1)

    # 显示图表
    print("\n4. 显示 response_time 折线图:")
    stats.plot("response_time", last_hours=1, aggregation="hourly")

    # 显示汇总信息
    print("\n5. 显示 api_calls 汇总信息:")
    stats.show("api_calls", last_hours=1, format="summary", aggregation="hourly")

    # 获取原始数据
    print("\n6. 获取 error_count 原始数据:")
    data = stats.get_stats("error_count", last_hours=1)
    print(f"记录数: {data['count']}")
    print(f"时间范围: {data['start_time']} ~ {data['end_time']}")

    # 获取聚合数据
    print("\n7. 获取 api_calls 聚合数据:")
    aggregated = stats.get_stats("api_calls", last_hours=1, aggregation="hourly")
    for time_key, stats_data in list(aggregated.items())[:3]:
        print(f"{time_key}: count={stats_data['count']}, avg={stats_data['avg']:.2f}")


def test_historical_data():
    """测试历史数据功能"""
    print("\n\n=== 测试历史数据功能 ===\n")

    stats = StatsManager()

    # 添加过去7天的数据
    print("1. 添加过去7天的模拟数据...")
    now = datetime.now()

    for days_ago in range(7, -1, -1):
        timestamp = now - timedelta(days=days_ago)

        # 每天添加多个数据点
        for hour in range(0, 24, 4):
            ts = timestamp.replace(hour=hour, minute=0, second=0)

            # 网站访问量（有日周期性）
            visits = 100 + hour * 10 + random.randint(-20, 20)
            stats.storage.add_metric("website_visits", visits, unit="次", timestamp=ts)

            # CPU使用率（有日周期性）
            cpu_usage = 30 + hour * 2 + random.uniform(-5, 5)
            stats.storage.add_metric("cpu_usage", cpu_usage, unit="%", timestamp=ts)

    print("✓ 历史数据添加完成\n")

    # 显示不同时间范围的数据
    print("2. 显示最近24小时的网站访问量:")
    stats.plot("website_visits", last_hours=24, aggregation="hourly")

    print("\n3. 显示最近7天的CPU使用率（按天聚合）:")
    stats.plot("cpu_usage", last_days=7, aggregation="daily", height=15)

    print("\n4. 显示最近7天的网站访问量汇总:")
    stats.show("website_visits", last_days=7, format="summary", aggregation="daily")


def test_tags_filtering():
    """测试标签过滤功能"""
    print("\n\n=== 测试标签过滤功能 ===\n")

    stats = StatsManager()

    # 添加带标签的数据
    print("1. 添加带标签的数据...")

    endpoints = ["/api/users", "/api/posts", "/api/comments"]
    methods = ["GET", "POST", "PUT", "DELETE"]

    for i in range(100):
        endpoint = random.choice(endpoints)
        method = random.choice(methods)
        latency = random.uniform(10, 500)

        stats.increment(
            "api_latency",
            amount=latency,
            unit="ms",
            tags={"endpoint": endpoint, "method": method},
        )

    print("✓ 数据添加完成\n")

    # 使用标签过滤
    print("2. 显示 /api/users 端点的延迟:")
    stats.show("api_latency", last_hours=1, tags={"endpoint": "/api/users"})

    print("\n3. 显示 POST 请求的延迟图表:")
    stats.plot("api_latency", last_hours=1, tags={"method": "POST"}, height=12)


if __name__ == "__main__":
    print("Jarvis 统计模块测试\n")

    # 运行测试
    test_basic_functionality()
    test_historical_data()
    test_tags_filtering()

    print("\n\n✓ 所有测试完成!")
