# Control everything, schedule everything —— 完备实施方案

> 状态：方案定稿，待按里程碑推进
> 目标：把 Jarvis 从「能控制本地系统 + 基础定时」推进到「控制一切、调度一切」的完整形态
> 原则：基于现有三层架构（前端控制层 / 网关编排层 / 本地守护层）增量演进，不推倒重来

---

## 1. 目标定义

**Control everything**：让系统能对用户机器上的任何事物执行操作——系统、进程、应用、窗口、输入、文件、服务、浏览器、网络、外设、电源，并能**编排多步操作序列**（RPA 式自动化）。

**Schedule everything**：让上述任何操作都能被**按时间、按事件、按条件**自动触发——支持 cron 表达式、一次性/循环、依赖触发、失败重试、结果反馈。

一句话：**任何能力，都可被编排；任何编排，都可被调度。**

---

## 2. 架构总览（现状）

```text
┌─────────────────────────────────────────────────────────────┐
│  前端控制层 (frontend/ Vue)                                   │
│  · 空格序列快捷键 + Ctrl 双轨 · 命令面板 · 弹窗焦点管理          │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS (jvs-ai.cn)
┌───────────────────────────▼─────────────────────────────────┐
│  网关编排层 (jarvis_web_gateway/ Python)                      │
│  · Agent 生命周期 · 节点管理 · 群组/聊天 · 定时任务(TimerManager)│
│  · daemon 会话管理 (capability.list / capability.call)        │
└───────────────────────────┬─────────────────────────────────┘
                            │ WS (jarvis-daemon 子协议)
┌───────────────────────────▼─────────────────────────────────┐
│  本地守护层 (daemon/ Go, 用户机器)                             │
│  · 35 个能力注册表 · DispatchWith(action,params) 分发          │
│  · Windows/Linux 平台能力 · 零第三方依赖                       │
└─────────────────────────────────────────────────────────────┘
```

**关键链路**（已打通并验证）：

- 前端 → 网关 → daemon：指令 `{action, params}` 经 `DispatchWith` 由能力注册表执行（`daemon/internal/handler/dispatch.go`）
- 网关 → daemon：`capability.list` / `capability.call` 两个 HTTP API
- 网关 → 定时：`TimerManager`（`timer_manager.py`）+ `/api/timers`，支持 `run_at` / `delay_seconds` / `interval_seconds`，动作类型 `create_agent` / `run_shell_command`

---

## 3. 现状盘点（基于代码事实）

### 3.1 本地守护层能力（daemon，35 个）

| 域          | 能力                                             | Win | Lin |
| ----------- | ------------------------------------------------ | :-: | :-: |
| system      | `system.info`                                    | ✅  | ✅  |
| process     | `process.list` / `process.kill`                  | ✅  | ✅  |
| app         | `app.list`（已安装应用）                         | ✅  | ❌  |
| gui         | `window.list` / `window.focus` / `window.close`  | ✅  | ❌  |
| input       | `input.click` / `input.type` / `input.keys`      | ✅  | ❌  |
| clipboard   | `clipboard.get` / `clipboard.set` / `screenshot` | ✅  | ❌  |
| script      | `script.exec`                                    | ✅  | ✅  |
| fs          | `fs.read` / `fs.write`                           | ✅  | ✅  |
| service     | `service.list`                                   | ✅  | ❌  |
| transfer    | `fs.transfer.push` / `fs.transfer.pull`          | ✅  | ✅  |
| browser_ext | `browser.ext.status` / `browser.ext.sync`        | ✅  | ✅  |
| ocr         | `ocr.recognize`                                  | ✅  | ✅  |

### 3.2 网关编排层

- Agent：create / send / list / delete / regenerate
- 节点：list / restart / update code
- 群组/聊天：create_group / send_group_message / 私聊
- 定时：`create_timer` / `list_timers` / `get_timer` / `delete_timer`（动作类型仅 2 种）

### 3.3 前端控制层

- 空格序列快捷键（Space p/a/v/n/m）+ Ctrl 双轨，命令面板 30 动作
- 弹窗焦点管理、纯键盘操作
- **无定时任务管理界面**

---

## 4. 差距分析

