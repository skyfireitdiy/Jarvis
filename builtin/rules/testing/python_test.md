---
name: python_test
description: 当需要为Python项目编写测试或配置测试框架时触发。每当用户提及"Python测试"、"pytest"、"unittest"时触发。不触发：非Python项目测试；代码审查；性能优化。
---

# Python 测试之规

## ⚠ 要

**写毕必行测试，至修毕乃止！**

### 行要

- **必**：每改码后，即行测试
- **必**：若测试败，修码至全过
- **禁**：提交未过之码
- **禁**：于测试未过之际续行开发

### 流程

1. 写或改码
2. **即**行测试
3. 若败，修之
4. 复步 2-3，至全过
5. 全过之后，方得提交

## 汝必用之测架

### pytest（荐）

**安装命令：**

```bash
pip install pytest pytest-cov
```

**运行命令：**

```bash
pytest           # 行全测
pytest tests/test_file.py # 行特文件
pytest -v        # 详出
pytest -x        # 败时止
pytest --cov=src # 示覆盖率
```

### unittest（标准库，无需安装）

**运行命令：**

```bash
python -m unittest discover    # 行全测
python -m unittest -v          # 详出
```

## 汝必写之测例

### pytest 测例

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

### unittest 测例

```python
import unittest
from src.module import function

class TestModule(unittest.TestCase):
    def test_function(self):
        """测试正常情况"""
        self.assertEqual(function(2, 3), 5)
```

## 测试行检单

提交码前，汝必确：

- [ ] **写毕即行测试矣**
- [ ] **全测皆过矣**
- [ ] **若败，已修至过矣**
- [ ] 测覆正常之情
- [ ] 测覆边界之情
- [ ] 测覆异常之情
- [ ] 用有意义之测试名
