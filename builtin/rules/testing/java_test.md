---
name: java_test
description: 当需要为Java项目编写测试或配置测试框架时触发。每当用户提及"Java测试"、"JUnit"、"TestNG"、"Mockito"时触发。不触发：非Java项目测试；代码审查；性能优化。
---

# Java 测试的规

## ⚠ 要

**写毕必行测试，至修毕乃止！**

### 行要

- **必须**：每改码后，即行测试
- **必须**：若测试败，修码至全过
- **禁止**：提交未过的码
- **禁止**：于测试未过的际续行开发

### 流程

1. 写或改码
2. **即**行测试
3. 若败，修的
4. 复步 2-3，至全过
5. 全过的后，方得提交

## 必须用的测架

### JUnit 5（荐）

**Maven 运行命令：**

```bash
mvn test                  # 行全测
mvn test -Dtest=TestClass # 行特测类
```

**Gradle 运行命令：**

```bash
gradle test               # 行全测
gradle test --tests TestClass # 行特测类
```

### JUnit 4

**运行命令：**

```bash
mvn test                  # 行全测
```

## 必须写的测例

### JUnit 5 测例

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

### JUnit 4 测例

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

## 测试行检单

提交码前，必须确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测覆正常的情
- [ ] 测覆边界的情
- [ ] 测覆异常的情
- [ ] 用 @BeforeEach/@AfterEach 行设置与清理（如需）
