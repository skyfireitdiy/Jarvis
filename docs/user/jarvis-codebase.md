# Jarvis Codebase - 代码库管理

## 工具介绍
Jarvis Codebase 是一个智能代码库管理工具，提供代码库索引生成、代码搜索和问答功能。它使用 FAISS 进行向量搜索，能够高效处理大型代码库。

## 主要功能
- 代码库索引生成和管理
- 基于语义的代码搜索
- 代码库问答
- 代码库文档导出

## 使用场景
- 快速定位代码库中的相关代码
- 回答关于代码库的问题
- 生成代码库文档
- 维护代码库索引

## 使用方法
```bash
jarvis-codebase <command> [options]
```

### 可用命令
- `generate`: 生成代码库索引
  - `--force`: 强制重建索引
- `search`: 搜索相关代码文件
  - `query`: 搜索查询
  - `--top-k`: 返回结果数量 (默认: 20)
- `ask`: 回答关于代码库的问题
  - `question`: 要回答的问题
  - `--top-k`: 使用的相关文件数量 (默认: 20)
- `export`: 导出当前索引数据

## 技术实现
- 使用 FAISS 进行向量搜索
- 支持多线程处理
- 自动管理代码库缓存
- 集成 git 版本控制

## 使用示例
1. 生成代码库索引：
```bash
jarvis-codebase generate
```

2. 搜索相关代码：
```bash
jarvis-codebase search "用户登录功能"
```

3. 回答代码库问题：
```bash
jarvis-codebase ask "如何处理用户认证？"
```

4. 导出代码库文档：
```bash
jarvis-codebase export
```

## 相关文档
- [代码库索引管理](codebase-index.md)
- [代码搜索指南](code-search.md)
- [代码库问答最佳实践](codebase-qa.md)
