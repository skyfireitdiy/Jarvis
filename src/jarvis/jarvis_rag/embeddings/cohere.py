"""
Cohere 嵌入模型实现。
"""

from typing import List
from typing import Optional
from typing import cast

from .base import OnlineEmbeddingModel


class CohereEmbeddingModel(OnlineEmbeddingModel):
    """
    Cohere 嵌入模型的实现。

    使用 Cohere 的 embed API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "embed-english-v3.0",
        input_type: str = "search_document",
        **kwargs,
    ):
        """
        初始化 Cohere 嵌入模型。

        参数:
            api_key: Cohere API密钥。如果为None，将从COHERE_API_KEY环境变量读取。
            model_name: 要使用的模型名称。
            input_type: 输入类型（'search_document' 或 'search_query'）。
            **kwargs: 传递给父类的其他参数。
        """
        super().__init__(
            api_key=api_key,
            api_key_env="COHERE_API_KEY",
            model_name=model_name,
            **kwargs,
        )
        self.input_type = input_type

    def _call_api(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        调用 Cohere API 获取嵌入。
        """
        try:
            import cohere

            client = cohere.Client(api_key=self.api_key)

            input_type = "search_query" if is_query else "search_document"

            response = client.embed(
                texts=texts,
                model=self.model_name,
                input_type=input_type,
            )

            return cast(List[List[float]], response.embeddings)
        except ImportError:
            raise ImportError(
                "使用 CohereEmbeddingModel 需要安装 cohere 包: pip install cohere"
            )
        except Exception as e:
            raise RuntimeError(f"调用 Cohere API 时出错: {e}")
