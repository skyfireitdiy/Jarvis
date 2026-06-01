# 压缩逻辑删除功能规范

## 功能概述

在 `src/jarvis/jarvis_platform/base.py` 文件中，需要删除与压缩相关的逻辑，仅保留 `trim_messages` 方法。压缩相关的功能将保留在 `src/jarvis/jarvis_agent/run_loop.py` 中，实现压缩逻辑的集中管理。

## 接口定义

### 函数签名

```python
# 保留的接口
def trim_messages(self) -> bool:
    """裁剪消息历史以腾出token空间
    当剩余token不足时，通过裁剪历史消息来腾出空间。
    默认实现应保留system消息，并丢弃开头的10条非system消息。

    返回:
        bool: 如果成功腾出空间返回True，否则返回False
    """
    raise NotImplementedError("trim_messages is not implemented")

# 删除的接口
def apply_compression_strategy(self, strategy_type: str = "adaptive") -> bool:
def _check_and_apply_compression(self) -> bool:
```

## 输入输出说明

### 保留功能
- `trim_messages`: 用于裁剪消息历史，保留 system 消息并丢弃开头的10条非system消息
- 返回值：布尔类型，表示是否成功腾出空间

### 删除功能
- `apply_compression_strategy`: 应用指定的压缩策略功能
- `_check_and_apply_compression`: 检查并应用压缩策略功能
- 类中的压缩相关属性：`_summarizing`, `_compression_applied`

## 功能行为

### 正常情况

1. 保留 `trim_messages` 抽象方法，供子类实现具体裁剪逻辑
2. 保留 `_truncate_message_if_needed` 方法中对 `trim_messages` 的调用
3. 删除所有与压缩策略相关的代码

### 边界情况

1. 当子类没有实现 `trim_messages` 时，应抛出 `NotImplementedError`
2. 确保删除压缩逻辑后，其他功能不受影响

### 异常情况

1. 保留现有的异常处理机制
2. 确保删除压缩逻辑不影响原有的错误处理

## 验收标准

1. `src/jarvis/jarvis_platform/base.py` 中的 `apply_compression_strategy` 方法被删除
2. `src/jarvis/jarvis_platform/base.py` 中的 `_check_and_apply_compression` 方法被删除
3. `src/jarvis/jarvis_platform/base.py` 中与压缩相关的属性被删除或保留为通用属性
4. `trim_messages` 方法及其调用被保留
5. `src/jarvis/jarvis_agent/run_loop.py` 中的压缩逻辑保持不变
6. 代码功能正常，无语法错误
7. 压缩功能仍然可以通过 `run_loop.py` 中的逻辑正常工作
