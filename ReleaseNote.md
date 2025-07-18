### Release Note - v0.1.222 2025-07-19

#### **新功能 (Features)**
- 为所有主要命令添加了快捷别名 (e.g., `jvs`, `jca`, `jcr`)，提升使用效率。
- 新增 `jarvis-rag` (`jrg`) 命令，提供独立的RAG功能入口。
- 新增 "GROW模型分析专家" 角色，用于结构化目标设定和问题解决。
- 新增 `JARVIS_ENABLE_STATIC_ANALYSIS` 配置项，允许用户控制是否在代码修改后执行静态分析。
- Kimi平台新增 "k2" 深度思考模型支持。

#### **修复 (Fixes)**
- (无)

#### **优化与重构 (Refactors & Improvements)**
- 重构了Agent的模型配置逻辑，使用 `llm_type` (`normal`/`thinking`)替代硬编码的 `platform` 和 `model_name`，增强了灵活性和可维护性。
- 优化了PDF导出样式 (`style.css`)，改善了字体、边距和布局，并增加了页码。
- 改进了会话恢复逻辑，确保恢复后能正确识别为非首次运行。
- 简化了Agent示例配置文件，移除了冗余的模型定义。

#### **文档更新 (Documentation)**
- 更新了 `README.md`，加入了所有命令的快捷方式，并补充了新功能说明。
- 更新了 `technical_documentation.md`，精简和澄清了RAG系统的架构描述。

#### **其他 (Miscellaneous)**
- (无)

本次更新主要聚焦于提升用户体验和内部架构优化。引入了大量命令别名以方便日常使用，并对核心Agent的LLM调用机制进行了重构，使其更加灵活。同时，新增了RAG和GROW模型专家等功能，并优化了文档和PDF产出质量。

### Release Note - v0.1.221 2025-07-14

#### **新功能 (Features)**
- (rag): 将 RAG 依赖项设为可选安装
- (rag): 支持配置RAG重排模型
- (rag): 为 add 命令添加 .ragignore 支持和批处理功能
- (docs): 引入基于 PrinceXML 的 PDF 生成流程

#### **修复 (Fixes)**
- (暂无)

#### **优化与重构 (Refactors & Improvements)**
- (edit_file): 移除AI辅助编辑并优化补丁应用逻辑
- (deps): 将RAG依赖项移至可选安装
- (jarvis_agent): 重构 Agent 类以提升模块化
- (jarvis_agent): 提取Agent提示词到独立文件
- (rag): 简化RAG配置，直接指定嵌入模型

#### **文档更新 (Documentation)**
- (jarvis_rag): 将模块文档和注释翻译为中文
- (docs): 修复技术文档中的标题格式和章节编号
- (config): 添加 JARVIS_RAG 配置项文档
- (cli): 更新CLI文档中嵌入模型参数名称
- (docs): 优化技术文档中的图表
- (rag): 补充 RAG 实现方案的技术文档

#### **其他 (Miscellaneous)**
- (reranker): 忽略 sort 方法的类型检查错误

本次更新主要围绕RAG功能进行增强和优化，将其依赖项设为可选，并支持了重排模型配置和`.ragignore`文件。同时，对Agent和代码编辑工具进行了重构，提升了系统的模块化和稳定性。文档方面也进行了大量更新和改进，并引入了PDF生成流程。

### Release Note - v0.1.220 2025-07-13

#### **新功能 (Features)**
- **新增 RAG 框架 (`jarvis-rag`)**: 引入了一个全新的 `jarvis-rag` 命令行工具，用于构建、管理和查询本地化的RAG（检索增强生成）知识库。
  - `jarvis-rag add`: 支持添加文件、目录或通配符模式的文档到知识库。
  - `jarvis-rag query`: 支持向知识库提问，并可指定不同的大语言模型进行回答。
- **支持 Python 3.12**: 项目现已正式支持 Python 3.12 版本。

#### **修复 (Fixes)**
- **元宝平台Cookie**: 修复了 `YUANBAO_COOKIES` 未设置时程序不抛出异常的问题，现在会明确提示用户进行设置。

#### **优化与重构 (Refactors & Improvements)**
- **Agent系统提示**: 重构并优化了核心Agent的系统提示（System Prompt），使其更清晰、更结构化，提升了与模型交互的稳定性。
- **依赖库更新**: 升级了多个核心依赖库，如 `ddgs`, `beautifulsoup4`, `lxml` 等，以获取最新的功能和安全修复。
- **提升Python版本要求**: 将项目的最低Python版本要求从 `3.8` 提升至 `3.9`。

#### **文档更新 (Documentation)**
- **README更新**: 详细更新了 `README.md` 文件，增加了 `jarvis-rag` 工具的完整使用说明和示例。

#### **其他 (Miscellaneous)**
- **项目配置**: 在 `pyproject.toml` 和 `setup.py` 中添加了 RAG 功能所需的新依赖项，并注册了新的 `jarvis-rag` 命令。
- **配置结构**: 在 `config_schema.json` 中添加了 `JARVIS_RAG` 的相关配置项，用于RAG功能的详细设置。

本次更新主要围绕 **本地化RAG知识库** 这一核心功能展开，极大地增强了Jarvis在特定领域知识问答和代码理解方面的能力。同时，通过对核心Agent的优化和依赖库的升级，提升了整体的稳定性和可维护性。

### Release Note - v0.1.219 2025-07-11

#### **新功能 (Features)**
- **增强网页搜索能力**: `search_web` 工具现已集成 DuckDuckGo 搜索引擎。当底层大模型不支持网页搜索时，本工具可独立执行搜索、抓取网页内容并进行总结，极大地扩展了信息获取能力。

#### **修复 (Fixes)**
- (本次更新无修复内容)
 
