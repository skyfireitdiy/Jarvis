import hashlib
from typing import Any
from typing import List
from typing import Optional

from diskcache import Cache


class EmbeddingCache:
    """
    一个用于存储和检索文本嵌入的基于磁盘的缓存。

    该类使用diskcache创建一个持久化的本地缓存。它根据每个文本内容的
    SHA256哈希值为其生成一个键，使得查找过程具有确定性和高效性。
    """

    def __init__(self, cache_dir: str, salt: str = ""):
        """
        初始化EmbeddingCache。

        参数:
            cache_dir (str): 缓存将要存储的目录。
            salt (str): 添加到哈希中的盐值。这对于确保由不同模型生成的
                        嵌入不会发生冲突至关重要。例如，可以使用模型名称作为盐值。
        """
        self.cache = Cache(cache_dir)
        self.salt = salt

    def _get_key(self, text: str) -> str:
        """为一个给定的文本和盐值生成一个唯一的缓存键。"""
        hash_object = hashlib.sha256((self.salt + text).encode("utf-8"))
        return hash_object.hexdigest()

    def get(self, text: str) -> Optional[Any]:
        """
        从缓存中检索一个嵌入。

        参数:
            text (str): 要查找的文本。

        返回:
            缓存的嵌入，如果不在缓存中则返回None。
        """
        key = self._get_key(text)
        return self.cache.get(key)

    def set(self, text: str, embedding: Any) -> None:
        """
        在缓存中存储一个嵌入。

        参数:
            text (str): 与嵌入相对应的文本。
            embedding (Any): 要存储的嵌入向量。
        """
        key = self._get_key(text)
        self.cache.set(key, embedding)

    def get_batch(self, texts: List[str]) -> List[Optional[Any]]:
        """
        从缓存中检索一批嵌入。

        参数:
            texts (List[str]): 要查找的文本列表。

        返回:
            一个列表，其中包含缓存的嵌入，对于缓存未命中的情况则为None。
        """
        return [self.get(text) for text in texts]

    def set_batch(self, texts: List[str], embeddings: List[Any]) -> None:
        """
        在缓存中存储一批嵌入。

        参数:
            texts (List[str]): 文本列表。
            embeddings (List[Any]): 相应的嵌入列表。
        """
        if len(texts) != len(embeddings):
            raise ValueError("Length of texts and embeddings must be the same.")

        with self.cache.transact():
            for text, embedding in zip(texts, embeddings):
                self.set(text, embedding)

    def close(self):
        """关闭缓存连接。"""
        self.cache.close()
