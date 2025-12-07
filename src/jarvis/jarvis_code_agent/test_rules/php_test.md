# PHP 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### PHPUnit（推荐）

```bash
phpunit                 # 运行所有测试
phpunit tests/TestClass.php # 运行特定文件
phpunit --filter testMethod # 运行特定测试方法
phpunit --coverage-html coverage/ # 生成覆盖率报告
```

### Pest

```bash
./vendor/bin/pest       # 运行所有测试
./vendor/bin/pest --filter test_name # 运行特定测试
```

## 测试示例

### PHPUnit

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

### Pest

```php
// tests/CalculatorTest.php
use Tests\TestCase;

test('adds two numbers', function () {
    $calc = new Calculator();
    expect($calc->add(2, 3))->toBe(5);
});
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试类继承 TestCase
- [ ] 测试方法以 `test` 开头或使用 `@test` 注解
