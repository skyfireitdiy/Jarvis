---
name: php_test
description: 当需要为PHP项目编写测试或配置测试框架时触发。每当用户提及"PHP测试"、"PHPUnit"、"Codeception"时触发。不触发：非PHP项目测试；代码审查；性能优化。
---

# PHP 测试规范

## 要点

**写完务必立刻运行测试，直到全部通过！**

### 执行要点

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

## 必须写的测例

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

- **必须**：测试类继承 `TestCase`
- **必须**：测试方法以 `test` 开头或用 `@test` 注解
- **必须**：测试方法必为 `public`

### Pest 规

- **必须**：用 `test()` 函数定义测试
- **必须**：用描述性的测试名

## 测试行检单

提交码前，必须确：

- [ ] **写完立刻运行测试**
- [ ] **所有测试都通过**
- [ ] **若失败，就修复到通过**
- [ ] 测试类继承 TestCase（PHPUnit）
- [ ] 测试方法以 `test` 开头或用 `@test` 注解
- [ ] 测覆正常的情
- [ ] 测覆边界的情
- [ ] 测覆异常的情
