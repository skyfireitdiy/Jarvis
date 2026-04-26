---
name: function_single_responsibility
description: 当需要识别和重构违反单一职责原则的函数时使用此规则——函数单一职责重构规则，单一职责原则识别和重构指导。包括：识别违反单一职责原则的函数；分析函数职责是否明确；判断函数是否承担多个不相关的职责；重构函数使其符合单一职责；提取独立的功能到独立函数；控制函数长度在合理范围（不超过50行）；降低函数复杂度（圈复杂度不超过10）；提高函数的可读性和可维护性；提升函数的可测试性。每当用户提及"单一职责"、"函数职责"、"函数拆分"、"重构函数"、"函数过长"、"复杂函数"、"代码异味"或需要函数重构、代码质量改进、函数拆分时触发，无论编程语言和项目规模如何。如果需要识别或重构违反单一职责原则的函数，请使用此规则。
---

# 函数单一职责重构

## 规则简介

本规则定义了函数单一职责原则的要求和重构方法。单一职责原则要求函数只做一件事，而且把这件事做好。违反单一职责原则的函数通常表现为：逻辑复杂、难以理解、难以测试、难以复用。

## 你必须遵守的原则

### 1. 函数职责唯一性

**要求说明：**

- **必须**：每个函数只完成一个明确的业务逻辑或功能
- **必须**：函数名应该准确描述函数的单一职责
- **禁止**：在同一个函数中混合多个逻辑层次（如：数据验证、业务处理、数据持久化）

**判断标准：**

如果你无法用一句话清晰描述"这个函数做什么"，那么它可能违反了单一职责原则。

### 2. 函数长度控制

**要求说明：**

- **必须**：函数长度（包括注释和空行）不超过 50 行
- **必须**：函数的复杂度（圈复杂度）不超过 10
- **禁止**：出现超过 3 层的嵌套结构

### 3. 参数数量限制

**要求说明：**

- **必须**：函数参数不超过 5 个
- **必须**：超过 3 个参数时考虑使用对象封装或数据类
- **禁止**：使用可变参数列表掩盖过多的参数

## 你必须执行的操作

### 操作1：识别违反单一职责的函数

**执行步骤：**

1. 审查函数名称，判断是否准确描述函数行为
2. 检查函数长度，如果超过 50 行，标记为需要重构
3. 分析函数逻辑，识别是否存在多个职责
4. 检查参数数量，如果超过 5 个，标记为需要重构

**常见反模式：**

- 函数名包含 "and"、"or"、"andThen" 等连接词
- 函数中包含过多的 if/else 分支，处理多种不同情况
- 函数中同时进行数据验证、业务逻辑、数据库操作、日志记录

### 操作2：重构函数

**执行步骤：**

1. **提取独立逻辑**：将函数中独立的逻辑块提取为独立的函数
2. **降低复杂度**：使用早期返回（Early Return）减少嵌套层级
3. **封装参数对象**：使用数据类或字典封装相关参数
4. **命名优化**：确保每个函数名准确描述其单一职责

**注意事项：**

- 保持重构的步骤足够小，每次只改动一个部分
- 重构前后保持相同的外部行为
- 对重构的代码进行单元测试验证

### 操作3：验证重构结果

**执行步骤：**

1. 确认每个新函数的长度不超过 50 行
2. 确认每个函数可以清晰描述其单一职责
3. 确认所有单元测试通过
4. 确认代码可读性明显提升

### 示例

#### 错误示例：违反单一职责

```python
def process_user_order(user_id, order_data, product_id, quantity, payment_info, shipping_info):
    """处理用户订单（违反单一职责：包含验证、业务处理、持久化、通知）"""
    # 步骤1：验证用户（职责1）
    if not validate_user(user_id):
        return {"error": "Invalid user"}

    # 步骤2：验证产品（职责2）
    if not validate_product(product_id, quantity):
        return {"error": "Invalid product"}

    # 步骤3：计算价格（职责3）
    total_price = calculate_price(product_id, quantity)

    # 步骤4：处理支付（职责4）
    payment_result = process_payment(payment_info, total_price)
    if not payment_result["success"]:
        return {"error": "Payment failed"}

    # 步骤5：保存订单（职责5）
    order_id = save_order_to_db(user_id, product_id, quantity, total_price)

    # 步骤6：发送通知（职责6）
    send_confirmation_email(user_id, order_id)

    return {"success": True, "order_id": order_id}
```

#### 正确示例：遵守单一职责

```python
def process_user_order(user_id: str, order_data: dict) -> dict:
    """处理用户订单的主流程（协调各个单一职责的函数）"""
    try:
        validate_user(user_id)
        validate_order_data(order_data)
        total_price = calculate_order_total(order_data)
        payment_result = process_payment(order_data["payment_info"], total_price)
        order_id = save_order(user_id, order_data, total_price)
        send_order_notification(user_id, order_id)
        return {"success": True, "order_id": order_id}
    except ValidationError as e:
        return {"error": str(e)}
    except PaymentError as e:
        return {"error": str(e)}

def validate_user(user_id: str) -> None:
    """验证用户是否有效"""
    if not user_exists(user_id):
        raise ValidationError("Invalid user")

def validate_order_data(order_data: dict) -> None:
    """验证订单数据"""
    if "product_id" not in order_data or "quantity" not in order_data:
        raise ValidationError("Invalid order data")

def calculate_order_total(order_data: dict) -> float:
    """计算订单总价"""
    product_price = get_product_price(order_data["product_id"])
    return product_price * order_data["quantity"]

def process_payment(payment_info: dict, amount: float) -> dict:
    """处理支付"""
    payment_service = PaymentService()
    return payment_service.charge(payment_info, amount)

def save_order(user_id: str, order_data: dict, total_price: float) -> str:
    """保存订单到数据库"""
    order = Order(
        user_id=user_id,
        product_id=order_data["product_id"],
        quantity=order_data["quantity"],
        total_price=total_price
    )
    order.save()
    return str(order.id)

def send_order_notification(user_id: str, order_id: str) -> None:
    """发送订单通知"""
    user_email = get_user_email(user_id)
    EmailService().send_order_confirmation(user_email, order_id)
```

## 检查清单

在完成函数单一职责重构后，你必须确认：

- [ ] 每个函数都有一个清晰、明确的职责
- [ ] 每个函数可以用一句话描述其功能
- [ ] 所有函数长度不超过 50 行
- [ ] 所有函数参数不超过 5 个
- [ ] 没有超过 3 层的嵌套结构
- [ ] 函数名准确描述其职责
- [ ] 已编写或更新单元测试
- [ ] 所有单元测试通过
- [ ] 代码可读性明显提升

## 相关资源

- 相关规则：`{{ rule_file_dir }}/code_quality/code_review.md`
- 参考规范：Clean Code 章节函数
