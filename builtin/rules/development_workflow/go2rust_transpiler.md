---
name: go2rust_transpiler
description: 当需要将Go代码转为Rust代码时触发。每当用户提及"Go到Rust"、"Go转Rust"、"Go迁移"时触发。不触发：仅编Rust代码不涉及Go转译；仅阅读Go代码不转；C/C++到Rust转译。
---

# Go2Rust 转译规则

## 规则简介

用于指导 Go 到 Rust 之代码转译过程，保转译质量、功能一致性与类型安全。本规则涵盖从规、现、构、审、优至评之完整转译流程。

⚠

**支持之语言特性：**

- **Go 语言**：函数、结构体、接口、方法、goroutines、channels、slices、maps、error handling、defer、packages、go modules 等
- **并发模型**：goroutines、channels、select、sync.WaitGroup、sync.Mutex、sync.RWMutex 等
- **标准库**：strings、bytes、io、fmt、context、time、net 等

## 汝必遵守之原则

### 1. 任务管原则（核心）

**要求说明：**

- **必**：每函数之转译过程皆须用 `task_list_manager` 进行任务管
- **必**：在开始转译前建任务列表，规全任务（规、现、构、审、优、评）
- **必**：用 task_list_manager 之 `add_tasks` 操作加全子任务
- **必**：按依赖关系设任务依赖（如：实现阶段依赖规划阶段）
- **禁**：跳过 task_list_manager，直接行任务

**多层级任务列表要求：**

Go 到 Rust 转译乃复杂流程，需据转译规模建立不同层级之任务列表：

1. **目录级任务列表**（按需）
   - **何时需要**：转译整个目录或多个相关目录时
   - **任务内容**：规目录结构、模块组、依赖关系等
   - **子任务**：含该目录下全文件之转译任务
   - **示例场景**：转译 `pkg/utils/` 目录下之所有 Go 文件（`.go`）

2. **文件级任务列表**（按需）
   - **何时需要**：转译单个文件或多个相关函数/结构体时
   - **任务内容**：规文件模块位置、函数/结构体组、共享类型定义等
   - **子任务**：含该文件中全函数/结构体之转译任务
   - **示例场景**：
     - 转译 `hash.go` 文件中之所有哈希相关函数与结构体
     - 转译 `http_handler.go` 文件中之 HTTP 处理器结构体

3. **函数/结构体级任务列表**（必）
   - **何时需要**：转译单个函数或结构体时（此乃最小粒度，必建）
   - **任务内容**：规函数/结构体签名、实现策略、测试用例等
   - **子任务**：含该函数/结构体之规、现、构、审、优、评
   - **示例场景**：
     - 转译单个函数 `calculateHash`
     - 转译单个结构体 `HTTPServer` 及其方法

**任务列表层级关系：**

- 目录级任务列表 → 文件级任务列表 → 函数/结构体级任务列表
- 上级任务列表之子任务可为下级任务列表
- 若只转译单个函数，只需建函数级任务列表
- 若转译多个函数但属同一文件，可建文件级任务列表，含多个函数级子任务
- 若转译多个文件，可建目录级任务列表，含多个文件级子任务

**任务列表要求：**

- 任务类型：复杂任务用 `sub` 类型，简单任务用 `main` 类型
- 任务描述：每任务必含约束条件、必要求、禁事项、验标准
- 预期输出：必用结构化格式列出预期输出
- 验方法：任务完成后必供验方法说明
- **Go 代码位置信息**：**必**在每子任务中含原始 Go 代码之行号位置信息
  - 函数/结构体级任务：必含 Go 函数/结构体所在之文件路径与行号范围
    - Go：`path/to/file.go:42-67`
  - 文件级任务：必含 Go 文件之路径（`.go`）
  - 目录级任务：必含 Go 目录之路径（如：`path/to/dir/`）
  - 位置信息应含于 `background` 字段或 `task_desc` 字段中

#### 示例1：函数级任务列表（必）