#### **优化与重构 (Refactors & Improvements)**
- **代码结构优化**: 将用户确认函数 `user_confirm` 统一移动至 `jarvis_utils.input` 模块，提升了代码的组织性和可维护性。
- **剪贴板功能增强**: 新增 `copy_to_clipboard` 工具函数，该函数能智能检测并依次尝试使用 `xsel` 和 `xclip` 命令，增强了在不同 Linux 环境下的剪贴板兼容性。
- **依赖项更新**: 在 `pyproject.toml` 和 `setup.py` 中添加了 `ddgs`, `beautifulsoup4`, `lxml` 等依赖，以支持新的网页搜索功能。

#### **文档更新 (Documentation)**
- **新增技术文档**: 添加了完整的技术文档 `docs/technical_documentation.md`，详细介绍了 Jarvis 的设计哲学、核心架构、组件交互、配置方法以及开发者指南。

#### **其他 (Miscellaneous)**
- **更新 .gitignore**: 将 `*.pdf` 文件类型添加到忽略列表，避免将 PDF 文件意外提交到版本库。

本次更新主要聚焦于增强系统的核心功能和提升开发者体验。通过引入独立的网页搜索能力，Jarvis 现在能够更自主地获取外部信息。同时，全面的技术文档和代码结构优化为未来的社区贡献和二次开发奠定了坚实的基础。

### Release Note - v0.1.214 2025-07-08

#### **新功能 (Features)**
- **会话持久化**: 新增了完整的会话保存与恢复功能。
- **新角色**: 在角色库中新增了 "公司技术教练认证首席导师" 角色，提供专业的教练式陪练引导。
- **命令增强**: `jpm role` 命令现在支持使用 `--platform` 和 `--model` 参数临时覆盖角色文件中定义的平台和模型。
- **内置命令**: 新增 `SaveSession` 内置命令，允许在 `jarvis` 交互中快速保存会话并退出。

#### **修复 (Fixes)**
- **流式服务**: 修复了 `jpm service` 中流式响应的实现问题，确保了数据能够实时、稳定地从模型传输到客户端。
- **文件编辑**: 改进了 `edit_file` 工具的补丁应用算法，提高了在处理不同缩进和首尾换行情况下的匹配成功率和准确性。

#### **优化与重构 (Refactors & Improvements)**
- **角色配置简化**: 移除了角色配置文件中每个角色必需的 `platform` 和 `model` 字段，使配置更简洁，并通过命令行参数赋予了更高的灵活性。
- **代码质量**: 对多个模块进行了代码重构，包括优化类型提示、移除冗余代码和改进中断处理逻辑，提升了代码的可读性和健壮性。

#### **文档更新 (Documentation)**
- **命令提示**: 更新了 `jpm` 的命令帮助信息和自动补全提示，加入了新的会话管理相关命令。
- **代码注释**: 在 `jarvis-code-agent(jac)` 相关代码中增加了关于何时执行静态检查的注释说明。

本次更新核心是引入了完整的会话持久化机制，极大地提升了工具的连续使用体验。同时，对底层服务和核心工具进行了多项修复与优化，并增加了一个功能强大的新角色。

### Release Note - v0.1.213 2025-07-07

#### **新功能 (Features)**
- 新增 "问题挖掘专家" 角色，专注于从复杂场景中识别和量化核心问题。

#### **修复 (Fixes)**
- 调整 `pyyaml` 依赖版本至 `>=5.3.1`，以提高兼容性。
- 将复制最后一条消息的快捷键从 `Ctrl+L` 更改为 `Ctrl+O`，以避免与终端清屏快捷键冲突。

#### **优化与重构 (Refactors & Improvements)**
- 重构 `AI8` 和 `Oyi` 平台模块，引入统一的 `http` 工具和 `while_success` 重试机制，增强了网络请求的稳定性和可靠性。
- 优化了部分代码的类型提示和格式，提升了代码质量和可读性。

本次更新主要通过重构网络请求模块提升了系统的稳定性，并新增了 "问题挖掘专家" 角色来增强问题分析能力，同时修复了一些依赖和快捷键问题。

### Release Note - v0.1.212 2025-07-06

#### **新功能 (Features)**  
- 新增AI8模型平台实现，支持AI8 API集成
- 新增OYI模型平台实现，支持OYI API集成
- 添加全局最后一条消息记录功能，可通过Ctrl+L快捷键复制

#### **修复 (Fixes)**  
- 修复Kimi模型文件解析和流式响应处理逻辑
- 修复Kimi模型消息流式响应处理中的Unicode解码问题

#### **优化与重构 (Refactors & Improvements)**  
- 重构Kimi模型的消息流式响应处理机制
- 优化平台管理器主模块的中文注释和文档
- 改进输入模块，添加最后一条消息复制功能

#### **文档更新 (Documentation)**  
- 更新平台管理器主模块的注释为中文
- 添加新功能的文档说明

#### **其他 (Miscellaneous)**  
- 更新输入模块的提示信息，包含新快捷键说明
- 优化代码格式和结构

本次更新主要增加了两个新的模型平台支持(AI8和OYI)，优化了Kimi模型的流式响应处理，并添加了实用的最后一条消息复制功能，提升了用户体验。

### Release Note - v0.1.211 2025-07-05

#### **新功能 (Features)**
- 添加tiktoken模型
- 添加提示信息复制到剪贴板功能

#### **修复 (Fixes)**
- 更新jarvis数据配置文件包含模式

#### **优化与重构 (Refactors & Improvements)**
- 移除HuggingFace模型解压功能
- 修改获取最近提交信息以过滤当前用户

本次更新主要增加了tiktoken相关功能支持，优化了提示交互体验，并改进了配置管理。


### Release Note - v0.1.210 2025-07-05

