# Go2Rust 转译规则

## 规则简介

用于指导 Go 到 Rust 的代码转译过程，确保转译质量、功能一致性和类型安全。本规则涵盖从规划、实现、构建、审查、优化到评估的完整转译流程。

⚠️ **重要提醒**：Go 到 Rust 转译是一项复杂的任务，必须保证每个指定接口的功能一致性，任何疏忽都可能导致严重的功能错误。

**支持的语言特性：**

- **Go 语言**：函数、结构体、接口、方法、goroutines、channels、slices、maps、error handling、defer、packages、go modules 等
- **并发模型**：goroutines、channels、select、sync.WaitGroup、sync.Mutex、sync.RWMutex 等
- **标准库**：strings、bytes、io、fmt、context、time、net 等

## 你必须遵守的原则

### 1. 任务管理原则（核心）

**要求说明：**

- **必须**：每个函数的转译过程都必须使用 `task_list_manager` 进行任务管理
- **必须**：在开始转译前创建任务列表，规划所有任务（规划、实现、构建、审查、优化、评估）
- **必须**：使用 task_list_manager 的 `add_tasks` 操作添加所有子任务
- **必须**：按照依赖关系设置任务依赖（如：实现阶段依赖规划阶段）
- **禁止**：跳过 task_list_manager，直接执行任务

**多层级任务列表要求：**

Go 到 Rust 转译是一个复杂的流程，需要根据转译规模建立不同层级的任务列表：

1. **目录级任务列表**（按需）
   - **何时需要**：转译整个目录或多个相关目录时
   - **任务内容**：规划目录结构、模块组织、依赖关系等
   - **子任务**：包含该目录下所有文件的转译任务
   - **示例场景**：转译 `pkg/utils/` 目录下的所有 Go 文件（`.go`）

2. **文件级任务列表**（按需）
   - **何时需要**：转译单个文件或多个相关函数/结构体时
   - **任务内容**：规划文件模块位置、函数/结构体分组、共享类型定义等
   - **子任务**：包含该文件中所有函数/结构体的转译任务
   - **示例场景**：
     - 转译 `hash.go` 文件中的所有哈希相关函数和结构体
     - 转译 `http_handler.go` 文件中的 HTTP 处理器结构体

3. **函数/结构体级任务列表**（必须）
   - **何时需要**：转译单个函数或结构体时（这是最小粒度，必须创建）
   - **任务内容**：规划函数/结构体签名、实现策略、测试用例等
   - **子任务**：包含该函数/结构体的规划、实现、构建、审查、优化、评估阶段
   - **示例场景**：
     - 转译单个函数 `calculateHash`
     - 转译单个结构体 `HTTPServer` 及其方法

**任务列表层级关系：**

- 目录级任务列表 → 文件级任务列表 → 函数/结构体级任务列表
- 上级任务列表的子任务可以是下级任务列表
- 如果只转译单个函数，只需创建函数级任务列表
- 如果转译多个函数但属于同一文件，可以创建文件级任务列表，包含多个函数级子任务
- 如果转译多个文件，可以创建目录级任务列表，包含多个文件级子任务

**任务列表要求：**

- 任务类型：复杂任务使用 `sub` 类型，简单任务使用 `main` 类型
- 任务描述：每个任务必须包含约束条件、必须要求、禁止事项、验证标准
- 预期输出：必须使用结构化格式列出预期输出
- 验证方法：任务完成后必须提供验证方法说明
- **Go 代码位置信息**：**必须**在每个子任务中包含原始 Go 代码的行号位置信息
  - 函数/结构体级任务：必须包含 Go 函数/结构体所在的文件路径和行号范围
    - Go：`path/to/file.go:42-67`
  - 文件级任务：必须包含 Go 文件的路径（`.go`）
  - 目录级任务：必须包含 Go 目录的路径（如：`path/to/dir/`）
  - 位置信息应包含在 `background` 字段或 `task_desc` 字段中

**示例：**

#### 示例1：函数级任务列表（必须）

```json
// ✅ 正确：函数级任务列表（包含 Go 代码行号位置信息）
{
  "action": "add_tasks",
  "main_goal": "转译函数 Foo",
  "background": "Go 函数 Foo 位于 path/to/foo.go:42-67，功能是...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "为函数 Foo (path/to/foo.go:42-67) 选择模块位置和设计 Rust 签名...",
      "expected_output": "- 模块路径：src/foo.rs\n- Rust 签名：pub fn foo(...) ...\n- Go 代码位置：path/to/foo.go:42-67\n- 规划文档：docs/transpilation/foo_planning.md",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "实现阶段",
      "task_desc": "使用 TDD 方法实现函数 Foo (path/to/foo.go:42-67)...",
      "expected_output": "- 测试用例已编写\n- 实现已完成\n- Go 代码位置：path/to/foo.go:42-67\n- 实现文档：docs/transpilation/foo_implementation.md",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "构建阶段",
      "task_desc": "运行 cargo test 并修复构建问题（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 所有测试通过\n- 无编译错误\n- Go 代码位置：path/to/foo.go:42-67\n- 构建文档：docs/transpilation/foo_build.md",
      "agent_type": "sub",
      "dependencies": ["实现阶段"]
    },
    {
      "task_name": "审查阶段",
      "task_desc": "审查代码质量、功能一致性、测试完备性（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 审查报告\n- 问题列表\n- Go 代码位置：path/to/foo.go:42-67\n- 审查文档：docs/transpilation/foo_review.md",
      "agent_type": "sub",
      "dependencies": ["构建阶段"]
    },
    {
      "task_name": "优化阶段",
      "task_desc": "修复审查发现的问题并验证（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 问题已修复\n- 所有测试通过\n- Go 代码位置：path/to/foo.go:42-67\n- 优化文档：docs/transpilation/foo_optimization.md",
      "agent_type": "sub",
      "dependencies": ["审查阶段"]
    },
    {
      "task_name": "评估阶段",
      "task_desc": "使用子agent对整体效果进行评估，检查功能对齐情况（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 评估报告\n- 功能对齐检查结果\n- 如有问题，创建优化子任务\n- Go 代码位置：path/to/foo.go:42-67\n- 评估文档：docs/transpilation/foo_evaluation.md",
      "agent_type": "sub",
      "dependencies": ["优化阶段"]
    }
  ]
}
```