```json
// ✅ 正确：函数级任务列表（含 Go 代码行号位置信息）
{
  "action": "add_tasks",
  "main_goal": "转译函数 Foo",
  "background": "Go 函数 Foo 位于 path/to/foo.go:42-67，功能是...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "为函数 Foo (path/to/foo.go:42-67) 选模块位置与设 Rust 签名...",
      "expected_output": "- 模块路径：src/foo.rs\n- Rust 签名：pub fn foo(...) ...\n- Go 代码位置：path/to/foo.go:42-67\n- 规文档：docs/transpilation/foo_planning.md",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "实现阶段",
      "task_desc": "用 TDD 方法实现函数 Foo (path/to/foo.go:42-67)...",
      "expected_output": "- 测试用例已编\n- 现已完成\n- Go 代码位置：path/to/foo.go:42-67\n- 现文档：docs/transpilation/foo_implementation.md",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "构建阶段",
      "task_desc": "运 cargo test 并修构问题（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 全测试通过\n- 无编译错误\n- Go 代码位置：path/to/foo.go:42-67\n- 构文档：docs/transpilation/foo_build.md",
      "agent_type": "sub",
      "dependencies": ["实现阶段"]
    },
    {
      "task_name": "审查阶段",
      "task_desc": "审代码质量、功能一致性、测试完备性（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 审报告\n- 问题列表\n- Go 代码位置：path/to/foo.go:42-67\n- 审文档：docs/transpilation/foo_review.md",
      "agent_type": "sub",
      "dependencies": ["构建阶段"]
    },
    {
      "task_name": "优化阶段",
      "task_desc": "修审发现之问题并验（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 问题已修\n- 全测试通过\n- Go 代码位置：path/to/foo.go:42-67\n- 优文档：docs/transpilation/foo_optimization.md",
      "agent_type": "sub",
      "dependencies": ["审查阶段"]
    },
    {
      "task_name": "评估阶段",
      "task_desc": "用子agent对整体效果进行评，查功能对齐情况（转译自 path/to/foo.go:42-67）...",
      "expected_output": "- 评估报告\n- 功能对齐查结果\n- 如有问题，建优子任务\n- Go 代码位置：path/to/foo.go:42-67\n- 评文档：docs/transpilation/foo_evaluation.md",
      "agent_type": "sub",
      "dependencies": ["优化阶段"]
    }
  ]
}
```

#### 示例2：文件级任务列表（按需）

```json
// ✅ 正确：文件级任务列表（转译 hash.go 文件，含 Go 代码行号位置信息）
{
  "background": "Go 文件 hash.go 含多个哈希相关函数：HashInit (hash.go:15-45), HashUpdate (hash.go:47-78), HashFinal (hash.go:80-110)...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "规 hash.go 之模块位置和整体结构...",
      "expected_output": "- 模块路径：src/hash.rs\n- 共享类型定义\n- 函数组方案\n- Go 文件位置：hash.go",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "转译函数 HashInit",
      "task_desc": "转译函数 HashInit (hash.go:15-45)（含规、现、构、审、优、评）...",
      "expected_output": "- HashInit 函数已转译完成\n- 测试通过\n- 功能对齐验通过\n- Go 代码位置：hash.go:15-45",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译函数 HashUpdate",
      "task_desc": "转译函数 HashUpdate (hash.go:47-78)（含规、现、构、审、优、评）...",
      "expected_output": "- HashUpdate 函数已转译完成\n- 测试通过\n- 功能对齐验通过\n- Go 代码位置：hash.go:47-78",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译函数 HashFinal",
      "task_desc": "转译函数 HashFinal (hash.go:80-110)（含规、现、构、审、优、评）...",
      "expected_output": "- HashFinal 函数已转译完成\n- 测试通过\n- 功能对齐验通过\n- Go 代码位置：hash.go:80-110",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "文件级集成测试",
      "task_desc": "运文件级集成测试，保全函数协同工作（转译自 hash.go）...",
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
// ✅ 正确：目录级任务列表（转译 pkg/utils/ 目录，含 Go 代码行号位置信息）
{
  "action": "add_tasks",
  "main_goal": "转译目录 pkg/utils/",
  "background": "Go 目录 pkg/utils/ 含多个工具文件：string.go, math.go, memory.go...",
  "tasks_info": [
    {
      "task_name": "规划阶段",
      "task_desc": "规目录结构、模块组、依赖关系（转译自 pkg/utils/）...",
      "expected_output": "- Rust 模块结构规\n- 依赖关系图\n- 转译顺序\n- Go 目录位置：pkg/utils/",
      "agent_type": "sub",
      "dependencies": []
    },
    {
      "task_name": "转译文件 string.go",
      "task_desc": "转译 string.go 文件（含该文件的全函数和结构体，位于 pkg/utils/string.go）...",
      "expected_output": "- string.go 已转译完成\n- 全函数和结构体测试通过\n- 功能对齐验通过\n- Go 文件位置：pkg/utils/string.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译文件 math.go",
      "task_desc": "转译 math.go 文件（含该文件的全函数和结构体，位于 pkg/utils/math.go）...",
      "expected_output": "- math.go 已转译完成\n- 全函数和结构体测试通过\n- 功能对齐验通过\n- Go 文件位置：pkg/utils/math.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "转译文件 memory.go",
      "task_desc": "转译 memory.go 文件（含该文件的全函数和结构体，位于 pkg/utils/memory.go）...",
      "expected_output": "- memory.go 已转译完成\n- 全函数和结构体测试通过\n- 功能对齐验通过\n- Go 文件位置：pkg/utils/memory.go",
      "agent_type": "sub",
      "dependencies": ["规划阶段"]
    },
    {
      "task_name": "目录级集成测试",
      "task_desc": "运目录级集成测试，保全模块协同工作（转译自 pkg/utils/）...",
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
# ❌ 错误：直接行，未用 task_list_manager
echo "开始转译函数 Foo"
# 直接编代码，没有任务管
```

