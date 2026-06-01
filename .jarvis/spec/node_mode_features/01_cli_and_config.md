# 01 CLI 参数与配置解析详细设计

## 1. 功能目标

为 `jarvis-web-gateway` 与 `jarvis-service` 增加 node 模式相关参数与配置解析能力，形成统一运行时配置对象，供后续启动流程与节点连接逻辑使用。

本功能点只负责“配置进入系统”的问题，不负责节点连接、认证或代理本身。

## 2. 影响模块

- `src/jarvis/jarvis_web_gateway/cli.py`
- `src/jarvis/jarvis_service/cli.py`
- `src/jarvis/jarvis_web_gateway/app.py`
- 建议新增：`src/jarvis/jarvis_web_gateway/node_config.py`

## 3. 输入/输出

### 3.1 输入

#### gateway CLI 输入

- `--node-mode <master|child>`
- `--node-id <string>`
- `--master-url <string>`
- `--node-secret <string>`

#### service 配置输入

- `JARVIS_NODE_MODE`
- `JARVIS_NODE_ID`
- `JARVIS_MASTER_URL`
- `JARVIS_NODE_SECRET`

### 3.2 输出

统一运行时配置对象 `NodeRuntimeConfig`，至少包含：

- `node_mode`
- `node_id`
- `master_url`
- `node_secret`
- `is_master`
- `is_child`

## 4. 数据结构

```python
class NodeRuntimeConfig:
    node_mode: str
    node_id: str | None
    master_url: str | None
    node_secret: str | None
    is_master: bool
    is_child: bool
```

### 4.1 字段约束

| 字段 | 约束 |
| --- | --- |
| `node_mode` | 只允许 `master` / `child` |
| `node_id` | `child` 模式必填；`master` 可空 |
| `master_url` | `child` 模式必填；`master` 可空 |
| `node_secret` | `child` 模式必填；`master` 可空 |

## 5. 详细流程

### 5.1 gateway 启动参数解析流程

```text
CLI 输入
  ├── 解析 host/port/gateway_password
  ├── 解析 node_mode/node_id/master_url/node_secret
  ├── 校验 node_mode 合法性
  ├── 若 node_mode=child，则校验依赖参数完整性
  ├── 构造 NodeRuntimeConfig
  └── 传入 app.run(..., node_config=...)
```

### 5.2 service 配置透传流程

```text
环境变量/配置
  ├── build_service_config() 读取服务配置
  ├── 解析 node 相关配置
  ├── _start_gateway_process() 组装 jwg 启动命令
  ├── 根据 node_mode 决定是否追加参数
  └── 启动 jwg 子进程
```

## 6. 状态变化

本功能点不引入业务状态机，仅负责形成配置对象。

但需要在启动前区分两种配置状态：

- `valid_config`
- `invalid_config`

若为 `invalid_config`，启动必须失败，不得进入后续业务阶段。

## 7. 异常处理

### 7.1 异常场景

| 场景 | 处理方式 |
| --- | --- |
| `node_mode` 非法 | CLI 退出并输出 `INVALID_NODE_MODE` |
| `child` 模式缺少 `node_id` | CLI 退出并输出 `MISSING_NODE_CONFIG` |
| `child` 模式缺少 `master_url` | CLI 退出并输出 `MISSING_NODE_CONFIG` |
| `child` 模式缺少 `node_secret` | CLI 退出并输出 `MISSING_NODE_CONFIG` |

### 7.2 错误输出要求

- gateway CLI 应输出明确缺失项
- service 启动阶段应在子进程启动前完成校验，避免把错误延后到 gateway 内部

## 8. 兼容性要求

- 未提供 node 相关参数时，系统必须按 `master` 默认模式运行
- 现有 `host/port/gateway_password` 参数语义不得改变
- `jarvis-service` 在未配置 node 环境变量时，生成的 `jwg` 命令应与当前一致

## 9. 代码落点建议

### 9.1 `jarvis_web_gateway/cli.py`

建议改动：

- 在 `serve()` 中增加 4 个 node 参数
- 在 `main()` 或 `serve()` 内构造 `NodeRuntimeConfig`
- 将 `run(host, port, password)` 扩展为 `run(host, port, password, node_config)`

### 9.2 `jarvis_service/cli.py`

建议改动：

- 在 `ServiceConfig` 中增加 node 配置字段
- 在 `build_service_config()` 中读取环境变量
- 在 `_start_gateway_process()` 中把 node 参数透传给 `jwg`

### 9.3 建议新增模块 `node_config.py`

建议职责：

- 定义 `NodeRuntimeConfig`
- 提供 `validate_node_config()`
- 提供 `build_node_runtime_config()`

## 10. 测试建议

### 10.1 单元测试

- `master` 默认模式配置构造成功
- `child` 模式完整参数构造成功
- 非法 `node_mode` 报错
- `child` 模式缺参报错

### 10.2 集成验证

- `jwg --node-mode master` 可启动
- `jwg --node-mode child` 缺参数时报错
- `jarvis-service` 在配置 `JARVIS_NODE_MODE=child` 后生成正确的 `jwg` 启动命令

## 11. 验收标准

1. 开发者可以明确知道 node 参数写入哪些文件
2. 开发者可以明确知道 `child` 模式参数校验在哪一层执行
3. 开发者可以直接根据本设计编写 CLI 参数解析代码与测试