#### **新功能 (Features)**  
- 新增httpx>=0.28.1依赖，用于改进HTTP请求处理
- 实现stream_post流式POST请求方法，支持更高效的流式响应处理

#### **修复 (Fixes)**  
- 修复平台消息流处理逻辑，改进SSE格式数据解析
- 修复git工具中最新提交日期检查逻辑

#### **优化与重构 (Refactors & Improvements)**  
- 重构HTTP模块，从requests迁移到httpx库
- 优化流式响应处理逻辑，减少内存使用
- 改进代码结构，增加类型提示和文档字符串

#### **文档更新 (Documentation)**  
- 更新HTTP模块文档，反映新的httpx实现
- 添加stream_post方法文档说明

#### **其他 (Miscellaneous)**  
- 禁用CodeAgent中的方法论和分析功能
- 改进错误处理和连接稳定性

本次更新主要改进了HTTP请求处理能力，迁移到更现代的httpx库，并优化了流式响应处理逻辑，提升了系统稳定性和性能。


### Release Note - v0.1.209 2025-07-04
#### 1. 新功能(New Features)
- **新增平台管理命令别名**  
  在`pyproject.toml`和`setup.py`中为`jarvis-platform-manager`添加了`jpm`别名，提高命令可用性  
- **新增HTTP工具模块**  
  新增`src/jarvis/jarvis_utils/http.py`文件，提供统一的HTTP请求处理  
- **新增自动安装机制**  
  在`jarvis_utils/git_utils.py`中增加git更新后自动pip安装的逻辑  

#### 2. Bug修复(Bug Fixes)
- **修复编辑文件输出抑制问题**  
  在`edit_file_handler.py`中修正输出抑制逻辑  

- **修复文件上传逻辑**  
  在各平台文件中统一使用新的HTTP模块处理上传  

- **修复初始化流程**  
  在`jarvis_agent/__init__.py`中移除无效的历史记录处理  

#### 3. 性能优化(Performance Improvements)
- **优化token计数**  
  使用`tiktoken`替代`transformers`进行token计数  

#### 4. 文档更新(Documentation)
- **更新README文档**  
  修正命令行别名说明和配置参数说明  

- **更新配置schema**  
  移除过期的配置参数如`JARVIS_AUTO_UPDATE`  

#### 5. 其他变更(Other Changes)
- **依赖项更新**  
  移除`transformers`和`torch`，新增`tiktoken`和`pyyaml`  
- **新增.gitignore规则**  


# Release Note v0.1.208 - 2025-07-02

## 新增功能
- 新增五个专家角色配置
- 增强JSS fish补全功能
- 新增文案润色专家角色配置

## 问题修复
- 修复大消息分块提交时的响应拼接问题
- 修复edit_file_handler中的文件差异格式处理

## 其他改进
### 重构优化
- 移除yaspin依赖并简化控制台输出
- 优化新增文件确认逻辑和类型提示
- 从Python文件类型中移除isort工具
- 移除开发中的jarvis-dev模块
- 移除未使用的工具并统一使用rewrite_file工具

### 代码质量
- 添加类型检查忽略注释
- 改进shell名称获取逻辑并更新类型注解


### Release Note - v0.1.207 2025-06-27

#### **新功能 (Features)**  
- 新增'ToolUsage'命令，提示可用工具列表及使用方法
- 新增'ReloadConfig'命令，重新加载配置文件
- 新增'Check'命令，执行静态代码检查，包括错误和风格问题

#### **修复 (Fixes)**  
- 修复了分块提交内容时的响应处理逻辑

#### **优化与重构 (Refactors & Improvements)**  
- 调整了JARVIS_CONFIRM_BEFORE_APPLY_PATCH默认值为false
- 优化了Web搜索命令的描述，支持多种提问格式
- 优化了'FindRelatedFiles'命令的描述，更准确地查找与功能相关的文件
- 重构了分块提交内容时的响应处理逻辑，提高稳定性

#### **文档更新 (Documentation)**  
- 更新了README.md中的命令列表和描述
- 更新了配置项JARVIS_CONFIRM_BEFORE_APPLY_PATCH的默认值说明

#### **其他 (Miscellaneous)**  
- 调整了部分代码格式和注释

本次更新主要优化了命令功能、修复了配置一致性问题，并改进了大内容分块提交的处理逻辑。

### Release Note - v0.1.206 2025-06-27

#### **优化与重构 (Refactors & Improvements)**  
- 优化了edit_file_handler.py中的代码格式和类型提示
- 修复了中断处理时的spinner显示问题
- 改进了补丁应用时的用户输入处理流程

本次更新主要针对代码质量和用户体验进行了优化，特别是改进了文件编辑处理器的稳定性和交互体验

### Release Note - v0.1.205 2025-06-23

#### **新功能 (Features)**  
- 新增中断处理机制，允许用户在补丁应用中断时提供补充信息
- 更新了多行输入提示信息，改为中文显示

#### **修复 (Fixes)**  
- 修复了多个类型检查警告，添加了类型忽略注释
- 修复了中断处理逻辑，添加了中断状态重置

#### **优化与重构 (Refactors & Improvements)**  
- 重构了文件编辑处理器的补丁应用逻辑
- 优化了输入工具的类型提示和导入结构

#### **其他 (Miscellaneous)**  
- 移除了不必要的代码注释
- 统一了多行输入工具的使用方式

本次更新主要优化了代码质量，增强了中断处理能力，并改进了用户体验。

### Release Note - v0.1.204 2025-06-19

#### **新功能 (Features)**  
- 新增文件添加确认机制，当检测到大量新增文件、代码行数或二进制文件时会提示用户确认
- 在代码编辑器中添加中断检查功能，支持用户中断补丁应用

#### **修复 (Fixes)**  
- 修复了长上下文提交时的进度显示问题
- 修复了git提交流程中新增文件检测逻辑

