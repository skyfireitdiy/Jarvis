# RAG 配置指南

本文档介绍如何配置 RAG 系统的嵌入模型和重排模型。

## 配置方式

RAG 配置通过 `rag` 环境变量或 `GLOBAL_CONFIG_DATA` 中的 `rag` 键进行设置。

## 配置结构

### 基本配置

```python
rag = {
    "embedding_model": "BAAI/bge-m3",           # 模型名称
    "embedding_type": "LocalEmbeddingModel",     # 模型实现类型
    "embedding_max_length": 512,                # 嵌入模型最大输入长度（token数）
    "rerank_model": "BAAI/bge-reranker-v2-m3",  # 重排模型名称
    "reranker_type": "LocalReranker",            # 重排模型实现类型
    "reranker_max_length": 512,                 # 重排模型最大输入长度（token数）
    "use_bm25": True,                            # 是否使用BM25
    "use_rerank": True,                          # 是否使用重排
}
```

### 高级配置（带额外参数）

```python
rag = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_type": "LocalEmbeddingModel",
    "embedding_config": {
        # 额外的嵌入模型配置参数
        # 这些参数会传递给模型的构造函数
    },
    "rerank_model": "bge-reranker-v2-m3",
    "reranker_type": "EdgeFnReranker",
    "reranker_config": {
        # 额外的重排模型配置参数
        "api_key": "your-api-key",  # 如果使用在线模型
        "base_url": "https://api.example.com/v1/rerank",
    },
    "use_bm25": True,
    "use_rerank": True,
}
```

## 配置组

类似于模型组，RAG 也支持配置组：

```python
rag_group = "text"  # 或 "code"

rag_groups = [
    {
        "text": {
            "embedding_model": "BAAI/bge-m3",
            "embedding_type": "LocalEmbeddingModel",
            "rerank_model": "BAAI/bge-reranker-v2-m3",
            "reranker_type": "LocalReranker",
            "use_bm25": True,
            "use_rerank": True,
        }
    },
    {
        "code": {
            "embedding_model": "Qodo/Qodo-Embed-1-1.5B",
            "embedding_type": "LocalEmbeddingModel",
            "use_bm25": False,
            "use_rerank": False,
        }
    },
]
```

## 可用的模型类型

### 嵌入模型类型

- `LocalEmbeddingModel` - 本地 HuggingFace 模型（默认）
- `OpenAIEmbeddingModel` - OpenAI API
- `CohereEmbeddingModel` - Cohere API
- `EdgeFnEmbeddingModel` - EdgeFn API
- 自定义模型（通过动态加载）

### 重排模型类型

- `LocalReranker` - 本地 CrossEncoder 模型（默认）
- `CohereReranker` - Cohere API
- `JinaReranker` - Jina API
- `EdgeFnReranker` - EdgeFn API
- 自定义模型（通过动态加载）

## 配置示例

### 示例 1: 使用本地模型（默认）

```python
# 使用默认配置，无需设置
# 或显式设置：
rag = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_type": "LocalEmbeddingModel",
    "embedding_max_length": 512,  # 根据模型调整
    "rerank_model": "BAAI/bge-reranker-v2-m3",
    "reranker_type": "LocalReranker",
    "reranker_max_length": 512,  # 根据模型调整
}
```

### 示例 2: 使用 OpenAI 嵌入模型

```python
rag = {
    "embedding_model": "text-embedding-3-small",
    "embedding_type": "OpenAIEmbeddingModel",
    "embedding_config": {
        "api_key": "your-openai-api-key",  # 或设置 OPENAI_API_KEY 环境变量
    },
    "rerank_model": "BAAI/bge-reranker-v2-m3",
    "reranker_type": "LocalReranker",
}
```

### 示例 3: 使用 EdgeFn 在线模型

```python
rag = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_type": "EdgeFnEmbeddingModel",
    "embedding_config": {
        "api_key": "your-edgefn-api-key",  # 或设置 EDGEFN_API_KEY 环境变量
    },
    "rerank_model": "bge-reranker-v2-m3",
    "reranker_type": "EdgeFnReranker",
    "reranker_config": {
        "api_key": "your-edgefn-api-key",
    },
}
```

### 示例 4: 混合使用（本地嵌入 + 在线重排）

```python
rag = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_type": "LocalEmbeddingModel",
    "rerank_model": "rerank-english-v3.0",
    "reranker_type": "CohereReranker",
    "reranker_config": {
        "api_key": "your-cohere-api-key",  # 或设置 COHERE_API_KEY 环境变量
    },
}
```

### 示例 5: 使用自定义模型

