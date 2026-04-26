"""文件忽略工具模块。

提供统一的文件/目录忽略逻辑，用于代码分析、依赖分析等场景。
"""

from pathlib import Path
from typing import Callable
from typing import List
from typing import Optional
from typing import Set


class FileIgnorePatterns:
    """文件忽略模式集合。

    定义了各种常见的需要忽略的文件和目录模式。
    """

    # 隐藏目录/文件（以 . 开头）
    HIDDEN_PATTERNS: Set[str] = {".git", ".svn", ".hg", ".bzr"}

    # 版本控制目录
    VCS_DIRS: Set[str] = {".git", ".svn", ".hg", ".bzr", ".gitignore"}

    # Python 相关
    PYTHON_DIRS: Set[str] = {
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".coverage",
        "htmlcov",
        ".hypothesis",
        ".ipynb_checkpoints",
        ".pyre",
        ".pytype",
        "develop-eggs",
        "downloads",
        "eggs",
        ".eggs",
        "lib",
        "lib64",
        "parts",
        "sdist",
        "var",
        "wheels",
        "pip-wheel-metadata",
        "share",
        "*.egg-info",
        ".installed.cfg",
        "MANIFEST",
    }
    PYTHON_VENV_DIRS: Set[str] = {"venv", "env", ".venv", "virtualenv", "ENV"}

    # Rust 相关
    RUST_DIRS: Set[str] = {"target", "Cargo.lock"}

    # Go 相关
    GO_DIRS: Set[str] = {"vendor", "bin", "coverage.out"}

    # Node.js 相关
    NODE_DIRS: Set[str] = {
        "node_modules",
        ".npm",
        ".yarn",
        ".pnpm",
        ".turbo",
        ".next",
        ".nuxt",
        "out",
        "dist",
        "coverage",
        "build",
    }

    # Java 相关
    JAVA_DIRS: Set[str] = {"target", ".gradle", "build", "out", "*.class"}

    # C/C++ 相关
    C_CPP_DIRS: Set[str] = {
        "build",
        "cmake-build-*",
        "out",
        "bin",
        "obj",
        "*.o",
        "*.a",
        "*.so",
        "*.obj",
        "*.dll",
        "*.dylib",
        "*.exe",
        "*.pdb",
    }

    # .NET 相关
    DOTNET_DIRS: Set[str] = {"bin", "obj", "packages"}

    # 构建产物目录（通用）
    BUILD_DIRS: Set[str] = {
        "build",
        "out",
        "target",
        "dist",
        "bin",
        "obj",
        "cmake-build-*",
    }

    # 依赖目录（通用）
    DEPENDENCY_DIRS: Set[str] = {
        "third_party",
        "vendor",
        "deps",
        "dependencies",
        "libs",
        "libraries",
        "external",
        "node_modules",
        "packages",
    }

    # 测试目录
    TEST_DIRS: Set[str] = {
        "test",
        "tests",
        "__tests__",
        "spec",
        "testsuite",
        "testdata",
        "test_data",
        "testdata",
        "fixtures",
        "mocks",
    }

    # 性能测试目录
    BENCHMARK_DIRS: Set[str] = {
        "benchmark",
        "benchmarks",
        "perf",
        "performance",
        "bench",
        "benches",
        "profiling",
        "profiler",
    }

    # 示例目录
    EXAMPLE_DIRS: Set[str] = {
        "example",
        "examples",
        "samples",
        "sample",
        "demo",
        "demos",
    }

    # 临时/缓存目录
    TEMP_DIRS: Set[str] = {
        "tmp",
        "temp",
        "cache",
        ".cache",
        "*.tmp",
        "*.log",
        "*.swp",
        "*.swo",
    }

    # 文档目录
    DOC_DIRS: Set[str] = {"docs", "doc", "documentation"}

    # 生成代码目录
    GENERATED_DIRS: Set[str] = {"generated", "gen", "auto-generated"}

    # 其他
    OTHER_DIRS: Set[str] = {
        "playground",
        "sandbox",
        ".idea",
        ".vscode",
        ".DS_Store",
        "Thumbs.db",
    }

    # Jarvis 特定
    dirs: Set[str] = {".jarvis"}

    @classmethod
    def get_all_ignore_dirs(cls) -> Set[str]:
        """获取所有需要忽略的目录名称集合。

        Returns:
            所有忽略目录名称的集合
        """
        return (
            cls.VCS_DIRS
            | cls.PYTHON_DIRS
            | cls.PYTHON_VENV_DIRS
            | cls.RUST_DIRS
            | cls.GO_DIRS
            | cls.NODE_DIRS
            | cls.JAVA_DIRS
            | cls.C_CPP_DIRS
            | cls.DOTNET_DIRS
            | cls.BUILD_DIRS
            | cls.DEPENDENCY_DIRS
            | cls.TEST_DIRS
            | cls.BENCHMARK_DIRS
            | cls.EXAMPLE_DIRS
            | cls.TEMP_DIRS
            | cls.DOC_DIRS
            | cls.GENERATED_DIRS
            | cls.OTHER_DIRS
            | cls.dirs
        )

    @classmethod
    def get_code_analysis_ignore_dirs(cls) -> Set[str]:
        """获取代码分析时应该忽略的目录（不包含测试目录）。

        Returns:
            代码分析忽略目录集合
        """
        return (
            cls.VCS_DIRS
            | cls.PYTHON_DIRS
            | cls.PYTHON_VENV_DIRS
            | cls.RUST_DIRS
            | cls.GO_DIRS
            | cls.NODE_DIRS
            | cls.JAVA_DIRS
            | cls.C_CPP_DIRS
            | cls.DOTNET_DIRS
            | cls.BUILD_DIRS
            | cls.DEPENDENCY_DIRS
            | cls.BENCHMARK_DIRS
            | cls.EXAMPLE_DIRS
            | cls.TEMP_DIRS
            | cls.DOC_DIRS
            | cls.GENERATED_DIRS
            | cls.OTHER_DIRS
            | cls.dirs
        )

    @classmethod
    def get_dependency_analysis_ignore_dirs(cls) -> Set[str]:
        """获取依赖分析时应该忽略的目录。

        Returns:
            依赖分析忽略目录集合
        """
        return (
            cls.VCS_DIRS
            | cls.BUILD_DIRS
            | cls.DEPENDENCY_DIRS
            | cls.TEST_DIRS
            | cls.BENCHMARK_DIRS
            | cls.EXAMPLE_DIRS
            | cls.TEMP_DIRS
            | cls.DOC_DIRS
            | cls.GENERATED_DIRS
            | cls.OTHER_DIRS
            | cls.dirs
        )


