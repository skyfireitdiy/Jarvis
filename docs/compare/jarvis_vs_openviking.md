# Jarvis vs OpenViking 机制对比分析报告

## 文档信息

- **分析日期**: 2026-09-29
- **分析目标**: 对比 Jarvis 与 OpenViking 在"上下文 / 记忆 / 知识复用"相关机制上的设计与取舍
- **分析范围**: 聚焦两者在**上下文组织、记忆存储与检索、知识/技能复用、会话沉淀、共享协作**等机制层面的异同
- **参考资料**:
  - Jarvis: 源码（`src/jarvis/jarvis_memory_organizer/`、`src/jarvis/jarvis_agent/memory_manager.py`、`src/jarvis/jarvis_tools/memory.py`、`src/jarvis/jarvis_tools/methodology.py`、`src/jarvis/jarvis_agent/rules_manager.py`、`src/jarvis/jarvis_rules_index/core.py`）及 `~/.jarvis/` 实际数据目录
  - OpenViking: 官方文档（docs.openviking.ai / docs.openviking.net）、GitHub 仓库 `volcengine/OpenViking`

> 说明：Jarvis 侧结论均以**当前源码**为准，未采信可能过时的说明文档。

---

## 执行摘要

### 一句话概括

- **Jarvis**：面向开发者的**协作式 AI 开发平台**，其"上下文/记忆"机制是**平台内部的一组能力**（记忆 + 规则 + 方法论 + 技能），强调**轻量、本地、无向量、按需加载**。
- **OpenViking**：面向 AI Agent 的**通用上下文数据库（Context Database）**，把上下文抽象为**独立的存储基础设施**，强调**虚拟文件系统、语义检索、渐进式加载**。

### 核心结论

1. **定位不同**：Jarvis 的机制是"平台内建能力"，服务于自身的开发工作流；OpenViking 是"可被任意 Agent 接入的独立数据层"，服务于所有 Agent 应用。
2. **组织范式不同**：Jarvis 采用**分层 + 分类**（记忆分层 / 规则 / 方法论 / 技能各自独立）；OpenViking 采用**统一虚拟文件系统**（`viking://` 下 Resource/Memory/Skill 三类统一寻址）。
3. **检索路线不同**：Jarvis 是**无向量的轻量检索**（标签 + BM25 + 时间/频率加权）；OpenViking 是**向量语义检索 + 目录感知 + Rerank**。
4. **加载策略相通**：两者都强调"**先看摘要、再读全文**"以节省 token——Jarvis 通过规则按需加载与记忆标签提示实现，OpenViking 通过 L0/L1/L2 三层实现。
5. **共享机制各有侧重**：Jarvis 用**中心 Git 仓库**共享规则/方法论；OpenViking 用**服务端 + 多租户 + ACL**共享上下文。

### 高层概览对比表

| 维度 | Jarvis | OpenViking |
| --- | --- | --- |
| 项目角色 | 协作式 AI 开发平台 | AI Agent 上下文数据库 |
| 上下文机制定位 | 平台内建能力（记忆/规则/方法论/技能） | 独立存储基础设施（可被任意 Agent 接入） |
| 组织模型 | 分层 + 分类，各自独立 | 统一 `viking://` 虚拟文件系统 |
| 存储形态 | 本地 JSON / Markdown 文件 | 服务端 AGFS + 向量索引 |
| 检索方式 | 标签 + BM25 加权，**无向量** | 向量语义检索 + 目录感知 + Rerank |
| 内容加载 | 规则按需加载、记忆标签提示 | L0/L1/L2 渐进式加载 |
| 记忆类型 | 3 类（短期 / 项目长期 / 全局长期） | 9+ 类内置记忆类型 |
| 共享方式 | 中心 Git 仓库 | 服务端多租户 + ACL |
| 技术栈 | Python 3.12（主） | Python / Rust / TypeScript |
| 部署形态 | 本地 CLI / Web / SDK | 独立服务端 + SDK / HTTP API |

---

## 1. 定位与形态对比

### 1.1 项目定位

| 维度 | Jarvis | OpenViking |
| --- | --- | --- |
| **定位** | 协作式 AI 开发平台，覆盖"人 × Agent"四象限协作 | 为 AI Agent 提供统一上下文管理的数据库 |
| **核心场景** | 代码开发、审查、验证、安全分析、C→Rust 迁移 | Agent 跨会话记忆、知识 RAG、技能管理 |
| **形态** | CLI + Web + Python SDK | 独立服务端（`openviking-server`）+ CLI（`ov`）+ SDK |
| **许可证** | MIT | AGPL-3.0（主）/ Apache-2.0（部分组件） |

