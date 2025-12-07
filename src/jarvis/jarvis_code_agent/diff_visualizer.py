# -*- coding: utf-8 -*-
"""改进的 Diff 可视化工具

提供多种 diff 可视化方式，改善代码变更的可读性。
"""

from typing import List, Optional
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
import difflib


class DiffVisualizer:
    """改进的 Diff 可视化工具"""

    def __init__(self, console: Optional[Console] = None):
        """初始化可视化器

        参数:
            console: Rich Console 实例，如果为 None 则创建新实例
        """
        self.console = console or Console()

    def visualize_unified_diff(
        self,
        diff_text: str,
        file_path: str = "",
        show_line_numbers: bool = True,
        context_lines: int = 3,
    ) -> None:
        """可视化统一格式的 diff（改进版）

        参数:
            diff_text: git diff 输出的文本
            file_path: 文件路径（用于显示标题）
            show_line_numbers: 是否显示行号
            context_lines: 上下文行数
        """
        if not diff_text.strip():
            return

        lines = diff_text.split("\n")

        # 创建表格显示
        table = Table(
            show_header=False,
            header_style="bold magenta",
            box=None,  # 无边框，更简洁
            padding=(0, 1),
        )

        if show_line_numbers:
            table.add_column("", style="dim red", width=8, justify="right")
            table.add_column("", style="dim green", width=8, justify="right")
        table.add_column("", width=4, justify="center")
        table.add_column("", style="white", overflow="fold")

        old_line_num = 0
        new_line_num = 0
        in_hunk = False
        hunk_lines = []  # 存储当前 hunk 中的所有行（包括上下文和变更）

        def flush_hunk_context():
            """刷新当前 hunk，只显示 context_lines 数量的上下文"""
            nonlocal hunk_lines
            if not hunk_lines:
                return

            # 找到所有变更行的索引
            change_indices = []
            for idx, (line_type, _, _, _) in enumerate(hunk_lines):
                if line_type in ("-", "+"):
                    change_indices.append(idx)

            if not change_indices:
                # 没有变更，只显示最后 context_lines 行上下文
                for line_type, old_ln, new_ln, content in hunk_lines[-context_lines:]:
                    if show_line_numbers:
                        table.add_row(
                            str(old_ln),
                            str(new_ln),
                            " ",
                            f"[dim]{content}[/dim]",
                        )
                    else:
                        table.add_row("", " ", f"[dim]{content}[/dim]")
            else:
                # 有变更，只显示变更前后的上下文
                first_change_idx = change_indices[0]
                last_change_idx = change_indices[-1]

                # 显示变更前的上下文（最多 context_lines 行）
                pre_context_start = max(0, first_change_idx - context_lines)
                for idx in range(pre_context_start, first_change_idx):
                    _, old_ln, new_ln, content = hunk_lines[idx]
                    if show_line_numbers:
                        table.add_row(
                            str(old_ln),
                            str(new_ln),
                            " ",
                            f"[dim]{content}[/dim]",
                        )
                    else:
                        table.add_row("", " ", f"[dim]{content}[/dim]")

                # 显示所有变更行
                for idx in range(first_change_idx, last_change_idx + 1):
                    line_type, old_ln, new_ln, content = hunk_lines[idx]
                    if line_type == "-":
                        if show_line_numbers:
                            table.add_row(
                                str(old_ln) if old_ln else "",
                                "",
                                "[bold red]-[/bold red]",
                                f"[red]{content}[/red]",
                            )
                        else:
                            table.add_row(
                                "",
                                "[bold red]-[/bold red]",
                                f"[red]{content}[/red]",
                            )
                    elif line_type == "+":
                        if show_line_numbers:
                            table.add_row(
                                "",
                                str(new_ln) if new_ln else "",
                                "[bold green]+[/bold green]",
                                f"[green]{content}[/green]",
                            )
                        else:
                            table.add_row(
                                "",
                                "[bold green]+[/bold green]",
                                f"[green]{content}[/green]",
                            )

                # 显示变更后的上下文（最多 context_lines 行）
                post_context_end = min(
                    len(hunk_lines), last_change_idx + 1 + context_lines
                )
                for idx in range(last_change_idx + 1, post_context_end):
                    _, old_ln, new_ln, content = hunk_lines[idx]
                    if show_line_numbers:
                        table.add_row(
                            str(old_ln),
                            str(new_ln),
                            " ",
                            f"[dim]{content}[/dim]",
                        )
                    else:
                        table.add_row("", " ", f"[dim]{content}[/dim]")

            hunk_lines = []

        for line in lines:
            if line.startswith("diff --git") or line.startswith("index"):
                # 跳过 diff 头部
                continue
            elif line.startswith("---"):
                # 旧文件路径
                old_path = line[4:].strip()
                if not file_path and old_path != "/dev/null":
                    file_path = old_path
            elif line.startswith("+++"):
                # 新文件路径
                new_path = line[4:].strip()
                if new_path != "/dev/null":
                    file_path = new_path
            elif line.startswith("@@"):
                # Hunk 头部 - 刷新上一个 hunk
                if in_hunk:
                    flush_hunk_context()

                in_hunk = True
                # 解析行号信息
                parts = line.split("@@")
                if len(parts) >= 2:
                    hunk_info = parts[1].strip()
                    if hunk_info:
                        # 解析格式: -old_start,old_count +new_start,new_count
                        old_part = ""
                        new_part = ""
                        for token in hunk_info.split():
                            if token.startswith("-"):
                                old_part = token[1:].split(",")[0]
                            elif token.startswith("+"):
                                new_part = token[1:].split(",")[0]

                        if old_part:
                            try:
                                old_line_num = int(old_part)
                            except ValueError:
                                pass
                        if new_part:
                            try:
                                new_line_num = int(new_part)
                            except ValueError:
                                pass

                # 显示 hunk 头部
                hunk_text = Text(f"[dim]{line}[/dim]", style="cyan")
                if show_line_numbers:
                    table.add_row("", "", "", hunk_text)
                else:
                    table.add_row("", "", hunk_text)
            elif in_hunk:
                if line.startswith("-"):
                    # 删除的行
                    content = line[1:] if len(line) > 1 else ""
                    hunk_lines.append(("-", old_line_num, None, content))
                    old_line_num += 1
                elif line.startswith("+"):
                    # 新增的行
                    content = line[1:] if len(line) > 1 else ""
                    hunk_lines.append(("+", None, new_line_num, content))
                    new_line_num += 1
                elif line.startswith(" "):
                    # 未更改的行（上下文）
                    content = line[1:] if len(line) > 1 else ""
                    hunk_lines.append((" ", old_line_num, new_line_num, content))
                    old_line_num += 1
                    new_line_num += 1
                elif line.strip() == "\\":
                    # 文件末尾换行符差异
                    if show_line_numbers:
                        table.add_row(
                            "", "", "", "[dim]\\ No newline at end of file[/dim]"
                        )
                    else:
                        table.add_row("", "", "[dim]\\ No newline at end of file[/dim]")

        # 刷新最后一个 hunk
        if in_hunk:
            flush_hunk_context()

        # 显示 diff 表格（包裹在 Panel 中）
        if table.rows:
            title = f"📝 {file_path}" if file_path else "Diff"
            panel = Panel(table, title=title, border_style="cyan", padding=(0, 1))
            self.console.print(panel)

    def visualize_statistics(
        self, file_path: str, additions: int, deletions: int, total_changes: int = 0
    ) -> None:
        """显示文件变更统计

        参数:
            file_path: 文件路径
            additions: 新增行数
            deletions: 删除行数
            total_changes: 总变更行数（如果为0则自动计算）
        """
        if total_changes == 0:
            total_changes = additions + deletions

        # 创建统计文本
        stats_text = Text()
        stats_text.append(f"📊 {file_path}\n", style="bold cyan")
        stats_text.append("  ", style="dim")
        stats_text.append("➕ 新增: ", style="green")
        stats_text.append(f"{additions} 行", style="bold green")
        stats_text.append("  |  ", style="dim")
        stats_text.append("➖ 删除: ", style="red")
        stats_text.append(f"{deletions} 行", style="bold red")
        if total_changes > 0:
            stats_text.append("  |  ", style="dim")
            stats_text.append("📈 总计: ", style="cyan")
            stats_text.append(f"{total_changes} 行", style="bold cyan")

        panel = Panel(stats_text, border_style="cyan", padding=(1, 2))
        self.console.print(panel)

    def visualize_syntax_highlighted(
        self, diff_text: str, file_path: str = "", theme: str = "monokai"
    ) -> None:
        """使用语法高亮显示 diff（保持原有风格但改进）

        参数:
            diff_text: git diff 输出的文本
            file_path: 文件路径
            theme: 语法高亮主题
        """
        if not diff_text.strip():
            return

        # 使用 Rich 的 diff 语法高亮
        syntax = Syntax(
            diff_text,
            "diff",
            theme=theme,
            line_numbers=True,
            word_wrap=True,
            background_color="default",
        )

        if file_path:
            panel = Panel(
                syntax,
                title=f"📝 {file_path}",
                border_style="cyan",
                padding=(0, 1),
            )
            self.console.print(panel)
        else:
            self.console.print(syntax)

    def visualize_compact(
        self,
        diff_text: str,
        file_path: str = "",
        max_lines: int = 50,
    ) -> None:
        """紧凑型 diff 显示（适合快速预览）

        参数:
            diff_text: git diff 输出的文本
            file_path: 文件路径
            max_lines: 最大显示行数
        """
        if not diff_text.strip():
            return

        lines = diff_text.split("\n")
        display_lines = lines[:max_lines]

        # 统计信息
        additions = sum(
            1
            for line in display_lines
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1
            for line in display_lines
            if line.startswith("-") and not line.startswith("---")
        )

        # 显示 diff（使用语法高亮，包裹在 Panel 中）
        if len(lines) > max_lines:
            remaining = len(lines) - max_lines
            display_text = "\n".join(display_lines)
            display_text += f"\n... ({remaining} 行已省略)"
        else:
            display_text = "\n".join(display_lines)

        syntax = Syntax(
            display_text,
            "diff",
            theme="monokai",
            line_numbers=False,
            word_wrap=True,
        )

        # 构建标题（包含统计信息）
        title = f"📝 {file_path}" if file_path else "Diff"
        if additions > 0 or deletions > 0:
            title += f"  [green]+{additions}[/green] / [red]-{deletions}[/red]"

        panel = Panel(syntax, title=title, border_style="cyan", padding=(0, 1))
        self.console.print(panel)

    def visualize_side_by_side_summary(
        self,
        old_lines: List[str],
        new_lines: List[str],
        file_path: str = "",
        context_lines: int = 3,
        old_line_map: Optional[List[int]] = None,
        new_line_map: Optional[List[int]] = None,
    ) -> None:
        """并排显示摘要（仅显示变更部分，智能配对）

        参数:
            old_lines: 旧文件行列表
            new_lines: 新文件行列表
            file_path: 文件路径
            context_lines: 上下文行数
            old_line_map: 旧文件行号映射（索引对应 old_lines 索引，值为文件中的绝对行号）
            new_line_map: 新文件行号映射（索引对应 new_lines 索引，值为文件中的绝对行号）
        """
        # 使用 difflib.SequenceMatcher 进行更精确的匹配
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        # 如果没有提供行号映射，使用索引+1作为行号（向后兼容）
        if old_line_map is None:
            old_line_map = [i + 1 for i in range(len(old_lines))]
        if new_line_map is None:
            new_line_map = [i + 1 for i in range(len(new_lines))]

        # 创建并排表格
        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=None,
            padding=(0, 1),
        )
        table.add_column("", style="dim", width=6, justify="right")
        table.add_column("", style="red", overflow="fold", ratio=1)
        table.add_column("", style="dim", width=6, justify="right")
        table.add_column("", style="green", overflow="fold", ratio=1)

        additions = 0
        deletions = 0
        has_changes = False

        for idx, (tag, i1, i2, j1, j2) in enumerate(opcodes):
            if tag == "equal":
                # 显示未更改的行（灰色/dim样式），但只显示上下文行数
                equal_chunk = old_lines[i1:i2]
                equal_len = len(equal_chunk)

                # 只显示最后 context_lines 行作为上下文
                if equal_len > context_lines * 2:
                    # 如果 equal 块太长，只显示开头和结尾的上下文
                    if idx > 0:  # 不是第一个块
                        # 显示开头的 context_lines 行
                        for k in range(min(context_lines, equal_len)):
                            old_line_num = (
                                old_line_map[i1 + k]
                                if i1 + k < len(old_line_map)
                                else i1 + k + 1
                            )
                            new_line_num = (
                                new_line_map[j1 + k]
                                if j1 + k < len(new_line_map)
                                else j1 + k + 1
                            )
                            table.add_row(
                                f"[dim]{old_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                                f"[dim]{new_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                            )
                        # 如果有省略，显示省略标记
                        if equal_len > context_lines * 2:
                            table.add_row(
                                "",
                                "[dim]... ({0} lines omitted) ...[/dim]".format(
                                    equal_len - context_lines * 2
                                ),
                                "",
                                "",
                            )
                        # 显示结尾的 context_lines 行
                        for k in range(max(0, equal_len - context_lines), equal_len):
                            old_line_num = (
                                old_line_map[i1 + k]
                                if i1 + k < len(old_line_map)
                                else i1 + k + 1
                            )
                            new_line_num = (
                                new_line_map[j1 + k]
                                if j1 + k < len(new_line_map)
                                else j1 + k + 1
                            )
                            table.add_row(
                                f"[dim]{old_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                                f"[dim]{new_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                            )
                    else:
                        # 第一个块，只显示结尾的上下文
                        start_idx = max(0, equal_len - context_lines)
                        for k in range(start_idx, equal_len):
                            old_line_num = (
                                old_line_map[i1 + k]
                                if i1 + k < len(old_line_map)
                                else i1 + k + 1
                            )
                            new_line_num = (
                                new_line_map[j1 + k]
                                if j1 + k < len(new_line_map)
                                else j1 + k + 1
                            )
                            table.add_row(
                                f"[dim]{old_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                                f"[dim]{new_line_num}[/dim]",
                                f"[dim]{equal_chunk[k]}[/dim]",
                            )
                else:
                    # 如果 equal 块不长，显示所有行
                    for k, line in enumerate(equal_chunk):
                        old_line_num = (
                            old_line_map[i1 + k]
                            if i1 + k < len(old_line_map)
                            else i1 + k + 1
                        )
                        new_line_num = (
                            new_line_map[j1 + k]
                            if j1 + k < len(new_line_map)
                            else j1 + k + 1
                        )
                        table.add_row(
                            f"[dim]{old_line_num}[/dim]",
                            f"[dim]{line}[/dim]",
                            f"[dim]{new_line_num}[/dim]",
                            f"[dim]{line}[/dim]",
                        )
                continue
            elif tag == "replace":
                # 替换：删除的行和新增的行配对显示
                old_chunk = old_lines[i1:i2]
                new_chunk = new_lines[j1:j2]
                deletions += len(old_chunk)
                additions += len(new_chunk)
                has_changes = True

                # 配对显示
                max_len = max(len(old_chunk), len(new_chunk))
                for k in range(max_len):
                    # 文件中的绝对行号
                    if k < len(old_chunk):
                        old_line_num = (
                            old_line_map[i1 + k]
                            if i1 + k < len(old_line_map)
                            else i1 + k + 1
                        )
                        old_line_num = str(old_line_num)
                        old_content = f"[red]{old_chunk[k]}[/red]"
                    else:
                        old_line_num = ""
                        old_content = ""

                    if k < len(new_chunk):
                        new_line_num = (
                            new_line_map[j1 + k]
                            if j1 + k < len(new_line_map)
                            else j1 + k + 1
                        )
                        new_line_num = str(new_line_num)
                        new_content = f"[green]{new_chunk[k]}[/green]"
                    else:
                        new_line_num = ""
                        new_content = ""

                    table.add_row(old_line_num, old_content, new_line_num, new_content)
            elif tag == "delete":
                # 仅删除
                old_chunk = old_lines[i1:i2]
                deletions += len(old_chunk)
                has_changes = True
                for k, line in enumerate(old_chunk):
                    # 文件中的绝对行号
                    old_line_num = (
                        old_line_map[i1 + k]
                        if i1 + k < len(old_line_map)
                        else i1 + k + 1
                    )
                    table.add_row(str(old_line_num), f"[red]{line}[/red]", "", "")
            elif tag == "insert":
                # 仅新增
                new_chunk = new_lines[j1:j2]
                additions += len(new_chunk)
                has_changes = True
                for k, line in enumerate(new_chunk):
                    # 文件中的绝对行号
                    new_line_num = (
                        new_line_map[j1 + k]
                        if j1 + k < len(new_line_map)
                        else j1 + k + 1
                    )
                    table.add_row("", "", str(new_line_num), f"[green]{line}[/green]")

        # 如果没有变更，显示提示
        if not has_changes:
            self.console.print("[dim]（无变更）[/dim]")
            return

        # 构建标题（包含统计信息）
        title = f"📝 {file_path}" if file_path else "Side-by-Side Diff"
        title += f"  [green]+{additions}[/green] / [red]-{deletions}[/red]"

        # 包裹在 Panel 中显示
        panel = Panel(table, title=title, border_style="cyan", padding=(0, 1))
        self.console.print(panel)


def _parse_diff_to_lines(diff_text: str) -> tuple:
    """从 git diff 文本中解析出旧文件和新文件的行列表（带行号信息）

    参数:
        diff_text: git diff 输出的文本

    返回:
        (old_lines, new_lines, old_line_map, new_line_map):
        旧文件行列表、新文件行列表、旧文件行号映射、新文件行号映射
        行号映射是一个列表，索引对应行列表的索引，值是该行在文件中的绝对行号
    """
    old_lines = []
    new_lines = []
    old_line_map = []  # 映射 old_lines 索引到文件中的绝对行号
    new_line_map = []  # 映射 new_lines 索引到文件中的绝对行号

    old_line_num = 0
    new_line_num = 0

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            # 解析 hunk 头，获取起始行号
            parts = line.split("@@")
            if len(parts) >= 2:
                hunk_info = parts[1].strip()
                if hunk_info:
                    for token in hunk_info.split():
                        if token.startswith("-"):
                            try:
                                old_line_num = int(token[1:].split(",")[0])
                            except ValueError:
                                pass
                        elif token.startswith("+"):
                            try:
                                new_line_num = int(token[1:].split(",")[0])
                            except ValueError:
                                pass
            continue
        elif line.startswith("---") or line.startswith("+++"):
            # 跳过文件头
            continue
        elif line.startswith("diff ") or line.startswith("index "):
            # 跳过 diff 元信息
            continue
        elif line.startswith("-"):
            # 删除的行
            old_lines.append(line[1:])
            old_line_map.append(old_line_num)
            old_line_num += 1
        elif line.startswith("+"):
            # 新增的行
            new_lines.append(line[1:])
            new_line_map.append(new_line_num)
            new_line_num += 1
        elif line.startswith(" "):
            # 未更改的行
            old_lines.append(line[1:])
            new_lines.append(line[1:])
            old_line_map.append(old_line_num)
            new_line_map.append(new_line_num)
            old_line_num += 1
            new_line_num += 1
        else:
            # 其他行（如空行）
            old_lines.append(line)
            new_lines.append(line)
            old_line_map.append(old_line_num if old_line_num > 0 else 0)
            new_line_map.append(new_line_num if new_line_num > 0 else 0)

    return old_lines, new_lines, old_line_map, new_line_map


def visualize_diff_enhanced(
    diff_text: str,
    file_path: str = "",
    mode: str = "unified",
    show_line_numbers: bool = True,
    context_lines: int = 3,
) -> None:
    """增强的 diff 可视化函数（便捷接口）

    参数:
        diff_text: git diff 输出的文本
        file_path: 文件路径
        mode: 可视化模式 ("unified" | "syntax" | "compact" | "side_by_side" | "statistics")
        show_line_numbers: 是否显示行号
        context_lines: 上下文行数
    """
    visualizer = DiffVisualizer()

    if mode == "unified":
        visualizer.visualize_unified_diff(
            diff_text,
            file_path,
            show_line_numbers=show_line_numbers,
            context_lines=context_lines,
        )
    elif mode == "syntax":
        visualizer.visualize_syntax_highlighted(diff_text, file_path)
    elif mode == "compact":
        visualizer.visualize_compact(diff_text, file_path)
    elif mode == "side_by_side":
        old_lines, new_lines, old_line_map, new_line_map = _parse_diff_to_lines(
            diff_text
        )
        visualizer.visualize_side_by_side_summary(
            old_lines,
            new_lines,
            file_path,
            context_lines=context_lines,
            old_line_map=old_line_map,
            new_line_map=new_line_map,
        )
    else:
        # 默认使用语法高亮
        visualizer.visualize_syntax_highlighted(diff_text, file_path)