| 维度             | 现状                      | 目标           | 完成度 |
| ---------------- | ------------------------- | -------------- | :----: |
| 控制-本地系统    | 35 能力（Win 20 / Lin 4） | 全系统         |  ~40%  |
| 控制-浏览器/网页 | 扩展 + eval_js            | 全网页         |  ~60%  |
| 控制-多步自动化  | 无 RPA/录制/宏            | 操作序列       |  ~10%  |
| 调度-定时引擎    | run_at/delay/interval     | 完整 cron      |  ~50%  |
| 调度-动作类型    | 2 种（agent/命令）        | 任意能力       |  ~30%  |
| 调度-事件驱动    | 无                        | 文件/系统事件  |  ~5%   |
| 调度-智能闭环    | 无                        | 反馈/重试/告警 |  ~20%  |
| 编排-可视化      | 无调度界面                | 可视化面板     |  ~10%  |

**综合完成度：约 40%。**

---

## 5. 分阶段实施路线

按「投入产出比」与「依赖关系」排序，分为 6 个里程碑（M1~M6）。每阶段独立可验证、可回退。

---

### M1：定时任务 → 任意 daemon 能力（打通「调度一切」的命脉）

**目标**：让定时任务的动作类型从 2 种扩展到能调用 daemon 的任意能力。
**收益**：立刻获得"每天 9 点打开某窗口 / 定时截图 / 定时清理进程 / 定时同步文件"等真实能力。

**改动点**：

1. `src/jarvis/jarvis_web_gateway/app.py`
   - `_build_timer_action` 增加 `action.type == "capability_call"` 分支
   - 新增 `_build_capability_call_callback(action_params)`：入参 `node_id` / `capability` / `params`，回调内通过现有 daemon `capability.call` HTTP API 下发指令
2. `src/jarvis/jarvis_tools/gateway_manager.py`
   - `_create_timer` 的 `timer_action_type` 枚举增加 `capability_call`
   - 工具 schema 的 `timer_action_params` 描述补充 `capability` / `params` 字段
3. `daemon/` 无需改动（`DispatchWith` 已能执行任意已注册能力）

**验证标准**：

- 新增 `capability_call` 定时任务，`run_at` 设为 5 秒后，目标为 `windows.screenshot`，到点后 daemon 返回截图结果
- `list_timers` / `get_timer` / `delete_timer` 全链路正常
- node 测试 + vitest + build 全绿

---

### M2：cron 表达式支持（真实调度需求）

**目标**：支持"每周一 9 点"、"每天 18:30"等 cron 语义，替代手算 `run_at`/`interval`。

**改动点**：

1. `src/jarvis/jarvis_web_gateway/timer_manager.py`
   - `TimerTask` 增加 `cron_expr: Optional[str]`
   - 新增 `schedule_cron(cron_expr, ...)`；用轻量 cron 解析（`croniter` 或自实现 5 段解析，优先自实现避免新依赖）
   - `_wait_for_next_task` / `_execute_task` 处理 cron 任务的下一触发时间计算
2. `app.py` `_parse_timer_schedule` 增加 `cron` 分支
3. `gateway_manager.py` schema 增加 `schedule.cron`

**验证标准**：

- 创建 `cron: "0 9 * * 1"` 任务，断言 `run_at` 计算为下一个周一 9 点
- 循环 cron 任务在触发后正确推进到下一触发点
- 持久化/重启恢复后 cron 语义不变

---

### M3：前端可视化调度面板（让调度"看得见、管得着"）

**目标**：在界面上创建/查看/启停/删除定时任务，而非仅靠命令。

**改动点**：

1. 新增组件 `src/jarvis/jarvis_service/frontend/src/components/TimerPanel.vue`
   - 列表：任务 ID / 动作类型 / 调度 / 下次触发时间 / 最近结果 / 启停
   - 新建：选动作类型（create_agent / run_shell_command / capability_call）+ 填参数 + 选调度（cron / run_at / interval）
   - 操作：启停 / 删除 / 立即执行一次
2. `App.vue`：新增入口（可挂在 Manage 领域 `Space m t`），弹窗纳入焦点陷阱/恢复体系
3. 复用网关 `/api/timers` + `/api/timers/{id}` 接口；若缺"立即执行/启停"接口则补充

**验证标准**：

- 面板能列出、创建、删除定时任务
- 弹窗自动聚焦 + Tab 陷阱 + 焦点恢复正常
- 新建的 `capability_call` 任务在面板上可见且可操作
- node + vitest + build 全绿

---

### M4：RPA 操作序列（Control everything 的真正形态）

**目标**：录制/编排多步 GUI 操作序列并回放（点这里 → 输入 → 点那里 → 截图校验）。

**改动点**：

