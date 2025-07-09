# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[快速开始](#quick-start) • [核心功能](#core-features) • [配置说明](#configuration) • [工具说明](#tools) • [扩展开发](#extensions) • [贡献指南](#contributing) • [许可证](#license) • [Wiki文档](https://deepwiki.com/skyfireitdiy/Jarvis)
</div>

---

## 🚀 快速开始 <a id="quick-start"></a>

### 系统要求
- 目前只能在Linux系统下使用（很多工具依赖Linux系统）
- Windows没有测试过，但Windows 10以上的用户可以在WSL上使用此工具

### 安装
```bash
# 从源码安装（推荐）
git clone https://github.com/skyfireitdiy/Jarvis
cd Jarvis
pip3 install -e .

# 或者从PyPI安装（可能更新不及时）
pip3 install jarvis-ai-assistant
```

### 基本使用
| 命令 | 快捷方式 | 功能描述 |
|------|----------|----------|
| `jarvis` | - | 使用通用代理 |
| `jarvis-code-agent` | `jca` | 使用代码代理 |
| `jarvis-smart-shell` | `jss` | 使用智能shell功能 |
| `jarvis-platform-manager` | `jpm` | 使用平台管理功能 |
| `jarvis-code-review` | - | 使用代码审查功能 |
| `jarvis-git-commit` | `jgc` | 使用自动化git commit功能 |
| `jarvis-git-squash` | - | 使用git squash功能 |
| `jarvis-multi-agent` | - | 使用多代理功能 |
| `jarvis-agent` | - | 使用agent功能 |
| `jarvis-tool` | - | 使用工具功能 |
| `jarvis-git-details` | - | 使用git details功能 |
| `jarvis-methodology` | - | 使用方法论功能 |

### Jarvis功能 (jarvis)

`jarvis` 是Jarvis的通用代理工具，提供开箱即用的AI助手功能。

#### 1. 核心功能
- 任务分析与规划
- 代码分析与修改
- 系统交互与操作
- 方法论应用与优化
- 多代理协作

#### 2. 使用方式
```bash
# 基本用法
jarvis

# 带参数使用
jarvis -p <平台> -m <模型> -t "初始任务"
```

#### 3. 命令行参数
| 参数 | 描述 |
|------|------|
| `-p/--platform` | 指定AI平台 (yuanbao/kimi/tongyi/openai) |
| `-m/--model` | 指定模型名称 |
| `-t/--task` | 指定初始任务 |

#### 4. 工作流程
1. 初始化环境
2. 加载默认配置
3. 创建代理实例
4. 执行初始任务（如果指定）
5. 进入交互式模式（如果没有初始任务）
6. 根据用户输入执行任务

#### 5. 任务执行特点
- 自动应用最佳方法论
- 智能任务分解
- 多工具协同工作
- 实时进度反馈
- 自动生成任务总结

#### 6. 示例
```bash
# 基本使用
jarvis

# 指定平台和模型
jarvis -p yuanbao -m deep_seek_v3

# 直接执行任务
jarvis -t "分析项目结构并生成架构图"

# 组合使用
jarvis -p kimi -m k1 -t "优化项目性能"
```

### 代码代理功能 (jarvis-code-agent)

`jarvis-code-agent` 是Jarvis的代码分析与修改工具，专注于代码工程任务。

#### 1. 核心功能
- 代码分析与修改
- 代码审查与优化
- 自动化git操作
- 代码问题诊断与修复

#### 2. 使用方式
```bash
# 基本用法
jarvis-code-agent

# 或使用快捷命令
jca

# 带参数使用
jarvis-code-agent -p <平台> -m <模型> -r "需求描述"
```

#### 3. 命令行参数
| 参数 | 描述 |
|------|------|
| `-p/--platform` | 指定AI平台 (yuanbao/kimi/tongyi/openai) |
| `-m/--model` | 指定模型名称 |
| `-r/--requirement` | 直接指定需求描述 |

#### 4. 工作流程
1. 初始化环境（查找git根目录，检查未提交修改）
2. 分析用户需求
3. 执行代码修改
4. 自动处理git提交
5. 显示修改结果

#### 5. 示例
```bash
# 使用默认平台分析代码
jca

# 指定平台和模型
jca -p yuanbao -m deep_seek_v3

# 直接处理需求
jca -r "修复src/example.py中的内存泄漏问题"
```

### Git提交功能 (jarvis-git-commit)

`jarvis-git-commit` 是Jarvis的自动化git提交工具，能够智能分析代码变更并生成规范的提交信息。

