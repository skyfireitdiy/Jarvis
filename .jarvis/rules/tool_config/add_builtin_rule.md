# 新增内置规则规范

## 规则简介

本规范用于指导如何在 Jarvis 系统中添加新的内置规则。内置规则是 Jarvis 系统自带的规则，适用于所有项目，存储在 `{{ jarvis_src_dir }}/builtin/rules/` 目录下。

## 规则文件基本要求

### 1. 文件位置（必须遵守）

**位置规范：**

- **必须**：内置规则文件应放置在 `{{ jarvis_src_dir }}/builtin/rules/` 目录下的对应分类子目录中

**文件路径：**

```text
{{ jarvis_src_dir }}/builtin/rules/<category>/<rule_name>.md
```

**分类说明：**

- `<category>`：规则分类，建议使用描述性目录名称
- **可选参考分类**（非强制限制）：
  - `architecture_design`（架构设计）
  - `code_quality`（代码质量）
  - `deployment`（部署规范）
  - `development_tools`（开发工具）
  - `development_workflow`（开发流程）
  - `performance`（性能优化）
  - `security`（安全规范）
  - `testing`（测试规范）
  - `tool_config`（工具配置）
  - `ui_design`（UI 设计）
- **可以创建新的分类目录**，根据实际需求组织规则

### 2. 规则注册（必须遵守）

**位置规范：**

- **必须**：创建规则文件后，必须将规则注册到内置规则列表中
- **注册文件位置：** `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md`

**注册要求：**

- **必须**：按照 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md` 的格式添加规则条目
- **必须**：提供规则的简短描述和文件路径
- **必须**：将规则添加到合适的分类下
- **必须**：使用 `{% raw %}{{ jarvis_src_dir }}{% endraw %}/builtin/rules/` 变量引用路径

**注册示例：**

```markdown
## 工具配置 (tool_config/)

- [规则名称]({% raw %}{{ jarvis_src_dir }}{% endraw %}/builtin/rules/tool_config/rule_name.md) - 规则简短描述
```

### 3. 文件命名规范（必须遵守）

**命名规则：**

- **必须**：使用小写字母
- **必须**：使用下划线 `_` 分隔单词
- **必须**：使用 `.md` 后缀
- **禁止**：使用空格、连字符 `-` 或大写字母

**命名示例：**

- ✅ 正确：`code_review.md`, `tdd.md`, `security.md`
- ❌ 错误：`CodeReview.md`, `code-review.md`, `CODE_REVIEW.md`

**命名建议：**

- 使用简短、描述性的名称
- 反映规则的核心用途
- 避免过于通用的名称（如 `rule.md`）

### 4. 规则分类（必须遵守）

**分类体系：**

规则文件应放置在合适的分类子目录中。以下是常见的分类参考（**非强制限制，可根据需要创建新分类**）：

- **architecture_design**（架构设计）：
  - 设计模式、架构原则、代码组织结构等
  - 例如：SOLID 原则、整洁架构、架构图生成器

- **code_quality**（代码质量）：
  - 代码规范、审查标准、文档要求等
  - 例如：代码审查、文档编写、重构检查

- **deployment**（部署规范）：
  - 部署流程、发布规范、环境配置等
  - 例如：开源部署、版本发布

- **development_tools**（开发工具）：
  - 开发工具使用、脚本生成、工具配置等
  - 例如：脚本生成专家、技能开发规则

- **development_workflow**（开发流程）：
  - 开发方法论、工作流程、协作流程等
  - 例如：TDD、SDD、重构流程

- **performance**（性能优化）：
  - 性能分析、优化策略、资源管理等
  - 例如：性能优化、Rust 性能优化

- **security**（安全规范）：
  - 安全编码、漏洞分析、安全测试等
  - 例如：安全编码、安全漏洞分析

- **testing**（测试规范）：
  - 测试方法、测试框架使用、测试最佳实践等
  - 例如：Python 测试、Go 测试、C/C++ 测试

- **tool_config**（工具配置）：
  - 工具配置、规则管理等
  - 例如：新增规则规范、自助配置规则

- **ui_design**（UI 设计）：
  - 界面设计规范、主题配置等
  - 例如：暗色/亮色主题设计

**分类选择原则：**

1. **单一职责**：每个规则只属于一个分类
2. **核心主题**：选择规则最核心的主题对应的分类
3. **避免歧义**：如果规则涉及多个领域，选择最主要的应用场景
4. **参考现有**：优先参考 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md` 中同类规则所在的分类

