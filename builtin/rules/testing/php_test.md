---
name: php_test
description: 当需要为PHP项目编写测试或配置测试框架时触发。每当用户提及"PHP测试"、"PHPUnit"、"Codeception"时触发。不触发：非PHP项目测试；代码审查；性能优化。
---

# PHP 测试之规

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

### PHPUnit（荐）

**安装命令：**

```bash
composer require --dev phpunit/phpunit
```

**运行命令：**

```bash
phpunit                 # 行全测
phpunit tests/TestClass.php # 行特文件
phpunit --filter testMethod # 行特测法
phpunit --coverage-html coverage/ # 生覆盖率报告
```

### Pest

**安装命令：**

```bash
composer require --dev pestphp/pest
```

**运行命令：**

```bash
./vendor/bin/pest       # 行全测
./vendor/bin/pest --filter test_name # 行特测
```

## 汝必写之测例

### PHPUnit 测例

```php
// tests/CalculatorTest.php
use PHPUnit\Framework\TestCase;

class CalculatorTest extends TestCase
{
    public function testAdd()
    {
        $calc = new Calculator();
        $this->assertEquals(5, $calc->add(2, 3));
    }

    public function testDivideByZero()
    {
        $calc = new Calculator();
        $this->expectException(DivisionByZeroError::class);
        $calc->divide(10, 0);
    }
}
```

### Pest 测例

```php
// tests/CalculatorTest.php
use Tests\TestCase;

test('adds two numbers', function () {
    $calc = new Calculator();
    expect($calc->add(2, 3))->toBe(5);
});
```

## 测试类与方法规

### PHPUnit 规

- **必**：测试类继承 `TestCase`
- **必**：测试方法以 `test` 开头或用 `@test` 注解
- **必**：测试方法必为 `public`

### Pest 规

- **必**：用 `test()` 函数定义测试
- **必**：用描述性之测试名

## 测试行检单

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测试类继承 TestCase（PHPUnit）
- [ ] 测试方法以 `test` 开头或用 `@test` 注解
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
