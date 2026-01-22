"""
EdgeFn 重排模型实现。
"""

from typing import List
from typing import Optional

from .base import OnlineReranker


class EdgeFnReranker(OnlineReranker):
    """
    EdgeFn 重排模型的实现。

    使用 EdgeFn 的 rerank API。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "bge-reranker-v2-m3",
        base_url: str = "https://api.edgefn.net/v1/rerank",
        **kwargs,
    ):
        """
        初始化 EdgeFn 重排模型。

        参数:
            api_key: EdgeFn API密钥。如果为None，将从EDGEFN_API_KEY环境变量读取。
            model_name: 要使用的模型名称（如 'bge-reranker-v2-m3'）。
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

    def _call_api(self, query: str, documents: List[str]) -> List[tuple[int, float]]:
        """
        调用 EdgeFn API 获取重排分数。

        参数:
            query: 查询文本。
            documents: 文档文本列表。

        返回:
            包含 (索引, 分数) 元组的列表，按分数降序排序。
        """
        try:
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
                self.base_url, json=payload, headers=headers, timeout=60
            )
            response.raise_for_status()

            data = response.json()

            # EdgeFn API 返回格式可能是多种形式，需要处理不同的格式
            # 可能的格式:
            # 1. {"results": [{"index": 0, "score": 0.95}, ...]}
            # 2. {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
            # 3. {"data": [{"index": 0, "score": 0.95}, ...]}
            # 4. 直接返回列表: [{"index": 0, "score": 0.95}, ...]

            results = []
            if "results" in data:
                # 格式1和2: 使用 results 字段
                for item in data["results"]:
                    index = item.get("index", item.get("rank", 0))
                    # 尝试不同的分数字段名
                    score = item.get(
                        "score",
                        item.get("relevance_score", item.get("relevance", 0.0)),
                    )
                    results.append((index, float(score)))
            elif "data" in data:
                # 格式3: 使用 data 字段
                for item in data["data"]:
                    index = item.get("index", item.get("rank", 0))
                    score = item.get(
                        "score",
                        item.get("relevance_score", item.get("relevance", 0.0)),
                    )
                    results.append((index, float(score)))
            elif isinstance(data, list):
                # 格式4: 直接是列表
                for item in data:
                    if isinstance(item, dict):
                        index = item.get("index", item.get("rank", 0))
                        score = item.get(
                            "score",
                            item.get("relevance_score", item.get("relevance", 0.0)),
                        )
                        if score is None:
                            score = 0.0
                        results.append((index, float(score)))
                    elif isinstance(item, (int, float)):
                        # 如果直接是分数列表，使用索引作为位置
                        results.append((len(results), float(item)))
            else:
                raise ValueError(
                    f"EdgeFn API 返回了意外的格式。响应键: {list(data.keys()) if isinstance(data, dict) else '非字典类型'}"
                )

            # 按分数降序排序
            results.sort(key=lambda x: x[1], reverse=True)

            return results

        except ImportError:
            raise ImportError(
                "使用 EdgeFnReranker 需要安装 requests 包: pip install requests"
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
