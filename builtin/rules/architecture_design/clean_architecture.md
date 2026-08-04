---
name: clean_architecture
description: 当需要设计或评估整洁架构时触发。每当用户提及"整洁架构"、"分层架构"、"依赖规则"、"业务逻辑分离"、"解耦框架"、"可测试架构"时触发。不触发：仅代码规范不涉及架构设计；SOLID原则（用solid规则）；仅重构不涉及架构评估。
---

# 整洁架构规则

## 汝必守之核心原则

### 1. 依赖规则（最高优先级）

**执行要求：**

- **必**：源码依赖只可指向内层，不可指向外层
- **必**：内层不知外层之任何细节
- **必**：外层通过接口依赖内层
- **禁**：内层引用外层之类、函数或模块

**依赖方向：**

```text
Frameworks & Drivers (最外层)

  ↑
Interface Adapters
         ↑
   Use Cases
         ↑
   Entities (最内层)
```

### 2. 关注点分离原则

**执行要求：**

- **必**：业务逻辑与外部细节完全分离
- **必**：核心业务规则不赖框架、数据库、UI 等外部细节
- **必**：外部细节（数据库、Web、UI）作为插件插入
- **禁**：业务逻辑中混入框架、数据库、UI 相关代码

**关注点分类：**

- **Entities（实体）**：企业级业务规则
- **Use Cases（用例）**：应用特定之业务规则
- **Interface Adapters（接口适配器）**：数据格式转换
- **Frameworks & Drivers（框架驱动）**：外部工具与框架

### 3. 可测试性原则

**执行要求：**

- **必**：核心业务逻辑可在不赖外部框架之情形下测试
- **必**：Use Cases 可在无数据库、Web 框架之情形下测试
- **必**：用依赖注入便于测试
- **禁**：测试需启动完整之外部系统（如数据库、Web 服务器）

## 汝必理解之架构层次

### 1. Entities 层（实体层）

**职责：**

- 封装企业级业务规则
- 为最内层，不赖任何外层
- 可跨多个应用使用

**要求：**

- **必**：不赖任何框架
- **必**：不赖数据库、UI、Web 等
- **必**：可独立测试

### 2. Use Cases 层（用例层）

**职责：**

- 封装应用特定之业务规则
- 编排 Entities 完成业务目标
- 驱动 Entities 工作

**要求：**

- **必**：不赖框架、数据库、UI
- **必**：只赖 Entities 层
- **必**：定义接口供外层实现

### 3. Interface Adapters 层（接口适配器层）

**职责：**

- 数据格式转换
- 将 Use Cases 之数据格式转换为框架或数据库所需之格式
- 将外部输入转换为 Use Cases 所需之格式

**要求：**

- **必**：不赖框架细节
- **必**：只赖 Use Cases 与 Entities 层
- **必**：通过接口与外层交互

### 4. Frameworks & Drivers 层（框架驱动层）

**职责：**

- 含框架、数据库、Web 框架、UI 等外部工具
- 为最外层，不含任何业务逻辑
- 提供具体实现

**要求：**

- **必**：不含业务规则
- **必**：赖所有内层
- **必**：易被替换（通过接口）

## 实践规范（必守）

### 依赖管理

- **必**：定义接口于内层，实现放于外层
- **必**：用依赖注入将外层实现注入内层
- **禁**：内层直接引用外层具体类
- **禁**：业务逻辑中直接调用框架 API

### 业务逻辑隔离

- **必**：业务规则代码只现于 Entities 与 Use Cases 层
- **禁**：于 Interface Adapters 或 Frameworks 层编写业务逻辑
- **禁**：于业务逻辑中混入数据库操作、HTTP 请求等

### 数据访问分离

- **必**：Entities 不赖任何数据库实现
- **必**：通过接口（Repository）访问数据
- **必**：数据库实现放于 Frameworks 层

## 代码示例

### ❌ 不善之实践（违反整洁架构）

```python
# 业务逻辑直接依赖数据库和框架

class OrderService:
    def __init__(self):
        # 违反：内层直接依赖外层的数据库框架
        self.db = DatabaseConnection()  # 依赖数据库框架
        self.http_client = HttpClient()   # 依赖 HTTP 框架

    def process_order(self, order_id: int) -> dict:
        # 违反：业务逻辑中混入数据库操作
        order_data = self.db.query(f"SELECT * FROM orders WHERE id = {order_id}")

        # 违反：业务逻辑中混入 HTTP 请求
        user_data = self.http_client.get(f"/api/users/{order_data['user_id']}")

        # 业务规则
        if order_data['amount'] > 1000 and user_data['is_vip']:
            discount = 0.1
        else:
            discount = 0.0

        # 违反：直接返回数据库格式的数据
        return {
            'order_id': order_id,
            'total': order_data['amount'] * (1 - discount),
            'raw_data': order_data  # 暴露内部数据结构
        }
```