### 1.2 机制定位差异

- **Jarvis**：上下文机制是**平台自身能力的一部分**。记忆、规则、方法论、技能虽然机制完备，但都**绑定在 Jarvis 平台内**，通过工具（`memory`、`methodology`、`load_rule`）和事件钩子驱动。
- **OpenViking**：上下文机制被**抽离为独立的基础设施**。它本身不产出内容，而是为**任意 Agent**（Claude、Codex、Cursor、LangChain 等）提供统一的"存取上下文"能力，通过 MCP / SDK / HTTP API 接入。

> **一句话理解**：Jarvis 的机制是"**自用**"，OpenViking 的机制是"**通用**"。

---

## 2. 上下文组织模型对比

### 2.1 Jarvis：分层 + 分类，各自独立

Jarvis 的"上下文"由几个**相互独立**的子系统构成，各自有独立的存储目录与工具：

| 子系统 | 存储位置 | 组织方式 | 对应工具 |
| --- | --- | --- | --- |
| **记忆** | `.jarvis/memory/`（项目）、`~/.jarvis/memory/`（全局） | 按类型分层，每条记忆一个 JSON 文件 | `memory` |
| **规则** | `builtin/rules/`、`.jarvis/rules/`、`~/.jarvis/rules/`、中心库 | 按来源分目录，Markdown + YAML front matter | `load_rule`、`auto_select_rule` |
| **方法论** | `~/.jarvis/methodologies/`、`.jarvis/methodologies/` | 按问题类型，MD5 命名 JSON 文件 | `methodology` |
| **技能** | `~/.jarvis/rules/skills/` | 复用规则系统扩展 | 通过规则/输入处理器 |

### 2.2 OpenViking：统一虚拟文件系统

OpenViking 把三类上下文**统一**到 `viking://` 虚拟文件系统下，用**同一套 URI 寻址**：

```
viking://
├── resources/              # 资源：项目文档、代码仓库、网页等
│   └── my_project/
│       ├── docs/
│       └── src/
└── user/{user_id}/
    ├── memories/           # 记忆：偏好、实体、事件、经验等
    │   └── preferences/
    ├── resources/          # 用户私有资源
    ├── skills/             # 技能
    └── peers/{peer_id}/    # Peer 级上下文
```

| 上下文类型 | 用途 | 生命周期 | 发起方 |
| --- | --- | --- | --- |
| **Resource** | 知识与规则（文档、代码仓库） | 长期、相对静态 | 用户添加 |
| **Memory** | Agent 的认知（偏好、实体、事件、经验） | 长期、动态更新 | Agent 记录 |
| **Skill** | 可声明、可调用的能力配置 | 长期、静态 | 用户或系统添加 |

### 2.3 关键差异

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 组织范式 | 分层 + 分类，子系统各自独立 | 统一文件系统，三类上下文统一寻址 |
| 寻址方式 | 文件路径 + 工具参数 | `viking://` 统一 URI |
| 可浏览性 | 需分别查看各目录 | 可像文件系统一样 `ls` / `tree` / `grep` |
| 扩展性 | 新增子系统需新增目录与工具 | 新增类型即新增目录，寻址方式不变 |

---

## 3. 记忆机制对比（重点）

### 3.1 存储结构

**Jarvis**：记忆是**一条一个 JSON 文件**，字段结构固定：

```json
{
  "id": "20260914_165026_146930",
  "type": "project_long_term",
  "tags": ["CPU限制", "cgroup", "systemd", "用户资源限制"],
  "content": "服务器(16核, Ubuntu 20.04, cgroup v1)用户CPU限制方案：...",
  "created_at": "2026-09-14T16:50:26.146957",
  "updated_at": "2026-09-14T16:50:26.146961"
}
```

- 分层：`short_term`（内存）、`project_long_term`（`.jarvis/memory/`）、`global_long_term`（`~/.jarvis/memory/global_long_term/`）
- 组织：**标签（tags）** 是核心索引维度

**OpenViking**：记忆是**Markdown 文件**，按**语义类型**分目录：