### 2. TDD 开发原则

**要求说明：**

- **必**：先写测试（#[cfg(test)] mod tests），基于 Go 函数/结构体行为设测试用例
- **必**：编写实现使测试通过，保与 Go 语义等价
- **必**：优代码，保持测试通过（重构阶段）
- **禁**：在没有测试之情况下直接编现代码
- **禁**：用 `todo!` 或 `unimplemented!` 作为占位符

**Go 特有虑：**

- 结构体方法需要分别测试公共接口和私有实现（通过公共接口）
- 接口方法需要测试不同之现类型
- 并发代码需要测试 goroutine 之同步和通信行为
- 错误处理需要测试不同之错误情况（Go 之 error 返回值）
- defer 语句需要测试资源清理行为

**示例：**

```rust
// ❌ 错误：先写现
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

- **必**：核心功能定义与 Go 现一致（主要目之和预期行为）
- **允许**：安全改进导致之行为不一致（修 nil 指针解引用、数据竞争等安全漏洞）
- **略**：语言差异导致之行为不一致（panic 恢复、goroutine 调度等）
- **允许**：用不同之类型设、错误处理方式、资源管方式
- **禁**：改变核心功能逻辑

**说明：** 核心功能指函数/结构体之主要目之（如"计算哈希值"、"解析字符串"、"管 HTTP 连接"），不包括实现细节。

**Go 特有虑：**

- 结构体之封装性：保持公共接口一致（Go 首字母大写导出），内部实现可以不同
- 接口关系：保持接口定义和现方法一致
- 并发模型：保持并发行为一致，但可以用不同之并发原语
- 错误处理：Go 之多返回值（value, error）可以转为 Rust 之 Result<T, E>
- defer 语义：可以用 Rust 之 Drop trait 实现类似之资源清理

### 4. 模块化设原则

**要求说明：**

- **必**：按功能内聚与依赖方向选模块，避免循环依赖
- **必**：模块路径必位于 crate 之 src/ 目录下
- **必**：优先将函数放置到已存在之模块中
- **允许**：必要时建新之子模块文件
- **禁**：将不相关之功能放在同一模块

**Go 特有虑：**

- Go 之 package（如 `package main`、`package utils`）映到 Rust 之 module
- Go 之 import 路径（如 `github.com/user/repo/pkg`）映到 Rust 之依赖管（Cargo.toml）
- Go 之内部包（internal）映到 Rust 之私有模块

### 5. 类型安全原则

**要求说明：**

- **必**：优先用 Rust 原生类型（i32/u32、&str/String、&[T]/&mut [T]、Result<T,E>）
- **禁**：优先用 Go 风格类型（空接口 interface{}、反射 reflect）
- **禁**：用 extern "C"（除非是 FFI 导出要求）
- **必**：函数签名应循 Rust 最佳实践，不需要兼容 Go 之数据类型
- **禁**：用 `use ...::*` 通配导入

### 6. 文档记原则

**要求说明：**

- **必**：每个转译阶段都必生文档记
- **必**：文档记应含阶段行过程、决策依据、遇到之问题和解决方案
- **必**：文档记应含 Go 代码位置信息，便于追溯
- **必**：文档记应用结构化格式（Markdown），便于阅读和维护
- **必**：文档记应在阶段完成后立即生，保信息准确完整
- **禁**：跳过文档记，直接进入下一阶段

**文档记要求：**

- 文档格式：用 Markdown 格式
- 文档位置：建议存在 `docs/transpilation/` 目录下，按函数/文件/目录组
- 文档名：用清晰之名规则（如：`function_name_planning.md`、`file_name_implementation.md`）
- 文档内容：必含阶段概述、行过程、关键决策、问题与解决方案、验结果
- 文档链接：在任务列表之预期输出中含文档路径

## 汝必行之操作

**重要提示：** 在开始转译前，必据转译规模选合适之任务列表层级：

- **转译单个函数**：建函数级任务列表（必）
- **转译单个文件或多个相关函数**：建文件级任务列表，含多个函数级子任务（按需）
- **转译整个目录或多个相关目录**：建目录级任务列表，含多个文件级子任务（按需）

以下操作阶段适用于所有层级之任务列表，但具体行粒度取决于任务列表层级。

### 阶段 1：规划阶段

#### 操作1：记 Go 代码位置信息

- **必**：记原始 Go 代码之位置信息
  - 函数/结构体级：记 Go 函数/结构体所在之文件路径和行号范围
    - Go：`path/to/file.go:42-67`
  - 文件级：记 Go 文件之完整路径（`.go`）
  - 目录级：记 Go 目录之路径（如：`path/to/dir/`）
- **必**：将位置信息含在任务描述、背景信息或预期输出中
- **必**：保位置信息准确，便于后续追溯和验

#### 操作2：选模块位置

- 析函数之功能特性，确定所属之功能模块
- 查 crate 目录结构，选或建合适之模块文件
- 保模块路径位于 src/ 目录下
- 评是否需要建新之子模块文件

#### 操作3：设 Rust 函数/结构体/特征签名

- 据 Go 函数/结构体签名设 Rust 函数/结构体/特征签名
- 优先用 Rust 原生类型，避免 Go 风格类型
- 虑用 `Result<T, E>` 或 `Option<T>` 处理错误
- 如果是根符号，必用 `pub` 关键字
- **必**：在函数/结构体注释中记对应之 Go 代码位置信息（如：`/// 转译自 path/to/file.go:42-67`）

