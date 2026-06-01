# 自我验证机制设计方案

**文档版本**：1.0  
**创建日期**：2026-01-29  
**设计目标**：建立完整的自我验证机制，确保Jarvis在进化过程中保持系统稳定性和代码质量

---

## 概述

本设计方案基于现有的测试基础设施（pytest、ruff、mypy、GitHub Actions），构建一个自动化、可回溯、高覆盖率的自我验证机制，确保Jarvis在持续进化过程中始终保持高质量和稳定性。

### 现有基础设施评估

**优势**：
- ✅ pytest测试框架已配置（52个测试文件）
- ✅ 代码质量工具：ruff（代码检查）、mypy（类型检查）
- ✅ CI/CD集成：.github/workflows/test.yml
- ✅ 完整的tests/目录结构（16个子模块）

**待补充**：
- ❌ 测试覆盖率工具（pytest-cov/coverage.py）
- ❌ 覆盖率报告生成
- ❌ CI/CD中的覆盖率检查
- ❌ 自动化测试框架扩展
- ❌ 回归测试系统
- ❌ 监控告警系统

---

## 1. 自动化测试框架设计方案

### 1.1 目标

- 扩展现有pytest框架，实现代码质量、架构健康度、性能指标的自动化测试
- 达到80%以上的测试覆盖率
- 支持持续集成和自动化执行

### 1.2 工具选择

**核心工具**：
- **pytest**：主要测试框架（已配置）
- **pytest-cov**：测试覆盖率工具（需添加）
- **pytest-xdist**：并行测试执行（需添加）
- **pytest-benchmark**：性能测试（需添加）
- **pytest-asyncio**：异步测试支持（需添加）
- **ruff**：代码风格和错误检查（已配置）
- **mypy**：静态类型检查（已配置）
- **bandit**：安全漏洞扫描（需添加）

**辅助工具**：
- **pytest-html**：HTML测试报告（需添加）
- **coverage**：覆盖率报告工具（需添加）
- **tox**：多环境测试管理（需添加）

### 1.3 实施步骤

#### 步骤1：增强pytest配置

**操作**：创建/更新 `pytest.ini` 或 `pyproject.toml` 中的pytest配置

```ini
[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --strict-markers --cov=src --cov-report=html --cov-report=term --cov-report=xml"
testpaths = ["tests"]
python_files = ["test_*.py", "*_test.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
markers = [
    "slow: marks tests as slow (deselect with '-m "not slow"')",
    "integration: marks tests as integration tests",
    "unit: marks tests as unit tests",
    "smoke: marks tests as smoke tests",
    "security: marks tests as security tests",
    "performance: marks tests as performance tests",
]
```

**文件**：`pyproject.toml` 或新建 `pytest.ini`

#### 步骤2：添加覆盖率工具

**操作**：将pytest-cov添加到依赖

```bash
# 添加到 pyproject.toml 的 dev 依赖
pip install pytest-cov coverage
```

**文件**：`pyproject.toml`

**修改位置**：第70行的 dev 依赖列表
```toml
dev = ["pytest", "pytest-cov", "coverage", "ruff", "mypy", "build", "twine"]
```

#### 步骤3：创建测试基类和工具模块

**操作**：创建测试工具模块，提供通用测试工具和断言

**文件**：`tests/test_utils/` 目录
- `tests/test_utils/__init__.py`
- `tests/test_utils/assertions.py`：自定义断言
- `tests/test_utils/fixtures.py`：通用fixtures
- `tests/test_utils/helpers.py`：测试辅助函数

#### 步骤4：扩展conftest.py

**操作**：在现有的 `tests/conftest.py` 中添加更多fixtures

**新增fixtures**：
- `mock_openai_response()`: 模拟OpenAI响应
- `mock_anthropic_response()`: 模拟Anthropic响应
- `sample_code_file()`: 示例代码文件
- `sample_project_structure()`: 示例项目结构
- `performance_thresholds()`: 性能阈值配置

