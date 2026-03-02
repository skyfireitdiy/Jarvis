# SOLID 设计原则规则

## 你必须遵守的核心原则

### 1. 单一职责原则 (Single Responsibility Principle, SRP)

**原则定义：**

一个类应该只有一个引起它变化的原因，即一个类只负责一项职责。

**执行要求：**

- **必须**：每个类只负责一个功能领域
- **必须**：每个类只有一个改变的理由
- **必须**：将职责不同的功能分离到不同的类中
- **禁止**：创建"上帝类"（承担过多职责的类）

**函数要求：**

- **必须**：每个函数只做一件事
- **必须**：函数名必须准确描述函数的功能
- **禁止**：一个函数做多件不相关的事

**代码示例：**

```python
# ❌ 不好的实践：违反单一职责原则
class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def save_to_database(self):
        """保存用户到数据库"""
        pass

    def send_email(self, message: str):
        """发送邮件"""
        pass

    def validate_email(self):
        """验证邮箱格式"""
        pass

# ✅ 好的实践：符合单一职责原则
class User:
    """用户数据模型，只负责存储用户信息"""
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

class UserRepository:
    """用户仓储，负责数据库操作"""
    def save(self, user: User):
        pass

class EmailService:
    """邮件服务，负责发送邮件"""
    def send(self, email: str, message: str):
        pass

class EmailValidator:
    """邮箱验证器，负责验证邮箱格式"""
    def validate(self, email: str) -> bool:
        pass
```

### 2. 开闭原则 (Open/Closed Principle, OCP)

**原则定义：**

软件实体（类、模块、函数等）应该对扩展开放，对修改关闭。

**执行要求：**

- **必须**：通过抽象和接口来支持扩展
- **必须**：在不修改现有代码的情况下，可以添加新功能
- **禁止**：为了添加新功能而修改经过测试的稳定代码
- **必须**：使用策略模式、模板方法模式等设计模式支持扩展

**实现方式：**

- 使用抽象类或接口定义规范
- 使用继承或多态实现不同行为
- 使用依赖注入将变化点隔离

**代码示例：**

```python
from abc import ABC, abstractmethod
from enum import Enum

# ❌ 不好的实践：违反开闭原则
class Order:
    def __init__(self, items: list, discount_type: str):
        self.items = items
        self.discount_type = discount_type

    def calculate_total(self) -> float:
        total = sum(item.price for item in self.items)

        # 每次添加新的折扣类型都需要修改这个方法
        if self.discount_type == "normal":
            return total * 0.9
        elif self.discount_type == "vip":
            return total * 0.8
        elif self.discount_type == "seasonal":
            return total * 0.7
        # 添加新的折扣类型需要修改这里！

# ✅ 好的实践：符合开闭原则
class DiscountStrategy(ABC):
    """折扣策略抽象类"""
    @abstractmethod
    def apply_discount(self, total: float) -> float:
        pass

class NormalDiscount(DiscountStrategy):
    def apply_discount(self, total: float) -> float:
        return total * 0.9

class VipDiscount(DiscountStrategy):
    def apply_discount(self, total: float) -> float:
        return total * 0.8

class SeasonalDiscount(DiscountStrategy):
    def apply_discount(self, total: float) -> float:
        return total * 0.7

# 添加新的折扣类型只需创建新的策略类，无需修改 Order 类
class NewYearDiscount(DiscountStrategy):
    def apply_discount(self, total: float) -> float:
        return total * 0.5

class Order:
    def __init__(self, items: list, discount_strategy: DiscountStrategy):
        self.items = items
        self.discount_strategy = discount_strategy

    def calculate_total(self) -> float:
        total = sum(item.price for item in self.items)
        return self.discount_strategy.apply_discount(total)
```

### 3. 里氏替换原则 (Liskov Substitution Principle, LSP)

**原则定义：**

子类对象必须能够替换父类对象，而不会导致程序的正确性被破坏。

**执行要求：**

- **必须**：子类必须完全实现父类的抽象方法
- **必须**：子类可以扩展父类的功能，但不能改变父类原有的功能
- **禁止**：子类重写父类方法时抛出父类未声明的异常
- **禁止**：子类重写方法时削弱父类方法的输入约束或输出约束

**判断标准：**

- 子类可以替换父类出现在任何父类出现的地方
- 替换后程序的行为应该与使用父类时一致

**代码示例：**

