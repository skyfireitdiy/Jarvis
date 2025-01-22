<div align="center">

# 🤖 Jarvis AI 助手

<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[功能特点](#-功能特点) •
[使用方法](#-使用方法) •
[配置说明](#-配置说明) •
[扩展功能](#-扩展功能) •
[参与贡献](#-参与贡献) •
[开源协议](#-开源协议)

[English](README.md) | 简体中文

</div>

---

## ✨ 功能特点

### 🧠 智能代理
- 通过经验积累实现自我提升
- 从成功问题解决中自动生成方法论
- 在每次交互中迭代学习
- 上下文感知的问题解决能力

### 🛠️ 可扩展架构
- 动态工具加载和集成
- 简单接口支持自定义模型
- AI驱动的工具生成
- 工具和模型的热重载支持

### 💡 智能特性
- 自动化方法论管理
- 特定问题的解决模式
- 持续能力增强
- 从过往交互中学习

### 🎨 用户体验
- 精美的控制台输出
- 交互式模式
- 多行输入支持
- 进度指示器
- 彩色输出

## 🚀 安装

```bash
pip install jarvis-ai-assistant
```

## 🔧 配置说明

Jarvis 通过环境变量进行配置，可以在 `~/.jarvis_env` 文件中设置：

| 环境变量 | 说明 | 默认值 | 是否必需 |
|---------|------|--------|---------|
| JARVIS_PLATFORM | AI平台选择，支持kimi/openai/ai8等 | kimi | 是 |
| JARVIS_MODEL | 使用的模型名称 | - | 否 |
| JARVIS_CODEGEN_PLATFORM | 代码生成使用的AI平台 | 同JARVIS_PLATFORM | 否 |
| JARVIS_CODEGEN_MODEL | 代码生成使用的模型名称 | 同JARVIS_MODEL | 否 |
| OPENAI_API_KEY | OpenAI平台的API密钥 | - | 使用OpenAI时必需 |
| OPENAI_API_BASE | OpenAI API的基础URL | https://api.deepseek.com | 否 |
| OPENAI_MODEL_NAME | OpenAI使用的模型名称 | deepseek-chat | 否 |
| AI8_API_KEY | AI8平台的API密钥 | - | 使用AI8时必需 |
| AI8_MODEL | AI8平台使用的模型名称 | deepseek-chat | 否 |
| KIMI_API_KEY | Kimi平台的API密钥 | - | 使用Kimi时必需 |
| OYI_API_KEY | OYI平台的API密钥 | - | 使用OYI时必需 |
| OYI_MODEL | OYI平台使用的模型名称 | deepseek-chat | 否 |

## 🎯 使用方法

### 基本使用
```bash
jarvis
```

### 指定模型
```bash
jarvis -p kimi  # 使用Kimi平台
jarvis -p openai  # 使用OpenAI平台
```

### 处理文件
```bash
jarvis -f file1.py file2.py  # 处理指定文件
```

### 保持对话历史
```bash
jarvis --keep-history  # 不删除对话会话
```

### 代码修改
```bash
jarvis coder --feature "添加新功能"  # 修改代码以添加新功能
```

### 代码库搜索
```bash
jarvis codebase --search "数据库连接"  # 搜索代码库
```

### 代码库问答
```bash
jarvis codebase --ask "如何使用数据库？"  # 询问代码库相关问题
```

## 🛠️ 工具

### 内置工具

| 工具名称 | 说明 |
|---------|------|
| execute_shell | 执行系统命令并捕获输出 |
| file_operation | 文件操作（读/写/追加/删除） |
| generate_tool | AI驱动的工具生成和集成 |
| methodology | 经验积累和方法论管理 |
| create_sub_agent | 创建专门的子代理处理特定任务 |
| coder | 自动代码修改和生成工具 |
| codebase | 代码库管理和搜索工具 |

### 工具位置
- 内置工具：`src/jarvis/tools/`
- 用户工具：`~/.jarvis_tools/`

### 主要特性

#### 1. 自我扩展能力
- 通过自然语言描述生成工具
- 自动代码生成和集成
- 通过子代理实现动态能力扩展
- 自动代码修改并集成版本控制
- 代码库索引和语义搜索

#### 2. 方法论学习
- 从交互中自动积累经验
- 模式识别和方法论提取
- 通过使用持续改进
- 跟踪代码修改历史
- 代码库分析和文档生成

#### 3. 自适应问题解决
- 上下文感知的子代理创建
- 动态工具组合
- 从执行反馈中学习
- 基于代码库的问题解决
- 复杂任务的多模型协作

#### 4. 代码智能
- 自动代码库索引
- 语义代码搜索
- 集成Git的代码修改
- 代码分析和文档
- 多模型代码生成

## 🎯 扩展功能

### 添加新工具

在 `~/.jarvis_tools/` 或 `src/jarvis/tools/` 中创建新的Python文件：

```python
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput

class CustomTool:
    name = "tool_name"              # 工具调用名称
    description = "Tool description" # 工具用途说明
    parameters = {                  # JSON Schema参数定义
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "参数说明"
            }
        },
        "required": ["param1"]
    }

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具功能
        
        Args:
            args: 传递给工具的参数
            
        Returns:
            Dict包含执行结果:
            {
                "success": bool,
                "stdout": str,  # 成功时的输出
                "stderr": str,  # 可选的错误详情
                "error": str    # 失败时的错误信息
            }
        """
        try:
            # 实现工具逻辑
            result = "工具执行结果"
            return {
                "success": True,
                "stdout": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
```

### 添加新模型

在 `~/.jarvis_models/` 中创建新的Python文件：

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
        """与模型进行对话
        
        Args:
            message: 用户输入消息
            
        Returns:
            str: 模型响应
        """
        try:
            # 实现对话逻辑
            PrettyOutput.print("发送请求...", OutputType.PROGRESS)
            
            # 添加消息到历史
            self.messages.append({"role": "user", "content": message})
            
            # 从模型获取响应
            response = "模型响应"
            
            # 添加响应到历史
            self.messages.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            PrettyOutput.print(f"对话失败: {str(e)}", OutputType.ERROR)
            raise Exception(f"对话失败: {str(e)}")
    
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
        """删除当前对话会话"""
        self.reset()
        return True  

    def set_system_message(self, message: str):
        """设置系统消息"""
        self.system_message = message

    def set_suppress_output(self, suppress: bool):
        """设置是否屏蔽输出"""
        self.suppress_output = suppress


```

### 开发指南

1. **工具开发**
   - 使用描述性的名称和文档
   - 定义清晰的参数模式
   - 优雅地处理错误
   - 返回标准化的结果
   - 保持工具功能专注和简单

2. **模型开发**
   - 实现所有必需的方法
   - 处理流式响应
   - 正确管理对话历史
   - 使用适当的错误处理
   - 遵循现有的模型模式

3. **最佳实践**
   - 使用PrettyOutput进行控制台输出
   - 编写文档
   - 添加类型提示
   - 充分测试
   - 处理边缘情况

## 🤝 参与贡献

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '添加一些功能'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交Pull Request

## 📄 开源协议

本项目采用 MIT 协议开源 - 查看 [LICENSE](LICENSE) 文件了解更多详情。

---

<div align="center">

由 Jarvis 团队用 ❤️ 打造

</div> 