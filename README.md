# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
*您的智能开发和系统交互助手*
[快速开始](#-快速开始) •
[核心功能](#-核心功能) •
[配置说明](#-配置说明) •
[工具说明](#-工具说明) •
[扩展开发](#-扩展开发) •
[贡献指南](#-贡献指南)
---
## 🚀 快速开始
### 安装
```bash
pip install jarvis-ai-assistant
```
### 最小化配置
```bash
JARVIS_PLATFORM=openai
JARVIS_MODEL=deepseek-chat
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_BASE=https://api.deepseek.com/v1
```
### 基本使用
```bash
# 使用主代理
jarvis
# 直接使用代码代理
jarvis-code-agent
# 查看帮助信息
jarvis --help
```
---
## 🎯 核心功能
### 代码智能
- 基于需求的智能文件选择和分析
- 语义化代码库搜索和查询
- 具有上下文感知的大文件高效处理
- 精确的基于补丁的代码修改
- 自动化的 git 提交管理
### 多模型架构
- 支持多个 AI 平台（Kimi/OpenAI/AI8/OYI/Ollama）
- 针对不同任务的平台特定优化
- 专门用于代码生成、思考和通用任务的模型
- 流式响应支持以提供更好的交互
- 自动的模型回退和重试机制
### RAG 能力
- 文档索引和语义搜索
- 大型文档的智能上下文管理
- 自动文件变更检测
- 高效的缓存机制
- 多格式文档支持
### 开发工具
- 交互式命令行生成
- 多维度的代码审查
- 基于代码库的问题解决
- 具有安全检查的文件操作
- 进度跟踪和错误处理
### 用户体验
- 支持彩色输出的精美控制台
- 交互式多行输入
- 长时间操作的进度指示
- 清晰的错误消息和处理
- 上下文感知的响应格式化
---
## ⚙️ 配置说明
### 环境变量配置
| 分类 | 变量名称 | 默认值 | 说明 |
|------|----------|--------|------|
| 核心配置 | `JARVIS_MAX_TOKEN_COUNT` | 131072 | 上下文窗口的最大token数量 |
| 核心配置 | `JARVIS_THREAD_COUNT` | 1 | 并行处理的线程数量 |
| 核心配置 | `JARVIS_AUTO_COMPLETE` | false | 是否启用自动补全功能 |
| 核心配置 | `JARVIS_EXECUTE_TOOL_CONFIRM` | false | 执行工具前是否需要确认 |
| 核心配置 | `JARVIS_CONFIRM_BEFORE_APPLY_PATCH` | true | 应用补丁前是否需要确认 |
| 模型配置 | `JARVIS_DONT_USE_LOCAL_MODEL` | false | 是否禁用本地模型 |
| 模型配置 | `JARVIS_PLATFORM` | kimi | 默认AI平台 |
| 模型配置 | `JARVIS_MODEL` | kimi | 默认模型 |
| 模型配置 | `JARVIS_CODEGEN_PLATFORM` | JARVIS_PLATFORM | 代码生成任务使用的平台 |
| 模型配置 | `JARVIS_CODEGEN_MODEL` | JARVIS_MODEL | 代码生成任务使用的模型 |
| 模型配置 | `JARVIS_THINKING_PLATFORM` | JARVIS_PLATFORM | 思考任务使用的平台 |
| 模型配置 | `JARVIS_THINKING_MODEL` | JARVIS_MODEL | 思考任务使用的模型 |
| 模型配置 | `JARVIS_CHEAP_PLATFORM` | JARVIS_PLATFORM | 低成本任务使用的平台 |
| 模型配置 | `JARVIS_CHEAP_MODEL` | JARVIS_MODEL | 低成本任务使用的模型 |
| 方法论配置 | `JARVIS_USE_METHODOLOGY` | true | 是否启用方法论系统 |
| 方法论配置 | `JARVIS_RECORD_METHODOLOGY` | true | 是否记录方法论 |
| 方法论配置 | `JARVIS_NEED_SUMMARY` | true | 是否自动生成摘要 |
| 文本处理 | `JARVIS_MIN_PARAGRAPH_LENGTH` | 50 | 文本处理的最小段落长度 |
| 文本处理 | `JARVIS_MAX_PARAGRAPH_LENGTH` | 12800 | 文本处理的最大段落长度 |
### 配置文件
在`~/.jarvis/env`文件中配置环境变量：
```bash
# 示例配置
JARVIS_MAX_TOKEN_COUNT=262144
JARVIS_AUTO_COMPLETE=true
JARVIS_CODEGEN_MODEL=gpt-4
JARVIS_THINKING_PLATFORM=openai
JARVIS_THREAD_COUNT=4
```
---
## 🛠️ 工具说明
### 内置工具
| 工具名称 | 描述 |
|----------|------|
| read_code | 支持行号和范围的代码文件读取 |
| execute_shell | 执行系统命令并捕获输出 |
| execute_shell_script | 执行shell脚本文件 |
| ask_codebase | 智能代码库查询和分析 |
| ask_user | 交互式用户输入收集 |
| file_operation | 基础文件操作（读取/存在性检查） |
| git_commiter | 自动化git提交处理 |
| code_review | 多维度的自动代码审查 |
| search_web | 开发相关的网络搜索 |
| read_webpage | 读取网页内容 |
| chdir | 安全地更改工作目录 |
| create_code_agent | 创建新的代码代理 |
| create_sub_agent | 创建子代理 |
| lsp_find_definition | 查找符号定义 |
| lsp_find_references | 查找符号引用 |
| lsp_get_diagnostics | 获取代码诊断信息 |
| lsp_get_document_symbols | 获取文档符号 |
| lsp_prepare_rename | 准备符号重命名 |
| lsp_validate_edit | 验证代码编辑 |
| rag | 文档检索和问答 |
| select_code_files | 智能选择代码文件 |
### 工具位置
- 内置工具：`src/jarvis/tools/`
- 用户工具：`~/.jarvis/tools/`
---
## 🛠️ 扩展开发
### 添加新工具
在 `~/.jarvis/tools/` 或 `src/jarvis/tools/` 中创建新的 Python 文件：
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
### 开发指南
1. **工具开发**
   - 使用描述性名称和文档
   - 定义清晰的参数模式
   - 优雅处理错误
   - 返回标准化结果
   - 保持工具功能集中和简单
2. **最佳实践**
   - 使用 PrettyOutput 进行控制台输出
   - 编写代码文档
   - 添加类型提示
   - 充分测试
   - 处理边界情况
---
## 🤝 贡献指南
1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '添加某个很棒的特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request
---
## 📄 许可证
本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。
---
<div align="center">
由 Jarvis 团队用 ❤️ 制作
</div>
