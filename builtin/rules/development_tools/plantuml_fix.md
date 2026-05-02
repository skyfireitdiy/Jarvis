---
name: plantuml_fix
description: 当需要修复Markdown文件中的PlantUML代码块时使用此规则——PlantUML修复规则，提取、校验和修复PlantUML代码。包括：从MD文件中提取PlantUML代码块为单独的.puml文件；使用PlantUML程序校验语法并报告错误；AI根据错误信息修复.puml文件；将修复后的代码写回原文件。每当用户提及"PlantUML"、"UML图"、"图表修复"、"语法错误"或需要修复/校验PlantUML代码时触发，无论他们使用什么编辑器或环境。如果需要提取、校验或修复Markdown文件中的PlantUML代码块，请使用此规则。
license: MIT
---

# PlantUML修复规则

## 规则简介

本规则用于修复Markdown文件中的PlantUML代码块。PlantUML是一种常用的UML图表绘制工具，但在Markdown文件中嵌入时可能出现语法错误或格式问题。

**工作流程：**

1. **提取**：使用脚本从Markdown文件中提取PlantUML代码块为单独的`.puml`文件
2. **校验**：使用脚本调用PlantUML程序校验`.puml`文件的语法并报告错误
3. **修复**：AI根据错误信息修复`.puml`文件内容
4. **写回**：使用脚本将修复后的`.puml`文件内容写回Markdown文件

**重要说明：**

- 脚本只负责提取、校验报告和写回
- 修复工作由AI执行，AI需要根据校验错误信息手动修复`.puml`文件

## 你必须遵守的原则

### 1. 安全性原则

**要求说明：**

- **必须**：在修改前备份原始文件
- **必须**：验证PlantUML程序可用性后再执行修复
- **禁止**：直接覆盖原始文件而不保留备份

### 2. 准确性原则

**要求说明：**

- **必须**：准确提取PlantUML代码块（包括开始和结束标记）
- **必须**：使用PlantUML官方程序进行语法校验
- **必须**：保留原始代码的缩进和格式
- **禁止**：修改非PlantUML代码块的内容

## 你必须执行的操作

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
- 为每个代码块创建单独的`.puml`文件
- 自动添加`@startuml`和`@enduml`标记（如果缺失）
- 默认输出到系统临时目录（如 `/tmp/plantuml_<filename>/`），避免被git管理
- 使用 `-o` 参数可以指定输出目录

### 操作3：校验PlantUML语法

**执行步骤：**

```bash
python3 {{ rule_file_dir }}/plantuml_fix.py validate <filename>_plantuml/
```

或直接使用plantuml命令：

```bash
plantuml -checkonly <filename>_plantuml/*.puml
```

### 操作4：AI修复.puml文件

**执行步骤：**

1. 根据校验错误信息，使用`edit_file`工具修复`.puml`文件
2. 常见修复包括：
   - 修复箭头语法（`-->`、`->`等）
   - 添加缺失的分号
   - 修复注释格式
   - 添加缺失的`@startuml`/`@enduml`标记

### 操作5：将修复后的内容写回Markdown

**执行步骤：**

```bash
python3 {{ rule_file_dir }}/plantuml_fix.py writeback <markdown_file> <puml_dir>
```

脚本会：

- 自动备份原始Markdown文件（`.bak`后缀）
- 将`.puml`文件内容替换回对应的PlantUML代码块
- 保持Markdown文件的其他内容不变

## 检查清单

在完成任务后，你必须确认：

- [ ] 脚本文件已创建在 `{{ rule_file_dir }}/plantuml_fix.py`
- [ ] 规则文件已创建在 `{{ rule_file_dir }}/plantuml_fix.md`
- [ ] 脚本具有可执行权限
- [ ] PlantUML程序已正确安装
- [ ] 测试文件中的PlantUML代码块能被正确提取
- [ ] 修复后的代码能通过PlantUML语法校验
- [ ] 修复后的内容已正确写回Markdown文件

## 相关资源

- PlantUML官方文档：https://plantuml.com/
- PlantUML语法参考：https://plantuml.com/zh/
