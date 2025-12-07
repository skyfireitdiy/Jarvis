# -*- coding: utf-8 -*-
"""优化器进度管理模块。"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, cast

import typer

from jarvis.jarvis_c2rust.optimizer_options import OptimizeOptions
from jarvis.jarvis_c2rust.optimizer_utils import (
    git_head_commit,
    git_reset_hard,
    git_toplevel,
)


class ProgressManager:
    """进度管理器，负责加载、保存进度和 Git 管理。"""

    def __init__(
        self,
        crate_dir: Path,
        options: OptimizeOptions,
        progress_path: Path,
    ):
        self.crate_dir = crate_dir
        self.options = options
        self.progress_path = progress_path
        self.processed: Set[str] = set()
        self.steps_completed: Set[str] = set()
        self._step_commits: Dict[str, str] = {}
        self._last_snapshot_commit: Optional[str] = None
        self._agent_before_commits: Dict[str, Optional[str]] = {}

    def load_or_reset_progress(self) -> None:
        """加载或重置进度。"""
        if self.options.reset_progress:
            try:
                self.progress_path.write_text(
                    json.dumps(
                        {"processed": [], "steps_completed": []},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except Exception:
                pass
            self.processed = set()
            if not hasattr(self, "steps_completed"):
                self.steps_completed = set()
            if not hasattr(self, "_step_commits"):
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
                        self.steps_completed = {
                            str(x) for x in steps if isinstance(x, str)
                        }
                    else:
                        self.steps_completed = set()
                    # 加载步骤的 commit id
                    step_commits = obj.get("step_commits") or {}
                    if isinstance(step_commits, dict):
                        self._step_commits = {
                            str(k): str(v)
                            for k, v in step_commits.items()
                            if isinstance(k, str) and isinstance(v, str)
                        }
                    else:
                        self._step_commits = {}

                    # 恢复时，reset 到最后一个步骤的 commit id
                    if self.options.resume and self._step_commits:
                        last_commit = None
                        # 按照步骤顺序找到最后一个已完成步骤的 commit
                        step_order = [
                            "clippy_elimination",
                            "unsafe_cleanup",
                            "visibility_opt",
                            "doc_opt",
                        ]
                        for step in reversed(step_order):
                            if (
                                step in self.steps_completed
                                and step in self._step_commits
                            ):
                                last_commit = self._step_commits[step]
                                break

                        if last_commit:
                            current_commit = self.get_crate_commit_hash()
                            if current_commit != last_commit:
                                typer.secho(
                                    f"[c2rust-optimizer][resume] 检测到代码状态不一致，正在 reset 到最后一个步骤的 commit: {last_commit}",
                                    fg=typer.colors.YELLOW,
                                )
                                if self.reset_to_commit(last_commit):
                                    typer.secho(
                                        f"[c2rust-optimizer][resume] 已 reset 到 commit: {last_commit}",
                                        fg=typer.colors.GREEN,
                                    )
                                else:
                                    typer.secho(
                                        "[c2rust-optimizer][resume] reset 失败，继续使用当前代码状态",
                                        fg=typer.colors.YELLOW,
                                    )
                            else:
                                typer.secho(
                                    "[c2rust-optimizer][resume] 代码状态一致，无需 reset",
                                    fg=typer.colors.CYAN,
                                )
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

    def get_crate_commit_hash(self) -> Optional[str]:
        """获取 crate 目录的当前 commit id。"""
        try:
            repo_root = git_toplevel(self.crate_dir)
            if repo_root is None:
                return None
            return git_head_commit(repo_root)
        except Exception:
            return None

    def reset_to_commit(self, commit_hash: str) -> bool:
        """回退 crate 目录到指定的 commit。"""
        try:
            repo_root = git_toplevel(self.crate_dir)
            if repo_root is None:
                return False
            return git_reset_hard(repo_root, commit_hash)
        except Exception:
            return False

    def snapshot_commit(self) -> None:
        """
        在启用 git_guard 时记录当前 HEAD commit（仅记录，不提交未暂存更改）。
        统一在仓库根目录执行 git 命令，避免子目录导致的意外。
        """
        if not self.options.git_guard:
            return
        try:
            repo_root = git_toplevel(self.crate_dir)
            if repo_root is None:
                return
            head = git_head_commit(repo_root)
            if head:
                self._last_snapshot_commit = head
        except Exception:
            # 忽略快照失败，不阻塞流程
            pass

    def reset_to_snapshot(self) -> bool:
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
        repo_root = git_toplevel(self.crate_dir)
        if repo_root is None:
            return False
        ok = git_reset_hard(repo_root, snap)
        return ok

    def save_progress_for_batch(self, files: List[Path]) -> None:
        """保存文件处理进度。"""
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
            current_commit = self.get_crate_commit_hash()

            data: Dict[str, Any] = {
                "processed": sorted(self.processed),
                "steps_completed": sorted(self.steps_completed),
            }
            if current_commit:
                data["last_commit"] = current_commit
                typer.secho(
                    f"[c2rust-optimizer][progress] 已记录当前 commit: {current_commit}",
                    fg=typer.colors.CYAN,
                )

            self.progress_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def save_fix_progress(
        self, step_name: str, fix_key: str, files: Optional[List[Path]] = None
    ) -> None:
        """
        保存单个修复的进度（包括 commit id）。

        Args:
            step_name: 步骤名称（如 "clippy_elimination", "unsafe_cleanup"）
            fix_key: 修复的唯一标识（如 "warning-1", "file_path.rs"）
            files: 修改的文件列表（可选）
        """
        try:
            # 获取当前 commit id
            current_commit = self.get_crate_commit_hash()
            if not current_commit:
                typer.secho(
                    "[c2rust-optimizer][progress] 无法获取 commit id，跳过进度记录",
                    fg=typer.colors.YELLOW,
                )
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
                        rel = (
                            p.resolve().relative_to(self.crate_dir.resolve()).as_posix()
                        )
                    except Exception:
                        rel = str(p)
                    rels.append(rel)
                self.processed.update(rels)
                obj["processed"] = sorted(self.processed)

            # 更新 last_commit
            obj["last_commit"] = current_commit

            # 保存进度
            self.progress_path.write_text(
                json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            typer.secho(
                f"[c2rust-optimizer][progress] 已记录修复进度: {step_name}/{fix_key} -> commit {current_commit[:8]}",
                fg=typer.colors.CYAN,
            )
        except Exception as e:
            typer.secho(
                f"[c2rust-optimizer] 保存修复进度失败（非致命）: {e}",
                fg=typer.colors.YELLOW,
            )

    def save_step_progress(self, step_name: str, files: List[Path]) -> None:
        """保存步骤进度：标记步骤完成并更新文件列表。"""
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
            current_commit = self.get_crate_commit_hash()

            # 保存进度
            data: Dict[str, Any] = {
                "processed": sorted(self.processed),
                "steps_completed": sorted(self.steps_completed),
            }
            if current_commit:
                # 记录每个步骤的 commit id
                step_commits = getattr(self, "_step_commits", {})
                step_commits[step_name] = current_commit
                self._step_commits = step_commits
                data["step_commits"] = cast(Dict[str, str], step_commits)
                data["last_commit"] = current_commit
                typer.secho(
                    f"[c2rust-optimizer][progress] 已记录步骤 '{step_name}' 的 commit: {current_commit}",
                    fg=typer.colors.CYAN,
                )

            self.progress_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            typer.secho(
                f"[c2rust-optimizer] 步骤 '{step_name}' 进度已保存",
                fg=typer.colors.CYAN,
            )
        except Exception as e:
            typer.secho(
                f"[c2rust-optimizer] 保存步骤进度失败（非致命）: {e}",
                fg=typer.colors.YELLOW,
            )

    def on_before_tool_call(self, agent: Any, current_response=None, **kwargs) -> None:
        """
        工具调用前的事件处理器，用于记录工具调用前的 commit id。

        在每次工具调用前记录当前的 commit，以便在工具调用后检测到问题时能够回退。
        """
        try:
            # 只关注可能修改代码的工具
            # 注意：在 BEFORE_TOOL_CALL 时，工具还未执行，无法获取工具名称
            # 但我们可以在 AFTER_TOOL_CALL 时检查工具名称，这里先记录 commit
            agent_id = id(agent)
            agent_key = f"agent_{agent_id}"
            current_commit = self.get_crate_commit_hash()
            if current_commit:
                # 记录工具调用前的 commit（如果之前没有记录，或者 commit 已变化）
                if (
                    agent_key not in self._agent_before_commits
                    or self._agent_before_commits[agent_key] != current_commit
                ):
                    self._agent_before_commits[agent_key] = current_commit
        except Exception as e:
            # 事件处理器异常不应影响主流程
            typer.secho(
                f"[c2rust-optimizer][test-detection] BEFORE_TOOL_CALL 事件处理器异常: {e}",
                fg=typer.colors.YELLOW,
            )

    def on_after_tool_call(
        self,
        agent: Any,
        current_response=None,
        need_return=None,
        tool_prompt=None,
        **kwargs,
    ) -> None:
        """
        工具调用后的事件处理器，用于细粒度检测测试代码删除。

        在每次工具调用后立即检测，如果检测到测试代码被错误删除，立即回退。
        """
        try:
            # 只检测编辑文件的工具调用
            last_tool = (
                agent.get_user_data("__last_executed_tool__")
                if hasattr(agent, "get_user_data")
                else None
            )
            if not last_tool:
                return

            # 只关注可能修改代码的工具
            edit_tools = {
                "edit_file",
                "rewrite_file",
                "apply_patch",
            }
            if last_tool not in edit_tools:
                return

            # 获取该 Agent 对应的工具调用前的 commit id
            agent_id = id(agent)
            agent_key = f"agent_{agent_id}"
            before_commit = self._agent_before_commits.get(agent_key)

            # 如果没有 commit 信息，无法检测
            if not before_commit:
                return

            # 检测测试代码删除
            from jarvis.jarvis_c2rust.utils import (
                detect_test_deletion,
                ask_llm_about_test_deletion,
            )

            detection_result = detect_test_deletion("[c2rust-optimizer]")
            if not detection_result:
                # 没有检测到删除，更新 commit 记录
                current_commit = self.get_crate_commit_hash()
                if current_commit and current_commit != before_commit:
                    self._agent_before_commits[agent_key] = current_commit
                return

            typer.secho(
                "[c2rust-optimizer][test-detection] 检测到可能错误删除了测试代码标记（工具调用后检测）",
                fg=typer.colors.YELLOW,
            )

            # 询问 LLM 是否合理
            need_reset = ask_llm_about_test_deletion(
                detection_result, agent, "[c2rust-optimizer]"
            )

            if need_reset:
                typer.secho(
                    f"[c2rust-optimizer][test-detection] LLM 确认删除不合理，正在回退到 commit: {before_commit}",
                    fg=typer.colors.RED,
                )
                if self.reset_to_commit(before_commit):
                    typer.secho(
                        "[c2rust-optimizer][test-detection] 已回退到之前的 commit（工具调用后检测）",
                        fg=typer.colors.GREEN,
                    )
                    # 回退后，保持之前的 commit 记录
                    self._agent_before_commits[agent_key] = before_commit
                    # 在 agent 的 session 中添加提示，告知修改被撤销
                    if hasattr(agent, "session") and hasattr(agent.session, "prompt"):
                        agent.session.prompt += "\n\n⚠️ 修改被撤销：检测到测试代码被错误删除，已回退到之前的版本。\n"
                else:
                    typer.secho(
                        "[c2rust-optimizer][test-detection] 回退失败",
                        fg=typer.colors.RED,
                    )
            else:
                # LLM 认为删除合理，更新 commit 记录
                current_commit = self.get_crate_commit_hash()
                if current_commit and current_commit != before_commit:
                    self._agent_before_commits[agent_key] = current_commit
        except Exception as e:
            # 事件处理器异常不应影响主流程
            typer.secho(
                f"[c2rust-optimizer][test-detection] AFTER_TOOL_CALL 事件处理器异常: {e}",
                fg=typer.colors.YELLOW,
            )

    def check_and_handle_test_deletion(
        self, before_commit: Optional[str], agent: Any
    ) -> bool:
        """
        检测并处理测试代码删除。

        参数:
            before_commit: agent 运行前的 commit hash
            agent: 代码优化或修复的 agent 实例，使用其 model 进行询问

        返回:
            bool: 如果检测到问题且已回退，返回 True；否则返回 False
        """
        from jarvis.jarvis_c2rust.utils import check_and_handle_test_deletion

        return check_and_handle_test_deletion(
            before_commit, agent, self.reset_to_commit, "[c2rust-optimizer]"
        )
