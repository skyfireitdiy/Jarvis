# 📋 jarvis_config 使用指南

`jarvis_config` 是一个基于 JSON Schema 动态生成配置 Web 页面的工具，提供友好的可视化界面来管理和编辑配置文件。

## ✨ 核心特性

- 🎨 **Zen-iOS Hybrid 风格**：精美的毛玻璃效果、双层物理描边、触觉反馈
- 📝 **动态表单生成**：根据 JSON Schema 自动生成表单，支持多种字段类型
- ✅ **实时验证**：表单提交时自动验证配置是否符合 Schema 规范
- 🚀 **简单易用**：一条命令启动 Web 服务，无需额外配置
- 📄 **多格式支持**：根据文件后缀自动支持 JSON 和 YAML 格式输出

---

## 🚀 快速开始

### 基本用法

```bash
# 启动 Web 配置界面（使用默认 schema 和输出路径）
jarvis-config web

# 指定 schema 和输出文件（JSON 格式）
jarvis-config web --schema schema.json --output config.json

# 指定 schema 和输出文件（YAML 格式）
jarvis-config web --schema schema.json --output config.yaml

# 指定端口
jarvis-config web --port 3000

# 禁用自动打开浏览器
jarvis-config web --no-browser
```

### 示例 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "应用配置",
  "description": "应用程序的基本配置",
  "type": "object",
  "required": ["name", "port"],
  "properties": {
    "name": {
      "type": "string",
      "description": "应用名称",
      "minLength": 1,
      "default": "my-app"
    },
    "port": {
      "type": "integer",
      "description": "服务端口",
      "minimum": 1,
      "maximum": 65535,
      "default": 8080
    },
    "enabled": {
      "type": "boolean",
      "description": "是否启用",
      "default": true
    },
    "mode": {
      "type": "string",
      "enum": ["development", "production", "test"],
      "description": "运行模式",
      "default": "development"
    }
  }
}
```

---

## 📖 命令行接口

### `web` 命令

启动 Web 配置界面，根据指定的 Schema 文件生成配置表单。

```bash
jarvis-config web [OPTIONS]
```

#### 选项说明

| 选项           | 简写  | 默认值                           | 说明                 |
| -------------- | ----- | -------------------------------- | -------------------- |
| `--schema`     | `-s`  | `jarvis_data/config_schema.json` | JSON Schema 文件路径 |
| `--output`     | `-o`  | `~/.jarvis/config.yaml`          | 输出的配置文件路径   |
| `--port`       | `-p`  | `8080`                           | Web 服务监听端口     |
| `--no-browser` | `/nb` | `False`                          | 禁用自动打开浏览器   |

#### 示例

```bash
# 使用默认配置（jarvis 的 config_schema.json）
jarvis-config web

# 指定自定义 schema 和输出文件
jarvis-config web -s config/schema.json -o config/output.json

# 指定端口 3000
jarvis-config web -s config/schema.json -o config/output.json -p 3000

