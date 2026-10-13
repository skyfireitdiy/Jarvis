# 插件接口向后兼容机制设计

> 对应 Issue #218：[Feature] 插件接口向后兼容机制设计
> 关联 Issue #217：Jarvis 插件市场仓库（结构化清单）

## 一、背景与目标

随着 Jarvis 插件生态发展，插件接口（config.yaml 扩展点、plugin/api.py 私有功能、前端扩展、工具协议）会不断演进。目前缺乏统一的向后兼容机制，接口变更可能导致已安装的旧插件失效，或新版本 Jarvis 无法加载旧插件。

**目标**：

1. 新版本 Jarvis 能继续加载/运行旧版本插件（向后兼容）。
2. 插件接口演进时有明确的版本声明、兼容策略与废弃（deprecation）流程。
3. 插件开发者能声明其依赖的接口版本，Jarvis 据此做兼容性检查。

## 二、现状梳理

| 接口 | 现状 | 版本管理 |
|---|---|---|
| 工具协议 | `protocol_version`（`Tool` 类默认 "1.0"，支持 "2.0"，`execute_tool` 按版本分发） | ✅ 已有 |
| config.yaml 扩展点 | `_PLUGIN_EXTENSION_FIELDS` 白名单，无版本声明；`version` 是插件自身版本（仅用于依赖检查） | ❌ 无 |
| plugin/api.py 私有功能 | `PUBLIC_FUNCTIONS` 白名单，无版本声明 | ❌ 无 |
| 前端扩展 | frontend 字段（admin_tabs/sidebar_views/tool_panels），无版本声明 | ❌ 无 |
| 插件加载 | `_load_plugin_configs` 无必填字段校验、无未知扩展点字段警告 | ❌ 无 |

## 三、设计原则

- **渐进式、低侵入**：不强制所有插件声明接口版本，未声明按默认值处理，旧插件无需改动。
- **向后兼容优先**：接口变更以"新增可选、旧字段保留、废弃标记"的方式演进，默认不拒绝加载旧插件。
- **警告而非阻断**：不兼容时降级警告，避免破坏插件生态；是否拒绝可由未来配置决定。

## 四、核心设计

### 4.1 接口版本声明：`api_version`

在插件 config.yaml 顶层新增可选字段 `api_version`，声明插件依赖的接口协议版本：

```yaml
name: my-plugin
version: 0.1.0        # 插件自身版本（安装时做版本比较）
api_version: "1.0"    # 接口协议版本（可选，默认 "1.0"）
```

- **默认 "1.0"**：未声明的旧插件按 "1.0" 处理，无需改动即可在新 Jarvis 上运行。
- **与 `version` 区分**：`version` 是插件版本，`api_version` 是接口协议版本，二者语义不同、互不干扰。

### 4.2 兼容性检查

`_load_plugin_configs` 加载插件时读取 `api_version`，与 Jarvis 当前支持的接口版本（`PLUGIN_API_VERSION`，当前 "1.0"）比较：

- **兼容策略**：以主版本号（major）判断。插件声明的 major ≤ 当前支持 major 即兼容（向后兼容）；插件声明更高 major 视为不兼容（可能依赖未来接口能力）。
- **不兼容处理**：**降级警告**（默认不拒绝加载），提示插件可能无法完全兼容。

### 4.3 向后兼容策略

- **新增扩展点字段可选**：新增字段不强制插件声明，旧插件不受影响。
- **旧字段保留**：已存在的字段不删除，保持向后兼容。
- **废弃字段标记**：`_DEPRECATED_PLUGIN_FIELDS` 集合登记已废弃字段，加载时打印 deprecation 警告，字段本身仍保留在 `_PLUGIN_EXTENSION_FIELDS`（旧插件仍可加载），仅提示开发者尽快迁移。
- **字段版本追踪**：`_PLUGIN_EXTENSION_FIELD_API_VERSION` 记录每个扩展点字段引入的接口版本，用于兼容性诊断与废弃流程追踪。

### 4.4 废弃（deprecation）流程

1. 某字段/能力需要废弃时，将其加入 `_DEPRECATED_PLUGIN_FIELDS`。
2. 加载插件时检测到废弃字段，打印 deprecation 警告，通知插件开发者迁移。
3. 字段本身仍保留在 `_PLUGIN_EXTENSION_FIELDS`，旧插件仍可加载（向后兼容）。
4. 未来主版本升级（如 api_version 2.0）时，可移除废弃字段。

### 4.5 覆盖范围

| 接口 | 版本管理方式 |
|---|---|
| config.yaml 扩展点 | `api_version` 声明 + 兼容检查 + 废弃字段警告 |
| plugin/api.py 私有功能 | 可选 `API_VERSION` 常量（预留），`PUBLIC_FUNCTIONS` 白名单随 api_version 演进 |
| 前端扩展 | 随 `api_version` 声明 |
| 工具协议 | 已有 `protocol_version`，纳入统一文档 |

## 五、与插件市场（Issue #217）的关系

插件市场清单可记录每个插件的 `api_version`，用于兼容性匹配：用户在安装插件时，市场可根据当前 Jarvis 支持的接口版本过滤/标记不兼容插件。本设计为市场提供 `api_version` 数据来源（插件 config.yaml 声明，`get_plugin_config` 可读取），具体市场实现见 Issue #217。

## 六、代码位置

- 接口版本常量：`src/jarvis/jarvis_utils/utils.py`（`PLUGIN_API_VERSION` / `_DEPRECATED_PLUGIN_FIELDS` / `_PLUGIN_EXTENSION_FIELD_API_VERSION`）
- 兼容性检查：`src/jarvis/jarvis_utils/utils.py`（`_is_api_version_compatible`，`_load_plugin_configs`）
- 文档：`docs/plugin_development_guide.md`（「接口版本与向后兼容」章节）
