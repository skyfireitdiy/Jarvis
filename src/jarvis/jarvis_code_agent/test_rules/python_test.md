# Python 测试规则

## ⚠️ 你必须遵守的核心要求

**编写完成务必执行测试，直到修复完成为止！**

### 执行要求

- **必须**：每次代码修改后，立即运行测试
- **必须**：如果测试失败，修复代码直到所有测试通过
- **禁止**：提交未通过测试的代码
- **禁止**：在测试未通过的情况下继续开发

### 工作流程

1. 编写或修改代码
2. **立即**运行测试
3. 如果测试失败，修复代码
4. 重复步骤 2-3，直到所有测试通过
5. 确认所有测试通过后，才能提交代码

## 你必须使用的测试框架

### pytest（推荐使用）

**安装命令：**

```bash
pip install pytest pytest-cov
```

**运行命令：**

```bash
pytest                    # 运行所有测试
pytest tests/test_file.py # 运行特定文件
pytest -v                 # 详细输出
pytest -x                 # 失败时停止
pytest --cov=src          # 显示覆盖率
```

### unittest（标准库，无需安装）

**运行命令：**

```bash
python -m unittest discover    # 运行所有测试
python -m unittest -v          # 详细输出
```

## 你必须编写的测试示例

### pytest 测试格式

```python
import pytest
from src.module import function

def test_function():
    """测试正常情况"""
    assert function(2, 3) == 5

def test_error_case():
    """测试异常情况"""
    with pytest.raises(ValueError):
        function(-1, 0)
```

### unittest 测试格式

```python
import unittest
from src.module import function

class TestModule(unittest.TestCase):
    def test_function(self):
        """测试正常情况"""
        self.assertEqual(function(2, 3), 5)
```

## 测试执行检查清单

在提交代码前，你必须确认：

- [ ] **编写完成后立即运行了测试**
- [ ] **所有测试都通过了**
- [ ] **如果测试失败，已修复代码直到通过**
- [ ] 测试覆盖了正常情况
- [ ] 测试覆盖了边界情况
- [ ] 测试覆盖了异常情况
- [ ] 使用了有意义的测试名称