```python
# ❌ 不好的实践：违反里氏替换原则
class Rectangle:
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height

    def set_width(self, width: float):
        self.width = width

    def set_height(self, height: float):
        self.height = height

    def get_area(self) -> float:
        return self.width * self.height

class Square(Rectangle):
    """正方形继承自矩形，但违反了里氏替换原则"""
    def __init__(self, side: float):
        super().__init__(side, side)

    def set_width(self, width: float):
        self.width = width
        self.height = width  # 正方形宽高必须相等

    def set_height(self, height: float):
        self.height = height
        self.width = height  # 正方形宽高必须相等

# 问题：Square 不能完全替换 Rectangle
def process_rectangle(rectangle: Rectangle):
    rectangle.set_width(5)
    rectangle.set_height(4)
    # 如果传入 Rectangle，面积为 20
    # 如果传入 Square，面积为 16（行为不一致！）
    print(f"面积: {rectangle.get_area()}")

# ✅ 好的实践：符合里氏替换原则
from abc import ABC, abstractmethod

class Shape(ABC):
    """形状抽象基类"""
    @abstractmethod
    def get_area(self) -> float:
        pass

class Rectangle(Shape):
    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height

    def get_area(self) -> float:
        return self.width * self.height

class Square(Shape):
    """正方形不再继承矩形，而是独立实现 Shape 接口"""
    def __init__(self, side: float):
        self.side = side

    def get_area(self) -> float:
        return self.side * self.side

# 现在 Square 和 Rectangle 都可以替换 Shape
def process_shape(shape: Shape):
    print(f"面积: {shape.get_area()}")
```

### 4. 接口隔离原则 (Interface Segregation Principle, ISP)

**原则定义：**

客户端不应该依赖它不需要的接口，接口应该小而专一，而不是大而全。

**执行要求：**

- **必须**：将大接口拆分为多个小而专一的接口
- **必须**：客户端只依赖它需要的接口方法
- **禁止**：创建"胖接口"（包含大量方法的接口）
- **禁止**：强迫客户端实现它不需要的方法

**设计原则：**

- 接口应该按功能职责进行拆分
- 每个接口应该服务于特定的客户端
- 避免接口污染

**代码示例：**

```python
from abc import ABC, abstractmethod

# ❌ 不好的实践：违反接口隔离原则
class WorkerInterface(ABC):
    """工作接口包含了所有可能的方法，导致某些类需要实现不需要的方法"""
    @abstractmethod
    def work(self):
        pass

    @abstractmethod
    def eat(self):
        pass

    @abstractmethod
    def sleep(self):
        pass

class Robot(WorkerInterface):
    """机器人不需要 eat 和 sleep，但被迫实现这些方法"""
    def work(self):
        print("机器人工作")

    def eat(self):
        raise NotImplementedError("机器人不需要吃东西")

    def sleep(self):
        raise NotImplementedError("机器人不需要睡觉")

# ✅ 好的实践：符合接口隔离原则
class Workable(ABC):
    """可工作的接口"""
    @abstractmethod
    def work(self):
        pass

class Eatable(ABC):
    """可进食的接口"""
    @abstractmethod
    def eat(self):
        pass

class Sleepable(ABC):
    """可睡觉的接口"""
    @abstractmethod
    def sleep(self):
        pass

class Human(Workable, Eatable, Sleepable):
    """人类实现所有接口"""
    def work(self):
        print("人类工作")

    def eat(self):
        print("人类吃饭")

    def sleep(self):
        print("人类睡觉")

class Robot(Workable):
    """机器人只实现需要的接口"""
    def work(self):
        print("机器人工作")
```

### 5. 依赖倒置原则 (Dependency Inversion Principle, DIP)

**原则定义：**

高层模块不应该依赖低层模块，两者都应该依赖抽象。抽象不应该依赖细节，细节应该依赖抽象。

**执行要求：**

- **必须**：高层模块和低层模块都依赖抽象接口
- **必须**：使用依赖注入、工厂模式等方式解耦
- **禁止**：高层模块直接依赖具体的低层模块实现
- **禁止**：在模块内部直接创建具体类的实例

**实现方式：**

- 使用抽象类或接口定义依赖
- 通过构造函数注入依赖
- 使用控制反转容器管理依赖

**代码示例：**