#### 示例2：文件级任务列表（按需）

```json
// ✅ 正确：文件级任务列表（转译 hash.go 文件，包含 Go 代码行号位置信息）
{
  "action": "add_tasks",
  "main_goal": "转译文件 hash.go",
  "background": "Go 文件 hash.go 包含多个哈希相关函数：HashInit (hash.go:15-45), HashUpdate (hash.go:47-78), HashFinal (hash.go:80-110)...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "规划 hash.go 的模块位置和整体结构...",
      "expected_output": "- 模块路径：src/hash.rs\n- 共享类型定义\n- 函数分组方案\n- Go 文件位置：hash.go",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "转译函数 HashInit",
      "task_desc": "转译函数 HashInit (hash.go:15-45)（包含规划、实现、构建、审查、优化、评估）...",
      "expected_output": "- HashInit 函数已转译完成\n- 测试通过\n- 功能对齐验证通过\n- Go 代码位置：hash.go:15-45",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译函数 HashUpdate",
      "task_desc": "转译函数 HashUpdate (hash.go:47-78)（包含规划、实现、构建、审查、优化、评估）...",
      "expected_output": "- HashUpdate 函数已转译完成\n- 测试通过\n- 功能对齐验证通过\n- Go 代码位置：hash.go:47-78",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译函数 HashFinal",
      "task_desc": "转译函数 HashFinal (hash.go:80-110)（包含规划、实现、构建、审查、优化、评估）...",
      "expected_output": "- HashFinal 函数已转译完成\n- 测试通过\n- 功能对齐验证通过\n- Go 代码位置：hash.go:80-110",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "文件级集成测试",
      "task_desc": "运行文件级集成测试，确保所有函数协同工作（转译自 hash.go）...",
      "expected_output": "- 集成测试通过\n- 文件转译完成\n- Go 文件位置：hash.go",
      "agent_type": "sub",
      "dependencies": [
        "转译函数 HashInit",
        "转译函数 HashUpdate",
        "转译函数 HashFinal"
      ]
    }
  ]
}
```

#### 示例3：目录级任务列表（按需）

```json
// ✅ 正确：目录级任务列表（转译 pkg/utils/ 目录，包含 Go 代码行号位置信息）
{
  "action": "add_tasks",
  "main_goal": "转译目录 pkg/utils/",
  "background": "Go 目录 pkg/utils/ 包含多个工具文件：string.go, math.go, memory.go...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "规划目录结构、模块组织、依赖关系（转译自 pkg/utils/）...",
      "expected_output": "- Rust 模块结构规划\n- 依赖关系图\n- 转译顺序\n- Go 目录位置：pkg/utils/",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "转译文件 string.go",
      "task_desc": "转译 string.go 文件（包含该文件的所有函数和结构体，位于 pkg/utils/string.go）...",
      "expected_output": "- string.go 已转译完成\n- 所有函数和结构体测试通过\n- 功能对齐验证通过\n- Go 文件位置：pkg/utils/string.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译文件 math.go",
      "task_desc": "转译 math.go 文件（包含该文件的所有函数和结构体，位于 pkg/utils/math.go）...",
      "expected_output": "- math.go 已转译完成\n- 所有函数和结构体测试通过\n- 功能对齐验证通过\n- Go 文件位置：pkg/utils/math.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译文件 memory.go",
      "task_desc": "转译 memory.go 文件（包含该文件的所有函数和结构体，位于 pkg/utils/memory.go）...",
      "expected_output": "- memory.go 已转译完成\n- 所有函数和结构体测试通过\n- 功能对齐验证通过\n- Go 文件位置：pkg/utils/memory.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "目录级集成测试",
      "task_desc": "运行目录级集成测试，确保所有模块协同工作（转译自 pkg/utils/）...",
      "expected_output": "- 集成测试通过\n- 目录转译完成\n- Go 目录位置：pkg/utils/",
      "agent_type": "sub",
      "dependencies": [
        "转译文件 string.go",
        "转译文件 math.go",
        "转译文件 memory.go"
      ]
    }
  ]
}
```

```bash
# ❌ 错误：直接执行，未使用 task_list_manager
echo "开始转译函数 Foo"
# 直接编写代码，没有任务管理
```

### 2. TDD 开发原则

**要求说明：**

- **必须**：先写测试（#[cfg(test)] mod tests），基于 Go 函数/结构体行为设计测试用例
- **必须**：编写实现使测试通过，确保与 Go 语义等价
- **必须**：优化代码，保持测试通过（重构阶段）
- **禁止**：在没有测试的情况下直接编写实现代码
- **禁止**：使用 `todo!` 或 `unimplemented!` 作为占位符