**Go 特有处理：**

- **结构体转结构体**：Go 结构体转为 Rust 结构体，字段保持相似名
- **方法转 impl**：Go 结构体方法转为 Rust impl 块中之方法
- **接口转特征**：Go 接口转为 Rust trait
- **嵌入字段转组合**：Go 嵌入字段转为 Rust 组合或 trait
- **goroutines 转 async**：Go goroutine 转为 Rust async/await（若用 Tokio 运时）
- **channels 转**：Go channel 转为 Rust `std::sync::mpsc`（同步）或 `tokio::sync::mpsc`（异步）
- **多返回值转**：Go 多返回值（value, error）转为 Rust `Result<T, E>` 或元组
- **slices 映**：Go slice 转为 Rust `&[T]` / `Vec<T>`
- **maps 映**：Go map 转为 Rust `HashMap<K, V>`
- **nil 处理**：Go nil 指针/接口转为 Rust `Option<T>`

#### 操作4：评估是否需要实现

以下情况可以跳过实现（设 skip_implementation 为 true）：

- **已现之函数/结构体**：函数/结构体已经在目标模块中现，且功能与 Go 现一致
- **资源释放类函数**：如 Close、defer 之资源清理等，通过 Drop trait 自动管
- **已被库替代**：函数/结构体已被标准库或第三方 crate 替代，且功能完全一致
- **空实现或无意义函数**：Go 函数是空实现、简单返回常量
- **测试辅助函数**：Go 之测试辅助函数（如 `TestMain`），在 Rust 中有对应之测试框架

**重要**：跳过实现必在 notes 字段中详细说明原因。

#### 操作5：生规划阶段文档

- **必**：生规划阶段文档记
- **必**：文档含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 模块选决策和理由
  - Rust 函数签名设说明
  - 实现必要性评估结果
  - 关键设决策和虑因素
- **必**：文档存到指定位置（如：`docs/transpilation/<function_name>_planning.md`）
- **必**：在任务预期输出中含文档路径

### 阶段 2：实现阶段

#### 操作1：编测试用例

- 在 `#[cfg(test)] mod tests { ... }` 块中编测试
- 测试用例必覆：
  - 主要功能路径
  - 边界情况（空输入、极值、边界值）
  - 错误情况（如果 Go 现有错误处理）
- 测试用例之预期结果必与 Go 现之行为一致
- 用清晰之测试名称和适当之断言

**Go 特有测试要求：**

- **结构体测试**：测试所有公共方法，包括构造函数、字段访问器、修改器
- **接口测试**：测试接口之全方法，包括不同之现类型
- **并发测试**：测试 goroutine 之并发行为和同步原语（WaitGroup、Mutex、Channel）
- **错误处理测试**：Go 之 error 返回值转为 Rust 之 Result，需要相应测试
- **defer 测试**：测试资源清理行为（用 Drop trait）
- **nil 处理测试**：测试 nil 指针/接口之等价行为（Option::None）

#### 操作2：现函数/结构体/特征

- 使测试通过，实现与 Go 语义等价之功能
- 用 Rust 原生类型和惯用法
- 虑用 RAII 管资源
- 加中文注释说明逻辑

**Go 特有实现要求：**

- **结构体实现**：将 Go 结构体转为 Rust 结构体，字段保持相似名（用 snake_case）
- **方法实现**：Go 结构体方法转为 Rust impl 块中之方法
- **接口实现**：用 Rust trait 现 Go 接口，为结构体实现 trait
- **goroutine 实现**：若用并发，虑用 Tokio async/await
- **channel 实现**：
  - 无缓冲 channel → `tokio::sync::mpsc::channel(0)`
  - 有缓冲 channel → `tokio::sync::mpsc::channel(capacity)`
- **WaitGroup 实现**：用 `tokio::task::JoinSet` 或 `Barrier`
- **Mutex 实现**：用 `std::sync::Mutex` 或 `tokio::sync::Mutex`
- **select 实现**：用 `tokio::select!` 宏
- **defer 实现**：用 `Drop` trait 或 `scopeguard` 模式
- **错误处理实现**：
  - Go 之 `value, error` → Rust 之 `Result<T, E>`
  - Go 之 `nil error` → Rust 之 `Ok(value)`
  - Go 之 `non-nil error` → Rust 之 `Err(error)`
