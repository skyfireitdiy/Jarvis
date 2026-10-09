# 编排 Python DSL（第 1 层：结构生成）设计文档

> 状态：**已实施**（第 1 层：结构生成）。实现见 `src/jarvis/jarvis_tools/orchestration_dsl.py`、`src/jarvis/jarvis_tools/orchestration_loader.py`。
> 前置讨论：`docs/research/` 三项方案 + 循环编排讨论。
> 目标读者：后续实施者、审阅者。
>
> **重要术语（实施期用户明确）**：DSL 脚本后缀是 **`.flow`**（不是 `.py`）。两种编排文件语义：
>
> - **`.yaml` / `.yml`** = **组织的编排**：批量创建 Agent，不生成 `flow`（不走流水线）。
> - **`.flow`** = **流程的编排**：执行 DSL 脚本生成 DAG，走流水线调度。
>
> 两者都算"编排文件"；后端 `load_orchestration` 与 `parse-orchestration` 通用处理，前端按后缀门控交互。
> 下文历史章节中出现的 `.py` 均指代当前实现的 `.flow` 后缀（保留原文以记录设计演进）。

---

## 1. 背景与目标

### 1.1 现状（已核实的事实）

编排文件当前是 **YAML**（`agents` 定义 + 可选 `flow`），由 `pipeline_runner` 引擎解析为 **DAG（有向无环图）** 并调度执行。

- 引擎：`src/jarvis/jarvis_tools/pipeline_runner.py`
  - `execute()`（:102）读取文件 → `yaml.safe_load`（:131）→ `_build_dag`（:354）→ `_schedule`（:857）。
  - 支持：`depends_on` / `input` / `output` / `when`（受限表达式，:1244）/ `on_error` / `retry` / `gate` / `max_workers`。
  - 环检测：`_topo_sort`（:457），有环直接报错（:450）。
- 解析入口共 **3 处**（重复实现）：
  1. `app.py:10444` `_handle_parse_orchestration_request`（master，前端预览/表单）。
  2. `node_manager.py:1432` `_handle_parse_orchestration_request`（child，跨节点）。
  3. `pipeline_runner.py:131`（真正执行时）。
- 运行入口 2 处（只传文件路径）：`app.py:10590`、`node_manager.py:1610`。
- 前端：`App.vue` 编排弹窗（`parseOrchestrationFile` :13221、`runOrchestration` :13366、`previewOrchestration` :13405）；文件过滤仅 `.yaml/.yml`（`ORCHESTRATE_FILE_EXTENSIONS` :13066）；`dagLayout.js` 按 `dependsOn` 分层布局。
- 产物：`.jarvis/artifacts/<pipeline_id>/`，跨阶段靠 `input`/`output` 路径传递。

### 1.2 痛点

YAML 表达力到顶了。`when` 这种**受限表达式**（白名单、不 eval）就是天花板，它无法表达：

- 按外部数据**动态生成**阶段集合（如"按 C 文件里的函数列表 fan-out"）。
- 复用/组合（把一组阶段定义成可复用单元）。
- 任何需要计算的结构（循环生成 N 个阶段、按条件选择不同子图）。

### 1.3 本方案目标（第 1 层：结构生成）

**让用户用 Python 写编排，但 Python 只负责"生成 DAG 结构"，不参与运行时调度。**

- Python 编排文件执行后，产出的是一份**与现有 `_build_dag` 输出同构的 DAG 数据**。
- 执行引擎、调度、事件、前端可视化、跨节点分发**全部不变**（消费的仍是 DAG 数据）。
- 循环是**编译期展开**（生成时决定有几轮/几个阶段），不是运行时循环。
  - 运行时动态循环（C2Rust 编译失败回炉）**不在本方案范围**，属第 2 层（引擎加 `loop` 原语），另立项。

### 1.4 非目标（明确排除）

- ❌ 运行时动态控制流（loop/while 原语、按运行时结果跳转）。
- ❌ 在编排脚本里直接 `send_to_agent` 等副作用（脚本只声明结构，不执行）。
- ❌ 破坏现有 YAML 编排：YAML 必须继续可用（并存，不替换）。

---

## 2. 核心设计

### 2.1 两阶段模型：加载（执行脚本）→ 调度（消费数据）

```text
编排文件(.flow)  ──执行──▶  DAG 数据(纯结构)  ──▶  _schedule 消费（不变）
     │                        ▲
     └── import jarvis.jarvis_tools.orchestration_dsl（受信库，仅构造器，无副作用）
```

- **加载阶段**：执行 `.flow` 脚本，脚本内用 DSL 构造器声明阶段，脚本跑完 `Pipeline` 对象里就是 DAG 数据。
- **调度阶段**：把 DAG 数据交给现有 `_schedule`，与 YAML 路径**完全一致**。

