# 输出颜色配置规范

## 功能概述

优化 Jarvis 系统的输出颜色配置，根据信息重要程度使用不同的颜色视觉层级，提升用户体验和信息可读性。非重要信息使用灰色等不显眼颜色，重要信息使用鲜艳颜色突出显示。

## 接口定义

### 修改位置

1. **章节输出样式配置** (`style_config`): `src/jarvis/jarvis_utils/output.py` 第 182-305 行
2. **文字颜色映射** (`text_colors`): `src/jarvis/jarvis_utils/output.py` 第 322-345 行

### 输出类型分类

#### 高优先级（鲜艳颜色 + 特效）

这些信息需要立即引起用户注意，使用最显眼的颜色和视觉特效。

| 输出类型 | 当前颜色 | 目标颜色 | 特效 |
|---------|---------|---------|------|
| ERROR | red | bright_red | blink=True, bold=True |
| SUCCESS | green | bright_green | bold=True |
| WARNING | yellow | bright_yellow | blink=True, bold=True |
| START | bright_blue | bright_cyan | bold=True |
| TARGET | bright_magenta | bright_magenta | bold=True |
| STOP | red | bright_red | bold=True |

#### 中优先级（标准颜色）

这些信息是常规输出，使用清晰但不刺眼的标准颜色。

| 输出类型 | 当前颜色 | 目标颜色 | 说明 |
|---------|---------|---------|------|
| SYSTEM | cyan | cyan | AI助手消息 |
| CODE | green | green | 代码相关输出 |
| RESULT | blue | blue | 工具执行结果 |
| USER | green | bright_green | 用户输入 |
| TOOL | green | green | 工具调用 |
| PLANNING | magenta | magenta | 任务规划 |
| DIRECTORY | cyan | cyan | 目录相关 |
| NORMAL_MODEL | blue | bright_blue | 普通模型 |
| SMART_MODEL | bright_magenta | bright_magenta | 智能模型 |

#### 低优先级（灰色/不显眼）

这些信息是辅助性信息，使用灰色或不显眼的颜色，避免干扰主要信息。

| 输出类型 | 当前颜色 | 目标颜色 | 说明 |
|---------|---------|---------|------|
| DEBUG | grey50 | grey30 | 调试信息，保持低调 |
| PROGRESS | dim / bright_black | grey50 | 进度信息 |
| INFO | cyan | grey70 | 系统提示 |
| STATISTICS | blue | grey58 | 统计信息 |
| RETRY | yellow | grey70 | 重试操作 |
| ROLLBACK | red | grey70 | 回滚操作 |
| CHEAP_MODEL | green | grey58 | 经济模型 |

## 功能行为

### 颜色选择原则

1. **高优先级信息**：使用 `bright_` 前缀的鲜艳颜色，配合 `bold` 和 `blink` 特效
2. **中优先级信息**：使用标准颜色，保持清晰可读
3. **低优先级信息**：使用 `grey30`、`grey50`、`grey58`、`grey70` 等灰色系，降低视觉干扰

### 特效使用规范

- `blink`（闪烁）：仅用于 ERROR 和 WARNING 等需要立即关注的错误信息
- `bold`（粗体）：用于重要信息（高优先级）和标题
- `dim`（暗淡）：用于次要信息
- `frame`（边框）：章节标题使用，区分不同板块

### 向后兼容性

- 保持所有 OutputType 枚举值不变
- 保持图标配置不变
- 保持整体输出结构不变
- 仅修改颜色和特效配置

## 验收标准

1. **高优先级信息验证**
   - ERROR 输出使用 bright_red + blink + bold，在终端中闪烁且醒目
   - SUCCESS 输出使用 bright_green + bold，清晰表示成功
   - WARNING 输出使用 bright_yellow + blink + bold，引起注意
   - START/TARGET/STOP 使用鲜艳颜色 + bold，易于识别

2. **中优先级信息验证**
   - SYSTEM/CODE/RESULT 等常规输出使用标准颜色，清晰可读
   - 颜色不过于鲜艳，也不过于暗淡
   - 与高优先级信息有明显的视觉区分

3. **低优先级信息验证**
   - DEBUG 输出使用 grey30，非常低调不干扰视线
   - INFO/STATISTICS 等辅助信息使用灰色系（grey50/grey58/grey70）
   - 低优先级信息不会吸引不必要的注意力

4. **整体效果验证**
   - 信息层级清晰，用户能快速识别重要信息
   - 颜色搭配协调，不会造成视觉疲劳
   - 所有输出类型都有对应颜色配置，无遗漏
   - 代码编译无错误，运行正常

5. **兼容性验证**
   - 不影响现有功能
   - 不改变输出格式和结构
   - 保持图标配置不变
