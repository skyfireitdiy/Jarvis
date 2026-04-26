---
name: file_encoding_detection
description: 文件编码检测与一致性处理规范
---

# 文件编码检测与一致性处理规范

## 功能概述

使用 charset-normalizer 库提供准确的文件编码检测，并确保文件读写时使用相同的编码，避免编码不一致导致的数据损坏。

## 接口定义

### detect_file_encoding 函数

```python
def detect_file_encoding(
    file_path: str,
    sample_size: int = 16384
) -> Optional[str]
```

#### 参数说明

- `file_path`: 文件路径
- `sample_size`: 用于检测的字节数，默认 16KB

#### 返回值说明

- 检测到的编码名称（如 'utf-8', 'gbk' 等）
- 若检测失败，返回 None

### EditFileNormalTool 编码处理

#### \_read_file_with_backup

```python
def _read_file_with_backup(
    file_path: str
) -> Tuple[str, Optional[str], Optional[str]]
```

返回值：`(文件内容, 备份文件路径, 检测到的编码)`

#### \_write_file_with_rollback

```python
def _write_file_with_rollback(
    abs_path: str,
    content: str,
    backup_path: Optional[str],
    encoding: Optional[str] = None
) -> Tuple[bool, Optional[str]]
```

新增 `encoding` 参数，优先使用传入的编码。

## 功能行为

### 正常情况

- UTF-8 文件检测为 'utf-8'
- GBK 文件检测为 'gbk'
- 读写使用相同编码

### 边界情况

- 空文件：默认返回 'utf-8'
- 二进制文件：返回 None
- 混合编码：返回最可能的编码

### 异常情况

- 文件不存在：返回 None
- 权限不足：返回 None
- 检测失败：返回 None

## 验收标准

1. 使用 charset-normalizer 库进行编码检测
2. 检测准确率高于原有实现
3. edit_file 读写使用相同编码
4. 现有功能不受影响
5. 支持常见编码：UTF-8, GBK, GB2312, UTF-16, Latin1 等