#### 步骤5：添加性能测试框架

**操作**：集成pytest-benchmark进行性能测试

```python
# tests/performance/test_agent_performance.py
import pytest

class TestAgentPerformance:
    def test_code_generation_speed(benchmark):
        def generate_code():
            # 测试代码生成速度
            pass
        
        result = benchmark(generate_code)
        assert result < 1.0  # 小于1秒
```

**文件**：`tests/performance/` 目录

#### 步骤6：添加安全测试框架

**操作**：集成bandit进行安全扫描

```bash
# 运行安全扫描
bandit -r src/ -f json -o security_report.json
```

**文件**：`tests/security/` 目录

### 1.4 验收标准

- [ ] pytest-cov已集成，覆盖率报告可生成
- [ ] 测试覆盖率达到80%以上
- [ ] 性能测试框架可用，关键操作有基准测试
- [ ] 安全扫描工具集成，无高危漏洞
- [ ] HTML测试报告可正常生成
- [ ] 所有测试可以在5分钟内完成

---

## 2. 回归测试系统设计方案

### 2.1 目标

- 确保进化活动不破坏现有功能
- 自动化执行回归测试套件
- 快速发现和定位回归问题

### 2.2 工具选择

**核心工具**：
- **pytest**：回归测试执行框架（已配置）
- **pytest-xdist**：并行测试加速（需添加）
- **pytest-rerunfailures**：失败重试机制（需添加）
- **git**：版本控制和变更检测（已配置）

**辅助工具**：
- **pytest-html**：测试结果报告（需添加）
- **allure-pytest**：增强测试报告（需添加）

### 2.3 实施步骤

#### 步骤1：定义回归测试套件

**操作**：在 `tests/` 目录下创建回归测试专用目录

**目录结构**：
```
tests/
├── regression/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_critical_functions.py
│   ├── test_api_compatibility.py
│   ├── test_data_integrity.py
│   └── test_user_workflows.py
```

**文件**：`tests/regression/` 目录

#### 步骤2：创建回归测试配置

**操作**：创建回归测试专用pytest配置

**文件**：`tests/regression/conftest.py`

```python
import pytest

# 只运行标记为 regression 的测试
def pytest_configure(config):
    config.addinivalue_line("markers", "regression: marks tests as regression tests")

# 回归测试专用fixture
@pytest.fixture(scope="session")
def regression_test_data():
    """回归测试数据"""
    return {
        "critical_functions": [
            "jarvis_agent",
            "code_agent",
            "git_utils",
        ],
        "api_endpoints": [
            "/api/agent/chat",
            "/api/code/analyze",
        ],
    }
```

#### 步骤3：实现关键功能回归测试

**操作**：为核心功能编写回归测试

**文件**：`tests/regression/test_critical_functions.py`

```python
import pytest
from jarvis.jarvis_agent import JarvisAgent

class TestCriticalFunctions:
    """测试关键功能是否正常工作"""
    
    @pytest.mark.regression
    def test_agent_initialization(self):
        """测试Agent初始化"""
        agent = JarvisAgent()
        assert agent is not None
        assert agent.is_initialized()
    
    @pytest.mark.regression
    def test_code_agent_execution(self):
        """测试代码Agent执行"""
        from jarvis.jarvis_code_agent import CodeAgent
        agent = CodeAgent()
        result = agent.analyze_code("print('hello')")
        assert result is not None
```

#### 步骤4：创建变更检测机制

**操作**：创建脚本检测代码变更，触发回归测试

**文件**：`scripts/run_regression_tests.sh`

```bash
#!/bin/bash
# 回归测试脚本

# 获取变更的文件
CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD)

# 判断是否需要运行回归测试
if echo "$CHANGED_FILES" | grep -q "src/"; then
    echo "检测到源代码变更，运行回归测试..."
    pytest tests/regression/ -v --tb=short --reruns 2
else
    echo "未检测到源代码变更，跳过回归测试"
fi
```

