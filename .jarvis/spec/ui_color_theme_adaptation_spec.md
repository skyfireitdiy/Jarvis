# UI 配色主题适配规范

## 功能概述

将 Jarvis 项目中的 Rich 输出配色修改为同时适配亮色和暗色主题的柔和配色方案。主要目标是将硬编码的深色背景色替换为双主题兼容的配色，确保在不同终端主题下都有良好的视觉效果。

## 接口定义

### 修改范围

1. **主要文件**：`src/jarvis/jarvis_utils/output.py`
   - `ConsoleOutputSink.emit()` 方法中的 `style_config` 字典（第182-327行）
   - `text_colors` 字典（第344-367行）
   - `styles` 字典中的 `bgcolor`（第370-390行）
   - `header_styles` 字典（第392-525行）

2. **辅助文件**：
   - `src/jarvis/jarvis_utils/utils.py`：`_show_usage_stats()` 中的欢迎面板（第970-976行）
   - `src/jarvis/jarvis_stats/visualizer.py`：统计可视化中的 Panel（第91-98行、第159-167行）

## 功能行为

### 当前问题

1. **硬编码深色背景**：所有 OutputType 都使用了深色背景色（如 `#1e2b3c`、`#1c2b1c` 等），在亮色主题下会显得突兀
2. **文字颜色过暗**：使用 `dark_cyan`、`dark_green` 等暗色调，在暗色主题下对比度不足
3. **缺少主题感知**：没有根据终端主题自动调整配色

### 修改策略

#### 方案 1：移除背景色，使用 Rich 标准颜色（推荐）

**原理**：移除所有硬编码的 `bgcolor`，只使用文字颜色和边框样式，让 Rich 根据终端主题自动适配。

**优点**：
- 完全适配亮色和暗色主题
- 代码简洁，维护成本低
- Rich 会自动处理主题适配

**缺点**：
- 失去背景色区分不同输出类型的能力
- 视觉层次感可能稍弱

#### 方案 2：检测终端主题，动态选择配色

**原理**：在代码中检测终端是否为暗色主题，然后动态选择对应的配色方案。

**优点**：
- 可以保留背景色区分
- 可以为不同主题定制不同的配色

**缺点**：
- 实现复杂度高
- 检测逻辑可能不准确
- 维护成本高

#### 方案 3：使用柔和的中性色调（推荐备选）

**原理**：将深色背景改为柔和的中性色调，文字颜色改为对比度更高的标准颜色。

**配色方案**：
- 背景色：移除硬编码背景，使用默认背景
- 文字颜色：使用标准颜色（`cyan`、`green`、`blue`、`red`、`yellow` 等）
- 边框样式：使用与文字颜色匹配的边框

**优点**：
- 在亮色和暗色主题下都有较好的视觉效果
- 配色简洁统一
- 易于维护

**缺点**：
- 需要仔细选择颜色组合
- 可能在某些极端主题下表现不佳

### 推荐方案

**采用方案 1（移除背景色）+ 方案 3（柔和标准颜色）的组合**：

1. 移除所有硬编码的 `bgcolor`
2. 将文字颜色改为标准颜色（去掉 `dark_` 前缀）
3. 保留边框样式和图标
4. 确保 Panel 的 `border_style` 与内容颜色协调

### 具体配色调整

#### OutputType 颜色映射

```python
# 原始文字颜色 → 新文字颜色
OutputType.SYSTEM:    "cyan"        # 原 "dark_cyan"
OutputType.CODE:     "green"       # 原 "dark_green"
OutputType.RESULT:   "blue"        # 原 "dark_blue"
OutputType.ERROR:    "red"         # 原 "dark_red"
OutputType.INFO:     "cyan"        # 原 "blue"
OutputType.PLANNING: "magenta"     # 原 "purple"
OutputType.SUCCESS:  "green"       # 原 "green"
OutputType.WARNING:  "yellow"      # 原 "orange3"
OutputType.DEBUG:    "grey50"      # 保持不变
OutputType.USER:     "green"       # 原 "dark_sea_green"
OutputType.TOOL:     "green"       # 原 "dark_olive_green"
OutputType.START:    "bright_blue"  # 保持不变
OutputType.TARGET:   "bright_magenta" # 保持不变
OutputType.STOP:     "red"         # 保持不变
OutputType.RETRY:    "yellow"      # 保持不变
OutputType.ROLLBACK: "red"         # 原 "dark_red"
OutputType.DIRECTORY: "cyan"       # 原 "bright_cyan"
OutputType.STATISTICS: "blue"     # 原 "bright_blue"
```