class FileIgnoreFilter:
    """文件忽略过滤器。

    提供统一的文件/目录过滤逻辑。
    """

    def __init__(
        self,
        ignore_dirs: Optional[Set[str]] = None,
        ignore_hidden: bool = True,
        custom_filter: Optional[Callable[[str], bool]] = None,
    ):
        """初始化文件忽略过滤器。

        Args:
            ignore_dirs: 要忽略的目录名称集合，如果为None则使用默认集合
            ignore_hidden: 是否忽略隐藏目录（以 . 开头）
            custom_filter: 自定义过滤函数，接收目录名，返回True表示忽略
        """
        if ignore_dirs is None:
            ignore_dirs = FileIgnorePatterns.get_code_analysis_ignore_dirs()

        self.ignore_dirs = ignore_dirs
        self.ignore_hidden = ignore_hidden
        self.custom_filter = custom_filter

    def should_ignore_dir(self, dir_name: str) -> bool:
        """判断是否应该忽略某个目录。

        Args:
            dir_name: 目录名称（不包含路径）

        Returns:
            如果应该忽略返回True，否则返回False
        """
        # 检查隐藏目录
        if self.ignore_hidden and dir_name.startswith("."):
            return True

        # 检查忽略目录集合
        if dir_name in self.ignore_dirs:
            return True

        # 检查自定义过滤器
        if self.custom_filter and self.custom_filter(dir_name):
            return True

        return False

    def should_ignore_path(self, path: str) -> bool:
        """判断是否应该忽略某个路径（文件或目录）。

        Args:
            path: 文件或目录路径

        Returns:
            如果应该忽略返回True，否则返回False
        """
        path_obj = Path(path)

        # 检查路径中的任何部分是否应该被忽略
        for part in path_obj.parts:
            if self.should_ignore_dir(part):
                return True

        return False

    def filter_dirs(self, dirs: List[str]) -> List[str]:
        """过滤目录列表，移除应该忽略的目录。

        这个方法可以直接用于 os.walk 的 dirs 列表修改：
        dirs[:] = filter.filter_dirs(dirs)

        Args:
            dirs: 目录名称列表

        Returns:
            过滤后的目录列表
        """
        return [d for d in dirs if not self.should_ignore_dir(d)]

    def filter_paths(self, paths: List[str]) -> List[str]:
        """过滤路径列表，移除应该忽略的路径。

        Args:
            paths: 路径列表

        Returns:
            过滤后的路径列表
        """
        return [p for p in paths if not self.should_ignore_path(p)]


# 预定义的过滤器实例
DEFAULT_FILTER = FileIgnoreFilter()
CODE_ANALYSIS_FILTER = FileIgnoreFilter(
    ignore_dirs=FileIgnorePatterns.get_code_analysis_ignore_dirs()
)
DEPENDENCY_ANALYSIS_FILTER = FileIgnoreFilter(
    ignore_dirs=FileIgnorePatterns.get_dependency_analysis_ignore_dirs()
)
ALL_IGNORE_FILTER = FileIgnoreFilter(
    ignore_dirs=FileIgnorePatterns.get_all_ignore_dirs()
)


def should_ignore_dir(dir_name: str, ignore_dirs: Optional[Set[str]] = None) -> bool:
    """便捷函数：判断是否应该忽略目录。

    Args:
        dir_name: 目录名称
        ignore_dirs: 忽略目录集合，如果为None使用默认集合

    Returns:
        如果应该忽略返回True
    """
    if ignore_dirs is None:
        ignore_dirs = FileIgnorePatterns.get_code_analysis_ignore_dirs()

    # 隐藏目录
    if dir_name.startswith("."):
        return True

    # 忽略目录集合
    return dir_name in ignore_dirs


def filter_walk_dirs(
    dirs: List[str], ignore_dirs: Optional[Set[str]] = None
) -> List[str]:
    """便捷函数：过滤 os.walk 的 dirs 列表。

    用法：
        for root, dirs, files in os.walk(path):
            dirs[:] = filter_walk_dirs(dirs)

    Args:
        dirs: os.walk 返回的目录列表
        ignore_dirs: 忽略目录集合，如果为None使用默认集合

    Returns:
        过滤后的目录列表
    """
    if ignore_dirs is None:
        ignore_dirs = FileIgnorePatterns.get_code_analysis_ignore_dirs()

    return [d for d in dirs if not (d.startswith(".") or d in ignore_dirs)]