| 内置记忆类型 | 默认位置 | 说明 |
| --- | --- | --- |
| profile | `~/memories/profile.md` | 用户基本信息 |
| preferences | `~/memories/preferences/` | 按主题组织的用户偏好 |
| entities | `~/memories/entities/` | 人、项目、组织等实体知识 |
| events | `~/memories/events/` | 决策、里程碑等事件记录 |
| identity | `~/memories/identity.md` | 助手名称、人设、气质 |
| soul | `~/memories/soul.md` | 助手原则、边界、风格 |
| cases | `~/memories/cases/` | 任务案例 |
| trajectories | `~/memories/trajectories/` | 可复用任务执行轨迹 |
| experiences | `~/memories/experiences/` | 从执行结果提炼的可复用经验 |

### 3.2 记忆写入

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 触发方式 | 事件钩子（`TASK_STARTED`/`TASK_COMPLETED`/`BEFORE_HISTORY_CLEAR`）+ 大模型自主判断 | 会话提交（`session.commit()`）后**异步**抽取 |
| 写入主体 | 大模型调用 `memory` 工具主动保存 | 系统按记忆策略自动抽取 |
| 分类粒度 | 3 类（短期/项目长期/全局长期） | 9+ 类语义化类型 |
| 去重/整理 | `MemoryOrganizer` 按**标签重叠**合并 | LLM 驱动的去重（Compressor） |

### 3.3 记忆检索

**Jarvis**：`smart_search` 采用**无向量的加权打分**（源码 `smart_retrieval.py` 核实）：

```
总分 = 内容相似度(BM25) × 0.4
     + 标签匹配度 × 0.3
     + 时间新鲜度 × 0.15
     + 使用频率 × 0.15
```

- 分词：`jieba`（中文分词）
- 相似度：**BM25**（非向量）
- 候选：先按扩展标签过滤，再打分排序
- 注意：`~/.jarvis/embeddings/` 目录为空，**证实 Jarvis 记忆检索不依赖向量嵌入**

**OpenViking**：采用**向量语义检索 + 目录感知**：

```
Query → 意图分析 → 分层检索（目录级递归）→ Rerank → 结果
```

- 检索方式：`find`（无会话上下文）/ `search`（结合会话上下文）
- 核心：**目录作用域检索**（可限定到某个项目/记忆子树，而非扫描整个向量池）
- 精排：标量过滤 + 模型 Rerank

### 3.4 关键差异

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 检索基础 | 标签 + BM25（**词法**） | 向量（**语义**） |
| 检索范围 | 按类型/标签过滤 | 目录作用域 + 全库 |
| 精排 | 加权打分 | 模型 Rerank |
| 依赖 | 无外部模型/索引 | 需 embedding 模型 + 向量索引 |
| 优点 | 轻量、离线、零依赖 | 语义理解强、跨语言/同义召回好 |
| 代价 | 语义泛化弱（依赖标签质量） | 需维护向量索引与模型服务 |

---

## 4. 渐进式加载 / Token 优化对比

两者都强调"**先看摘要、再读全文**"，但实现路径不同：

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 核心手段 | 规则按需加载（`load_rule`/`auto_select_rule`）、记忆标签提示 | L0/L1/L2 三层渐进加载 |
| 摘要生成 | 规则自带 YAML `description` | 目录自动生成 `.abstract.md`(L0) / `.overview.md`(L1) |
| 加载粒度 | 规则级（整条规则）、记忆级（整条记忆） | 目录级 + 文件级 |
| Token 控制 | 规则正文限长（`_limit_rule_body`）、记忆条数上限 | L0 约 256 字符、L1 约 4000 字符、L2 按需 |

**OpenViking 三层模型**：

| 层 | 内容 | 默认上限 |
| --- | --- | --- |
| L0 | 一句话摘要，快速相关性判断 | 256 字符 |
| L1 | 概览，用于导航 | 4000 字符 |
| L2 | 完整原文，按需读取 | 无统一限制 |

> **相通点**：都认识到"全量塞入上下文"不可持续，均采用"**元信息先行、按需展开**"策略。
> **差异点**：Jarvis 的摘要依赖**人工/规则编写**，OpenViking 的摘要由**系统自动生成**（语义处理阶段）。

---

## 5. 知识与技能复用对比

### 5.1 Jarvis：规则系统 + 方法论 + 技能

