# -*- coding: utf-8 -*-
"""语言功能支持信息模块

提供语言功能支持情况的收集和展示功能。
"""

from typing import Any


def _collect_language_support_info() -> dict[str, dict[str, Any]]:
    """收集所有语言的功能支持信息"""
    info: dict[str, dict[str, Any]] = {}

    # 确保语言支持模块已加载（触发自动注册）
    try:
        pass
    except Exception:
        pass

    # 从 code_analyzer 获取语言支持
    try:
        from jarvis.jarvis_code_agent.code_analyzer.language_registry import (
            get_registry,
        )

        registry = get_registry()

        for lang_name in registry.get_supported_languages():
            lang_support = registry.get_language_support(lang_name)
            if lang_support:
                if lang_name not in info:
                    info[lang_name] = {}

                # 检查符号提取支持
                try:
                    extractor = lang_support.create_symbol_extractor()
                    info[lang_name]["符号提取"] = extractor is not None
                except Exception:
                    # 如果创建失败，先标记为 False，后续会检查 file_context_handler 中的提取器
                    info[lang_name]["符号提取"] = False

                # 检查依赖分析支持
                try:
                    analyzer = lang_support.create_dependency_analyzer()
                    info[lang_name]["依赖分析"] = analyzer is not None
                except Exception:
                    info[lang_name]["依赖分析"] = False

    except Exception:
        pass

    # 从 file_context_handler 获取上下文提取支持，同时也用于补充符号提取支持
    try:
        from jarvis.jarvis_agent.file_context_handler import _LANGUAGE_EXTRACTORS

        # 扩展名到语言名称的映射
        lang_name_map = {
            ".py": "python",
            ".pyw": "python",
            ".rs": "rust",
            ".go": "go",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
        }

        for ext, factory in _LANGUAGE_EXTRACTORS.items():
            try:
                # 尝试创建提取器，只有成功创建才标记为支持
                extractor = factory()
                if extractor is not None:
                    lang_name = lang_name_map.get(
                        ext, ext[1:] if ext.startswith(".") else ext
                    )

                    if lang_name not in info:
                        info[lang_name] = {}

                    # 上下文提取支持（只有成功创建才支持）
                    info[lang_name]["上下文提取"] = True

                    # 如果 code_analyzer 中的符号提取不支持，但 file_context_handler 中能成功创建提取器，也标记为支持
                    if (
                        "符号提取" not in info[lang_name]
                        or not info[lang_name]["符号提取"]
                    ):
                        info[lang_name]["符号提取"] = True
            except Exception:
                # 静默失败，不记录错误（避免输出过多调试信息）
                pass
    except Exception:
        pass

    # 检查构建验证支持（自动发现所有构建验证器）
    try:
        import jarvis.jarvis_code_agent.code_analyzer.build_validator as build_validator_module
        from jarvis.jarvis_code_agent.code_analyzer.build_validator import __all__
        from jarvis.jarvis_code_agent.code_analyzer.build_validator.base import (
            BuildValidatorBase,
        )

        # 自动发现所有构建验证器类（排除基类和工具类）
        validator_classes = []
        exclude_classes = {
            "BuildValidatorBase",
            "BuildSystemDetector",
            "BuildValidator",
            "BuildSystem",
            "BuildResult",
        }

        for name in __all__:
            if name not in exclude_classes and name.endswith("BuildValidator"):
                try:
                    validator_class = getattr(build_validator_module, name)
                    # 检查是否是 BuildValidatorBase 的子类
                    if (
                        issubclass(validator_class, BuildValidatorBase)
                        and validator_class != BuildValidatorBase
                    ):
                        validator_classes.append(validator_class)
                except (AttributeError, TypeError, Exception):
                    continue

        # 为每种语言收集支持的构建系统名称
        lang_to_build_systems: dict[str, list[str]] = {}

        for validator_class in validator_classes:
            try:
                # 检查类是否有 BUILD_SYSTEM_NAME 和 SUPPORTED_LANGUAGES
                build_system_name = getattr(validator_class, "BUILD_SYSTEM_NAME", "")
                supported_languages = getattr(
                    validator_class, "SUPPORTED_LANGUAGES", []
                )

                if build_system_name and supported_languages:
                    for lang in supported_languages:
                        if lang not in lang_to_build_systems:
                            lang_to_build_systems[lang] = []
                        if build_system_name not in lang_to_build_systems[lang]:
                            lang_to_build_systems[lang].append(build_system_name)
            except (AttributeError, Exception):
                continue

        # 将构建系统信息添加到 info 中
        for lang_name, build_systems in lang_to_build_systems.items():
            if lang_name not in info:
                info[lang_name] = {}
            if build_systems:
                # 存储构建系统名称列表（用于显示）
                info[lang_name]["构建验证"] = ", ".join(sorted(build_systems))
            else:
                info[lang_name]["构建验证"] = False

    except (ImportError, Exception):
        pass

    # 检查静态检查支持（从 lint.py 获取）
    try:
        from jarvis.jarvis_code_agent.lint import LINT_COMMAND_TEMPLATES_BY_FILE

        # 扩展名到语言名称的映射
        ext_to_lang_for_lint = {
            ".py": "python",
            ".pyw": "python",
            ".pyi": "python",
            ".rs": "rust",
            ".go": "go",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".cts": "typescript",
            ".mts": "typescript",
            ".java": "java",
        }

        # 检查每种语言是否有对应的 lint 工具
        for ext, lang_name in ext_to_lang_for_lint.items():
            if lang_name not in info:
                info[lang_name] = {}
            if (
                ext in LINT_COMMAND_TEMPLATES_BY_FILE
                and LINT_COMMAND_TEMPLATES_BY_FILE.get(ext)
            ):
                info[lang_name]["静态检查"] = True
    except Exception:
        pass

    # 确保所有已知语言都在 info 中（即使某些功能不支持）
    # 这样表格会显示所有语言，即使某些功能不支持
    known_languages = [
        "python",
        "c",
        "cpp",
        "rust",
        "go",
        "javascript",
        "typescript",
        "java",
    ]
    for lang_name in known_languages:
        if lang_name not in info:
            info[lang_name] = {}
        # 确保所有功能字段都存在
        for feature in [
            "符号提取",
            "依赖分析",
            "上下文提取",
            "构建验证",
            "静态检查",
        ]:
            if feature not in info[lang_name]:
                # 对于上下文提取，检查是否有对应的提取器
                if feature == "上下文提取":
                    try:
                        from jarvis.jarvis_agent.file_context_handler import (
                            _LANGUAGE_EXTRACTORS,
                        )

                        ext_map = {
                            "python": [".py", ".pyw"],
                            "rust": [".rs"],
                            "go": [".go"],
                            "c": [".c", ".h"],
                            "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
                            "javascript": [".js", ".jsx"],
                            "typescript": [".ts", ".tsx"],
                            "java": [".java"],
                        }
                        exts = ext_map.get(lang_name, [])
                        # 尝试创建提取器，只有成功创建才认为支持（需要 tree-sitter 已安装）
                        has_extractor = False
                        for ext in exts:
                            if ext in _LANGUAGE_EXTRACTORS:
                                try:
                                    factory = _LANGUAGE_EXTRACTORS[ext]
                                    extractor = factory()
                                    if extractor:
                                        has_extractor = True
                                        break
                                except Exception:
                                    continue
                        info[lang_name][feature] = has_extractor
                    except Exception:
                        info[lang_name][feature] = False
                elif feature == "符号提取":
                    # 如果之前没有设置或为 False，再次检查 file_context_handler 中的提取器
                    # 只有能成功创建提取器才标记为支持（需要 tree-sitter 已安装）
                    if (
                        "符号提取" not in info[lang_name]
                        or not info[lang_name]["符号提取"]
                    ):
                        try:
                            from jarvis.jarvis_agent.file_context_handler import (
                                _LANGUAGE_EXTRACTORS,
                            )

                            ext_map = {
                                "python": [".py", ".pyw"],
                                "rust": [".rs"],
                                "go": [".go"],
                                "c": [".c", ".h"],
                                "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
                                "javascript": [".js", ".jsx"],
                                "typescript": [".ts", ".tsx"],
                            }
                            exts = ext_map.get(lang_name, [])
                            # 尝试创建提取器，只有成功创建才认为支持
                            has_extractor = False
                            for ext in exts:
                                if ext in _LANGUAGE_EXTRACTORS:
                                    try:
                                        factory = _LANGUAGE_EXTRACTORS[ext]
                                        extractor = factory()
                                        if extractor:
                                            has_extractor = True
                                            break
                                    except Exception:
                                        continue
                            info[lang_name][feature] = has_extractor
                        except Exception:
                            info[lang_name][feature] = False
                elif feature == "构建验证":
                    # 默认 False，已在上面检查过（可能是字符串或False）
                    if feature not in info[lang_name]:
                        info[lang_name][feature] = False
                elif feature == "静态检查":
                    # 默认 False，已在上面检查过
                    info[lang_name][feature] = info[lang_name].get(feature, False)
                else:
                    info[lang_name][feature] = False

    # 确保所有已知语言都在 info 中（即使某些功能不支持）
    # 这样表格会显示所有语言，即使某些功能不支持
    known_languages = [
        "python",
        "c",
        "cpp",
        "rust",
        "go",
        "javascript",
        "typescript",
        "java",
    ]
    for lang_name in known_languages:
        if lang_name not in info:
            info[lang_name] = {}
        # 确保所有功能字段都存在
        for feature in [
            "符号提取",
            "依赖分析",
            "上下文提取",
            "构建验证",
            "静态检查",
        ]:
            if feature not in info[lang_name]:
                # 对于上下文提取，检查是否有对应的提取器
                if feature == "上下文提取":
                    try:
                        from jarvis.jarvis_agent.file_context_handler import (
                            _LANGUAGE_EXTRACTORS,
                        )

                        ext_map = {
                            "python": [".py", ".pyw"],
                            "rust": [".rs"],
                            "go": [".go"],
                            "c": [".c", ".h"],
                            "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
                            "javascript": [".js", ".jsx"],
                            "typescript": [".ts", ".tsx"],
                            "java": [".java"],
                        }
                        exts = ext_map.get(lang_name, [])
                        # 尝试创建提取器，只有成功创建才认为支持（需要 tree-sitter 已安装）
                        has_extractor = False
                        for ext in exts:
                            if ext in _LANGUAGE_EXTRACTORS:
                                try:
                                    factory = _LANGUAGE_EXTRACTORS[ext]
                                    extractor = factory()
                                    if extractor:
                                        has_extractor = True
                                        break
                                except Exception:
                                    continue
                        info[lang_name][feature] = has_extractor
                    except Exception:
                        info[lang_name][feature] = False
                elif feature == "符号提取":
                    # 如果之前没有设置或为 False，再次检查 file_context_handler 中的提取器
                    # 只有能成功创建提取器才标记为支持（需要 tree-sitter 已安装）
                    if (
                        "符号提取" not in info[lang_name]
                        or not info[lang_name]["符号提取"]
                    ):
                        try:
                            from jarvis.jarvis_agent.file_context_handler import (
                                _LANGUAGE_EXTRACTORS,
                            )

                            ext_map = {
                                "python": [".py", ".pyw"],
                                "rust": [".rs"],
                                "go": [".go"],
                                "c": [".c", ".h"],
                                "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hxx"],
                                "javascript": [".js", ".jsx"],
                                "typescript": [".ts", ".tsx"],
                            }
                            exts = ext_map.get(lang_name, [])
                            # 尝试创建提取器，只有成功创建才认为支持
                            has_extractor = False
                            for ext in exts:
                                if ext in _LANGUAGE_EXTRACTORS:
                                    try:
                                        factory = _LANGUAGE_EXTRACTORS[ext]
                                        extractor = factory()
                                        if extractor:
                                            has_extractor = True
                                            break
                                    except Exception:
                                        continue
                            info[lang_name][feature] = has_extractor
                        except Exception:
                            info[lang_name][feature] = False
                elif feature == "构建验证":
                    # 默认 False，已在上面检查过（可能是字符串或False）
                    if feature not in info[lang_name]:
                        info[lang_name][feature] = False
                elif feature == "静态检查":
                    # 默认 False，已在上面检查过
                    info[lang_name][feature] = info[lang_name].get(feature, False)
                else:
                    info[lang_name][feature] = False

    return info