**Go 特有考虑：**

- 结构体方法需要分别测试公共接口和私有实现（通过公共接口）
- 接口方法需要测试不同的实现类型
- 并发代码需要测试 goroutine 的同步和通信行为
- 错误处理需要测试不同的错误情况（Go 的 error 返回值）
- defer 语句需要测试资源清理行为

**示例：**

```rust
// ❌ 错误：先写实现
pub fn calculate(x: i32) -> i32 {
    x * 2
}

#[cfg(test)]
mod tests {
    #[test]
    fn test_calculate() { }
}
```

```rust
// ✅ 正确：先写测试
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_calculate_normal() {
        assert_eq!(calculate(5), 10);
    }

    #[test]
    fn test_calculate_zero() {
        assert_eq!(calculate(0), 0);
    }
}

pub fn calculate(x: i32) -> i32 {
    x * 2
}
```

### 3. 功能一致性原则

**要求说明：**

- **必须**：核心功能定义与 Go 实现一致（主要目的和预期行为）
- **允许**：安全改进导致的行为不一致（修复 nil 指针解引用、数据竞争等安全漏洞）
- **忽略**：语言差异导致的行为不一致（panic 恢复、goroutine 调度等）
- **允许**：使用不同的类型设计、错误处理方式、资源管理方式
- **禁止**：改变核心功能逻辑

**说明：** 核心功能指函数/结构体的主要目的（如"计算哈希值"、"解析字符串"、"管理 HTTP 连接"），不包括实现细节。

**Go 特有考虑：**

- 结构体的封装性：保持公共接口一致（Go 首字母大写导出），内部实现可以不同
- 接口关系：保持接口定义和实现方法一致
- 并发模型：保持并发行为一致，但可以使用不同的并发原语
- 错误处理：Go 的多返回值（value, error）可以转换为 Rust 的 Result<T, E>
- defer 语义：可以使用 Rust 的 Drop trait 实现类似的资源清理

### 4. 模块化设计原则

**要求说明：**

- **必须**：按功能内聚与依赖方向选择模块，避免循环依赖
- **必须**：模块路径必须位于 crate 的 src/ 目录下
- **必须**：优先将函数放置到已存在的模块中
- **允许**：必要时创建新的子模块文件
- **禁止**：将不相关的功能放在同一模块

**Go 特有考虑：**

- Go 的 package（如 `package main`、`package utils`）映射到 Rust 的 module
- Go 的 import 路径（如 `github.com/user/repo/pkg`）映射到 Rust 的依赖管理（Cargo.toml）
- Go 的内部包（internal）映射到 Rust 的私有模块

### 5. 类型安全原则

**要求说明：**

- **必须**：优先使用 Rust 原生类型（i32/u32、&str/String、&[T]/&mut [T]、Result<T,E>）
- **禁止**：优先使用 Go 风格类型（空接口 interface{}、反射 reflect）
- **禁止**：使用 extern "C"（除非是 FFI 导出要求）
- **必须**：函数签名应遵循 Rust 最佳实践，不需要兼容 Go 的数据类型
- **禁止**：使用 `use ...::*` 通配导入

### 6. 文档记录原则

**要求说明：**

- **必须**：每个转译阶段都必须生成文档记录
- **必须**：文档记录应包含阶段执行过程、决策依据、遇到的问题和解决方案
- **必须**：文档记录应包含 Go 代码位置信息，便于追溯
- **必须**：文档记录应使用结构化格式（Markdown），便于阅读和维护
- **必须**：文档记录应在阶段完成后立即生成，确保信息准确完整
- **禁止**：跳过文档记录，直接进入下一阶段

**文档记录要求：**

- 文档格式：使用 Markdown 格式
- 文档位置：建议保存在 `docs/transpilation/` 目录下，按函数/文件/目录组织
- 文档命名：使用清晰的命名规则（如：`function_name_planning.md`、`file_name_implementation.md`）
- 文档内容：必须包含阶段概述、执行过程、关键决策、问题与解决方案、验证结果
- 文档链接：在任务列表的预期输出中包含文档路径

## 你必须执行的操作

**重要提示：** 在开始转译前，必须根据转译规模选择合适的任务列表层级：

- **转译单个函数**：创建函数级任务列表（必须）
- **转译单个文件或多个相关函数**：创建文件级任务列表，包含多个函数级子任务（按需）
- **转译整个目录或多个相关目录**：创建目录级任务列表，包含多个文件级子任务（按需）

以下操作阶段适用于所有层级的任务列表，但具体执行粒度取决于任务列表层级。

### 阶段 1：规划阶段

#### 操作1：记录 Go 代码位置信息

- **必须**：记录原始 Go 代码的位置信息
  - 函数/结构体级：记录 Go 函数/结构体所在的文件路径和行号范围
    - Go：`path/to/file.go:42-67`
  - 文件级：记录 Go 文件的完整路径（`.go`）
  - 目录级：记录 Go 目录的路径（如：`path/to/dir/`）
- **必须**：将位置信息包含在任务描述、背景信息或预期输出中
- **必须**：确保位置信息准确，便于后续追溯和验证

#### 操作2：选择模块位置

- 分析函数的功能特性，确定所属的功能模块
- 检查 crate 目录结构，选择或创建合适的模块文件
- 确保模块路径位于 src/ 目录下
- 评估是否需要创建新的子模块文件

