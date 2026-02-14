# Jarvis Tool CLI 使用规则

## 规则简介

本规则说明如何使用 `jarvis-tool` 命令行工具来管理和查看 Jarvis 工具系统中的工具信息。

## 可用命令

### 1. list 命令

**功能：** 列出所有可用工具

**语法：**

```bash
jarvis-tool list [OPTIONS]
```

**选项：**

- `--json`: 以 JSON 格式输出
- `--detailed`: 显示详细信息（包括参数定义）

**示例：**

```bash
# 简单列表
jarvis-tool list

# 详细信息
jarvis-tool list --detailed

# JSON 格式
jarvis-tool list --json

# 详细 JSON 格式
jarvis-tool list --detailed --json
```

### 2. show 命令

**功能：** 显示指定工具的详细信息

**语法：**

```bash
jarvis-tool show TOOL_NAME [OPTIONS]
```

**参数：**

- `TOOL_NAME`: 要查看的工具名称（必填）

**选项：**

- `--json`: 以 JSON 格式输出

**示例：**

```bash
# 查看工具详情
jarvis-tool show execute_script

# JSON 格式
jarvis-tool show execute_script --json
```

## 常见使用场景

### 场景 1：查看所有可用工具

```bash
jarvis-tool list
```

### 场景 2：查看某个工具的详细参数

```bash
jarvis-tool show read_code
```

### 场景 3：以 JSON 格式获取工具信息（用于脚本处理）

```bash
jarvis-tool show edit_tool --json
```

### 场景 4：查看包含参数定义的工具列表

```bash
jarvis-tool list --detailed
```

## 相关资源

- CLI 实现位置：`{{ git_root_dir }}/src/jarvis/jarvis_tools/cli/main.py`
- 工具注册表：`{{ git_root_dir }}/src/jarvis/jarvis_tools/registry.py`