#### **优化与重构 (Refactors & Improvements)**  
- 重构了git工具类，提取新增文件检测和确认逻辑到独立函数
- 优化了平台基础类的长文本提交处理，移除spinner改用普通输出
- 改进代码编辑器的错误处理流程

#### **文档更新 (Documentation)**  
- 更新代码工程师指南，添加文件操作工具使用说明

#### **其他 (Miscellaneous)**  
- 添加开发者激励提示信息
- 改进git提交信息模板

本次更新主要增强了git变更检测和用户确认机制，优化了长文本处理性能，并改进了开发者体验。

### Release Note - v0.1.203 2025-06-17

#### **新功能 (Features)**  
- 改进了文件路径解析逻辑，支持单引号、双引号和无引号的文件路径格式
- 添加了重复文件路径的合并处理功能
- 增强了搜索文本的多处匹配警告提示

#### **修复 (Fixes)**  
- 修复了搜索文本在文件中不存在时的错误处理
- 修复了缩进搜索文本的多处匹配检测问题

#### **优化与重构 (Refactors & Improvements)**  
- 统一了补丁数据结构中的键名（SEARCH/REPLACE）
- 优化了错误提示信息的输出格式
- 重构了补丁解析逻辑，提高代码可读性

#### **文档更新 (Documentation)**  
- 更新了方法注释，更清晰地描述功能和行为

#### **其他 (Miscellaneous)**  
- 改进了代码缩进和格式一致性

本次更新主要改进了文件编辑处理器的稳定性和用户体验，增强了错误检测和处理能力。

### Release Note - v0.1.202 2025-06-16

#### **优化与重构 (Refactors & Improvements)**  
- 优化了文件编辑处理器的正则表达式匹配逻辑，移除了不必要的空格匹配
- 简化了DIFF块的格式标记，使用更简洁的SEARCH/REPLACE标签
- 改进了文件编辑指令的模板格式，使其更加紧凑易读

#### **其他 (Miscellaneous)**  
- 修复了平台基础类中消息接收确认的格式问题

本次更新主要对代码编辑功能进行了优化和重构，提高了文件编辑指令的处理效率和可靠性。


### Release Note - v0.1.201 2025-06-15

#### **新功能 (Features)**  
- 新增EditFileHandler类，用于处理文件编辑指令(PATCH块)
- 支持通过PATCH指令进行精确的文件内容修改
- 新增fast_edit和slow_edit两种编辑模式

#### **修复 (Fixes)**  
- 修复yuanbao平台首次聊天标志未正确重置的问题
- 修复文件编辑工具中yaml解析失败时的错误处理
- 修复thinking标签未正确处理的问题

#### **优化与重构 (Refactors & Improvements)**  
- 重构文件编辑工具为多文件处理模式
- 优化代码补丁生成逻辑，增加自动缩进匹配功能
- 改进文件编辑失败时的回滚机制

#### **文档更新 (Documentation)**  
- 更新文件编辑指令格式文档
- 添加PATCH处理器使用说明

#### **其他 (Miscellaneous)**  
- 移除旧的edit_file工具，改用新的EditFileHandler
- 优化工具调用格式错误提示信息

本次更新主要改进了文件编辑功能，新增了更精确的PATCH指令支持，并优化了编辑失败时的处理流程。

### Release Note - v0.1.200 2025-06-13

#### **新功能 (Features)**  
- 添加了工具调用中断时的用户干预处理逻辑
- 新增git仓库更新后的自动重启功能

#### **修复 (Fixes)**  
- 修复了builtin_input_handler中ReloadConfig的返回逻辑
- 修复了Yuanbao平台请求超时问题

#### **优化与重构 (Refactors & Improvements)**  
- 优化了Yuanbao平台所有请求的超时处理(统一设置为600秒)
- 移除了builtin_replace_map.py中冗余的ToolHelp模板

#### **文档更新 (Documentation)**  
- 无

#### **其他 (Miscellaneous)**  
- 优化了utils.py的导入顺序

本次更新主要增强了工具调用中断处理能力，优化了Yuanbao平台的请求稳定性，并简化了内置替换映射表。

### Release Note - v0.1.199 2025-06-10

#### **新功能 (Features)**  
- 无

#### **修复 (Fixes)**  
- 修复了edit_file工具的多处匹配错误提示格式
- 修复了user_confirm函数中的KeyboardInterrupt异常处理问题

#### **优化与重构 (Refactors & Improvements)**  
- 优化rewrite_file工具，统一使用绝对路径处理文件
- 改进rewrite_file工具的文件列表记录功能
- 移除了utils.py中不必要的空行

#### **文档更新 (Documentation)**  
- 无

#### **其他 (Miscellaneous)**  
- 更新了docs/images/wechat.png图片文件

本次更新主要优化了文件工具的错误处理和路径处理逻辑，增强了工具的健壮性。

### Release Note - v0.1.197 2025-06-07

#### **新功能 (Features)**  
- 新增历史对话文件上传功能，支持将历史对话保存为临时文件并上传
- 添加JARVIS_USE_HISTORY_COUNT配置项，替代原有的JARVIS_USE_HISTORY布尔配置

#### **优化与重构 (Refactors & Improvements)**  
- 重构历史记录处理逻辑，分离保存功能到独立方法
- 优化上下文切换机制，支持文件上传方式保留历史
- 改进README.md配置说明，更新历史记录相关文档

#### **其他 (Miscellaneous)**  
- 修复临时文件清理逻辑，确保异常情况下也能正确清理

本次更新主要增强了历史记录处理能力，支持通过文件上传方式保留完整对话历史，同时优化了配置项和文档说明。

### Release Note - v0.1.196 2025-06-05

