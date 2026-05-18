---
name: ai_friendly_code_structure
description: 当需要编写或重构代码以优化代码结构、提升 AI Agent 可理解性时使用此规则——AI 友好型代码结构规范。包括：单文件大小控制（≤500 行）、单函数长度控制（≤50 行）、单一职责原则、清晰命名规范、适度注释、扁平嵌套结构、正交设计。每当用户提及"AI 友好代码"、"代码结构优化"、"便于 AI 理解的代码"、"代码可读性"或需要确保代码结构清晰、易于 AI Agent 理解和维护时触发。
---

# AI 友好型代码结构规范

## 规则简介

本规范定义了编写 AI 友好型代码必须遵守的结构化要求，旨在使代码更易于被 AI Agent 理解、分析和维护。遵循这些规范可以显著提升 AI 辅助编程的效率和准确性。

## 你必须遵守的原则

### 1. 文件大小限制

**要求说明：**

- **必须**：单个源代码文件不超过 1000 行（不含空行和注释）
- **必须**：当文件超过 800 行时，应考虑拆分
- **禁止**：将无关的功能模块放在同一文件中
- **例外**：如果文件功能非常内聚（如核心算法、领域模型定义），拆分反而降低可读性，可保留原文件但应添加说明注释

**拆分策略：**

- 按功能模块拆分：不同业务逻辑分离到不同文件
- 按职责拆分：数据模型、业务逻辑、接口定义分别存放
- 按复用性拆分：通用工具函数提取到独立模块

**示例：**

```python
# ✅ 正确：文件职责单一，约 200 行
# user_service.py - 只处理用户相关业务逻辑
class UserService:
    def create_user(self, ...): ...
    def get_user(self, ...): ...
    def update_user(self, ...): ...

# ✅ 正确：工具函数独立成文件
# utils/validation.py - 只包含验证相关函数
def validate_email(...): ...
def validate_phone(...): ...
```

### 2. 函数长度限制

**要求说明：**

- **必须**：单个函数不超过 50 行（不含空行和注释）
- **必须**：当函数超过 40 行时，应考虑提取子函数
- **禁止**：在函数内嵌套超过 3 层的条件判断

**拆分策略：**

- 提取子函数：将独立逻辑块提取为私有方法
- 提前返回：使用 guard clause 减少嵌套
- 策略模式：复杂条件分支使用策略模式

**示例：**

```python
# ✅ 正确：函数职责单一，约 20 行
def process_order(order: Order) -> bool:
    """处理订单，返回是否成功"""
    if not validate_order(order):
        return False

    if not check_inventory(order.items):
        return False

    total = calculate_total(order)
    return charge_payment(order.user, total)

# ❌ 错误：函数过长，超过 80 行
def process_order(order):
    # 验证逻辑... (20 行)
    # 库存检查... (20 行)
    # 价格计算... (20 行)
    # 支付处理... (20 行)
    # 日志记录... (10 行)
    pass
```

### 3. 单一职责原则

**要求说明：**

- **必须**：每个类/函数只负责一个明确的职责
- **必须**：类名和函数名能准确反映其唯一职责
- **禁止**：在工具类中混杂业务逻辑

**示例：**

```python
# ✅ 正确：职责分离
class UserAuthenticator:
    """只负责用户认证"""
    def authenticate(self, ...): ...

class UserProfileManager:
    """只负责用户资料管理"""
    def update_profile(self, ...): ...

# ❌ 错误：职责混杂
class UserManager:
    # 既管认证，又管资料，还管权限...
    def login(self, ...): ...
    def update_profile(self, ...): ...
    def assign_role(self, ...): ...
```

### 4. 清晰命名规范

**要求说明：**

- **必须**：使用有意义的名称，避免缩写（除非是通用缩写）
- **必须**：变量名体现数据类型和用途
- **必须**：函数名体现操作和行为（动词 + 名词）
- **禁止**：使用 `a`, `b`, `temp`, `data` 等模糊名称

**示例：**

```python
# ✅ 正确：命名清晰
def calculate_monthly_revenue(orders: List[Order]) -> Decimal: ...
def find_active_users_by_department(dept_id: int) -> List[User]: ...
user_creation_timestamp: datetime
max_retry_count: int = 3

# ❌ 错误：命名模糊
def calc(data): ...
def find(id): ...
tmp = ...
info = ...
```