- **panic/recover 实现**：用 `panic!` 和 `catch_unwind`

#### 操作3：重构代码

- 优代码结构，保持测试通过
- 改进代码可读性和可维护性
- 保不改变功能行为

#### 操作4：生实现阶段文档

- **必**：生实现阶段文档记
- **必**：文档含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 测试用例设说明和覆情况
  - 实现策略和关键实现细节
  - 遇到之实现难点和解决方案
  - 重构说明和改进点
  - 代码变更摘要
- **必**：文档存到指定位置（如：`docs/transpilation/<function_name>_implementation.md`）
- **必**：在任务预期输出中含文档路径

### 阶段 3：构建阶段

#### 操作1：运 cargo test

- 保全测试用例都能通过
- 修编译错误和测试失败
- 如果修过程中导致其他测试失败，必一并修

#### 操作2：修构问题

- 处理编译错误（类型不匹配、缺少依赖等）
- 处理测试失败（断言错误、panic 等）
- 最小化修改，避免无关重构
- 用精确之 use 语句，禁通配导入

#### 操作3：生构建阶段文档

- **必**：生构建阶段文档记
- **必**：文档含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 构建过程记（编译命令、测试命令）
  - 遇到之构问题和错误信息
  - 问题析和解决方案
  - 修后之验结果
  - 构建时间统计（如适用）
- **必**：文档存到指定位置（如：`docs/transpilation/<function_name>_build.md`）
- **必**：在任务预期输出中含文档路径

### 阶段 4：审查阶段

**审查优先级：**

1. **测试破坏性查**（最高优先级）
   - 查 `#[test]` 标记是否丢失
   - 查 `#[test]` 标记是否重复
   - 查代码插入位置是否破坏测试结构
   - 验测试仍然可以运

2. **严重问题查**
   - 空指针解引用风险
   - 越界访问问题
   - 会导致 panic 之严重错误
   - 数据竞争风险（goroutine 转时）

3. **测试用例完备性查**
   - 是否有测试用例
   - 是否覆主要功能
   - 是否覆边界情况
   - 是否覆错误情况

4. **功能一致性查**
   - 核心输入输出是否一致
   - 主要功能逻辑是否一致
   - 允许安全改进导致之行为不一致
   - **Go 特有**：
     - 结构体之公共接口是否一致
     - 接口方法是否完整实现
     - 并发行为是否保持一致
     - 错误处理是否正确转

5. **破坏性变更检测**
   - 查模块导出变更
   - 查类型定义变更
   - 允许签名不一致（只要功能实现）

6. **文件结构合理性查**
   - 模块文件位置是否合理
   - 文件名是否符合规范
   - 模块导出是否正确

**操作：** 据审结果，供详细之问题描述、修建议和修代码示例。

#### 操作：生审查阶段文档

- **必**：生审查阶段文档记
- **必**：文档含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 审查范围和方法
  - 审结果摘要（按优先级分类）
  - 发现之问题列表（详细描述、严重程度、影响范围）
  - 修建议和代码示例
  - 审查结论和改进方向
- **必**：文档存到指定位置（如：`docs/transpilation/<function_name>_review.md`）
- **必**：在任务预期输出中含文档路径

### 阶段 5：优化阶段

#### 操作1：修审发现之问题

- 按优先级修问题（严重问题 > 功能一致性问题 > 其他问题）
- 最小化修改，避免无关重构
- 修后必重新运 cargo test 验

#### 操作2：验全测试通过

- 保当前函数之测试通过
- 保其他函数之测试没有因修改而失败
- 若引回归问题，必一并修

#### 操作3：生优化阶段文档

- **必**：生优化阶段文档记
- **必**：文档含以下内容：
  - Go 代码位置信息（文件路径和行号范围）
  - 优化之问题列表和优先级
  - 每个问题之修方案和行过程
  - 修后之验结果
  - 回归测试结果
  - 优化效果总结
- **必**：文档存到指定位置（如：`docs/transpilation/<function_name>_optimization.md`）
- **必**：在任务预期输出中含文档路径

### 阶段 6：评估阶段

**重要说明：** 评估阶段必用子 agent 进行独立评估，保客观性和全面性。

#### 操作1：用子 agent 进行整体效果评

- **必**：用子 agent（`agent_type: "sub"`）对转译结果进行独立评估
- **必**：评估范围包括：
  - 功能对齐查：对比 Go 现和 Rust 现之核心功能是否一致
  - 测试覆查：测试用例是否充分覆 Go 函数/结构体之行为
  - 边界情况查：边界条件和错误处理是否与 Go 现一致
  - 性能影响评：Rust 现之性能是否满足要求（如适用）
  - 代码质量评：代码可读性、可维护性、类型安全性
  - **Go 特有**：
    - 结构体之封装性是否保持
    - 接口实现是否完整
    - 并发行为是否一致（goroutine、channel、mutex）
    - 错误处理是否正确转（error 返回值 → Result）
    - defer 语义是否正确实现（Drop trait）