#### 1. 核心功能
- 自动分析git变更
- 智能生成符合规范的提交信息
- 支持自定义提交信息前缀和后缀
- 自动处理大文件差异
- 支持多行提交信息

#### 2. 使用方式
```bash
# 基本用法
jarvis-git-commit

# 或使用快捷命令
jgc

# 带参数使用
jarvis-git-commit --root-dir <目录> --prefix "前缀" --suffix "后缀"
```

#### 3. 命令行参数
| 参数 | 描述 |
|------|------|
| `--root-dir` | Git仓库的根目录路径（默认为当前目录） |
| `--prefix` | 提交信息前缀（可选） |
| `--suffix` | 提交信息后缀（可选） |

#### 4. 提交信息格式
提交信息遵循以下格式：
```
<类型>(<范围>): <主题>

[可选] 详细描述变更内容和原因
```

类型说明：
- `fix`: 修复bug
- `feat`: 新功能
- `docs`: 文档更新
- `style`: 代码格式修改
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 其他修改

默认格式规则（可配置）：
1. 类型必须使用上述预定义类型
2. 范围表示变更的模块或组件（例如：auth, database, ui）
3. 主题行不超过72个字符，不以句号结尾，使用祈使语气
4. 详细描述部分应解释"是什么"和"为什么"，而非"如何"

#### 5. 工作流程
1. 检查git环境并确认有未提交的更改
2. 自动暂存所有更改
3. 分析代码差异
4. 智能生成提交信息
5. 执行git提交
6. 显示提交结果

#### 6. 示例
```bash
# 基本提交
jgc

# 指定仓库目录
jgc --root-dir /path/to/repo

# 添加提交信息前缀
jgc --prefix "[紧急修复]"

# 添加提交信息后缀
jgc --suffix "相关issue: #123"
```

### 自定义代理功能 (jarvis-agent)

`jarvis-agent` 是Jarvis的核心代理工具，提供通用的AI助手功能，支持自定义配置和任务执行。

#### 1. 核心功能
- 通用任务处理
- 自定义代理配置
- 多步骤任务规划
- 子代理任务拆分
- 交互式任务执行

#### 2. 使用方式
```bash
# 基本用法
jarvis-agent

# 带参数使用
jarvis-agent -f <配置文件> -c <代理定义文件> -t "初始任务"
```

#### 3. 命令行参数
| 参数 | 描述 |
|------|------|
| `-f/--config` | 指定配置文件路径（可选） |
| `-c/--agent_definition` | 指定代理定义文件路径（可选） |
| `-t/--task` | 指定初始任务（可选） |

#### 4. 配置文件格式
代理定义文件使用YAML格式：
```yaml
# 代理配置示例
name: "自定义代理名称"
system_prompt: "系统提示词"
auto_complete: false
need_summary: true
```

#### 5. 工作流程
1. 初始化环境
2. 加载配置文件（如果指定）
3. 创建代理实例
4. 执行初始任务（如果指定）
5. 进入交互式模式（如果没有初始任务）
6. 根据用户输入执行任务

#### 6. 任务执行特点
- 支持多行输入
- 自动任务规划
- 复杂任务自动拆分子代理
- 交互式执行过程
- 任务执行状态反馈

#### 7. 示例
```bash
# 基本使用
jarvis-agent

# 使用配置文件
jarvis-agent -f ~/.jarvis/config.yaml

# 使用代理定义文件
jarvis-agent -c custom_agent.yaml

# 直接执行任务
jarvis-agent -t "分析项目代码结构并生成文档"

# 组合使用
jarvis-agent -f config.yaml -c agent.yaml -t "优化项目性能"
```

### 平台管理功能 (jarvis-platform-manager)

`jarvis-platform-manager` 是Jarvis的平台管理工具，用于管理AI平台、模型和提供API服务。

#### 1. 核心功能
- 查看支持的平台和模型
- 与指定平台和模型进行交互式对话
- 启动OpenAI兼容的API服务
- 加载预定义角色进行对话

#### 2. 子命令说明

##### 2.1 查看平台信息
```bash
# 显示所有支持的平台和模型
jarvis-platform-manager info
```

##### 2.2 交互式对话
```bash
# 与指定平台和模型对话
jarvis-platform-manager chat -p <平台名称> -m <模型名称>
```

可用命令：
- `/bye` - 退出聊天
- `/clear` - 清除当前会话
- `/upload <文件路径>` - 上传文件到当前会话
- `/shell <命令>` - 执行shell命令
- `/save <文件名>` - 保存最后一条消息
- `/saveall <文件名>` - 保存完整对话历史

