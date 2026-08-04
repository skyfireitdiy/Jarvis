---
name: cpp_test
description: 当需要为C/C++项目编写测试或配置测试框架时触发。每当用户提及"C++测试"、"C测试"、"Google Test"、"GTest"、"Catch2"时触发。不触发：非C/C++项目测试；代码审查；性能优化。
---

# C/C++ 测试之规

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

### Google Test (gtest)（荐）

**安装之法：**

- 以包管理器安（如 `apt-get install libgtest-dev`）
- 或自源码编译安之

**CMake 构建运行：**

```bash
mkdir build && cd build
cmake ..
make
./test_runner              # 行全测
./test_runner --gtest_filter=TestClass.* # 行特测
```

**直接编译运行：**

```bash
g++ -std=c++17 test.cpp -lgtest -lgtest_main -pthread
./a.out
```

### Catch2

**安装之法：**

- 下载单头文件版
- 或以包管理器安

**编译运行：**

```bash
g++ -std=c++17 test.cpp -o test
./test
```

## 汝必写之测例

### Google Test 测例

```cpp
// test/calculator_test.cpp
#include <gtest/gtest.h>
#include "../src/calculator.h"

TEST(CalculatorTest, Add) {
    Calculator calc;
    EXPECT_EQ(5, calc.add(2, 3));
}


TEST(CalculatorTest, DivideByZero) {
    Calculator calc;
    EXPECT_THROW(calc.divide(10, 0), std::invalid_argument);
}
```

### Catch2 测例

```cpp
// test/calculator_test.cpp
#include <catch2/catch.hpp>
#include "../src/calculator.h"

TEST_CASE("Calculator add", "[calculator]") {
    Calculator calc;
    REQUIRE(calc.add(2, 3) == 5);
}
```

## 断言宏用规

### Google Test 断言

- **必**：用 `EXPECT_*` 行非致命断言（测续行）
- **必**：用 `ASSERT_*` 行致命断言（测即止）
- **常用**：`EXPECT_EQ`, `ASSERT_EQ`, `EXPECT_THROW`, `ASSERT_THROW`

### Catch2 断言

- **必**：用 `REQUIRE` 行致命断言
- **必**：用 `CHECK` 行非致命断言

## 测试行检单

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
- [ ] 用适当之断言宏（EXPECT_EQ, ASSERT_EQ 等）
