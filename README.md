<div align="center">

# 🤖 Jarvis AI 助手

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[功能特性](#功能特性) •
[使用方法](#使用方法) •
[配置说明](#配置说明) •
[扩展 Jarvis](#-扩展-jarvis) •
[贡献指南](#-贡献指南) •
[许可证](#-许可证)

</div>

---

## ✨ 功能特性

### 🧠 智能代理
- 通过经验积累实现自我提升
- 从成功的问题解决中自动生成方法论
- 从每次交互中进行迭代学习
- 上下文感知的问题解决能力

### 🛠️ 可扩展架构
- 动态工具加载和集成
- 简单接口支持自定义模型
- AI 驱动的工具生成
- 工具和模型的热重载支持

### 💡 智能特性
- 自动化方法论管理
- 特定问题的解决方案模式
- 持续能力增强
- 从过往交互中学习

### 🎨 用户体验
- 精美的控制台输出
- 交互模式
- 多行输入支持
- 进度指示器
- 彩色输出

## 🚀 安装

```bash
pip install jarvis-ai-assistant
```

## 🔧 配置说明

Jarvis 支持通过环境变量进行配置，可以在 `~/.jarvis/env` 文件中设置：

| 环境变量 | 描述 | 默认值 | 是否必需 |
|---------|------|--------|------|
| JARVIS_PLATFORM | 使用的 AI 平台 | kimi | 是 |
| JARVIS_MODEL | 使用的模型名称 | kimi | 否 |
| JARVIS_CODEGEN_PLATFORM | 代码生成使用的平台 | 同 JARVIS_PLATFORM | 否 |
| JARVIS_CODEGEN_MODEL | 代码生成使用的模型 | 同 JARVIS_MODEL | 否 |
| JARVIS_THINKING_PLATFORM | 思考任务使用的平台 | 同 JARVIS_PLATFORM | 否 |
| JARVIS_THINKING_MODEL | 思考任务使用的模型 | 同 JARVIS_MODEL | 否 |
| JARVIS_CHEAP_PLATFORM | 低成本操作使用的平台 | 同 JARVIS_PLATFORM | 否 |
| JARVIS_CHEAP_MODEL | 低成本操作使用的模型 | 同 JARVIS_MODEL | 否 |
| JARVIS_THREAD_COUNT | 线程数量 | 1 | 否 |
| JARVIS_MAX_CONTEXT_LENGTH | 最大上下文长度 | 131072 | 否 |
| JARVIS_MIN_PARAGRAPH_LENGTH | 最小段落长度 | 50 | 否 |
| JARVIS_MAX_PARAGRAPH_LENGTH | 最大段落长度 | 1000 | 否 |
| JARVIS_CONTEXT_WINDOW | 上下文窗口大小 | 5 | 否 |
| JARVIS_AUTO_COMPLETE | 启用自动完成 | false | 否 |
| JARVIS_USE_METHODOLOGY | 启用方法论 | true | 否 |
| JARVIS_RECORD_METHODOLOGY | 记录方法论 | true | 否 |
| JARVIS_NEED_SUMMARY | 生成摘要 | true | 否 |
| JARVIS_DONT_USE_LOCAL_MODEL | 避免使用本地模型 | false | 否 |
| OPENAI_API_KEY | OpenAI 平台的 API 密钥 | - | OpenAI 必需 |
| OPENAI_API_BASE | OpenAI API 的基础 URL | https://api.openai.com | 否 |
| OPENAI_MODEL_NAME | OpenAI 的模型名称 | gpt-4o | 否 |
| AI8_API_KEY | AI8 平台的 API 密钥 | - | AI8 必需 |
| KIMI_API_KEY | Kimi 平台的 API 密钥 | - | Kimi 必需 |
| OYI_API_KEY | OYI 平台的 API 密钥 | - | OYI 必需 |
| OLLAMA_API_BASE | Ollama API 的基础 URL | http://localhost:11434 | 否 |

## 最小化配置（openai兼容接口为例）

```bash
JARVIS_PLATFORM=openai
JARVIS_MODEL=deepseek-chat
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_BASE=https://api.deepseek.com/v1
```

## 🎯 使用方法

### 代码修改
```bash
# 使用主代理
jarvis

# 直接使用代码代理
jarvis-code-agent
```

### 代码库查询
```bash
# 询问代码库相关问题
jarvis-codebase ask "你的问题"
```

### 文档分析 (RAG)
```bash
# 构建文档索引
jarvis-rag --dir /path/to/documents --build

# 询问文档相关问题
jarvis-rag --query "你的问题"
```

### 智能命令行
```bash
# 使用完整名称
jarvis-smart-shell "描述你想要执行的操作"

# 使用简写
jss "描述你想要执行的操作"
```

### 开发工具
```bash
# 管理 git 提交
jarvis-git-commit

# 管理 AI 平台
jarvis-platform-manager
```

每个命令都支持 `--help` 参数来获取详细使用说明：
```bash
jarvis --help
jarvis-code-agent --help
jarvis-codebase --help
jarvis-rag --help
jarvis-smart-shell --help
jarvis-platform-manager --help
jarvis-git-commit --help
```

## 🛠️ 工具

### 内置工具

| 工具 | 描述 |
|------|-------------|
| read_code | 支持行号和范围的代码文件读取 |
| execute_shell | 执行系统命令并捕获输出 |
| search | 开发相关的网络搜索 |
| ask_user | 交互式用户输入收集 |
| ask_codebase | 智能代码库查询和分析 |
| code_review | 多维度的自动代码审查 |
| file_operation | 基础文件操作（读取/存在性检查） |
| git_commiter | 自动化 git 提交处理 |

### 工具位置
- 内置工具：`src/jarvis/tools/`
- 用户工具：`~/.jarvis/tools/`

### 核心功能

#### 1. 代码智能
- 基于需求的智能文件选择和分析
- 语义化代码库搜索和查询
- 具有上下文感知的大文件高效处理
- 精确的基于补丁的代码修改
- 自动化的 git 提交管理

#### 2. 多模型架构
- 支持多个 AI 平台（Kimi/OpenAI/AI8/OYI/Ollama）
- 针对不同任务的平台特定优化
- 专门用于代码生成、思考和通用任务的模型
- 流式响应支持以提供更好的交互
- 自动的模型回退和重试机制

#### 3. RAG 能力
- 文档索引和语义搜索
- 大型文档的智能上下文管理
- 自动文件变更检测
- 高效的缓存机制
- 多格式文档支持

#### 4. 开发工具
- 交互式命令行生成
- 多维度的代码审查
- 基于代码库的问题解决
- 具有安全检查的文件操作
- 进度跟踪和错误处理

#### 5. 用户体验
- 支持彩色输出的精美控制台
- 交互式多行输入
- 长时间操作的进度指示
- 清晰的错误消息和处理
- 上下文感知的响应格式化

## 🎯 扩展 Jarvis

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

### 添加新模型

在 `~/.jarvis/models/` 中创建新的 Python 文件：

```python
from typing import Dict, List
from jarvis.models.base import BasePlatform
from jarvis.utils import PrettyOutput, OutputType

class CustomPlatform(BasePlatform):
    """自定义模型实现"""
    
    platform_name = "custom"  # 平台标识符
    
    def __init__(self):
        """初始化模型"""
        # 添加初始化代码
        super().__init__()
        self.messages = []
        self.system_message = ""

    def set_model_name(self, model_name: str):
        """设置模型名称"""
        self.model_name = model_name

    def chat(self, message: str) -> str:
        """与模型对话
        
        参数：
            message: 用户输入消息
            
        返回：
            str: 模型响应
        """
        try:
            # 实现聊天逻辑
            if not self.suppress_output:
                PrettyOutput.print("发送请求...", OutputType.PROGRESS)
            
            # 将消息添加到历史记录
            self.messages.append({"role": "user", "content": message})
            
            # 从模型获取响应
            response = "模型响应"
            
            # 将响应添加到历史记录
            self.messages.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"聊天失败：{str(e)}", OutputType.ERROR)
            raise Exception(f"聊天失败：{str(e)}")
    
    def upload_files(self, file_list: List[str]) -> List[Dict]:
        """上传文件"""
        # 实现文件上传逻辑
        return []    
        
    def reset(self):
        """重置模型状态"""
        self.messages = []
        if self.system_message:
            self.messages.append({"role": "system", "content": self.system_message})
            
    def name(self) -> str:
        """返回模型名称"""
        return self.model_name
            
    def delete_chat(self) -> bool:
        """删除当前聊天会话"""
        self.reset()
        return True  

    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message

    def set_suppress_output(self, suppress: bool):
        """设置是否抑制输出"""
        self.suppress_output = suppress
```

### 开发指南

1. **工具开发**
   - 使用描述性名称和文档
   - 定义清晰的参数模式
   - 优雅处理错误
   - 返回标准化结果
   - 保持工具功能集中和简单

2. **模型开发**
   - 实现所有必需方法
   - 处理流式响应
   - 正确管理聊天历史
   - 使用适当的错误处理
   - 遵循现有模型模式

3. **最佳实践**
   - 使用 PrettyOutput 进行控制台输出
   - 编写代码文档
   - 添加类型提示
   - 充分测试
   - 处理边界情况

## 🤝 贡献指南

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '添加某个很棒的特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

<div align="center">

由 Jarvis 团队用 ❤️ 制作

</div> 