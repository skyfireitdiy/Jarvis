"""配置读取模块

该模块提供 LSP 配置读取功能，从 ~/.jarvis/config.yaml 中
读取各种语言的 LSP 服务器配置。

配置复用 jarvis_utils.config 的全局配置数据。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from jarvis.jarvis_utils.config import get_global_config_data


@dataclass
class LanguageConfig:
    """语言配置数据类

    Attributes:
        command: LSP 服务器可执行文件命令
        args: 启动参数列表
        file_extensions: 支持的文件扩展名列表
    """

    command: str
    args: list[str]
    file_extensions: list[str]


@dataclass
class LSPConfig:
    """LSP 配置数据类

    Attributes:
        languages: 语言配置字典，key 为语言名，value 为 LanguageConfig
    """

    languages: Dict[str, LanguageConfig]


# 默认语言配置
# 这些配置可以覆盖大部分常用语言的 LSP 服务器
DEFAULT_LANGUAGES: Dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        command="pylsp",
        args=["--check-parent-process", "--log-file", "/tmp/pylsp.log", "-v"],
        file_extensions=[".py", ".pyi"],
    ),
    "go": LanguageConfig(
        command="gopls",
        args=[],
        file_extensions=[".go"],
    ),
    "rust": LanguageConfig(
        command="rust-analyzer",
        args=[],
        file_extensions=[".rs"],
    ),
    "c": LanguageConfig(
        command="clangd",
        args=[],
        file_extensions=[".c", ".h"],
    ),
    "cpp": LanguageConfig(
        command="clangd",
        args=[],
        file_extensions=[".cpp", ".hpp", ".cc", ".cxx", ".hh"],
    ),
    "c++": LanguageConfig(
        command="clangd",
        args=[],
        file_extensions=[".cpp", ".hpp", ".cc", ".cxx", ".hh"],
    ),
    "javascript": LanguageConfig(
        command="javascript-typescript-stdio",
        args=[],
        file_extensions=[".js", ".jsx", ".mjs"],
    ),
    "typescript": LanguageConfig(
        command="typescript-language-server",
        args=["--stdio"],
        file_extensions=[".ts", ".tsx"],
    ),
    "lua": LanguageConfig(
        command="lua-language-server",
        args=[],
        file_extensions=[".lua"],
    ),
    "bash": LanguageConfig(
        command="bash-language-server",
        args=["start"],
        file_extensions=[".sh", ".bash", ".zsh"],
    ),
    "ruby": LanguageConfig(
        command="solargraph",
        args=["stdio"],
        file_extensions=[".rb"],
    ),
    "php": LanguageConfig(
        command="intelephense",
        args=["--stdio"],
        file_extensions=[".php"],
    ),
    "html": LanguageConfig(
        command="vscode-html-language-server",
        args=["--stdio"],
        file_extensions=[".html", ".htm"],
    ),
    "css": LanguageConfig(
        command="vscode-css-language-server",
        args=["--stdio"],
        file_extensions=[".css", ".scss", ".less"],
    ),
}


class LSPConfigReader:
    """LSP 配置读取器

    从全局配置数据中读取 LSP 配置，并提供
    语言检测和配置查询功能。
    """

    def load_config(self) -> LSPConfig:
        """加载 LSP 配置

        默认配置和用户配置合并，用户配置优先。

        Returns:
            LSPConfig 对象

        Raises:
            ValueError: 配置格式错误
        """
        # 从默认配置开始
        languages: Dict[str, LanguageConfig] = dict(DEFAULT_LANGUAGES)

        # 加载用户配置并覆盖默认配置
        config_data = get_global_config_data()
        lsp_data = config_data.get("lsp", {})
        languages_data = lsp_data.get("languages", {})

        for lang_name, lang_data in languages_data.items():
            if not isinstance(lang_data, dict):
                raise ValueError(
                    f"语言配置格式错误: {lang_name}"
                )

            # 验证必需字段
            if "command" not in lang_data:
                raise ValueError(
                    f"语言 {lang_name} 缺少必需字段: command"
                )

            if "args" not in lang_data:
                raise ValueError(
                    f"语言 {lang_name} 缺少必需字段: args"
                )

            if "file_extensions" not in lang_data:
                raise ValueError(
                    f"语言 {lang_name} 缺少必需字段: file_extensions"
                )

            # 用户配置覆盖默认配置
            languages[lang_name] = LanguageConfig(
                command=lang_data["command"],
                args=lang_data["args"],
                file_extensions=lang_data["file_extensions"],
            )

        return LSPConfig(languages=languages)

    def get_language_config(self, language: str) -> Optional[LanguageConfig]:
        """获取指定语言的配置

        Args:
            language: 语言名称

        Returns:
            LanguageConfig 对象，如果不存在则返回 None
        """
        try:
            config = self.load_config()
            return config.languages.get(language)
        except ValueError:
            return None

    def detect_language(self, file_path: str) -> Optional[str]:
        """根据文件扩展名检测语言

        Args:
            file_path: 文件路径

        Returns:
            语言名称，如果无法检测则返回 None
        """
        try:
            config = self.load_config()
            path = Path(file_path)
            ext = path.suffix

            for lang_name, lang_config in config.languages.items():
                if ext in lang_config.file_extensions:
                    return lang_name

            return None
        except ValueError:
            return None