#### **新功能 (Features)**  
- 新增历史记录功能(JARVIS_USE_HISTORY_COUNT配置项)
- 添加历史记录导出为Markdown的功能

#### **优化与重构 (Refactors & Improvements)**  
- 调整首次运行时文件上传逻辑
- 重构Agent初始化代码，提取_first_run方法
- 优化历史记录处理逻辑

#### **文档更新 (Documentation)**  
- 更新README.md添加JARVIS_USE_HISTORY配置说明

本次更新主要增加了历史记录功能，可以将历史记录作为上下文，并支持导出为Markdown格式，同时优化了代码结构和文件处理逻辑。

### Release Note - v0.1.195 2025-06-04

#### **新功能 (Features)**  
- 新增Jarvis历史记录功能(jarvis_history)
- 新增Jarvis通用代理工具功能文档

#### **优化与重构 (Refactors & Improvements)**  
- 改进git差异获取逻辑，支持空仓库情况
- 优化输出异常处理，防止崩溃
- 增强方法论上传功能，支持同时上传其他文件
- 改进代码导入组织，加快初始化速度

#### **文档更新 (Documentation)**  
- 更新README.md，添加Jarvis通用代理工具详细文档

#### **其他 (Miscellaneous)**  
- 修复git差异解码错误处理
- 改进文件上传失败处理逻辑
- 优化代码格式和类型提示

本次更新主要增强了Jarvis的历史记录功能，改进了git操作和异常处理，并完善了文档体系。

### Release Note - v0.1.194 2025-06-01

#### **新功能 (Features)**  
- 添加重新加载配置功能
- 添加ToolUsage标记处理功能
- 在提交流程中提前获取修改文件列表

#### **修复 (Fixes)**  
- 修复缩进处理时空行也被添加空格的问题
- 调整工具调用和中断处理的执行顺序

#### **优化与重构 (Refactors & Improvements)**  
- 将配置文件加载逻辑提取到独立函数
- 优化代码格式和导入顺序
- 精简各语言默认的lint工具配置
- 移除未使用的导入语句和功能

#### **文档更新 (Documentation)**  
- 重构文档结构并优化内容组织

本次更新主要包含配置管理增强、工具调用流程优化、代码质量改进和文档重构。

### Release Note - v0.1.193 2025-05-31

#### **新功能 (Features)**  
- 添加example/roles/roles.yaml角色配置文件
- 完善代码代理功能文档和使用说明

#### **修复 (Fixes)**  
- 修复addon_prompt生成逻辑
- 修复代码代理功能中的文件修改提示逻辑
- 修复yuanbao平台初始化参数传递问题

#### **优化与重构 (Refactors & Improvements)**  
- 优化代码代理功能的输出格式
- 重构工具注册表的输出格式
- 改进方法论模块的输出显示

#### **文档更新 (Documentation)**  
- 更新README.md添加代码代理功能说明
- 完善内置工具帮助文档

#### **其他 (Miscellaneous)**  
- 添加空文件处理逻辑
- 改进错误处理提示

本次更新主要新增了代码代理功能，并优化了多个模块的输出显示和错误处理。

### Release Note - v0.1.192 2025-05-31

#### **新功能 (Features)**  
- 新增OpenAI平台文件上传功能支持检测方法
- 改进中断信号处理机制，支持中断计数

#### **修复 (Fixes)**  
- 修复用户干预信息拼接格式问题
- 修正补丁应用后的提示信息显示逻辑

#### **优化与重构 (Refactors & Improvements)**  
- 重构全局变量管理代码，改进代码格式和可读性
- 优化中断信号处理逻辑，增加多次中断保护
- 改进代码代理的返回信息提示

#### **文档更新 (Documentation)**  
- 更新代码注释和类型提示

#### **其他 (Miscellaneous)**  
- 调整控制台主题配置格式
- 优化SIGINT信号处理逻辑

本次更新主要改进了中断处理机制和代码可维护性，新增了文件上传功能支持检测，并优化了用户交互体验。

### Release Note - v0.1.191 2025-05-31

#### **新功能 (Features)**  
- 新增角色配置功能，支持从YAML文件加载角色配置并开始对话
- 添加中断处理机制，支持在模型交互期间接收SIGINT信号
- 为平台管理器添加角色子命令(--role/-c)

#### **修复 (Fixes)**  
- 修复了文件分析工具的输出格式，使用<output>和<error>标签包裹
- 修复了set_system_message方法名不一致问题，统一为set_system_prompt

#### **优化与重构 (Refactors & Improvements)**  
- 重构了平台管理器的代码结构，提高可读性
- 移除了默认的addon提示

#### **文档更新 (Documentation)**  
- 更新了工具注册表的输出处理文档
- 添加了角色配置文件的示例说明

#### **其他 (Miscellaneous)**  
- 优化了信号处理逻辑

本次更新主要增强了平台管理器的功能，新增了角色配置支持，并改进了中断处理机制，提高了系统的稳定性和用户体验。

### Release Note - v0.1.190 2025-05-30

#### **新功能 (Features)**  
- 新增预定义任务(pre-command)功能，支持通过YAML文件快速执行常用命令
- 工具生成功能增加自动依赖检查和安装功能

#### **修复 (Fixes)**  
- 修复了工具注册时参数处理的问题
- 移除了已废弃的`jarvis-ask-codebase`功能

#### **优化与重构 (Refactors & Improvements)**  
- 优化了工具生成器的代码结构和错误处理
- 改进了工具注册流程的稳定性
- 增强了工具生成时的依赖管理功能

#### **文档更新 (Documentation)**  
- 更新了README中的预定义任务使用说明
- 完善了工具生成功能的文档

#### **其他 (Miscellaneous)**  
- 更新了微信图片资源

