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