**关键不变量**：DSL 产出的 DAG 数据结构 = 现有 `_build_dag` 的 `nodes` 结构（字段：`stage/agent/depends_on/input/output/gate/when/retry/on_error`）。这是"引擎零改动"的前提。

### 2.2 受信环境假设

用户明确：**运行环境为受信环境**。因此：

- 编排 `.flow` 与 Jarvis 自身代码同信任级别，**不需要沙箱**。
- 但仍保留一条边界：**脚本只声明结构，不执行副作用**（不派发任务、不写产物）。这是为了**可预览、可跨节点、可可视化**，不是为了安全。

### 2.3 预览语义

预览 = **执行 DSL 脚本拿到 DAG 结构，但不创建 Agent、不派发任务**。这正是现有 `dry_run`（`pipeline_runner.py:175`）的语义：

- YAML：`parse-orchestration` 静态解析出 `nodes`（`app.py:10547`）。
- Python：执行脚本 → 取 `Pipeline.nodes` → 同样的 `nodes` 结构。
- 前端拿到 `nodes` 后行为不变（`previewOrchestration` 已消费 `nodes`）。

### 2.4 跨节点分发

推荐：**分发"执行后的 DAG 数据"，而非脚本本身**。

- 理由：子节点无需安装 DSL 库、无需执行脚本、无需共享脚本文件；只需消费数据。
- 但**执行入口仍传文件路径**（现状如此，`app.py:10590`）。因此有两种落地方式：
  - **方式 1（推荐，改动小）**：子节点也执行脚本（要求子节点有 `jarvis.jarvis_tools.orchestration_dsl`，Jarvis 代码统一分发，天然满足）。脚本路径通过共享文件系统/同机可达。
  - **方式 2（更彻底）**：master 执行脚本得到 DAG 数据后，把**数据**随 `run-orchestration` 请求传给子节点。需要扩展请求协议（新增 `dag` 字段），子节点跳过解析直接用。
- 本方案**默认方式 1**（与现状一致、改动最小）；方式 2 作为可选增强，视跨节点部署形态决定。

---

## 3. DSL 设计

### 3.1 模块位置

新增 `src/jarvis/jarvis_tools/orchestration_dsl.py`（与 `orchestration_loader.py` 同目录，便于统一加载器导入）。

**纯库、无副作用、不依赖引擎**：只提供构造器，把声明累积成 DAG 数据。

### 3.2 最小 API（已实现）

```python
from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage

p = Pipeline()                       # 顶层容器

# 声明阶段（对应 flow 的一项）
p.add(stage("planner", agent="demo_planner", output=".df/plan.md"))
p.add(stage("worker_a", agent="demo_worker_a",
            depends_on=["planner"], input=".df/plan.md", output=".df/a.md"))
p.add(stage("worker_b", agent="demo_worker_b",
            depends_on=["planner"], input=".df/plan.md", output=".df/b.md"))
p.add(stage("aggregator", agent="demo_aggregator",
            depends_on=["worker_a", "worker_b"],
            input=[".df/a.md", ".df/b.md"], output=".df/final.md"))

# agents 定义
p.agent("demo_planner", working_dir=".", task="你是规划器……")
# …其余 agent

# 顶层可选
p.spec("流水线背景……")
p.default_on_error("abort")

# 脚本执行完，p.nodes / p.agents 即 DAG 数据（供引擎消费）
```

### 3.3 用 Python 表达"任意结构"（第 1 层的价值）

```python
# 例：按函数列表 fan-out（YAML 做不到）
funcs = [f.name for f in parse_c_functions("input.c")]   # 任意 Python 逻辑
for fn in funcs:
    p.add(stage(f"translate_{fn}", agent="translator", output=f"out/{fn}.rs"))
    p.add(stage(f"compile_{fn}", agent="builder",
                depends_on=[f"translate_{fn}"], input=f"out/{fn}.rs",
                output=f"build/{fn}.log"))

# 例：编译期展开的"循环"（固定轮次）
for i in range(3):
    p.add(stage(f"pass_{i}", agent="optimizer",
                depends_on=[f"pass_{i-1}"] if i else []))
```

### 3.4 与 YAML 的字段映射

DSL 构造器参数 = YAML `flow` 项的键，一一对应：

| DSL | YAML flow 键 | 说明 |
|---|---|---|
| `stage(name, agent=...)` | `stage` / `agent` | 必填 |
| `depends_on=[...]` | `depends_on` | 缺省 = 上一阶段（线性） |
| `input=...` | `input` | 字符串或列表 |
| `output=...` | `output` | 全局唯一 |
| `gate=True` | `gate` | 门禁 |
| `when="a.b > 0"` | `when` | 受限表达式，语义不变 |
| `retry=3` | `retry` | 单阶段重试 |
| `on_error="abort"` | `on_error` | 失败策略 |