### ✅ 善之实践（合整洁架构）

```python
# Entities 层：业务规则

class Order:
    def __init__(self, order_id: int, amount: float, user_id: int):
        self.order_id = order_id
        self.amount = amount
        self.user_id = user_id

    def calculate_discount(self, user_is_vip: bool) -> float:
        """计算折扣（业务规则）"""
        if self.amount > 1000 and user_is_vip:
            return 0.1
        return 0.0


# Use Cases 层：应用业务规则

class ProcessOrderUseCase:
    def __init__(self, order_repository: 'OrderRepository', user_service: 'UserService'):
        # 依赖注入：通过接口依赖外层
        self.order_repository = order_repository
        self.user_service = user_service

    def execute(self, order_id: int) -> ProcessOrderResult:
        """处理订单（应用逻辑）"""
        order = self.order_repository.get_by_id(order_id)
        user = self.user_service.get_user(order.user_id)

        discount = order.calculate_discount(user.is_vip)
        total = order.amount * (1 - discount)

        return ProcessOrderResult(
            order_id=order_id,
            total=total,
            discount=discount
        )


# 数据类（DTO）

class ProcessOrderResult:
    def __init__(self, order_id: int, total: float, discount: float):
        self.order_id = order_id
        self.total = total
        self.discount = discount


# 接口定义（在内层）

from abc import ABC, abstractmethod

class OrderRepository(ABC):
    @abstractmethod
    def get_by_id(self, order_id: int) -> Order:
        pass

    @abstractmethod
    def save(self, order: Order) -> None:
        pass


class UserService(ABC):
    @abstractmethod
    def get_user(self, user_id: int) -> 'User':
        pass


class User:
    def __init__(self, user_id: int, is_vip: bool):
        self.user_id = user_id
        self.is_vip = is_vip


# Frameworks 层：具体实现（外层）

class DatabaseOrderRepository(OrderRepository):
    def __init__(self, db_connection: 'DatabaseConnection'):
        self.db = db_connection  # 外层依赖框架

    def get_by_id(self, order_id: int) -> Order:
        # 数据库操作被封装在外层
        data = self.db.query("SELECT * FROM orders WHERE id = %s", order_id)
        return Order(data['id'], data['amount'], data['user_id'])

    def save(self, order: Order) -> None:
        self.db.execute(
            "INSERT INTO orders VALUES (%s, %s, %s)",
            order.order_id, order.amount, order.user_id
        )


class HttpUserService(UserService):
    def __init__(self, http_client: 'HttpClient'):
        self.http = http_client  # 外层依赖框架

    def get_user(self, user_id: int) -> User:
        # HTTP 请求被封装在外层
        data = self.http.get(f"/api/users/{user_id}")
        return User(data['id'], data['is_vip'])
```

## 整洁架构检查清单

编写代码前，汝必确认：

### 依赖方向检查

- [ ] 源码依赖方向是否向内指向
- [ ] 内层是否无引用外层之具体类
- [ ] 接口定义是否在内层
- [ ] 具体实现是否在外层

### 业务逻辑检查

- [ ] 业务规则是否只现于 Entities 与 Use Cases 层
- [ ] 业务逻辑是否独立于框架、数据库、UI
- [ ] Entities 是否不赖任何外部细节
- [ ] Use Cases 是否只赖 Entities 层

### 数据访问检查

- [ ] 数据库操作是否被封装于最外层
- [ ] 是否通过接口（Repository）访问数据
- [ ] 数据格式转换是否在 Interface Adapters 层
- [ ] 是否暴露内部数据结构

### 可测试性检查

- [ ] 核心业务逻辑是否可在不启动外部系统之情形下测试
- [ ] 是否用依赖注入便于测试
- [ ] 是否可轻松 Mock 外层依赖
- [ ] 测试是否需要数据库、Web 服务器等外部设施

### 架构分层检查

- [ ] Entities 层是否只含企业级业务规则
- [ ] Use Cases 层是否编排 Entities 完成业务目标
- [ ] Interface Adapters 层是否只做数据格式转换
- [ ] Frameworks 层是否不含任何业务逻辑

### 代码组织检查

- [ ] 各层代码是否放于不同之目录或包中
- [ ] 是否有清晰之层边界
- [ ] 是否有明确之接口定义
- [ ] 是否易于理解与维护
