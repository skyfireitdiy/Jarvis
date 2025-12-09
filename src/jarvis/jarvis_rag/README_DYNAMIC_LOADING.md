# 动态加载自定义模型指南

本文档介绍如何使用动态加载功能添加自定义嵌入模型和重排模型。

## 概述

Jarvis RAG 框架支持动态加载自定义模型实现，类似于 `jarvis_platform` 的注册表机制。您可以在用户数据目录中创建自定义模型实现，系统会自动发现并加载它们。

## 目录结构

自定义模型应该放在以下目录：

- **嵌入模型**: `~/.jarvis/embeddings/` (或通过 `get_data_dir()` 获取的目录下的 `embeddings/`)
- **重排模型**: `~/.jarvis/rerankers/` (或通过 `get_data_dir()` 获取的目录下的 `rerankers/`)

这些目录会在首次使用时自动创建。

## 实现自定义嵌入模型

### 1. 创建模型文件

在 `~/.jarvis/embeddings/` 目录下创建一个 Python 文件，例如 `my_custom_embedding.py`:

```python
from typing import List, Optional
from jarvis.jarvis_rag.embedding_interface import EmbeddingInterface
from jarvis.jarvis_rag.embeddings.base import OnlineEmbeddingModel

class MyCustomEmbeddingModel(OnlineEmbeddingModel):
    """
    自定义嵌入模型实现示例。
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "my-model",
        base_url: str = "https://api.example.com/v1/embeddings",
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            api_key_env="MY_API_KEY",  # 环境变量名
            base_url=base_url,
            model_name=model_name,
            **kwargs,
        )
    
    def _call_api(
        self, texts: List[str], is_query: bool = False
    ) -> List[List[float]]:
        """
        实现您的 API 调用逻辑。
        """
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model_name,
            "input": texts if len(texts) > 1 else texts[0],
        }
        
        response = requests.post(
            self.base_url, headers=headers, json=payload, timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        # 根据您的 API 响应格式解析嵌入向量
        return data["embeddings"]
```

### 2. 必需的方法

自定义嵌入模型必须实现以下方法：

- `embed_documents(texts: List[str]) -> List[List[float]]`: 为文档列表计算嵌入
- `embed_query(text: str) -> List[float]`: 为查询计算嵌入

如果继承自 `OnlineEmbeddingModel`，只需要实现 `_call_api` 方法。

### 3. 使用自定义模型

```python
from jarvis.jarvis_rag.embeddings import EmbeddingRegistry

# 获取注册表
registry = EmbeddingRegistry.get_global_registry()

# 查看可用的模型
print(registry.get_available_embeddings())

# 创建自定义模型实例
embedding = registry.create_embedding(
    "MyCustomEmbeddingModel",
    api_key="your-api-key",
    model_name="my-model"
)

# 使用模型
embeddings = embedding.embed_documents(["文档1", "文档2"])
query_embedding = embedding.embed_query("查询文本")
```

## 实现自定义重排模型

### 1. 创建模型文件

在 `~/.jarvis/rerankers/` 目录下创建一个 Python 文件，例如 `my_custom_reranker.py`:

```python
from typing import List, Optional
from langchain.docstore.document import Document
from jarvis.jarvis_rag.reranker_interface import RerankerInterface
from jarvis.jarvis_rag.rerankers.base import OnlineReranker

class MyCustomReranker(OnlineReranker):
    """
    自定义重排模型实现示例。
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "my-reranker",
        base_url: str = "https://api.example.com/v1/rerank",
        **kwargs,
    ):
        super().__init__(
            api_key=api_key,
            api_key_env="MY_API_KEY",
            base_url=base_url,
            model_name=model_name,
            **kwargs,
        )
    
    def _call_api(
        self, query: str, documents: List[str]
    ) -> List[tuple[int, float]]:
        """
        实现您的 API 调用逻辑。
        返回 (索引, 分数) 元组列表，按分数降序排序。
        """
        import requests
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
        }
        
        response = requests.post(
            self.base_url, headers=headers, json=payload, timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        
        # 解析结果，返回 (索引, 分数) 列表
        results = [
            (item["index"], item["score"])
            for item in data["results"]
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
```

### 2. 必需的方法

自定义重排模型必须实现以下方法：

