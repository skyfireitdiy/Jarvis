<!-- markdownlint-disable MD029 -->
# 版本发布规则

## 规则简介

本规则用于规范Jarvis项目的版本发布流程，确保版本号的正确性、ReleaseNote的格式一致性，以及代码变更的准确性。

本规则适用于以下场景：

- **完整版本发布**：更新版本号、生成git tag、更新ReleaseNote
- **仅更新ReleaseNote**：只更新ReleaseNote.md文件，不创建git tag（适用于阶段性文档更新）

## 你必须遵守的原则

### 1. 语义化版本号

**要求说明：**

- **必须**：使用语义化版本格式 `vX.Y.Z`（如 `v1.2.0`）
- **必须**：版本号格式为 `v` + `主版本号` + `.` + `次版本号` + `.` + `修订号`
- **禁止**：跳过版本号或使用非标准格式（如 `v1.2`、`1.2.0`）

**版本号含义：**

- **主版本号（X）**：不兼容的API修改或破坏性变更
- **次版本号（Y）**：向下兼容的功能性新增
- **修订号（Z）**：向下兼容的问题修正

### 2. 代码变更获取准确性

**要求说明：**

- **必须**：使用 `git diff` 获取真实的代码变更
- **禁止**：使用 `git log` 或 commit 信息（可能不准确）
- **必须**：变更范围从最新tag到HEAD

**原因：** commit 信息可能存在不准确、不完整的情况，而 `git diff` 提供的是真实的代码差异。

### 3. ReleaseNote格式一致性

**要求说明：**

- **必须**：保持与现有ReleaseNote.md相同的格式结构
- **必须**：在文件头部插入新版本信息
- **必须**：使用统一的分类（新功能、修复、优化、文档等）

## 你必须执行的操作

### 操作1：获取最新版本号

> ⚠️ **注意**：在「仅更新ReleaseNote」模式下，此步骤用于获取基准版本号，但仍需执行。

**执行步骤：**

1. 执行命令获取最新tag：

```bash
git describe --tags --abbrev=0
```

2. 如果没有tag，使用默认版本 `v1.0.0`

**预期输出：** 最新版本号（如 `v1.1.1`）

### 操作2：获取当前日期

> ⚠️ **注意**：在「仅更新ReleaseNote」模式下，此步骤用于生成ReleaseNote中的日期，必须执行。

**执行步骤：**

1. 执行命令获取当前日期：

```bash
date +%Y-%m-%d
```

**预期输出：** 日期字符串（如 `2026-01-12`）

### 操作3：获取代码变更

**执行步骤：**

1. 首先获取变更统计信息：

```bash
git diff <latest_tag> HEAD --stat
```

2. 然后获取完整的代码差异：

```bash
git diff <latest_tag> HEAD
```

**注意事项：**

- `<latest_tag>` 替换为操作1获取的版本号
- 如果输出过大，可以限制行数（如 `| head -n 500`）

### 操作4：学习ReleaseNote格式

**执行步骤：**

1. 读取ReleaseNote.md前200行：

```bash
head -n 200 {{ git_root_dir }}/ReleaseNote.md
```

2. 分析以下内容：
   - 标题格式：`### Release Note - v{version} {date}`
   - 分类结构：新功能、修复、优化与重构、文档更新等
   - 图标使用：🚀、📌、🔧、📚、🧪、🗑️等
   - 子分类格式：`#### **分类名称**`
   - 条目格式：`- **标题**` + 详细说明

### 操作5：生成新版本ReleaseNote

**执行步骤：**

1. **计算新版本号**（根据用户提供的版本类型）：

```python
# 版本号计算逻辑
major, minor, patch = map(int, latest_version[1:].split('.'))

if version_type == 'major':
    new_version = f"v{major + 1}.0.0"
elif version_type == 'minor':
    new_version = f"v{major}.{minor + 1}.0"
elif version_type == 'patch':
    new_version = f"v{major}.{minor}.{patch + 1}"
else:
    raise ValueError("版本类型必须是 major、minor 或 patch")
```

2. **生成新版本内容**：

```markdown
### Release Note - {new_version} {date}
#### **🚀 新功能**

#### **📌 修复**

#### **🔧 优化与重构**

#### **📚 文档更新**

---
```

3. **在ReleaseNote.md头部插入新版本内容**：

   - 读取现有ReleaseNote.md内容
   - 在文件开头插入新版本内容
   - 保持原有格式和分隔符

**注意事项：**

- 必须在用户确认版本类型后再执行插入操作
- 插入位置为文件第一行之前
- 保持原有的 `---` 分隔符格式

## 检查清单

在完成任务后，你必须确认：

- [ ] 最新版本号获取成功（格式正确：vX.Y.Z）
- [ ] 日期获取成功（格式正确：YYYY-MM-DD）
- [ ] 代码变更已获取（使用了git diff而非git log）
- [ ] ReleaseNote格式已学习（了解分类和图标使用）
- [ ] 新版本号计算正确（根据版本类型）
- [ ] 新版本内容已插入到ReleaseNote.md头部
- [ ] ReleaseNote.md文件格式完整（无语法错误）

## 常见问题

### Q1：如何区分「完整版本发布」和「仅更新ReleaseNote」？

- **完整版本发布**：适用于正式发布，需要创建git tag，更新版本号，并更新ReleaseNote
- **仅更新ReleaseNote**：适用于阶段性文档整理或预览，只更新ReleaseNote.md文件，不创建git tag

执行前必须明确用户需求，选择合适的模式。

### Q2：如果没有git tag怎么办？

使用默认版本号 `v1.0.0` 作为基准版本。

### Q2：如何确定版本类型（major/minor/patch）？

必须询问用户确认版本类型，不能自行推断。

### Q3：在「仅更新ReleaseNote」模式下，是否需要更新版本号？

否。「仅更新ReleaseNote」模式下，仅在ReleaseNote.md中添加新版本说明，不修改项目中的版本号（如`__init__.py`、`setup.py`等），也不创建git tag。

### Q4：ReleaseNote内容如何生成？

根据操作3获取的代码变更，结合操作4学习的格式，人工分析并生成ReleaseNote内容。

## 相关资源

- ReleaseNote模板：`{{ git_root_dir }}/ReleaseNote.md`
- Git命令参考：`git diff --help`
- 语义化版本规范：<https://semver.org/lang/zh-CN/>
