# 🌐 Jarvis Platform Manager - AI平台管理中心

<div align="center">
  <img src="../images/platform-manager.png" alt="Platform Manager" width="250" style="margin-bottom: 20px"/>
  
  *无缝连接多平台AI能力*
  
  ![Version](https://img.shields.io/badge/version-0.1.x-blue)
  ![Status](https://img.shields.io/badge/status-stable-green)
</div>

## ✨ 魔法简介
Jarvis Platform Manager 是一个强大的AI平台管理工具，支持多平台、多模型的统一访问和管理。它让您可以轻松切换不同的AI提供商，查看可用模型，进行交互式聊天，甚至启动兼容OpenAI接口的本地服务。

## 🚀 核心功能
- **平台信息查询** - 获取所有支持平台与模型列表
- **交互式聊天** - 与指定平台和模型进行对话
- **兼容性API服务** - 提供OpenAI兼容的本地API
- **平台配置管理** - 统一管理多平台的配置和凭证
- **日志与会话记录** - 自动记录交互会话，便于回溯

## 💫 使用方法
```bash
jarvis-platform-manager <command> [options]
```

### 📋 可用命令

#### 📊 信息查询
```bash
jarvis-platform-manager info
```
显示所有支持的平台和每个平台上可用的模型列表。

#### 💬 交互式聊天
```bash
jarvis-platform-manager chat [--platform <平台名称>] [--model <模型名称>]
```
启动交互式聊天环境，与指定平台和模型进行对话。

#### 🔌 API服务
```bash
jarvis-platform-manager service [--host <主机地址>] [--port <端口号>] [--platform <默认平台>] [--model <默认模型>]
```
启动兼容OpenAI接口的本地API服务，可用于任何支持OpenAI API的应用。

## 🌟 功能亮点

### 🔄 平台无缝切换
- 在不同AI提供商间无缝切换，对比性能与结果
- 自动处理不同平台间的请求格式差异
- 支持平台特定功能的访问与调用

### 🛠️ OpenAI兼容服务
- 提供完全兼容OpenAI接口规范的本地HTTP服务
- 支持所有主流的聊天完成和嵌入API端点
- 允许第三方应用和工具直接连接使用

### 📝 会话日志记录
- 自动保存所有交互历史和模型响应
- 结构化存储便于分析和回溯
- 支持会话ID管理，连续多轮对话

## 📊 支持的平台
| 平台 | 描述 | 支持的功能 |
|------|------|-----------|
| OpenAI | OpenAI官方API | 聊天完成、嵌入 |
| Azure | Azure OpenAI服务 | 聊天完成、嵌入 |
| Anthropic | Claude系列模型API | 聊天完成 |
| DeepSeek | DeepSeek模型API | 聊天完成、代码生成 |
| Kimi | Moonshot AI开发的Kimi模型 | 聊天完成 |
| Ollama | 本地运行的开源模型 | 聊天完成、嵌入 |
| Local | 本地运行的私有模型服务 | 聊天完成 |

## 🔍 使用示例

### 查询支持的平台与模型
```bash
jarvis-platform-manager info
```

### 与特定平台和模型聊天
```bash
jarvis-platform-manager chat --platform openai --model gpt-4
```

### 启动API服务（默认使用OpenAI）
```bash
jarvis-platform-manager service --port 8000 --platform openai --model gpt-4
```

### 客户端调用本地API服务
```python
import openai
openai.api_key = "any-key"  # 本地服务不验证密钥
openai.api_base = "http://localhost:8000/v1"

response = openai.chat.completions.create(
    model="any-model",  # 实际使用服务启动时指定的默认模型
    messages=[{"role": "user", "content": "你好，Jarvis!"}]
)
```

## 🔧 环境变量配置
可以通过以下环境变量配置平台行为（添加到`~/.jarvis/env`）：
```bash
# OpenAI配置
OPENAI_API_KEY=your_openai_key
OPENAI_API_BASE=https://api.openai.com/v1

# Azure配置
AZURE_API_KEY=your_azure_key
AZURE_API_BASE=your_azure_endpoint
AZURE_API_VERSION=2023-05-15
```

## 💡 专家提示
- 使用`service`命令启动本地API服务，让不支持多平台的应用也能访问其他模型
- 在平台受限区域，可以将不同区域的同一平台配置为不同的平台名称
- 利用日志记录功能，分析不同模型对同一问题的回答差异
- 实验时使用`chat`命令比较不同模型的表现，选出最适合的模型

---

<div align="center">
  <p><i>Jarvis Platform Manager - 解锁全球AI能力的统一入口</i></p>
</div> 