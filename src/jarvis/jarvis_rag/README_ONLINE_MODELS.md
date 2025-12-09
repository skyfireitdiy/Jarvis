# 在线模型使用指南

本文档介绍如何使用在线嵌入模型和重排模型。

## 概述

Jarvis RAG 框架现在支持通过抽象接口使用在线模型（API）和本地模型。这允许您：

- 使用本地 HuggingFace 模型（默认）
- 使用在线 API（如 OpenAI、Cohere、Jina 等）
- 轻松切换或混合使用不同的模型

## 接口抽象

### EmbeddingInterface

所有嵌入模型都实现 `EmbeddingInterface` 接口，提供以下方法：

- `embed_documents(texts: List[str]) -> List[List[float]]`: 为文档列表计算嵌入
- `embed_query(text: str) -> List[float]`: 为查询计算嵌入

### RerankerInterface

所有重排模型都实现 `RerankerInterface` 接口，提供以下方法：

- `rerank(query: str, documents: List[Document], top_n: int = 5) -> List[Document]`: 对文档进行重排

## 使用示例

### 使用本地模型（默认）

```python
from jarvis.jarvis_rag import JarvisRAGPipeline

# 使用默认的本地模型
pipeline = JarvisRAGPipeline()
```

### 使用在线嵌入模型

#### OpenAI 嵌入模型

```python
from jarvis.jarvis_rag import JarvisRAGPipeline
from jarvis.jarvis_rag.online_embedding import OpenAIEmbeddingModel

# 创建在线嵌入模型
embedding_model = OpenAIEmbeddingModel(
    api_key="your-api-key",  # 或设置 OPENAI_API_KEY 环境变量
    model_name="text-embedding-3-small"
)

# 注意：目前 JarvisRAGPipeline 的构造函数还不直接支持传入嵌入模型实例
# 您需要修改代码或等待后续更新
```

#### Cohere 嵌入模型

```python
from jarvis.jarvis_rag.online_embedding import CohereEmbeddingModel

embedding_model = CohereEmbeddingModel(
    api_key="your-api-key",  # 或设置 COHERE_API_KEY 环境变量
    model_name="embed-english-v3.0"
)
```

#### EdgeFn 嵌入模型

```python
from jarvis.jarvis_rag.online_embedding import EdgeFnEmbeddingModel

embedding_model = EdgeFnEmbeddingModel(
    api_key="your-api-key",  # 或设置 EDGEFN_API_KEY 环境变量
    model_name="BAAI/bge-m3"  # 或其他支持的模型
)
```

### 完整示例：使用 EdgeFn 嵌入和重排模型

```python
from jarvis.jarvis_rag.online_embedding import EdgeFnEmbeddingModel
from jarvis.jarvis_rag.online_reranker import EdgeFnReranker
from langchain.docstore.document import Document

# 初始化 EdgeFn 嵌入模型
embedding_model = EdgeFnEmbeddingModel(
    api_key="your-api-key",  # 或设置 EDGEFN_API_KEY 环境变量
    model_name="BAAI/bge-m3"
)

# 初始化 EdgeFn 重排模型
reranker = EdgeFnReranker(
    api_key="your-api-key",  # 或设置 EDGEFN_API_KEY 环境变量
    model_name="bge-reranker-v2-m3"
)

# 使用嵌入模型
documents = ["文档1内容", "文档2内容", "文档3内容"]
embeddings = embedding_model.embed_documents(documents)
query_embedding = embedding_model.embed_query("查询文本")

# 使用重排模型
doc_list = [
    Document(page_content="apple", metadata={"source": "doc1"}),
    Document(page_content="banana", metadata={"source": "doc2"}),
    Document(page_content="fruit", metadata={"source": "doc3"}),
    Document(page_content="vegetable", metadata={"source": "doc4"}),
]
reranked_docs = reranker.rerank(query="Apple", documents=doc_list, top_n=3)
```

### 使用在线重排模型

#### Cohere 重排模型

```python
from jarvis.jarvis_rag.online_reranker import CohereReranker

reranker = CohereReranker(
    api_key="your-api-key",  # 或设置 COHERE_API_KEY 环境变量
    model_name="rerank-english-v3.0"
)
```

#### Jina 重排模型

```python
from jarvis.jarvis_rag.online_reranker import JinaReranker

reranker = JinaReranker(
    api_key="your-api-key",  # 或设置 JINA_API_KEY 环境变量
    model_name="jina-reranker-v1-base-en"
)
```

#### EdgeFn 重排模型

```python
from jarvis.jarvis_rag.online_reranker import EdgeFnReranker

reranker = EdgeFnReranker(
    api_key="your-api-key",  # 或设置 EDGEFN_API_KEY 环境变量
    model_name="bge-reranker-v2-m3"  # 或其他支持的模型
)
```

## 实现自定义在线模型

### 实现自定义嵌入模型

```python
from jarvis.jarvis_rag.embedding_interface import EmbeddingInterface
from typing import List

class MyCustomEmbeddingModel(EmbeddingInterface):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # 初始化您的API客户端
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 实现您的API调用逻辑
        embeddings = []
        for text in texts:
            # 调用您的API
            embedding = self._call_your_api(text)
            embeddings.append(embedding)
        return embeddings
    
    def embed_query(self, text: str) -> List[float]:
        # 实现查询嵌入逻辑
        return self._call_your_api(text)
```

### 实现自定义重排模型

```python
from jarvis.jarvis_rag.reranker_interface import RerankerInterface
from langchain.docstore.document import Document
from typing import List

class MyCustomReranker(RerankerInterface):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # 初始化您的API客户端
    
    def rerank(
        self, query: str, documents: List[Document], top_n: int = 5
    ) -> List[Document]:
        # 实现您的重排逻辑
        doc_texts = [doc.page_content for doc in documents]
        scores = self._call_your_api(query, doc_texts)
        
        # 根据分数排序
        doc_with_scores = list(zip(documents, scores))
        doc_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [doc for doc, _ in doc_with_scores[:top_n]]
```

## 向后兼容性

为了保持向后兼容性，原有的类名仍然可用：

- `EmbeddingManager` 是 `LocalEmbeddingModel` 的别名
- `Reranker` 是 `LocalReranker` 的别名

现有代码无需修改即可继续工作。

## 注意事项

1. **API 密钥安全**: 建议使用环境变量存储 API 密钥，而不是硬编码在代码中。

2. **成本考虑**: 在线模型通常按使用量收费，请根据您的需求选择合适的模型。

3. **性能**: 在线模型需要网络请求，可能比本地模型慢，但通常提供更好的效果。

4. **依赖安装**: 使用特定的在线模型需要安装相应的 Python 包：
   - OpenAI: `pip install openai`
   - Cohere: `pip install cohere`
   - EdgeFn (嵌入和重排): `pip install requests` (已包含在大多数环境中)
   - Jina: `pip install requests` (已包含在大多数环境中)

## 未来扩展

框架设计允许轻松添加新的在线模型提供商。如果您需要支持其他 API，可以：

1. 继承 `OnlineEmbeddingModel` 或 `OnlineReranker` 基类
2. 实现 `_call_api` 方法
3. 在 `__init__.py` 中导出新类
