# Jarvis RAG - 检索增强生成

## 工具介绍
Jarvis RAG 是一个基于检索增强生成（RAG）技术的文档处理工具，支持多种文档格式的处理和索引。它使用 FAISS 进行向量搜索，能够高效处理大规模文档集。

## 主要功能
- 多格式文档处理（PDF、DOCX、文本文件）
- 文档内容索引和向量化
- 基于语义的文档搜索
- 文档内容问答
- 文档缓存管理

## 使用场景
- 大规模文档集的快速搜索
- 基于文档内容的智能问答
- 文档内容的自动摘要
- 跨文档的信息整合
- 文档内容的语义分析

## 使用方法
```bash
jarvis-rag [options]
```

### 可用选项
- `--dir`: 指定文档目录 (默认: 当前目录)
- `--build`: 创建或更新文档索引
- `--search`: 搜索相关文档
  - `query`: 搜索查询
- `--ask`: 回答基于文档内容的问题
  - `question`: 要回答的问题

## 技术实现
- 使用 FAISS 进行向量搜索
- 支持多线程处理
- 自动管理文档缓存
- 集成多种文档解析器（PDF、DOCX、文本）
- 使用 transformer 模型进行语义理解

## 使用示例
1. 创建文档索引：
```bash
jarvis-rag --dir /path/to/documents --build
```

2. 搜索相关文档：
```bash
jarvis-rag --search "人工智能发展趋势"
```

3. 回答文档问题：
```bash
jarvis-rag --ask "机器学习的主要应用领域有哪些？"
```

## 相关文档
- [文档索引管理](document-indexing.md)
- [文档搜索指南](document-search.md)
- [文档问答最佳实践](document-qa.md)
