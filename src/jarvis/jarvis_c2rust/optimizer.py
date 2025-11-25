# -*- coding: utf-8 -*-
"""
Rust 代码优化器：对转译或生成后的 Rust 项目执行若干保守优化步骤。

所有优化步骤均使用 CodeAgent 完成，确保智能、准确且可回退。

目标与策略（保守、可回退）:
1) unsafe 清理：
   - 使用 CodeAgent 识别可移除的 `unsafe { ... }` 包裹，移除后执行 `cargo test` 验证
   - 若必须保留 unsafe，缩小范围并在紧邻位置添加 `/// SAFETY: ...` 文档注释说明理由
2) 可见性优化（尽可能最小可见性）：
   - 使用 CodeAgent 将 `pub fn` 降为 `pub(crate) fn`（如果函数仅在 crate 内部使用）
   - 保持对外接口（跨 crate 使用的接口，如 lib.rs 中的顶层导出）为 `pub`
3) 文档补充：
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
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterable, Set
import fnmatch

import typer

# 引入 CodeAgent（参考 transpiler）
from jarvis.jarvis_code_agent.code_agent import CodeAgent
from jarvis.jarvis_c2rust.utils import check_and_handle_test_deletion


@dataclass
class OptimizeOptions:
    enable_unsafe_cleanup: bool = True
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

def _check_clippy_warnings(crate_dir: Path) -> Tuple[bool, str]:
    """
    检查是否有 clippy 告警。
    使用 JSON 格式输出，便于精确解析和指定警告。
    返回 (has_warnings, json_output)，has_warnings 为 True 表示有告警，json_output 为 JSON 格式的输出。
    """
    try:
        res = subprocess.run(
            ["cargo", "clippy", "--message-format=json", "--", "-W", "clippy::all"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        # clippy 的 JSON 输出通常在 stdout
        stdout_output = (res.stdout or "").strip()
        stderr_output = (res.stderr or "").strip()
        
        # 解析 JSON 输出，提取警告信息
        warnings = []
        if stdout_output:
            for line in stdout_output.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    # 只处理 warning 类型的消息
                    if msg.get("reason") == "compiler-message" and msg.get("message", {}).get("level") == "warning":
                        warnings.append(msg)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # 忽略无法解析的行（可能是其他输出）
                    continue
        
        has_warnings = len(warnings) > 0
        
        # 调试输出
        if has_warnings:
            typer.secho(f"[c2rust-optimizer][clippy-check] 检测到 {len(warnings)} 个 Clippy 告警", fg=typer.colors.YELLOW)
        elif res.returncode != 0:
            # 如果返回码非零但没有警告，可能是编译错误
            typer.secho(f"[c2rust-optimizer][clippy-check] Clippy 返回非零退出码（{res.returncode}），但未检测到告警，可能是编译错误", fg=typer.colors.CYAN)
            if stderr_output:
                typer.secho(f"[c2rust-optimizer][clippy-check] 错误输出预览（前200字符）: {stderr_output[:200]}", fg=typer.colors.CYAN)
        
        # 返回 JSON 格式的输出（用于后续解析）
        return has_warnings, stdout_output
    except Exception as e:
        # 检查失败时假设没有告警，避免阻塞流程
        typer.secho(f"[c2rust-optimizer][clippy-check] 检查 Clippy 告警异常（非致命）: {e}", fg=typer.colors.YELLOW)
        return False, ""

def _check_missing_safety_doc_warnings(crate_dir: Path) -> Tuple[bool, str]:
    """
    检查是否有 missing_safety_doc 告警。
    使用 JSON 格式输出，便于精确解析和指定警告。
    返回 (has_warnings, json_output)，has_warnings 为 True 表示有告警，json_output 为 JSON 格式的输出。
    """
    try:
        res = subprocess.run(
            ["cargo", "clippy", "--message-format=json", "--", "-W", "clippy::missing_safety_doc"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        # clippy 的 JSON 输出通常在 stdout
        stdout_output = (res.stdout or "").strip()
        stderr_output = (res.stderr or "").strip()
        
        # 解析 JSON 输出，提取警告信息
        warnings = []
        if stdout_output:
            for line in stdout_output.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    # 只处理 warning 类型的消息，且是 missing_safety_doc
                    if msg.get("reason") == "compiler-message":
                        message = msg.get("message", {})
                        if message.get("level") == "warning":
                            code = message.get("code", {})
                            code_str = code.get("code", "") if code else ""
                            if "missing_safety_doc" in code_str:
                                warnings.append(msg)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # 忽略无法解析的行（可能是其他输出）
                    continue
        
        has_warnings = len(warnings) > 0
        
        # 调试输出
        if has_warnings:
            typer.secho(f"[c2rust-optimizer][missing-safety-doc-check] 检测到 {len(warnings)} 个 missing_safety_doc 告警", fg=typer.colors.YELLOW)
        elif res.returncode != 0:
            # 如果返回码非零但没有警告，可能是编译错误
            typer.secho(f"[c2rust-optimizer][missing-safety-doc-check] Clippy 返回非零退出码（{res.returncode}），但未检测到告警，可能是编译错误", fg=typer.colors.CYAN)
            if stderr_output:
                typer.secho(f"[c2rust-optimizer][missing-safety-doc-check] 错误输出预览（前200字符）: {stderr_output[:200]}", fg=typer.colors.CYAN)
        
        # 返回 JSON 格式的输出（用于后续解析）
        return has_warnings, stdout_output
    except Exception as e:
        # 检查失败时假设没有告警，避免阻塞流程
        typer.secho(f"[c2rust-optimizer][missing-safety-doc-check] 检查 missing_safety_doc 告警异常（非致命）: {e}", fg=typer.colors.YELLOW)
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
                        step_order = ["clippy_elimination", "unsafe_cleanup", "visibility_opt", "doc_opt"]
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
                                    typer.secho("[c2rust-optimizer][resume] reset 失败，继续使用当前代码状态", fg=typer.colors.YELLOW)
                            else:
                                typer.secho("[c2rust-optimizer][resume] 代码状态一致，无需 reset", fg=typer.colors.CYAN)
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

    def _check_and_handle_test_deletion(self, before_commit: Optional[str], agent: Any) -> bool:
        """
        检测并处理测试代码删除。
        
        参数:
            before_commit: agent 运行前的 commit hash
            agent: 代码优化或修复的 agent 实例，使用其 model 进行询问
            
        返回:
            bool: 如果检测到问题且已回退，返回 True；否则返回 False
        """
        return check_and_handle_test_deletion(
            before_commit,
            agent,
            self._reset_to_commit,
            "[c2rust-optimizer]"
        )

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

    def _save_fix_progress(self, step_name: str, fix_key: str, files: Optional[List[Path]] = None) -> None:
        """
        保存单个修复的进度（包括 commit id）。
        
        Args:
            step_name: 步骤名称（如 "clippy_elimination", "unsafe_cleanup"）
            fix_key: 修复的唯一标识（如 "warning-1", "file_path.rs"）
            files: 修改的文件列表（可选）
        """
        try:
            # 获取当前 commit id
            current_commit = self._get_crate_commit_hash()
            if not current_commit:
                typer.secho("[c2rust-optimizer][progress] 无法获取 commit id，跳过进度记录", fg=typer.colors.YELLOW)
                return
            
            # 加载现有进度
            if self.progress_path.exists():
                try:
                    obj = json.loads(self.progress_path.read_text(encoding="utf-8"))
                except Exception:
                    obj = {}
            else:
                obj = {}
            
            # 初始化修复进度结构
            if "fix_progress" not in obj:
                obj["fix_progress"] = {}
            if step_name not in obj["fix_progress"]:
                obj["fix_progress"][step_name] = {}
            
            # 记录修复进度
            obj["fix_progress"][step_name][fix_key] = {
                "commit": current_commit,
                "timestamp": None,  # 可以添加时间戳如果需要
            }
            
            # 更新已处理的文件列表
            if files:
                rels = []
                for p in files:
                    try:
                        rel = p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                    except Exception:
                        rel = str(p)
                    rels.append(rel)
                self.processed.update(rels)
                obj["processed"] = sorted(self.processed)
            
            # 更新 last_commit
            obj["last_commit"] = current_commit
            
            # 保存进度
            self.progress_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            typer.secho(f"[c2rust-optimizer][progress] 已记录修复进度: {step_name}/{fix_key} -> commit {current_commit[:8]}", fg=typer.colors.CYAN)
        except Exception as e:
            typer.secho(f"[c2rust-optimizer] 保存修复进度失败（非致命）: {e}", fg=typer.colors.YELLOW)

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

    def _get_report_display_path(self, report_path: Path) -> str:
        """
        获取报告文件的显示路径（优先使用相对路径）。
        
        Args:
            report_path: 报告文件的绝对路径
            
        Returns:
            显示路径字符串
        """
        try:
            return str(report_path.relative_to(self.project_root))
        except ValueError:
            try:
                return str(report_path.relative_to(self.crate_dir))
            except ValueError:
                try:
                    return str(report_path.relative_to(Path.cwd()))
                except ValueError:
                    return str(report_path)

    def _write_final_report(self, report_path: Path) -> None:
        """
        写入最终优化报告。
        
        Args:
            report_path: 报告文件路径
        """
        try:
            _write_file(report_path, json.dumps(asdict(self.stats), ensure_ascii=False, indent=2))
        except Exception:
            pass

    def _verify_and_fix_after_step(self, step_name: str, target_files: List[Path]) -> bool:
        """
        验证步骤执行后的测试，如果失败则尝试修复。
        
        Args:
            step_name: 步骤名称（用于错误消息）
            target_files: 目标文件列表（用于修复范围）
            
        Returns:
            True: 测试通过或修复成功
            False: 测试失败且修复失败（已回滚）
        """
        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
        if not ok:
            fixed = self._build_fix_loop(target_files)
            if not fixed:
                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                self.stats.errors.append(f"test after {step_name} failed: {first}")
                try:
                    self._reset_to_snapshot()
                finally:
                    return False
        return True

    def _run_optimization_step(self, step_name: str, step_display_name: str, step_num: int, 
                               target_files: List[Path], opt_func) -> Optional[int]:
        """
        执行单个优化步骤（unsafe_cleanup, visibility_opt, doc_opt）。
        
        Args:
            step_name: 步骤名称（用于进度保存和错误消息）
            step_display_name: 步骤显示名称（用于日志）
            step_num: 步骤编号
            target_files: 目标文件列表
            opt_func: 优化函数（接受 target_files 作为参数）
            
        Returns:
            下一个步骤编号，如果失败则返回 None
        """
        typer.secho(f"\n[c2rust-optimizer] 第 {step_num} 步：{step_display_name}", fg=typer.colors.MAGENTA)
        self._snapshot_commit()
        if not self.options.dry_run:
            opt_func(target_files)
            if not self._verify_and_fix_after_step(step_name, target_files):
                # 验证失败，已回滚，返回 None 表示失败
                return None
            # 保存步骤进度
            self._save_step_progress(step_name, target_files)
        return step_num + 1

    def _handle_clippy_after_auto_fix(self, clippy_targets: List[Path], clippy_output: str) -> bool:
        """
        处理自动修复后的 clippy 告警检查。
        如果仍有告警，使用 CodeAgent 继续修复。
        
        Args:
            clippy_targets: 目标文件列表
            clippy_output: 当前的 clippy 输出
            
        Returns:
            True: 所有告警已消除
            False: 仍有告警未消除（步骤未完成）
        """
        typer.secho("[c2rust-optimizer] 自动修复后仍有告警，继续使用 CodeAgent 修复...", fg=typer.colors.CYAN)
        all_warnings_eliminated = self._codeagent_eliminate_clippy_warnings(clippy_targets, clippy_output)
        
        # 验证修复后是否还有告警
        if not self._verify_and_fix_after_step("clippy_elimination", clippy_targets):
            return False
        
        # 再次检查是否还有告警
        has_warnings_after, _ = _check_clippy_warnings(self.crate_dir)
        if not has_warnings_after and all_warnings_eliminated:
            typer.secho("[c2rust-optimizer] Clippy 告警已全部消除", fg=typer.colors.GREEN)
            self._save_step_progress("clippy_elimination", clippy_targets)
            return True
        else:
            typer.secho("[c2rust-optimizer] 仍有部分 Clippy 告警无法自动消除，步骤未完成，停止后续优化步骤", fg=typer.colors.YELLOW)
            return False

    def _run_clippy_elimination_step(self) -> bool:
        """
        执行 Clippy 告警修复步骤（第 0 步）。
        
        Returns:
            True: 步骤完成（无告警或已修复）
            False: 步骤未完成（仍有告警未修复，应停止后续步骤）
        """
        if self.options.dry_run:
            return True
            
        typer.secho("[c2rust-optimizer] 检查 Clippy 告警...", fg=typer.colors.CYAN)
        has_warnings, clippy_output = _check_clippy_warnings(self.crate_dir)
        
        # 如果步骤已标记为完成，但仍有告警，说明之前的完成标记是错误的，需要清除
        if "clippy_elimination" in self.steps_completed and has_warnings:
            typer.secho("[c2rust-optimizer] 检测到步骤已标记为完成，但仍有 Clippy 告警，清除完成标记并继续修复", fg=typer.colors.YELLOW)
            self.steps_completed.discard("clippy_elimination")
            if "clippy_elimination" in self._step_commits:
                del self._step_commits["clippy_elimination"]
        
        if not has_warnings:
            typer.secho("[c2rust-optimizer] 未发现 Clippy 告警，跳过消除步骤", fg=typer.colors.CYAN)
            # 如果没有告警，标记 clippy_elimination 为完成（跳过状态）
            if "clippy_elimination" not in self.steps_completed:
                clippy_targets = list(_iter_rust_files(self.crate_dir))
                if clippy_targets:
                    self._save_step_progress("clippy_elimination", clippy_targets)
            return True
        
        # 有告警，需要修复
        typer.secho("\n[c2rust-optimizer] 第 0 步：消除 Clippy 告警（必须完成此步骤才能继续其他优化）", fg=typer.colors.MAGENTA)
        self._snapshot_commit()
        
        clippy_targets = list(_iter_rust_files(self.crate_dir))
        if not clippy_targets:
            typer.secho("[c2rust-optimizer] 警告：未找到任何 Rust 文件，无法修复 Clippy 告警", fg=typer.colors.YELLOW)
            return False
        
        # 先尝试使用 clippy --fix 自动修复
        auto_fix_success = self._try_clippy_auto_fix()
        if auto_fix_success:
            typer.secho("[c2rust-optimizer] clippy 自动修复成功，继续检查是否还有告警...", fg=typer.colors.GREEN)
            # 重新检查告警
            has_warnings, clippy_output = _check_clippy_warnings(self.crate_dir)
            if not has_warnings:
                typer.secho("[c2rust-optimizer] 所有 Clippy 告警已通过自动修复消除", fg=typer.colors.GREEN)
                self._save_step_progress("clippy_elimination", clippy_targets)
                return True
            else:
                # 仍有告警，使用 CodeAgent 继续修复
                return self._handle_clippy_after_auto_fix(clippy_targets, clippy_output)
        else:
            # 自动修复失败或未执行，继续使用 CodeAgent 修复
            typer.secho("[c2rust-optimizer] clippy 自动修复未成功，继续使用 CodeAgent 修复...", fg=typer.colors.CYAN)
            all_warnings_eliminated = self._codeagent_eliminate_clippy_warnings(clippy_targets, clippy_output)
            
            # 验证修复后是否还有告警
            if not self._verify_and_fix_after_step("clippy_elimination", clippy_targets):
                return False
            
            # 再次检查是否还有告警
            has_warnings_after, _ = _check_clippy_warnings(self.crate_dir)
            if not has_warnings_after and all_warnings_eliminated:
                typer.secho("[c2rust-optimizer] Clippy 告警已全部消除", fg=typer.colors.GREEN)
                self._save_step_progress("clippy_elimination", clippy_targets)
                return True
            else:
                typer.secho("[c2rust-optimizer] 仍有部分 Clippy 告警无法自动消除，步骤未完成，停止后续优化步骤", fg=typer.colors.YELLOW)
                return False

    def run(self) -> OptimizeStats:
        """
        执行优化流程的主入口。
        
        Returns:
            优化统计信息
        """
        report_path = self.report_dir / "optimize_report.json"
        typer.secho(f"[c2rust-optimizer][start] 开始优化 Crate: {self.crate_dir}", fg=typer.colors.BLUE)
        try:
            # 批次开始前记录快照
            self._snapshot_commit()

            # ========== 第 0 步：Clippy 告警修复（必须第一步，且必须完成） ==========
            # 注意：clippy 告警修复不依赖于是否有新文件需要处理，即使所有文件都已处理，也应该检查并修复告警
            if not self._run_clippy_elimination_step():
                # Clippy 告警修复未完成，停止后续步骤
                return self.stats

            # ========== 后续优化步骤（只有在 clippy 告警修复完成后才执行） ==========
            # 计算本次批次的目标文件列表（按 include/exclude/resume/max_files）
            targets = self._compute_target_files()
            
            # 检查是否有未完成的步骤需要执行
            has_pending_steps = False
            if self.options.enable_unsafe_cleanup and "unsafe_cleanup" not in self.steps_completed:
                has_pending_steps = True
            if self.options.enable_visibility_opt and "visibility_opt" not in self.steps_completed:
                has_pending_steps = True
            if self.options.enable_doc_opt and "doc_opt" not in self.steps_completed:
                has_pending_steps = True
            
            # 如果没有新文件但有未完成的步骤，使用所有 Rust 文件作为目标
            if not targets and has_pending_steps:
                typer.secho("[c2rust-optimizer] 无新文件需要处理，但检测到未完成的步骤，使用所有 Rust 文件作为目标。", fg=typer.colors.CYAN)
                targets = list(_iter_rust_files(self.crate_dir))
            
            if not targets:
                typer.secho("[c2rust-optimizer] 根据当前选项，无新文件需要处理，且所有步骤均已完成。", fg=typer.colors.CYAN)
            else:
                typer.secho(f"[c2rust-optimizer] 本次批次发现 {len(targets)} 个待处理文件。", fg=typer.colors.BLUE)

                # 所有优化步骤都使用 CodeAgent
                step_num = 1
                
                if self.options.enable_unsafe_cleanup:
                    step_num = self._run_optimization_step(
                        "unsafe_cleanup", "unsafe 清理", step_num, targets,
                        self._codeagent_opt_unsafe_cleanup
                    )
                    if step_num is None:  # 步骤失败，已回滚
                        return self.stats

                if self.options.enable_visibility_opt:
                    step_num = self._run_optimization_step(
                        "visibility_opt", "可见性优化", step_num, targets,
                        self._codeagent_opt_visibility
                    )
                    if step_num is None:  # 步骤失败，已回滚
                        return self.stats

                if self.options.enable_doc_opt:
                    step_num = self._run_optimization_step(
                        "doc_opt", "文档补充", step_num, targets,
                        self._codeagent_opt_docs
                    )
                    if step_num is None:  # 步骤失败，已回滚
                        return self.stats

                # 最终保存进度（确保所有步骤的进度都已记录）
                self._save_progress_for_batch(targets)

        except Exception as e:
            self.stats.errors.append(f"fatal: {e}")
        finally:
            # 写出简要报告
            report_display = self._get_report_display_path(report_path)
            typer.secho(f"[c2rust-optimizer] 优化流程结束。报告已生成于: {report_display}", fg=typer.colors.GREEN)
            self._write_final_report(report_path)
        return self.stats

    # ========== 0) clippy warnings elimination (CodeAgent) ==========

    def _try_clippy_auto_fix(self) -> bool:
        """
        尝试使用 `cargo clippy --fix` 自动修复 clippy 告警。
        修复时同时包含测试代码（--tests），避免删除测试中使用的变量。
        修复后运行测试验证，如果测试失败则撤销修复。
        
        返回：
            True: 自动修复成功且测试通过
            False: 自动修复失败或测试未通过（已撤销修复）
        """
        crate = self.crate_dir.resolve()
        typer.secho("[c2rust-optimizer][clippy-auto-fix] 尝试使用 clippy --fix 自动修复（包含测试代码）...", fg=typer.colors.CYAN)
        
        # 记录修复前的 commit id
        commit_before = self._get_crate_commit_hash()
        if not commit_before:
            typer.secho("[c2rust-optimizer][clippy-auto-fix] 无法获取 commit id，跳过自动修复", fg=typer.colors.YELLOW)
            return False
        
        # 执行 cargo clippy --fix，添加 --tests 标志以包含测试代码
        try:
            res = subprocess.run(
                ["cargo", "clippy", "--fix", "--tests", "--allow-dirty", "--allow-staged", "--", "-W", "clippy::all"],
                capture_output=True,
                text=True,
                check=False,
                cwd=str(crate),
                timeout=300,  # 5 分钟超时
            )
            
            if res.returncode != 0:
                typer.secho(f"[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行失败（返回码: {res.returncode}）", fg=typer.colors.YELLOW)
                if res.stderr:
                    typer.secho(f"[c2rust-optimizer][clippy-auto-fix] 错误输出: {res.stderr[:500]}", fg=typer.colors.YELLOW)
                return False
            
            # 检查是否有文件被修改（通过 git status 或直接检查）
            # 如果没有修改，说明 clippy --fix 没有修复任何问题
            repo_root = _git_toplevel(crate)
            has_changes = False
            if repo_root:
                try:
                    code, out, _ = _run_cmd(["git", "diff", "--quiet", "--exit-code"], repo_root)
                    has_changes = (code != 0)  # 非零表示有修改
                except Exception:
                    # 如果无法检查 git 状态，假设有修改
                    has_changes = True
            else:
                # 不在 git 仓库中，假设有修改
                has_changes = True
            
            if not has_changes:
                typer.secho("[c2rust-optimizer][clippy-auto-fix] clippy --fix 未修改任何文件", fg=typer.colors.CYAN)
                return False
            
            typer.secho("[c2rust-optimizer][clippy-auto-fix] clippy --fix 已执行，正在验证测试...", fg=typer.colors.CYAN)
            
            # 运行 cargo test 验证
            ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
            
            if ok:
                typer.secho("[c2rust-optimizer][clippy-auto-fix] 自动修复成功且测试通过", fg=typer.colors.GREEN)
                return True
            else:
                typer.secho("[c2rust-optimizer][clippy-auto-fix] 自动修复后测试失败，正在撤销修复...", fg=typer.colors.YELLOW)
                # 撤销修复：回退到修复前的 commit
                if self._reset_to_commit(commit_before):
                    typer.secho(f"[c2rust-optimizer][clippy-auto-fix] 已成功撤销自动修复，回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                else:
                    typer.secho("[c2rust-optimizer][clippy-auto-fix] 撤销修复失败，请手动检查代码状态", fg=typer.colors.RED)
                return False
                
        except subprocess.TimeoutExpired:
            typer.secho("[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行超时，跳过自动修复", fg=typer.colors.YELLOW)
            # 尝试撤销（如果有修改）
            if commit_before:
                self._reset_to_commit(commit_before)
            return False
        except Exception as e:
            typer.secho(f"[c2rust-optimizer][clippy-auto-fix] clippy --fix 执行异常: {e}，跳过自动修复", fg=typer.colors.YELLOW)
            # 尝试撤销（如果有修改）
            if commit_before:
                self._reset_to_commit(commit_before)
            return False

    def _codeagent_eliminate_clippy_warnings(self, target_files: List[Path], clippy_output: str) -> bool:
        """
        使用 CodeAgent 消除 clippy 告警。
        按文件修复，每次修复单个文件的前10个告警（不足10个就全部给出），修复后重新扫描，不断迭代。
        
        注意：CodeAgent 必须在 crate 目录下创建和执行，以确保所有文件操作和命令执行都在正确的上下文中进行。
        
        返回：
            True: 所有告警已消除
            False: 仍有告警未消除（达到最大迭代次数或无法提取告警）
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

        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        iteration = 0
        
        try:
            os.chdir(str(crate))
            
            # 循环修复告警，按文件处理
            while True:
                iteration += 1
                
                # 检查当前告警
                has_warnings, current_clippy_output = _check_clippy_warnings(crate)
                if not has_warnings:
                    typer.secho(f"[c2rust-optimizer][codeagent][clippy] 所有告警已消除（共迭代 {iteration - 1} 次）", fg=typer.colors.GREEN)
                    return True  # 所有告警已消除

                # 按文件提取告警
                warnings_by_file = self._extract_warnings_by_file(current_clippy_output)
                if not warnings_by_file:
                    typer.secho("[c2rust-optimizer][codeagent][clippy] 无法提取告警，停止修复", fg=typer.colors.YELLOW)
                    return False  # 仍有告警未消除
                
                # 找到第一个有告警的文件（优先处理目标文件列表中的文件）
                target_file_path = None
                target_warnings = None
                
                # 优先处理目标文件列表中的文件
                for file_rel in file_list:
                    # 尝试匹配文件路径（可能是相对路径或绝对路径）
                    for file_path, warnings in warnings_by_file.items():
                        if file_rel in file_path or file_path.endswith(file_rel):
                            target_file_path = file_path
                            target_warnings = warnings
                            break
                    if target_file_path:
                        break
                
                # 如果目标文件列表中没有告警，选择第一个有告警的文件
                if not target_file_path:
                    target_file_path = next(iter(warnings_by_file.keys()))
                    target_warnings = warnings_by_file[target_file_path]
                
                # 获取该文件的前10个告警（不足10个就全部给出）
                warnings_to_fix = target_warnings[:10]
                warning_count = len(warnings_to_fix)
                total_warnings_in_file = len(target_warnings)
                
                typer.secho(f"[c2rust-optimizer][codeagent][clippy] 第 {iteration} 次迭代：修复文件 {target_file_path} 的前 {warning_count} 个告警（共 {total_warnings_in_file} 个）", fg=typer.colors.CYAN)
                
                # 格式化告警信息
                formatted_warnings = self._format_warnings_for_prompt(warnings_to_fix, max_count=10)
                
                # 构建提示词，修复该文件的前10个告警
                prompt_lines: List[str] = [
                    "你是资深 Rust 代码工程师。请在当前 crate 下修复指定文件中的 Clippy 告警，并以补丁形式输出修改：",
                    f"- crate 根目录：{crate}",
                    "",
                    "本次修复仅允许修改以下文件（严格限制，只处理这一个文件）：",
                    f"- {target_file_path}",
                    "",
                    f"重要：本次修复仅修复该文件中的前 {warning_count} 个告警，不要修复其他告警。",
                    "",
                    "优化目标：",
                    f"1) 修复文件 {target_file_path} 中的 {warning_count} 个 Clippy 告警：",
                    "   - 根据以下 Clippy 告警信息，修复这些告警；",
                    "   - 告警信息包含文件路径、行号、警告类型、消息和建议，请根据这些信息进行修复；",
                    "   - 对于无法自动修复的告警，请根据 Clippy 的建议进行手动修复；",
                    "   - **如果确认是误报**（例如：告警建议的修改会导致性能下降、代码可读性降低、或与项目设计意图不符），可以添加 `#[allow(clippy::...)]` 注释来屏蔽该告警；",
                    "   - 使用 `#[allow(...)]` 时，必须在注释中说明为什么这是误报，例如：`#[allow(clippy::unnecessary_wraps)] // 保持 API 一致性，返回值类型需要与接口定义一致`；",
                    "   - 优先尝试修复告警，只有在确认是误报时才使用 `#[allow(...)]` 屏蔽。",
                    "",
                    "约束与范围：",
                    f"- **仅修改文件 {target_file_path}，不要修改其他文件**；除非必须（如修复引用路径），否则不要修改其他文件。",
                    "- 保持最小改动，不要进行与消除告警无关的重构或格式化。",
                    f"- **只修复该文件中的前 {warning_count} 个告警，不要修复其他告警**。",
                    "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
                    "- 输出仅为补丁，不要输出解释或多余文本。",
                    "",
                    "优先级说明：",
                    "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
                    "- 在修复告警之前，先确保代码能够正常编译和通过测试；",
                    "- 如果修复告警导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
                    "",
                    "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                    "若出现编译错误或测试失败，请优先修复这些问题，然后再继续修复告警；",
                    "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                    "",
                    f"文件 {target_file_path} 中的 Clippy 告警信息如下：",
                    "<WARNINGS>",
                    formatted_warnings,
                    "</WARNINGS>",
                ]
                prompt = "\n".join(prompt_lines)
                prompt = self._append_additional_notes(prompt)
                
                # 修复前执行 cargo fmt
                _run_cargo_fmt(crate)
                
                # 记录运行前的 commit id
                commit_before = self._get_crate_commit_hash()
                
                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(name=f"ClippyWarningEliminator-iter{iteration}", need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
                agent.run(prompt, prefix="[c2rust-optimizer][codeagent][clippy]", suffix="")
                
                # 检测并处理测试代码删除
                if self._check_and_handle_test_deletion(commit_before, agent):
                    # 如果回退了，需要重新运行 agent
                    typer.secho(f"[c2rust-optimizer][codeagent][clippy] 检测到测试代码删除问题，已回退，重新运行 agent (iter={iteration})", fg=typer.colors.YELLOW)
                    commit_before = self._get_crate_commit_hash()
                    agent.run(prompt, prefix="[c2rust-optimizer][codeagent][clippy][retry]", suffix="")
                    # 再次检测
                    if self._check_and_handle_test_deletion(commit_before, agent):
                        typer.secho(f"[c2rust-optimizer][codeagent][clippy] 再次检测到测试代码删除问题，已回退 (iter={iteration})", fg=typer.colors.RED)
                
                # 验证修复是否成功（通过 cargo test）
                ok, _ = _cargo_check_full(crate, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                if ok:
                    # 修复成功，保存进度和 commit id
                    try:
                        file_path = crate / target_file_path if not Path(target_file_path).is_absolute() else Path(target_file_path)
                        if file_path.exists():
                            self._save_fix_progress("clippy_elimination", f"{target_file_path}-iter{iteration}", [file_path])
                        else:
                            self._save_fix_progress("clippy_elimination", f"{target_file_path}-iter{iteration}", None)
                    except Exception:
                        self._save_fix_progress("clippy_elimination", f"{target_file_path}-iter{iteration}", None)
                    typer.secho(f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 的前 {warning_count} 个告警修复成功，已保存进度", fg=typer.colors.GREEN)
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        typer.secho(f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 修复后测试失败，回退到运行前的 commit: {commit_before[:8]}", fg=typer.colors.YELLOW)
                        if self._reset_to_commit(commit_before):
                            typer.secho(f"[c2rust-optimizer][codeagent][clippy] 已成功回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                        else:
                            typer.secho("[c2rust-optimizer][codeagent][clippy] 回退失败，请手动检查代码状态", fg=typer.colors.RED)
                    else:
                        typer.secho(f"[c2rust-optimizer][codeagent][clippy] 文件 {target_file_path} 修复后测试失败，但无法获取运行前的 commit，继续修复", fg=typer.colors.YELLOW)
                
                # 修复后再次检查告警，如果告警数量没有减少，可能需要停止
                has_warnings_after, _ = _check_clippy_warnings(crate)
                if not has_warnings_after:
                    typer.secho(f"[c2rust-optimizer][codeagent][clippy] 所有告警已消除（共迭代 {iteration} 次）", fg=typer.colors.GREEN)
                    return True  # 所有告警已消除
        finally:
            os.chdir(prev_cwd)
        
        # 默认返回 False（仍有告警）
        return False
    
    def _extract_warnings_by_file(self, clippy_json_output: str) -> Dict[str, List[Dict]]:
        """
        从 clippy JSON 输出中提取所有告警并按文件分组。
        
        Returns:
            字典，键为文件路径，值为该文件的告警列表
        """
        if not clippy_json_output:
            return {}
        
        warnings_by_file: Dict[str, List[Dict]] = {}
        
        for line in clippy_json_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                # 只处理 warning 类型的消息
                if msg.get("reason") == "compiler-message" and msg.get("message", {}).get("level") == "warning":
                    message = msg.get("message", {})
                    spans = message.get("spans", [])
                    if spans:
                        primary_span = spans[0]
                        file_path = primary_span.get("file_name", "")
                        if file_path:
                            if file_path not in warnings_by_file:
                                warnings_by_file[file_path] = []
                            warnings_by_file[file_path].append(msg)
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        
        return warnings_by_file

    def _format_warnings_for_prompt(self, warnings: List[Dict], max_count: int = 10) -> str:
        """
        格式化告警列表，用于提示词。
        
        Args:
            warnings: 告警消息列表
            max_count: 最多格式化多少个告警（默认10个）
            
        Returns:
            格式化后的告警信息字符串
        """
        if not warnings:
            return ""
        
        # 只取前 max_count 个告警
        warnings_to_format = warnings[:max_count]
        formatted_warnings = []
        
        for idx, warning_msg in enumerate(warnings_to_format, 1):
            message = warning_msg.get("message", {})
            spans = message.get("spans", [])
            
            warning_parts = [f"告警 {idx}:"]
            
            # 警告类型和消息
            code = message.get("code", {})
            code_str = code.get("code", "") if code else ""
            message_text = message.get("message", "")
            warning_parts.append(f"  警告类型: {code_str}")
            warning_parts.append(f"  消息: {message_text}")
            
            # 文件位置
            if spans:
                primary_span = spans[0]
                line_start = primary_span.get("line_start", 0)
                column_start = primary_span.get("column_start", 0)
                line_end = primary_span.get("line_end", 0)
                column_end = primary_span.get("column_end", 0)
                
                if line_start == line_end:
                    warning_parts.append(f"  位置: {line_start}:{column_start}-{column_end}")
                else:
                    warning_parts.append(f"  位置: {line_start}:{column_start} - {line_end}:{column_end}")
                
                # 代码片段
                label = primary_span.get("label", "")
                if label:
                    warning_parts.append(f"  代码: {label}")
            
            # 建议（help 消息）
            children = message.get("children", [])
            for child in children:
                if child.get("level") == "help":
                    help_message = child.get("message", "")
                    help_spans = child.get("spans", [])
                    if help_message:
                        warning_parts.append(f"  建议: {help_message}")
                    if help_spans:
                        help_span = help_spans[0]
                        help_label = help_span.get("label", "")
                        if help_label:
                            warning_parts.append(f"  建议代码: {help_label}")
            
            formatted_warnings.append("\n".join(warning_parts))
        
        if len(warnings) > max_count:
            formatted_warnings.append(f"\n（该文件还有 {len(warnings) - max_count} 个告警，将在后续迭代中处理）")
        
        return "\n\n".join(formatted_warnings)

    # ========== 1) unsafe cleanup (CodeAgent) ==========

    def _codeagent_opt_unsafe_cleanup(self, target_files: List[Path]) -> None:
        """
        使用 CodeAgent 进行 unsafe 清理优化。
        使用 clippy 的 missing_safety_doc checker 来查找 unsafe 告警，按文件处理，每次处理一个文件的所有告警。
        
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

        # 切换到 crate 目录，确保 CodeAgent 在正确的上下文中创建和执行
        prev_cwd = os.getcwd()
        iteration = 0
        
        try:
            os.chdir(str(crate))
            
            # 循环修复 unsafe 告警，按文件处理
            while True:
                iteration += 1
                
                # 检查当前 missing_safety_doc 告警
                has_warnings, current_clippy_output = _check_missing_safety_doc_warnings(crate)
                if not has_warnings:
                    typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 所有 missing_safety_doc 告警已消除（共迭代 {iteration - 1} 次）", fg=typer.colors.GREEN)
                    return  # 所有告警已消除

                # 按文件提取告警
                warnings_by_file = self._extract_warnings_by_file(current_clippy_output)
                if not warnings_by_file:
                    typer.secho("[c2rust-optimizer][codeagent][unsafe-cleanup] 无法提取告警，停止修复", fg=typer.colors.YELLOW)
                    return  # 仍有告警未消除
                
                # 找到第一个有告警的文件（优先处理目标文件列表中的文件）
                target_file_path = None
                target_warnings = None
                
                # 优先处理目标文件列表中的文件
                for file_rel in file_list:
                    # 尝试匹配文件路径（可能是相对路径或绝对路径）
                    for file_path, warnings in warnings_by_file.items():
                        if file_rel in file_path or file_path.endswith(file_rel):
                            target_file_path = file_path
                            target_warnings = warnings
                            break
                    if target_file_path:
                        break
                
                # 如果目标文件列表中没有告警，选择第一个有告警的文件
                if not target_file_path:
                    target_file_path = next(iter(warnings_by_file.keys()))
                    target_warnings = warnings_by_file[target_file_path]
                
                # 获取该文件的所有告警（一次处理一个文件的所有告警）
                warnings_to_fix = target_warnings
                warning_count = len(warnings_to_fix)
                
                typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 第 {iteration} 次迭代：修复文件 {target_file_path} 的 {warning_count} 个 missing_safety_doc 告警", fg=typer.colors.CYAN)
                
                # 格式化告警信息
                formatted_warnings = self._format_warnings_for_prompt(warnings_to_fix, max_count=len(warnings_to_fix))
                
                # 构建提示词，修复该文件的所有 missing_safety_doc 告警
                prompt_lines: List[str] = [
                    "你是资深 Rust 代码工程师。请在当前 crate 下修复指定文件中的 missing_safety_doc 告警，并以补丁形式输出修改：",
                    f"- crate 根目录：{crate}",
                    "",
                    "本次优化仅允许修改以下文件（严格限制，只处理这一个文件）：",
                    f"- {target_file_path}",
                    "",
                    f"重要：本次修复仅修复该文件中的 {warning_count} 个 missing_safety_doc 告警。",
                    "",
                    "优化目标：",
                    f"1) 修复文件 {target_file_path} 中的 {warning_count} 个 missing_safety_doc 告警：",
                    "   **修复原则：能消除就消除，不能消除才增加 SAFETY 注释**",
                    "",
                    "   优先级 1（优先尝试）：消除 unsafe",
                    "   - 如果 unsafe 函数或方法实际上不需要是 unsafe 的，应该移除 unsafe 关键字；",
                    "   - 如果 unsafe 块可以移除，应该移除整个 unsafe 块；",
                    "   - 如果 unsafe 块可以缩小范围，应该缩小范围；",
                    "   - 仔细分析代码，判断是否真的需要 unsafe，如果可以通过安全的方式实现，优先使用安全的方式。",
                    "",
                    "   优先级 2（无法消除时）：添加 SAFETY 注释",
                    "   - 只有在确认无法消除 unsafe 的情况下，才为 unsafe 函数或方法添加 `/// SAFETY: ...` 文档注释；",
                    "   - SAFETY 注释必须详细说明为什么该函数或方法是 unsafe 的，包括：",
                    "     * 哪些不变量必须由调用者维护；",
                    "     * 哪些前提条件必须满足；",
                    "     * 可能导致未定义行为的情况；",
                    "     * 为什么不能使用安全的替代方案；",
                    "   - 如果 unsafe 块无法移除但可以缩小范围，应该缩小范围并在紧邻位置添加 `/// SAFETY: ...` 注释。",
                    "",
                    "约束与范围：",
                    f"- **仅修改文件 {target_file_path}，不要修改其他文件**；除非必须（如修复引用路径），否则不要修改其他文件。",
                    "- 保持最小改动，不要进行与修复 missing_safety_doc 告警无关的重构或格式化。",
                    f"- **只修复该文件中的 {warning_count} 个 missing_safety_doc 告警，不要修复其他告警**。",
                    "- 修改后需保证 `cargo test` 可以通过；如需引入少量配套改动，请一并包含在补丁中以确保通过。",
                    "- 输出仅为补丁，不要输出解释或多余文本。",
                    "",
                    "优先级说明：",
                    "- **修复 unsafe 的优先级：能消除就消除，不能消除才增加 SAFETY 注释**；",
                    "- 对于每个 unsafe，首先尝试分析是否可以安全地移除，只有在确认无法移除时才添加 SAFETY 注释；",
                    "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
                    "- 在修复告警之前，先确保代码能够正常编译和通过测试；",
                    "- 如果修复告警导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
                    "",
                    "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                    "若出现编译错误或测试失败，请优先修复这些问题，然后再继续修复告警；",
                    "若未通过，请继续输出新的补丁进行最小修复并再次自检，直至 `cargo test` 通过为止。",
                    "",
                    f"文件 {target_file_path} 中的 missing_safety_doc 告警信息如下：",
                    "<WARNINGS>",
                    formatted_warnings,
                    "</WARNINGS>",
                ]
                prompt = "\n".join(prompt_lines)
                prompt = self._append_additional_notes(prompt)
                
                # 修复前执行 cargo fmt
                _run_cargo_fmt(crate)
                
                # 记录运行前的 commit id
                commit_before = self._get_crate_commit_hash()
                
                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(name=f"UnsafeCleanupAgent-iter{iteration}", need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
                agent.run(prompt, prefix=f"[c2rust-optimizer][codeagent][unsafe-cleanup][iter{iteration}]", suffix="")
                
                # 检测并处理测试代码删除
                if self._check_and_handle_test_deletion(commit_before, agent):
                    # 如果回退了，需要重新运行 agent
                    typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 检测到测试代码删除问题，已回退，重新运行 agent (iter={iteration})", fg=typer.colors.YELLOW)
                    commit_before = self._get_crate_commit_hash()
                    agent.run(prompt, prefix=f"[c2rust-optimizer][codeagent][unsafe-cleanup][iter{iteration}][retry]", suffix="")
                    # 再次检测
                    if self._check_and_handle_test_deletion(commit_before, agent):
                        typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 再次检测到测试代码删除问题，已回退 (iter={iteration})", fg=typer.colors.RED)
                
                # 验证修复是否成功（通过 cargo test）
                ok, _ = _cargo_check_full(crate, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                if ok:
                    # 修复成功，保存进度和 commit id
                    try:
                        file_path = crate / target_file_path if not Path(target_file_path).is_absolute() else Path(target_file_path)
                        if file_path.exists():
                            self._save_fix_progress("unsafe_cleanup", f"{target_file_path}-iter{iteration}", [file_path])
                        else:
                            self._save_fix_progress("unsafe_cleanup", f"{target_file_path}-iter{iteration}", None)
                    except Exception:
                        self._save_fix_progress("unsafe_cleanup", f"{target_file_path}-iter{iteration}", None)
                    typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 的 {warning_count} 个告警修复成功，已保存进度", fg=typer.colors.GREEN)
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 修复后测试失败，回退到运行前的 commit: {commit_before[:8]}", fg=typer.colors.YELLOW)
                        if self._reset_to_commit(commit_before):
                            typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 已成功回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                        else:
                            typer.secho("[c2rust-optimizer][codeagent][unsafe-cleanup] 回退失败，请手动检查代码状态", fg=typer.colors.RED)
                    else:
                        typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 文件 {target_file_path} 修复后测试失败，但无法获取运行前的 commit，继续修复", fg=typer.colors.YELLOW)
                
                # 修复后再次检查告警
                has_warnings_after, _ = _check_missing_safety_doc_warnings(crate)
                if not has_warnings_after:
                    typer.secho(f"[c2rust-optimizer][codeagent][unsafe-cleanup] 所有 missing_safety_doc 告警已消除（共迭代 {iteration} 次）", fg=typer.colors.GREEN)
                    return  # 所有告警已消除
            
        finally:
            os.chdir(prev_cwd)

    # ========== 2) visibility optimization (CodeAgent) ==========

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
            "优先级说明：",
            "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
            "- 在进行可见性优化之前，先确保代码能够正常编译和通过测试；",
            "- 如果可见性优化导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若出现编译错误或测试失败，请优先修复这些问题，然后再继续可见性优化；",
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
            
            # 记录运行前的 commit id
            commit_before = self._get_crate_commit_hash()
            
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(name="VisibilityOptimizer", need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][visibility]", suffix="")
            
            # 检测并处理测试代码删除
            if self._check_and_handle_test_deletion(commit_before, agent):
                # 如果回退了，需要重新运行 agent
                typer.secho("[c2rust-optimizer][codeagent][visibility] 检测到测试代码删除问题，已回退，重新运行 agent", fg=typer.colors.YELLOW)
                commit_before = self._get_crate_commit_hash()
                agent.run(prompt, prefix="[c2rust-optimizer][codeagent][visibility][retry]", suffix="")
                # 再次检测
                if self._check_and_handle_test_deletion(commit_before, agent):
                    typer.secho("[c2rust-optimizer][codeagent][visibility] 再次检测到测试代码删除问题，已回退", fg=typer.colors.RED)
            
            # 验证修复是否成功（通过 cargo test）
            ok, _ = _cargo_check_full(crate, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
            if ok:
                # 修复成功，保存进度和 commit id
                file_paths = [crate / f for f in file_list if (crate / f).exists()]
                self._save_fix_progress("visibility_opt", "batch", file_paths if file_paths else None)
                typer.secho("[c2rust-optimizer][codeagent][visibility] 可见性优化成功，已保存进度", fg=typer.colors.GREEN)
            else:
                # 测试失败，回退到运行前的 commit
                if commit_before:
                    typer.secho(f"[c2rust-optimizer][codeagent][visibility] 可见性优化后测试失败，回退到运行前的 commit: {commit_before[:8]}", fg=typer.colors.YELLOW)
                    if self._reset_to_commit(commit_before):
                        typer.secho(f"[c2rust-optimizer][codeagent][visibility] 已成功回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                    else:
                        typer.secho("[c2rust-optimizer][codeagent][visibility] 回退失败，请手动检查代码状态", fg=typer.colors.RED)
                else:
                    typer.secho("[c2rust-optimizer][codeagent][visibility] 可见性优化后测试失败，但无法获取运行前的 commit", fg=typer.colors.YELLOW)
        finally:
            os.chdir(prev_cwd)

    # ========== 3) doc augmentation (CodeAgent) ==========

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
            "优先级说明：",
            "- **如果优化过程中出现了测试不通过或编译错误，必须优先解决这些问题**；",
            "- 在进行文档补充之前，先确保代码能够正常编译和通过测试；",
            "- 如果文档补充导致了编译错误或测试失败，必须立即修复这些错误，然后再继续优化。",
            "",
            "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
            "若出现编译错误或测试失败，请优先修复这些问题，然后再继续文档补充；",
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
            
            # 记录运行前的 commit id
            commit_before = self._get_crate_commit_hash()
            
            # CodeAgent 在 crate 目录下创建和执行
            agent = CodeAgent(name="DocumentationAgent", need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
            agent.run(prompt, prefix="[c2rust-optimizer][codeagent][doc]", suffix="")
            
            # 检测并处理测试代码删除
            if self._check_and_handle_test_deletion(commit_before, agent):
                # 如果回退了，需要重新运行 agent
                typer.secho("[c2rust-optimizer][codeagent][doc] 检测到测试代码删除问题，已回退，重新运行 agent", fg=typer.colors.YELLOW)
                commit_before = self._get_crate_commit_hash()
                agent.run(prompt, prefix="[c2rust-optimizer][codeagent][doc][retry]", suffix="")
                # 再次检测
                if self._check_and_handle_test_deletion(commit_before, agent):
                    typer.secho("[c2rust-optimizer][codeagent][doc] 再次检测到测试代码删除问题，已回退", fg=typer.colors.RED)
            
            # 验证修复是否成功（通过 cargo test）
            ok, _ = _cargo_check_full(crate, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
            if ok:
                # 修复成功，保存进度和 commit id
                file_paths = [crate / f for f in file_list if (crate / f).exists()]
                self._save_fix_progress("doc_opt", "batch", file_paths if file_paths else None)
                typer.secho("[c2rust-optimizer][codeagent][doc] 文档补充成功，已保存进度", fg=typer.colors.GREEN)
            else:
                # 测试失败，回退到运行前的 commit
                if commit_before:
                    typer.secho(f"[c2rust-optimizer][codeagent][doc] 文档补充后测试失败，回退到运行前的 commit: {commit_before[:8]}", fg=typer.colors.YELLOW)
                    if self._reset_to_commit(commit_before):
                        typer.secho(f"[c2rust-optimizer][codeagent][doc] 已成功回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                    else:
                        typer.secho("[c2rust-optimizer][codeagent][doc] 回退失败，请手动检查代码状态", fg=typer.colors.RED)
                else:
                    typer.secho("[c2rust-optimizer][codeagent][doc] 文档补充后测试失败，但无法获取运行前的 commit", fg=typer.colors.YELLOW)
        finally:
            os.chdir(prev_cwd)

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
                "优先级说明：",
                "- **必须优先解决所有编译错误和测试失败问题**；",
                "- 修复时应该先解决编译错误，然后再解决测试失败；",
                "- 如果修复过程中引入了新的错误，必须立即修复这些新错误。",
                "",
                "自检要求：在每次输出补丁后，请使用 execute_script 工具在 crate 根目录执行 `cargo test -q` 进行验证；",
                "若出现编译错误或测试失败，请优先修复这些问题；",
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
                
                # 记录运行前的 commit id
                commit_before = self._get_crate_commit_hash()
                
                # CodeAgent 在 crate 目录下创建和执行
                agent = CodeAgent(name=f"BuildFixAgent-iter{attempt}", need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
                agent.run(prompt, prefix=f"[c2rust-optimizer][build-fix iter={attempt}]", suffix="")
                
                # 检测并处理测试代码删除
                if self._check_and_handle_test_deletion(commit_before, agent):
                    # 如果回退了，需要重新运行 agent
                    typer.secho(f"[c2rust-optimizer][build-fix] 检测到测试代码删除问题，已回退，重新运行 agent (iter={attempt})", fg=typer.colors.YELLOW)
                    commit_before = self._get_crate_commit_hash()
                    agent.run(prompt, prefix=f"[c2rust-optimizer][build-fix iter={attempt}][retry]", suffix="")
                    # 再次检测
                    if self._check_and_handle_test_deletion(commit_before, agent):
                        typer.secho(f"[c2rust-optimizer][build-fix] 再次检测到测试代码删除问题，已回退 (iter={attempt})", fg=typer.colors.RED)
                
                # 验证修复是否成功（通过 cargo test）
                ok, _ = _cargo_check_full(crate, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                if ok:
                    # 修复成功，保存进度和 commit id
                    file_paths = [crate / f for f in allowed if (crate / f).exists()]
                    self._save_fix_progress("build_fix", f"iter{attempt}", file_paths if file_paths else None)
                    typer.secho(f"[c2rust-optimizer][build-fix] 第 {attempt} 次修复成功，已保存进度", fg=typer.colors.GREEN)
                    # 返回 True 表示修复成功
                    return True
                else:
                    # 测试失败，回退到运行前的 commit
                    if commit_before:
                        typer.secho(f"[c2rust-optimizer][build-fix] 第 {attempt} 次修复后测试失败，回退到运行前的 commit: {commit_before[:8]}", fg=typer.colors.YELLOW)
                        if self._reset_to_commit(commit_before):
                            typer.secho(f"[c2rust-optimizer][build-fix] 已成功回退到 commit: {commit_before[:8]}", fg=typer.colors.CYAN)
                        else:
                            typer.secho("[c2rust-optimizer][build-fix] 回退失败，请手动检查代码状态", fg=typer.colors.RED)
                    else:
                        typer.secho(f"[c2rust-optimizer][build-fix] 第 {attempt} 次修复后测试失败，但无法获取运行前的 commit，继续尝试", fg=typer.colors.YELLOW)
            finally:
                os.chdir(prev_cwd)

        return False

def optimize_project(
    project_root: Optional[Path] = None,
    crate_dir: Optional[Path] = None,
    enable_unsafe_cleanup: bool = True,
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