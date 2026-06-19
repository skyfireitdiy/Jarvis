---
name: extract_magnet_from_torrent
description: 当需要从 torrent 种子文件中提取磁力链接时使用此规则——torrent 磁力链接提取，指导如何从 .torrent 文件（bencode 格式）中解析出 info_hash 并构建 magnet 链接。包括：解析 bencode 格式的 torrent 文件；计算 info_hash（SHA1）；构建 magnet:?xt=urn:btih: 格式的磁力链接；批量处理多个 torrent 文件。每当用户提及"提取磁力链接"、"torrent 转 magnet"、"种子转磁力"、"从 torrent 获取 magnet"或需要从 BT 种子文件中获取可分享的磁力链接时触发，无论使用何种编程语言。如果需要从 torrent 二进制数据中提取磁力链接，请使用此规则。
---

# Torrent 文件提取磁力链接规则

## 规则简介

本规则指导如何从 .torrent 种子文件（bencode 编码格式）中提取磁力链接（magnet link）。核心原理是解析 torrent 文件中的 `info` 字典，计算其 SHA1 哈希值作为 `btih`，然后构建标准格式的磁力链接。此方法无需第三方库，仅使用标准库即可完成。

## 你必须遵守的原则

### 1. 优先使用标准库解析

**要求说明：**

- **必须**：优先使用编程语言标准库解析 torrent 文件，避免引入第三方依赖
- **必须**：torrent 文件使用 bencode 编码，需手动解析或使用标准库
- **禁止**：假设 torrent 文件可直接读取为文本，bencode 是二进制格式
- **禁止**：使用需要 pip install 的第三方库（如 bencodepy），除非环境已预装

### 2. 磁力链接构建规范

**要求说明：**

- **必须**：磁力链接格式为 `magnet:?xt=urn:btih:{INFO_HASH}&dn={FILENAME}`
- **必须**：INFO_HASH 使用大写十六进制字符串
- **必须**：从 torrent 文件的 `info` 字典计算 SHA1 哈希，而非整个文件
- **可选**：可添加 `&tr=` 参数包含 tracker 地址

### 3. 正确处理编码

**要求说明：**

- **必须**：文件名可能包含中文等非 ASCII 字符，需进行 URL 编码
- **必须**：处理 torrent 文件时使用二进制模式（rb）读取
- **必须**：info_hash 计算使用原始二进制数据，不进行任何编码转换

## 你必须执行的操作

### 操作1：解析 torrent 文件并提取 info_hash

**执行步骤：**

1. 以二进制模式获取 torrent 文件数据（从文件读取或 HTTP 下载）
2. 在数据中定位 `4:info` 标记，找到 `info` 字典的起始位置
3. 从 `info` 字典起始位置开始，解析 bencode 字典结构找到对应的结束 `e`
4. 提取 `info` 字典的完整二进制数据（从 `d` 到匹配的 `e`）
5. 对提取的二进制数据计算 SHA1 哈希值
6. 将哈希值转换为大写十六进制字符串作为 btih

**Python 实现示例：**

```python
import hashlib

def extract_info_hash(torrent_data: bytes) -> str:
    """从 torrent 二进制数据中提取 info_hash"""
    info_marker = b'4:info'
    idx = torrent_data.find(info_marker)
    if idx < 0:
        raise ValueError('Invalid torrent file: no info section')
    
    info_start = idx + len(info_marker)
    depth = 0
    info_end = -1
    
    for i in range(info_start, len(torrent_data)):
        b = torrent_data[i:i+1]
        if b == b'd':
            depth += 1
        elif b == b'e':
            if depth == 0:
                info_end = i + 1
                break
            depth -= 1
    
    if info_end <= info_start:
        raise ValueError('Invalid torrent file: cannot find info end')
    
    info_data = torrent_data[info_start:info_end]
    return hashlib.sha1(info_data).hexdigest().upper()
```

### 操作2：构建磁力链接

**执行步骤：**

1. 使用提取的 info_hash 构建基础磁力链接：`magnet:?xt=urn:btih:{info_hash}`
2. 可选添加 `dn` 参数（显示名称），需进行 URL 编码
3. 可选从 torrent 中提取 `announce` 和 `announce-list` 字段添加 tracker
4. 输出完整的磁力链接字符串

**Python 实现示例：**

```python
import urllib.parse

def build_magnet(info_hash: str, filename: str = '', trackers: list = None) -> str:
    """构建磁力链接"""
    magnet = f'magnet:?xt=urn:btih:{info_hash}'
    if filename:
        magnet += f'&dn={urllib.parse.quote(filename)}'
    if trackers:
        for tr in trackers:
            magnet += f'&tr={urllib.parse.quote(tr, safe="")}'
    return magnet
```

### 操作3：批量处理多个 torrent 文件

**执行步骤：**

1. 获取 torrent 文件列表（从 API 或本地目录）
2. 对每个文件执行操作1和操作2
3. 汇总所有磁力链接，按版本/质量分类输出
4. 注意去重：不同文件名可能对应相同的 info_hash

## 检查清单

在完成任务后，你必须确认：

- [ ] 磁力链接格式正确：`magnet:?xt=urn:btih:40位十六进制哈希`
- [ ] info_hash 长度为 40 个十六进制字符
- [ ] 文件名中的中文已正确 URL 编码
- [ ] 已区分不同版本（分辨率、编码、音轨等）
- [ ] 已去重（相同 info_hash 的不同文件名）
- [ ] 磁力链接可直接在 BT 客户端中使用

## 相关资源

- 参考规则：`{{ rule_file_dir }}/web_scraping.md`（如需要从网页获取 torrent 文件）
- 参考规则：`{{ rule_file_dir }}/api_integration.md`（如需要调用 API 获取 torrent 文件）