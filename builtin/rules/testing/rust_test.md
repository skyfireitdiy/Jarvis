---
name: rust_test
description: 当需要为Rust项目编写测试或配置测试框架时触发。每当用户提及"Rust测试"、"cargo test"、"测试模块"时触发。不触发：非Rust项目测试；代码审查；性能优化。
---

# Rust 测试之规

## ⚠ 要

**写毕必行测试，至修毕乃止！**

### 行要

- **必**：每改码后，即行测试
- **必**：若测试败，修码至全过
- **禁**：提交未过之码
- **禁**：于测试未过之际续行开发

### 流程

1. 写或改码
2. **即**行测试
3. 若败，修之
4. 复步 2-3，至全过
5. 全过之后，方得提交

## 汝必用之测架

### 标准库 test（无需安装）

**运行命令：**

```bash
cargo test               # 行全测
cargo test --lib         # 只行库测
cargo test --bin name    # 行特二进制文件测
cargo test test_name     # 行特测函数
cargo test -- --nocapture # 示 println! 输出
cargo test -- --test-threads=1 # 单线程行
```

## 汝必写之测例

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

## 测试模块规

### 模块标记

- **必**：测试模块用 `#[cfg(test)]` 属性
- **必**：测试函数用 `#[test]` 属性

### 断言宏

- **必**：用 `assert!` 行布尔断言
- **必**：用 `assert_eq!` 行相等断言
- **必**：用 `assert_ne!` 行不等断言

## 测试行检单

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测试模块用 `#[cfg(test)]` 属性
- [ ] 测试函数用 `#[test]` 属性
- [ ] 用 `assert!`, `assert_eq!`, `assert_ne!` 行断言
- [ ] 测覆正常、边界与异常之情