- `rerank(query: str, documents: List[Document], top_n: int = 5) -> List[Document]`: 对文档进行重排

如果继承自 `OnlineReranker`，只需要实现 `_call_api` 方法。

### 3. 使用自定义模型

```python
from jarvis.jarvis_rag.rerankers import RerankerRegistry
from langchain.docstore.document import Document

# 获取注册表
registry = RerankerRegistry.get_global_registry()

# 查看可用的模型
print(registry.get_available_rerankers())

# 创建自定义模型实例
reranker = registry.create_reranker(
    "MyCustomReranker",
    api_key="your-api-key",
    model_name="my-reranker"
)

# 使用模型
documents = [
    Document(page_content="文档1", metadata={"source": "doc1"}),
    Document(page_content="文档2", metadata={"source": "doc2"}),
]
reranked = reranker.rerank("查询", documents, top_n=3)
```

## 实现本地模型

您也可以实现完全自定义的本地模型（不继承基类）：

```python
from typing import List
from jarvis.jarvis_rag.embedding_interface import EmbeddingInterface

class MyLocalEmbeddingModel(EmbeddingInterface):
    """
    完全自定义的本地嵌入模型。
    """
    
    def __init__(self, model_path: str):
        # 加载您的本地模型
        self.model = load_your_model(model_path)
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # 实现文档嵌入逻辑
        return [self.model.encode(text) for text in texts]
    
    def embed_query(self, text: str) -> List[float]:
        # 实现查询嵌入逻辑
        return self.model.encode(text)
```

## 验证实现

系统会自动验证您的实现：

1. **方法检查**: 确保实现了所有必需的方法
2. **参数检查**: 确保方法参数匹配
3. **类型检查**: 确保类继承自正确的接口

如果验证失败，系统会输出错误信息，但不会中断其他模型的加载。

## 注册表 API

### EmbeddingRegistry

- `get_global_registry() -> EmbeddingRegistry`: 获取全局注册表实例
- `get_available_embeddings() -> List[str]`: 获取所有可用的嵌入模型名称
- `create_embedding(name: str, *args, **kwargs) -> Optional[EmbeddingInterface]`: 创建嵌入模型实例
- `register_embedding(name: str, embedding_class: Type[EmbeddingInterface])`: 手动注册模型类

### RerankerRegistry

- `get_global_registry() -> RerankerRegistry`: 获取全局注册表实例
- `get_available_rerankers() -> List[str]`: 获取所有可用的重排模型名称
- `create_reranker(name: str, *args, **kwargs) -> Optional[RerankerInterface]`: 创建重排模型实例
- `register_reranker(name: str, reranker_class: Type[RerankerInterface])`: 手动注册模型类

## 注意事项

1. **文件命名**: 文件名应该使用下划线命名（如 `my_custom_model.py`），类名使用驼峰命名（如 `MyCustomModel`）

2. **导入依赖**: 确保您的自定义模型所需的依赖已安装

3. **错误处理**: 建议在 `_call_api` 方法中添加适当的错误处理

4. **性能考虑**: 对于批量处理，考虑实现批处理逻辑以提高效率

5. **缓存**: 如果需要缓存，可以在自定义类中添加缓存逻辑

## 示例：完整工作流

```python
# 1. 创建自定义模型文件 ~/.jarvis/embeddings/my_api.py
# (参考上面的示例代码)

# 2. 在代码中使用
from jarvis.jarvis_rag.embeddings import EmbeddingRegistry

registry = EmbeddingRegistry.get_global_registry()

# 检查模型是否已加载
if "MyApiEmbeddingModel" in registry.get_available_embeddings():
    # 创建实例
    embedding = registry.create_embedding(
        "MyApiEmbeddingModel",
        api_key="your-key"
    )
    
    # 使用模型
    result = embedding.embed_query("测试查询")
    print(result)
else:
    print("模型未找到，请检查文件是否正确放置")
```

## 调试

如果模型未加载，检查：

1. 文件是否在正确的目录（`~/.jarvis/embeddings/` 或 `~/.jarvis/rerankers/`）
2. 文件是否以 `.py` 结尾且不以 `__` 开头
3. 类是否继承自正确的接口
4. 是否实现了所有必需的方法
5. 查看控制台输出的错误信息
