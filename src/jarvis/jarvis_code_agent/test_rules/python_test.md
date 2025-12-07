# Python 测试规则

## ⚠️ 核心要求

**编写完成务必执行测试，直到修复完成为止！**

- 每次代码修改后，必须立即运行测试
- 如果测试失败，必须修复代码直到所有测试通过
- 不允许提交未通过测试的代码

## 测试框架

### pytest（推荐）

```bash
pytest                    # 运行所有测试
pytest tests/test_file.py # 运行特定文件
pytest -v                 # 详细输出
pytest -x                 # 失败时停止
pytest --cov=src          # 显示覆盖率
```

### unittest（标准库）

```bash
python -m unittest discover    # 运行所有测试
python -m unittest -v          # 详细输出
```

## 测试示例

### pytest

```python
import pytest
from src.module import function

def test_function():
    assert function(2, 3) == 5

def test_error_case():
    with pytest.raises(ValueError):
        function(-1, 0)
```

### unittest

```python
import unittest
from src.module import function

class TestModule(unittest.TestCase):
    def test_function(self):
        self.assertEqual(function(2, 3), 5)
```

## 检查清单

- [ ] **编写完成后立即运行测试**
- [ ] **所有测试通过后才提交代码**
- [ ] **测试失败时，修复代码直到通过**
- [ ] 测试覆盖正常、边界和异常情况
- [ ] 使用有意义的测试名称
