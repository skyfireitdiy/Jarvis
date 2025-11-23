# -*- coding: utf-8 -*-
"""
Rust 代码优化器：对转译或生成后的 Rust 项目执行若干保守优化步骤。

所有优化步骤均使用 CodeAgent 完成，确保智能、准确且可回退。

目标与策略（保守、可回退）:
1) unsafe 清理：
   - 使用 CodeAgent 识别可移除的 `unsafe { ... }` 包裹，移除后执行 `cargo test` 验证
   - 若必须保留 unsafe，缩小范围并在紧邻位置添加 `/// SAFETY: ...` 文档注释说明理由
2) 代码结构优化（重复代码检测与消除）：
   - 使用 CodeAgent 检测重复函数实现（签名+主体近似或完全相同）
   - 如能安全抽取公共辅助函数进行复用，进行最小化重构以消除重复
   - 若无法安全抽取，在重复处添加 `/// TODO: duplicate of ...` 注释标注
3) 可见性优化（尽可能最小可见性）：
   - 使用 CodeAgent 将 `pub fn` 降为 `pub(crate) fn`（如果函数仅在 crate 内部使用）
   - 保持对外接口（跨 crate 使用的接口，如 lib.rs 中的顶层导出）为 `pub`
4) 文档补充：
   - 使用 CodeAgent 为缺少模块级文档的文件添加 `//! ...` 模块文档注释
   - 为缺少函数文档的公共函数添加 `/// ...` 文档注释（可以是占位注释或简要说明）

实现说明：
- 所有优化步骤均通过 CodeAgent 完成，每个步骤后执行 `cargo test` 进行验证
- 若验证失败，进入构建修复循环（使用 CodeAgent 进行最小修复），直到通过或达到重试上限
- 所有修改保留最小必要的文本变动，失败时自动回滚到快照（git_guard 启用时）
- 结果摘要与日志输出到 <crate_dir>/.jarvis/c2rust/optimize_report.json
- 进度记录（断点续跑）：<crate_dir>/.jarvis/c2rust/optimize_progress.json
  - 字段 processed: 已优化完成的文件（相对 crate 根的路径，posix 斜杠）

限制：
- 依赖 CodeAgent 的智能分析能力，复杂语法与宏、条件编译等情况由 CodeAgent 处理
- 所有优化步骤均通过 `cargo test` 验证，确保修改后代码可正常编译和运行
- 提供 Git 保护（git_guard），失败时自动回滚到快照

使用入口：
- optimize_project(project_root: Optional[Path], crate_dir: Optional[Path], ...) 作为对外简单入口
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable, Set
import fnmatch

import typer

# 引入 CodeAgent（参考 transpiler）
from jarvis.jarvis_code_agent.code_agent import CodeAgent


@dataclass
class OptimizeOptions:
    enable_unsafe_cleanup: bool = True
    enable_structure_opt: bool = True
    enable_visibility_opt: bool = True
    enable_doc_opt: bool = True
    max_checks: int = 0  # 0 表示不限；用于限制 cargo check 次数（防止过慢）
    dry_run: bool = False
    # 大项目分批优化控制
    include_patterns: Optional[str] = None  # 逗号分隔的 glob，相对 crate 根（支持 src/**.rs）
    exclude_patterns: Optional[str] = None  # 逗号分隔的 glob
    max_files: int = 0  # 本次最多处理的文件数（0 不限）
    resume: bool = True  # 断点续跑：跳过已处理文件
    reset_progress: bool = False  # 重置进度（清空 processed 列表）
    build_fix_retries: int = 3  # 构建失败时的修复重试次数
    # Git 保护：优化前快照 commit，失败时自动 reset 回快照
    git_guard: bool = True
    llm_group: Optional[str] = None
    cargo_test_timeout: int = 300  # cargo test 超时（秒）
    non_interactive: bool = True


@dataclass
class OptimizeStats:
    files_scanned: int = 0
    unsafe_removed: int = 0
    unsafe_annotated: int = 0
    duplicates_tagged: int = 0
    visibility_downgraded: int = 0
    docs_added: int = 0
    cargo_checks: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _run_cmd(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None, timeout: Optional[int] = None) -> Tuple[int, str, str]:
    p = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(os.environ, **(env or {})),
    )
    try:
        out, err = p.communicate(timeout=timeout if timeout and timeout > 0 else None)
        return p.returncode, out, err
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        err_msg = f"Command '{' '.join(cmd)}' timed out after {timeout} seconds."
        if err:
            err_msg += f"\n{err}"
        return -1, out, err_msg


def _cargo_check(crate_dir: Path, stats: OptimizeStats, max_checks: int, timeout: Optional[int] = None) -> Tuple[bool, str]:
    # 统一使用 cargo test 作为验证手段
    if max_checks and stats.cargo_checks >= max_checks:
        return False, "cargo test budget exhausted"
    code, out, err = _run_cmd(["cargo", "test", "-q"], crate_dir, timeout=timeout)
    stats.cargo_checks += 1
    ok = code == 0
    diag = err.strip() or out.strip()
    # 取首行作为摘要
    first_line = next((ln for ln in diag.splitlines() if ln.strip()), "")
    return ok, first_line

def _run_cargo_fmt(crate_dir: Path) -> None:
    """
    执行 cargo fmt 格式化代码。
    fmt 失败不影响主流程，只记录警告。
    """
    try:
        res = subprocess.run(
            ["cargo", "fmt"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        if res.returncode == 0:
            typer.secho("[c2rust-optimizer][fmt] 代码格式化完成", fg=typer.colors.CYAN)
        else:
            # fmt 失败不影响主流程，只记录警告
            typer.secho(f"[c2rust-optimizer][fmt] 代码格式化失败（非致命）: {res.stderr or res.stdout}", fg=typer.colors.YELLOW)
    except Exception as e:
        # fmt 失败不影响主流程，只记录警告
        typer.secho(f"[c2rust-optimizer][fmt] 代码格式化异常（非致命）: {e}", fg=typer.colors.YELLOW)

def _run_cargo_clippy_fix(crate_dir: Path) -> None:
    """
    执行 cargo clippy --fix 自动修复代码。
    clippy 修复失败不影响主流程，只记录警告。
    """
    try:
        res = subprocess.run(
            ["cargo", "clippy", "--fix", "--allow-dirty", "--allow-staged"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        if res.returncode == 0:
            typer.secho("[c2rust-optimizer][clippy] Clippy 自动修复完成", fg=typer.colors.CYAN)
        else:
            # clippy 修复失败不影响主流程，只记录警告
            # clippy 可能返回非零退出码（如果有无法自动修复的问题），这是正常的
            output = (res.stderr or res.stdout or "").strip()
            if output:
                typer.secho(f"[c2rust-optimizer][clippy] Clippy 自动修复完成（可能有无法自动修复的问题）: {output[:200]}", fg=typer.colors.YELLOW)
            else:
                typer.secho("[c2rust-optimizer][clippy] Clippy 自动修复完成（可能有无法自动修复的问题）", fg=typer.colors.YELLOW)
    except Exception as e:
        # clippy 修复失败不影响主流程，只记录警告
        typer.secho(f"[c2rust-optimizer][clippy] Clippy 自动修复异常（非致命）: {e}", fg=typer.colors.YELLOW)

def _check_clippy_warnings(crate_dir: Path) -> Tuple[bool, str]:
    """
    检查是否有 clippy 告警。
    返回 (has_warnings, output)，has_warnings 为 True 表示有告警。
    """
    try:
        res = subprocess.run(
            ["cargo", "clippy", "--", "-W", "clippy::all"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        # clippy 的输出通常在 stderr，但也要检查 stdout
        stderr_output = (res.stderr or "").strip()
        stdout_output = (res.stdout or "").strip()
        output = (stderr_output + "\n" + stdout_output).strip() if (stderr_output and stdout_output) else (stderr_output or stdout_output or "").strip()
        
        # 检测告警的多种方式：
        # 1. 检查是否有 "warning:" 关键字（clippy 告警的标准格式）
        # 2. 检查是否有 "clippy::" 关键字（clippy 特定的告警类型）
        # 3. 检查是否有 "warn(" 关键字（某些告警格式）
        # 4. 检查返回码（clippy 有告警时通常返回非零，但某些情况下可能返回 0）
        output_lower = output.lower()
        has_warning_keyword = "warning:" in output_lower or "warn(" in output_lower
        has_clippy_keyword = "clippy::" in output_lower
        has_nonzero_exit = res.returncode != 0
        
        # 如果有告警关键字，或者（返回码非零且包含 clippy 关键字），则认为有告警
        has_warnings = has_warning_keyword or (has_nonzero_exit and has_clippy_keyword)
        
        # 调试输出：如果检测到告警，输出一些调试信息
        if has_warnings:
            typer.secho(f"[c2rust-optimizer][clippy-check] 检测到 Clippy 告警（返回码={res.returncode}，输出长度={len(output)}）", fg=typer.colors.YELLOW)
        else:
            # 如果返回码非零但没有检测到告警关键字，可能是编译错误，输出调试信息
            if has_nonzero_exit:
                typer.secho(f"[c2rust-optimizer][clippy-check] Clippy 返回非零退出码（{res.returncode}），但未检测到告警关键字，可能是编译错误", fg=typer.colors.CYAN)
                typer.secho(f"[c2rust-optimizer][clippy-check] 输出预览（前200字符）: {output[:200]}", fg=typer.colors.CYAN)
        
        return has_warnings, output
    except Exception as e:
        # 检查失败时假设没有告警，避免阻塞流程
        typer.secho(f"[c2rust-optimizer][clippy-check] 检查 Clippy 告警异常（非致命）: {e}", fg=typer.colors.YELLOW)
        return False, ""

def _cargo_check_full(crate_dir: Path, stats: OptimizeStats, max_checks: int, timeout: Optional[int] = None) -> Tuple[bool, str]:
    """
    执行 cargo test，返回是否成功与完整输出（stdout+stderr）。
    会计入 stats.cargo_checks，并受 max_checks 预算限制。
    """
    if max_checks and stats.cargo_checks >= max_checks:
        return False, "cargo test budget exhausted"
    try:
        res = subprocess.run(
            ["cargo", "test", "-q"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
            timeout=timeout if timeout and timeout > 0 else None,
        )
        stats.cargo_checks += 1
        ok = (res.returncode == 0)
        out = (res.stdout or "")
        err = (res.stderr or "")
        msg = (out + ("\n" + err if err else "")).strip()
        return ok, msg
    except subprocess.TimeoutExpired as e:
        stats.cargo_checks += 1
        out_s = e.stdout.decode("utf-8", errors="ignore") if e.stdout else ""
        err_s = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
        msg = f"cargo test timed out after {timeout} seconds"
        full_output = (out_s + ("\n" + err_s if err_s else "")).strip()
        if full_output:
            msg += f"\nOutput:\n{full_output}"
        return False, msg
    except Exception as e:
        stats.cargo_checks += 1
        return False, f"cargo test exception: {e}"

def _git_is_repo(root: Path) -> bool:
    try:
        code, out, err = _run_cmd(["git", "rev-parse", "--is-inside-work-tree"], root)
        return code == 0 and (out.strip() == "true" or (not out.strip() and "true" in (err or "")))
    except Exception:
        return False

def _git_toplevel(start: Path) -> Optional[Path]:
    """
    返回包含 start 的 Git 仓库根目录（--show-toplevel）。若不在仓库中则返回 None。
    """
    try:
        code, out, err = _run_cmd(["git", "rev-parse", "--show-toplevel"], start)
        if code == 0:
            p = (out or "").strip()
            if p:
                return Path(p)
        return None
    except Exception:
        return None

def _git_head_commit(root: Path) -> Optional[str]:
    try:
        code, out, err = _run_cmd(["git", "rev-parse", "--verify", "HEAD"], root)
        if code == 0:
            return out.strip()
        return None
    except Exception:
        return None

def _git_reset_hard(root: Path, commit: str) -> bool:
    try:
        code, _, _ = _run_cmd(["git", "reset", "--hard", commit], root)
        if code != 0:
            return False
        return True
    except Exception:
        return False


def _iter_rust_files(crate_dir: Path) -> Iterable[Path]:
    src = crate_dir / "src"
    if not src.exists():
        # 仍尝试遍历整个 crate 目录，但优先 src
        yield from crate_dir.rglob("*.rs")
        return
    # 遍历 src 优先
    yield from src.rglob("*.rs")


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _backup_file(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak_opt")
    shutil.copy2(path, bak)
    return bak


def _restore_file_from_backup(path: Path, backup: Path) -> None:
    shutil.move(str(backup), str(path))


def _remove_backup(backup: Path) -> None:
    if backup.exists():
        backup.unlink(missing_ok=True)


def _ensure_report_dir(crate_dir: Path) -> Path:
    report_dir = crate_dir / ".jarvis" / "c2rust"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _find_project_root() -> Optional[Path]:
    """
    查找项目根目录（包含 .jarvis/c2rust 的目录）。
    从当前目录向上查找，最多向上查找 5 层。
    """
    from jarvis.jarvis_c2rust.constants import C2RUST_DIRNAME
    cwd = Path(".").resolve()
    current = cwd
    for _ in range(5):
        if current and current.exists():
            jarvis_dir = current / C2RUST_DIRNAME
            if jarvis_dir.exists() and jarvis_dir.is_dir():
                return current
            parent = current.parent
            if parent == current:  # 已到达根目录
                break
            current = parent
    return None


def detect_crate_dir(preferred: Optional[Path]) -> Path:
    """
    选择 crate 目录策略：
    - 若提供 preferred 且包含 Cargo.toml，则使用
    - 否则：尝试从项目根目录推断（查找包含 .jarvis/c2rust 的目录）
    - 否则：优先 <cwd>/<cwd.name>_rs；若存在 Cargo.toml 则用之
    - 否则：在当前目录下递归寻找第一个包含 Cargo.toml 的目录
    - 若失败：若当前目录有 Cargo.toml 则返回当前目录，否则抛错
    """
    if preferred:
        preferred = preferred.resolve()
        if (preferred / "Cargo.toml").exists():
            return preferred

    # 尝试从项目根目录推断 crate 目录
    project_root = _find_project_root()
    if project_root:
        # 策略1: project_root 的父目录下的 <project_root.name>_rs
        candidate1 = project_root.parent / f"{project_root.name}_rs"
        if (candidate1 / "Cargo.toml").exists():
            return candidate1
        # 策略2: project_root 本身（如果包含 Cargo.toml）
        if (project_root / "Cargo.toml").exists():
            return project_root
        # 策略3: project_root 下的子目录中包含 Cargo.toml 的
        for d in project_root.iterdir():
            if d.is_dir() and (d / "Cargo.toml").exists():
                return d

    cwd = Path(".").resolve()
    candidate = cwd / f"{cwd.name}_rs"
    if (candidate / "Cargo.toml").exists():
        return candidate

    # 搜索第一个包含 Cargo.toml 的目录（限制深度2以避免过慢）
    for p in [cwd] + [d for d in cwd.iterdir() if d.is_dir()]:
        if (p / "Cargo.toml").exists():
            return p

    if (cwd / "Cargo.toml").exists():
        return cwd
    raise FileNotFoundError("未找到 Cargo.toml，对应 crate 目录无法确定。")


class Optimizer:
    def __init__(self, crate_dir: Path, options: OptimizeOptions, project_root: Optional[Path] = None):
        self.crate_dir = crate_dir
        self.project_root = project_root if project_root else crate_dir.parent  # 默认使用 crate_dir 的父目录
        self.options = options
        self.stats = OptimizeStats()
        # 进度文件
        self.report_dir = _ensure_report_dir(self.crate_dir)
        self.progress_path = self.report_dir / "optimize_progress.json"
        self.processed: Set[str] = set()
        self.steps_completed: Set[str] = set()  # 已完成的步骤集合
        self._step_commits: Dict[str, str] = {}  # 每个步骤的 commit id
        self._target_files: List[Path] = []
        self._load_or_reset_progress()
        self._last_snapshot_commit: Optional[str] = None
        # 读取附加说明
        self.additional_notes = self._load_additional_notes()

    def _load_additional_notes(self) -> str:
        """从配置文件加载附加说明"""
        try:
            from jarvis.jarvis_c2rust.constants import CONFIG_JSON
            # 尝试从项目根目录读取配置（crate_dir 的父目录或同级目录）
            # 首先尝试 crate_dir 的父目录
            project_root = self.crate_dir.parent
            config_path = project_root / ".jarvis" / "c2rust" / CONFIG_JSON
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = json.load(f)
                    if isinstance(config, dict):
                        return str(config.get("additional_notes", "") or "").strip()
            # 如果父目录没有，尝试当前目录
            config_path = self.crate_dir / ".jarvis" / "c2rust" / CONFIG_JSON
            if config_path.exists():
                with config_path.open("r", encoding="utf-8") as f:
                    config = json.load(f)
                    if isinstance(config, dict):
                        return str(config.get("additional_notes", "") or "").strip()
        except Exception:
            pass
        return ""

    def _append_additional_notes(self, prompt: str) -> str:
        """
        在提示词末尾追加附加说明（如果存在）。
        
        Args:
            prompt: 原始提示词
            
        Returns:
            追加了附加说明的提示词
        """
        if self.additional_notes and self.additional_notes.strip():
            return prompt + "\n\n" + "【附加说明（用户自定义）】\n" + self.additional_notes.strip()
        return prompt

    def _snapshot_commit(self) -> None:
        """
        在启用 git_guard 时记录当前 HEAD commit（仅记录，不提交未暂存更改）。
        统一在仓库根目录执行 git 命令，避免子目录导致的意外。
        """
        if not self.options.git_guard:
            return
        try:
            repo_root = _git_toplevel(self.crate_dir)
            if repo_root is None:
                return
            head = _git_head_commit(repo_root)
            if head:
                self._last_snapshot_commit = head
        except Exception:
            # 忽略快照失败，不阻塞流程
            pass

    def _reset_to_snapshot(self) -> bool:
        """
        在启用 git_guard 且存在快照时，将工作区 reset --hard 回快照。
        统一在仓库根目录执行 git 命令，避免子目录导致的意外。
        返回是否成功执行 reset。
        """
        if not self.options.git_guard:
            return False
        snap = getattr(self, "_last_snapshot_commit", None)
        if not snap:
            return False
        repo_root = _git_toplevel(self.crate_dir)
        if repo_root is None:
            return False
        ok = _git_reset_hard(repo_root, snap)
        return ok

    # ---------- 进度管理与文件选择 ----------

    def _load_or_reset_progress(self) -> None:
        if self.options.reset_progress:
            try:
                self.progress_path.write_text(json.dumps({"processed": [], "steps_completed": []}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            self.processed = set()
            self.steps_completed: Set[str] = set()
            self._step_commits = {}
            return
        try:
            if self.progress_path.exists():
                obj = json.loads(self.progress_path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    arr = obj.get("processed") or []
                    if isinstance(arr, list):
                        self.processed = {str(x) for x in arr if isinstance(x, str)}
                    else:
                        self.processed = set()
                    # 加载已完成的步骤
                    steps = obj.get("steps_completed") or []
                    if isinstance(steps, list):
                        self.steps_completed = {str(x) for x in steps if isinstance(x, str)}
                    else:
                        self.steps_completed = set()
                    # 加载步骤的 commit id
                    step_commits = obj.get("step_commits") or {}
                    if isinstance(step_commits, dict):
                        self._step_commits = {str(k): str(v) for k, v in step_commits.items() if isinstance(k, str) and isinstance(v, str)}
                    else:
                        self._step_commits = {}
                    
                    # 恢复时，reset 到最后一个步骤的 commit id
                    if self.options.resume and self._step_commits:
                        last_commit = None
                        # 按照步骤顺序找到最后一个已完成步骤的 commit
                        step_order = ["clippy_elimination", "unsafe_cleanup", "structure_opt", "visibility_opt", "doc_opt"]
                        for step in reversed(step_order):
                            if step in self.steps_completed and step in self._step_commits:
                                last_commit = self._step_commits[step]
                                break
                        
                        if last_commit:
                            current_commit = self._get_crate_commit_hash()
                            if current_commit != last_commit:
                                typer.secho(f"[c2rust-optimizer][resume] 检测到代码状态不一致，正在 reset 到最后一个步骤的 commit: {last_commit}", fg=typer.colors.YELLOW)
                                if self._reset_to_commit(last_commit):
                                    typer.secho(f"[c2rust-optimizer][resume] 已 reset 到 commit: {last_commit}", fg=typer.colors.GREEN)
                                else:
                                    typer.secho(f"[c2rust-optimizer][resume] reset 失败，继续使用当前代码状态", fg=typer.colors.YELLOW)
                            else:
                                typer.secho(f"[c2rust-optimizer][resume] 代码状态一致，无需 reset", fg=typer.colors.CYAN)
                else:
                    self.processed = set()
                    self.steps_completed = set()
                    self._step_commits = {}
            else:
                self.processed = set()
                self.steps_completed = set()
                self._step_commits = {}
        except Exception:
            self.processed = set()
            self.steps_completed = set()
            self._step_commits = {}

    def _get_crate_commit_hash(self) -> Optional[str]:
        """获取 crate 目录的当前 commit id"""
        try:
            repo_root = _git_toplevel(self.crate_dir)
            if repo_root is None:
                return None
            return _git_head_commit(repo_root)
        except Exception:
            return None

    def _reset_to_commit(self, commit_hash: str) -> bool:
        """回退 crate 目录到指定的 commit"""
        try:
            repo_root = _git_toplevel(self.crate_dir)
            if repo_root is None:
                return False
            return _git_reset_hard(repo_root, commit_hash)
        except Exception:
            return False

    def _save_progress_for_batch(self, files: List[Path]) -> None:
        """保存文件处理进度"""
        try:
            rels = []
            for p in files:
                try:
                    rel = p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                except Exception:
                    rel = str(p)
                rels.append(rel)
            self.processed.update(rels)
            
            # 获取当前 commit id 并记录
            current_commit = self._get_crate_commit_hash()
            
            data = {
                "processed": sorted(self.processed),
                "steps_completed": sorted(self.steps_completed)
            }
            if current_commit:
                data["last_commit"] = current_commit
                typer.secho(f"[c2rust-optimizer][progress] 已记录当前 commit: {current_commit}", fg=typer.colors.CYAN)
            
            self.progress_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_step_progress(self, step_name: str, files: List[Path]) -> None:
        """保存步骤进度：标记步骤完成并更新文件列表"""
        try:
            # 标记步骤为已完成
            self.steps_completed.add(step_name)
            # 更新已处理的文件列表
            rels = []
            for p in files:
                try:
                    rel = p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                except Exception:
                    rel = str(p)
                rels.append(rel)
            self.processed.update(rels)
            
            # 获取当前 commit id 并记录
            current_commit = self._get_crate_commit_hash()
            
            # 保存进度
            data = {
                "processed": sorted(self.processed),
                "steps_completed": sorted(self.steps_completed)
            }
            if current_commit:
                # 记录每个步骤的 commit id
                step_commits = getattr(self, "_step_commits", {})
                step_commits[step_name] = current_commit
                self._step_commits = step_commits
                data["step_commits"] = step_commits
                data["last_commit"] = current_commit
                typer.secho(f"[c2rust-optimizer][progress] 已记录步骤 '{step_name}' 的 commit: {current_commit}", fg=typer.colors.CYAN)
            
            self.progress_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            typer.secho(f"[c2rust-optimizer] 步骤 '{step_name}' 进度已保存", fg=typer.colors.CYAN)
        except Exception as e:
            typer.secho(f"[c2rust-optimizer] 保存步骤进度失败（非致命）: {e}", fg=typer.colors.YELLOW)

    def _parse_patterns(self, s: Optional[str]) -> List[str]:
        if not s or not isinstance(s, str):
            return []
        parts = [x.strip() for x in s.replace("\n", ",").split(",")]
        return [x for x in parts if x]

    def _match_any(self, rel: str, patterns: List[str]) -> bool:
        if not patterns:
            return False
        return any(fnmatch.fnmatch(rel, pat) for pat in patterns)

    def _compute_target_files(self) -> List[Path]:
        include = self._parse_patterns(self.options.include_patterns)
        exclude = self._parse_patterns(self.options.exclude_patterns)
        maxn = int(self.options.max_files or 0)
        take: List[Path] = []
        for p in sorted(_iter_rust_files(self.crate_dir), key=lambda x: x.as_posix()):
            try:
                rel = p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
            except Exception:
                rel = p.as_posix()
            # include 过滤（若提供，则必须命中其一）
            if include and not self._match_any(rel, include):
                continue
            # exclude 过滤
            if exclude and self._match_any(rel, exclude):
                continue
            # resume：跳过已处理文件
            if self.options.resume and rel in self.processed:
                continue
            take.append(p)
            if maxn > 0 and len(take) >= maxn:
                break
        self._target_files = take
        return take

    # ---------- 主运行入口 ----------

    def run(self) -> OptimizeStats:
        report_path = self.report_dir / "optimize_report.json"
        typer.secho(f"[c2rust-optimizer][start] 开始优化 Crate: {self.crate_dir}", fg=typer.colors.BLUE)
        try:
            # 计算本次批次的目标文件列表（按 include/exclude/resume/max_files）
            targets = self._compute_target_files()
            if not targets:
                # 无文件可处理：仍然写出报告并返回
                typer.secho("[c2rust-optimizer] 根据当前选项，无新文件需要处理。", fg=typer.colors.CYAN)
                pass
            else:
                typer.secho(f"[c2rust-optimizer] 本次批次发现 {len(targets)} 个待处理文件。", fg=typer.colors.BLUE)
                # 批次开始前记录快照
                self._snapshot_commit()

                # 优化前先执行 clippy 自动修复
                if not self.options.dry_run:
                    typer.secho("[c2rust-optimizer] 优化前执行 Clippy 自动修复...", fg=typer.colors.CYAN)
                    _run_cargo_clippy_fix(self.crate_dir)

                # 检查是否有 clippy 告警，如果有则使用 CodeAgent 消除
                if not self.options.dry_run:
                    typer.secho("[c2rust-optimizer] 检查 Clippy 告警...", fg=typer.colors.CYAN)
                    has_warnings, clippy_output = _check_clippy_warnings(self.crate_dir)
                    if has_warnings:
                        typer.secho(f"\n[c2rust-optimizer] 第 0 步：消除 Clippy 告警", fg=typer.colors.MAGENTA)
                        self._snapshot_commit()
                        self._codeagent_eliminate_clippy_warnings(targets, clippy_output)
                        # 验证修复后是否还有告警
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after clippy_elimination failed: {first}")
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats
                        # 再次检查是否还有告警
                        has_warnings_after, _ = _check_clippy_warnings(self.crate_dir)
                        if not has_warnings_after:
                            typer.secho("[c2rust-optimizer] Clippy 告警已全部消除", fg=typer.colors.GREEN)
                        else:
                            typer.secho("[c2rust-optimizer] 仍有部分 Clippy 告警无法自动消除", fg=typer.colors.YELLOW)
                        # 保存步骤进度
                        self._save_step_progress("clippy_elimination", targets)
                    else:
                        typer.secho("[c2rust-optimizer] 未发现 Clippy 告警，跳过消除步骤", fg=typer.colors.CYAN)

                # 所有优化步骤都使用 CodeAgent
                step_num = 1
                
                if self.options.enable_unsafe_cleanup:
                    typer.secho(f"\n[c2rust-optimizer] 第 {step_num} 步：unsafe 清理", fg=typer.colors.MAGENTA)
                    self._snapshot_commit()
                    if not self.options.dry_run:
                        self._codeagent_opt_unsafe_cleanup(targets)
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after unsafe_cleanup failed: {first}")
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats
                        # 保存步骤进度
                        self._save_step_progress("unsafe_cleanup", targets)
                    step_num += 1

                if self.options.enable_structure_opt:
                    typer.secho(f"\n[c2rust-optimizer] 第 {step_num} 步：结构优化 (重复代码检测)", fg=typer.colors.MAGENTA)
                    self._snapshot_commit()
                    if not self.options.dry_run:
                        self._codeagent_opt_structure_duplicates(targets)
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after structure_opt failed: {first}")
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats
                        # 保存步骤进度
                        self._save_step_progress("structure_opt", targets)
                    step_num += 1

                if self.options.enable_visibility_opt:
                    typer.secho(f"\n[c2rust-optimizer] 第 {step_num} 步：可见性优化", fg=typer.colors.MAGENTA)
                    self._snapshot_commit()
                    if not self.options.dry_run:
                        self._codeagent_opt_visibility(targets)
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after visibility_opt failed: {first}")
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats
                        # 保存步骤进度
                        self._save_step_progress("visibility_opt", targets)
                    step_num += 1

                if self.options.enable_doc_opt:
                    typer.secho(f"\n[c2rust-optimizer] 第 {step_num} 步：文档补充", fg=typer.colors.MAGENTA)
                    self._snapshot_commit()
                    if not self.options.dry_run:
                        self._codeagent_opt_docs(targets)
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after doc_opt failed: {first}")
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats
                        # 保存步骤进度
                        self._save_step_progress("doc_opt", targets)
                    step_num += 1

                # 最终保存进度（确保所有步骤的进度都已记录）
                self._save_progress_for_batch(targets)

        except Exception as e:
            self.stats.errors.append(f"fatal: {e}")
        finally:
            # 写出简要报告
            # 尝试显示相对路径，优先相对于 project_root，然后相对于 crate_dir，最后显示绝对路径
            try:
                report_display = str(report_path.relative_to(self.project_root))
            except ValueError:
                try:
                    report_display = str(report_path.relative_to(self.crate_dir))
                except ValueError:
                    try:
                        report_display = str(report_path.relative_to(Path.cwd()))
                    except ValueError:
                        # 如果都不行，显示绝对路径
                        report_display = str(report_path)
            typer.secho(f"[c2rust-optimizer] 优化流程结束。报告已生成于: {report_display}", fg=typer.colors.GREEN)
            try:
                _write_file(report_path, json.dumps(asdict(self.stats), ensure_ascii=False, indent=2))
            except Exception:
                pass
        return self.stats

    # ========== 0) clippy warnings elimination (CodeAgent) ==========

    def _codeagent_eliminate_clippy_warnings(self, target_files: List[Path], clippy_output: str) -> None:
        """
        使用 CodeAgent 消除 clippy 告警。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下消除 Clippy 告警，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次修复仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) 消除 Clippy 告警：",
            "   - 根据以下 Clippy 告警信息，修复所有可以修复的告警；",
            "   - 对于无法自动修复的告警，请根据 Clippy 的建议进行手动修复；",
            "   - 如果某些告警确实需要保留（如性能优化相关的告警），可以添加 `#[allow(clippy::...)]` 注释，但需要说明理由。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与消除告警无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo clippy -- -W clippy::all` 进行验证；",
            "若仍有告警，请继续输出新的补丁进行修复并再次自检，直至所有告警消除或无法进一步修复为止。",
            "",
            "Clippy 告警信息如下：",
            "<CLIPPY_WARNINGS>",
            clippy_output,
            "</CLIPPY_WARNINGS>",
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent][clippy] 正在调用 CodeAgent 消除 Clippy 告警...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][clippy]", suffix="")
        finally:
            os.chdir(prev_cwd)

    # ========== 1) unsafe cleanup (CodeAgent) ==========

    def _codeagent_opt_unsafe_cleanup(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行 unsafe 清理优化。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行 unsafe 清理优化，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) unsafe 清理：",
            "   - 识别并移除不必要的 `unsafe { ... }` 包裹；",
            "   - 若必须使用 unsafe，缩小 unsafe 块的范围，并在紧邻位置添加 `/// SAFETY: ...` 文档注释说明理由；",
            "   - 对于无法移除的 unsafe，添加详细的 SAFETY 注释说明为什么需要 unsafe。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与 unsafe 清理无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。"
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent][unsafe-cleanup] 正在调用 CodeAgent 进行 unsafe 清理...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][unsafe-cleanup]", suffix="")
        finally:
            os.chdir(prev_cwd)

    # ========== 2) structure duplicates (CodeAgent) ==========

    def _codeagent_opt_structure_duplicates(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行结构优化（重复代码检测与消除）。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行代码结构优化（重复代码检测与消除），并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) 重复代码检测与消除：",
            "   - 检测重复函数实现（签名+主体近似或完全相同）；",
            "   - 如能安全抽取公共辅助函数进行复用，进行最小化重构以消除重复；",
            "   - 若无法安全抽取（如涉及复杂上下文依赖），在重复处添加 `/// TODO: duplicate of <file>::<function>` 注释标注。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与重复代码消除无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。"
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent][structure] 正在调用 CodeAgent 进行结构优化...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][structure]", suffix="")
        finally:
            os.chdir(prev_cwd)

    # ========== 3) visibility optimization (CodeAgent) ==========

    def _codeagent_opt_visibility(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行可见性优化。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行可见性优化，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) 可见性最小化：",
            "   - 优先将 `pub fn` 降为 `pub(crate) fn`（如果函数仅在 crate 内部使用）；",
            "   - 保持对外接口（跨 crate 使用的接口，如 lib.rs 中的顶层导出）为 `pub`；",
            "   - 在 lib.rs 中的顶层导出保持现状，不要修改。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与可见性优化无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。"
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent][visibility] 正在调用 CodeAgent 进行可见性优化...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][visibility]", suffix="")
        finally:
            os.chdir(prev_cwd)

    # ========== 4) doc augmentation (CodeAgent) ==========

    def _codeagent_opt_docs(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行文档补充。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)
            self.stats.files_scanned += 1

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行文档补充优化，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标：",
            "1) 文档补充：",
            "   - 为缺少模块级文档的文件添加 `//! ...` 模块文档注释（放在文件开头）；",
            "   - 为缺少函数文档的公共函数（pub 或 pub(crate)）添加 `/// ...` 文档注释；",
            "   - 文档内容可以是占位注释（如 `//! TODO: Add module-level documentation` 或 `/// TODO: Add documentation`），也可以根据函数签名和实现提供简要说明。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与文档补充无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。"
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent][doc] 正在调用 CodeAgent 进行文档补充...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][doc]", suffix="")
        finally:
            os.chdir(prev_cwd)

    # ========== 5) CodeAgent 整体优化（可选，综合优化） ==========

    def _codeagent_optimize_crate(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 对 crate 进行一次保守的整体优化，输出补丁并进行一次 cargo check 验证。
        仅限本批次的目标文件（target_files）范围内进行修改，以支持大项目分批优化。
        包含：
        - unsafe 清理与 SAFETY 注释补充（范围最小化）
        - 重复代码最小消除（允许抽取公共辅助函数），或添加 TODO 标注
        - 可见性最小化（尽量使用 pub(crate)，保持对外接口为 pub）
        - 文档补充（模块/函数缺失文档添加占位）
        约束：
        - 保持最小改动，避免大范围重构或格式化
        - 不得删除公开 API；跨 crate 接口保持 pub
        - 仅在 crate_dir 下进行修改（Cargo.toml、src/**/*.rs）；不得改动其他目录
        - 仅输出补丁（由 CodeAgent 控制），不输出解释
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        crate = self.crate_dir.resolve()
        file_list: List[str] = []
        for p in target_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            file_list.append(rel)

        prompt_lines: List[str] = [
            "你是资深 Rust 代码工程师。请在当前 crate 下执行一次保守的整体优化，并以补丁形式输出修改：",
            f"- crate 根目录：{crate}",
            "",
            "本次优化仅允许修改以下文件范围（严格限制）：",
            *[f"- {rel}" for rel in file_list],
            "",
            "优化目标（按优先级）：",
            "1) unsafe 清理：",
            "   - 移除不必要的 unsafe 包裹；若必须使用 unsafe，缩小范围并在紧邻位置添加 `/// SAFETY: ...` 文档注释说明理由。",
            "2) 代码结构优化（重复消除/提示）：",
            "   - 检测重复函数实现（签名+主体近似），如能安全抽取公共辅助函数进行复用，进行最小化重构；否则在重复处添加 `/// TODO: duplicate of ...` 注释。",
            "3) 可见性优化：",
            "   - 优先将 `pub fn` 降为 `pub(crate) fn`；保持对外接口（跨 crate 使用的接口）为 `pub`；在 lib.rs 中的顶层导出保持现状。",
            "4) 文档补充：",
            "   - 为缺少模块/函数文档的位置添加占位注释（//! 或 ///）。",
            "",
            "约束与范围：",
            "- 仅修改上述列出的文件；除非必须（如修复引用路径），否则不要修改其他文件。",
            "- 保持最小改动，不要进行与上述优化无关的重构或格式化。",
            "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
            "- 输出仅为补丁，不要输出解释或多余文本。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。"
        ]
        prompt = "\n".join(prompt_lines)
        prompt = self._append_additional_notes(prompt)
        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        typer.secho("[c2rust-optimizer][codeagent] 正在调用 CodeAgent 进行整体优化...", fg=typer.colors.CYAN)
        try:
            os.chdir(str(crate))
            # 修复前执行 cargo fmt
            _run_cargo_fmt(crate)
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent]", suffix="")
        finally:
            os.chdir(prev_cwd)
        # 运行一次 cargo check 验证；若失败则进入本地最小修复循环
        ok, diag = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
        if not ok:
            fixed = self._build_fix_loop(target_files)
            if not fixed:
                first = (diag.splitlines()[0] if isinstance(diag, str) and diag else "failed")
                self.stats.errors.append(f"codeagent test failed: {first}")
                try:
                    self._reset_to_snapshot()
                finally:
                    return

    def _build_fix_loop(self, scope_files: List[Path]) -> bool:
        """
        循环执行 cargo check 并用 CodeAgent 进行最小修复，直到通过或达到重试上限或检查预算耗尽。
        仅允许（优先）修改 scope_files（除非确有必要），以支持分批优化。
        返回 True 表示修复成功构建通过；False 表示未能在限制内修复。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        """
        maxr = int(self.options.build_fix_retries or 0)
        if maxr <= 0:
            return False
        crate = self.crate_dir.resolve()
        allowed: List[str] = []
        for p in scope_files:
            try:
                rel = p.resolve().relative_to(crate).as_posix()
            except Exception:
                rel = p.as_posix()
            allowed.append(rel)

        attempt = 0
        while True:
            # 检查预算
            if self.options.max_checks and self.stats.cargo_checks >= self.options.max_checks:
                return False
            # 执行构建
            output = ""
            try:
                res = subprocess.run(
                    ["cargo", "test", "-q"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=str(crate),
                    timeout=self.options.cargo_test_timeout if self.options.cargo_test_timeout > 0 else None,
                )
                self.stats.cargo_checks += 1
                if res.returncode == 0:
                    typer.secho("[c2rust-optimizer][build-fix] 构建修复成功。", fg=typer.colors.GREEN)
                    return True
                output = ((res.stdout or "") + ("\n" + (res.stderr or ""))).strip()
            except subprocess.TimeoutExpired as e:
                self.stats.cargo_checks += 1
                out_s = e.stdout.decode("utf-8", errors="ignore") if e.stdout else ""
                err_s = e.stderr.decode("utf-8", errors="ignore") if e.stderr else ""
                output = f"cargo test timed out after {self.options.cargo_test_timeout} seconds"
                full_output = (out_s + ("\n" + err_s if err_s else "")).strip()
                if full_output:
                    output += f"\nOutput:\n{full_output}"
            except Exception as e:
                self.stats.cargo_checks += 1
                output = f"cargo test exception: {e}"

            # 达到重试上限则失败
            attempt += 1
            if attempt > maxr:
                typer.secho("[c2rust-optimizer][build-fix] 构建修复重试次数已用尽。", fg=typer.colors.RED)
                return False

            typer.secho(f"[c2rust-optimizer][build-fix] 构建失败。正在尝试使用 CodeAgent 进行修复 (第 {attempt}/{maxr} 次尝试)...", fg=typer.colors.YELLOW)
            # 生成最小修复提示
            prompt_lines = [
                "请根据以下测试/构建错误对 crate 进行最小必要的修复以通过 `cargo test`：",
                f"- crate 根目录：{crate}",
                "",
                "本次修复优先且仅允许修改以下文件（除非确有必要，否则不要修改范围外文件）：",
                *[f"- {rel}" for rel in allowed],
                "",
                "约束与范围：",
                "- 保持最小改动，不要进行与错误无关的重构或格式化；",
                "- 仅输出补丁，不要输出解释或多余文本。",
                "",
                "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                "",
                "构建错误如下：",
                "<BUILD_ERROR>",
                output,
                "</BUILD_ERROR>",
            ]
            prompt = "\n".join(prompt_lines)
            prompt = self._append_additional_notes(prompt)
            # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(crate))
                # 修复前执行 cargo fmt
                _run_cargo_fmt(crate)
                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
                agent.run(prompt, prefix=f"[c2rust-optimizer][build-fix iter={attempt}]", suffix="")
            finally:
                os.chdir(prev_cwd)

        return False

def optimize_project(
    project_root: Optional[Path] = None,
    crate_dir: Optional[Path] = None,
    enable_unsafe_cleanup: bool = True,
    enable_structure_opt: bool = True,
    enable_visibility_opt: bool = True,
    enable_doc_opt: bool = True,
    max_checks: int = 0,
    dry_run: bool = False,
    include_patterns: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    max_files: int = 0,
    resume: bool = True,
    reset_progress: bool = False,
    build_fix_retries: int = 3,
    git_guard: bool = True,
    llm_group: Optional[str] = None,
    cargo_test_timeout: int = 300,
    non_interactive: bool = True,
) -> Dict:
    """
    对指定 crate 执行优化。返回结果摘要 dict。
    - project_root: 原 C 项目根目录（包含 .jarvis/c2rust）；为 None 时自动检测
    - crate_dir: crate 根目录（包含 Cargo.toml）；为 None 时自动检测
    - enable_*: 各优化步骤开关
    - max_checks: 限制 cargo check 调用次数（0 不限）
    - dry_run: 不写回，仅统计潜在修改
    - include_patterns/exclude_patterns: 逗号分隔的 glob；相对 crate 根（如 src/**/*.rs）
    - max_files: 本次最多处理文件数（0 不限）
    - resume: 启用断点续跑（跳过已处理文件）
    - reset_progress: 清空进度（processed 列表）
    """
    # 如果 project_root 为 None，尝试从当前目录查找
    if project_root is None:
        project_root = _find_project_root()
        if project_root is None:
            # 如果找不到项目根目录，使用当前目录
            project_root = Path(".").resolve()
    else:
        project_root = Path(project_root).resolve()
    
    # 如果 crate_dir 为 None，使用 detect_crate_dir 自动检测
    # detect_crate_dir 内部已经包含了从项目根目录推断的逻辑
    crate = detect_crate_dir(crate_dir)
    opts = OptimizeOptions(
        enable_unsafe_cleanup=enable_unsafe_cleanup,
        enable_structure_opt=enable_structure_opt,
        enable_visibility_opt=enable_visibility_opt,
        enable_doc_opt=enable_doc_opt,
        max_checks=max_checks,
        dry_run=dry_run,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        max_files=max_files,
        resume=resume,
        reset_progress=reset_progress,
        build_fix_retries=build_fix_retries,
        git_guard=git_guard,
        llm_group=llm_group,
        cargo_test_timeout=cargo_test_timeout,
        non_interactive=non_interactive,
    )
    optimizer = Optimizer(crate, opts, project_root=project_root)
    stats = optimizer.run()
    return asdict(stats)