- **必**：生详细之评估报告，含：
  - 评估范围和方法
  - 功能对齐查结果（逐项对比）
  - 发现之问题列表（如有）
  - 改进建议（如有）
- **必**：将评估报告存为文档（如：`docs/transpilation/<function_name>_evaluation.md`）
- **必**：在任务预期输出中含文档路径

#### 操作2：处理功能未对齐问题

- **必**：若评发现功能未对齐问题，必建优子任务
- **必**：优子任务应含：
  - 问题描述：详细说明功能未对齐之具体表现
  - 对齐目标：明确需要对齐之功能点
  - 修计划：制定修方案和验方法
  - 依赖关系：依赖评估阶段
- **必**：行优子任务，修功能对齐问题
- **必**：修后重新进行评，直到功能完全对齐

#### 操作3：迭代优直到完全对齐

- **必**：如果重新评仍发现功能未对齐，继续建优子任务
- **必**：重复"优 → 评"循环，直到：
  - 全功能对齐查通过
  - 评估报告认功能完全对齐
  - 全测试用例通过
- **禁**：在功能未完全对齐之情况下结束转译任务

**评估报告模板：**

```markdown
## 转译评估报告

### 评估范围

- 转译对象：[函数名/结构体名/文件名/目录名]
- Go 代码位置：[文件路径:行号范围]（如：path/to/file.go:42-67）
- 评估时间：[时间戳]
- 评方法：[用的评方法]

### 功能对齐查结果

1. [功能点1]：✅ 对齐 / ❌ 未对齐
   - Go 现位置：[文件路径:行号范围]
   - Go 现行为：[描述]
   - Rust 现位置：[文件路径:行号范围]
   - Rust 现行为：[描述]
   - 差异析：[如有差异，说明原因]

2. [功能点2]：✅ 对齐 / ❌ 未对齐
   - Go 现位置：[文件路径:行号范围]
     ...

### 测试覆查

- 主要功能路径：✅ 已覆 / ❌ 未覆
- 边界情况：✅ 已覆 / ❌ 未覆
- 错误情况：✅ 已覆 / ❌ 未覆
- **Go 特有**：
  - 结构体的所有公共方法：✅ 已覆 / ❌ 未覆
  - 接口的全方法：✅ 已覆 / ❌ 未覆
  - 并发行为（goroutine、channel）：✅ 已覆 / ❌ 未覆
  - 错误处理（error → Result）：✅ 已覆 / ❌ 未覆

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
- 是否需要优：是 / 否
- 下一步行动：[具体行动]
```

**阶段文档模板：**

每阶段之文档应循以下基本结构：

```markdown
# [阶段名称]文档 - [函数名/结构体名/文件名/目录名]

## 基本信息

- Go 代码位置：[文件路径:行号范围]（如：path/to/file.go:42-67）
- 转译对象：[函数名/结构体名/文件名/目录名]
- 阶段：[规划/实现/构建/审查/优化/评估]
- 行时间：[时间戳]
- 行人员：[agent名称]

## 阶段概述

[简要描述本阶段的目标和主要工作]

## 行过程

[详细记行步骤和过程]

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

## 验结果

- [验项1]：✅ 通过 / ❌ 失败
- [验项2]：✅ 通过 / ❌ 失败
  ...

## 总结

[阶段总结和下一步计划]
```

## Go 语言特性到 Rust 映表

### 1. 并发模型映

| Go 特性           | Rust 等价物                         | 备注                                     |
| ----------------- | ----------------------------------- | ---------------------------------------- |
| `go func()`       | `tokio::spawn(async move { ... })`  | 需要用 Tokio 运时                    |
| `chan T`          | `tokio::sync::mpsc::channel<T>`     | 异步 channel；同步用 `std::sync::mpsc` |
| `<-chan`          | `receiver.recv()`                   | 接收操作                                 |
| `chan<-`          | `sender.send()`                     | 发送操作                                 |
| `close(chan)`     | `drop(sender)`                      | Rust 中 sender 被 drop 自动关闭          |
| `select`          | `tokio::select!`                    | 多路复用                                 |
| `sync.WaitGroup`  | `tokio::task::JoinSet` 或 `Barrier` | 等待多个任务完成                         |
| `sync.Mutex`      | `std::sync::Mutex`                  | 互斥锁                                   |
| `sync.RWMutex`    | `std::sync::RwLock`                 | 读写锁                                   |
| `sync.Once`       | `std::sync::OnceLock`               | 单次初始化                               |
| `context.Context` | `tokio::task::CancellationToken`    | 取消上下文                               |

### 2. 类型系统映