### 5. 适度注释

**要求说明：**

- **必须**：为公共 API 编写文档字符串（docstring）
- **必须**：为复杂算法编写实现思路注释
- **必须**：为非直观的代码编写"为什么这样做"的注释
- **禁止**：注释重复代码本身（"what"而非"why"）

**示例：**

```python
# ✅ 正确：注释解释原因
def retry_request(url: str, max_retries: int = 3) -> Response:
    """
    发送 HTTP 请求，失败时自动重试。

    使用指数退避策略，因为立即重试可能加重服务器负载。
    """
    for attempt in range(max_retries):
        # 指数退避：1s, 2s, 4s...
        # 避免请求风暴，给服务器恢复时间
        wait_time = 2 ** attempt
        time.sleep(wait_time)

        try:
            return http.get(url)
        except ConnectionError:
            if attempt == max_retries - 1:
                raise

# ❌ 错误：注释重复代码
i += 1  # i 加 1
return result  # 返回结果
```

### 6. 扁平嵌套结构

**要求说明：**

- **必须**：代码嵌套层级不超过 3 层
- **必须**：使用 guard clause（提前返回）减少嵌套
- **禁止**：深层嵌套的 if-else 或 try-except

**示例：**

```python
# ✅ 正确：扁平结构（最大嵌套 2 层）
def process_data(data: Optional[Dict]) -> Result:
    if data is None:
        return Error("Data is None")

    if "items" not in data:
        return Error("Missing items")

    for item in data["items"]:
        if not is_valid(item):
            continue
        process_item(item)

    return Success()

# ❌ 错误：深层嵌套（5 层）
def process_data(data):
    if data is not None:
        if "items" in data:
            for item in data["items"]:
                if is_valid(item):
                    try:
                        process_item(item)
                    except Exception:
                        pass
```

### 7. 正交设计

**要求说明：**

- **必须**：模块之间保持低耦合
- **必须**：每个模块有明确的输入输出边界
- **禁止**：循环依赖和隐式全局状态

**示例：**

```python
# ✅ 正确：正交设计
# 模块 A：只依赖接口，不依赖具体实现
class PaymentProcessor:
    def __init__(self, gateway: PaymentGateway):  # 依赖抽象
        self.gateway = gateway

    def process(self, amount: Decimal) -> bool:
        return self.gateway.charge(amount)

# ❌ 错误：耦合严重
class PaymentProcessor:
    def process(self, amount):
        # 直接依赖具体实现
        from alipay_sdk import Alipay
        alipay = Alipay(...)
        return alipay.charge(amount)
```

## 你必须执行的操作

### 操作 1：代码审查时检查

**执行步骤：**

1. 统计文件行数（排除空行和注释），确认≤500 行
2. 统计函数行数（排除空行和注释），确认≤50 行
3. 检查嵌套层级，确认≤3 层
4. 审查命名是否清晰有意义
5. 确认注释解释了"为什么"而非"是什么"

### 操作 2：重构超长文件

**执行步骤：**

1. 识别文件中的不同职责模块
2. 将每个职责模块提取到独立文件
3. 在新文件中保持原有函数签名
4. 在原文件中导入并转发调用
5. 运行测试确保行为不变

### 操作 3：重构超长函数

**执行步骤：**

1. 识别函数中的独立逻辑块
2. 将每个逻辑块提取为私有方法
3. 为新方法选择清晰的名称
4. 在原函数中调用新方法
5. 运行测试确保行为不变

## 检查清单

在编写或审查代码后，你必须确认：

- [ ] 所有源文件不超过 500 行（不含空行和注释）
- [ ] 所有函数不超过 50 行（不含空行和注释）
- [ ] 所有类/函数只承担单一职责
- [ ] 所有命名清晰且有意义
- [ ] 关键代码有解释"为什么"的注释
- [ ] 代码嵌套层级不超过 3 层
- [ ] 模块之间无循环依赖

## 相关资源

- 参考代码质量规则：`{{ rule_file_dir }}/code_review.md`
- 参考重构流程：`{{ rule_file_dir }}/../development_workflow/refactoring.md`
