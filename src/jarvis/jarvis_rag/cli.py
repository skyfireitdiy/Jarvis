import os
import sys
from pathlib import Path
from typing import Optional, List, Literal, cast
import mimetypes

import typer
from langchain.docstore.document import Document
from langchain_community.document_loaders import (
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.document_loaders.base import BaseLoader
from rich.markdown import Markdown

from jarvis.jarvis_utils.utils import init_env


def is_likely_text_file(file_path: Path) -> bool:
    """
    Checks if a file is likely to be a text file by reading its beginning.
    Avoids loading large binary files into memory.
    """
    try:
        # Heuristic 1: Check MIME type if available
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("text/"):
            return True
        if mime_type and any(x in mime_type for x in ["json", "xml", "javascript"]):
            return True

        # Heuristic 2: Check for null bytes in the first few KB
        with open(file_path, "rb") as f:
            chunk = f.read(4096)  # Read first 4KB
            if b"\x00" in chunk:
                return False  # Null bytes are a strong indicator of a binary file
        return True
    except Exception:
        return False


# Ensure the project root is in the Python path to allow absolute imports
# This makes the script runnable as a module.
_project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from jarvis.jarvis_platform.base import BasePlatform
from jarvis.jarvis_platform.registry import PlatformRegistry
from jarvis.jarvis_rag.llm_interface import LLMInterface
from jarvis.jarvis_rag.rag_pipeline import JarvisRAGPipeline

app = typer.Typer(
    name="jarvis-rag",
    help="A command-line tool to interact with the Jarvis RAG framework.",
    add_completion=False,
)


class _CustomPlatformLLM(LLMInterface):
    """A simple wrapper to make a BasePlatform instance compatible with LLMInterface."""

    def __init__(self, platform: BasePlatform):
        self.platform = platform
        print(
            f"✅ 使用自定义LLM: 平台='{platform.platform_name()}', 模型='{platform.name()}'"
        )

    def generate(self, prompt: str, **kwargs) -> str:
        return self.platform.chat_until_success(prompt)


def _create_custom_llm(platform_name: str, model_name: str) -> Optional[LLMInterface]:
    """Creates an LLM interface from a specific platform and model."""
    if not platform_name or not model_name:
        return None
    try:
        registry = PlatformRegistry.get_global_platform_registry()
        platform_instance = registry.create_platform(platform_name)
        if not platform_instance:
            print(f"❌ 错误: 平台 '{platform_name}' 未找到。")
            return None
        platform_instance.set_model_name(model_name)
        platform_instance.set_suppress_output(True)
        return _CustomPlatformLLM(platform_instance)
    except Exception as e:
        print(f"❌ 创建自定义LLM时出错: {e}")
        return None


@app.command(
    "add",
    help="Add documents from files, directories, or glob patterns (e.g., 'src/**/*.py').",
)
def add_documents(
    paths: List[Path] = typer.Argument(
        ...,
        help="File/directory paths or glob patterns. Shell expansion is supported.",
    ),
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="Name of the collection in the vector database.",
    ),
    embedding_mode: Optional[str] = typer.Option(
        None,
        "--embedding-mode",
        "-e",
        help="Embedding mode ('performance' or 'accuracy'). Overrides global config.",
    ),
    db_path: Optional[Path] = typer.Option(
        None, "--db-path", help="Path to the vector database. Overrides global config."
    ),
):
    """Adds documents to the RAG knowledge base from various sources."""
    files_to_process = set()

    for path_str in paths:
        # Typer with List[Path] might not expand globs, so we do it manually
        from glob import glob

        expanded_paths = glob(str(path_str), recursive=True)

        for p_str in expanded_paths:
            path = Path(p_str)
            if not path.exists():
                continue

            if path.is_dir():
                print(f"🔍 正在扫描目录: {path}")
                for item in path.rglob("*"):
                    if item.is_file() and is_likely_text_file(item):
                        files_to_process.add(item)
            elif path.is_file():
                if is_likely_text_file(path):
                    files_to_process.add(path)
                else:
                    print(f"⚠️ 跳过可能的二进制文件: {path}")

    if not files_to_process:
        print(f"⚠️ 在指定路径中未找到任何文本文件。")
        return

    print(f"✅ 发现 {len(files_to_process)} 个独立文件待处理。")

    try:
        pipeline = JarvisRAGPipeline(
            embedding_mode=cast(
                Optional[Literal["performance", "accuracy"]], embedding_mode
            ),
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        docs: List[Document] = []
        loader: BaseLoader
        for file_path in sorted(list(files_to_process)):
            try:
                if file_path.suffix.lower() == ".md":
                    loader = UnstructuredMarkdownLoader(str(file_path))
                else:  # Default to TextLoader for .txt and all code files
                    loader = TextLoader(str(file_path), encoding="utf-8")

                docs.extend(loader.load())
                print(f"✅ 已加载: {file_path}")
            except Exception as e:
                print(f"⚠️ 加载失败 {file_path}: {e}")

        if not docs:
            print("❌ 未能成功加载任何文档。")
            raise typer.Exit(code=1)

        pipeline.add_documents(docs)
        print(f"✅ 成功将 {len(docs)} 个文档的内容添加至集合 '{collection_name}'。")

    except Exception as e:
        print(f"❌ 发生严重错误: {e}")
        raise typer.Exit(code=1)


@app.command("list-docs", help="List all unique documents in the knowledge base.")
def list_documents(
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="Name of the collection in the vector database.",
    ),
    db_path: Optional[Path] = typer.Option(
        None, "--db-path", help="Path to the vector database. Overrides global config."
    ),
):
    """Lists all unique documents in the specified collection."""
    try:
        pipeline = JarvisRAGPipeline(
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        collection = pipeline.retriever.collection
        results = collection.get()  # Get all items in the collection

        if not results or not results["metadatas"]:
            print("ℹ️ 知识库中没有找到任何文档。")
            return

        # Extract unique source file paths from metadata
        sources = set()
        for metadata in results["metadatas"]:
            if metadata:
                source = metadata.get("source")
                if isinstance(source, str):
                    sources.add(source)

        if not sources:
            print("ℹ️ 知识库中没有找到任何带有源信息的文档。")
            return

        print(f"📚 知识库 '{collection_name}' 中共有 {len(sources)} 个独立文档:")
        for i, source in enumerate(sorted(list(sources)), 1):
            print(f"  {i}. {source}")

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        raise typer.Exit(code=1)


@app.command("query", help="Ask a question to the knowledge base.")
def query(
    question: str = typer.Argument(..., help="The question to ask."),
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="Name of the collection in the vector database.",
    ),
    embedding_mode: Optional[str] = typer.Option(
        None,
        "--embedding-mode",
        "-e",
        help="Embedding mode ('performance' or 'accuracy'). Overrides global config.",
    ),
    db_path: Optional[Path] = typer.Option(
        None, "--db-path", help="Path to the vector database. Overrides global config."
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        "-p",
        help="Specify a platform name for the LLM. Overrides the default thinking model.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Specify a model name for the LLM. Requires --platform.",
    ),
):
    """Queries the RAG knowledge base and prints the answer."""
    if model and not platform:
        print("❌ 错误: --model 需要指定 --platform。")
        raise typer.Exit(code=1)

    try:
        custom_llm = _create_custom_llm(platform, model) if platform and model else None
        if (platform or model) and not custom_llm:
            raise typer.Exit(code=1)

        pipeline = JarvisRAGPipeline(
            llm=custom_llm,
            embedding_mode=cast(
                Optional[Literal["performance", "accuracy"]], embedding_mode
            ),
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        print(f"🤔 正在查询: '{question}'")
        answer = pipeline.query(question)

        print("💬 答案:")
        # We can still use rich.markdown.Markdown as PrettyOutput uses rich underneath
        from jarvis.jarvis_utils.globals import console

        console.print(Markdown(answer))

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        raise typer.Exit(code=1)


def main():
    init_env(welcome_str="Jarvis RAG")
    app()
