"""
OpenAI 嵌入模型实现。
"""

from typing import List
from typing import Optional

from .base import OnlineEmbeddingModel


class OpenAIEmbeddingModel(OnlineEmbeddingModel):
    """
    OpenAI 嵌入模型的实现。

    使用 OpenAI 的 embeddings API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "text-embedding-3-small",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        """
        初始化 OpenAI 嵌入模型。

        参数:
            api_key: OpenAI API密钥。如果为None，将从OPENAI_API_KEY环境变量读取。
            model_name: 要使用的模型名称（如 'text-embedding-3-small'）。
            base_url: API的基础URL（用于自定义端点）。
            **kwargs: 传递给父类的其他参数。
        """
        super().__init__(
            api_key=api_key,
            api_key_env="OPENAI_API_KEY",
            base_url=base_url,
            model_name=model_name,
            **kwargs,
        )

    def _call_api(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        调用 OpenAI API 获取嵌入。
        """
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key, base_url=self.base_url)

            response = client.embeddings.create(
                model=self.model_name,
                input=texts,
            )

            return [item.embedding for item in response.data]
        except ImportError:
            raise ImportError(
                "使用 OpenAIEmbeddingModel 需要安装 openai 包: pip install openai"
            )
        except Exception as e:
            raise RuntimeError(f"调用 OpenAI API 时出错: {e}")
