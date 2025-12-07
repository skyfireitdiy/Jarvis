# C/C++ 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### Google Test (gtest)

```bash
# CMake
mkdir build && cd build
cmake ..
make
./test_runner              # 运行所有测试
./test_runner --gtest_filter=TestClass.* # 运行特定测试

# 直接编译
g++ -std=c++17 test.cpp -lgtest -lgtest_main -pthread
./a.out
```

### Catch2

```bash
# 单头文件版本
g++ -std=c++17 test.cpp -o test
./test
```

## 测试示例

### Google Test

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

### Catch2

```cpp
// test/calculator_test.cpp
#include <catch2/catch.hpp>
#include "../src/calculator.h"

TEST_CASE("Calculator add", "[calculator]") {
    Calculator calc;
    REQUIRE(calc.add(2, 3) == 5);
}
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试覆盖正常、边界和异常情况
- [ ] 使用适当的断言宏（EXPECT_EQ, ASSERT_EQ 等）