- **规则系统**：Markdown + YAML front matter，支持多来源（内置/项目/全局/中心库/配置目录），支持 Jinja2 模板渲染，**按需加载**。规则系统是一套"**元机制**"，可扩展出 skill、spec 等能力。
- **方法论**：把"成功解决问题的解法"沉淀为可复用库，按**问题类型**索引（MD5 命名），支持项目级/全局级，可通过**中心 Git 仓库**共享。
- **技能**：通过规则系统扩展，支持从 Git 仓库或本地路径安装。

### 5.2 OpenViking：Skill 作为一等上下文

- **Skill** 是三类上下文之一，与 Resource、Memory **平级**，统一用 `viking://` 寻址。
- 存储结构标准化：`SKILL.md`（定义）+ `.abstract.md`/`.overview.md`（摘要）+ `scripts`（实现）。
- 作用域：用户私有（`viking://~/skills/`）或全局共享（`viking://agent/skills/`）。
- 扩展方向：Skill 属于 `AgentDefinedContextType`，同类还规划了 Endpoint / Tool / Payment 等子类型。

### 5.3 关键差异

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 知识复用载体 | 规则 + 方法论（两个独立系统） | Resource + Skill（统一上下文） |
| 技能地位 | 规则系统的扩展 | 一等上下文类型 |
| 共享方式 | 中心 Git 仓库 | 服务端多租户 + 作用域 URI |
| 元信息 | YAML front matter（人工编写） | 自动生成 L0/L1 摘要 |

---

## 6. 会话沉淀与记忆抽取对比

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 会话载体 | 对话历史（`~/.jarvis/history`、`dialogues`） | Session（服务端管理） |
| 沉淀触发 | 任务开始/完成/清空历史时的事件钩子 | `session.commit()` 显式提交 |
| 抽取方式 | 大模型判断后调用 `memory` 工具 | 后台任务异步抽取（可轮询状态） |
| 抽取产物 | JSON 记忆条目 | Markdown 记忆文件（按类型分目录） |
| 可观测性 | 记忆文件可直接查看 | 记忆文件可直接查看/编辑，且有 `ov compile` 可整理成 wiki/知识图谱 |

> **相通点**：都支持把"会话"转化为"可复用的长期记忆"，且产物都是**人类可读的文件**。
> **差异点**：Jarvis 是**事件驱动 + 模型自主**，OpenViking 是**显式提交 + 异步流水线**。

---

## 7. 共享与协作机制对比

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 共享单元 | 规则、方法论 | 全部上下文（Resource/Memory/Skill） |
| 共享方式 | 中心 Git 仓库（`central_rules_repo` 等） | 服务端多租户 + 作用域 URI |
| 权限模型 | 多用户认证（JWT）+ 分组权限 + ACL | 账号/用户隔离 + 可选资源 ACL |
| 隔离维度 | 项目级 / 全局级 | 用户级 / Peer 级 / Agent 级 |
| 冲突处理 | 中心仓库优先级最高 | 由服务端统一管理 |

> **差异本质**：Jarvis 的共享是"**文件 + Git**"的去中心化模式；OpenViking 的共享是"**服务端 + 数据库**"的中心化模式。

---

## 8. 技术栈与部署对比

| 对比点 | Jarvis | OpenViking |
| --- | --- | --- |
| 主要语言 | Python 3.12 | Python 74.8% / Rust 12.4% / TypeScript 8.7% |
| 运行形态 | 本地 CLI / Web / SDK | 独立服务端 + SDK / HTTP API |
| 数据存储 | 本地文件（JSON/Markdown） | AGFS（内容）+ 向量索引 |
| 外部依赖 | 无向量依赖，可选大模型 | 需 embedding 模型 + VLM |
| 部署复杂度 | 低（本地运行） | 中（需部署服务端与模型） |
| 离线能力 | 强（本地文件即可） | 需本地模型或联网 |

---

## 9. 综合对比与互补性分析

### 9.1 机制对比总表