#### 操作3：设计 Rust 函数/结构体/特征签名

- 根据 Go 函数/结构体签名设计 Rust 函数/结构体/特征签名
- 优先使用 Rust 原生类型，避免 Go 风格类型
- 考虑使用 `Result<T, E>` 或 `Option<T>` 处理错误
- 如果是根符号，必须使用 `pub` 关键字
- **必须**：在函数/结构体注释中记录对应的 Go 代码位置信息（如：`/// 转译自 path/to/file.go:42-67`）

**Go 特有处理：**

- **结构体转结构体**：Go 结构体转换为 Rust 结构体，字段保持相似命名
- **方法转 impl**：Go 结构体方法转换为 Rust impl 块中的方法
- **接口转特征**：Go 接口转换为 Rust trait
- **嵌入字段转组合**：Go 嵌入字段转换为 Rust 组合或 trait
- **goroutines 转 async**：Go goroutine 转换为 Rust async/await（如果使用 Tokio 运行时）
- **channels 转换**：Go channel 转换为 Rust `std::sync::mpsc`（同步）或 `tokio::sync::mpsc`（异步）
- **多返回值转换**：Go 多返回值（value, error）转换为 Rust `Result<T, E>` 或元组
- **slices 映射**：Go slice 转换为 Rust `&[T]` / `Vec<T>`
- **maps 映射**：Go map 转换为 Rust `HashMap<K, V>`
- **nil 处理**：Go nil 指针/接口转换为 Rust `Option<T>`

#### 操作4：评估是否需要实现

以下情况可以跳过实现（设置 skip_implementation 为 true）：

- **已实现的函数/结构体**：函数/结构体已经在目标模块中实现，且功能与 Go 实现一致
- **资源释放类函数**：如 Close、defer 的资源清理等，通过 Drop trait 自动管理
- **已被库替代**：函数/结构体已被标准库或第三方 crate 替代，且功能完全一致
- **空实现或无意义函数**：Go 函数是空实现、简单返回常量
- **测试辅助函数**：Go 的测试辅助函数（如 `TestMain`），在 Rust 中有对应的测试框架

**重要**：跳过实现必须在 notes 字段中详细说明原因。

#### 操作5：生成规划阶段文档

- **必须**：生成规划阶段文档记录
- **必须**：文档包含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 模块选择决策和理由
  - Rust 函数签名设计说明
  - 实现必要性评估结果
  - 关键设计决策和考虑因素
- **必须**：文档保存到指定位置（如：`docs/transpilation/<function_name>_planning.md`）
- **必须**：在任务预期输出中包含文档路径

### 阶段 2：实现阶段

#### 操作1：编写测试用例

- 在 `#[cfg(test)] mod tests { ... }` 块中编写测试
- 测试用例必须覆盖：
  - 主要功能路径
  - 边界情况（空输入、极值、边界值）
  - 错误情况（如果 Go 实现有错误处理）
- 测试用例的预期结果必须与 Go 实现的行为一致
- 使用清晰的测试名称和适当的断言

**Go 特有测试要求：**

- **结构体测试**：测试所有公共方法，包括构造函数、字段访问器、修改器
- **接口测试**：测试接口的所有方法，包括不同的实现类型
- **并发测试**：测试 goroutine 的并发行为和同步原语（WaitGroup、Mutex、Channel）
- **错误处理测试**：Go 的 error 返回值转换为 Rust 的 Result，需要相应测试
- **defer 测试**：测试资源清理行为（使用 Drop trait）
- **nil 处理测试**：测试 nil 指针/接口的等价行为（Option::None）

#### 操作2：实现函数/结构体/特征

- 使测试通过，实现与 Go 语义等价的功能
- 使用 Rust 原生类型和惯用法
- 考虑使用 RAII 管理资源
- 添加中文注释说明逻辑

**Go 特有实现要求：**

- **结构体实现**：将 Go 结构体转换为 Rust 结构体，字段保持相似命名（使用 snake_case）
- **方法实现**：Go 结构体方法转换为 Rust impl 块中的方法
- **接口实现**：使用 Rust trait 实现 Go 接口，为结构体实现 trait
- **goroutine 实现**：如果使用并发，考虑使用 Tokio async/await
- **channel 实现**：
  - 无缓冲 channel → `tokio::sync::mpsc::channel(0)`
  - 有缓冲 channel → `tokio::sync::mpsc::channel(capacity)`
- **WaitGroup 实现**：使用 `tokio::task::JoinSet` 或 `Barrier`
- **Mutex 实现**：使用 `std::sync::Mutex` 或 `tokio::sync::Mutex`
- **select 实现**：使用 `tokio::select!` 宏
- **defer 实现**：使用 `Drop` trait 或 `scopeguard` 模式
- **错误处理实现**：
  - Go 的 `value, error` → Rust 的 `Result<T, E>`
  - Go 的 `nil error` → Rust 的 `Ok(value)`
  - Go 的 `non-nil error` → Rust 的 `Err(error)`
- **panic/recover 实现**：使用 `panic!` 和 `catch_unwind`

#### 操作3：重构代码

- 优化代码结构，保持测试通过
- 改进代码可读性和可维护性
- 确保不改变功能行为

#### 操作4：生成实现阶段文档

- **必须**：生成实现阶段文档记录
- **必须**：文档包含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 测试用例设计说明和覆盖情况
  - 实现策略和关键实现细节
  - 遇到的实现难点和解决方案
  - 重构说明和改进点
  - 代码变更摘要