def print_language_support_table() -> None:
    """打印语言功能支持表格"""
    from rich.align import Align
    from rich.console import Console
    from rich.table import Table

    info = _collect_language_support_info()

    if not info:
        return

    # 定义功能列表
    features = [
        "符号提取",
        "依赖分析",
        "上下文提取",
        "构建验证",
        "静态检查",
    ]

    # 定义语言显示名称映射
    lang_display_names = {
        "python": "Python",
        "rust": "Rust",
        "go": "Go",
        "c": "C",
        "cpp": "C++",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "java": "Java",
    }

    # 获取所有语言（按固定顺序，优先显示 C, C++, Rust, Go）
    priority_languages = ["c", "cpp", "rust", "go"]
    other_languages = ["python", "javascript", "typescript", "java"]
    all_languages = priority_languages + [
        lang for lang in other_languages if lang not in priority_languages
    ]
    # 显示所有已知语言，即使某些功能不支持（只要在 info 中有记录）
    languages = [lang for lang in all_languages if lang in info]

    # 如果没有任何语言，尝试显示 info 中的所有语言
    if not languages:
        languages = list(info.keys())
        # 按优先级排序
        languages = sorted(
            languages,
            key=lambda x: (
                0 if x in priority_languages else 1,
                priority_languages.index(x) if x in priority_languages else 999,
                x,
            ),
        )

    if not languages:
        return

    # 创建表格
    table = Table(
        title="[bold cyan]编程语言功能支持情况[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        border_style="blue",
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )

    # 添加语言列（第一列）
    table.add_column("语言", style="cyan", no_wrap=True, justify="left")

    # 添加功能列
    for feature in features:
        table.add_column(feature, justify="center", style="green", no_wrap=True)

    # 添加语言行
    for lang in languages:
        display_name = lang_display_names.get(lang, lang.capitalize())
        row = [display_name]
        for feature in features:
            supported = info.get(lang, {}).get(feature, False)
            if supported:
                # 如果是构建验证，显示构建系统名称
                if feature == "构建验证" and isinstance(supported, str):
                    row.append(f"[bold green]{supported}[/bold green]")
                else:
                    row.append("[bold green]✓[/bold green]")
            else:
                row.append("[bold red]✗[/bold red]")
        table.add_row(*row)

    console = Console()
    console.print()
    # 居中显示表格
    aligned_table = Align.center(table)
    console.print(aligned_table)
    console.print()
