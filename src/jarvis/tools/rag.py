from typing import Dict, Any, List
import chromadb
from chromadb.utils import embedding_functions
import hashlib
import re
from ..utils import PrettyOutput, OutputType

class RAGTool:
    name = "rag_query"
    description = """Execute RAG queries on documents.
    Features:
    1. Auto-creates document embeddings
    2. Returns relevant passages
    3. Maintains embedding database
    """
    parameters = {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files to process"
            },
            "query": {
                "type": "string",
                "description": "Query text"
            },
            "num_passages": {
                "type": "integer",
                "description": "Number of passages",
                "default": 3
            },
            "chunk_size": {
                "type": "integer",
                "description": "Chunk size",
                "default": 500
            }
        },
        "required": ["files", "query"]
    }

    def _get_document_hash(self, content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest()

    def _chunk_text(self, text: str, chunk_size: int = 500) -> List[str]:
        """将文本分割成适当大小的块"""
        # 按句子分割
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            if current_length + sentence_length > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(sentence)
            current_length += sentence_length
            
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        return chunks

    def execute(self, args: Dict) -> Dict[str, Any]:
        """执行RAG查询"""
        try:
            files = args["files"]
            query = args["query"]
            num_passages = args.get("num_passages", 3)
            chunk_size = args.get("chunk_size", 500)
            
            # 初始化ChromaDB
            chroma_client = chromadb.PersistentClient(path="./data/chromadb")
            
            # 使用sentence-transformers作为嵌入模型
            embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            
            # 获取或创建集合
            collection = chroma_client.get_or_create_collection(
                name="document_store",
                embedding_function=embedding_function
            )
            
            # 处理每个文件
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 计算文档哈希值
                    doc_hash = self._get_document_hash(content)
                    
                    # 检查文档是否已经存在且未更改
                    existing_ids = collection.get(
                        where={"doc_hash": doc_hash}
                    )
                    
                    if not existing_ids["ids"]:
                        # 分块处理文档
                        chunks = self._chunk_text(content, chunk_size)
                        
                        # 为每个块生成唯一ID
                        chunk_ids = [f"{doc_hash}_{i}" for i in range(len(chunks))]
                        
                        # 添加到数据库
                        collection.add(
                            documents=chunks,
                            ids=chunk_ids,
                            metadatas=[{
                                "file_path": file_path,
                                "doc_hash": doc_hash,
                                "chunk_index": i
                            } for i in range(len(chunks))]
                        )
                        
                        PrettyOutput.print(f"已添加文档: {file_path}", OutputType.INFO)
                    else:
                        PrettyOutput.print(f"文档已存在且未更改: {file_path}", OutputType.INFO)
                        
                except Exception as e:
                    PrettyOutput.print(f"处理文件 {file_path} 时出错: {str(e)}", OutputType.ERROR)
            
            # 执行查询
            results = collection.query(
                query_texts=[query],
                n_results=num_passages
            )
            
            # 格式化输出
            output = [f"查询: {query}\n"]
            output.append(f"找到 {len(results['documents'][0])} 个相关段落:\n")
            
            for i, (doc, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0]), 1):
                output.append(f"\n段落 {i}:")
                output.append(f"来源: {metadata['file_path']}")
                output.append(f"相关内容:\n{doc}\n")
                output.append("-" * 50)
            
            return {
                "success": True,
                "stdout": "\n".join(output),
                "stderr": ""
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"RAG查询失败: {str(e)}"
            } 