#### 步骤5：集成到CI/CD

**操作**：更新 `.github/workflows/test.yml`

**文件**：`.github/workflows/test.yml`

```yaml
- name: Run regression tests
  run: |
    pytest tests/regression/ -v --cov=src --cov-report=xml
  if: github.event_name == 'pull_request'
```

#### 步骤6：创建回归测试报告

**操作**：生成详细的回归测试报告

**文件**：`scripts/generate_regression_report.py`

```python
#!/usr/bin/env python3
"""生成回归测试报告"""

import json
import subprocess
from datetime import datetime

def generate_report():
    """生成回归测试报告"""
    # 运行测试
    result = subprocess.run(
        ["pytest", "tests/regression/", "--json-report", "--json-report-file=report.json"],
        capture_output=True,
        text=True
    )
    
    # 生成HTML报告
    # ...

if __name__ == "__main__":
    generate_report()
```

### 2.4 验收标准

- [ ] 回归测试套件包含至少20个关键测试
- [ ] 回归测试可在3分钟内完成
- [ ] 变更检测机制正常工作
- [ ] CI/CD集成回归测试
- [ ] 回归测试报告可正常生成
- [ ] 回归测试失败时能够快速定位问题

---

## 3. 监控告警系统设计方案

### 3.1 目标

- 实时监控系统健康状态
- 自动检测异常并发出告警
- 记录监控指标，支持趋势分析

### 3.2 工具选择

**核心工具**：
- **pytest**：健康检查测试（已配置）
- **Prometheus**：指标收集和存储（需添加）
- **Grafana**：可视化监控仪表板（需添加）
- **Alertmanager**：告警管理（需添加）

**Python库**：
- **prometheus_client**：Python Prometheus客户端（需添加）
- **psutil**：系统资源监控（需添加）
- **logging**：日志记录（已配置）

### 3.3 实施步骤

#### 步骤1：创建健康检查模块

**操作**：创建健康检查模块，监控关键指标

**文件**：`src/jarvis/jarvis_monitor/health_check.py`

```python
import psutil
import time
from typing import Dict, Any

def check_system_health() -> Dict[str, Any]:
    """检查系统健康状态"""
    return {
        "cpu_usage": psutil.cpu_percent(interval=1),
        "memory_usage": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "timestamp": time.time(),
    }

def check_service_health() -> Dict[str, Any]:
    """检查服务健康状态"""
    return {
        "agent_status": "running",
        "code_agent_status": "running",
        "memory_organizer_status": "running",
        "timestamp": time.time(),
    }
```

#### 步骤2：集成Prometheus客户端

**操作**：添加Prometheus指标导出

**文件**：`src/jarvis/jarvis_monitor/metrics.py`

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# 定义指标
REQUEST_COUNT = Counter('jarvis_requests_total', 'Total requests', ['method', 'endpoint'])
REQUEST_LATENCY = Histogram('jarvis_request_duration_seconds', 'Request latency')
SYSTEM_CPU = Gauge('jarvis_system_cpu_percent', 'System CPU usage')
SYSTEM_MEMORY = Gauge('jarvis_system_memory_percent', 'System memory usage')

def start_metrics_server(port: int = 9090):
    """启动Prometheus metrics服务器"""
    start_http_server(port)
```

#### 步骤3：创建监控告警规则

**操作**：定义Prometheus告警规则

**文件**：`monitoring/prometheus-alerts.yml`

```yaml
groups:
  - name: jarvis_alerts
    rules:
      - alert: HighCPUUsage
        expr: jarvis_system_cpu_percent > 80
        for: 5m
        annotations:
          summary: "High CPU usage detected"
      
      - alert: HighMemoryUsage
        expr: jarvis_system_memory_percent > 85
        for: 5m
        annotations:
          summary: "High memory usage detected"
      
      - alert: HighErrorRate
        expr: rate(jarvis_requests_total{status="error"}[5m]) > 0.1
        for: 5m
        annotations:
          summary: "High error rate detected"
