# 🧰 Jarvis Tool - 工具管理系统

<div align="center">
  <img src="../images/jarvis-tool.png" alt="Jarvis Tool" width="250" style="margin-bottom: 20px"/>
  
  *智能工具扩展与管理中心*
  
  ![Version](https://img.shields.io/badge/version-0.1.x-blue)
  ![Status](https://img.shields.io/badge/status-stable-green)
</div>

## 🔮 魔法简介
Jarvis Tool 是 Jarvis 生态系统的工具管理中心，用于注册、管理和调用各种工具功能。它使用结构化格式定义工具接口，支持动态加载内置和外部工具，并通过智能路由将任务分配给合适的工具执行，是整个 Jarvis 系统的能力扩展基础。

## ✨ 核心特性
- **工具注册管理** - 统一管理所有可用工具
- **动态工具发现** - 自动加载内置和外部工具
- **结构化接口** - 标准化的工具定义与调用接口
- **智能调用分发** - 根据请求智能匹配合适的工具
- **权限与安全控制** - 工具调用前的安全检查机制
- **工具开发框架** - 简化新工具的创建和集成

## 🚀 使用方法
```bash
jarvis-tool [command] [options]
```

### 📋 可用命令
- `list` - 列出所有已注册的工具
- `info <工具名称>` - 查看特定工具的详细信息
- `add <工具文件>` - 添加新的外部工具
- `remove <工具名称>` - 移除已注册的工具
- `call <工具名称> [参数]` - 直接调用特定工具

## 💎 工具开发指南
Jarvis Tool 提供了简单而强大的框架来开发和集成新工具。

### 基本工具结构
```python
from typing import Dict, Any
from jarvis.jarvis_utils.output import OutputType, PrettyOutput

class MyNewTool:
    name = "my_new_tool"
    description = "这是我的新工具，用于执行特定功能"
    parameters = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "第一个参数的描述"
            },
            "param2": {
                "type": "integer",
                "description": "第二个参数的描述"
            }
        },
        "required": ["param1"]
    }
    
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # 工具的主要实现逻辑
        param1 = args.get("param1", "")
        param2 = args.get("param2", 0)
        
        # 执行操作...
        result = f"处理结果：{param1}, {param2}"
        
        # 返回结果
        return {
            "success": True,
            "stdout": result,
            "stderr": ""
        }
```

### 工具安装位置
- **内置工具**：位于 `src/jarvis/jarvis_tools/` 目录
- **用户工具**：位于 `~/.jarvis/tools/` 目录

## 🔍 内置工具一览

| 工具名称 | 描述 | 典型用途 |
|---------|------|---------|
| `read_code` | 读取代码文件内容 | 分析和理解源代码 |
| `execute_shell` | 执行shell命令 | 系统操作和自动化 |
| `execute_shell_script` | 执行shell脚本文件 | 运行复杂的系统任务 |
| `ask_codebase` | 查询代码库信息 | 代码理解和探索 |
| `ask_user` | 向用户请求输入 | 交互式信息收集 |
| `file_operation` | 文件基本操作 | 读写和管理文件 |
| `search_web` | 网络搜索功能 | 获取外部信息 |
| `read_webpage` | 读取网页内容 | 网络内容分析 |
| `git_commiter` | Git提交助手 | 自动化代码提交 |
| `code_review` | 代码审查工具 | 代码质量评估 |
| `rag` | 检索增强生成 | 文档查询和问答 |

## 💡 高级使用技巧

### 工具组合调用
通过组合多个基础工具，解决复杂问题：
```python
# 示例：搜索网络信息并保存到文件
search_result = search_web_tool.execute({"query": "最新AI发展趋势"})
file_operation_tool.execute({
    "operation": "write",
    "path": "ai_trends.md",
    "content": search_result["stdout"]
})
```

### 工具权限控制
限制某些工具的使用范围，增强安全性：
```python
# 在代理初始化时只启用特定工具
tool_registry = ToolRegistry()
tool_registry.use_tools([
    "read_code", 
    "ask_user", 
    "search_web"
])
```

### 自定义工具链
创建针对特定领域的工具组合：
```python
# 开发专用工具链
dev_tools = ToolRegistry()
dev_tools.use_tools([
    "read_code", 
    "code_review"
])
```

## 🌟 工具开发最佳实践
- **单一职责原则** - 每个工具专注于一个明确的功能
- **详细的参数描述** - 提供清晰的参数说明和类型定义
- **健壮的错误处理** - 妥善处理各种异常情况
- **有意义的返回值** - 返回结构化且有用的执行结果
- **命令行兼容性** - 支持作为独立命令行工具使用
- **详细的日志记录** - 记录工具执行过程和关键节点

---

<div align="center">
  <p><i>Jarvis Tool - 打造您自己的智能工具生态系统</i></p>
</div> 