- **必须**：文档保存到指定位置（如：`docs/transpilation/<function_name>_implementation.md`）
- **必须**：在任务预期输出中包含文档路径

### 阶段 3：构建阶段

#### 操作1：运行 cargo test

- 确保所有测试用例都能通过
- 修复编译错误和测试失败
- 如果修复过程中导致其他测试失败，必须一并修复

#### 操作2：修复构建问题

- 处理编译错误（类型不匹配、缺少依赖等）
- 处理测试失败（断言错误、panic 等）
- 最小化修改，避免无关重构
- 使用精确的 use 语句，禁止通配导入

#### 操作3：生成构建阶段文档

- **必须**：生成构建阶段文档记录
- **必须**：文档包含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 构建过程记录（编译命令、测试命令）
  - 遇到的构建问题和错误信息
  - 问题分析和解决方案
  - 修复后的验证结果
  - 构建时间统计（如适用）
- **必须**：文档保存到指定位置（如：`docs/transpilation/<function_name>_build.md`）
- **必须**：在任务预期输出中包含文档路径

### 阶段 4：审查阶段

**审查优先级：**

1. **测试破坏性检查**（最高优先级）
   - 检查 `#[test]` 标记是否丢失
   - 检查 `#[test]` 标记是否重复
   - 检查代码插入位置是否破坏测试结构
   - 验证测试仍然可以运行

2. **严重问题检查**
   - 空指针解引用风险
   - 越界访问问题
   - 会导致 panic 的严重错误
   - 数据竞争风险（goroutine 转换时）

3. **测试用例完备性检查**
   - 是否有测试用例
   - 是否覆盖主要功能
   - 是否覆盖边界情况
   - 是否覆盖错误情况

4. **功能一致性检查**
   - 核心输入输出是否一致
   - 主要功能逻辑是否一致
   - 允许安全改进导致的行为不一致
   - **Go 特有**：
     - 结构体的公共接口是否一致
     - 接口方法是否完整实现
     - 并发行为是否保持一致
     - 错误处理是否正确转换

5. **破坏性变更检测**
   - 检查模块导出变更
   - 检查类型定义变更
   - 允许签名不一致（只要功能实现）

6. **文件结构合理性检查**
   - 模块文件位置是否合理
   - 文件命名是否符合规范
   - 模块导出是否正确

**操作：** 根据审查结果，提供详细的问题描述、修复建议和修复代码示例。

#### 操作：生成审查阶段文档

- **必须**：生成审查阶段文档记录
- **必须**：文档包含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 审查范围和方法
  - 审查结果摘要（按优先级分类）
  - 发现的问题列表（详细描述、严重程度、影响范围）
  - 修复建议和代码示例
  - 审查结论和改进方向
- **必须**：文档保存到指定位置（如：`docs/transpilation/<function_name>_review.md`）
- **必须**：在任务预期输出中包含文档路径

### 阶段 5：优化阶段

#### 操作1：修复审查发现的问题

- 按优先级修复问题（严重问题 > 功能一致性问题 > 其他问题）
- 最小化修改，避免无关重构
- 修复后必须重新运行 cargo test 验证

#### 操作2：验证所有测试通过

- 确保当前函数的测试通过
- 确保其他函数的测试没有因修改而失败
- 如果引入回归问题，必须一并修复

#### 操作3：生成优化阶段文档

- **必须**：生成优化阶段文档记录
- **必须**：文档包含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 优化的问题列表和优先级
  - 每个问题的修复方案和执行过程
  - 修复后的验证结果
  - 回归测试结果
  - 优化效果总结
- **必须**：文档保存到指定位置（如：`docs/transpilation/<function_name>_optimization.md`）
- **必须**：在任务预期输出中包含文档路径

### 阶段 6：评估阶段

**重要说明：** 评估阶段必须使用子 agent 进行独立评估，确保客观性和全面性。

#### 操作1：使用子 agent 进行整体效果评估

- **必须**：使用子 agent（`agent_type: "sub"`）对转译结果进行独立评估
- **必须**：评估范围包括：
  - 功能对齐检查：对比 Go 实现和 Rust 实现的核心功能是否一致
  - 测试覆盖检查：测试用例是否充分覆盖 Go 函数/结构体的行为
  - 边界情况检查：边界条件和错误处理是否与 Go 实现一致
  - 性能影响评估：Rust 实现的性能是否满足要求（如适用）
  - 代码质量评估：代码可读性、可维护性、类型安全性
  - **Go 特有**：
    - 结构体的封装性是否保持
    - 接口实现是否完整
    - 并发行为是否一致（goroutine、channel、mutex）
    - 错误处理是否正确转换（error 返回值 → Result）
    - defer 语义是否正确实现（Drop trait）
- **必须**：生成详细的评估报告，包含：
  - 评估范围和方法
  - 功能对齐检查结果（逐项对比）
  - 发现的问题列表（如有）
  - 改进建议（如有）
- **必须**：将评估报告保存为文档（如：`docs/transpilation/<function_name>_evaluation.md`）
- **必须**：在任务预期输出中包含文档路径

#### 操作2：处理功能未对齐问题

- **必须**：如果评估发现功能未对齐问题，必须创建优化子任务
- **必须**：优化子任务应包含：
  - 问题描述：详细说明功能未对齐的具体表现
  - 对齐目标：明确需要对齐的功能点
  - 修复计划：制定修复方案和验证方法
  - 依赖关系：依赖评估阶段
