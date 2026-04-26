# 在项目中引入 CodeAgent 和 Agent

## 1. 概述

### 1.1 CodeAgent 和 Agent 简介

- **Agent**：Jarvis 的基础代理类，提供通用的 AI 助手能力，包括对话管理、工具调用、记忆系统等。
- **CodeAgent**：继承自 Agent 的代码代理类，专门用于处理代码修改、重构和开发任务，提供代码分析、Git 操作、代码审查等功能。

### 1.2 安装

**使用 pip 安装**：

```bash
pip install jarvis-ai-assistant
```

**从源码安装**：

```bash
git clone https://github.com/your-org/jarvis.git
cd jarvis
pip install -e .
```

---

## 2. 使用 Python API

### 2.1 导入 Agent 和 CodeAgent

```python
from jarvis.jarvis_agent import Agent
from jarvis.jarvis_code_agent.code_agent import CodeAgent
```

### 2.2 创建 CodeAgent 实例

**基本创建**：

```python
from jarvis.jarvis_code_agent.code_agent import CodeAgent

# 创建 CodeAgent 实例
agent = CodeAgent(
    llm_group="smart",
    non_interactive=False,
    rule_names="clean_code,security"
)

# 执行任务
agent.run("创建用户认证模块")
```

**完整参数示例**：

```python
agent = CodeAgent(
    llm_group="smart",              # 模型组
    need_summary=True,                # 是否需要总结
    non_interactive=False,            # 是否非交互模式
    rule_names="clean_code,security", # 规则名称（逗号分隔）
    disable_review=False,             # 是否禁用代码审查
    review_max_iterations=3,          # 代码审查最大迭代次数
    enable_task_list_manager=True,    # 是否启用任务列表管理器
    use_methodology=True,              # 是否使用方法论
    use_analysis=True                 # 是否使用分析
)
```

### 2.3 创建 Agent 实例

**基本创建**：

```python
from jarvis.jarvis_agent import Agent

# 创建 Agent 实例
agent = Agent(
    llm_group="smart",
    system_prompt="你是一个有用的 AI 助手",
    use_tools=["search_web", "read_file"]
)

# 执行任务
agent.run("搜索 Python 最佳实践")
```

**完整参数示例**：

```python
agent = Agent(
    llm_group="smart",              # 模型组
    system_prompt="你是一个有用的 AI 助手",  # 系统提示词
    use_tools=["search_web", "read_file"],    # 工具列表
    need_summary=True,                # 是否需要总结
    non_interactive=False,            # 是否非交互模式
    use_methodology=True,             # 是否使用方法论
    use_analysis=True                 # 是否使用分析
)
```

### 2.4 在项目中使用

**示例 1：在脚本中使用 CodeAgent**

```python
#!/usr/bin/env python3
"""使用 CodeAgent 自动生成代码"""

from jarvis.jarvis_code_agent.code_agent import CodeAgent

def main():
    # 创建 CodeAgent
    agent = CodeAgent(
        llm_group="smart",
        non_interactive=True,
        rule_names="clean_code,security"
    )
    
    # 执行任务
    task = """
    创建用户认证模块：
    1. 实现用户注册功能
    2. 实现用户登录功能
    3. 添加 JWT token 生成
    4. 编写单元测试
    """
    
    agent.run(task)

if __name__ == "__main__":
    main()
```

**示例 2：在 CI/CD 中使用**

```python
#!/usr/bin/env python3
"""CI/CD 中使用 CodeAgent 自动修复代码"""

from jarvis.jarvis_code_agent.code_agent import CodeAgent

def auto_fix_code():
    agent = CodeAgent(
        llm_group="smart",
        non_interactive=True,
        rule_names="code_review"
    )
    
    task = """
    审查并修复代码中的问题：
    1. 修复 lint 错误
    2. 修复类型注解问题
    3. 修复安全漏洞
    """
    
    agent.run(task)

if __name__ == "__main__":
    auto_fix_code()
```

**示例 3：在测试中使用 Agent**

```python
"""使用 Agent 进行测试辅助"""

from jarvis.jarvis_agent import Agent

def test_with_agent():
    agent = Agent(
        llm_group="smart",
        use_tools=["read_file", "execute_script"]
    )
    
    # 使用 Agent 分析测试结果
    result = agent.run("分析测试输出，找出失败的测试用例")
    return result
```