DSL 只做**语法糖**，不引入新语义——保证引擎/前端零改动。

---

## 4. 改动点清单（已实施）

### 4.1 新增

| 文件 | 内容 |
|---|---|
| `src/jarvis/jarvis_tools/orchestration_dsl.py` | DSL 库：`Pipeline` / `stage` / `agent` 等构造器，产出 DAG 数据 |
| `src/jarvis/jarvis_tools/orchestration_loader.py` | **统一加载器** `load_orchestration(path) -> {agents, flow, spec, default_on_error}`：按后缀分发（`.yaml/.yml`→`yaml.safe_load`；`.flow`→执行脚本取结构）。**消除 3 处重复解析** |
| `tests/jarvis_tools/test_orchestration_dsl.py` | DSL 单测：构造 → 产出结构与 `_build_dag` 同构；字段映射；错误处理 |

### 4.2 修改

| 文件:行 | 改动 |
|---|---|
| `pipeline_runner.py` | 移除 `import yaml`，`yaml.safe_load` 改为调用 `load_orchestration(path)`；后续逻辑不变 |
| `app.py` `_handle_parse_orchestration_request` | `yaml.safe_load` 改为 `load_orchestration(path)`（import 放 try 内），异常转 `ORCHESTRATION_PARSE_ERROR`；`has_flow`/`nodes` 逻辑不变 |
| `node_manager.py` `_handle_parse_orchestration_request` | 同上（child 端） |
| `App.vue` `ORCHESTRATE_FILE_EXTENSIONS` | 增加 `.flow`（原 `.yaml/.yml`） |
| `App.vue` 输入框 placeholder | 提示"（.yaml/.yml=组织编排，.flow=流程编排）" |
| `App.vue` `accept` | `accept=".yaml,.yml,.flow"` |
| `App.vue` `parseOrchestrationFile` | `has_flow` 判定按后缀 `.flow` 门控 |
| `pipeline_runner.py` 工具 `description` / 参数描述 | 编排文件支持 YAML/`.flow` DSL |

> 注：`app.py` / `node_manager.py` 中 `import yaml` 仍有其他用途，予以保留。

### 4.3 不动（重要）

- `_build_dag` / `_topo_sort` / `_schedule` / `_run_stage` / `_eval_when`：**完全不动**（消费的是 DAG 数据，与来源无关）。
- `pipeline_events.py`、事件协议、`pipelineStore.js`、`OrchestrationView.vue`、`dagLayout.js`：**完全不动**。
- 产物目录、`pipeline_id` 生成（`_make_pipeline_id` 用文件名 stem，`.flow` 同样适用）：不动。

---

## 5. 加载器设计（关键）

```python
def load_orchestration(path: str) -> dict:
    """按后缀加载编排文件，返回统一结构 {agents, flow, spec, default_on_error}。

    - .yaml/.yml：yaml.safe_load（现状行为）
    - .flow：执行脚本，脚本须定义顶层变量 `pipeline`（Pipeline 实例），
             返回其导出的结构。
    """
    suffix = Path(path).suffix.lower()
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if suffix == ".flow":
        return _load_flow(path)
    raise ValueError(f"不支持的编排文件类型: {suffix}（仅支持 .yaml/.yml/.flow）")
```

`_load_flow` 的约定（**契约**）：

- 脚本执行后，须存在顶层变量 `pipeline`（`Pipeline` 实例）。
- 优先调用 `pipeline.to_dict()`，回退读属性 `agents`/`flow`/`spec_text`/`default_on_error`。
- 脚本**不得有副作用**（不派发任务、不写产物）；约定 + 文档约束（受信环境，不做强制沙箱）。
- 执行方式：在**独立命名空间** `exec` 脚本并捕获异常，返回清晰错误。

**错误处理**：脚本语法错/运行错/缺 `pipeline` 变量 → 抛 `ValueError`（含清晰信息）；调用方（`app.py`/`node_manager.py`）捕获后转 `ORCHESTRATION_PARSE_ERROR`，与现有 YAML 解析失败同构，前端提示一致。

---

## 6. C2Rust 示例（第 1 层能表达的部分）

第 1 层能表达"**编译期已知**的结构"，例如：

