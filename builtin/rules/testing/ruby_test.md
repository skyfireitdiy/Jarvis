---
name: ruby_test
description: 当需要为Ruby项目编写测试或配置测试框架时触发。每当用户提及"Ruby测试"、"RSpec"、"Minitest"时触发。不触发：非Ruby项目测试；代码审查；性能优化。
---

# Ruby 测试规范

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

### RSpec（荐）

**安装命令：**

```bash
gem install rspec
# 或添加到 Gemfile
gem 'rspec'
```

**运行命令：**

```bash
rspec                 # 行全测
rspec spec/file_spec.rb  # 行特文件
rspec -fd                # 详出
rspec --format documentation # 文档式出
```

### Minitest（标准库，无需安装）

**运行命令：**

```bash
ruby -I test test/test_file.rb  # 行特文件
rake test                        # 行全测（Rake）
```

## 必须写的测例

### RSpec 测例

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

### Minitest 测例

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

## 测试行检单

提交码前，必须确：

- [ ] **写完立刻运行测试**
- [ ] **所有测试都通过**
- [ ] **若失败，就修复到通过**
- [ ] 用描述性的测试名
- [ ] 测覆正常的情
- [ ] 测覆边界的情
- [ ] 测覆异常的情
