# -*- coding: utf-8 -*-
"""
Rust 代码优化器：对转译或生成后的 Rust 项目执行若干保守优化步骤。

目标与策略（保守、可回退）:
1) unsafe 清理：
   - 识别可移除的 `unsafe { ... }` 包裹，尝试移除后执行 `cargo check`
   - 若编译失败，回滚该处修改，并在该块或相邻函数前添加 `/// SAFETY: ` 说明
2) 代码结构优化（重复代码提示/最小消除）：
   - 基于文本的简单函数重复检测（签名 + 主体文本），为重复体添加 TODO 文档提示
   - 在 CodeAgent 阶段，允许最小化抽取公共辅助函数以消除重复（若易于安全完成）
3) 可见性优化（尽可能最小可见性）：
   - 对 `pub fn` 尝试降为 `pub(crate) fn`，变更后执行 `cargo check` 验证
   - 若失败回滚
   - 在 CodeAgent 阶段，允许在不破坏 API 的前提下进一步减少可见性（保持对外接口为 pub）
4) 文档补充：
   - 为缺少文档的模块/函数添加基础占位文档

实现说明：
- 以文件为粒度进行优化，每次微小变更均伴随 cargo check 进行验证
- 所有修改保留最小必要的文本变动，失败立即回滚
- 结果摘要与日志输出到 <crate_dir>/.jarvis/c2rust/optimize_report.json
- 进度记录（断点续跑）：<crate_dir>/.jarvis/c2rust/optimize_progress.json
  - 字段 processed: 已优化完成的文件（相对 crate 根的路径，posix 斜杠）

限制：
- 未依赖 rust-analyzer/LSP，主要使用静态文本 + `cargo check` 验证
- 复杂语法与宏、条件编译等情况下可能存在漏检或误判，将尽量保守处理
- 提供 CodeAgent 驱动的“整体优化”阶段，参考 transpiler 的 CodeAgent 使用方式；该阶段输出补丁并进行一次 cargo check 验证

使用入口：
- optimize_project(crate_dir: Optional[Path], ...) 作为对外简单入口
"""

from __future__ import annotations

import json5 as json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable, Set
import fnmatch

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


