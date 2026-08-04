---
name: ruby_test
description: 当需要为Ruby项目编写测试或配置测试框架时触发。每当用户提及"Ruby测试"、"RSpec"、"Minitest"时触发。不触发：非Ruby项目测试；代码审查；性能优化。
---

# Ruby 测试之规

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

## 汝必写之测例

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

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 用描述性之测试名
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
