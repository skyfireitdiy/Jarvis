# C/C++ 测试规则

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

### Google Test (gtest)（推荐使用）

**安装方式：**

- 使用包管理器安装（如 `apt-get install libgtest-dev`）
- 或从源码编译安装

**CMake 构建和运行：**

```bash
mkdir build && cd build
cmake ..
make
./test_runner              # 运行所有测试
./test_runner --gtest_filter=TestClass.* # 运行特定测试
```

**直接编译运行：**

```bash
g++ -std=c++17 test.cpp -lgtest -lgtest_main -pthread
./a.out
```

### Catch2

**安装方式：**

- 下载单头文件版本
- 或使用包管理器安装

**编译运行：**

```bash
g++ -std=c++17 test.cpp -o test
./test
```

## 你必须编写的测试示例

### Google Test 测试格式

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

### Catch2 测试格式

```cpp
// test/calculator_test.cpp
#include <catch2/catch.hpp>
#include "../src/calculator.h"

TEST_CASE("Calculator add", "[calculator]") {
    Calculator calc;
    REQUIRE(calc.add(2, 3) == 5);
}
```

## 断言宏使用规范

### Google Test 断言

- **必须**：使用 `EXPECT_*` 进行非致命断言（测试继续执行）
- **必须**：使用 `ASSERT_*` 进行致命断言（测试立即终止）
- **常用断言**：`EXPECT_EQ`, `ASSERT_EQ`, `EXPECT_THROW`, `ASSERT_THROW`

### Catch2 断言

- **必须**：使用 `REQUIRE` 进行致命断言
- **必须**：使用 `CHECK` 进行非致命断言

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试覆盖了正常情况
- [ ] 测试覆盖了边界情况
- [ ] 测试覆盖了异常情况
- [ ] 使用了适当的断言宏（EXPECT_EQ, ASSERT_EQ 等）
