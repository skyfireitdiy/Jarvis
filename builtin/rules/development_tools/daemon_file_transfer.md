---
name: daemon_file_transfer
description: 当需要在两台机器（尤其是 jarvis-daemon 之间，如 NAS↔PC）之间搬运文件时触发。每当用户提及"传文件到某机器"、"把文件下载/上传到某设备"、"跨机传文件"、"fs.transfer.push/pull"、"daemon 之间传文件"、"把文件放到桌面"时触发。不触发：同一台机器内复制文件（用 fs.read/write 或 shell cp）；仅读取远端文件内容（用 fs.read）；Web 上传下载（用 browser_ext）。
---

# 跨机文件传输（fs.transfer.push / pull）操作指南

## 规则简介

`fs.transfer.push` / `fs.transfer.pull` 是 jarvis-daemon 提供的**跨机文件直传**能力：daemon 内部循环分块，字节只在 daemon 与网关之间流动，**不经过 Agent 上下文**，因此搬运大文件也不会撑爆上下文，只返回摘要（路径、大小、sha256）。

本规则记录正确用法与全部已知坑，避免重复踩。

## 你必须遵守的原则

### 1. 认清传输拓扑：daemon ↔ **agent 节点**，不是 daemon ↔ daemon

**这是最容易搞错的一点。**

数据通路是：

```text
本机 daemon --(HTTP, 带网关 Token)--> 网关 /api/node/{node_id}/file-transfer/{upload|download}
                                        --(WebSocket)--> 目标节点落盘/打包
```

`node_id` 必须是**网关侧注册的 agent 节点**（`gateway_manager(action="list_nodes")` 能列出的，如 `master`、`worker-83`、`sf-pc`），**不是 daemon 会话的 client_id**。

**禁止**把 `daemon(action="list_sessions")` 返回的 `client_id` / `node_id`（形如 `daemon-hinas-11408`）当 `node_id` 传给 push/pull——网关查不到该节点，会返回 **HTTP 502 `Node xxx not found`**。

**判断方法**：`node_id` 只能取自 `gateway_manager(action="list_nodes")` 的 `nodes[].node_id`。

### 2. daemon ↔ daemon 传文件：用「agent 节点中转」两步法

当两台机器都是 daemon（例如家用 NAS 与 PC），**没有** daemon 直连通道。正确做法是借一个双方都能访问的 agent 节点中转：

**步骤 A（源机 push 到中转节点）：**

```text
daemon(action="call", session_id="<源机 sid>", name="fs.transfer.push",
       params={"gateway":"https://jvs-ai.cn:4443",
               "node_id":"master",              # 必须是 agent 节点
               "local_path":"/源机/路径/文件.jpg",
               "remote_path":"文件.jpg",         # 收敛到中转节点 ~/.jarvis/transfers/
               "mode":"file",
               "chunk_size":524288},             # 见第 3 条，必须 <=524288
       timeout=120)
```

**步骤 B（目标机从同一中转节点 pull）：**

```text
daemon(action="call", session_id="<目标机 sid>", name="fs.transfer.pull",
       params={"gateway":"https://jvs-ai.cn:4443",
               "node_id":"master",              # 与步骤 A 同一个节点
               "remote_path":"文件.jpg",         # 与步骤 A 的 remote_path 一致
               "local_path":"C:\\Users\\xxx\\Desktop\\文件.jpg",
               "mode":"file",
               "chunk_size":524288},
       timeout=120)
```

**要点**：

- 两步的 `gateway`、`node_id`、`remote_path`、`mode` 必须一致。
- 中转节点上文件落在 `~/.jarvis/transfers/<remote_path>`（绝对路径会去根保留结构）。
- 完成后建议清理中转节点上的残留文件（用该节点的 shell 能力 `rm`）。

**方向辨析（务必先分清，最容易搞反）**：

- `fs.transfer.push` = **「发起方本机 → 指定远端节点」**。`local_path` 是**发起方本机**的文件，`remote_path` 是**远端节点**上的落点。
- `fs.transfer.pull` = **「指定远端节点 → 发起方本机」**。`remote_path` 是**远端节点**上的文件，`local_path` 是**发起方本机**的落点。
- 记忆法：**`local` 永远指发起方本机，`remote` 永远指 `node_id` 那个节点**；push 是"推出去"（本机→远端），pull 是"拉进来"（远端→本机）。
- 谁发起就由谁的 `session_id` 调用：**要往哪台机器放文件，就在那台机器的 daemon 会话上发起**（放进去用 push，从别处取用 pull）。
- 常见错法：想"把 A 机文件送到 B 机"，却在 A 机上调 `pull`（方向反了）——正确是 **A 机 push 到中转节点，B 机 pull**（见第 2 节两步法）。

