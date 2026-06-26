# 启发式规则测试数据集

本目录包含为每个启发式规则提供的测试数据集，用于验证规则的准确性和减少误报。

## 目录结构

```
datasets/
├── possible_null_deref/          # 空指针解引用检测
│   ├── positive_no_check.c       # 正例：应该检测到
│   ├── negative_if_check.c       # 反例：不应该检测到
│   └── ...
├── data_race_suspect/            # 数据竞争检测
│   ├── positive_write_no_lock.c  # 正例：应该检测到
│   ├── negative_with_mutex.c     # 反例：不应该检测到
│   └── ...
└── ...                           # 其他规则
```

## 文件命名规范

- **正例文件**：`positive_*.c` 或 `positive_*.cpp`
  - 包含应该被检测到的真实问题
  - 文件头部注释说明预期检测到的规则名称

- **反例文件**：`negative_*.c` 或 `negative_*.cpp`
  - 包含不应该被检测到的安全代码
  - 用于验证规则不会产生误报

## 测试数据集用途

1. **验证规则准确性**：确保规则能正确检测真实问题
2. **减少误报**：确保规则不会误报安全代码
3. **持续优化基准**：为后续规则优化提供验证基准

## 使用方法

### 手动验证

```python
from jarvis.jarvis_sec.checkers.c_checker import analyze_c_cpp_text

# 读取测试文件
with open('datasets/possible_null_deref/positive_no_check.c', 'r') as f:
    src = f.read()

# 分析代码
issues = analyze_c_cpp_text('test.c', src)

# 检查是否检测到预期问题
assert any(i.pattern == 'possible_null_deref' for i in issues)
```

### 批量验证

可以使用测试框架批量验证所有测试数据集：

```bash
pytest tests/jarvis_sec/test_checkers.py -v
```

## 规则列表

| 规则名称                     | 目录                          | 说明                       |
| ---------------------------- | ----------------------------- | -------------------------- |
| possible_null_deref          | possible_null_deref/          | 空指针解引用检测           |
| data_race_suspect            | data_race_suspect/            | 数据竞争检测               |
| unsafe_api                   | unsafe_api/                   | 不安全API检测              |
| malloc_no_null_check         | malloc_no_null_check/         | malloc返回值检查           |
| format_string                | format_string/                | 格式化字符串检测           |
| uaf_suspect                  | uaf_suspect/                  | Use-After-Free检测         |
| double_free                  | double_free/                  | Double Free检测            |
| command_execution            | command_execution/            | 命令执行检测               |
| alloc_size_overflow          | alloc_size_overflow/          | 分配大小溢出检测           |
| scanf_no_width               | scanf_no_width/               | scanf宽度检测              |
| insecure_tmpfile             | insecure_tmpfile/             | 不安全临时文件检测         |
| atoi_family                  | atoi_family/                  | atoi家族检测               |
| rand_insecure                | rand_insecure/                | rand不安全检测             |
| strtok_nonreentrant          | strtok_nonreentrant/          | strtok不可重入检测         |
| pthread_returns_unchecked    | pthread_returns_unchecked/    | pthread返回值检查          |
| thread_leak_no_join          | thread_leak_no_join/          | 线程泄漏检测               |
| deadlock_patterns            | deadlock_patterns/            | 死锁模式检测               |
| uninitialized_ptr_use        | uninitialized_ptr_use/        | 未初始化指针使用检测       |
| smart_ptr_cycle              | smart_ptr_cycle/              | 智能指针循环检测           |
| smart_ptr_get_unsafe         | smart_ptr_get_unsafe/         | 智能指针get()不安全检测    |
| new_delete_mismatch          | new_delete_mismatch/          | new/delete不匹配检测       |
| reinterpret_cast_unsafe      | reinterpret_cast_unsafe/      | reinterpret_cast不安全检测 |
| const_cast_unsafe            | const_cast_unsafe/            | const_cast不安全检测       |
| missing_virtual_dtor         | missing_virtual_dtor/         | 缺少虚析构函数检测         |
| move_after_use               | move_after_use/               | move后使用检测             |
| uncaught_exception           | uncaught_exception/           | 未捕获异常检测             |
| vector_string_bounds_check   | vector_string_bounds_check/   | vector字符串边界检查       |
| strncpy_no_nullterm          | strncpy_no_nullterm/          | strncpy未终止检测          |
| realloc_assign_back          | realloc_assign_back/          | realloc未赋回检测          |
| function_return_ptr_no_check | function_return_ptr_no_check/ | 函数返回指针未检查         |
| unchecked_io                 | unchecked_io/                 | I/O返回值未检查            |
| alloca_unbounded             | alloca_unbounded/             | alloca无界检测             |
| vla_usage                    | vla_usage/                    | VLA使用检测                |
| cond_wait_no_loop            | cond_wait_no_loop/            | cond_wait无循环检测        |
| inet_legacy                  | inet_legacy/                  | inet旧版API检测            |
| time_apis_not_threadsafe     | time_apis_not_threadsafe/     | 时间API不线程安全检测      |
| getenv_unchecked             | getenv_unchecked/             | getenv未检查检测           |
| open_permissive_perms        | open_permissive_perms/        | 权限过于宽松检测           |

## 贡献指南

添加新的测试数据集时，请遵循以下规范：

1. 为每个规则创建独立目录
2. 提供至少一个正例和一个反例
3. 文件头部添加注释说明预期检测结果
4. 使用 `.c` 扩展名用于C代码，`.cpp` 用于C++代码
5. 文件命名遵循 `positive_*.c` 和 `negative_*.c` 规范
