# PHP 测试规则

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

### PHPUnit（推荐使用）

**安装命令：**

```bash
composer require --dev phpunit/phpunit
```

**运行命令：**

```bash
phpunit                 # 运行所有测试
phpunit tests/TestClass.php # 运行特定文件
phpunit --filter testMethod # 运行特定测试方法
phpunit --coverage-html coverage/ # 生成覆盖率报告
```

### Pest

**安装命令：**

```bash
composer require --dev pestphp/pest
```

**运行命令：**

```bash
./vendor/bin/pest       # 运行所有测试
./vendor/bin/pest --filter test_name # 运行特定测试
```

## 你必须编写的测试示例

### PHPUnit 测试格式

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

### Pest 测试格式

```php
// tests/CalculatorTest.php
use Tests\TestCase;

test('adds two numbers', function () {
    $calc = new Calculator();
    expect($calc->add(2, 3))->toBe(5);
});
```

## 测试类和方法规范

### PHPUnit 规范

- **必须**：测试类继承 `TestCase`
- **必须**：测试方法以 `test` 开头或使用 `@test` 注解
- **必须**：测试方法必须是 `public`

### Pest 规范

- **必须**：使用 `test()` 函数定义测试
- **必须**：使用描述性的测试名称

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试类继承 TestCase（PHPUnit）
- [ ] 测试方法以 `test` 开头或使用 `@test` 注解
- [ ] 测试覆盖了正常情况
- [ ] 测试覆盖了边界情况
- [ ] 测试覆盖了异常情况