本次更新主要增强了工具的生成和管理能力，特别是新增了预定义任务功能和自动依赖管理功能，同时优化了现有功能的稳定性和用户体验。

### Release Note - v0.1.189 2025-05-29

#### **新功能 (Features)**  
- 新增`support_upload_files()`方法用于检查平台是否支持文件上传
- 新增`generate_summary()`方法用于生成对话历史摘要
- 优化了代码差异文件上传处理逻辑

#### **修复 (Fixes)**  
- 修复了文件上传失败时的错误处理流程
- 修复了`clear_history()`方法的重命名问题
- 修复了平台不支持上传文件时的错误提示

#### **优化与重构 (Refactors & Improvements)**  
- 重构了`GitCommitTool`的代码结构，提取了独立方法
- 优化了文件上传前的平台支持检查
- 改进了大文件处理逻辑

#### **文档更新 (Documentation)**  
- 更新了方法文档字符串
- 完善了错误提示信息

#### **其他 (Miscellaneous)**  
- 调整了`JARVIS_MAX_BIG_CONTENT_SIZE`默认值为160000
- 优化了代码格式和缩进风格

本次更新主要优化了文件上传处理流程，新增了平台支持检查功能，并改进了错误处理机制。

### Release Note - v0.1.188 2025-05-28

#### **新功能 (Features)**  
- 新增RefactorCheckerExpert重构检查专家，用于检查重构后的代码逻辑是否与原代码完全一致

#### **修复 (Fixes)**  
- 修复了文件输入处理器中文件引用解析的问题，防止有其他引号干扰文件路径解析
- 修复了edit_file工具中补丁应用失败的问题，现在会自动尝试增加1-16个空格缩进重试匹配

#### **优化与重构 (Refactors & Improvements)**  
- 重构了jarvis_agent的初始化逻辑，调整了输入处理器的执行顺序
- 优化了文件输入处理器的中文注释和错误处理
- 去除了main.py中的交互模式循环结构

#### **文档更新 (Documentation)**  
- 更新了RefactorCheckerExpert的详细工作流程文档
- 完善了file_input_handler的中文参数说明

#### **其他 (Miscellaneous)**  
- 改进了edit_file工具的错误提示信息，现在会显示更详细的匹配失败原因

本次更新主要增强了代码重构检查能力，改进了文件处理逻辑，并优化了用户体验。

### Release Note - v0.1.187 2025-05-27

#### **修复 (Fixes)**  
- 修复了config参数从必选改为可选(main.py)
- 修复了对话长度计算逻辑(__init__.py)

#### **优化与重构 (Refactors & Improvements)**  
- 优化了模型响应处理流程(__init__.py)
- 改进了文件上传后的提示信息(__init__.py)

### Release Note - v0.1.186 2025-05-27

#### **新功能 (Features)**  
- 新增支持通过`-f/--config`参数指定自定义配置文件路径
- 添加对`-c/--agent_definition`参数的支持，用于指定代理定义文件

#### **修复 (Fixes)**  
- 修复文件编辑工具中文件路径处理问题，现在使用绝对路径

#### **优化与重构 (Refactors & Improvements)**  
- 重构`init_env`函数，支持通过参数传递配置文件路径
- 优化配置文件加载逻辑
- 改进HuggingFace模型解压路径处理

本次更新主要增强了配置管理功能，改进了初始化流程，并修复了文件路径处理相关的问题。

### Release Note - v0.1.185 2025-05-26

#### **新功能 (Features)**  
- 推荐腾讯元宝作为首选平台，优化了平台适配性
- 新增文件上传功能，支持在Agent初始化时自动上传文件
- 扩展通义平台支持的文件类型，新增对多种图片格式的支持

#### **修复 (Fixes)**  
- 修复了文件处理工具中的文件存在性检查逻辑
- 修复了补丁应用失败时的错误信息显示问题
- 修复了工具调用格式错误的提示信息

#### **优化与重构 (Refactors & Improvements)**  
- 优化了README文档中的平台推荐说明
- 重构了文件上传处理流程，提升稳定性
- 改进了补丁应用的错误处理机制

#### **文档更新 (Documentation)**  
- 更新了README中的配置说明，明确推荐腾讯元宝平台
- 完善了工具调用格式错误的帮助信息

本次更新主要增强了文件处理能力和平台适配性，优化了用户体验和错误处理机制。

### Release Note - v0.1.184 2025-05-26

#### **新功能 (Features)**
- 添加文件上传进度指示和错误处理
  - 在文件上传过程中增加了进度指示，并改进了错误处理机制。
- 添加系统消息初始化功能
  - 增加了系统消息支持，以提升对话初始化的功能。

#### **代码优化与修复 (Code Refinement & Fixes)**
- 移除了生成新工具时的代码验证和处理步骤，直接写入原始工具代码。
  - 这简化了工具生成流程，但可能要求用户提供更规范的输入代码。

本次更新主要优化了文件上传的用户体验，并增加了系统消息的支持，以提升对话初始化的功能。

#### **新功能 (Features)**  
- 新增通义千问平台支持，包含四种模型类型：Normal, Thinking, Deep-Research, Code-Chat
- 添加通义千问cookies获取指南和配置说明文档
- 新增通义千问平台实现文件(src/jarvis/jarvis_platform/tongyi.py)

#### **修复 (Fixes)**  
- 修复Yuanbao平台中思考模式消息处理逻辑
- 修复Kimi平台模型名称返回问题

#### **优化与重构 (Refactors & Improvements)**  
- 优化平台注册表中不再需要的set_suppress_output方法
- 统一各平台思考模式消息处理格式

#### **文档更新 (Documentation)**  
- 更新README.md添加通义千问平台配置说明
- 添加通义千问cookies获取图示(docs/images/tongyi.png)