```

#### 步骤4：创建Grafana仪表板

**操作**：创建监控仪表板配置

**文件**：`monitoring/grafana-dashboard.json`

```json
{
  "dashboard": {
    "title": "Jarvis System Monitor",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [{"expr": "jarvis_system_cpu_percent"}]
      },
      {
        "title": "Memory Usage",
        "targets": [{"expr": "jarvis_system_memory_percent"}]
      },
      {
        "title": "Request Rate",
        "targets": [{"expr": "rate(jarvis_requests_total[5m])"}]
      }
    ]
  }
}
```

#### 步骤5：创建告警通知系统

**操作**：实现告警通知机制

**文件**：`src/jarvis/jarvis_monitor/alerting.py`

```python
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def send_alert(alert: Dict[str, Any]):
    """发送告警通知"""
    logger.error(f"Alert: {alert['summary']}")
    # 可以扩展为发送邮件、Slack、钉钉等通知

def check_thresholds(metrics: Dict[str, Any]):
    """检查指标是否超过阈值"""
    if metrics['cpu_usage'] > 80:
        send_alert({
            'summary': 'High CPU usage',
            'value': metrics['cpu_usage'],
            'severity': 'warning'
        })
```

#### 步骤6：集成到测试框架

**操作**：在pytest中集成健康检查

**文件**：`tests/monitoring/test_health_checks.py`

```python
import pytest
from jarvis.jarvis_monitor.health_check import check_system_health

class TestHealthChecks:
    """测试健康检查"""
    
    @pytest.mark.monitoring
    def test_system_cpu_usage(self):
        """测试系统CPU使用率"""
        health = check_system_health()
        assert health['cpu_usage'] < 90, f"CPU usage too high: {health['cpu_usage']}%"
    
    @pytest.mark.monitoring
    def test_system_memory_usage(self):
        """测试系统内存使用率"""
        health = check_system_health()
        assert health['memory_usage'] < 90, f"Memory usage too high: {health['memory_usage']}%"
```

### 3.4 验收标准

- [ ] 健康检查模块可正常运行
- [ ] Prometheus metrics可正常导出
- [ ] Grafana仪表板可正常显示指标
- [ ] 告警规则可正常触发
- [ ] 告警通知可正常发送
- [ ] 监控数据至少保留30天

---

## 4. 实施计划

### 阶段1：基础增强（1周）
- [ ] 添加pytest-cov和覆盖率配置
- [ ] 扩展conftest.py添加更多fixtures
- [ ] 创建测试工具模块

### 阶段2：回归测试（1周）
- [ ] 创建回归测试套件
- [ ] 实现变更检测机制
- [ ] 集成到CI/CD

### 阶段3：监控告警（1周）
- [ ] 创建健康检查模块
- [ ] 集成Prometheus和Grafana
- [ ] 配置告警规则

### 阶段4：优化完善（1周）
- [ ] 性能测试框架
- [ ] 安全扫描集成
- [ ] 测试报告优化

---

## 5. 风险评估

### 技术风险
- **风险**：新工具集成可能引入兼容性问题
- **缓解**：充分测试后再集成到生产环境

### 性能风险
- **风险**：大量测试可能影响开发效率
- **缓解**：使用pytest-xdist并行执行测试

### 维护风险
- **风险**：测试套件维护成本高
- **缓解**：保持测试简单、独立、可维护

---

## 6. 成功指标

- 测试覆盖率 ≥ 80%
- 回归测试执行时间 ≤ 3分钟
- 系统健康检查响应时间 ≤ 1秒
- 告警准确率 ≥ 95%
- 监控数据完整性 ≥ 99%

---

**文档结束**

**下一步**：执行任务7 - 设计自我修复机制方案