# 不自动打开浏览器
jarvis-config web -s config/schema.json -o config/output.json --no-browser
```

---

## 🛠️ JSON Schema 支持

### 支持的字段类型

| 类型      | 说明   | 示例        |
| --------- | ------ | ----------- |
| `string`  | 字符串 | 用户名、URL |
| `number`  | 浮点数 | 速率、比例  |
| `integer` | 整数   | 端口、数量  |
| `boolean` | 布尔值 | 开关状态    |
| `array`   | 数组   | 标签列表    |
| `object`  | 对象   | 嵌套配置    |

### 支持的约束

| 约束               | 适用类型       | 说明                  |
| ------------------ | -------------- | --------------------- |
| `required`         | 所有           | 必填字段              |
| `default`          | 所有           | 默认值                |
| `enum`             | 所有           | 枚举值列表            |
| `minimum`          | number/integer | 最小值                |
| `maximum`          | number/integer | 最大值                |
| `exclusiveMinimum` | number/integer | 严格大于              |
| `exclusiveMaximum` | number/integer | 严格小于              |
| `minLength`        | string         | 最小长度              |
| `maxLength`        | string         | 最大长度              |
| `pattern`          | string         | 正则表达式            |
| `format`           | string         | 格式（如 uri, email） |
| `minItems`         | array          | 最小项数              |
| `maxItems`         | array          | 最大项数              |
| `items`            | array          | 数组项类型            |
| `properties`       | object         | 对象属性定义          |

### 字段类型示例

```json
{
  "properties": {
    "username": {
      "type": "string",
      "minLength": 3,
      "maxLength": 20,
      "default": "admin"
    },
    "port": {
      "type": "integer",
      "minimum": 1,
      "maximum": 65535,
      "default": 8080
    },
    "rate": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.5
    },
    "enabled": {
      "type": "boolean",
      "default": true
    },
    "status": {
      "type": "string",
      "enum": ["active", "inactive", "pending"],
      "default": "pending"
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 0,
      "maxItems": 10,
      "default": []
    },
    "database": {
      "type": "object",
      "properties": {
        "host": { "type": "string", "default": "localhost" },
        "port": { "type": "integer", "default": 5432 }
      },
      "default": {}
    }
  }
}
```

---

## 💡 使用示例

### 简单配置

**Schema (`simple.json`)**:

```json
{
  "title": "简单配置",
  "type": "object",
  "required": ["app_name", "debug_mode"],
  "properties": {
    "app_name": {
      "type": "string",
      "description": "应用名称",
      "default": "my-app"
    },
    "debug_mode": {
      "type": "boolean",
      "description": "调试模式",
      "default": false
    }
  }
}
```

**启动命令**:

```bash
jarvis-config web simple.json output.json
```

**生成的配置 (`output.json`)**:

```json
{
  "app_name": "my-app",
  "debug_mode": false
}
```

---

### 复杂嵌套配置

**Schema (`complex.json`)**:

```json
{
  "title": "复杂配置",
  "type": "object",
  "required": ["name", "servers"],
  "properties": {
    "name": {
      "type": "string",
      "description": "项目名称"
    },
    "servers": {
      "type": "array",
      "description": "服务器列表",
      "items": {
        "type": "object",
        "properties": {
          "host": { "type": "string" },
          "port": { "type": "integer", "minimum": 1, "maximum": 65535 }
        },
        "required": ["host", "port"]
      },
      "minItems": 1
    },
    "database": {
      "type": "object",
      "properties": {
        "driver": {
          "type": "string",
          "enum": ["postgresql", "mysql", "sqlite"]
        },
        "connection": {
          "type": "object",
          "properties": {
            "host": { "type": "string" },
            "port": { "type": "integer" },
            "username": { "type": "string" },
            "password": { "type": "string" }
          }
        }
      }
    }
  }
}
```

**启动命令**:

```bash
jarvis-config web complex.json config.json --port 3000
```

---

## 🎨 设计说明

### Zen-iOS Hybrid 前端风格

`jarvis_config` 采用 **Zen-iOS Hybrid** 设计语言，提供精致的用户界面体验。

#### 核心设计原则

1. **全局底色**：使用 iOS 系统级灰 `#F2F2F7`，杜绝纯白背景
2. **极致毛玻璃**：层级容器使用 `backdrop-blur-40px` 到 `60px`，半透明背景 `White/40-60`
3. **双层物理描边**：
   - 内描边：`1px border-white/60`（模拟玻璃切面光线）
   - 外描边：`1px border-gray-200/40`（定义物理轮廓）
4. **深度阴影**：悬浮组件使用柔和扩散阴影 `shadow-[0_24px_48px_-12px_rgba(0,0,0,0.08)]`
5. **圆角美学**：
   - 大容器：`rounded-[40px]` 到 `[50px]`
   - 功能块：`rounded-[28px]`
   - 小组件：`rounded-xl`
6. **触觉反馈**：所有可点击项具备 `active:scale-95` 物理回弹

#### 组件样式

- **主按钮**：深空黑 `#1C1C1E`，高对比度引导用户注意力
- **输入框**：凹陷效果，`shadow-inner` 配合浅灰背景
- **开关器**：iOS 风格绿色开关 `#34C759`
- **间距**：强制大间距 `p-6` 或 `p-8`，确保呼吸感

#### 字体系统

- 使用 **Inter** 或 **SF Pro Display** 字体
- 标题：`Font-Extrabold` + `Tracking-tight`
- 标签：全大写 + `Tracking-widest` + `Font-Bold` + `text-[10px]`

---

## 🔧 API 接口

### GET `/api/schema`

获取 Schema 数据及元数据。

**响应示例**:

```json
{
  "title": "应用配置",
  "description": "应用程序的基本配置",
  "properties": {
    "name": {
      "type": "string",
      "_meta": {
        "description": "应用名称",
        "default": "my-app",
        "required": true
      }
    }
  },
  "required": ["name"]
}
```

### POST `/api/save`

保存配置数据并验证。根据输出文件后缀自动保存为 JSON 或 YAML 格式。

**请求体**:

```json
{
  "config": {
    "name": "my-app",
    "port": 8080
  }
}
```

**响应示例（成功）**:

```json
{
  "success": true,
  "message": "配置已保存到 /path/to/config.json",
  "path": "/path/to/config.json"
}
```

**注意**：如果输出文件后缀为 `.yaml` 或 `.yml`，配置将以 YAML 格式保存；否则以 JSON 格式保存。

**响应示例（验证失败）**:

```json
{
  "success": false,
  "errors": [
    {
      "path": "name",
      "message": "String length 0 is less than minimum 1"
    }
  ]
}
```

### GET `/api/health`

健康检查接口。

**响应示例**:

```json
{
  "status": "ok"
}
```

---

## 📝 注意事项

1. **Schema 版本**：支持 JSON Schema Draft-07 规范
2. **输出目录**：输出文件的父目录如果不存在会自动创建
3. **验证规则**：配置保存时会根据 Schema 进行验证，验证失败会返回错误详情
4. **浏览器支持**：建议使用现代浏览器（Chrome、Firefox、Safari、Edge 最新版本）

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📄 许可证

MIT License
