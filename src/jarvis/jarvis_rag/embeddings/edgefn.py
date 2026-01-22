"""
EdgeFn 嵌入模型实现。
"""

from typing import List
from typing import Optional

from .base import OnlineEmbeddingModel


class EdgeFnEmbeddingModel(OnlineEmbeddingModel):
    """
    EdgeFn 嵌入模型的实现。

    使用 EdgeFn 的 embeddings API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "BAAI/bge-m3",
        base_url: str = "https://api.edgefn.net/v1/embeddings",
        **kwargs,
    ):
        """
        初始化 EdgeFn 嵌入模型。

        参数:
            api_key: EdgeFn API密钥。如果为None，将从EDGEFN_API_KEY环境变量读取。
            model_name: 要使用的模型名称（如 'BAAI/bge-m3'）。
            base_url: API的基础URL。
            **kwargs: 传递给父类的其他参数。
        """
        super().__init__(
            api_key=api_key,
            api_key_env="EDGEFN_API_KEY",
            base_url=base_url,
            model_name=model_name,
            **kwargs,
        )

    def _call_api(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        调用 EdgeFn API 获取嵌入。

        参数:
            texts: 要嵌入的文本列表。
            is_query: 是否为查询（EdgeFn API 不区分查询和文档）。

        返回:
            嵌入向量列表。
        """
        try:
            import requests

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            # EdgeFn API 支持批量处理
            # 如果只有一个文本，可以发送字符串；多个文本发送列表
            payload = {
                "model": self.model_name,
                "input": texts[0] if len(texts) == 1 else texts,
            }

            response = requests.post(
                self.base_url, headers=headers, json=payload, timeout=60
            )
            response.raise_for_status()

            data = response.json()

            # EdgeFn API 返回格式通常是: {"data": [{"embedding": [...]}, ...]}
            # 处理不同的返回格式
            if "data" in data:
                # 标准格式：data 是列表，每个元素包含 embedding
                if isinstance(data["data"], list) and len(data["data"]) > 0:
                    if (
                        isinstance(data["data"][0], dict)
                        and "embedding" in data["data"][0]
                    ):
                        # 格式: {"data": [{"embedding": [...]}, ...]}
                        embeddings = [item["embedding"] for item in data["data"]]
                    else:
                        # 格式: {"data": [[...], [...]]} - 直接是嵌入向量列表
                        embeddings = data["data"]
                    return embeddings
                else:
                    raise ValueError("EdgeFn API 返回的 data 格式不正确")
            elif "embedding" in data:
                # 单个嵌入的情况（非标准格式）
                return [data["embedding"]]
            else:
                # 尝试直接返回（如果 API 直接返回嵌入列表）
                if isinstance(data, list):
                    return data
                raise ValueError(
                    f"EdgeFn API 返回了意外的格式。响应键: {list(data.keys()) if isinstance(data, dict) else '非字典类型'}"
                )

        except ImportError:
            raise ImportError(
                "使用 EdgeFnEmbeddingModel 需要安装 requests 包: pip install requests"
            )
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    error_msg = f"{error_msg} - 详情: {error_detail}"
                except Exception:
                    error_msg = f"{error_msg} - 响应状态码: {e.response.status_code}"
            raise RuntimeError(f"调用 EdgeFn API 时出错: {error_msg}")
        except Exception as e:
            raise RuntimeError(f"处理 EdgeFn API 响应时出错: {e}")
