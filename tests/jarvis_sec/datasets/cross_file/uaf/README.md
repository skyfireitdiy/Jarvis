# 跨文件UAF测试集

本目录包含跨文件Use-After-Free漏洞测试案例。

## 测试案例列表

### 1. basic_cross_file_uaf

**描述**：内存分配、使用、释放在不同文件中

**难度**：简单

**检测要点**：

- 跨函数调用链追踪
- 指针状态跨文件传播
- UAF模式识别

### 2. callback_uaf

**描述**：通过回调函数触发的UAF

**难度**：中等

**检测要点**：

- 回调函数生命周期分析
- 间接调用追踪

### 3. struct_member_uaf

**描述**：结构体成员指针的UAF

**难度**：中等

**检测要点**：

- 结构体字段访问追踪
- 成员指针状态管理

## 测试方法

```bash
# 运行单个测试案例
pytest tests/jarvis_sec/test_cross_file_analysis.py::TestCrossFileUAF::test_uaf_alloc_use_free_different_files -v

# 运行所有UAF测试
pytest tests/jarvis_sec/test_cross_file_analysis.py::TestCrossFileUAF -v
```

## 添加新测试案例

1. 在本目录创建子目录（如 `my_uaf_case/`）

2. 添加源代码文件（.c/.h）

3. 创建 `metadata.json` 描述测试信息

4. 在测试框架中添加对应的测试方法