### 5. 文件格式要求（必须遵守）

**Markdown 格式：**

- **必须**：使用 Markdown 格式
- **必须**：使用 UTF-8 编码
- **必须**：使用 LF 换行符（Unix 风格）

**结构要求：**

```markdown
# 规则标题

## 简介/背景

（可选）简要说明规则的用途和背景

## 你必须遵守的原则

（必需）规则的核心原则

### 具体要求1

**要求说明：**

- **必须**：具体要求
- **禁止**：禁止事项

## 你必须执行的操作

（必需）具体的执行步骤或规范

## 检查清单

（可选）完成后的验证项

- [ ] 检查项1
- [ ] 检查项2
```

### 6. 内容编写要求（必须遵守）

**语言风格：**

- **必须**：使用清晰、简洁的语言
- **必须**：使用肯定式表述（"必须"、"禁止"）
- **必须**：避免模糊的表达

**结构化要求：**

- 使用分级标题组织内容（`#`、`##`、`###`）
- 使用列表罗列要求（`-` 或 `1.`）
- 使用代码块提供示例
- 使用加粗强调关键词（`**必须**`、`**禁止**`）

**完整性要求：**

- 说明规则的适用场景
- 提供具体的示例代码
- 列出必须遵守的要求
- 列出禁止的事项
- 提供验证或检查清单

## Jinja2 变量使用指南

### 可用的内置变量

内置规则文件中可以使用以下 Jinja2 模板变量：

| 变量名                                       | 说明                 | 示例值                         |
| -------------------------------------------- | -------------------- | ------------------------------ |
| `{% raw %}{{ rule_file_dir }}{% endraw %}`   | 当前规则文件所在目录 | `/path/to/builtin/rules`       |
| `{% raw %}{{ git_root_dir }}{% endraw %}`    | Git 仓库根目录       | `/home/user/project`           |
| `{% raw %}{{ current_dir }}{% endraw %}`     | 当前工作目录         | `/home/user/project/src`       |
| `{% raw %}{{ jarvis_src_dir }}{% endraw %}`  | Jarvis 源码目录      | `/home/user/jarvis`            |
| `{% raw %}{{ jarvis_data_dir }}{% endraw %}` | Jarvis 数据目录      | `/home/user/.jarvis`           |

### 变量使用示例

#### 示例 1：引用其他规则文件

```markdown
### 相关规则

- 参考代码审查规则：`{% raw %}{{ rule_file_dir }}{% endraw %}/code_quality/code_review.md`
- 参考安全规则：`{% raw %}{{ rule_file_dir }}{% endraw %}/security/security.md`
```

#### 示例 2：指定项目路径

```markdown
### 文件放置位置

**测试文件必须放置在：**

- `{% raw %}{{ git_root_dir }}{% endraw %}/tests/`
- `{% raw %}{{ git_root_dir }}{% endraw %}/src/{% raw %}{{ module_name }}{% endraw %}/tests/`
```

## 规则模板

以下是一个完整的内置规则文件模板，可直接复制使用：

````markdown
# [规则名称]

## 规则简介

简要描述规则的用途、适用场景和预期效果。

## 你必须遵守的原则

### 1. 原则名称

**要求说明：**

- **必须**：具体要求1
- **必须**：具体要求2
- **禁止**：禁止事项

**示例：**

    ```python
    # 示例代码
    def example():
        pass
    ```

## 你必须执行的操作

### 操作1：操作名称

**执行步骤：**

1. 步骤1
2. 步骤2
3. 步骤3

**注意事项：**

- 注意事项1
- 注意事项2

## 检查清单

在完成任务后，你必须确认：

