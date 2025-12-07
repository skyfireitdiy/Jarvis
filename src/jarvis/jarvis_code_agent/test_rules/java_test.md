# Java 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### JUnit 5（推荐）

```bash
mvn test                  # Maven: 运行所有测试
mvn test -Dtest=TestClass # 运行特定测试类
gradle test               # Gradle: 运行所有测试
gradle test --tests TestClass # 运行特定测试类
```

### JUnit 4

```bash
mvn test                  # 运行所有测试
```

## 测试示例

### JUnit 5

```java
// src/test/java/CalculatorTest.java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CalculatorTest {
    @Test
    void testAdd() {
        Calculator calc = new Calculator();
        assertEquals(5, calc.add(2, 3));
    }

    @Test
    void testDivideByZero() {
        Calculator calc = new Calculator();
        assertThrows(ArithmeticException.class, () -> {
            calc.divide(10, 0);
        });
    }
}
```

### JUnit 4

```java
import org.junit.Test;
import static org.junit.Assert.*;

public class CalculatorTest {
    @Test
    public void testAdd() {
        Calculator calc = new Calculator();
        assertEquals(5, calc.add(2, 3));
    }
}
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试覆盖正常、边界和异常情况
- [ ] 使用 @BeforeEach/@AfterEach 进行设置和清理
