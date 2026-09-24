"""LSP 语言服务器配置读取模块（唯一配置来源）。

配置统一来自 ``~/.jarvis/config.yaml`` 的 ``lsp.languages`` 段，jarvis-lsp
（CLI / 守护进程）与 Web 网关（Monaco 编辑器）共用本模块，避免两套配置漂移。

配置结构::

    lsp:
      languages:
        python:
          command: pylsp
          args: []
          file_extensions: [".py", ".pyi"]
          monaco_language: python
          root_markers: ["pyproject.toml", ".git"]
          initialization_options: {}
          install_hint: "pip install python-lsp-server"

字段说明：

    command                 str        启动命令（必填，字符串而非列表，
                                       避免 shell 解析；参数放 args）
    args                    list[str]  启动参数（可选，默认 []）
    file_extensions         list[str]  文件扩展名（可选，默认 []），
                                       用于按扩展名匹配语言
    monaco_language         str        对应 Monaco 语言 id（可选，默认取语言名）
    root_markers            list[str]  workspace 根标记文件（可选，默认 []）
    initialization_options  dict       传给 LSP initialize 的选项（可选，默认 {}）
    install_hint            str        服务器未安装时的提示文案（可选，默认 ""）

用户配置会覆盖内置默认配置（``DEFAULT_LANGUAGES``），语言名大小写不敏感。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvis.jarvis_utils.config import get_global_config_data


@dataclass
class LanguageConfig:
    """单种语言的 LSP 服务器配置。

    Attributes:
        command: LSP 服务器可执行文件命令。
        args: 启动参数列表。
        file_extensions: 支持的文件扩展名列表。
        monaco_language: 对应 Monaco 语言 id，默认取语言名。
        root_markers: 用于确定 workspace 根的标记文件。
        initialization_options: 传给 LSP ``initialize`` 的选项。
        install_hint: 服务器未安装时的提示文案。
    """

    command: str
    args: List[str] = field(default_factory=list)
    file_extensions: List[str] = field(default_factory=list)
    monaco_language: str = ""
    root_markers: List[str] = field(default_factory=list)
    initialization_options: Dict[str, Any] = field(default_factory=dict)
    install_hint: str = ""


@dataclass
class LSPConfig:
    """LSP 配置数据类。

    Attributes:
        languages: 语言配置字典，key 为语言名，value 为 LanguageConfig。
    """

    languages: Dict[str, LanguageConfig]


# 内置默认语言配置：用户未在 config.yaml 配置时使用。
# 用户同名配置会整体覆盖对应的默认项。
DEFAULT_LANGUAGES: Dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        command="pylsp",
        args=[],
        file_extensions=[".py", ".pyi"],
        monaco_language="python",
        root_markers=["pyproject.toml", "setup.py", "setup.cfg", ".git"],
        install_hint="pip install python-lsp-server",
    ),
    "go": LanguageConfig(
        command="gopls",
        args=[],
        file_extensions=[".go"],
        monaco_language="go",
        root_markers=["go.mod", "go.sum", ".git"],
        install_hint="go install golang.org/x/tools/gopls@latest",
    ),
    "typescript": LanguageConfig(
        command="typescript-language-server",
        args=["--stdio"],
        file_extensions=[".ts", ".tsx"],
        monaco_language="typescript",
        root_markers=["package.json", "tsconfig.json", ".git"],
        install_hint="npm install -g typescript-language-server typescript",
    ),
    "javascript": LanguageConfig(
        command="typescript-language-server",
        args=["--stdio"],
        file_extensions=[".js", ".jsx", ".mjs", ".cjs"],
        monaco_language="javascript",
        root_markers=["package.json", "jsconfig.json", ".git"],
        install_hint="npm install -g typescript-language-server typescript",
    ),
    "rust": LanguageConfig(
        command="rust-analyzer",
        args=[],
        file_extensions=[".rs"],
        monaco_language="rust",
        root_markers=["Cargo.toml", "Cargo.lock", ".git"],
        install_hint="rustup component add rust-analyzer",
    ),
    "c": LanguageConfig(
        command="clangd",
        args=[],
        file_extensions=[".c", ".h"],
        monaco_language="c",
        root_markers=["compile_commands.json", "CMakeLists.txt", ".git"],
        install_hint="安装 clangd（如 apt install clangd）",
    ),
    "cpp": LanguageConfig(
        command="clangd",
        args=[],
        file_extensions=[".cpp", ".hpp", ".cc", ".cxx", ".hh"],
        monaco_language="cpp",
        root_markers=["compile_commands.json", "CMakeLists.txt", ".git"],
        install_hint="安装 clangd（如 apt install clangd）",
    ),
    "lua": LanguageConfig(
        command="lua-language-server",
        args=[],
        file_extensions=[".lua"],
        monaco_language="lua",
        root_markers=[".luarc.json", ".git"],
        install_hint="安装 lua-language-server",
    ),
    "bash": LanguageConfig(
        command="bash-language-server",
        args=["start"],
        file_extensions=[".sh", ".bash", ".zsh"],
        monaco_language="shell",
        root_markers=[".git"],
        install_hint="npm install -g bash-language-server",
    ),
    "ruby": LanguageConfig(
        command="solargraph",
        args=["stdio"],
        file_extensions=[".rb"],
        monaco_language="ruby",
        root_markers=["Gemfile", ".git"],
        install_hint="gem install solargraph",
    ),
    "php": LanguageConfig(
        command="intelephense",
        args=["--stdio"],
        file_extensions=[".php"],
        monaco_language="php",
        root_markers=["composer.json", ".git"],
        install_hint="npm install -g intelephense",
    ),
    "html": LanguageConfig(
        command="vscode-html-language-server",
        args=["--stdio"],
        file_extensions=[".html", ".htm"],
        monaco_language="html",
        root_markers=[".git"],
        install_hint="npm install -g vscode-langservers-extracted",
    ),
    "css": LanguageConfig(
        command="vscode-css-language-server",
        args=["--stdio"],
        file_extensions=[".css", ".scss", ".less"],
        monaco_language="css",
        root_markers=[".git"],
        install_hint="npm install -g vscode-langservers-extracted",
    ),
}


def _as_str_list(value: Any) -> List[str]:
    """把配置值规整为字符串列表；类型不符时返回空列表。"""
    if isinstance(value, list) and all(isinstance(i, str) for i in value):
        return list(value)
    return []


def _parse_language(name: str, raw: Any) -> Optional[LanguageConfig]:
    """解析单条语言配置。

    Args:
        name: 语言名（config.yaml 中的 key）。
        raw: 原始配置对象。

    Returns:
        LanguageConfig；格式非法时返回 None（调用方记录 warning 并跳过）。
    """
    if not isinstance(raw, dict):
        return None

    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        return None

    monaco_language = raw.get("monaco_language")
    if not isinstance(monaco_language, str) or not monaco_language.strip():
        monaco_language = name

    initialization_options = raw.get("initialization_options")
    if not isinstance(initialization_options, dict):
        initialization_options = {}

    install_hint = raw.get("install_hint")
    if not isinstance(install_hint, str):
        install_hint = ""

    return LanguageConfig(
        command=command.strip(),
        args=_as_str_list(raw.get("args")),
        file_extensions=_as_str_list(raw.get("file_extensions")),
        monaco_language=monaco_language.strip(),
        root_markers=_as_str_list(raw.get("root_markers")),
        initialization_options=initialization_options,
        install_hint=install_hint,
    )


class LSPConfigReader:
    """LSP 配置读取器。

    从全局配置数据（``~/.jarvis/config.yaml``）中读取 ``lsp.languages``，
    与内置默认配置合并，用户配置优先。提供语言检测与配置查询功能。
    """

    def load_config(self) -> LSPConfig:
        """加载 LSP 配置：内置默认 + 用户配置（用户优先）。

        Returns:
            LSPConfig 对象。格式非法的语言项会被跳过，不影响其他语言。
        """
        languages: Dict[str, LanguageConfig] = {
            name: cfg for name, cfg in DEFAULT_LANGUAGES.items()
        }

        config_data = get_global_config_data()
        lsp_data = config_data.get("lsp") or {}
        if not isinstance(lsp_data, dict):
            return LSPConfig(languages=languages)

        languages_data = lsp_data.get("languages") or {}
        if not isinstance(languages_data, dict):
            return LSPConfig(languages=languages)

        for lang_name, lang_data in languages_data.items():
            if not isinstance(lang_name, str) or not lang_name.strip():
                continue
            parsed = _parse_language(lang_name.strip(), lang_data)
            if parsed is None:
                continue
            # 用户配置整体覆盖同名默认项
            languages[lang_name.strip()] = parsed

        return LSPConfig(languages=languages)

    def get_language_config(self, language: str) -> Optional[LanguageConfig]:
        """获取指定语言的配置。

        Args:
            language: 语言名称（大小写不敏感）。

        Returns:
            LanguageConfig 对象，不存在则返回 None。
        """
        if not isinstance(language, str) or not language.strip():
            return None
        config = self.load_config()
        target = language.strip()
        if target in config.languages:
            return config.languages[target]
        # 大小写不敏感回退
        lowered = target.lower()
        for name, cfg in config.languages.items():
            if name.lower() == lowered:
                return cfg
        return None

    def detect_language(self, file_path: str) -> Optional[str]:
        """根据文件扩展名检测语言。

        Args:
            file_path: 文件路径。

        Returns:
            语言名称，无法检测则返回 None。
        """
        try:
            config = self.load_config()
        except Exception:
            return None
        ext = Path(file_path).suffix
        if not ext:
            return None
        for lang_name, lang_config in config.languages.items():
            if ext in lang_config.file_extensions:
                return lang_name
        return None