### 3. chunk_size 必须 <= 524288（512 KiB）——否则 413

网关前面的 **nginx 默认 `client_max_body_size` 为 1 MB**，而分块内容以 base64 传输（膨胀约 4/3）。daemon 默认块大小是 **1 MiB**，base64 后约 1.4 MB，**必然被 nginx 拒绝**，报：

```text
413 Request Entity Too Large (nginx)
```

**必须显式传 `chunk_size`，且满足：`chunk_size * 4/3 < 1 MB`，即 `chunk_size <= ~750 KB`。**

**推荐值 `524288`（512 KiB，base64 后约 683 KB）**，安全且往返次数可接受。

> 若误用默认值看到 413，不要怀疑 daemon 或网络，直接改小 `chunk_size` 重试。

### 4. gateway 必须是 daemon 已认证的**精确地址（含端口）**

daemon 按 `hostname:port` 索引凭据（`GatewayKey`）。`https://jvs-ai.cn` 与 `https://jvs-ai.cn:4443` 是**两个不同的网关**。

若报「网关 xxx 没有可用凭据，无法发起直传」，说明该 daemon 认证的网关地址与你传的不一致。

**取正确地址的方法**：查该 daemon 的日志（Linux `~/.jarvis/logs/daemon.log`、Windows `C:\Users\<user>\.jarvis\logs\daemon.log`），找形如：

```text
[localapi] 收到认证推送: gateway=https://jvs-ai.cn:4443 token=... name="SF-PC"
```

**照抄日志里的 gateway 原值**（含端口），不要自行省略端口。

### 5. 工具调用 timeout 必须放大到 120s

`daemon(action="call")` 默认超时 30s。跨公网分块传输较慢（实测 5 MB 文件约 35s，10 块），**默认超时会误报 `capability call timed out`**，但传输可能仍在后台进行或已被中止。

**必须显式传 `timeout=120`**（大文件可再放大）。

> 超时后**不要立刻重试**——先查目标文件是否已落地（见第 6 条），避免重复传输。

### 6. 完成后必须校验

用摘要里的 `sha256` 与两端实际文件比对，确认完整性：

```text
# 源机（Linux）
sha256sum /源机/路径/文件.jpg

# 目标机（Windows）
(Get-FileHash 'C:\...\文件.jpg' -Algorithm SHA256).Hash
```

push/pull 返回的 `sha256` 字段即整包 SHA-256，两端应完全一致（Windows 侧大小写不敏感）。**校验通过才算成功**，不要只看命令没报错就宣称完成。

## 常见错误速查

| 现象                                | 原因                                              | 处理                                               |
| ----------------------------------- | ------------------------------------------------- | -------------------------------------------------- |
| `HTTP 502 Node xxx not found`       | `node_id` 传了 daemon 的 client_id                | 改用 `list_nodes` 里的 agent 节点 id               |
| `HTTP 413 Request Entity Too Large` | `chunk_size` 过大（默认 1 MiB）                   | 显式传 `chunk_size=524288`                         |
| `网关 xxx 没有可用凭据`             | gateway 地址与 daemon 认证的不一致（端口不同）    | 查 daemon 日志，照抄含端口的 gateway               |
| `capability call timed out`         | 工具默认 30s 超时太短                             | 传 `timeout=120`；先查文件是否已落地再决定是否重试 |
| 文件在源机找不到                    | `remote_path` 被收敛到节点 `~/.jarvis/transfers/` | 用相对路径，或按去根结构推算实际落点               |

## 完整实例：NAS 照片 → Windows 桌面（真机实测，2026-09-27）

**场景**：把 NAS（hinas，Linux）上的 `/mnt/sdb1/pictures/香蕉派照片/IMG20230827095833.jpg`（约 5 MB）传到 SF-PC（Windows）的桌面。两台机器都是 daemon，**没有直连通道**，需借 agent 节点 `master` 中转。

### 第 1 步：盘点环境

