# Rust 测试规则

## ⚠️ 你必须遵守的核心要求

**编写完成务必执行测试，直到修复完成为止！**

### 执行要求

- **必须**：每次代码修改后，立即运行测试
- **必须**：如果测试失败，修复代码直到所有测试通过
- **禁止**：提交未通过测试的代码
- **禁止**：在测试未通过的情况下继续开发

### 工作流程

1. 编写或修改代码
2. **立即**运行测试
3. 如果测试失败，修复代码
4. 重复步骤 2-3，直到所有测试通过
5. 确认所有测试通过后，才能提交代码

## 你必须使用的测试框架

### 标准库 test（无需安装）

**运行命令：**

```bash
cargo test               # 运行所有测试
cargo test --lib         # 只运行库测试
cargo test --bin name    # 运行特定二进制文件测试
cargo test test_name     # 运行特定测试函数
cargo test -- --nocapture # 显示 println! 输出
cargo test -- --test-threads=1 # 单线程运行
```

## 你必须编写的测试示例

```rust
// src/lib.rs 或 src/calculator.rs
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
    }

    #[test]
    fn test_divide_by_zero() {
        assert!(divide(10, 0).is_err());
    }

    #[test]
    #[should_panic(expected = "Division by zero")]
    fn test_panic() {
        divide_unchecked(10, 0);
    }
}
```

## 测试模块规范

### 模块标记

- **必须**：测试模块使用 `#[cfg(test)]` 属性
- **必须**：测试函数使用 `#[test]` 属性

### 断言宏

- **必须**：使用 `assert!` 进行布尔断言
- **必须**：使用 `assert_eq!` 进行相等断言
- **必须**：使用 `assert_ne!` 进行不等断言

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试模块使用 `#[cfg(test)]` 属性
- [ ] 测试函数使用 `#[test]` 属性
- [ ] 使用 `assert!`, `assert_eq!`, `assert_ne!` 进行断言
- [ ] 测试覆盖了正常、边界和异常情况