| Go 类型       | Rust 等价物                            | 备注           |
| ------------- | -------------------------------------- | -------------- |
| `int`         | `i32` 或 `isize`                       | 据平台选   |
| `int32`       | `i32`                                  | 固定大小       |
| `int64`       | `i64`                                  | 固定大小       |
| `uint`        | `u32` 或 `usize`                       | 据平台选   |
| `float32`     | `f32`                                  | 单精度浮点     |
| `float64`     | `f64`                                  | 双精度浮点     |
| `string`      | `String` 或 `&str`                     | 所有权 vs 借用 |
| `[]T`         | `Vec<T>` 或 `&[T]`                     | 动态数组       |
| `[N]T`        | `[T; N]`                               | 固定大小数组   |
| `map[K]V`     | `HashMap<K, V>`                        | 哈希映       |
| `*T`          | `&T` 或 `Box<T>`                       | 指针/堆分    |
| `nil`         | `None`                                 | 空值           |
| `interface{}` | `dyn Any`                              | 类型擦除       |
| `error`       | `Result<T, E>`                         | 错误处理       |
| `chan T`      | `mpsc::Sender<T>`, `mpsc::Receiver<T>` | 通道           |

### 3. 结构体和方法映

| Go 特性                    | Rust 等价物                      | 备注              |
| -------------------------- | -------------------------------- | ----------------- |
| `type T struct { ... }`    | `struct T { ... }`               | 结构体定义        |
| `func (t *T) Method() {}`  | `impl T { fn method(&self) {} }` | 方法定义          |
| `func (t T) Method() {}`   | `impl T { fn method(self) {} }`  | 值接收者方法      |
| `type T interface { ... }` | `trait T { ... }`                | 接口/特征         |
| `type U struct { T }`      | `struct U { t: T }`              | 嵌入结构体 → 组合 |
| `type U struct { *T }`     | `struct U { t: Box<T> }`         | 指针嵌入          |

### 4. 函数映

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

### 5. 控制流映

| Go 特性                    | Rust 等价物                                    | 备注         |
| -------------------------- | ---------------------------------------------- | ------------ |
| `if err != nil { ... }`    | `match result { Ok(v) => ..., Err(e) => ... }` | 错误处理     |
| `defer f()`                | `Drop trait` 或 `scopeguard`                   | 延迟行     |
| `panic("msg")`             | `panic!("msg")`                                | Panic        |
| `recover()`                | `catch_unwind()`                               | Panic 恢复   |
| `for i := 0; i < N; i++`   | `for i in 0..N {}`                             | C 风格循环   |
| `for range slice`          | `for item in slice {}`                         | 迭代         |
| `for i, v := range slice`  | `for (i, v) in slice.iter().enumerate() {}`    | 索引和值迭代 |
| `range map`                | `for (k, v) in map.iter() {}`                  | Map 迭代     |
| `range chan`               | `while let Some(v) = receiver.recv() {}`       | Channel 迭代 |
| `go`                       | `tokio::spawn(async { ... })`                  | Goroutine    |
| `select`                   | `tokio::select!`                               | 多路选     |
| `switch v { case x: ... }` | `match v { x => ... }`                         | Switch/Match |

### 6. 包和模块映

| Go 特性            | Rust 等价物       | 备注                 |
| ------------------ | ----------------- | -------------------- |
| `package main`     | `fn main() {}`    | 主包/函数            |
| `package foo`      | `mod foo {}`      | 模块定义             |
| `import "pkg"`     | `use pkg;`        | 导入模块             |
| `import _ "pkg"`   | -                 | Go 特有，Rust 无对应 |
| `import . "pkg"`   | `use pkg::*;`     | 通配导入（不推荐）   |
| `import foo "pkg"` | `use pkg as foo;` | 别名导入             |
| `go.mod`           | `Cargo.toml`      | 包管文件           |
| `go build`         | `cargo build`     | 构                 |
| `go test`          | `cargo test`      | 测试                 |
| `go vet`           | `cargo clippy`    | 静态析             |

## 查清单

### 任务管查清单

**多层级任务列表查：**

- [ ] 已据转译规模确定任务列表层级（目录级/文件级/函数级）
- [ ] 目录级任务列表（如需要）：已规目录结构、模块组、依赖关系
- [ ] 文件级任务列表（如需要）：已规文件模块位置、函数组、共享类型
- [ ] 函数级任务列表（必）：已为每函数建任务列表
- [ ] 任务列表层级关系正确（目录级 → 文件级 → 函数级）

**任务列表质量查：**

- [ ] 已用 task_list_manager 建任务列表
- [ ] 任务列表含全阶段（规、现、构、审、优、评）
- [ ] 任务类型正确（sub/main）
- [ ] 任务描述完整（含约束条件、必要求、禁事项、验标准）
- [ ] **每子任务都含 Go 代码行号位置信息**
- [ ] Go 代码位置信息格式正确（函数/结构体级：`file.go:start-end`，文件级：`file.go`，目录级：`dir/`）
- [ ] 预期输出结构化（用分条列出格式）
- [ ] 预期输出中含 Go 代码位置信息
- [ ] 任务依赖关系正确设
- [ ] 已验任务列表建成功

### 规划阶段查清单

