import os
import sys
from pathlib import Path
from typing import Optional, List, Literal, cast, Tuple
import mimetypes

import pathspec  # type: ignore
import typer
from langchain.docstore.document import Document
from langchain_community.document_loaders import (
    TextLoader,
    UnstructuredMarkdownLoader,
)
from langchain_core.document_loaders.base import BaseLoader
from rich.markdown import Markdown

from jarvis.jarvis_utils.utils import init_env
from jarvis.jarvis_utils.config import (
    get_rag_embedding_model,
    get_rag_use_bm25,
    get_rag_use_rerank,
)


def is_likely_text_file(file_path: Path) -> bool:
    """
    通过读取文件开头部分，检查文件是否可能为文本文件。
    此方法可以避免将大型二进制文件加载到内存中。
    """
    try:
        # 启发式方法1：检查MIME类型（如果可用）
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and mime_type.startswith("text/"):
            return True
        if mime_type and any(x in mime_type for x in ["json", "xml", "javascript"]):
            return True

        # 启发式方法2：检查文件的前几KB中是否包含空字节
        with open(file_path, "rb") as f:
            chunk = f.read(4096)  # 读取前4KB
            if b"\x00" in chunk:
                return False  # 空字节是二进制文件的强指示符
        return True
    except Exception:
        return False


# 确保项目根目录在Python路径中，以允许绝对导入
# 这使得脚本可以作为模块运行。
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
    help="一个与Jarvis RAG框架交互的命令行工具。",
    add_completion=False,
)


class _CustomPlatformLLM(LLMInterface):
    """一个简单的包装器，使BasePlatform实例与LLMInterface兼容。"""

    def __init__(self, platform: BasePlatform):
        self.platform = platform
        print(f"✅ 使用自定义LLM: 平台='{platform.platform_name()}', 模型='{platform.name()}'")

    def generate(self, prompt: str, **kwargs) -> str:
        return self.platform.chat_until_success(prompt)


def _create_custom_llm(platform_name: str, model_name: str) -> Optional[LLMInterface]:
    """从指定的平台和模型创建LLM接口。"""
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


def _load_ragignore_spec() -> Tuple[Optional[pathspec.PathSpec], Optional[Path]]:
    """
    从项目根目录加载忽略模式。
    首先查找 `.jarvis/rag/.ragignore`，如果未找到，则回退到 `.gitignore`。
    """
    project_root_path = Path(_project_root)
    ragignore_file = project_root_path / ".jarvis" / "rag" / ".ragignore"
    gitignore_file = project_root_path / ".gitignore"

    ignore_file_to_use = None
    if ragignore_file.is_file():
        ignore_file_to_use = ragignore_file
    elif gitignore_file.is_file():
        ignore_file_to_use = gitignore_file

    if ignore_file_to_use:
        try:
            with open(ignore_file_to_use, "r", encoding="utf-8") as f:
                patterns = f.read().splitlines()
            spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
            print(f"✅ 加载忽略规则: {ignore_file_to_use}")
            return spec, project_root_path
        except Exception as e:
            print(f"⚠️ 加载 {ignore_file_to_use.name} 文件失败: {e}")

    return None, None


@app.command(
    "add",
    help="从文件、目录或glob模式（例如 'src/**/*.py'）添加文档。",
)
def add_documents(
    paths: List[Path] = typer.Argument(
        ...,
        help="文件/目录路径或glob模式。支持Shell扩展。",
    ),
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="向量数据库中集合的名称。",
    ),
    embedding_model: Optional[str] = typer.Option(
        None,
        "--embedding-model",
        "-e",
        help="嵌入模型的名称。覆盖全局配置。",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="向量数据库的路径。覆盖全局配置。"),
    batch_size: int = typer.Option(
        500,
        "--batch-size",
        "-b",
        help="单个批次中要处理的文档数。",
    ),
):
    """从不同来源向RAG知识库添加文档。"""
    files_to_process = set()

    for path_str in paths:
        # Typer的List[Path]可能不会扩展glob，所以我们手动处理
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
        print("⚠️ 在指定路径中未找到任何文本文件。")
        return

    # 使用 .ragignore 过滤文件
    ragignore_spec, ragignore_root = _load_ragignore_spec()
    if ragignore_spec and ragignore_root:
        initial_count = len(files_to_process)
        retained_files = set()
        for file_path in files_to_process:
            try:
                # 将文件路径解析为绝对路径以确保正确比较
                resolved_path = file_path.resolve()
                relative_path = str(resolved_path.relative_to(ragignore_root))
                if not ragignore_spec.match_file(relative_path):
                    retained_files.add(file_path)
            except ValueError:
                # 文件不在项目根目录下，保留它
                retained_files.add(file_path)

        ignored_count = initial_count - len(retained_files)
        if ignored_count > 0:
            print(f"ℹ️ 根据 .ragignore 规则过滤掉 {ignored_count} 个文件。")
        files_to_process = retained_files

    if not files_to_process:
        print("⚠️ 所有找到的文本文件都被忽略规则过滤掉了。")
        return

    print(f"✅ 发现 {len(files_to_process)} 个独立文件待处理。")

    try:
        pipeline = JarvisRAGPipeline(
            embedding_model=embedding_model,
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        docs_batch: List[Document] = []
        total_docs_added = 0
        loader: BaseLoader

        sorted_files = sorted(list(files_to_process))
        total_files = len(sorted_files)

        for i, file_path in enumerate(sorted_files):
            try:
                if file_path.suffix.lower() == ".md":
                    loader = UnstructuredMarkdownLoader(str(file_path))
                else:  # 对.txt和所有代码文件默认使用TextLoader
                    loader = TextLoader(str(file_path), encoding="utf-8")

                docs_batch.extend(loader.load())
                print(f"✅ 已加载: {file_path} (文件 {i + 1}/{total_files})")
            except Exception as e:
                print(f"⚠️ 加载失败 {file_path}: {e}")

            # 当批处理已满或是最后一个文件时处理批处理
            if docs_batch and (len(docs_batch) >= batch_size or (i + 1) == total_files):
                print(f"⚙️ 正在处理批次，包含 {len(docs_batch)} 个文档...")
                pipeline.add_documents(docs_batch)
                total_docs_added += len(docs_batch)
                print(f"✅ 成功添加 {len(docs_batch)} 个文档。")
                docs_batch = []  # 清空批处理

        if total_docs_added == 0:
            print("❌ 未能成功加载任何文档。")
            raise typer.Exit(code=1)

        print(f"✅ 成功将 {total_docs_added} 个文档的内容添加至集合 '{collection_name}'。")

    except Exception as e:
        print(f"❌ 发生严重错误: {e}")
        raise typer.Exit(code=1)


@app.command("list-docs", help="列出知识库中所有唯一的文档。")
def list_documents(
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="向量数据库中集合的名称。",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="向量数据库的路径。覆盖全局配置。"),
):
    """列出指定集合中的所有唯一文档。"""
    try:
        pipeline = JarvisRAGPipeline(
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
        )

        collection = pipeline._get_collection()
        results = collection.get()  # 获取集合中的所有项目

        if not results or not results["metadatas"]:
            print("ℹ️ 知识库中没有找到任何文档。")
            return

        # 从元数据中提取唯一的源文件路径
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


