# 整洁代码规则

## 核心原则

1. **可读性优先**：
   - 代码是写给人看的，机器只是顺便执行
   - 使用有意义的变量名和函数名
   - 代码应该自解释，减少不必要的注释

2. **单一职责**：
   - 每个函数只做一件事
   - 每个类只有一个改变的理由
   - 保持函数和类的简洁

3. **DRY (Don't Repeat Yourself)**：
   - 避免重复代码
   - 提取公共逻辑到函数或类中
   - 使用配置而非硬编码

## 命名规范

- 使用描述性的名称，避免缩写
- 函数名应该是动词或动词短语
- 类名应该是名词或名词短语
- 布尔变量应该使用 is/has/can 等前缀
- 常量应该使用全大写，单词间用下划线分隔

## 函数设计

- 函数应该短小，最好不超过 20 行
- 函数参数应该尽可能少，最好不超过 3 个
- 函数应该只做一件事，做好一件事
- 避免副作用，函数应该可预测

## 代码组织

- 相关代码应该放在一起
- 使用空行分隔逻辑块
- 保持一致的代码风格
- 删除未使用的代码和注释

## 示例

```python
# 不好的实践
def calc(x, y, z):
    return x * y + z * 2

# 好的实践
def calculate_total_price(quantity: int, unit_price: float, tax_rate: float) -> float:
    subtotal = quantity * unit_price
    tax = subtotal * tax_rate
    return subtotal + tax
```
