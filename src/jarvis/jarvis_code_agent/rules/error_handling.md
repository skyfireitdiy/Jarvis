# 错误处理规则

## 错误处理原则

1. **明确性**：
   - 错误信息应该清晰、具体
   - 错误应该包含足够的上下文信息
   - 使用有意义的错误类型

2. **可恢复性**：
   - 区分可恢复的错误和不可恢复的错误
   - 对于可恢复的错误，提供恢复路径
   - 对于不可恢复的错误，优雅地终止

3. **不要静默失败**：
   - 不要忽略错误
   - 不要使用空的 except 块
   - 记录所有错误，便于调试

## 最佳实践

- 使用具体的异常类型，而不是通用的 Exception
- 在适当的层级处理错误，不要过早捕获
- 提供有意义的错误消息
- 使用日志记录错误，而不是只打印
- 考虑使用 Result 类型或 Optional 来表示可能的错误

## 错误处理模式

```python
# 好的实践：具体异常 + 清晰消息
try:
    result = process_data(data)
except ValueError as e:
    logger.error(f"Invalid data format: {e}")
    return None
except FileNotFoundError as e:
    logger.error(f"Required file not found: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise RuntimeError(f"Failed to process data: {e}") from e
```

## 检查清单

- [ ] 所有可能的错误情况都被处理
- [ ] 错误消息清晰、有用
- [ ] 错误被适当地记录
- [ ] 错误处理不会隐藏真正的问题
- [ ] 有适当的错误恢复机制
