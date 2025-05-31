# 🤖 Jarvis AI 助手
<p align="center">
  <img src="docs/images/jarvis-logo.png" alt="Jarvis Logo" width="200"/>
</p>
<div align="center">

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*您的智能开发和系统交互助手*

[核心特色](#core-features) • [视频介绍](#video-introduction) • [快速开始](#quick-start) • [配置说明](#configuration) • [工具说明](#tools) • [扩展开发](#extensions) • [贡献指南](#contributing) • [许可证](#license) • [Wiki文档](https://deepwiki.com/skyfireitdiy/Jarvis)
</div>

---

## 🌟 核心特色 <a id="core-features"></a>

- 🆓 零成本接入：无缝集成腾讯元宝(推荐首选)、Kimi等优质模型，无需支付API费用，同时保留强大的文件处理、搜索和推理能力
- 🛠️ 工具驱动：内置丰富工具集，涵盖脚本执行、代码开发、网页搜索、终端操作等核心功能
- 👥 人机协作：支持实时交互，用户可随时介入指导，确保AI行为符合预期
- 🔌 高度可扩展：支持自定义工具和平台，轻松集成MCP协议
- 📈 智能进化：内置方法论系统，持续学习优化，越用越智能


## 📺 视频介绍<a id="video-introduction"></a>

[![视频介绍](docs/images/intro.png)](https://player.bilibili.com/player.html?isOutside=true&aid=114306578382907&bvid=BV1x2dAYeEpM&cid=29314583629&p=1)


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

### 预定义任务(pre-command)

您可以创建预定义任务文件来快速执行常用命令：

1. 在`~/.jarvis/pre-command`或当前目录的`.jarvis/pre-command`文件中定义任务
2. 使用YAML格式定义任务，例如：
```yaml
build: "构建项目并运行测试"
deploy: "部署应用到生产环境"
```
3. 运行`jarvis`命令时会自动加载这些任务并提示选择执行

### 最小化配置

将以下配置写入到`~/.jarvis/config.yaml`文件中。

#### 腾讯元宝 (推荐首选)
```yaml
JARVIS_PLATFORM: yuanbao  # 推荐使用腾讯元宝平台，适配性最佳
JARVIS_MODEL: deep_seek_v3
JARVIS_THINKING_PLATFORM: yuanbao
JARVIS_THINKING_MODEL: deep_seek
ENV:
  YUANBAO_COOKIES: <元宝cookies>
  YUANBAO_AGENT_ID: <元宝AgentID>
```

元宝cookies以及AgentID获取方式：

![元宝cookies以及AgentID获取方式](docs/images/yuanbao.png)

浏览器地址栏中那部分是AgentID。


#### Kimi
```yaml
JARVIS_PLATFORM: kimi
JARVIS_MODEL: kimi
JARVIS_THINKING_PLATFORM: kimi
JARVIS_THINKING_MODEL: k1

ENV:
  KIMI_API_KEY: <Kimi API KEY>
```

Kimi API Key获取方式：

![Kimi API Key获取方式](docs/images/kimi.png)

删除Bearer前缀，剩下的内容就是Kimi API Key。


#### 通义千问
```yaml
JARVIS_PLATFORM: tongyi
JARVIS_MODEL: Normal  # 可选模型：Normal, Thinking, Deep-Research, Code-Chat
JARVIS_THINKING_PLATFORM: tongyi
JARVIS_THINKING_MODEL: Thinking

ENV:
  TONGYI_COOKIES: <通义千问cookies>
```

通义千问cookies获取方式：

![通义千问cookies获取方式](docs/images/tongyi.png)

1. 登录[通义千问](https://www.tongyi.com/qianwen)
2. 打开浏览器开发者工具（F12）
3. 在Network标签页中找到任意请求
4. 在请求头中找到Cookie字段，复制其值

配置说明：
1. `TONGYI_COOKIES`: 必填，用于身份验证
2. 支持的模型：
   - `Normal`: 标准对话模型
   - `Thinking`: 深度思考模型
   - `Deep-Research`: 深度研究模型
   - `Code-Chat`: 代码对话模型


#### OpenAI
```yaml
JARVIS_PLATFORM: openai
JARVIS_MODEL: gpt-4o  # 默认模型，可选gpt-4-turbo, gpt-3.5-turbo等
JARVIS_THINKING_PLATFORM: openai
JARVIS_THINKING_MODEL: gpt-4o

OPENAI_API_KEY: <OpenAI API Key>
OPENAI_API_BASE: https://api.openai.com/v1  # 可选，默认为官方API地址
```

配置说明：
1. `OPENAI_API_KEY`: 必填。
2. `OPENAI_API_BASE`: 可选，用于自定义API端点

以上配置编写到`~/.jarvis/config.yaml`文件中。

支持的模型可通过`jarvis-platform-manager --list-models`查看完整列表。

### 基本使用
| 命令 | 快捷方式 | 功能描述 |
|------|----------|----------|
| `jarvis` | - | 使用通用代理 |
| `jarvis-code-agent` | `jca` | 使用代码代理 |
| `jarvis-smart-shell` | `jss` | 使用智能shell功能 |
| `jarvis-platform-manager` | - | 使用平台管理功能 |
| `jarvis-code-review` | - | 使用代码审查功能 |
| `jarvis-git-commit` | `jgc` | 使用自动化git commit功能 |
| `jarvis-dev` | - | 使用dev功能（开发中） |
| `jarvis-git-squash` | - | 使用git squash功能 |
| `jarvis-multi-agent` | - | 使用多代理功能 |
| `jarvis-agent` | - | 使用agent功能 |
| `jarvis-tool` | - | 使用工具功能 |
| `jarvis-git-details` | - | 使用git details功能 |
| `jarvis-methodology` | - | 使用方法论功能 |

## 🏗️ 平台管理功能

`jarvis-platform-manager` 提供以下子命令来管理AI平台和模型：

### 1. 列出支持的平台和模型
```bash
jarvis-platform-manager info
```
显示所有支持的AI平台及其可用模型列表。

### 2. 与指定平台和模型聊天
```bash
jarvis-platform-manager chat -p <平台名称> -m <模型名称>
```
启动交互式聊天会话，支持以下命令：
- `/bye` - 退出聊天
- `/clear` - 清除当前会话
- `/upload <文件路径>` - 上传文件到当前会话
- `/shell <命令>` - 执行shell命令
- `/save <文件名>` - 保存最后一条消息
- `/saveall <文件名>` - 保存完整对话历史

### 3. 启动OpenAI兼容的API服务
```bash
jarvis-platform-manager service --host <IP地址> --port <端口号> -p <平台名称> -m <模型名称>
```
启动一个兼容OpenAI API的服务，可用于其他应用程序集成。

### 4. 加载角色配置文件
```bash
jarvis-platform-manager role -c <配置文件路径>
```
从YAML配置文件加载预定义角色进行对话。配置文件格式示例：
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


---

## ⚙️ 配置说明 <a id="configuration"></a>
### 配置项
| 变量名称 | 默认值 | 说明 |
|----------|--------|------|
| `ENV` | {} | 环境变量配置，用于设置系统环境变量 |
| `JARVIS_MAX_TOKEN_COUNT` | 960000 | 上下文窗口的最大token数量 |
| `JARVIS_MAX_INPUT_TOKEN_COUNT` | 32000 | 输入的最大token数量 |
| `JARVIS_AUTO_COMPLETE` | false | 是否启用自动完成功能（任务判定完成的时候会自动终止） |
| `JARVIS_SHELL_NAME` | bash | 系统shell名称 |
| `JARVIS_PLATFORM` | yuanbao | 默认AI平台 |
| `JARVIS_MODEL` | deep_seek_v3 | 默认模型 |
| `JARVIS_THINKING_PLATFORM` | JARVIS_PLATFORM | 推理任务使用的平台 |
| `JARVIS_THINKING_MODEL` | JARVIS_MODEL | 推理任务使用的模型 |
| `JARVIS_EXECUTE_TOOL_CONFIRM` | false | 执行工具前是否需要确认 |
| `JARVIS_CONFIRM_BEFORE_APPLY_PATCH` | true | 应用补丁前是否需要确认 |
| `JARVIS_MAX_TOOL_CALL_COUNT` | 20 | 最大连续工具调用次数，如果是0表示无限制 |
| `JARVIS_AUTO_UPDATE` | true | 是否自动更新Jarvis（仅在以git仓库方式安装时有效） |
| `JARVIS_MAX_BIG_CONTENT_SIZE` | 160000 | 最大大内容大小 |
| `JARVIS_PRETTY_OUTPUT` | false | 是否启用PrettyOutput |
| `JARVIS_GIT_COMMIT_PROMPT` | "" | 自定义git提交信息生成提示模板 |
| `JARVIS_PRINT_PROMPT` | false | 是否打印提示 |
| `JARVIS_USE_METHODOLOGY` | true | 是否启用方法论功能 |
| `JARVIS_USE_ANALYSIS` | true | 是否启用任务分析功能 |
| `JARVIS_DATA_PATH` | ~/.jarvis | Jarvis数据存储目录路径 |

所有配置编写到`~/.jarvis/config.yaml`文件中即可生效。

### 配置文件格式
配置文件仅支持YAML格式：
```yaml
JARVIS_PLATFORM: yuanbao
JARVIS_MODEL: deep_seek_v3
ENV:
  YUANBAO_COOKIES: "your_cookies_here"
```

---
## 🛠️ 工具说明 <a id="tools"></a>
### 内置工具
| 工具名称 | 描述 |
|----------|------|
| ask_user | 交互式用户输入收集 |
| chdir | 更改当前工作目录 |
| rewrite_file | 文件重写工具，用于完全重写或创建文件，提供完整的文件内容替换 |
| edit_file | 代码编辑工具，用于精确修改文件内容，支持搜索替换方式编辑 |
| code_plan | 理解需求并制定详细的代码修改计划，在修改前获取用户确认 |
| create_code_agent | 代码开发工具，当需要修改代码时使用 |
| create_sub_agent | 创建子代理以处理特定任务，子代理将生成任务总结报告 |
| execute_script | 执行脚本并返回结果，支持任意解释器。 |
| file_analyzer | 分析文件内容并提取关键信息。支持的文件：文本文件、word文档、pdf文件、图片 |
| file_operation | 文件批量操作工具，可批量读写多个文件，支持文本文件，适用于需要同时处理多个文件的场景（读取配置文件、保存生成内容等） |
| methodology | 方法论管理工具，支持添加、更新和删除操作 |
| read_code | 代码阅读与分析工具，用于读取源代码文件并添加行号，针对代码文件优化，提供更好的格式化输出和行号显示，适用于代码分析、审查和理解代码实现的场景 |
| read_webpage | 读取网页内容并分析 |
| search_web | 使用互联网搜索 |
| virtual_tty | 控制虚拟终端执行各种操作，如启动终端、输入命令、获取输出等。 |


### 命令替换功能
Jarvis支持使用特殊标记`'<tag>'`来触发命令替换功能，其中`tag`是预定义的标记名称。系统会自动将这些标记替换为预定义的模板内容。

#### 内置标记
| 标记 | 功能 |
|------|------|
| `'Summary'` | 总结当前会话并清空历史记录 |
| `'Clear'` | 清空当前会话 |
| `'CodeBase'` | 查询代码库 |
| `'Web'` | 网页搜索 |
| `'Methodology'` | 查找相关方法论 |
| `'Plan'` | 生成代码修改计划 |
| `'FindRelatedFiles'` | 查找相关文件 |
| `'FindMethodology'` | 查找方法论 |
| `'Dev'` | 调用create_code_agent开发需求 |
| `'Fix'` | 修复问题 |

#### 自定义替换
可以通过以下方式配置自定义替换规则：

**配置文件**:
在`~/.jarvis/config.yaml`中添加`JARVIS_REPLACE_MAP`配置项：
```yaml
JARVIS_REPLACE_MAP:
  tag_name:
    template: "替换后的内容"
    description: "标记描述"
    append: false  # 可选，true表示追加到输入末尾，false表示直接替换
```



#### 文件路径补全
在交互式输入中，输入`@`可以触发文件路径补全功能，支持模糊匹配。


### 工具位置
- 内置工具：`src/jarvis/tools/`
- 用户工具：`~/.jarvis/tools/`
---
## 🛠️ 扩展开发 <a id="extensions"></a>
### 添加新工具
在 `~/.jarvis/tools/` 中创建新的 Python 文件：
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


### 添加MCP
MCP(模型上下文协议)支持以下配置方式：

#### 配置文件
在`~/.jarvis/config.yaml`中添加`JARVIS_MCP`配置项：
```yaml
JARVIS_MCP:
  - type: stdio  # 或 sse/streamable
    name: MCP名称
    command: 可执行命令  # stdio模式必填
    base_url: http://example.com/api  # sse/streamable模式必填
    args: [参数列表]  # 可选
    env:  # 可选环境变量
      KEY: VALUE
    enable: true  # 可选，默认为true
```



### 添加新大模型平台
在 `~/.jarvis/platforms/` 中创建新的 Python 文件：
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

    def set_system_prompt(self, message: str):
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

![Jarvis技术支持群](docs/images/wechat.png)