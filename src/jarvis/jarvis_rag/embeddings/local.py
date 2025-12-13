"""
本地嵌入模型实现。
"""

from jarvis.jarvis_utils.output import PrettyOutput

import os
from typing import List
from typing import Optional
from typing import cast

import torch
from huggingface_hub import snapshot_download
from langchain_huggingface import HuggingFaceEmbeddings

from ..cache import EmbeddingCache
from ..embedding_interface import EmbeddingInterface


class LocalEmbeddingModel(EmbeddingInterface):
    """
    管理本地嵌入模型的加载和使用，并带有缓存功能。

    该类负责从Hugging Face加载指定的模型，并使用基于磁盘的缓存
    来避免为相同文本重新计算嵌入。

    这是 EmbeddingInterface 的本地实现，使用 HuggingFace 模型。
    """

    def __init__(
        self, model_name: str, cache_dir: str, max_length: Optional[int] = None
    ):
        """
        初始化LocalEmbeddingModel。

        参数:
            model_name: 要加载的Hugging Face模型的名称。
            cache_dir: 用于存储嵌入缓存的目录。
            max_length: 模型的最大输入长度（token数），用于文档分割。
        """
        self.model_name = model_name
        self.max_length = max_length

        PrettyOutput.auto_print(f"ℹ️ 初始化嵌入管理器, 模型: '{self.model_name}'...")

        # 缓存的salt是模型名称，以防止冲突
        self.cache = EmbeddingCache(cache_dir=cache_dir, salt=self.model_name)
        self.model = self._load_model()

    def _load_model(self) -> HuggingFaceEmbeddings:
        """根据配置加载Hugging Face嵌入模型。"""
        model_kwargs = {"device": "cuda" if torch.cuda.is_available() else "cpu"}
        encode_kwargs = {"normalize_embeddings": True}

        try:
            # First try to load model from local cache without any network access
            try:
                local_dir = None
                # Prefer explicit local dir via env or direct path

                if os.path.isdir(self.model_name):
                    return HuggingFaceEmbeddings(
                        model_name=self.model_name,
                        model_kwargs=model_kwargs,
                        encode_kwargs=encode_kwargs,
                        show_progress=False,
                    )

                # Try common local cache directories for sentence-transformers and HF hub
                try:
                    home = os.path.expanduser("~")
                    st_home = os.path.join(home, ".cache", "sentence_transformers")
                    torch_st_home = os.path.join(
                        home, ".cache", "torch", "sentence_transformers"
                    )
                    # Build common name variants found in local caches
                    org, name = (
                        self.model_name.split("/", 1)
                        if "/" in self.model_name
                        else ("", self.model_name)
                    )
                    san1 = self.model_name.replace("/", "_")
                    san2 = self.model_name.replace("/", "__")
                    san3 = self.model_name.replace("/", "--")
                    # include plain 'name' for caches that drop org prefix
                    name_variants = list(
                        dict.fromkeys([self.model_name, san1, san2, san3, name])
                    )
                    candidates = []
                    for base in [st_home, torch_st_home]:
                        for nv in name_variants:
                            p = os.path.join(base, nv)
                            if os.path.isdir(p):
                                candidates.append(p)
                        # Fuzzy scan cache directory for entries that include variants
                        try:
                            for entry in os.listdir(base):
                                ep = os.path.join(base, entry)
                                if not os.path.isdir(ep):
                                    continue
                                if (
                                    (
                                        org
                                        and entry.startswith(f"{org}__")
                                        and name in entry
                                    )
                                    or (san1 in entry)
                                    or (name in entry)
                                ):
                                    candidates.append(ep)
                        except Exception:
                            pass

                    # Hugging Face Hub cache snapshots
                    hf_cache = os.path.join(home, ".cache", "huggingface", "hub")
                    if "/" in self.model_name:
                        org, name = self.model_name.split("/", 1)
                        models_dir = os.path.join(
                            hf_cache, f"models--{org}--{name}", "snapshots"
                        )
                        if os.path.isdir(models_dir):
                            try:
                                snaps = sorted(
                                    [
                                        os.path.join(models_dir, d)
                                        for d in os.listdir(models_dir)
                                    ],
                                    key=lambda p: os.path.getmtime(p),
                                    reverse=True,
                                )
                            except Exception:
                                snaps = [
                                    os.path.join(models_dir, d)
                                    for d in os.listdir(models_dir)
                                ]
                            for sp in snaps:
                                if os.path.isdir(sp):
                                    candidates.append(sp)
                                    break

                    for cand in candidates:
                        try:
                            return HuggingFaceEmbeddings(
                                model_name=cand,
                                model_kwargs=model_kwargs,
                                encode_kwargs=encode_kwargs,
                                show_progress=False,
                            )
                        except Exception:
                            continue
                except Exception:
                    pass

                try:
                    # Try resolve local cached directory; do not hit network
                    local_dir = snapshot_download(
                        repo_id=self.model_name, local_files_only=True
                    )
                except Exception:
                    local_dir = None

                if local_dir:
                    return HuggingFaceEmbeddings(
                        model_name=local_dir,
                        model_kwargs=model_kwargs,
                        encode_kwargs=encode_kwargs,
                        show_progress=False,
                    )

                # Fall back to remote download if local cache not found and not offline
                return HuggingFaceEmbeddings(
                    model_name=self.model_name,
                    model_kwargs=model_kwargs,
                    encode_kwargs=encode_kwargs,
                    show_progress=True,
                )
            except Exception as _e:
                # 如果已检测到本地候选路径（直接目录 / 本地缓存快照），则视为本地加载失败，
                # 为避免在用户期望"本地优先不联网"的情况下触发联网，直接抛错并给出修复建议。
                had_local_candidate = False
                try:
                    had_local_candidate = (
                        os.path.isdir(self.model_name)
                        # 如果上面 snapshot_download 命中了本地缓存，会将 local_dir 设为非 None
                        or (locals().get("local_dir") is not None)
                    )
                except Exception:
                    pass

                if had_local_candidate:
                    PrettyOutput.auto_print(
                        "❌ 检测到本地模型路径但加载失败。为避免触发网络访问，已中止远程回退。\n"
                        "请确认本地目录包含完整的 Transformers/Tokenizer 文件（如 config.json、model.safetensors、tokenizer.json/merges.txt 等），\n"
                        "或在配置中将 embedding_model 设置为该本地目录，或将模型放置到默认的 Hugging Face 缓存目录（例如 ~/.cache/huggingface/hub）。"
                    )
                    raise

                # 未发现任何本地候选，则保持原有行为：回退至远程下载
                return HuggingFaceEmbeddings(
                    model_name=self.model_name,
                    model_kwargs=model_kwargs,
                    encode_kwargs=encode_kwargs,
                    show_progress=True,
                )
        except Exception as e:
            PrettyOutput.auto_print(f"❌ 加载嵌入模型 '{self.model_name}' 时出错: {e}")
            PrettyOutput.auto_print(
                "⚠️ 请确保您已安装 'sentence_transformers' 和 'torch'。"
            )
            raise

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        使用缓存为文档列表计算嵌入。

        参数:
            texts: 要嵌入的文档（字符串）列表。

        返回:
            一个嵌入列表，每个文档对应一个嵌入。
        """
        if not texts:
            return []

        # 检查缓存中是否已存在嵌入
        cached_embeddings = self.cache.get_batch(texts)

        texts_to_embed = []
        indices_to_embed = []
        for i, (text, cached) in enumerate(zip(texts, cached_embeddings)):
            if cached is None:
                texts_to_embed.append(text)
                indices_to_embed.append(i)

        # 为不在缓存中的文本计算嵌入
        if texts_to_embed:
            PrettyOutput.auto_print(
                f"ℹ️ 缓存未命中。正在为 {len(texts_to_embed)}/{len(texts)} 个文档计算嵌入。"
            )
            new_embeddings = self.model.embed_documents(texts_to_embed)

            # 将新的嵌入存储在缓存中
            self.cache.set_batch(texts_to_embed, new_embeddings)

            # 将新的嵌入放回结果列表中
            for i, embedding in zip(indices_to_embed, new_embeddings):
                cached_embeddings[i] = embedding
        else:
            PrettyOutput.auto_print(
                f"✅ 缓存命中。所有 {len(texts)} 个文档的嵌入均从缓存中检索。"
            )

        return cast(List[List[float]], cached_embeddings)

    def embed_query(self, text: str) -> List[float]:
        """
        为单个查询计算嵌入。
        查询通常不被缓存，但如果需要可以添加。
        """
        return self.model.embed_query(text)
