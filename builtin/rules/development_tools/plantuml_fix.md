---
name: plantuml_fix
description: 当需要修复或校验PlantUML代码块时触发。每当用户提及"PlantUML"、"UML图"、"图表修复"、"语法错误"时触发。不触发：仅生成PlantUML不修复；非PlantUML图表；Mermaid图表。
license: MIT
---

# PlantUML修复规则

## 规则简介

此规则用于修复Markdown文件中之PlantUML代码块。PlantUML乃常用之UML图表绘制工具，然在Markdown文件中嵌入时或出现语法错误或格式问题。

**工作流程：**

1. **提取**：用脚本从Markdown文件中提取PlantUML代码块为单独之`.puml`文件
2. **校验**：用脚本调用PlantUML程序校验`.puml`文件之语法并报告错误
3. **修复**：AI根据错误信息修复`.puml`文件内容
4. **写回**：用脚本将修复后之`.puml`文件内容写回Markdown文件

**重要说明：**

- 脚本只负责提取、校验报告与写回
- 修复工作由AI执行，AI需根据校验错误信息手动修复`.puml`文件

## 汝必守之原则

### 1. 安全性原则

**要求说明：**

- **必**：修改前备份原始文件
- **必**：验证PlantUML程序可用性后再执行修复
- **禁**：直接覆盖原始文件而不保留备份

### 2. 准确性原则

**要求说明：**

- **必**：准确提取PlantUML代码块（含开始与结束标记）
- **必**：用PlantUML官方程序进行语法校验
- **必**：保留原始代码之缩进与格式
- **禁**：修改非PlantUML代码块之内容

## 汝必行之操作

### 操作1：检查环境依赖

**执行步骤：**

1. 检查Python环境是否可用
2. 检查PlantUML程序是否已安装（`plantuml`命令或Java jar文件）
3. 验证脚本文件是否存在：`{{ rule_file_dir }}/plantuml_fix.py`

### 操作2：提取PlantUML代码块

**执行步骤：**

```bash
python3 {{ rule_file_dir }}/plantuml_fix.py extract <markdown_file>
```

脚本会：

- 从Markdown文件中提取所有PlantUML代码块
- 为每个代码块创建单独之`.puml`文件
- 自动添加`@startuml`与`@enduml`标记（若缺失）
- 默认输出至系统临时目录（如`/tmp/plantuml_<filename>/`），避免被git管理
- 用`-o`参数可指定输出目录

### 操作3：校验PlantUML语法

**执行步骤：**

```bash
python3 {{ rule_file_dir }}/plantuml_fix.py validate <filename>_plantuml/
```

或直接用plantuml命令：

```bash
plantuml -checkonly <filename>_plantuml/*.puml
```

### 操作4：AI修复.puml文件

**执行步骤：**

1. 根据校验错误信息，用`edit_file`工具修复`.puml`文件
2. 常见修复包括：
   - 修复箭头语法（`-->`、`->`等）
   - 添加缺失之分号
   - 修复注释格式
   - 添加缺失之`@startuml`/`@enduml`标记

### 操作5：将修复后之内容写回Markdown

**执行步骤：**

```bash
python3 {{ rule_file_dir }}/plantuml_fix.py writeback <markdown_file> <puml_dir>
```

脚本会：

- 自动备份原始Markdown文件（`.bak`后缀）
- 将`.puml`文件内容替换回对应之PlantUML代码块
- 保持Markdown文件之其他内容不变

## 检查清单

完成任务后，汝必确认：

- [ ] 脚本文件已创建于`{{ rule_file_dir }}/plantuml_fix.py`
- [ ] 规则文件已创建于`{{ rule_file_dir }}/plantuml_fix.md`
- [ ] 脚本具有可执行权限
- [ ] PlantUML程序已正确安装
- [ ] 测试文件中之PlantUML代码块能被正确提取
- [ ] 修复后之代码能通过PlantUML语法校验
- [ ] 修复后之内容已正确写回Markdown文件

## 常见错误类型与修复方法

### 1. 版本兼容性问题

**问题：** `!theme plain`等指令在旧版本（如1.2020.02）中不支持

**修复方法：**

- 移除不支持之`!theme`指令
- 检查PlantUML版本：`plantuml -version`
- 用`-checkonly`验证语法兼容性

### 2. Activity Diagram语法问题

**问题：** 单独之代码行非有效语法

```plantuml
# 错误示例
::调用函数;
enqueueCommandInLane();  # 单独之代码行无效
```

**修复方法：** 将代码合并至描述行

```plantuml
# 正确示例
::调用函数 enqueueCommandInLane();
```

### 3. 变量赋值语法问题

**问题：** 单独之变量赋值行无效

```plantuml
# 错误示例
::初始化;
count = 1;  # 单独之赋值行无效
```

**修复方法：** 将赋值合并至描述行

```plantuml
# 正确示例
::初始化 count = 1;
```

### 4. 条件语句语法问题

**问题：** `if`/`elseif`缺少`then`关键字

```plantuml
# 错误示例
if (条件?) (是)
  :操作;
else (否)
  :其他操作;
endif
```

**修复方法：** 添加`then`关键字

```plantuml
# 正确示例
if (条件?) then (是)
  :操作;
else (否)
  :其他操作;
endif
```

### 5. 多行对象字面量问题

**问题：** 对象字面量跨多行或导致解析错误

```plantuml
# 错误示例
::调用函数 func({
  key1: value1,
  key2: value2
});
```

**修复方法：** 合并为单行或用变量

```plantuml
# 正确示例
::调用函数 func({ key1: value1, key2: value2 });
```

### 6. 箭头语法问题

**问题：** 箭头语法不正确

```plantuml
# 错误示例
A -> B: 消息
A --> B: 消息
```

**修复方法：** 根据图表类型用正确之箭头

- 类图：用`-->`或`--*`等
- 时序图：用`->`或`-->`
- 活动图：用`->`连接活动

## 修复策略总结

### 最小化修改原则

1. 只修复语法错误，不改变语义
2. 保持原始代码之缩进与格式
3. 优先合并代码行，而非删除

### 修复顺序

1. 先修复版本兼容性问题（如移除`!theme`）
2. 再修复语法结构问题（如`if`/`then`）
3. 最后修复代码行合并问题

### 验证方法

```bash
# 逐个文件验证
for f in *.puml; do
  echo "检查 $f"
  plantuml -checkonly "$f"
done

# 或批量验证
plantuml -checkonly *.puml
```

## 相关资源

- PlantUML官方文档：<https://plantuml.com/>
- PlantUML语法参考：<https://plantuml.com/zh/>
- Activity Diagram语法：<https://plantuml.com/activity-diagram-beta>
- PlantUML版本历史：<https://plantuml.com/changes>