##### 2.3 启动API服务
```bash
# 启动OpenAI兼容的API服务
jarvis-platform-manager service --host <IP地址> --port <端口号> -p <平台名称> -m <模型名称>
```

参数说明：
- `--host`: 服务主机地址（默认：127.0.0.1）
- `--port`: 服务端口（默认：8000）
- `-p/--platform`: 指定默认平台
- `-m/--model`: 指定默认模型

##### 2.4 角色对话
```bash
# 加载角色配置文件并开始对话
jarvis-platform-manager role -c <配置文件路径>
```

角色配置文件格式（YAML）：
```yaml
roles:
  - name: "代码助手"
    description: "专注于代码分析和生成的AI助手"
    platform: "yuanbao"
    model: "deep_seek_v3"
    system_prompt: "你是一个专业的代码助手，专注于分析和生成高质量的代码"
  - name: "文档撰写"
    description: "帮助撰写技术文档的AI助手"
    platform: "kimi"
    model: "k1"
    system_prompt: "你是一个技术文档撰写专家，擅长将复杂技术概念转化为清晰易懂的文字"
```

#### 3. 示例
```bash
# 查看支持的平台和模型
jarvis-platform-manager info

# 与元宝平台的deep_seek_v3模型对话
jarvis-platform-manager chat -p yuanbao -m deep_seek_v3

# 启动API服务
jarvis-platform-manager service --host 0.0.0.0 --port 8080 -p yuanbao -m deep_seek_v3

# 使用角色配置文件
jarvis-platform-manager role -c ~/.jarvis/roles.yaml
```

## 🌟 核心功能 <a id="core-features"></a>

### 1. 主要特性
- 🆓 零成本接入：无缝集成腾讯元宝(推荐首选)、Kimi等优质模型，无需支付API费用
- 🛠️ 工具驱动：内置丰富工具集，涵盖脚本执行、代码开发、网页搜索、终端操作等核心功能
- 👥 人机协作：支持实时交互，用户可随时介入指导，确保AI行为符合预期
- 🔌 高度可扩展：支持自定义工具和平台，轻松集成MCP协议
- 📈 智能进化：内置方法论系统，持续学习优化，越用越智能

