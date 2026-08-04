---
name: java_test
description: 当需要为Java项目编写测试或配置测试框架时触发。每当用户提及"Java测试"、"JUnit"、"TestNG"、"Mockito"时触发。不触发：非Java项目测试；代码审查；性能优化。
---

# Java 测试之规

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

## 汝必写之测例

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

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
- [ ] 用 @BeforeEach/@AfterEach 行设置与清理（如需）