```python
# ❌ 不好的实践：违反依赖倒置原则
class LightBulb:
    """低层模块：灯泡"""
    def turn_on(self):
        print("灯泡打开")

    def turn_off(self):
        print("灯泡关闭")

class Switch:
    """高层模块：开关"""
    def __init__(self):
        self.bulb = LightBulb()  # 直接依赖具体实现，违反依赖倒置原则
        self.on = False

    def press(self):
        if self.on:
            self.bulb.turn_off()
            self.on = False
        else:
            self.bulb.turn_on()
            self.on = True

# 问题：如果想使用其他设备（如风扇），必须修改 Switch 类

# ✅ 好的实践：符合依赖倒置原则
from abc import ABC, abstractmethod

class Switchable(ABC):
    """抽象接口：可开关的设备"""
    @abstractmethod
    def turn_on(self):
        pass

    @abstractmethod
    def turn_off(self):
        pass

class LightBulb(Switchable):
    """灯泡实现 Switchable 接口"""
    def turn_on(self):
        print("灯泡打开")

    def turn_off(self):
        print("灯泡关闭")

class Fan(Switchable):
    """风扇实现 Switchable 接口"""
    def turn_on(self):
        print("风扇打开")

    def turn_off(self):
        print("风扇关闭")

class Switch:
    """开关依赖抽象接口，不依赖具体实现"""
    def __init__(self, device: Switchable):
        self.device = device  # 依赖注入
        self.on = False

    def press(self):
        if self.on:
            self.device.turn_off()
            self.on = False
        else:
            self.device.turn_on()
            self.on = True

# 使用示例
bulb = LightBulb()
switch = Switch(bulb)
switch.press()  # 灯泡打开

fan = Fan()
switch = Switch(fan)
switch.press()  # 风扇打开
```

## 综合应用示例

### ❌ 违反 SOLID 的订单处理系统

```python
class OrderProcessor:
    """违反所有 SOLID 原则的糟糕设计"""

    def __init__(self):
        # 违反 DIP：直接依赖具体实现
        self.database = MySQLDatabase()
        self.email_sender = SMTPSender()
        self.logger = FileLogger()

    def process_order(self, order_data: dict):
        # 违反 SRP：一个方法做太多事情
        # 1. 验证订单
        if not order_data.get('user_id'):
            raise Exception("用户ID不能为空")
        if order_data.get('amount', 0) <= 0:
            raise Exception("金额必须大于0")

        # 2. 计算折扣（违反 OCP：每次添加新折扣都要修改代码）
        discount = 0
        if order_data.get('user_type') == 'vip':
            discount = 0.1
        elif order_data.get('season') == 'christmas':
            discount = 0.2
        # 添加新折扣需要修改这里

        # 3. 保存订单
        self.database.save_order(order_data)

        # 4. 发送邮件
        self.email_sender.send_email(order_data['user_id'], "订单确认")

        # 5. 记录日志
        self.logger.log(f"订单已处理: {order_data}")
```

### ✅ 符合 SOLID 的订单处理系统

