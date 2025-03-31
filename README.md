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
pip install jarvis-ai-assistant # 安装jarvis-ai-assistant
playwright install # 安装playwright
```

### 最小化配置
```bash
JARVIS_PLATFORM=openai # 设置AI平台
JARVIS_MODEL=deepseek-chat # 设置AI模型
OPENAI_API_KEY=your_openai_api_key # 设置OpenAI API密钥
OPENAI_API_BASE=https://api.deepseek.com/v1 # 设置OpenAI API基础URL
```

以上配置编写到`~/.jarvis/env`文件中。

### 基本使用
```bash
# 使用通用代理
jarvis
# 使用代码代理
jarvis-code-agent
# 或者 jca
# 使用codebase的功能
jarvis-codebase --help
# 使用rag的功能
jarvis-rag --help
# 使用智能shell的功能
jarvis-smart-shell --help
# 或者 jss
# 使用平台管理的功能
jarvis-platform-manager --help
# 使用自动化git commit的功能
jarvis-git-commit --help
# 或者 jgc
# 使用代码审查的功能
jarvis-code-review --help
# 使用dev功能（开发中）
jarvis-dev --help
# 使用git squash的功能
jarvis-git-squash --help
# 使用代码库查询功能
jarvis-ask-codebase --help
```

---

## ⚙️ 配置说明 <a id="configuration"></a>
### 环境变量配置
| 分类 | 变量名称 | 默认值 | 说明 |
|------|----------|--------|------|
| 核心配置 | `JARVIS_MAX_TOKEN_COUNT` | 131072 | 上下文窗口的最大token数量 |
| 核心配置 | `JARVIS_THREAD_COUNT` | 1 | 并行处理的线程数量 |
| 核心配置 | `JARVIS_AUTO_COMPLETE` | false | 是否启用自动补全功能 |
| 核心配置 | `JARVIS_EXECUTE_TOOL_CONFIRM` | false | 执行工具前是否需要确认 |
| 核心配置 | `JARVIS_CONFIRM_BEFORE_APPLY_PATCH` | true | 应用补丁前是否需要确认 |
| 模型配置 | `JARVIS_PLATFORM` | yuanbao | 默认AI平台 |
| 模型配置 | `JARVIS_MODEL` | deep_seek_v3 | 默认模型 |
| 模型配置 | `JARVIS_THINKING_PLATFORM` | JARVIS_PLATFORM | 思考任务使用的平台 |
| 模型配置 | `JARVIS_THINKING_MODEL` | JARVIS_MODEL | 思考任务使用的模型 |
| 方法论配置 | `JARVIS_USE_METHODOLOGY` | true | 是否启用方法论系统 |
| 方法论配置 | `JARVIS_RECORD_METHODOLOGY` | true | 是否记录方法论 |
| 方法论配置 | `JARVIS_NEED_SUMMARY` | true | 是否自动生成摘要 |
| 文本处理 | `JARVIS_MIN_PARAGRAPH_LENGTH` | 50 | 文本处理的最小段落长度 |
| 文本处理 | `JARVIS_MAX_PARAGRAPH_LENGTH` | 12800 | 文本处理的最大段落长度 |
---
## 🛠️ 工具说明 <a id="tools"></a>
### 内置工具
| 工具名称 | 描述 |
|----------|------|
| read_code | 支持行号和范围的代码文件读取 |
| execute_shell | 执行系统命令并捕获输出 |
| execute_script | 执行脚本并返回结果，支持Shell命令、Shell脚本和Python脚本 |
| ask_codebase | 智能代码库查询和分析，用于定位功能所在文件和理解单点实现，适合查询特定功能位置和实现原理 |
| ask_user | 交互式用户输入收集 |
| file_operation | 基础文件操作（读取/写入/存在性检查） |
| git_commiter | 自动化git提交处理 |
| code_review | 多维度的自动代码审查 |
| search_web | 使用bing进行网络搜索 |
| read_webpage | 读取网页内容 |
| chdir | 更改工作目录 |
| create_code_agent | 创建新的代码代理 |
| create_sub_agent | 创建子代理 |
| lsp_validate_edit | 验证代码编辑 |
| rag | 文档检索和问答 |
| select_code_files | 选择代码文件 |
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

    def reset(self):
        # 重置平台
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