- [ ] 规则文件已创建在 `{{ jarvis_src_dir }}/builtin/rules/` 目录
- [ ] 规则已注册到 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md` 文件
- [ ] 规则注册格式符合规范

## 相关资源

- 参考文档：`related_rule.md`
````

## 最佳实践

### 1. 规则设计原则

- **单一职责**：每个规则只关注一个主题
- **可操作性**：规则必须具体、可执行
- **可验证**：规则结果必须可检查
- **简洁明了**：避免冗长和重复

### 2. 常见错误

- ❌ **规则过于抽象**："代码要写得好看"
- ✅ **规则具体明确**："函数长度不超过 50 行"

- ❌ **规则相互冲突**：规则 A 要求 X，规则 B 要求非 X
- ✅ **规则协调一致**：相关规则应相互补充

- ❌ **缺少示例**：只有文字描述，没有示例代码
- ✅ **提供示例**：包含正面和反面的示例

### 3. 规则维护

- 定期审查规则的适用性
- 根据项目发展更新规则
- 删除过时或不再使用的规则
- 记录规则变更历史

## 示例：创建一个内置规则

假设我们需要创建一个"Python 编码规范"规则：

### 步骤 1：创建文件

```bash
touch {{ jarvis_src_dir }}/builtin/rules/code_quality/python_coding_style.md
```

### 步骤 2：编写内容

````markdown
# Python 编码规范

## 规则简介

本规范定义了 Python 代码编写必须遵守的编码风格和最佳实践。

## 你必须遵守的编码原则

### 1. 命名规范

**要求：**

- **必须**：使用小写字母和下划线命名变量和函数
- **必须**：使用大写字母和下划线命名常量
- **必须**：使用首字母大写的驼峰命名法命名类
- **禁止**：使用单字母变量（除循环变量外）

**示例：**

    ```python
    # ✅ 正确
    user_name = "John"
    MAX_RETRY_COUNT = 3
    class UserService:
        pass

    # ❌ 错误
    userName = "John"  # 应使用下划线
    max_retry_count = 3  # 常量应大写
    class user_service:  # 类名应大写
        pass
    ```

### 2. 代码组织

**要求：**

- **必须**：每个函数不超过 50 行
- **必须**：使用类型注解
- **禁止**：使用通用的 `except:` 语句

**示例：**

    ```python
    # ✅ 正确
    def calculate_total(items: list[dict]) -> float:
        """计算总价"""
        total = 0.0
        for item in items:
            total += item['price']
        return total

    # ❌ 错误
    def calculate_total(items):
        total = 0
        for item in items:
            total += item['price']
        return total
    ```

## 检查清单

在完成任务后，你必须确认：

- [ ] 所有变量和函数使用下划线命名
- [ ] 所有常量使用大写字母
- [ ] 所有类使用首字母大写的驼峰命名
- [ ] 所有函数添加了类型注解
- [ ] 所有函数长度不超过 50 行
````

### 步骤 3：注册规则

在 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md` 中添加：

```markdown
## 代码质量 (code_quality/)

- [Python 编码规范]({% raw %}{{ jarvis_src_dir }}{% endraw %}/builtin/rules/code_quality/python_coding_style.md) - Python 代码编码规范和最佳实践
```

## 常见问题

### Q1：如何删除不再需要的内置规则？

**A：** 需要谨慎操作。1）确认没有项目依赖该规则；2）删除规则文件；3）从 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md` 中移除注册；4）提交 PR 并经过代码审查。

## 检查清单

在添加内置规则后，你必须确认：

- [ ] 规则文件已创建在 `{{ jarvis_src_dir }}/builtin/rules/<category>/` 目录
- [ ] 文件命名符合规范（小写、下划线、.md 后缀）
- [ ] 规则已注册到 `{{ jarvis_src_dir }}/builtin/rules/builtin_rules.md`
- [ ] 注册格式正确，使用了 `{% raw %}{{ jarvis_src_dir }}{% endraw %}/builtin/rules/` 变量
- [ ] 规则内容完整，包含必要的章节
- [ ] 规则使用 `load_rule` 工具可以正常加载
- [ ] 规则内容与其他规则保持一致的风格
- [ ] 如果规则依赖其他规则，已在文档中说明
