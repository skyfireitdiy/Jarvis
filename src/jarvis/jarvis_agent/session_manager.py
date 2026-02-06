# -*- coding: utf-8 -*-
import glob
import json
import os
import subprocess
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

from jarvis.jarvis_utils.output import PrettyOutput

if TYPE_CHECKING:
    from jarvis.jarvis_platform.base import BasePlatform
    from jarvis.jarvis_agent import Agent


class SessionManager:
    """
    Manages the session state of an agent, including conversation history,
    user data, and persistence.
    """

    def __init__(
        self, model: "BasePlatform", agent_name: str, agent: Optional["Agent"] = None
    ):
        self.model = model
        self.agent_name = agent_name
        self.agent = agent  # 添加agent引用
        self.prompt: str = ""
        self.user_data: Dict[str, Any] = {}
        self.addon_prompt: str = ""
        self.conversation_length: int = 0
        self.last_restored_session: Optional[str] = None  # 记录最后恢复的会话文件路径
        self.non_interactive: bool = False  # 是否为非交互模式

    def set_user_data(self, key: str, value: Any) -> None:
        """Sets a value in the user data dictionary."""
        self.user_data[key] = value

    def get_user_data(self, key: str) -> Optional[Any]:
        """Gets a value from the user data dictionary."""
        return self.user_data.get(key)

    def set_addon_prompt(self, addon_prompt: str) -> None:
        """Sets the addon prompt for the next model call."""
        self.addon_prompt = addon_prompt

    def _list_session_files(self) -> List[str]:
        """
        扫描并返回所有匹配当前会话的会话文件列表。

        Returns:
            会话文件路径列表，按文件名排序。
        """
        session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
        if not os.path.exists(session_dir):
            return []

        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")

        # 匹配新旧两种格式的会话文件
        # 旧格式：saved_session_{agent_name}_{platform_name}_{model_name}.json
        # 新格式：saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        pattern = os.path.join(
            session_dir,
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}*.json",
        )

        files = sorted(glob.glob(pattern))

        # 过滤掉辅助文件（commit文件、tasklist文件、state文件、codeagent文件）
        session_files = []
        for f in files:
            basename = os.path.basename(f)
            # 排除 _commit.json、_tasklist.json、_state.json 和 _codeagent.json 结尾的辅助文件
            if not (
                basename.endswith("_commit.json")
                or basename.endswith("_tasklist.json")
                or basename.endswith("_state.json")
                or basename.endswith("_codeagent.json")
            ):
                session_files.append(f)

        return session_files

    def _extract_timestamp(self, filename: str) -> Optional[str]:
        """
        从会话文件名中提取时间戳。

        Args:
            filename: 会话文件名（不包含路径）。

        Returns:
            时间戳字符串（如 "20250106_084038"），如果没有时间戳则返回 None。
        """
        import re

        basename = os.path.basename(filename)
        # 新格式：saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        # 时间戳格式：YYYYMMDD_HHMMSS（8位日期_6位时间）
        # 使用正则表达式精确匹配时间戳格式
        # \d{8}_\d{6} 匹配 8位数字 + 下划线 + 6位数字
        timestamp_pattern = r"_(\d{8}_\d{6})\.json$"
        match = re.search(timestamp_pattern, basename)

        if match:
            return match.group(1)

        return None

    def _parse_session_files(self) -> List[Tuple[str, Optional[str]]]:
        """
        解析会话文件列表，返回包含文件路径和时间戳的列表。

        Returns:
            会话信息列表，每个元素为 (文件路径, 时间戳)，按时间戳降序排列。
            如果文件没有时间戳，时间戳为 None，这类文件会排在最后。
        """
        files = self._list_session_files()

        sessions = []
        for file_path in files:
            timestamp = self._extract_timestamp(file_path)
            sessions.append((file_path, timestamp))

        # 按时间戳降序排列（最新的在前），没有时间戳的排在最后
        sessions.sort(key=lambda x: (x[1] is None, x[1] or ""), reverse=True)

        return sessions

    def save_session(self) -> bool:
        """Saves the current session state to a file."""
        session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file = os.path.join(
            session_dir,
            f"saved_session_{self.agent_name}_{platform_name}_{model_name}_{timestamp}.json",
        )
        result = self.model.save(session_file)

        # 保存成功后，保存 commit 信息到辅助文件
        if result:
            self._save_commit_info(session_file)
            # 清理旧会话文件（最多保留10个）
            self._cleanup_old_sessions(session_dir)

        return result

    def _save_commit_info(self, session_file: str) -> None:
        """
        保存 commit 信息到辅助文件。

        Args:
            session_file: 会话文件路径
        """
        try:
            from jarvis.jarvis_utils.git_utils import get_latest_commit_hash

            # 获取当前 commit 和 start_commit（如果有）
            current_commit = get_latest_commit_hash()

            # 获取 start_commit（从 agent 的 user_data 中）
            start_commit = None
            if self.agent:
                start_commit = self.agent.get_user_data("start_commit")

            # 获取元数据
            agent_name = self.agent_name
            platform_name = self.model.platform_name()
            model_name = self.model.name().replace("/", "_").replace("\\", "_")

            # 从会话文件路径中提取时间戳
            import os

            basename = os.path.basename(session_file)
            parts = (
                basename.replace("saved_session_", "").replace(".json", "").split("_")
            )
            timestamp = parts[-1] if len(parts) >= 4 else None
            if timestamp and "_" in timestamp:
                from datetime import datetime

                try:
                    dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                    timestamp_iso = dt.isoformat()
                except Exception:
                    timestamp_iso = timestamp
            else:
                timestamp_iso = datetime.now().isoformat()

            # 构建 commit 信息（包含所有字段）
            commit_info = {
                "current_commit": current_commit,
                "agent_name": agent_name,
                "platform_name": platform_name,
                "model_name": model_name,
                "timestamp": timestamp_iso,
            }
            if start_commit:
                commit_info["start_commit"] = start_commit

            # 写入 _commit.json 文件
            commit_file = (
                session_file[:-5] + "_commit.json"
            )  # 去掉 ".json" 加上 "_commit.json"
            with open(commit_file, "w", encoding="utf-8") as f:
                json.dump(commit_info, f, ensure_ascii=False, indent=4)

        except Exception as e:
            # 保存 commit 信息失败不影响主流程
            PrettyOutput.auto_print(f"⚠️  保存 commit 信息失败: {e}")

    def _cleanup_old_sessions(self, session_dir: str) -> None:
        """
        清理旧会话文件，最多保留10个最近的会话。

        Args:
            session_dir: 会话文件所在目录
        """
        try:
            # 直接在传入的目录中查找会话文件
            platform_name = self.model.platform_name()
            model_name = self.model.name().replace("/", "_").replace("\\", "_")

            # 匹配会话文件模式
            pattern = os.path.join(
                session_dir,
                f"saved_session_{self.agent_name}_{platform_name}_{model_name}*.json",
            )

            # 获取所有匹配的文件
            all_files = glob.glob(pattern)

            # 过滤掉辅助文件，只保留主会话文件
            session_files = []
            for f in all_files:
                basename = os.path.basename(f)
                # 排除辅助文件
                if not (
                    basename.endswith("_commit.json")
                    or basename.endswith("_tasklist.json")
                    or basename.endswith("_state.json")
                    or basename.endswith("_codeagent.json")
                ):
                    # 提取时间戳并排序
                    timestamp = self._extract_timestamp(f)
                    session_files.append((f, timestamp))

            # 按时间戳降序排列（最新的在前）
            session_files.sort(key=lambda x: (x[1] is None, x[1] or ""), reverse=True)

            # 如果超过10个，删除最旧的
            if len(session_files) > 10:
                # 删除第11个及之后的所有会话
                for session_file, _ in session_files[10:]:
                    try:
                        # 删除主会话文件
                        if os.path.exists(session_file):
                            os.remove(session_file)

                        # 删除对应的辅助文件
                        base_path = session_file[:-5]  # 去掉 ".json"
                        auxiliary_suffixes = [
                            "_commit.json",
                            "_tasklist.json",
                            "_state.json",
                            "_codeagent.json",
                        ]

                        for suffix in auxiliary_suffixes:
                            auxiliary_file = base_path + suffix
                            if os.path.exists(auxiliary_file):
                                os.remove(auxiliary_file)
                    except Exception as e:
                        # 删除失败不影响其他文件的清理
                        PrettyOutput.auto_print(f"⚠️  删除旧会话文件失败: {e}")
        except Exception as e:
            # 清理过程出错不应影响保存功能
            PrettyOutput.auto_print(f"⚠️  清理旧会话文件时出错: {e}")

    def _check_commit_consistency(self, session_file: str) -> bool:
        """
        检查会话文件保存时的 commit 与当前 commit 是否一致。

        Args:
            session_file: 会话文件路径

        Returns:
            bool: True 表示一致或用户选择继续，False 表示用户取消
        """
        try:
            # 从 _commit.json 文件读取保存时的 commit
            commit_file = session_file[:-5] + "_commit.json"

            # 如果 commit 文件不存在，跳过检查
            if not os.path.exists(commit_file):
                return True

            with open(commit_file, "r", encoding="utf-8") as f:
                commit_data = json.load(f)

            saved_commit = commit_data.get("current_commit", "")

            # 如果会话文件中没有保存 commit 信息，跳过检查
            if not saved_commit:
                return True

            # 获取当前 HEAD commit
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                current_commit = result.stdout.strip()

                # 如果不在 git 仓库中，跳过检查
                if result.returncode != 0:
                    return True

            except Exception:
                # git 命令执行失败，跳过检查
                return True

            # 检查 commit 是否一致
            if saved_commit == current_commit:
                PrettyOutput.auto_print("✅ Git commit 一致校验通过")
                return True

            # commit 不一致，显示警告并询问用户
            PrettyOutput.auto_print("")
            PrettyOutput.auto_print("⚠️  ==============================================")
            PrettyOutput.auto_print("⚠️  Git Commit 不一致警告")
            PrettyOutput.auto_print("⚠️  ==============================================")
            PrettyOutput.auto_print("")
            PrettyOutput.auto_print(f"会话保存时的 commit: {saved_commit[:12]}")
            PrettyOutput.auto_print(f"当前 HEAD commit:    {current_commit[:12]}")
            PrettyOutput.auto_print("")
            PrettyOutput.auto_print("代码状态可能与会话保存时不一致，这可能导致：")
            PrettyOutput.auto_print("  • 代码上下文缺失")
            PrettyOutput.auto_print("  • 引用的文件或函数不存在")
            PrettyOutput.auto_print("  • 历史对话中的代码引用失效")
            PrettyOutput.auto_print("")

            # 如果是非交互模式，直接警告并继续
            if self.non_interactive:
                PrettyOutput.auto_print("🤖 非交互模式：自动继续恢复（状态可能不一致）")
                return True

            # 交互模式：询问用户
            while True:
                choice = input(
                    "请选择操作: [1] Reset 到保存的 commit  [2] 继续恢复（可能不一致）: "
                ).strip()

                if choice == "1":
                    # 执行 git reset
                    PrettyOutput.auto_print(
                        f"正在 reset 到 commit {saved_commit[:12]}..."
                    )
                    reset_result = subprocess.run(
                        ["git", "reset", "--hard", saved_commit],
                        capture_output=True,
                        text=True,
                    )

                    if reset_result.returncode == 0:
                        PrettyOutput.auto_print("✅ 已成功 reset 到会话保存时的 commit")
                        return True
                    else:
                        PrettyOutput.auto_print(f"❌ Reset 失败: {reset_result.stderr}")
                        # reset 失败，询问是否继续
                        cont = input("是否仍然继续恢复会话？[y/N]: ").strip().lower()
                        if cont in ["y", "yes"]:
                            PrettyOutput.auto_print("⚠️  继续恢复会话（状态可能不一致）")
                            return True
                        else:
                            return False

                elif choice == "2":
                    PrettyOutput.auto_print("⚠️  继续恢复会话（状态可能不一致）")
                    return True

                else:
                    PrettyOutput.auto_print("❌ 无效的选择，请输入 1 或 2")

        except Exception as e:
            # 检查过程出错，记录警告但继续恢复
            PrettyOutput.auto_print(f"⚠️  检查 commit 一致性时出错: {e}")
            return True

    def restore_session(self) -> bool:
        """Restores the session state from a file."""
        sessions = self._parse_session_files()

        if not sessions:
            PrettyOutput.auto_print("❌ 未找到可恢复的会话文件。")
            return False

        # 如果只有一个会话文件，直接恢复
        if len(sessions) == 1:
            session_file = sessions[0][0]
            timestamp = sessions[0][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"📂 恢复会话: {os.path.basename(session_file)} ({time_str})"
            )

            # 检查 commit 一致性
            if not self._check_commit_consistency(session_file):
                PrettyOutput.auto_print("⏸️  已取消恢复会话。")
                return False

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 多个会话文件，显示列表让用户选择
        # 检查是否为非交互模式
        if self.non_interactive:
            # 非交互模式：自动恢复最新的会话
            session_file = sessions[0][0]
            timestamp = sessions[0][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"🤖 非交互模式：自动恢复最新会话: {os.path.basename(session_file)} ({time_str})"
            )

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 交互模式：显示列表让用户选择
        PrettyOutput.auto_print("📋 找到多个会话文件：")
        for idx, (file_path, timestamp) in enumerate(sessions, 1):
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"  {idx}. {os.path.basename(file_path)} [{time_str}]"
            )
        # 添加取消选项
        PrettyOutput.auto_print("  0. 取消恢复")

        try:
            while True:
                choice = input("请选择要恢复的会话（输入序号，0取消）: ").strip()

                if not choice.isdigit():
                    PrettyOutput.auto_print("❌ 无效的选择，请输入数字。")
                    continue

                choice_idx = int(choice) - 1
                # 选择0表示取消恢复
                if choice_idx == -1:
                    PrettyOutput.auto_print("⏸️  已取消恢复会话。")
                    return False

                if choice_idx < 0 or choice_idx >= len(sessions):
                    PrettyOutput.auto_print(
                        f"❌ 无效的选择，请输入0-{len(sessions)}之间的数字。"
                    )
                    continue

                # 输入有效，跳出循环
                break

            # 恢复选中的会话
            session_file = sessions[choice_idx][0]
            timestamp = sessions[choice_idx][1]
            time_str = timestamp if timestamp else "(无时间戳)"
            PrettyOutput.auto_print(
                f"📂 恢复会话: {os.path.basename(session_file)} ({time_str})"
            )

            # 检查 commit 一致性
            if not self._check_commit_consistency(session_file):
                PrettyOutput.auto_print("⏸️  已取消恢复会话。")
                return False

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                PrettyOutput.auto_print("✅ 会话已恢复。")
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        except (EOFError, KeyboardInterrupt):
            PrettyOutput.auto_print("⚠️ 用户取消恢复。")
            return False

    def clear_history(self) -> None:
        """
        Clears conversation history but keeps the system prompt by resetting the model state.
        """
        self.prompt = ""
        self.conversation_length = 0
        self.model.reset()

    def clear(self) -> None:
        """
        Clears the session state, resetting prompt and conversation length while
        preserving user_data. This method is an alias of clear_history for backward
        compatibility with existing tests and callers.
        """
        self.clear_history()
