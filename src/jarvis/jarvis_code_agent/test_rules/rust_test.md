# Rust 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### 标准库 test

```bash
cargo test               # 运行所有测试
cargo test --lib         # 只运行库测试
cargo test --bin name    # 运行特定二进制文件测试
cargo test test_name     # 运行特定测试函数
cargo test -- --nocapture # 显示 println! 输出
cargo test -- --test-threads=1 # 单线程运行
```

## 测试示例

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

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试模块使用 `#[cfg(test)]`
- [ ] 测试函数使用 `#[test]` 属性
- [ ] 使用 `assert!`, `assert_eq!`, `assert_ne!` 进行断言