```python
# 首先在 ~/.jarvis/embeddings/ 或 ~/.jarvis/rerankers/ 中创建自定义模型
# 然后配置使用：

rag = {
    "embedding_model": "my-custom-model",
    "embedding_type": "MyCustomEmbeddingModel",  # 自定义类名
    "embedding_config": {
        "api_key": "your-api-key",
        "custom_param": "value",
    },
}
```

## 配置优先级

配置的优先级顺序（从高到低）：

1. **顶级 rag 设置** - 直接设置的配置项
2. **rag_group 组配置** - 通过组名选择的配置
3. **代码默认值** - 硬编码的默认值

## 配置函数

系统提供了以下配置函数：

### 嵌入模型配置

- `get_rag_embedding_model() -> str`: 获取嵌入模型名称
- `get_rag_embedding_type() -> str`: 获取嵌入模型类型
- `get_rag_embedding_max_length() -> int`: 获取嵌入模型最大输入长度（token数）
- `get_rag_embedding_config() -> Dict[str, Any]`: 获取嵌入模型额外配置

### 重排模型配置

- `get_rag_rerank_model() -> str`: 获取重排模型名称
- `get_rag_reranker_type() -> str`: 获取重排模型类型
- `get_rag_reranker_max_length() -> int`: 获取重排模型最大输入长度（token数）
- `get_rag_reranker_config() -> Dict[str, Any]`: 获取重排模型额外配置

### 其他配置

- `get_rag_use_bm25() -> bool`: 是否使用BM25
- `get_rag_use_rerank() -> bool`: 是否使用重排
- `get_rag_embedding_cache_path() -> str`: 嵌入缓存路径
- `get_rag_vector_db_path() -> str`: 向量数据库路径

## 在代码中使用配置

### 方式 1: 使用 Registry 从配置创建

```python
from jarvis.jarvis_rag.embeddings import EmbeddingRegistry
from jarvis.jarvis_rag.rerankers import RerankerRegistry

# 从配置创建模型实例
embedding = EmbeddingRegistry.create_from_config()
reranker = RerankerRegistry.create_from_config()
```

### 方式 2: 手动创建（覆盖配置）

```python
from jarvis.jarvis_rag.embeddings import EmbeddingRegistry

registry = EmbeddingRegistry.get_global_registry()
embedding = registry.create_embedding(
    "LocalEmbeddingModel",
    model_name="custom-model",
    cache_dir="/custom/cache"
)
```

### 方式 3: 在 RAG Pipeline 中使用

```python
from jarvis.jarvis_rag import JarvisRAGPipeline

# RAG Pipeline 会自动从配置创建模型
pipeline = JarvisRAGPipeline()
# 内部会调用 EmbeddingRegistry.create_from_config() 和 RerankerRegistry.create_from_config()
```

## 环境变量

对于在线模型，建议使用环境变量存储 API 密钥：

```bash
export OPENAI_API_KEY="your-key"
export COHERE_API_KEY="your-key"
export EDGEFN_API_KEY="your-key"
export JINA_API_KEY="your-key"
```

然后在配置中只需要指定类型，不需要在 `embedding_config` 或 `reranker_config` 中提供 API 密钥。

## 向后兼容性

如果不指定 `embedding_type` 或 `reranker_type`，系统会：

1. 尝试从配置创建（如果配置了类型）
2. 回退到使用 `LocalEmbeddingModel` 和 `LocalReranker`（传统方式）

这确保了现有代码无需修改即可继续工作。

## 调试

如果模型创建失败，检查：

1. 配置中的类型名称是否正确（区分大小写）
2. 模型类型是否已在注册表中注册
3. 配置参数是否正确（特别是 API 密钥）
4. 查看控制台输出的错误信息

## 完整配置示例

```python
# 在环境变量或配置文件中设置
rag = {
    # 嵌入模型配置
    "embedding_model": "BAAI/bge-m3",
    "embedding_type": "LocalEmbeddingModel",
    "embedding_max_length": 512,  # 模型最大输入token数，用于文档分割
    "embedding_config": {
        # 本地模型通常不需要额外配置
        # 在线模型可能需要 api_key 等
    },
    
    # 重排模型配置
    "rerank_model": "bge-reranker-v2-m3",
    "reranker_type": "LocalReranker",
    "reranker_max_length": 512,  # 模型最大输入token数
    "reranker_config": {
        # 配置参数
    },
    
    # 功能开关
    "use_bm25": True,
    "use_rerank": True,
}

# 或使用配置组
rag_group = "text"
rag_groups = [
    {
        "text": {
            "embedding_model": "BAAI/bge-m3",
            "embedding_type": "LocalEmbeddingModel",
            "rerank_model": "BAAI/bge-reranker-v2-m3",
            "reranker_type": "LocalReranker",
            "use_bm25": True,
            "use_rerank": True,
        }
    },
]
```
