---
name: add_builtin_command
description: 当需要添加@触发的内置快捷命令时触发。每当用户提及"添加命令"、"内置命令"、"@命令"、"快捷命令"时触发。不触发：添加规则（用add_builtin_rule）；添加工具；修改现有命令逻辑。
---
# 添加 @ 触发的内置快捷命令规则

## 规则简介

本规则说明如何在 Jarvis 系统中添加新之 `@` 触发之内置快捷命令。此等命令可输入 `@` 符号触发自动补全，择后立即执行相应功能。

## 汝必遵守之原则

### 1. 数据源统一

**要求说明：**

- **必**：于 `{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py` 文件顶部定义 `BUILTIN_COMMANDS` 常量
- **必**：所有内置命令必从此统一之数据源添加
- **禁**：于 `get_completions` 与 `_get_fzf_completion_items` 中重复定义命令列表
**原因：**
保持数据源统一可避重复，确保 prompt_toolkit 与 fzf 之补全列表始终一致。

### 2. 命令类型

内置命令分两种类型：

#### 2.1 提示词模板命令

此类命令会替换为特定之提示词模板，然后传递予 Agent 处理。
**特点：**

- 不会立即返回
- 会将模板内容追加至用户输入
- 通过 `replace_map` 管理
**示例：** `@Web`、`@Dev`、`@Fix`、`@Check`

#### 2.2 内置命令标记

此类命令由 `builtin_input_handler` 直接处理，立即执行特定功能。
**特点：**

- 立即返回，不传递予 Agent
- 执行特定之系统功能
- 格式为 `'<CommandName>'`
**示例：** `'<CommandName>'`（如具体之内置命令名）

## 汝必执行之操作

### 操作 1：添加提示词模板命令

**适用场景：** 需为 Agent 提供预设之提示词模板。
**执行步骤：**

1. **确认无需于 `BUILTIN_COMMANDS` 中添加**（提示词模板命令由 `replace_map` 管理）
2. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_utils/builtin_replace_map.py`
3. 于 `BUILTIN_REPLACE_MAP` 字典中添加新条目
**示例：**

```python
BUILTIN_REPLACE_MAP = {
    "Web": {
        "append": True,
        "template": "请使用search_web工具...",
        "description": "网页搜索",
    },
    "YourCommand": {
        "append": False,  # False 表示替换用户输入
        "template": "你的提示词模板",
        "description": "命令描述",
    },
}
```

**注意事项：**

- `append: True`：模板追加至用户输入后
- `append: False`：模板替换用户输入
- 自动补全会自动从 `replace_map` 中读取，无需手动添加至 `BUILTIN_COMMANDS`

### 操作 2：添加内置命令标记

**适用场景：** 需立即执行特定功能，不传递予 Agent。
**执行步骤：**

1. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py`
2. 于 `BUILTIN_COMMANDS` 常量中添加新命令
**示例：**

```python
# 内置命令标记列表（用于自动补全和 fzf）
BUILTIN_COMMANDS = [
    # ("CommandName", "命令描述"),  # 按需添加，避免列出具体命令名触发额外行为
    ("YourCommand", "命令描述"),  # 添加新命令
]
```

1. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_agent/builtin_input_handler.py`
2. 于 `builtin_input_handler` 函数中添加处理逻辑
**示例：**

```python
def builtin_input_handler(user_input: str, agent_: Any) -> Tuple[str, bool]:
    """处理内置的特殊输入标记，并追加相应的提示词"""
    agent: Agent = agent_
    special_tags = re.findall(r"'<([^>]+)>'", user_input)
    if not special_tags:
        return user_input, False
    processed_tag = set()
    add_on_prompt = ""
    modified_input = user_input
    for tag in special_tags:
        if tag == "YourCommand":
            # 处理你的命令逻辑
            # 如果需要立即返回，返回 "", True
            return "", True
        # ... 其他命令处理
    return modified_input, False
```

**注意事项：**

- 若命令需立即返回并跳过 Agent 处理，返回 `("", True)`
- 若命令仅修改输入，返回 `(modified_input, False)`
- 命令名称必与 `BUILTIN_COMMANDS` 中定义者完全一致

### 操作 3：注册规则

**执行步骤：**

1. 于 `{{ git_root_dir }}/.jarvis/rule` 文件中添加规则条目
**示例：**

```markdown
### 添加内置快捷命令规则
说明如何添加 @ 触发的内置快捷命令。（{{ git_root_dir }}/.jarvis/rules/development_tools/add_builtin_command.md）
```

## 检查清单

完成任务后，汝必确认：

- [ ] 已确认命令类型（提示词模板 vs 内置命令标记）
- [ ] 提示词模板命令已于 `builtin_replace_map.py` 中定义
- [ ] 内置命令标记已于 `BUILTIN_COMMANDS` 中添加
- [ ] 内置命令标记已于 `builtin_input_handler.py` 中实现处理逻辑
- [ ] 规则已于 `.jarvis/rule` 文件中注册
- [ ] 已通过实际测试验证自动补全功能

## 相关资源

- 内置命令定义位置：`{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py`（第68-80行）
- 提示词模板位置：`{{ git_root_dir }}/src/jarvis/jarvis_utils/builtin_replace_map.py`
- 命令处理逻辑：`{{ git_root_dir }}/src/jarvis/jarvis_agent/builtin_input_handler.py`
- 参考规则：[新增规则规范]({{ rule_file_dir }}/../tool_config/add_rule.md)
