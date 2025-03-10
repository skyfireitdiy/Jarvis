import os
import yaml
import numpy as np
import faiss
from typing import Dict, Any
from ..jarvis_utils.output import PrettyOutput, OutputType
from ..jarvis_utils.embedding import load_embedding_model
from ..jarvis_utils.config import dont_use_local_model
def _create_methodology_embedding(embedding_model: Any, methodology_text: str) -> np.ndarray:
    """Create embedding vector for methodology text"""
    try:
        # Truncate long text
        max_length = 512
        text = ' '.join(methodology_text.split()[:max_length])
        
        # 使用sentence_transformers模型获取嵌入向量
        embedding = embedding_model.encode([text], 
                                          convert_to_tensor=True,
                                          normalize_embeddings=True)
        vector = np.array(embedding.cpu().numpy(), dtype=np.float32)
        return vector[0]  # Return first vector, because we only encoded one text
    except Exception as e:
        PrettyOutput.print(f"创建方法论嵌入向量失败: {str(e)}", OutputType.ERROR)
        return np.zeros(1536, dtype=np.float32)
def load_methodology(user_input: str) -> str:
    """Load methodology and build vector index"""
    PrettyOutput.print("加载方法论...", OutputType.PROGRESS)
    user_jarvis_methodology = os.path.expanduser("~/.jarvis/methodology")
    if not os.path.exists(user_jarvis_methodology):
        return ""
    
    def make_methodology_prompt(data: Dict) -> str:
        ret = """This is the standard methodology for handling previous problems, if the current task is similar, you can refer to it, if not,just ignore it:\n""" 
        for key, value in data.items():
            ret += f"Problem: {key}\nMethodology: {value}\n"
        return ret
    
    try:
        with open(user_jarvis_methodology, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if dont_use_local_model():
            return make_methodology_prompt(data)
        # Reset data structure
        methodology_data = []
        vectors = []
        ids = []
        # Get embedding model
        embedding_model = load_embedding_model()
        
        # Create test embedding to get correct dimension
        test_embedding = _create_methodology_embedding(embedding_model, "test")
        embedding_dimension = len(test_embedding)
        # Create embedding vector for each methodology
        for i, (key, value) in enumerate(data.items()):
            methodology_text = f"{key}\n{value}"
            embedding = _create_methodology_embedding(embedding_model, methodology_text)
            vectors.append(embedding)
            ids.append(i)
            methodology_data.append({"key": key, "value": value})
        if vectors:
            vectors_array = np.vstack(vectors)
            # Use correct dimension from test embedding
            hnsw_index = faiss.IndexHNSWFlat(embedding_dimension, 16)
            hnsw_index.hnsw.efConstruction = 40
            hnsw_index.hnsw.efSearch = 16
            methodology_index = faiss.IndexIDMap(hnsw_index)
            methodology_index.add_with_ids(vectors_array, np.array(ids)) # type: ignore
            query_embedding = _create_methodology_embedding(embedding_model, user_input)
            k = min(3, len(methodology_data))
            PrettyOutput.print(f"检索方法论...", OutputType.INFO)
            distances, indices = methodology_index.search(
                query_embedding.reshape(1, -1), k
            ) # type: ignore
            relevant_methodologies = {}
            output_lines = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx >= 0:
                    similarity = 1.0 / (1.0 + float(dist))
                    methodology = methodology_data[idx]
                    output_lines.append(
                        f"Methodology '{methodology['key']}' similarity: {similarity:.3f}"
                    )
                    if similarity >= 0.5:
                        relevant_methodologies[methodology["key"]] = methodology["value"]
            
            if output_lines:
                PrettyOutput.print("\n".join(output_lines), OutputType.INFO)
                    
            if relevant_methodologies:
                return make_methodology_prompt(relevant_methodologies)
        return make_methodology_prompt(data)
    except Exception as e:
        PrettyOutput.print(f"加载方法论失败: {str(e)}", OutputType.ERROR)
        return ""