1. `daemon/internal/capability/` 新增 `windows_automation_windows.go`
   - `automation.record`：监听鼠标/键盘事件，生成步骤序列（基于 `SetWindowsHookEx`）
   - `automation.replay`：按序列逐步执行（复用现有 `input.click` / `input.type` / `input.keys` 底层）
   - `automation.sequence`：直接接受 JSON 步骤数组执行（无需录制，可由 Agent 生成）
   - 步骤类型：click / type / keys / wait / screenshot / focus / run_script
2. `registry_windows.go` 注册以上能力
3. 网关侧可选：`capability_call` 定时任务可直接调度 `automation.sequence`

**验证标准**：

- 录制一段打开记事本并输入文字的序列，回放后窗口内容正确
- `automation.sequence` 接受 JSON 步骤并逐步执行，中间步骤失败可定位
- 定时任务能调度 `automation.sequence`

---

### M5：事件驱动调度（文件/系统事件触发）

**目标**：支持"当某文件变化时"、"当某进程启动时"等事件触发，而非仅时间触发。

**改动点**：

1. `daemon/internal/capability/` 新增 `windows_events_windows.go`（或跨平台 `fs_watch`）
   - `fs.watch`：基于 `ReadDirectoryChangesW`（Win）/ inotify（Linux）监听目录变化，回调上报网关
   - 事件类型：文件创建/修改/删除/重命名、进程启动/退出（可选）
2. 网关 `TimerManager` 或新增 `EventManager`：接收 daemon 事件上报 → 匹配已注册的"事件→动作"规则 → 触发动作（复用 M1 的 capability_call 链路）
3. `gateway_manager.py` 增加 `create_event_rule` / `list_event_rules` / `delete_event_rule`

**验证标准**：

- 监听目录，创建文件后自动触发一个 `capability_call`（如截图）
- 事件规则可列出/删除，重启后恢复

---

### M6：智能闭环（计划-执行-反馈-重试-告警）

**目标**：让调度任务具备结果校验、失败重试、成功/失败告警，形成自动化闭环。

**改动点**：

1. `timer_manager.py` / 定时回调增加：
   - `retry` 配置（重试次数、间隔、指数退避）
   - `on_success` / `on_failure` 钩子（可指向通知 Agent / 群组消息 / 另一个任务）
   - 结果持久化（成功/失败/耗时/输出摘要）
2. 前端 `TimerPanel` 展示执行历史与下次重试信息
3. 可选：自然语言调度（"每天上午提醒我" → 解析为 cron + 通知动作）

**验证标准**：

- 配置重试的任务在失败后按退避重试，成功则停止
- 失败后按 `on_failure` 向群组发告警
- 执行历史在面板可见

---

## 6. 依赖与顺序

```text
M1 (定时→能力)  ← 一切调度的基础，最先做
M2 (cron)       ← 依赖 M1 的动作框架
M3 (可视化面板)  ← 依赖 M1/M2 的接口
M4 (RPA 序列)   ← 独立，可与 M2/M3 并行
M5 (事件驱动)   ← 依赖 M1 的动作链路 + daemon 事件上报
M6 (智能闭环)   ← 依赖 M1/M3
```

**建议执行顺序**：M1 → M2 → M3 → M4 → M5 → M6（M4 可与 M2/M3 并行推进）。

---

## 7. 风险与注意事项

1. **最小改动**：每阶段独立提交、独立验证，保持随时可回退（当前安全回退点 `7c043685efd88da3c4f80bad1935ff18fa8b01b8`）。
2. **零第三方依赖**：daemon 侧坚持纯 syscall + PowerShell，不引入 cgo/外部工具；cron 解析优先自实现。
3. **安全**：`capability_call` 定时任务涉及在用户机器执行操作，需校验参数、避免越权；事件监听注意隐私边界。
4. **不破坏现有快捷键/焦点体系**：M3 新增弹窗必须纳入焦点陷阱/恢复，不引入新组合键。
5. **测试纪律**：每阶段验证标准明确（node + vitest + build 全绿），绝不用 `npx jest`。

---

## 8. 完成度追踪

| 里程碑        | 状态 | 验证                  |
| ------------- | :--: | --------------------- |
| M1 定时→能力  |  ⬜  | node + vitest + build |
| M2 cron 支持  |  ⬜  | node + vitest + build |
| M3 可视化面板 |  ⬜  | node + vitest + build |
| M4 RPA 序列   |  ⬜  | node + vitest + build |
| M5 事件驱动   |  ⬜  | node + vitest + build |
| M6 智能闭环   |  ⬜  | node + vitest + build |

完成 M1~M6 后，"Control everything, schedule everything" 综合完成度预计从 **40% → 85%+**。