本次更新主要新增了对通义千问平台的支持，提供了完整的平台实现和配置文档，并优化了现有平台的消息处理逻辑。

### Release Note - v0.1.182 2025-05-25

#### **新功能 (Features)**  
- 新增文件输入处理功能 (file_input_handler.py)
- 新增用户数据存储功能 (__init__.py)
- 新增文件内容读取时的用户数据跟踪功能 (file_operation.py, read_code.py)

#### **修复 (Fixes)**  
- 修正git diff命令参数错误 (pre-command)
- 修复文件操作工具中的边界条件问题 (file_operation.py)

#### **优化与重构 (Refactors & Improvements)**  
- 优化编辑工具的核心逻辑 (edit_file.py)
- 改进代码阅读工具的输出格式 (read_code.py)
- 重构系统提示标签格式 (__init__.py)

#### **文档更新 (Documentation)**  
- 更新jarvis_agent模块的初始化文档 (__init__.py)

本次更新主要增强了文件处理能力和用户数据管理功能，同时优化了核心工具的性能和稳定性。新增的文件输入处理功能可以智能识别文件引用并自动读取内容，用户数据存储功能为工具间数据共享提供了便利。

### Release Note - v0.1.181 2025-05-24

#### **主要变更**
1. **文档清理**
- 移除了所有过时的文档图片和markdown文件
- 清理了不再使用的用户文档内容

2. **代码重构**
- 大幅精简了code_agent.py的实现逻辑
- 移除了find_methodology工具及相关代码
- 优化了配置系统，使用原生布尔类型替代字符串配置
- 重构了git工具函数到专用模块

3. **功能调整**
- 移除了ask_codebase工具的全部实现
- 更新了多个工具的默认配置值
- 增强了execute_script工具的功能

4. **其他改进**
- 更新了项目依赖配置
- 优化了多个工具的实现细节
- 清理了不再使用的代码和资源


### Release Note - v0.1.180 2025-05-23

#### **新功能 (Features)**  
- 新增yaml配置文件方式配置替换键值对
- 添加MCP工具配置支持并重构注册逻辑
- 重构配置文件管理逻辑
- Kimi、OpenAI和Yuanbao平台认证配置项使用ENV配置管理
- 添加配置文件schema支持并改进配置文件处理

#### **修复 (Fixes)**  
- 修正自动更新配置默认值
- 修正文件编辑工具中的补丁内容格式化

#### **优化与重构 (Refactors & Improvements)**  
- 将配置文件读取逻辑拆分为独立函数
- 重构环境初始化逻辑以同时支持配置文件和旧版env文件
- 简化命令使用统计逻辑并移除未使用的datetime导入
- 优化MCP配置错误信息的输出内容
- 优化版本检查和更新逻辑
- 优化配置项枚举值的格式并移除未使用的API配置
- 将环境变量配置重构为通用配置系统
- 移除不再使用的旧配置文件引用

#### **文档更新 (Documentation)**  
- 更新配置方式说明并移除废弃方法
- 更新MCP配置文档并调整配置模式
- 更新Yuanbao配置格式
- 更新配置文件格式和路径说明
- 为所有MCP配置模式添加enable字段说明
- 添加流式MCP配置说明

#### **其他 (Miscellaneous)**  
- 添加旧配置文件格式迁移警告
- 移除API密钥未设置时的详细指引信息
- 为所有yaml.safe_dump调用添加allow_unicode参数支持

本次更新主要围绕配置系统进行了全面重构和功能增强，新增了多平台API支持，优化了文档和错误处理机制，并修复了若干关键问题。


### Release Note - v0.1.179 2025-05-22

#### **新功能 (Features)**  
- 添加可流式传输的HTTP MCP客户端实现(StreamableMcpClient)
- 新增lint工具支持并集成到代码修改提示中
- 添加命令使用统计功能
- 添加YAML格式配置文件支持
- 添加任务分析功能支持

#### **修复 (Fixes)**  
- 修改环境变量默认值：JARVIS_USE_METHODOLOGY和JARVIS_USE_ANALYSIS从'true'改为'false'
- 移除不再使用的lsp_get_diagnostics工具

#### **优化与重构 (Refactors & Improvements)**  
- 优化代码结构和导入顺序
- 优化lint工具匹配逻辑并统一文件名大小写处理
- 优化git差异获取功能以包含新增文件
- 优化操作列表的显示格式
- 优化系统提示格式和内容
- 优化提交信息生成提示模板结构

#### **文档更新 (Documentation)**  
- 统一函数文档字符串格式
- 更新README导航链接格式
- 更新配置格式并添加文件路径说明

#### **其他 (Miscellaneous)**  
- 删除空文件aaaa
- 移除不再需要的依赖项(jedi和sseclient)
- 添加tabulate依赖项

本次更新主要增强了配置管理、代码质量检查和统计功能，同时进行了多项代码优化和重构。特别值得注意的是配置系统的改进，包括YAML格式支持和环境变量默认值的调整。


### Release Note - v0.1.178 2025-05-21

#### **新功能 (Features)**  
- 添加方法论分析功能，支持通过配置启用任务分析和方法论生成
- 新增`use_methodology`参数控制方法论的使用
- 增强文件编辑工具功能，支持两种编辑模式和AI辅助编辑

#### **修复 (Fixes)**  
- 修复工具过滤逻辑错误，避免KeyError异常
- 修正生成release note时的git log参数错误
- 移除冗余的错误信息输出和未使用的库导入

#### **优化与重构 (Refactors & Improvements)**  
- 移除整个LSP实现模块，将被新的代码分析架构替代
- 重构文件编辑工具文档，提供更清晰的使用指南
- 更新代码库分析工具的平台配置

#### **文档更新 (Documentation)**  
- 为OpenAIModel类添加详细方法文档
- 在分析步骤中新增要求，确保结论基于实际代码证据
- 更新微信二维码图片