- [ ] 已记 Go 代码位置信息（文件路径和行号范围）
- [ ] Go 代码位置信息已含在任务描述或背景信息中
- [ ] 已选合适之模块位置
- [ ] 已设符合 Rust 最佳实践之函数签名
- [ ] 函数/结构体/特征注释中含对应之 Go 代码位置信息
- [ ] 对于 Go 结构体，已虑转为 Rust 结构体和方法
- [ ] 对于 Go 接口，已虑转为 Rust trait
- [ ] 对于 Go goroutine，已虑转为 Rust async/await
- [ ] 对于 Go channel，已虑转为 Rust channel
- [ ] 已评估是否需要实现（如跳过，已详细说明原因）
- [ ] 如果是根符号，签名含 `pub` 关键字
- [ ] **已生规划阶段文档记**
- [ ] 规文档含全必需内容（位置信息、决策、评结果等）
- [ ] 规文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 实现阶段查清单

- [ ] 已先编测试用例
- [ ] 测试用例覆主要功能、边界情况、错误情况
- [ ] 已现函数使测试通过
- [ ] 未用 `todo!` 或 `unimplemented!` 占位符
- [ ] 用 Rust 原生类型和惯用法
- [ ] 注释用中文
- [ ] 函数/结构体/特征注释中含 Go 代码位置信息
- [ ] 对于 Go 结构体，已正确转为 Rust 结构体和方法
- [ ] 对于 Go 接口，已正确转为 Rust trait
- [ ] 对于 Go goroutine，已正确转为 Rust async/await
- [ ] 对于 Go channel，已正确转为 Rust channel
- [ ] 对于 Go 错误处理，已正确转为 Result<T,E>
- [ ] 未用 `use ...::*` 通配导入
- [ ] **已生实现阶段文档记**
- [ ] 现文档含全必需内容（测试设、实现策略、重构说明等）
- [ ] 现文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 构建阶段查清单

- [ ] 全测试用例通过
- [ ] 无编译错误
- [ ] 修过程未破坏其他测试
- [ ] 修改最小化，无无关重构
- [ ] **已生构建阶段文档记**
- [ ] 构文档含全必需内容（构过程、问题与解决方案、验结果等）
- [ ] 构文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 审查阶段查清单

- [ ] 测试用例未被破坏（#[test] 标记完整）
- [ ] 无严重问题（空指针、越界等）
- [ ] 测试用例完备（覆主要功能、边界、错误）
- [ ] 核心功能与 Go 现一致
- [ ] 对于 Go 结构体，公共接口与原始现一致
- [ ] 对于 Go 接口，接口方法完整实现
- [ ] 对于 Go 并发，并发行为保持一致
- [ ] 文件结构合理
- [ ] 问题报告含详细描述、修建议和修代码示例
- [ ] **已生审查阶段文档记**
- [ ] 审文档含全必需内容（审结果、问题列表、修建议等）
- [ ] 审文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 优化阶段查清单

- [ ] 已按优先级修全问题
- [ ] 修后全测试通过
- [ ] 未引回归问题
- [ ] 修改最小化
- [ ] **已生优化阶段文档记**
- [ ] 优文档含全必需内容（优问题、修方案、验结果等）
- [ ] 优文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 评估阶段查清单

- [ ] 已用子 agent 进行独立评估
- [ ] 评估报告已生，含功能对齐查结果
- [ ] 评估报告中含 Go 代码位置信息
- [ ] 功能对齐查已完成，逐项对比 Go 和 Rust 现
- [ ] 对于 Go 结构体，已查封装性和接口一致性
- [ ] 对于 Go 接口，已查接口实现完整性
- [ ] 对于 Go 并发，已查并发行为一致性
- [ ] 测试覆查已完成
- [ ] 边界情况查已完成
- [ ] 如发现功能未对齐问题，已建优子任务
- [ ] 优子任务含 Go 代码位置信息
- [ ] 优子任务已行并修问题
- [ ] 修后已重新评，功能完全对齐
- [ ] 评估报告认功能完全对齐
- [ ] 全测试用例通过
- [ ] **已生评估阶段文档记**
- [ ] 评文档含全必需内容（评估报告、功能对齐查、问题与建议等）
- [ ] 评文档已存到指定位置
- [ ] 任务预期输出中含文档路径

### 根符号特殊要求

若函数是根符号（需要从 crate 外部访问）：

- [ ] 函数签名含 `pub` 关键字
- [ ] 函数所在之模块已在 `src/lib.rs` 中导出（`pub mod <模块名>;`）
- [ ] 若需 FFI 导出，用了 `#[no_mangle]` 和 `pub extern "C"`

## 相关资源

- 参考 TDD 规则：{{ rule_file_dir }}/../development_workflow/tdd.md
- 参考代码审规则：{{ rule_file_dir }}/../code_quality/code_review.md
- 参考 Rust 性能优：{{ rule_file_dir }}/../performance/rust_performance.md