@app.command("retrieve", help="仅从知识库检索相关文档，不生成答案。")
def retrieve(
    question: str = typer.Argument(..., help="要提出的问题。"),
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="向量数据库中集合的名称。",
    ),
    embedding_model: Optional[str] = typer.Option(
        None,
        "--embedding-model",
        "-e",
        help="嵌入模型的名称。覆盖全局配置。",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="向量数据库的路径。覆盖全局配置。"),
    n_results: int = typer.Option(5, "--top-n", help="要检索的文档数量。"),
):
    """仅从RAG知识库检索文档并打印结果。"""
    try:
        # 如果未在命令行中指定，则从配置中加载RAG设置
        final_embedding_model = embedding_model or get_rag_embedding_model()
        use_bm25 = get_rag_use_bm25()
        use_rerank = get_rag_use_rerank()

        pipeline = JarvisRAGPipeline(
            embedding_model=final_embedding_model,
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
            use_bm25=use_bm25,
            use_rerank=use_rerank,
        )

        print(f"🤔 正在为问题检索文档: '{question}'")
        retrieved_docs = pipeline.retrieve_only(question, n_results=n_results)

        if not retrieved_docs:
            print("ℹ️ 未找到相关文档。")
            return

        print(f"✅ 成功检索到 {len(retrieved_docs)} 个文档:")
        from jarvis.jarvis_utils.globals import console

        for i, doc in enumerate(retrieved_docs, 1):
            source = doc.metadata.get("source", "未知来源")
            content = doc.page_content
            panel_title = f"文档 {i} | 来源: {source}"
            console.print(
                f"\n[bold magenta]{panel_title}[/bold magenta]"
            )
            console.print(Markdown(f"```\n{content}\n```"))

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        raise typer.Exit(code=1)


@app.command("query", help="向知识库提问。")
def query(
    question: str = typer.Argument(..., help="要提出的问题。"),
    collection_name: str = typer.Option(
        "jarvis_rag_collection",
        "--collection",
        "-c",
        help="向量数据库中集合的名称。",
    ),
    embedding_model: Optional[str] = typer.Option(
        None,
        "--embedding-model",
        "-e",
        help="嵌入模型的名称。覆盖全局配置。",
    ),
    db_path: Optional[Path] = typer.Option(None, "--db-path", help="向量数据库的路径。覆盖全局配置。"),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        "-p",
        help="为LLM指定平台名称。覆盖默认的思考模型。",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="为LLM指定模型名称。需要 --platform。",
    ),
):
    """查询RAG知识库并打印答案。"""
    if model and not platform:
        print("❌ 错误: --model 需要指定 --platform。")
        raise typer.Exit(code=1)

    try:
        custom_llm = _create_custom_llm(platform, model) if platform and model else None
        if (platform or model) and not custom_llm:
            raise typer.Exit(code=1)

        # 如果未在命令行中指定，则从配置中加载RAG设置
        final_embedding_model = embedding_model or get_rag_embedding_model()
        use_bm25 = get_rag_use_bm25()
        use_rerank = get_rag_use_rerank()

        pipeline = JarvisRAGPipeline(
            llm=custom_llm,
            embedding_model=final_embedding_model,
            db_path=str(db_path) if db_path else None,
            collection_name=collection_name,
            use_bm25=use_bm25,
            use_rerank=use_rerank,
        )

        print(f"🤔 正在查询: '{question}'")
        answer = pipeline.query(question)

        print("💬 答案:")
        # 我们仍然可以使用 rich.markdown.Markdown，因为 PrettyOutput 底层使用了 rich
        from jarvis.jarvis_utils.globals import console

        console.print(Markdown(answer))

    except Exception as e:
        print(f"❌ 发生错误: {e}")
        raise typer.Exit(code=1)


_RAG_INSTALLED = False
try:
    import langchain  # noqa

    _RAG_INSTALLED = True
except ImportError:
    pass


def _check_rag_dependencies():
    if not _RAG_INSTALLED:
        print("❌ RAG依赖项未安装。" "请运行 'pip install \"jarvis-ai-assistant[rag]\"' 来使用此命令。")
        raise typer.Exit(code=1)


def main():
    _check_rag_dependencies()
    init_env(welcome_str="Jarvis RAG")
    app()
