# 🧠 Jarvis - AI 智能助手

<div align="center">
  <img src="../images/jarvis.png" alt="Jarvis AI" width="250" style="margin-bottom: 20px"/>
  
  *新一代智能交互体验*
  
  ![Version](https://img.shields.io/badge/version-0.1.x-blue)
  ![Architecture](https://img.shields.io/badge/架构-第三代-green)
</div>

## 🌟 魔法简介
Jarvis 是一个智能 AI 助手，采用第三代架构设计，支持多种任务执行和工具调用。它遵循严格的执行协议，确保任务执行的可靠性和可追溯性，为您提供强大而可控的 AI 交互体验。

## ✨ 核心特性
- **智能任务执行管理** - 精确规划和自主执行复杂任务流程
- **多工具协调调用** - 灵活组合多种工具完成复杂任务
- **长期对话历史管理** - 智能记忆对话内容，保持上下文连贯
- **先进方法论记录** - 自动记录有价值的问题解决方法
- **结构化任务总结** - 生成清晰的任务执行报告和结果摘要

## 💫 适用场景
- **复杂任务分解与执行** - 将大型任务拆分为可管理的子任务
- **多工具协同工作流** - 创建和执行涉及多个工具的工作流
- **任务执行过程记录** - 追踪和记录所有执行步骤
- **问题解决方法论生成** - 创建和积累解决特定问题的方法
- **任务结果的全面总结** - 概括和整理任务执行的关键结果

## 🚀 使用方法
```bash
jarvis [options]
```

### 📋 常用选项
- `-p, --platform <平台>` - 指定使用的AI平台（如 openai、azure）
- `-m, --model <模型>` - 指定使用的AI模型（如 gpt-4、claude-3）
- `--no-methodology` - 禁用方法论记录功能
- `--no-summary` - 禁用任务总结功能
- `--execute-confirm` - 执行工具前需要确认

## 🔄 执行流程
<div align="center">
  <img src="../images/jarvis-workflow.png" alt="Jarvis Workflow" width="600" style="margin: 20px 0"/>
</div>

1. **初始化环境** - 加载配置和准备执行环境
2. **加载预定义任务** - 读取预定义任务（如果存在）
3. **进入交互模式** - 启动用户交互界面
4. **接收用户输入** - 获取并分析用户指令
5. **执行任务流程** - 规划并执行必要的操作步骤
6. **生成总结报告** - 创建执行过程和结果摘要

## 🛡️ 技术特点
- **顺序执行协议** - 严格保证一次只执行一个工具，确保操作安全
- **验证检查点** - 每个步骤都进行结果验证，确保执行质量
- **方法论记录** - 自动记录有价值的解决方案，持续积累知识
- **对话管理** - 支持长对话的自动总结和上下文管理，提高交互效率

## 💎 使用示例

### 基础使用
启动 Jarvis 并进入交互模式：
```bash
jarvis
```

### 指定平台和模型
使用特定的 AI 平台和模型：
```bash
jarvis --platform openai --model gpt-4
```

### 使用预定义任务
预先定义任务并让 Jarvis 执行：
```bash
# 步骤1: 在 ~/.jarvis/pre-command 中定义任务
echo "分析当前目录下所有Python文件并生成代码质量报告" > ~/.jarvis/pre-command

# 步骤2: 执行预定义任务
jarvis
```

## 🔮 高级用法

### 环境变量配置
通过设置环境变量或在 `~/.jarvis/env` 文件中配置 Jarvis：
```bash
# 设置默认平台和模型
JARVIS_PLATFORM=openai
JARVIS_MODEL=gpt-4

# 控制方法论和总结功能
JARVIS_USE_METHODOLOGY=true
JARVIS_NEED_SUMMARY=true

# 配置上下文窗口大小
JARVIS_MAX_TOKEN_COUNT=131072
```

### 与其他工具集成
Jarvis 可以与生态系统中的其他工具无缝协作：
```bash
# 先使用 Jarvis 生成方案
jarvis "设计一个用户认证系统"

# 再使用 Jarvis Code Agent 实现代码
jarvis-code-agent "根据之前的设计实现用户认证系统"
```

## 💡 专家提示
- 提供清晰、详细的指令以获得最佳结果
- 使用方法论记录功能积累解决特定问题的工作流
- 对于复杂任务，先分解为小步骤再逐步执行
- 结合环境变量配置个性化您的 Jarvis 体验
- 定期查看自动生成的总结，了解任务执行模式

---

<div align="center">
  <p><i>Jarvis - 您的智能决策与执行伙伴</i></p>
</div>