#### 其他文件 Panel 配色

```python
# utils.py - welcome_panel
border_style="cyan"  # 原 "yellow"

# visualizer.py - 统计面板
border_style="cyan"  # 原 "blue"

# visualizer.py - 表格列
"时间": "cyan"        # 原 "cyan"（保持）
"计数": "green"       # 原 "green"（保持）
"总和": "yellow"      # 原 "yellow"（保持）
"平均": "yellow"      # 原 "yellow"（保持）
"最小": "blue"        # 原 "blue"（保持）
"最大": "red"         # 原 "red"（保持）
```

## 边界条件

1. **终端主题检测失败**：无法确定终端主题时，使用默认配色方案
2. **颜色不受支持**：Rich 不支持某些颜色时，回退到标准颜色
3. **用户自定义主题**：支持用户通过配置文件覆盖默认配色（未来扩展）

## 异常处理

1. 颜色映射失败时，使用白色作为默认颜色
2. Rich 渲染失败时，降级为纯文本输出
3. 不影响原有功能的正常使用

## 验收标准

### 功能验收

1. [ ] `output.py` 中所有硬编码的 `bgcolor` 已移除
2. [ ] `output.py` 中所有文字颜色已更新为标准颜色（无 `dark_` 前缀）
3. [ ] `utils.py` 中欢迎面板的 `border_style` 已更新为 `cyan`
4. [ ] `visualizer.py` 中统计面板的 `border_style` 已更新为 `cyan`
5. [ ] 所有 Panel 的配色在亮色主题下清晰可读
6. [ ] 所有 Panel 的配色在暗色主题下清晰可读
7. [ ] 保留所有图标和表情符号

### 视觉验收

1. [ ] 颜色对比度符合 WCAG AA 标准（至少 4.5:1）
2. [ ] 配色柔和舒适，无刺眼感
3. [ ] 不同 OutputType 之间有明显的视觉区分
4. [ ] 整体风格统一协调

### 代码质量验收

1. [ ] 代码风格符合 PEP 8 规范
2. [ ] 没有引入新的硬编码颜色值
3. [ ] 没有破坏原有功能
4. [ ] 添加必要的注释说明配色调整

### 测试场景

1. 在亮色主题终端中运行 Jarvis，检查输出效果
2. 在暗色主题终端中运行 Jarvis，检查输出效果
3. 测试各种 OutputType 的输出（SYSTEM, CODE, RESULT, ERROR 等）
4. 测试欢迎界面的显示效果
5. 测试统计信息的显示效果

## 执行步骤

### 阶段 1：修改 output.py

1. 移除 `style_config` 字典中的所有 `bgcolor` 参数
2. 更新 `style_config` 中的 `color` 为标准颜色
3. 更新 `text_colors` 字典中的颜色映射
4. 移除 `styles` 字典中的 `bgcolor` 键
5. 更新 `header_styles` 字典，移除 `bgcolor`，更新 `color`

### 阶段 2：修改其他文件

1. 修改 `utils.py` 中欢迎面板的 `border_style`
2. 修改 `visualizer.py` 中统计面板的 `border_style`
3. 检查并更新其他使用 Panel 的文件

### 阶段 3：验证测试

1. 在亮色主题终端测试
2. 在暗色主题终端测试
3. 测试各种输出类型
4. 回归测试确保功能正常