```python
from abc import ABC, abstractmethod
from typing import Protocol

# ============ 抽象接口（符合 DIP、ISP） ============

class Database(ABC):
    @abstractmethod
    def save_order(self, order: 'Order') -> None:
        pass

class EmailSender(ABC):
    @abstractmethod
    def send_email(self, user_id: str, message: str) -> None:
        pass

class Logger(ABC):
    @abstractmethod
    def log(self, message: str) -> None:
        pass

class DiscountStrategy(ABC):
    @abstractmethod
    def calculate_discount(self, order: 'Order') -> float:
        pass

class OrderValidator(ABC):
    @abstractmethod
    def validate(self, order: 'Order') -> bool:
        pass

# ============ 具体实现（符合 SRP） ============

class Order:
    """订单实体：只负责存储订单数据（SRP）"""
    def __init__(self, user_id: str, amount: float, user_type: str, season: str):
        self.user_id = user_id
        self.amount = amount
        self.user_type = user_type
        self.season = season

class OrderValidatorImpl(OrderValidator):
    """订单验证器：只负责验证订单（SRP）"""
    def validate(self, order: Order) -> bool:
        if not order.user_id:
            raise ValueError("用户ID不能为空")
        if order.amount <= 0:
            raise ValueError("金额必须大于0")
        return True

class VipDiscount(DiscountStrategy):
    """VIP折扣策略（SRP + OCP：可以独立添加新策略）"""
    def calculate_discount(self, order: Order) -> float:
        return 0.1 if order.user_type == 'vip' else 0

class SeasonalDiscount(DiscountStrategy):
    """季节折扣策略（SRP + OCP）"""
    def calculate_discount(self, order: Order) -> float:
        return 0.2 if order.season == 'christmas' else 0

class DiscountCalculator:
    """折扣计算器：组合多个折扣策略（OCP）"""
    def __init__(self, strategies: list[DiscountStrategy]):
        self.strategies = strategies

    def calculate_total_discount(self, order: Order) -> float:
        return sum(strategy.calculate_discount(order) for strategy in self.strategies)

class MySQLDatabase(Database):
    """MySQL数据库实现（SRP）"""
    def save_order(self, order: Order) -> None:
        print(f"保存订单到MySQL: {order.user_id}")

class SMTPSender(EmailSender):
    """SMTP邮件发送器（SRP）"""
    def send_email(self, user_id: str, message: str) -> None:
        print(f"发送邮件给 {user_id}: {message}")

class FileLogger(Logger):
    """文件日志记录器（SRP）"""
    def log(self, message: str) -> None:
        print(f"记录日志到文件: {message}")

class OrderProcessor:
    """订单处理器：协调各个组件（SRP + DIP）"""
    def __init__(
        self,
        validator: OrderValidator,
        discount_calculator: DiscountCalculator,
        database: Database,
        email_sender: EmailSender,
        logger: Logger
    ):
        # 依赖抽象接口，不依赖具体实现（DIP）
        self.validator = validator
        self.discount_calculator = discount_calculator
        self.database = database
        self.email_sender = email_sender
        self.logger = logger

    def process_order(self, order: Order) -> None:
        # 1. 验证订单
        self.validator.validate(order)

        # 2. 计算折扣
        discount = self.discount_calculator.calculate_total_discount(order)
        final_amount = order.amount * (1 - discount)

        # 3. 保存订单
        self.database.save_order(order)

        # 4. 发送邮件
        self.email_sender.send_email(order.user_id, f"订单确认，金额: {final_amount}")

        # 5. 记录日志
        self.logger.log(f"订单已处理: {order.user_id}, 金额: {final_amount}")

# 使用示例
validator = OrderValidatorImpl()
discount_calculator = DiscountCalculator([VipDiscount(), SeasonalDiscount()])
database = MySQLDatabase()
email_sender = SMTPSender()
logger = FileLogger()

processor = OrderProcessor(
    validator,
    discount_calculator,
    database,
    email_sender,
    logger
)
order = Order("user123", 1000, "vip", "christmas")
processor.process_order(order)
```

## SOLID 检查清单

在编写代码时，你必须确认：

### 单一职责原则 (SRP)

- [ ] 每个类只有一个改变的理由
- [ ] 每个类只负责一个功能领域
- [ ] 每个函数只做一件事
- [ ] 没有承担过多职责的"上帝类"
- [ ] 类名和函数名准确反映了其职责

### 开闭原则 (OCP)

- [ ] 添加新功能时无需修改现有代码
- [ ] 使用抽象类或接口支持扩展
- [ ] 使用多态替代大量的条件判断
- [ ] 设计模式（策略模式、模板方法等）用于支持扩展
- [ ] 现有代码经过充分测试，避免频繁修改

### 里氏替换原则 (LSP)

- [ ] 子类可以完全替换父类
- [ ] 子类没有改变父类原有的行为
- [ ] 子类重写方法时没有引入新的约束
- [ ] 子类重写方法时没有抛出父类未声明的异常
- [ ] 继承关系合理，不是仅仅为了代码复用

### 接口隔离原则 (ISP)

- [ ] 接口小而专一，没有包含不相关的方法
- [ ] 客户端只依赖它需要的接口
- [ ] 没有强迫类实现不需要的方法
- [ ] 使用组合替代继承减少接口依赖
- [ ] 接口按功能职责进行合理拆分

### 依赖倒置原则 (DIP)

- [ ] 高层模块依赖抽象接口，不依赖具体实现
- [ ] 低层模块实现抽象接口
- [ ] 使用依赖注入传递依赖
- [ ] 在模块内部没有直接创建具体类的实例
- [ ] 使用工厂模式或控制反转容器管理依赖

### 综合评估

- [ ] 代码结构清晰，易于理解和维护
- [ ] 代码具有良好的可扩展性
- [ ] 单元测试易于编写和执行
- [ ] 模块之间耦合度低
- [ ] 代码符合项目的设计规范和最佳实践