```text
gateway_manager(action="list_nodes")
# → 返回 agent 节点列表，取 node_id="master"（这是网关侧注册的节点，不是 daemon）

daemon(action="list_sessions")
# → 返回所有 daemon 会话，取两个：
#   源机 NAS：  session_id="daemon-hinas-11408"  （注意：这是 daemon 的 client_id，绝不能当 node_id 用！）
#   目标机 PC： session_id="daemon-SF-PC-35748"
```

### 第 2 步：源机（NAS）push 到中转节点 master

```text
daemon(action="call", session_id="daemon-hinas-11408", name="fs.transfer.push",
       params={"gateway": "https://jvs-ai.cn:4443",
               "node_id": "master",                       # agent 节点，不是 daemon
               "local_path": "/mnt/sdb1/pictures/香蕉派照片/IMG20230827095833.jpg",
               "remote_path": "IMG20230827095833.jpg",    # master 上 ~/.jarvis/transfers/ 下的相对路径
               "mode": "file",
               "chunk_size": 524288},
       timeout=120)
# 实测：耗时约 15.7s，分 10 块；返回 size=5178920, sha256=8c87abdf01396f00...
```

### 第 3 步：目标机（SF-PC）从同一节点 master pull 到桌面

```text
daemon(action="call", session_id="daemon-SF-PC-35748", name="fs.transfer.pull",
       params={"gateway": "https://jvs-ai.cn:4443",          # 与第 2 步完全一致
               "node_id": "master",                          # 与第 2 步完全一致
               "remote_path": "IMG20230827095833.jpg",       # 与第 2 步 remote_path 一致
               "local_path": "C:\\Users\\skyfire\\Desktop\\IMG20230827095833.jpg",
               "mode": "file",
               "chunk_size": 524288},
       timeout=120)
# 实测：耗时约 35.5s，分 10 块
```

### 第 4 步：校验（两端 sha256 必须一致）

```text
# NAS 侧
sha256sum "/mnt/sdb1/pictures/香蕉派照片/IMG20230827095833.jpg"
# Windows 侧（在 SF-PC 的 daemon 上跑）
daemon(action="call", session_id="daemon-SF-PC-35748", name="windows.script.exec",
       params={"interpreter": "powershell",
               "script": "(Get-FileHash 'C:\\Users\\skyfire\\Desktop\\IMG20230827095833.jpg' -Algorithm SHA256).Hash"})

# 实测结果：两端均为
#   8C87ABDF01396F00DF2FF6A881D13E7036C58B93AA12578ECA497399F2BB1246
#   大小 5178920 字节 —— 完全一致，传输成功
```

### 第 5 步：清理中转节点上的残留文件

```text
# master 上文件落在 ~/.jarvis/transfers/IMG20230827095833.jpg，用完删掉
gateway_manager(action="exec_command", node_id="master",
                command="rm -f ~/.jarvis/transfers/IMG20230827095833.jpg")
```

**这个实例踩过的坑（都已写进上文对应小节）**：

1. 一开始把 `daemon(action="list_sessions")` 返回的 `daemon-hinas-11408` 当 `node_id` 传 → **HTTP 502 `Node daemon-hinas-11408 not found`**。正解：`node_id` 只能取 `list_nodes` 的 agent 节点（`master`）。
2. 未传 `chunk_size`，用默认 1 MiB → **HTTP 413**。正解：显式传 `524288`。
3. 工具默认 `timeout=30`，5 MB 文件耗时 35s → 误报 `capability call timed out`。正解：传 `timeout=120`。
4. `gateway` 一开始写 `https://jvs-ai.cn`（无端口）→ 报「没有可用凭据」。正解：照抄 daemon 日志里的 `https://jvs-ai.cn:4443`。

## 能力参数速查

| 能力               | 方向            | 必填参数                                          | 关键返回                   |
| ------------------ | --------------- | ------------------------------------------------- | -------------------------- |
| `fs.transfer.push` | 本机 → 远端节点 | `gateway`、`node_id`、`local_path`、`remote_path` | `size`、`sha256`、`chunks` |
| `fs.transfer.pull` | 远端节点 → 本机 | `gateway`、`node_id`、`local_path`、`remote_path` | `size`、`sha256`、`chunks` |

公共可选参数：`mode`（`file`/`dir`，缺省按 `local_path` 类型推断）、`chunk_size`（**务必传 524288**）。单次上限 512 MiB。