- **必须**：执行优化子任务，修复功能对齐问题
- **必须**：修复后重新进行评估，直到功能完全对齐

#### 操作3：迭代优化直到完全对齐

- **必须**：如果重新评估仍发现功能未对齐，继续创建优化子任务
- **必须**：重复"优化 → 评估"循环，直到：
  - 所有功能对齐检查通过
  - 评估报告确认功能完全对齐
  - 所有测试用例通过
- **禁止**：在功能未完全对齐的情况下结束转译任务

**评估报告模板：**

```markdown
## 转译评估报告

### 评估范围

- 转译对象：[函数名/结构体名/文件名/目录名]
- Go 代码位置：[文件路径:行号范围]（如：path/to/file.go:42-67）
- 评估时间：[时间戳]
- 评估方法：[使用的评估方法]

### 功能对齐检查结果

1. [功能点1]：✅ 对齐 / ❌ 未对齐
   - Go 实现位置：[文件路径:行号范围]
   - Go 实现行为：[描述]
   - Rust 实现位置：[文件路径:行号范围]
   - Rust 实现行为：[描述]
   - 差异分析：[如有差异，说明原因]

2. [功能点2]：✅ 对齐 / ❌ 未对齐
   - Go 实现位置：[文件路径:行号范围]
     ...

### 测试覆盖检查

- 主要功能路径：✅ 已覆盖 / ❌ 未覆盖
- 边界情况：✅ 已覆盖 / ❌ 未覆盖
- 错误情况：✅ 已覆盖 / ❌ 未覆盖
- **Go 特有**：
  - 结构体的所有公共方法：✅ 已覆盖 / ❌ 未覆盖
  - 接口的所有方法：✅ 已覆盖 / ❌ 未覆盖
  - 并发行为（goroutine、channel）：✅ 已覆盖 / ❌ 未覆盖
  - 错误处理（error → Result）：✅ 已覆盖 / ❌ 未覆盖

### 发现的问题

1. [问题1]：[详细描述]
2. [问题2]：[详细描述]
   ...

### 改进建议

1. [建议1]：[详细说明]
2. [建议2]：[详细说明]
   ...

### 结论

- 功能对齐状态：✅ 完全对齐 / ❌ 部分对齐 / ❌ 未对齐
- 是否需要优化：是 / 否
- 下一步行动：[具体行动]
```

**阶段文档模板：**

每个阶段的文档应遵循以下基本结构：

```markdown
# [阶段名称]文档 - [函数名/结构体名/文件名/目录名]

## 基本信息

- Go 代码位置：[文件路径:行号范围]（如：path/to/file.go:42-67）
- 转译对象：[函数名/结构体名/文件名/目录名]
- 阶段：[规划/实现/构建/审查/优化/评估]
- 执行时间：[时间戳]
- 执行人员：[agent名称]

## 阶段概述

[简要描述本阶段的目标和主要工作]

## 执行过程

[详细记录执行步骤和过程]

## 关键决策

1. [决策1]：[决策内容和理由]
2. [决策2]：[决策内容和理由]
   ...

## 问题与解决方案

1. [问题1]：[问题描述]
   - 解决方案：[解决方案]
   - 结果：[解决结果]
2. [问题2]：[问题描述]
   ...

## 验证结果

- [验证项1]：✅ 通过 / ❌ 失败
- [验证项2]：✅ 通过 / ❌ 失败
  ...

## 总结

[阶段总结和下一步计划]
```

## Go 语言特性到 Rust 映射表

### 1. 并发模型映射

| Go 特性           | Rust 等价物                         | 备注                                     |
| ----------------- | ----------------------------------- | ---------------------------------------- |
| `go func()`       | `tokio::spawn(async move { ... })`  | 需要使用 Tokio 运行时                    |
| `chan T`          | `tokio::sync::mpsc::channel<T>`     | 异步 channel；同步使用 `std::sync::mpsc` |
| `<-chan`          | `receiver.recv()`                   | 接收操作                                 |
| `chan<-`          | `sender.send()`                     | 发送操作                                 |
| `close(chan)`     | `drop(sender)`                      | Rust 中 sender 被 drop 自动关闭          |
| `select`          | `tokio::select!`                    | 多路复用                                 |
| `sync.WaitGroup`  | `tokio::task::JoinSet` 或 `Barrier` | 等待多个任务完成                         |
| `sync.Mutex`      | `std::sync::Mutex`                  | 互斥锁                                   |
| `sync.RWMutex`    | `std::sync::RwLock`                 | 读写锁                                   |
| `sync.Once`       | `std::sync::OnceLock`               | 单次初始化                               |
| `context.Context` | `tokio::task::CancellationToken`    | 取消上下文                               |

### 2. 类型系统映射

| Go 类型       | Rust 等价物                            | 备注           |
| ------------- | -------------------------------------- | -------------- |
| `int`         | `i32` 或 `isize`                       | 根据平台选择   |
| `int32`       | `i32`                                  | 固定大小       |
| `int64`       | `i64`                                  | 固定大小       |
| `uint`        | `u32` 或 `usize`                       | 根据平台选择   |
| `float32`     | `f32`                                  | 单精度浮点     |
| `float64`     | `f64`                                  | 双精度浮点     |
| `string`      | `String` 或 `&str`                     | 所有权 vs 借用 |
| `[]T`         | `Vec<T>` 或 `&[T]`                     | 动态数组       |
| `[N]T`        | `[T; N]`                               | 固定大小数组   |
| `map[K]V`     | `HashMap<K, V>`                        | 哈希映射       |
| `*T`          | `&T` 或 `Box<T>`                       | 指针/堆分配    |
| `nil`         | `None`                                 | 空值           |
| `interface{}` | `dyn Any`                              | 类型擦除       |
| `error`       | `Result<T, E>`                         | 错误处理       |
| `chan T`      | `mpsc::Sender<T>`, `mpsc::Receiver<T>` | 通道           |

