# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[快速开始](#quick-start) •
[配置说明](#configuration) •
[工具说明](#tools) •
[扩展开发](#extensions) •
[贡献指南](#contributing) •
[许可证](#license) •
</div>

---

## 🚀 快速开始 <a id="quick-start"></a>
### 安装
```bash
git clone https://github.com/skyfireitdiy/Jarvis
cd Jarvis
pip3 install -e .
```

### 最小化配置

#### 腾讯元宝
```bash
JARVIS_PLATFORM=yuanbao
JARVIS_MODEL=deep_seek_v3
JARVIS_THINKING_PLATFORM=yuanbao
JARVIS_THINKING_MODEL=deep_seek

YUANBAO_COOKIES=<元宝cookies>
YUANBAO_AGENT_ID=<元宝AgentID>
```

元宝cookies以及AgentID获取方式：

![元宝cookies以及AgentID获取方式](docs/images/yuanbao.png)

浏览器地址栏中那部分是AgentID。


#### Kimi
```bash
JARVIS_PLATFORM=kimi
JARVIS_MODEL=kimi
JARVIS_THINKING_PLATFORM=kimi
JARVIS_THINKING_MODEL=k1

KIMI_API_KEY=<Kimi API KEY>
```

Kimi API Key获取方式：

![Kimi API Key获取方式](docs/images/kimi.png)

删除Bearer前缀，剩下的内容就是Kimi API Key。

以上配置编写到`~/.jarvis/env`文件中。

### 基本使用
```bash
# 使用通用代理
jarvis

# 使用代码代理
jarvis-code-agent
# 或者 jca

# 使用智能shell的功能
jarvis-smart-shell --help
# 或者 jss

# 使用平台管理的功能
jarvis-platform-manager --help

# 使用代码审查的功能
jarvis-code-review --help

# 使用自动化git commit的功能
jarvis-git-commit --help
# 或者 jgc

# 使用dev功能（开发中）
jarvis-dev --help

# 使用git squash的功能
jarvis-git-squash --help

# 使用多代理的功能
jarvis-multi-agent --help

# 使用agent的功能
jarvis-agent --help

# 使用工具的功能
jarvis-tool --help

# 使用代码库查询功能
jarvis-ask-codebase --help

# 使用git details的功能
jarvis-git-details --help

# 使用方法论的功能
jarvis-methodology --help
```

---

## ⚙️ 配置说明 <a id="configuration"></a>
### 环境变量配置
| 分类 | 变量名称 | 默认值 | 说明 |
|------|----------|--------|------|
| 核心配置 | `JARVIS_MAX_TOKEN_COUNT` | 102400000 | 上下文窗口的最大token数量 |
| 核心配置 | `JARVIS_MAX_INPUT_TOKEN_COUNT` | 32000 | 输入的最大token数量 |
| 核心配置 | `JARVIS_THREAD_COUNT` | 1 | 并行处理的线程数量 |
| 核心配置 | `JARVIS_AUTO_COMPLETE` | false | 是否启用自动补全功能 
| 核心配置 | `JARVIS_SHELL_NAME` | bash | 系统shell名称 |
| 核心配置 | `JARVIS_PLATFORM` | yuanbao | 默认AI平台 |
| 核心配置 | `JARVIS_MODEL` | deep_seek_v3 | 默认模型 |
| 核心配置 | `JARVIS_THINKING_PLATFORM` | JARVIS_PLATFORM | 思考任务使用的平台 |
| 核心配置 | `JARVIS_THINKING_MODEL` | JARVIS_MODEL | 思考任务使用的模型 |
| 核心配置 | `JARVIS_EXECUTE_TOOL_CONFIRM` | false | 执行工具前是否需要确认 |
| 核心配置 | `JARVIS_CONFIRM_BEFORE_APPLY_PATCH` | true | 应用补丁前是否需要确认 |
| 核心配置 | `JARVIS_MAX_TOOL_CALL_COUNT` | 20 | 最大连续工具调用次数 |


---
## 🛠️ 工具说明 <a id="tools"></a>
### 内置工具
| 工具名称 | 描述 |
|----------|------|
| ask_codebase | 智能代码库查询和分析，用于定位功能所在文件和理解单点实现，适合查询特定功能位置和实现原理 |
| ask_user | 交互式用户输入收集 |
| chdir | 更改当前工作目录 |
| code_plan | 理解需求并制定详细的代码修改计划，在修改前获取用户确认 |
| create_code_agent | 代码开发工具，当需要修改代码时使用，如果只是简单文件修改，使用文件操作或者脚本即可 |
| create_sub_agent | 创建子代理以处理特定任务，子代理将生成任务总结报告 |
| execute_script | 执行脚本并返回结果，支持任意解释器。 |
| file_analyzer | 分析文件内容并提取关键信息。支持的文件：文本文件、word文档、pdf文件、图片 |
| file_operation | 文件批量操作工具，可批量读写多个文件，支持文本、PDF、Word、Excel、PPT等格式，适用于需要同时处理多个文件的场景（读取配置文件、保存生成内容等） |
| find_methodology | 方法论查找工具，用于在执行过程中查看历史方法论辅助决策 |
| lsp_get_diagnostics | 获取代码诊断信息（错误、警告） |
| methodology | 经验管理工具，支持添加、更新和删除操作 |
| read_code | 代码阅读与分析工具，用于读取源代码文件并添加行号，针对代码文件优化，提供更好的格式化输出和行号显示，适用于代码分析、审查和理解代码实现的场景 |
| read_webpage | 读取网页内容，提取标题、文本和超链接 |
| search_web | 使用bing进行网络搜索 |
| virtual_tty | 控制虚拟终端执行各种操作，如启动终端、输入命令、获取输出等。 |


### 工具位置
- 内置工具：`src/jarvis/tools/`
- 用户工具：`~/.jarvis/tools/`
---
## 🛠️ 扩展开发 <a id="extensions"></a>
### 添加新工具
在 `~/.jarvis/tools/》 中创建新的 Python 文件：
```python
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput
class CustomTool:
    name = "工具名称"              # 调用时使用的工具名称
    description = "工具描述"       # 工具用途
    parameters = {                # 参数的 JSON Schema
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "参数描述"
            }
        },
        "required": ["param1"]
    }
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具功能
        
        参数：
            args: 传递给工具的参数
            
        返回：
            包含执行结果的字典：
            {
                "success": bool,
                "stdout": str,  # 成功时的输出
                "stderr": str,  # 可选的错误详情
            }
        """
        try:
            # 在此实现工具逻辑
            result = "工具执行结果"
            return {
                "success": True,
                "stdout": result,
                "stderr": ""
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e)
            }
```


### 添加新大模型平台
在 `~/.jarvis/platforms/》 中创建新的 Python 文件：
```python
from jarvis.jarvis_platform.base import BasePlatform
class CustomPlatform(BasePlatform):
    def __init__(self):
        # 初始化平台
        pass

    def __del__(self):
        # 销毁平台
        pass

    def chat(self, message: str) -> str:
        # 执行对话
        pass

    def upload_files(self, file_list: List[str]) -> bool:
        # 上传文件
        pass

    def delete_chat(self):
        # 删除对话
        pass

    def set_model_name(self, model_name: str):
        # 设置模型名称
        pass

    def set_system_message(self, message: str):
        # 设置系统消息
        pass

    def get_model_list(self) -> List[Tuple[str, str]]:
        # 获取模型列表
        pass

    def name(self) -> str:
        # 获取平台名称
        pass
```


## 🤝 贡献指南 <a id="contributing"></a>
1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '添加某个很棒的特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 许可证 <a id="license"></a>

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---
<div align="center">
由 Jarvis 团队用 ❤️ 制作
</div>