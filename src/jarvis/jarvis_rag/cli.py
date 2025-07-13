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
from rich.markdown import Markdown

from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.output import PrettyOutput, OutputType


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
        PrettyOutput.print(
            f"Using custom LLM: Platform='{platform.platform_name()}', Model='{platform.name()}'",
            OutputType.SUCCESS,
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
            PrettyOutput.print(
                f"Error: Platform '{platform_name}' not found.", OutputType.ERROR
            )
            return None
        platform_instance.set_model_name(model_name)
        platform_instance.set_suppress_output(True)
        return _CustomPlatformLLM(platform_instance)
    except Exception as e:
        PrettyOutput.print(f"Error creating custom LLM: {e}", OutputType.ERROR)
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
                PrettyOutput.print(f"Scanning directory: {path}", OutputType.INFO)
                for item in path.rglob("*"):
                    if item.is_file() and is_likely_text_file(item):
                        files_to_process.add(item)
            elif path.is_file():
                if is_likely_text_file(path):
                    files_to_process.add(path)
                else:
                    PrettyOutput.print(
                        f"Skipping likely binary file: {path}", OutputType.WARNING
                    )

    if not files_to_process:
        PrettyOutput.print(
            f"No text files found in the specified paths.", OutputType.WARNING
        )
        return

    PrettyOutput.print(
        f"Found {len(files_to_process)} unique file(s) to process.",
        OutputType.SUCCESS,
    )

    try:
        pipeline = JarvisRAGPipeline(
            embedding_mode=cast(
                Optional[Literal["performance", "accuracy"]], embedding_mode
            ),
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        docs: List[Document] = []
        for file_path in sorted(list(files_to_process)):
            try:
                if file_path.suffix.lower() == ".md":
                    loader = UnstructuredMarkdownLoader(str(file_path))
                else:  # Default to TextLoader for .txt and all code files
                    loader = TextLoader(str(file_path), encoding="utf-8")

                docs.extend(loader.load())
                PrettyOutput.print(f"Loaded: {file_path}", OutputType.INFO)
            except Exception as e:
                PrettyOutput.print(
                    f"Failed to load {file_path}: {e}", OutputType.WARNING
                )

        if not docs:
            PrettyOutput.print(
                "No documents were successfully loaded.", OutputType.ERROR
            )
            raise typer.Exit(code=1)

        pipeline.add_documents(docs)
        PrettyOutput.print(
            f"Successfully added content from {len(docs)} document(s) to the collection '{collection_name}'.",
            OutputType.SUCCESS,
        )

    except Exception as e:
        PrettyOutput.print(
            f"A critical error occurred: {e}", OutputType.ERROR, traceback=True
        )
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
        PrettyOutput.print(
            "Error: --model requires --platform to be specified.", OutputType.ERROR
        )
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

        PrettyOutput.print(f"Querying with: '{question}'", OutputType.INFO)
        answer = pipeline.query(question)

        PrettyOutput.print("Answer:", OutputType.RESULT)
        # We can still use rich.markdown.Markdown as PrettyOutput uses rich underneath
        from jarvis.jarvis_utils.globals import console

        console.print(Markdown(answer))

    except Exception as e:
        PrettyOutput.print(f"An error occurred: {e}", OutputType.ERROR, traceback=True)
        raise typer.Exit(code=1)


def main():
    init_env(welcome_str="Jarvis RAG")
    app()