### 3. 结构体和方法映射

| Go 特性                    | Rust 等价物                      | 备注              |
| -------------------------- | -------------------------------- | ----------------- |
| `type T struct { ... }`    | `struct T { ... }`               | 结构体定义        |
| `func (t *T) Method() {}`  | `impl T { fn method(&self) {} }` | 方法定义          |
| `func (t T) Method() {}`   | `impl T { fn method(self) {} }`  | 值接收者方法      |
| `type T interface { ... }` | `trait T { ... }`                | 接口/特征         |
| `type U struct { T }`      | `struct U { t: T }`              | 嵌入结构体 → 组合 |
| `type U struct { *T }`     | `struct U { t: Box<T> }`         | 指针嵌入          |

### 4. 函数映射

| Go 特性                                     | Rust 等价物                | 备注              |
| ------------------------------------------- | -------------------------- | ----------------- |
| `func foo() {}`                             | `fn foo() {}`              | 函数定义          |
| `func foo() (T, error)`                     | `fn foo() -> Result<T, E>` | 多返回值 → Result |
| `func foo() (T, error) { return T{}, nil }` | `Ok(T{})`                  | 成功返回          |
| `func foo() (T, error) { return T{}, err }` | `Err(err)`                 | 错误返回          |
| `func foo() (T, T)`                         | `fn foo() -> (T, T)`       | 多值返回元组      |
| `vararg ...T`                               | `fn foo(args: &[T])`       | 可变参数          |
| `func foo(f func())`                        | `fn foo<F: Fn()>(f: F)`    | 函数作为参数      |
| `func foo() func()`                         | `fn foo() -> impl Fn()`    | 函数作为返回值    |

### 5. 控制流映射

| Go 特性                    | Rust 等价物                                    | 备注         |
| -------------------------- | ---------------------------------------------- | ------------ |
| `if err != nil { ... }`    | `match result { Ok(v) => ..., Err(e) => ... }` | 错误处理     |
| `defer f()`                | `Drop trait` 或 `scopeguard`                   | 延迟执行     |
| `panic("msg")`             | `panic!("msg")`                                | Panic        |
| `recover()`                | `catch_unwind()`                               | Panic 恢复   |
| `for i := 0; i < N; i++`   | `for i in 0..N {}`                             | C 风格循环   |
| `for range slice`          | `for item in slice {}`                         | 迭代         |
| `for i, v := range slice`  | `for (i, v) in slice.iter().enumerate() {}`    | 索引和值迭代 |
| `range map`                | `for (k, v) in map.iter() {}`                  | Map 迭代     |
| `range chan`               | `while let Some(v) = receiver.recv() {}`       | Channel 迭代 |
| `go`                       | `tokio::spawn(async { ... })`                  | Goroutine    |
| `select`                   | `tokio::select!`                               | 多路选择     |
| `switch v { case x: ... }` | `match v { x => ... }`                         | Switch/Match |

### 6. 包和模块映射

| Go 特性            | Rust 等价物       | 备注                 |
| ------------------ | ----------------- | -------------------- |
| `package main`     | `fn main() {}`    | 主包/函数            |
| `package foo`      | `mod foo {}`      | 模块定义             |
| `import "pkg"`     | `use pkg;`        | 导入模块             |
| `import _ "pkg"`   | -                 | Go 特有，Rust 无对应 |
| `import . "pkg"`   | `use pkg::*;`     | 通配导入（不推荐）   |
| `import foo "pkg"` | `use pkg as foo;` | 别名导入             |
| `go.mod`           | `Cargo.toml`      | 包管理文件           |
| `go build`         | `cargo build`     | 构建                 |
| `go test`          | `cargo test`      | 测试                 |
| `go vet`           | `cargo clippy`    | 静态分析             |

## 检查清单

### 任务管理检查清单

**多层级任务列表检查：**

- [ ] 已根据转译规模确定任务列表层级（目录级/文件级/函数级）
- [ ] 目录级任务列表（如需要）：已规划目录结构、模块组织、依赖关系
- [ ] 文件级任务列表（如需要）：已规划文件模块位置、函数分组、共享类型
- [ ] 函数级任务列表（必须）：已为每个函数创建任务列表
- [ ] 任务列表层级关系正确（目录级 → 文件级 → 函数级）

**任务列表质量检查：**

- [ ] 已使用 task_list_manager 创建任务列表
- [ ] 任务列表包含所有阶段（规划、实现、构建、审查、优化、评估）
- [ ] 任务类型正确（sub/main）
- [ ] 任务描述完整（包含约束条件、必须要求、禁止事项、验证标准）
- [ ] **每个子任务都包含 Go 代码行号位置信息**
- [ ] Go 代码位置信息格式正确（函数/结构体级：`file.go:start-end`，文件级：`file.go`，目录级：`dir/`）
- [ ] 预期输出结构化（使用分条列出格式）
- [ ] 预期输出中包含 Go 代码位置信息
- [ ] 任务依赖关系正确设置
- [ ] 已验证任务列表创建成功

