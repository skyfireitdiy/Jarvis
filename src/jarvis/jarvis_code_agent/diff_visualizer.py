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
            show_header=True,
            header_style="bold magenta",
            box=None,  # 无边框，更简洁
            padding=(0, 1),
        )

        if show_line_numbers:
            table.add_column("旧行号", style="dim red", width=8, justify="right")
            table.add_column("新行号", style="dim green", width=8, justify="right")
        table.add_column("类型", width=4, justify="center")
        table.add_column("内容", style="white", overflow="fold")

        old_line_num = 0
        new_line_num = 0
        in_hunk = False

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
                # Hunk 头部
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
                    if show_line_numbers:
                        table.add_row(
                            str(old_line_num),
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
                    old_line_num += 1
                elif line.startswith("+"):
                    # 新增的行
                    content = line[1:] if len(line) > 1 else ""
                    if show_line_numbers:
                        table.add_row(
                            "",
                            str(new_line_num),
                            "[bold green]+[/bold green]",
                            f"[green]{content}[/green]",
                        )
                    else:
                        table.add_row(
                            "",
                            "[bold green]+[/bold green]",
                            f"[green]{content}[/green]",
                        )
                    new_line_num += 1
                elif line.startswith(" "):
                    # 未更改的行（上下文）
                    content = line[1:] if len(line) > 1 else ""
                    if show_line_numbers:
                        table.add_row(
                            str(old_line_num),
                            str(new_line_num),
                            " ",
                            f"[dim]{content}[/dim]",
                        )
                    else:
                        table.add_row("", " ", f"[dim]{content}[/dim]")
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
        self, old_lines: List[str], new_lines: List[str], file_path: str = ""
    ) -> None:
        """并排显示摘要（仅显示变更部分，智能配对）

        参数:
            old_lines: 旧文件行列表
            new_lines: 新文件行列表
            file_path: 文件路径
        """
        # 使用 difflib.SequenceMatcher 进行更精确的匹配
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        opcodes = matcher.get_opcodes()

        # 创建并排表格
        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=None,
            padding=(0, 1),
        )
        table.add_column("行号", style="dim", width=6, justify="right")
        table.add_column("删除 (-)", style="red", overflow="fold", ratio=1)
        table.add_column("行号", style="dim", width=6, justify="right")
        table.add_column("新增 (+)", style="green", overflow="fold", ratio=1)

        additions = 0
        deletions = 0
        has_changes = False

        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                # 跳过未更改的行（可选：显示省略提示）
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
                    old_line_num = str(i1 + k + 1) if k < len(old_chunk) else ""
                    old_content = (
                        f"[red]{old_chunk[k]}[/red]" if k < len(old_chunk) else ""
                    )
                    new_line_num = str(j1 + k + 1) if k < len(new_chunk) else ""
                    new_content = (
                        f"[green]{new_chunk[k]}[/green]" if k < len(new_chunk) else ""
                    )
                    table.add_row(old_line_num, old_content, new_line_num, new_content)
            elif tag == "delete":
                # 仅删除
                old_chunk = old_lines[i1:i2]
                deletions += len(old_chunk)
                has_changes = True
                for k, line in enumerate(old_chunk):
                    table.add_row(str(i1 + k + 1), f"[red]{line}[/red]", "", "")
            elif tag == "insert":
                # 仅新增
                new_chunk = new_lines[j1:j2]
                additions += len(new_chunk)
                has_changes = True
                for k, line in enumerate(new_chunk):
                    table.add_row("", "", str(j1 + k + 1), f"[green]{line}[/green]")

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
    """从 git diff 文本中解析出旧文件和新文件的行列表

    参数:
        diff_text: git diff 输出的文本

    返回:
        (old_lines, new_lines): 旧文件行列表和新文件行列表
    """
    old_lines = []
    new_lines = []

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            # 跳过 hunk 头
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
        elif line.startswith("+"):
            # 新增的行
            new_lines.append(line[1:])
        elif line.startswith(" "):
            # 未更改的行
            old_lines.append(line[1:])
            new_lines.append(line[1:])
        else:
            # 其他行（如空行）
            old_lines.append(line)
            new_lines.append(line)

    return old_lines, new_lines


def visualize_diff_enhanced(
    diff_text: str,
    file_path: str = "",
    mode: str = "unified",
    show_line_numbers: bool = True,
) -> None:
    """增强的 diff 可视化函数（便捷接口）

    参数:
        diff_text: git diff 输出的文本
        file_path: 文件路径
        mode: 可视化模式 ("unified" | "syntax" | "compact" | "side_by_side" | "statistics")
        show_line_numbers: 是否显示行号
    """
    visualizer = DiffVisualizer()

    if mode == "unified":
        visualizer.visualize_unified_diff(
            diff_text, file_path, show_line_numbers=show_line_numbers
        )
    elif mode == "syntax":
        visualizer.visualize_syntax_highlighted(diff_text, file_path)
    elif mode == "compact":
        visualizer.visualize_compact(diff_text, file_path)
    elif mode == "side_by_side":
        old_lines, new_lines = _parse_diff_to_lines(diff_text)
        visualizer.visualize_side_by_side_summary(old_lines, new_lines, file_path)
    else:
        # 默认使用语法高亮
        visualizer.visualize_syntax_highlighted(diff_text, file_path)
