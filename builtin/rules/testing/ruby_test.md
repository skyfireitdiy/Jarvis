# Ruby 测试规则

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

### RSpec（推荐使用）

**安装命令：**

```bash
gem install rspec
# 或添加到 Gemfile
gem 'rspec'
```

**运行命令：**

```bash
rspec                    # 运行所有测试
rspec spec/file_spec.rb  # 运行特定文件
rspec -fd                # 详细输出
rspec --format documentation # 文档格式输出
```

### Minitest（标准库，无需安装）

**运行命令：**

```bash
ruby -I test test/test_file.rb  # 运行特定文件
rake test                 # 运行所有测试（Rake）
```

## 你必须编写的测试示例

### RSpec 测试格式

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

### Minitest 测试格式

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

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 使用了描述性的测试名称
- [ ] 测试覆盖了正常情况
- [ ] 测试覆盖了边界情况
- [ ] 测试覆盖了异常情况