### 规划阶段检查清单

- [ ] 已记录 Go 代码位置信息（文件路径和行号范围）
- [ ] Go 代码位置信息已包含在任务描述或背景信息中
- [ ] 已选择合适的模块位置
- [ ] 已设计符合 Rust 最佳实践的函数签名
- [ ] 函数/结构体/特征注释中包含对应的 Go 代码位置信息
- [ ] 对于 Go 结构体，已考虑转换为 Rust 结构体和方法
- [ ] 对于 Go 接口，已考虑转换为 Rust trait
- [ ] 对于 Go goroutine，已考虑转换为 Rust async/await
- [ ] 对于 Go channel，已考虑转换为 Rust channel
- [ ] 已评估是否需要实现（如跳过，已详细说明原因）
- [ ] 如果是根符号，签名包含 `pub` 关键字
- [ ] **已生成规划阶段文档记录**
- [ ] 规划文档包含所有必需内容（位置信息、决策、评估结果等）
- [ ] 规划文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 实现阶段检查清单

- [ ] 已先编写测试用例
- [ ] 测试用例覆盖主要功能、边界情况、错误情况
- [ ] 已实现函数使测试通过
- [ ] 未使用 `todo!` 或 `unimplemented!` 占位符
- [ ] 使用 Rust 原生类型和惯用法
- [ ] 注释使用中文
- [ ] 函数/结构体/特征注释中包含 Go 代码位置信息
- [ ] 对于 Go 结构体，已正确转换为 Rust 结构体和方法
- [ ] 对于 Go 接口，已正确转换为 Rust trait
- [ ] 对于 Go goroutine，已正确转换为 Rust async/await
- [ ] 对于 Go channel，已正确转换为 Rust channel
- [ ] 对于 Go 错误处理，已正确转换为 Result<T,E>
- [ ] 未使用 `use ...::*` 通配导入
- [ ] **已生成实现阶段文档记录**
- [ ] 实现文档包含所有必需内容（测试设计、实现策略、重构说明等）
- [ ] 实现文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 构建阶段检查清单

- [ ] 所有测试用例通过
- [ ] 无编译错误
- [ ] 修复过程未破坏其他测试
- [ ] 修改最小化，无无关重构
- [ ] **已生成构建阶段文档记录**
- [ ] 构建文档包含所有必需内容（构建过程、问题与解决方案、验证结果等）
- [ ] 构建文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 审查阶段检查清单

- [ ] 测试用例未被破坏（#[test] 标记完整）
- [ ] 无严重问题（空指针、越界等）
- [ ] 测试用例完备（覆盖主要功能、边界、错误）
- [ ] 核心功能与 Go 实现一致
- [ ] 对于 Go 结构体，公共接口与原始实现一致
- [ ] 对于 Go 接口，接口方法完整实现
- [ ] 对于 Go 并发，并发行为保持一致
- [ ] 文件结构合理
- [ ] 问题报告包含详细描述、修复建议和修复代码示例
- [ ] **已生成审查阶段文档记录**
- [ ] 审查文档包含所有必需内容（审查结果、问题列表、修复建议等）
- [ ] 审查文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 优化阶段检查清单

- [ ] 已按优先级修复所有问题
- [ ] 修复后所有测试通过
- [ ] 未引入回归问题
- [ ] 修改最小化
- [ ] **已生成优化阶段文档记录**
- [ ] 优化文档包含所有必需内容（优化问题、修复方案、验证结果等）
- [ ] 优化文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 评估阶段检查清单

- [ ] 已使用子 agent 进行独立评估
- [ ] 评估报告已生成，包含功能对齐检查结果
- [ ] 评估报告中包含 Go 代码位置信息
- [ ] 功能对齐检查已完成，逐项对比 Go 和 Rust 实现
- [ ] 对于 Go 结构体，已检查封装性和接口一致性
- [ ] 对于 Go 接口，已检查接口实现完整性
- [ ] 对于 Go 并发，已检查并发行为一致性
- [ ] 测试覆盖检查已完成
- [ ] 边界情况检查已完成
- [ ] 如发现功能未对齐问题，已创建优化子任务
- [ ] 优化子任务包含 Go 代码位置信息
- [ ] 优化子任务已执行并修复问题
- [ ] 修复后已重新评估，功能完全对齐
- [ ] 评估报告确认功能完全对齐
- [ ] 所有测试用例通过
- [ ] **已生成评估阶段文档记录**
- [ ] 评估文档包含所有必需内容（评估报告、功能对齐检查、问题与建议等）
- [ ] 评估文档已保存到指定位置
- [ ] 任务预期输出中包含文档路径

### 根符号特殊要求

如果函数是根符号（需要从 crate 外部访问）：

- [ ] 函数签名包含 `pub` 关键字
- [ ] 函数所在的模块已在 `src/lib.rs` 中导出（`pub mod <模块名>;`）
- [ ] 如果需要 FFI 导出，使用了 `#[no_mangle]` 和 `pub extern "C"`

## 相关资源

- 参考 TDD 规则：{{ rule_file_dir }}/../development_workflow/tdd.md
- 参考代码审查规则：{{ rule_file_dir }}/../code_quality/code_review.md
- 参考 Rust 性能优化：{{ rule_file_dir }}/../performance/rust_performance.md
