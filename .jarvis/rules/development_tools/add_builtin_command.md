# 添加 @ 触发的内置快捷命令规则

## 规则简介

本规则说明如何在 Jarvis 系统中添加新的 `@` 触发的内置快捷命令。这些命令可以通过输入 `@` 符号触发自动补全，选择后立即执行相应功能。

## 你必须遵守的原则

### 1. 数据源统一

**要求说明：**

- **必须**：在 `{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py` 文件顶部定义 `BUILTIN_COMMANDS` 常量
- **必须**：所有内置命令必须从这个统一的数据源添加
- **禁止**：在 `get_completions` 和 `_get_fzf_completion_items` 中重复定义命令列表

**原因：**

保持数据源统一可以避免重复，确保 prompt_toolkit 和 fzf 的补全列表始终一致。

### 2. 命令类型

内置命令分为两种类型：

#### 2.1 提示词模板命令

这类命令会替换为特定的提示词模板，然后传递给 Agent 处理。

**特点：**

- 不会立即返回
- 会将模板内容追加到用户输入中
- 通过 `replace_map` 管理

**示例：** `@Web`、`@Dev`、`@Fix`、`@Check`

#### 2.2 内置命令标记

这类命令由 `builtin_input_handler` 直接处理，立即执行特定功能。

**特点：**

- 立即返回，不传递给 Agent
- 执行特定的系统功能
- 格式为 `'<CommandName>'`

**示例：** `'<Summary>'`、`'<Clear>'`、`'<FixToolCall>'`

## 你必须执行的操作

### 操作 1：添加提示词模板命令

**适用场景：** 需要为 Agent 提供预设的提示词模板。

**执行步骤：**

1. **确认不需要在 `BUILTIN_COMMANDS` 中添加**（提示词模板命令由 `replace_map` 管理）
2. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_utils/builtin_replace_map.py`
3. 在 `BUILTIN_REPLACE_MAP` 字典中添加新的条目

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

- `append: True`：模板追加到用户输入后面
- `append: False`：模板替换用户输入
- 自动补全会自动从 `replace_map` 中读取，无需手动添加到 `BUILTIN_COMMANDS`

### 操作 2：添加内置命令标记

**适用场景：** 需要立即执行特定功能，不传递给 Agent。

**执行步骤：**

1. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py`
2. 在 `BUILTIN_COMMANDS` 常量中添加新命令

**示例：**

```python
# 内置命令标记列表（用于自动补全和 fzf）
BUILTIN_COMMANDS = [
    ("Summary", "总结"),
    ("Pin", "固定/置顶内容"),
    ("Clear", "清除历史"),
    ("ToolUsage", "工具使用说明"),
    ("ReloadConfig", "重新加载配置"),
    ("SaveSession", "保存当前会话"),
    ("RestoreSession", "恢复会话"),
    ("ListSessions", "列出所有会话"),
    ("Quiet", "无人值守模式"),
    ("FixToolCall", "修复工具调用"),
    ("YourCommand", "命令描述"),  # 添加新命令
]
```

3. 编辑 `{{ git_root_dir }}/src/jarvis/jarvis_agent/builtin_input_handler.py`
4. 在 `builtin_input_handler` 函数中添加处理逻辑

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

- 如果命令需要立即返回并跳过 Agent 处理，返回 `("", True)`

- 如果命令只是修改输入，返回 `(modified_input, False)`

- 命令名称必须与 `BUILTIN_COMMANDS` 中定义的完全一致

### 操作 3：注册规则

**执行步骤：**

1. 在 `{{ git_root_dir }}/.jarvis/rule` 文件中添加规则条目

**示例：**

```markdown
### 添加内置快捷命令规则

说明如何添加 @ 触发的内置快捷命令。（{{ git_root_dir }}/.jarvis/rules/development_tools/add_builtin_command.md）
```

## 检查清单

在完成任务后，你必须确认：

- [ ] 已确认命令类型（提示词模板 vs 内置命令标记）
- [ ] 提示词模板命令已在 `builtin_replace_map.py` 中定义
- [ ] 内置命令标记已在 `BUILTIN_COMMANDS` 中添加
- [ ] 内置命令标记已在 `builtin_input_handler.py` 中实现处理逻辑
- [ ] 规则已在 `.jarvis/rule` 文件中注册
- [ ] 已通过实际测试验证自动补全功能

## 相关资源

- 内置命令定义位置：`{{ git_root_dir }}/src/jarvis/jarvis_utils/input.py`（第68-80行）
- 提示词模板位置：`{{ git_root_dir }}/src/jarvis/jarvis_utils/builtin_replace_map.py`
- 命令处理逻辑：`{{ git_root_dir }}/src/jarvis/jarvis_agent/builtin_input_handler.py`
- 参考规则：[新增规则规范]({{ rule_file_dir }}/../tool_config/add_rule.md)
