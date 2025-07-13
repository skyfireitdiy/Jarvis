from typing import List

import chromadb
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from .embedding_manager import EmbeddingManager


class ChromaRetriever:
    """
    A retriever class for managing documents in a ChromaDB vector store.

    This class handles document splitting, embedding, storage, and retrieval
    using a persistent ChromaDB client.
    """

    def __init__(
        self,
        embedding_manager: EmbeddingManager,
        db_path: str,
        collection_name: str = "jarvis_rag_collection",
    ):
        """
        Initializes the ChromaRetriever.

        Args:
            embedding_manager: An instance of EmbeddingManager for embedding documents.
            db_path: The file path for ChromaDB's persistent storage.
            collection_name: The name of the collection within ChromaDB.
        """
        self.embedding_manager = embedding_manager
        self.db_path = db_path
        self.collection_name = collection_name

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name
        )
        print(
            f"ChromaDB client initialized at '{db_path}' with collection '{collection_name}'."
        )

    def add_documents(
        self, documents: List[Document], chunk_size=1000, chunk_overlap=100
    ):
        """
        Splits, embeds, and adds a list of documents to the vector store.

        Args:
            documents: A list of LangChain Document objects.
            chunk_size: The size of each text chunk.
            chunk_overlap: The overlap between consecutive chunks.
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        chunks = text_splitter.split_documents(documents)

        print(f"Split {len(documents)} documents into {len(chunks)} chunks.")

        # Extract content and metadata
        chunk_texts = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]

        # Get embeddings, utilizing the cache in the embedding manager
        embeddings = self.embedding_manager.embed_documents(chunk_texts)

        # Generate unique IDs for each chunk
        ids = [
            f"doc_{i}"
            for i in range(
                self.collection.count(), self.collection.count() + len(chunks)
            )
        ]

        # Add to ChromaDB collection
        if chunk_texts:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=chunk_texts,
                metadatas=metadatas,
            )
            print(f"Successfully added {len(chunks)} chunks to the collection.")

    def retrieve(self, query: str, n_results: int = 5) -> List[Document]:
        """
        Retrieves the most relevant document chunks for a given query.

        Args:
            query: The user's query string.
            n_results: The number of top results to return.

        Returns:
            A list of LangChain Document objects representing the relevant chunks.
        """
        # Embed the query
        query_embedding = self.embedding_manager.embed_query(query)

        # Query the collection
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )

        # Format results into LangChain Document objects
        retrieved_docs = []
        if results and results["documents"]:
            for i, doc_text in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                retrieved_docs.append(
                    Document(page_content=doc_text, metadata=metadata)
                )

        return retrieved_docs