def detect_crate_dir(preferred: Optional[Path]) -> Path:
    """
    选择 crate 目录策略：
    - 若提供 preferred 且包含 Cargo.toml，则使用
    - 否则：优先 <cwd>/<cwd.name>_rs；若存在 Cargo.toml 则用之
    - 否则：在当前目录下递归寻找第一个包含 Cargo.toml 的目录
    - 若失败：若当前目录有 Cargo.toml 则返回当前目录，否则抛错
    """
    if preferred:
        preferred = preferred.resolve()
        if (preferred / "Cargo.toml").exists():
            return preferred

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
    def __init__(self, crate_dir: Path, options: OptimizeOptions):
        self.crate_dir = crate_dir
        self.options = options
        self.stats = OptimizeStats()
        # 进度文件
        self.report_dir = _ensure_report_dir(self.crate_dir)
        self.progress_path = self.report_dir / "optimize_progress.json"
        self.processed: Set[str] = set()
        self._target_files: List[Path] = []
        self._load_or_reset_progress()
        self._last_snapshot_commit: Optional[str] = None
        self.log_prefix = "[c2rust-优化器]"

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
                self.progress_path.write_text(json.dumps({"processed": []}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            self.processed = set()
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
        except Exception:
            self.processed = set()

    def _save_progress_for_batch(self, files: List[Path]) -> None:
        try:
            rels = []
            for p in files:
                try:
                    rel = p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                except Exception:
                    rel = str(p)
                rels.append(rel)
            self.processed.update(rels)
            data = {"processed": sorted(self.processed)}
            self.progress_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

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
        print(f"{self.log_prefix} 开始优化 Crate: {self.crate_dir}")
        try:
            # 计算本次批次的目标文件列表（按 include/exclude/resume/max_files）
            targets = self._compute_target_files()
            if not targets:
                # 无文件可处理：仍然写出报告并返回
                print(f"{self.log_prefix} 根据当前选项，无新文件需要处理。")
                pass
            else:
                print(f"{self.log_prefix} 本次批次发现 {len(targets)} 个待处理文件。")
                # 批次开始前记录快照
                self._snapshot_commit()

                if self.options.enable_unsafe_cleanup:
                    # 步骤前快照
                    print(f"\n{self.log_prefix} 第 1 步：unsafe 清理")
                    self._snapshot_commit()
                    self._opt_unsafe_cleanup(targets)
                    # Step build verification
                    if not self.options.dry_run:
                        print(f"{self.log_prefix} unsafe 清理后，正在验证构建...")
                        ok, diag_full = _cargo_check_full(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                        if not ok:
                            # 循环最小修复
                            fixed = self._build_fix_loop(targets)
                            if not fixed:
                                first = (diag_full.splitlines()[0] if isinstance(diag_full, str) and diag_full else "failed")
                                self.stats.errors.append(f"test after unsafe_cleanup failed: {first}")
                                # 回滚到快照并结束
                                try:
                                    self._reset_to_snapshot()
                                finally:
                                    return self.stats

                if self.options.enable_structure_opt:
                    # 步骤前快照
                    print(f"\n{self.log_prefix} 第 2 步：结构优化 (重复代码检测)")
                    self._snapshot_commit()
                    self._opt_structure_duplicates(targets)
                    # Step build verification
                    if not self.options.dry_run:
                        print(f"{self.log_prefix} 结构优化后，正在验证构建...")
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

                if self.options.enable_visibility_opt:
                    # 步骤前快照
                    print(f"\n{self.log_prefix} 第 3 步：可见性优化")
                    self._snapshot_commit()
                    self._opt_visibility(targets)
                    # Step build verification
                    if not self.options.dry_run:
                        print(f"{self.log_prefix} 可见性优化后，正在验证构建...")
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

                if self.options.enable_doc_opt:
                    # 步骤前快照
                    print(f"\n{self.log_prefix} 第 4 步：文档补充")
                    self._snapshot_commit()
                    self._opt_docs(targets)
                    # Step build verification
                    if not self.options.dry_run:
                        print(f"{self.log_prefix} 文档补充后，正在验证构建...")
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

                # CodeAgent 驱动的整体优化（参考 transpiler 使用模式）
                # 在静态优化后执行一次 CodeAgent 以最小化进一步提升（可选：dry_run 时跳过）
                if not self.options.dry_run:
                    try:
                        print(f"\n{self.log_prefix} 第 5 步：CodeAgent 整体优化")
                        self._codeagent_optimize_crate(targets)
                    except Exception as _e:
                        self.stats.errors.append(f"codeagent: {_e}")

                # 标记本批次文件为“已处理”
                self._save_progress_for_batch(targets)

        except Exception as e:
            self.stats.errors.append(f"fatal: {e}")
        finally:
            # 写出简要报告
            print(f"{self.log_prefix} 优化流程结束。报告已生成于: {report_path.relative_to(Path.cwd())}")
            try:
                _write_file(report_path, json.dumps(asdict(self.stats), ensure_ascii=False, indent=2))
            except Exception:
                pass
        return self.stats

    # ========== 1) unsafe cleanup ==========

    _re_unsafe_block = re.compile(r"\bunsafe\s*\{", re.MULTILINE)

    def _opt_unsafe_cleanup(self, files: List[Path]) -> None:
        for i, path in enumerate(files):
            try:
                rel_path = path.relative_to(self.crate_dir)
            except ValueError:
                rel_path = path
            print(f"{self.log_prefix} [unsafe 清理] 正在处理文件 {i + 1}/{len(files)}: {rel_path}")
            try:
                content = _read_file(path)
            except Exception:
                continue
            self.stats.files_scanned += 1

            # 简单逐处尝试：每次仅移除一个 unsafe 以保持回滚粒度
            pos = 0
            while True:
                m = self._re_unsafe_block.search(content, pos)
                if not m:
                    break

                # 准备试移除（仅移除 "unsafe " 关键字，保留后续块）
                start, end = m.span()
                trial = content[:start] + "{" + content[end:]  # 将 "unsafe {" 替换为 "{"

                if self.options.dry_run:
                    # 仅统计
                    self.stats.unsafe_removed += 1  # 计为潜在可移除
                    pos = start + 1
                    continue

                # 备份并写入尝试版
                bak = _backup_file(path)
                try:
                    _write_file(path, trial)
                    ok, diag = _cargo_check(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                    if ok:
                        # 保留修改
                        content = trial
                        self.stats.unsafe_removed += 1
                        # 不需要移动 pos 太多，继续搜索后续位置
                        pos = start + 1
                    else:
                        # 回滚，并在 unsafe 前添加说明
                        _restore_file_from_backup(path, bak)
                        content = _read_file(path)  # 还原后的内容
                        self._annotate_safety_comment(path, content, start, diag)
                        # 重新读取注释后的文本，以便继续
                        content = _read_file(path)
                        self.stats.unsafe_annotated += 1
                        pos = start + 1
                finally:
                    _remove_backup(bak)

            # 若最后的 content 与磁盘不同步（dry_run 时不会），这里无需写回

    def _annotate_safety_comment(self, path: Path, content: str, unsafe_pos: int, diag: str) -> None:
        """
        在 unsafe 块前注入一行文档注释，格式：
        /// SAFETY: 自动清理失败，保留 unsafe。原因摘要: <diag>
        """
        # 寻找 unsafe 所在行首
        line_start = content.rfind("\n", 0, unsafe_pos)
        if line_start == -1:
            insert_at = 0
        else:
            insert_at = line_start + 1

        annotation = f'/// SAFETY: 自动清理失败，保留 unsafe。原因摘要: {diag}\n'
        new_content = content[:insert_at] + annotation + content[insert_at:]

        if not self.options.dry_run:
            _write_file(path, new_content)

    # ========== 2) structure duplicates ==========

    _re_fn = re.compile(
        r"(?P<leading>\s*(?:pub(?:\([^\)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:extern\s+\"[^\"]*\"\s+)?fn\s+"
        r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)\s*(?:->\s*[^ \t\r\n\{]+)?\s*)\{",
        re.MULTILINE,
    )

    def _opt_structure_duplicates(self, files: List[Path]) -> None:
        # 建立函数签名+主体的简易哈希，重复则为后出现者添加 TODO 注释
        print(f"{self.log_prefix} [结构优化] 正在扫描 {len(files)} 个文件以查找重复函数...")
        seen: Dict[str, Tuple[Path, int]] = {}
        for path in files:
            try:
                content = _read_file(path)
            except Exception:
                continue

            for m in self._re_fn.finditer(content):
                name = m.group("name")
                body_start = m.end() - 1  # at '{'
                body_end = self._find_matching_brace(content, body_start)
                if body_end is None:
                    continue
                sig = m.group(0)[: m.group(0).rfind("{")].strip()
                body = content[body_start: body_end + 1]
                key = f"{name}::{self._normalize_ws(sig)}::{self._normalize_ws(body)}"
                if key not in seen:
                    seen[key] = (path, m.start())
                else:
                    # 重复：在该函数前添加 TODO
                    if self.options.dry_run:
                        self.stats.duplicates_tagged += 1
                        continue
                    bak = _backup_file(path)
                    try:
                        insert_pos = content.rfind("\n", 0, m.start())
                        insert_at = 0 if insert_pos == -1 else insert_pos + 1
                        origin_path, _ = seen[key]
                        try:
                            origin_rel = origin_path.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                        except Exception:
                            origin_rel = origin_path.as_posix()
                        todo = f'/// TODO: duplicate of {origin_rel}::{name}\n'
                        new_content = content[:insert_at] + todo + content[insert_at:]
                        _write_file(path, new_content)
                        content = new_content
                        self.stats.duplicates_tagged += 1
                    finally:
                        _remove_backup(bak)

    def _find_matching_brace(self, s: str, open_pos: int) -> Optional[int]:
        """
        给定 s[open_pos] == '{'，返回匹配的 '}' 位置；简单计数器，忽略字符串/注释的复杂性（保守）
        """
        if open_pos >= len(s) or s[open_pos] != "{":
            return None
        depth = 0
        for i in range(open_pos, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
        return None

    def _normalize_ws(self, s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    # ========== 3) visibility optimization ==========

    _re_pub_fn = re.compile(
        r"(?P<prefix>\s*)pub\s+fn\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    )

    def _opt_visibility(self, files: List[Path]) -> None:
        for i, path in enumerate(files):
            try:
                rel_path = path.relative_to(self.crate_dir)
            except ValueError:
                rel_path = path
            print(f"{self.log_prefix} [可见性优化] 正在处理文件 {i + 1}/{len(files)}: {rel_path}")
            try:
                content = _read_file(path)
            except Exception:
                continue

            for m in list(self._re_pub_fn.finditer(content)):
                start, end = m.span()
                name = m.group("name")
                candidate = content[:start] + f"{m.group('prefix')}pub(crate) fn {name}(" + content[end:]
                if self.options.dry_run:
                    self.stats.visibility_downgraded += 1
                    continue
                bak = _backup_file(path)
                try:
                    _write_file(path, candidate)
                    ok, _ = _cargo_check(self.crate_dir, self.stats, self.options.max_checks, timeout=self.options.cargo_test_timeout)
                    if ok:
                        content = candidate
                        self.stats.visibility_downgraded += 1
                    else:
                        _restore_file_from_backup(path, bak)
                        content = _read_file(path)
                finally:
                    _remove_backup(bak)

    # ========== 4) doc augmentation ==========

    _re_mod_doc = re.compile(r"(?m)^\s*//!")  # 顶部模块文档
    _re_any_doc = re.compile(r"(?m)^\s*///")

    def _opt_docs(self, files: List[Path]) -> None:
        for i, path in enumerate(files):
            try:
                rel_path = path.relative_to(self.crate_dir)
            except ValueError:
                rel_path = path
            print(f"{self.log_prefix} [文档补充] 正在处理文件 {i + 1}/{len(files)}: {rel_path}")
            try:
                content = _read_file(path)
            except Exception:
                continue

            changed = False
            # 模块级文档：若文件开头不是文档，补充
            if not self._re_mod_doc.search(content[:500]):  # 仅检查开头部分
                header = "//! TODO: Add module-level documentation\n"
                content = header + content
                changed = True
                self.stats.docs_added += 1

            # 函数文档：为未有文档注释的函数前补充
            new_content = []
            last_end = 0
            for m in self._re_fn.finditer(content):
                fn_start = m.start()
                # 检查前一行是否有 /// 文档
                line_start = content.rfind("\n", 0, fn_start)
                prev_line_start = content.rfind("\n", 0, line_start - 1) if line_start > 0 else -1
                segment_start = last_end
                segment_end = line_start + 1 if line_start != -1 else 0
                new_content.append(content[segment_start:segment_end])

                doc_exists = False
                if line_start != -1:
                    prev_line = content[prev_line_start + 1: line_start] if prev_line_start != -1 else content[:line_start]
                    if self._re_any_doc.search(prev_line):
                        doc_exists = True

                if not doc_exists:
                    new_content.append("/// TODO: Add documentation\n")
                    changed = True
                    self.stats.docs_added += 1

                new_content.append(content[segment_end: m.end()])  # 包含到函数体起始的部分
                last_end = m.end()

            new_content.append(content[last_end:])
            new_s = "".join(new_content)

            if changed and not self.options.dry_run:
                _write_file(path, new_s)

    # ========== 5) CodeAgent 整体优化（参考 transpiler 的 CodeAgent 使用方式） ==========

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
        prev_cwd = os.getcwd()
        print(f"{self.log_prefix} [CodeAgent] 正在调用 CodeAgent 进行整体优化...")
        try:
            os.chdir(str(crate))
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
                    print(f"{self.log_prefix} 构建修复成功。")
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
                print(f"{self.log_prefix} 构建修复重试次数已用尽。")
                return False

            print(f"{self.log_prefix} 构建失败。正在尝试使用 CodeAgent 进行修复 (第 {attempt}/{maxr} 次尝试)...")
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
            prev_cwd = os.getcwd()
            try:
                os.chdir(str(crate))
                agent = CodeAgent(need_summary=False, non_interactive=self.options.non_interactive, model_group=self.options.llm_group)
                agent.run(prompt, prefix=f"[c2rust-optimizer][build-fix iter={attempt}]", suffix="")
            finally:
                os.chdir(prev_cwd)

        return False

def optimize_project(
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
    - crate_dir: crate 根目录（包含 Cargo.toml）；为 None 时自动检测
    - enable_*: 各优化步骤开关
    - max_checks: 限制 cargo check 调用次数（0 不限）
    - dry_run: 不写回，仅统计潜在修改
    - include_patterns/exclude_patterns: 逗号分隔的 glob；相对 crate 根（如 src/**/*.rs）
    - max_files: 本次最多处理文件数（0 不限）
    - resume: 启用断点续跑（跳过已处理文件）
    - reset_progress: 清空进度（processed 列表）
    """
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
    optimizer = Optimizer(crate, opts)
    stats = optimizer.run()
    return asdict(stats)