```python
# c2rust_pipeline.flow
from jarvis.jarvis_tools.orchestration_dsl import Pipeline, stage
from pathlib import Path

p = Pipeline()
p.spec("把 C 代码翻译为 Rust，逐函数翻译并编译验证。")

# 任意 Python：扫描待翻译函数
funcs = scan_functions("input.c")          # 返回函数名列表

p.agent("translator", working_dir=".", task="把指定 C 函数翻译为 Rust……")
p.agent("builder",    working_dir=".", task="编译 Rust 代码，输出编译日志……")

for fn in funcs:
    p.add(stage(f"translate_{fn}", agent="translator", output=f"out/{fn}.rs"))
    p.add(stage(f"compile_{fn}", agent="builder",
                depends_on=[f"translate_{fn}"],
                input=f"out/{fn}.rs", output=f"build/{fn}.log"))

# 编译期固定轮次的重试（不是运行时循环）
for i in range(2):
    p.add(stage(f"retry_round_{i}", agent="builder",
                depends_on=[f"compile_{f}" for f in funcs] if i == 0
                           else [f"retry_round_{i-1}"]))
```

**第 1 层表达不了的**：`compile_{fn}` 失败后**带着编译错误**回到 `translate_{fn}` 重翻，且**轮次取决于编译结果**——这是运行时循环，属第 2 层。

> 说明：第 1 层已能覆盖"**每个函数独立翻译+编译、最多固定轮**"这类结构，比 YAML 强很多；只有"**运行时才知道要几轮**"的场景才需要第 2 层。

---

## 7. 已确认决策（原待定项）

1. **模块路径**：采用 `jarvis_tools/orchestration_dsl.py`（与 `orchestration_loader.py` 同目录，便于统一加载器导入）。
2. **脚本入口约定**：顶层变量名 `pipeline`（`Pipeline` 实例）。
3. **统一加载器**：本次**已做**，3 处重复解析收敛到 `load_orchestration`。
4. **跨节点分发**：采用方式 1（子节点执行脚本）；Jarvis 代码统一分发，天然满足。
5. **前端模板/生成器**：本次**不做**，仅支持用户手写 `.flow`。
6. **后缀**：`.flow`（非 `.py`）；`.yaml/.yml` 保持组织编排语义。

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 脚本副作用（受信但仍可能误用） | 预览时误执行任务 | 文档强约定"只声明不执行"；DSL 库不提供任何副作用 API |
| 脚本执行失败定位难 | 用户体验差 | 加载器捕获异常并回传 traceback 摘要，前端提示 |
| 3 处解析漂移 | 行为不一致 | 收敛到统一 `load_orchestration` |
| 跨节点无共享存储 | 子节点拿不到脚本 | 预留方式 2（传 DAG 数据），必要时启用 |
| 用户误以为支持运行时循环 | 期望落空 | 文档明确第 1 层边界；第 2 层单独立项 |

---

## 9. 验证方案（实施后）

1. **DSL 单测**：`Pipeline` 构造 → 产出结构与等价 YAML 经 `_build_dag` 的结果**逐字段一致**。✅ 已实现（`tests/jarvis_tools/test_orchestration_dsl.py`，18 用例全过）。
2. **加载器单测**：`.yaml`/`.flow` 两种来源返回同构结构；错误路径（语法错/缺 `pipeline`/不支持后缀）。✅ 已实现。
3. **端到端**：把 `simple_demo.yaml` 改写成等价 `.flow`，跑 dry-run 与真实执行，结果一致。（待补）
4. **前端**：`.flow` 文件可被选择/解析/预览（`has_flow`/`nodes` 正常）。✅ 已实现（`vite build` 通过）。
5. **回归**：现有 YAML 编排全部用例不变；`pipeline_runner` 既有单测全过。✅ 已回归（`ruff` + `pytest` 相关用例全过）。

---

## 10. 与第 2 层的关系

- 第 1 层是第 2 层的**基础**：DSL 库、统一加载器、前端 `.flow` 支持都可复用。
- 第 2 层（引擎加 `loop` 原语）**独立立项**，因为它破坏 DAG 无环假设，牵连 `_build_dag`/`_schedule`/事件协议/`dagLayout.js`。
- 第 1 层实施后，若"运行时循环"需求被证实，再启动第 2 层。

---

## 附：改动影响面速查

```text
新增：
  orchestration_dsl.py        （DSL 库）
  orchestration_loader.py     （统一加载器）
  test_orchestration_dsl.py   （单测，18 用例）

修改：
  pipeline_runner.py          （改用 load_orchestration；工具 description/参数描述）
  app.py                      （_handle_parse_orchestration_request 改用 load_orchestration）
  node_manager.py             （同上，child 端）
  App.vue                     （支持 .flow 后缀、placeholder、accept、has_flow 门控）

不动：
  _build_dag / _topo_sort / _schedule / _run_stage / _eval_when
  pipeline_events.py / pipelineStore.js / OrchestrationView.vue / dagLayout.js
  pipeline_events.py / pipelineStore.js / OrchestrationView.vue / dagLayout.js
```
