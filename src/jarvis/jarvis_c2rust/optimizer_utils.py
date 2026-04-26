# -*- coding: utf-8 -*-
"""优化器工具函数。"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput
from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions
from jarvis.jarvis_c2rust.optimizer_options import OptimizeStats


def run_cmd(
    cmd: List[str],
    cwd: Path,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> Tuple[int, str, str]:
    """执行命令并返回结果。"""
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


def cargo_check(
    crate_dir: Path,
    stats: OptimizeStats,
    max_checks: int,
    timeout: Optional[int] = None,
) -> Tuple[bool, str]:
    """执行 cargo test 并返回结果摘要。"""
    # 统一使用 cargo test 作为验证手段
    if max_checks and stats.cargo_checks >= max_checks:
        return False, "cargo test budget exhausted"
    code, out, err = run_cmd(["cargo", "test", "-q"], crate_dir, timeout=timeout)
    stats.cargo_checks += 1
    ok = code == 0
    diag = err.strip() or out.strip()
    # 取首行作为摘要
    first_line = next((ln for ln in diag.splitlines() if ln.strip()), "")
    return ok, first_line


def run_cargo_fmt(crate_dir: Path) -> None:
    """执行 cargo fmt 格式化代码。fmt 失败不影响主流程，只记录警告。"""
    try:
        res = subprocess.run(
            ["cargo", "fmt"],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(crate_dir),
        )
        if res.returncode == 0:
            PrettyOutput.auto_print("✅ [c2rust-optimizer][fmt] 代码格式化完成")
        else:
            # fmt 失败不影响主流程，只记录警告
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-optimizer][fmt] 代码格式化失败（非致命）: {res.stderr or res.stdout}"
            )
    except Exception as e:
        # fmt 失败不影响主流程，只记录警告
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-optimizer][fmt] 代码格式化异常（非致命）: {e}"
        )


def check_clippy_warnings(crate_dir: Path) -> Tuple[bool, str]:
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
                    if (
                        msg.get("reason") == "compiler-message"
                        and msg.get("message", {}).get("level") == "warning"
                    ):
                        warnings.append(msg)
                except (json.JSONDecodeError, KeyError, TypeError):
                    # 忽略无法解析的行（可能是其他输出）
                    continue

        has_warnings = len(warnings) > 0

        # 调试输出
        if has_warnings:
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-optimizer][clippy-check] 检测到 {len(warnings)} 个 Clippy 告警"
            )
        elif res.returncode != 0:
            # 如果返回码非零但没有警告，可能是编译错误
            PrettyOutput.auto_print(
                f"📊 [c2rust-optimizer][clippy-check] Clippy 返回非零退出码（{res.returncode}），但未检测到告警，可能是编译错误"
            )
            if stderr_output:
                PrettyOutput.auto_print(
                    f"📊 [c2rust-optimizer][clippy-check] 错误输出预览（前200字符）: {stderr_output[:200]}"
                )

        # 返回 JSON 格式的输出（用于后续解析）
        return has_warnings, stdout_output
    except Exception as e:
        # 检查失败时假设没有告警，避免阻塞流程
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-optimizer][clippy-check] 检查 Clippy 告警异常（非致命）: {e}"
        )
        return False, ""


def check_missing_safety_doc_warnings(crate_dir: Path) -> Tuple[bool, str]:
    """
    检查是否有 missing_safety_doc 告警。
    使用 JSON 格式输出，便于精确解析和指定警告。
    返回 (has_warnings, json_output)，has_warnings 为 True 表示有告警，json_output 为 JSON 格式的输出。
    """
    try:
        res = subprocess.run(
            [
                "cargo",
                "clippy",
                "--message-format=json",
                "--",
                "-W",
                "clippy::missing_safety_doc",
            ],
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
            PrettyOutput.auto_print(
                f"⚠️ [c2rust-optimizer][missing-safety-doc-check] 检测到 {len(warnings)} 个 missing_safety_doc 告警"
            )
        elif res.returncode != 0:
            # 如果返回码非零但没有警告，可能是编译错误
            PrettyOutput.auto_print(
                f"📊 [c2rust-optimizer][missing-safety-doc-check] Clippy 返回非零退出码（{res.returncode}），但未检测到告警，可能是编译错误"
            )
            if stderr_output:
                PrettyOutput.auto_print(
                    f"📊 [c2rust-optimizer][missing-safety-doc-check] 错误输出预览（前200字符）: {stderr_output[:200]}"
                )

        # 返回 JSON 格式的输出（用于后续解析）
        return has_warnings, stdout_output
    except Exception as e:
        # 检查失败时假设没有告警，避免阻塞流程
        PrettyOutput.auto_print(
            f"⚠️ [c2rust-optimizer][missing-safety-doc-check] 检查 missing_safety_doc 告警异常（非致命）: {e}"
        )
        return False, ""


def cargo_check_full(
    crate_dir: Path,
    stats: OptimizeStats,
    max_checks: int,
    timeout: Optional[int] = None,
) -> Tuple[bool, str]:
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
        ok = res.returncode == 0
        out = res.stdout or ""
        err = res.stderr or ""
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


def git_toplevel(start: Path) -> Optional[Path]:
    """返回包含 start 的 Git 仓库根目录（--show-toplevel）。若不在仓库中则返回 None。"""
    try:
        code, out, err = run_cmd(["git", "rev-parse", "--show-toplevel"], start)
        if code == 0:
            p = (out or "").strip()
            if p:
                return Path(p)
        return None
    except Exception:
        return None


def git_head_commit(root: Path) -> Optional[str]:
    """获取 Git HEAD commit hash。"""
    try:
        code, out, err = run_cmd(["git", "rev-parse", "--verify", "HEAD"], root)
        if code == 0:
            return out.strip()
        return None
    except Exception:
        return None


def git_reset_hard(root: Path, commit: str) -> bool:
    """执行 git reset --hard 到指定 commit。"""
    try:
        code, _, _ = run_cmd(["git", "reset", "--hard", commit], root)
        if code != 0:
            return False
        return True
    except Exception:
        return False


def iter_rust_files(crate_dir: Path) -> Iterable[Path]:
    """遍历 crate 目录下的所有 Rust 文件。"""
    src = crate_dir / "src"
    if not src.exists():
        # 仍尝试遍历整个 crate 目录，但优先 src
        yield from crate_dir.rglob("*.rs")
        return
    # 遍历 src 优先
    yield from src.rglob("*.rs")


def read_file(path: Path) -> str:
    """读取文件内容。"""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, content: str) -> None:
    """写入文件内容。"""
    path.write_text(content, encoding="utf-8")


def backup_file(path: Path) -> Path:
    """备份文件。"""
    bak = path.with_suffix(path.suffix + ".bak_opt")
    shutil.copy2(path, bak)
    return bak


def restore_file_from_backup(path: Path, backup: Path) -> None:
    """从备份恢复文件。"""
    shutil.move(str(backup), str(path))


def remove_backup(backup: Path) -> None:
    """删除备份文件。"""
    if backup.exists():
        backup.unlink(missing_ok=True)


def ensure_report_dir(crate_dir: Path) -> Path:
    """确保报告目录存在。"""
    report_dir = crate_dir / ".jarvis" / "c2rust"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def find_project_root() -> Optional[Path]:
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


def parse_patterns(s: Optional[str]) -> List[str]:
    """解析逗号分隔的模式字符串。"""
    if not s or not isinstance(s, str):
        return []
    parts = [x.strip() for x in s.replace("\n", ",").split(",")]
    return [x for x in parts if x]


def match_any_pattern(rel: str, patterns: List[str]) -> bool:
    """检查相对路径是否匹配任一模式。"""
    if not patterns:
        return False
    import fnmatch

    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def compute_target_files(
    crate_dir: Path,
    options: OptimizeOptions,
    processed: Set[str],
) -> List[Path]:
    """
    计算目标文件列表（按 include/exclude/resume/max_files 过滤）。

    Args:
        crate_dir: crate 根目录
        options: 优化选项
        processed: 已处理的文件集合

    Returns:
        目标文件列表
    """
    include = parse_patterns(options.include_patterns)
    exclude = parse_patterns(options.exclude_patterns)
    maxn = int(options.max_files or 0)
    take: List[Path] = []
    for p in sorted(iter_rust_files(crate_dir), key=lambda x: x.as_posix()):
        try:
            rel = p.resolve().relative_to(crate_dir.resolve()).as_posix()
        except Exception:
            rel = p.as_posix()
        # include 过滤（若提供，则必须命中其一）
        if include and not match_any_pattern(rel, include):
            continue
        # exclude 过滤
        if exclude and match_any_pattern(rel, exclude):
            continue
        # resume：跳过已处理文件
        if options.resume and rel in processed:
            continue
        take.append(p)
        if maxn > 0 and len(take) >= maxn:
            break
    return take


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
    project_root = find_project_root()
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