| 机制维度 | Jarvis | OpenViking | 关系 |
| --- | --- | --- | --- |
| 上下文组织 | 分层 + 分类，各自独立 | 统一虚拟文件系统 | 互补 |
| 记忆存储 | JSON 文件，标签索引 | Markdown 文件，类型分目录 | 相似（皆文件化） |
| 记忆检索 | 标签 + BM25，无向量 | 向量 + 目录感知 + Rerank | 互补 |
| 渐进加载 | 规则按需加载 | L0/L1/L2 三层 | 相通 |
| 知识复用 | 规则 + 方法论 | Resource + Skill | 互补 |
| 会话沉淀 | 事件驱动 + 模型自主 | 显式提交 + 异步抽取 | 相通 |
| 共享协作 | 中心 Git 仓库 | 服务端多租户 + ACL | 互补 |
| 部署形态 | 本地轻量 | 服务端 + 模型 | 互补 |

### 9.2 各自的优势与边界

**Jarvis 的优势**：
- 轻量、本地、零向量依赖，离线可用
- 与开发工作流深度绑定（规则/方法论直接服务于编码任务）
- 记忆/规则/方法论产物均为人类可读文件，透明可控

**Jarvis 的边界**：
- 检索以词法（BM25）为主，语义泛化能力有限，强依赖标签质量
- 上下文机制为平台自用，难以被外部 Agent 直接复用
- 共享依赖 Git，缺少服务端级的权限与多租户能力

**OpenViking 的优势**：
- 语义检索能力强，跨语言/同义召回好
- 统一文件系统 + 目录感知检索，组织与检索一体
- 服务端化，天然支持多租户、ACL、跨语言接入

**OpenViking 的边界**：
- 需部署服务端与 embedding/VLM 模型，依赖较重
- 是通用数据层，不直接提供开发工作流能力
- 主协议 AGPL-3.0，商用需注意许可

### 9.3 互补性与借鉴点

1. **检索能力可互补**：Jarvis 若引入向量检索（或对接 OpenViking 类服务），可提升记忆/方法论的语义召回能力。
2. **渐进加载可借鉴**：OpenViking 的 L0/L1/L2 自动摘要机制，可为 Jarvis 的记忆/规则自动生成摘要，减少人工维护成本。
3. **统一寻址可借鉴**：OpenViking 的 `viking://` 统一 URI，可为 Jarvis 的分散子系统提供统一寻址范式。
4. **共享机制可互补**：Jarvis 的中心 Git 仓库适合离线/去中心化场景，OpenViking 的服务端模式适合团队在线协作。
5. **定位不同，非替代关系**：Jarvis 是"开发平台"，OpenViking 是"上下文基础设施"，二者可在不同层次协同。

---

## 10. 结论

1. **两者不在同一层次**：Jarvis 的上下文机制是**平台内建能力**，OpenViking 是**通用上下文基础设施**，属于"应用"与"底座"的关系。
2. **组织范式迥异**：Jarvis 是"分层 + 分类"，OpenViking 是"统一虚拟文件系统"。
3. **检索路线分野**：Jarvis 走**轻量无向量的词法路线**，OpenViking 走**向量语义 + 目录感知路线**，各有取舍。
4. **加载理念相通**：两者都强调"摘要先行、按需展开"，是应对上下文膨胀的共同选择。
5. **互补大于竞争**：在检索增强、自动摘要、统一寻址、共享协作等方向，Jarvis 可从 OpenViking 的设计中获得借鉴。

---

## 附录：信息来源

### Jarvis（源码核实）

| 机制 | 关键源码/数据位置 |
| --- | --- |
| 记忆工具 | `src/jarvis/jarvis_tools/memory.py` |
| 记忆管理 | `src/jarvis/jarvis_agent/memory_manager.py` |
| 记忆整理 | `src/jarvis/jarvis_memory_organizer/memory_organizer.py` |
| 智能检索 | `src/jarvis/jarvis_memory_organizer/smart_retrieval.py` |
| 方法论工具 | `src/jarvis/jarvis_tools/methodology.py` |
| 规则管理 | `src/jarvis/jarvis_agent/rules_manager.py` |
| 规则索引 | `src/jarvis/jarvis_rules_index/core.py` |
| 记忆数据 | `~/.jarvis/memory/global_long_term/*.json` |
| 方法论数据 | `~/.jarvis/methodologies/*.json` |

### OpenViking（官方资料）

- 官网：<https://www.openviking.ai/>
- 文档：<https://docs.openviking.ai/>
- GitHub：<https://github.com/volcengine/OpenViking>
- 架构文档：Architecture Overview / Context Types / Context Layers / Sessions

---

*本报告基于 2026-09-29 的源码与官方文档整理，Jarvis 侧结论以当前源码为准。*