#### **其他 (Miscellaneous)**  
- 修改任务完成提示逻辑，明确禁止输出TOOL_CALL标签
- 清理代码保持简洁性

本次更新主要包含功能增强、错误修复和架构优化，特别是新增了方法论分析功能并重构了文件编辑工具。同时移除了LSP相关模块，为新的代码分析架构做准备。


### 版本发布说明 - v0.1.177 (2025-05-20)

#### ✨ 核心功能增强
1. **全新欢迎系统**
   - 为所有工具添加动态ASCII艺术欢迎界面
   - 实现渐变色彩文本输出效果（蓝→青渐变）
   - 显示版本号和项目链接

2. **代码编辑工具升级**
   - 新增`fast_edit`快速编辑模式
   - 优化`slow_edit`容错机制（3次重试）
   - 增强补丁应用的唯一性检查

3. **统计监控**
   - 新增工具调用次数统计
   - 支持通过`jarvis-tools stat`查看排名
   - 数据持久化存储到`tool_stat.yaml`

#### 🐛 关键修复
1. **稳定性修复**
   - 支持`MAX_TOOL_CALL_COUNT=0`时工具无限调用
   - 解决长文本分块时的最小块大小计算错误
   - 修正Yuanbao平台文件大小显示格式

2. **输出优化**
   - 统一所有错误信息的图标间距
   - 将语法高亮主题从Dracula改为Monokai
   - 优化多行输出的显示逻辑

#### ⚙️ 配置变更
| 配置项 | 原值 | 新值 | 说明 |
|-------|------|------|------|
| MAX_TOKEN_COUNT | 102M | 960K | 降低内存占用 |
| MAX_BIG_CONTENT | 96K | 1M | 支持更大文件处理 |
| MAX_TOOL_CALLS | 20 | 0=∞ | 支持无限调用模式 |

### Release Note - v0.1.176 2025-05-19

#### **新功能 (Features)**
- 无

#### **修复 (Fixes)**
- 修正pre-command文件中git diff命令的格式说明
- 更新JARVIS_MAX_BIG_CONTENT_SIZE配置值
- 添加JARVIS_PRETTY_OUTPUT配置选项

#### **优化与重构 (Refactors & Improvements)**
- 优化文件输入处理逻辑
- 重构平台聊天输出处理
- 改进文本分块处理逻辑

#### **文档更新 (Documentation)**
- 更新README.md中的配置说明

#### **其他 (Miscellaneous)**
- 删除未使用的file_input_handler模块

本次更新主要优化了代码结构和配置选项，移除了不使用的模块，并改进了文本处理逻辑。

### Release Note - v0.1.175 2025-05-17

#### **新功能 (Features)**
- 新增了方法论上传功能，支持将方法论上传到平台
- 在代码代理中添加了静态检查工具支持
- 为Kimi、OpenAI和Yuanbao平台添加了Rich实时输出显示功能
- 在平台管理器中新增对话记录保存功能(/save和/saveall命令)

#### **修复 (Fixes)**
- 修复了pre-command文件中release_note生成步骤的描述
- 移除了jarvis_agent中冗余的print_stream方法
- 修正了工具注册表中的格式说明

#### **优化与重构 (Refactors & Improvements)**
- 优化了多agent系统的消息格式
- 改进了方法论提取和上传逻辑
- 重构了平台交互的输出显示方式

#### **文档更新 (Documentation)**
- 更新了pre-command文档中的指令说明
- 完善了方法论模板格式

#### **其他 (Miscellaneous)**
- 统一了各平台的消息格式规范
- 优化了代码格式和注释

本次更新主要针对平台交互、方法论管理和输出显示进行了全面优化，提升了系统的交互体验和可维护性。


### Release Note - v0.1.174 2025-05-16

#### **修复 (Fixes)**  
- 调整JARVIS_MAX_BIG_CONTENT_SIZE默认值从64000到96000

#### **优化与重构 (Refactors & Improvements)**  
- 优化长文本处理逻辑和token计算方式

本次更新主要优化了文本处理逻辑和token计算方式。

### Release Note - v0.1.173 2025-05-16

#### **修复 (Fixes)**  
- 调整JARVIS_MAX_BIG_CONTENT_SIZE默认值为64000，优化内存使用

本次更新主要优化了系统内存使用效率，将大内容处理默认值调整为更合理的62.5KB。


### Release Note - v0.1.171 2025-05-16

#### **新功能 (Features)**  
- 添加生成ReleaseNote的自动化流程
- 添加长上下文交互时的进度显示
- 新增JARVIS_MAX_BIG_CONTENT_SIZE配置参数
- 改进任务分析流程和工作生成机制
- 重构任务分析提示模板以支持工作生成和版本控制
- 为agent添加基本优先级显示
- 改进release_note生成格式和内容结构  

#### **修复 (Fixes)**  
- 修正ReleaseNote.md文件写入方式为追加导致重复问题
- 修改默认最大内容大小从10MB改为1MB
- 修复上下文丢失时的空响应处理
- 修复自定义回复循环和显示格式问题
- 修复大文件上下文丢失时的错误处理逻辑  

#### **优化与重构 (Refactors & Improvements)**  
- 优化上下文长度过滤编辑逻辑
- 简化对话配置和结果显示模板
- 移除chat_big_content策略并统一为大内容处理编辑逻辑  

#### **文档更新 (Documentation)**  
- 更新release_note生成编辑和重命名文件
- 更新pre-command文档中jgc命令的说明
- 重构发布说明格式和补充细节更新内容  

#### **其他 (Miscellaneous)**  
- 在发布说明中添加当前日期和预期发布时间

本次更新主要改进了发布流程自动化，优化了任务分析机制，并修复了多个关键问题。