### 2. 视频介绍
[![视频介绍](docs/images/intro.png)](https://player.bilibili.com/player.html?isOutside=true&aid=114306578382907&bvid=BV1x2dAYeEpM&cid=29314583629&p=1)

### 3. 预定义任务
您可以创建预定义任务文件来快速执行常用命令：

1. 在`~/.jarvis/pre-command`或当前目录的`.jarvis/pre-command`文件中定义任务
2. 使用YAML格式定义任务，例如：
```yaml
build: "构建项目并运行测试"
deploy: "部署应用到生产环境"
```
3. 运行`jarvis`命令时会自动加载这些任务并提示选择执行

## ⚙️ 配置说明 <a id="configuration"></a>

### 1. 平台配置

#### 腾讯元宝 (推荐首选)
```yaml
JARVIS_PLATFORM: yuanbao
JARVIS_MODEL: deep_seek_v3
JARVIS_THINKING_PLATFORM: yuanbao
JARVIS_THINKING_MODEL: deep_seek
ENV:
  YUANBAO_COOKIES: <元宝cookies>
```

#### Kimi
```yaml
JARVIS_PLATFORM: kimi
JARVIS_MODEL: kimi
JARVIS_THINKING_PLATFORM: kimi
JARVIS_THINKING_MODEL: k1
ENV:
  KIMI_API_KEY: <Kimi API KEY>
```

#### 通义千问
```yaml
JARVIS_PLATFORM: tongyi
JARVIS_MODEL: Normal
JARVIS_THINKING_PLATFORM: tongyi
JARVIS_THINKING_MODEL: Thinking
ENV:
  TONGYI_COOKIES: <通义千问cookies>
```

#### OpenAI
```yaml
JARVIS_PLATFORM: openai
JARVIS_MODEL: gpt-4o
JARVIS_THINKING_PLATFORM: openai
JARVIS_THINKING_MODEL: gpt-4o
OPENAI_API_KEY: <OpenAI API Key>
OPENAI_API_BASE: https://api.openai.com/v1
```

### 2. 配置项说明
| 变量名称 | 默认值 | 说明 |
|----------|--------|------|
| `ENV` | {} | 环境变量配置 |
| `JARVIS_MAX_TOKEN_COUNT` | 960000 | 上下文窗口的最大token数量 |
| `JARVIS_MAX_INPUT_TOKEN_COUNT` | 32000 | 输入的最大token数量 |
| `JARVIS_PLATFORM` | yuanbao | 默认AI平台 |
| `JARVIS_MODEL` | deep_seek_v3 | 默认模型 |
| `JARVIS_THINKING_PLATFORM` | JARVIS_PLATFORM | 推理任务使用的平台 |
| `JARVIS_THINKING_MODEL` | JARVIS_MODEL | 推理任务使用的模型 |
| `JARVIS_EXECUTE_TOOL_CONFIRM` | false | 执行工具前是否需要确认 |
| `JARVIS_CONFIRM_BEFORE_APPLY_PATCH` | false | 应用补丁前是否需要确认 |
| `JARVIS_MAX_BIG_CONTENT_SIZE` | 160000 | 最大大内容大小 |
| `JARVIS_PRETTY_OUTPUT` | false | 是否启用PrettyOutput |
| `JARVIS_GIT_COMMIT_PROMPT` | "" | 自定义git提交信息生成提示模板 |
| `JARVIS_PRINT_PROMPT` | false | 是否打印提示 |
| `JARVIS_USE_METHODOLOGY` | true | 是否启用方法论功能 |
| `JARVIS_USE_ANALYSIS` | true | 是否启用任务分析功能 |
| `JARVIS_DATA_PATH` | ~/.jarvis | Jarvis数据存储目录路径 |

## 🛠️ 工具说明 <a id="tools"></a>

### 1. 内置工具
| 工具名称 | 描述 |
|----------|------|
| ask_user | 交互式用户输入收集 |
| rewrite_file | 文件重写工具 |
| edit_file | 代码编辑工具 |
| execute_script | 执行脚本并返回结果 |
| file_analyzer | 分析文件内容并提取关键信息 |
| methodology | 方法论管理工具 |
| read_code | 代码阅读与分析工具 |
| read_webpage | 读取网页内容并分析 |
| search_web | 使用互联网搜索 |
| virtual_tty | 控制虚拟终端执行操作 |

### 2. 命令替换功能
支持使用特殊标记`'<tag>'`触发命令替换功能：

| 标记 | 功能 |
|------|------|
| `'Summary'` | 总结当前会话并清空历史记录 |
| `'Clear'` | 清空当前会话 |
| `'ToolUsage'` | 显示可用工具列表及使用方法 |
| `'ReloadConfig'` | 重新加载配置文件 |
| `'Web'` | 网页搜索，支持多种提问格式 |
| `'FindRelatedFiles'` | 查找与功能相关的文件 |
| `'Fix'` | 修复问题 |
| `'Check'` | 执行静态代码检查，包括错误和风格问题 |
| `'SaveSession'` | 保存当前会话并退出 |

### 3. 自定义替换配置
在`~/.jarvis/config.yaml`中添加：
```yaml
JARVIS_REPLACE_MAP:
  tag_name:
    template: "替换后的内容"
    description: "标记描述"
    append: false
```

## 🛠️ 扩展开发 <a id="extensions"></a>

### 1. 添加新工具
在 `~/.jarvis/tools/` 中创建新的 Python 文件：
```python
from typing import Dict, Any
from jarvis.utils import OutputType, PrettyOutput

class CustomTool:
    name = "工具名称"
    description = "工具描述"
    parameters = {
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
        try:
            # 实现工具逻辑
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

### 2. 添加MCP
在`~/.jarvis/config.yaml`中添加：
```yaml
JARVIS_MCP:
  - type: stdio  # 或 sse/streamable
    name: MCP名称
    command: 可执行命令
    base_url: http://example.com/api
    args: [参数列表]
    env:
      KEY: VALUE
    enable: true
```

### 3. 添加新大模型平台
在 `~/.jarvis/platforms/` 中创建新的 Python 文件：
```python
from jarvis.jarvis_platform.base import BasePlatform

class CustomPlatform(BasePlatform):
    def __init__(self):
        pass

    def __del__(self):
        pass

    def chat(self, message: str) -> str:
        pass

    def upload_files(self, file_list: List[str]) -> bool:
        pass

    def delete_chat(self):
        pass

    def set_model_name(self, model_name: str):
        pass

    def set_system_prompt(self, message: str):
        pass

    def get_model_list(self) -> List[Tuple[str, str]]:
        pass

    def name(self) -> str:
        pass
```

## 🤝 贡献指南 <a id="contributing"></a>
1. Fork 仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m '添加某个很棒的特性'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证 <a id="license"></a>
本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---
<div align="center">
由 Jarvis 团队用 ❤️ 制作
</div>

![Jarvis技术支持群](docs/images/wechat.png)