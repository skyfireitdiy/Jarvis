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