# Ruby 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### RSpec（推荐）

```bash
rspec                    # 运行所有测试
rspec spec/file_spec.rb  # 运行特定文件
rspec -fd                # 详细输出
rspec --format documentation # 文档格式输出
```

### Minitest（标准库）

```bash
ruby -I test test/test_file.rb  # 运行特定文件
rake test                 # 运行所有测试（Rake）
```

## 测试示例

### RSpec

```ruby
# spec/calculator_spec.rb
require_relative '../lib/calculator'

RSpec.describe Calculator do
  describe '#add' do
    it 'adds two numbers' do
      calc = Calculator.new
      expect(calc.add(2, 3)).to eq(5)
    end
  end

  describe '#divide' do
    it 'raises error on divide by zero' do
      calc = Calculator.new
      expect { calc.divide(10, 0) }.to raise_error(ZeroDivisionError)
    end
  end
end
```

### Minitest

```ruby
# test/test_calculator.rb
require 'minitest/autorun'
require_relative '../lib/calculator'

class TestCalculator < Minitest::Test
  def test_add
    calc = Calculator.new
    assert_equal 5, calc.add(2, 3)
  end
end
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 使用描述性的测试名称
- [ ] 测试覆盖正常、边界和异常情况
