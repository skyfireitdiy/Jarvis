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
from typing import cast

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
        self.current_session_name: Optional[str] = None  # 当前会话名称
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

    def _generate_session_name(self, user_input: str) -> str:
        """根据用户输入生成会话名称

        Args:
            user_input: 用户第一条输入

        Returns:
            str: 生成的会话名称（3-8个中文字符）
        """
        import re
        from jarvis.jarvis_platform.registry import PlatformRegistry

        # 限制输入长度，避免token过多
        if len(user_input) > 200:
            user_input = user_input[:200]

        # 使用cheap模型生成会话名称
        try:
            registry = PlatformRegistry.get_global_platform_registry()
            cheap_model = registry.create_platform(platform_type="cheap")
            if cheap_model is None:
                return "未命名会话"
            prompt = f"""请根据以下用户输入，生成一个简洁的会话名称（3-8个中文字符）。
要求：
1. 名称要能概括会话主题
2. 使用简洁的中文表达
3. 只返回名称，不要其他内容

用户输入：{user_input}

会话名称："""

            # 调用模型生成
            response = ""
            for chunk in cheap_model.chat(prompt):
                response += chunk

            # 清理响应
            session_name = response.strip()

            # 限制长度（3-8个中文字符，约等于6-16个字符）
            if len(session_name) > 16:
                session_name = session_name[:16]

            # 清理特殊字符，只保留中文、字母、数字、下划线、短横线
            session_name = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_-]", "", session_name)

            # 如果清理后为空，使用默认名称
            if not session_name:
                session_name = "未命名会话"

            return session_name

        except Exception as e:
            # 生成失败时使用默认名称
            PrettyOutput.auto_print(f"⚠️  生成会话名称失败: {e}，使用默认名称")
            return "未命名会话"

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
        # 中间格式：saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        # 新格式：{session_name}_saved_session_{agent_name}_{platform_name}_{model_name}_{timestamp}.json
        pattern = os.path.join(
            session_dir,
            f"*saved_session_{self.agent_name}_{platform_name}_{model_name}*.json",
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

    def _read_session_name(self, session_file: str) -> Optional[str]:
        """
        从会话的 commit 信息文件中读取会话名称。

        Args:
            session_file: 会话文件路径

        Returns:
            会话名称，如果不存在则返回 None。
        """
        try:
            # 构建对应的 _commit.json 文件路径
            commit_file = (
                session_file[:-5] + "_commit.json"
            )  # 去掉 ".json" 加上 "_commit.json"

            if not os.path.exists(commit_file):
                return None

            with open(commit_file, "r", encoding="utf-8") as f:
                commit_info = cast(Dict[str, Any], json.load(f))
                session_name = commit_info.get("session_name")
                # 确保返回值类型为 Optional[str]
                if session_name is not None and isinstance(session_name, str):
                    return cast(Optional[str], session_name)
                return None

        except Exception:
            # 读取失败不影响主流程，返回 None
            return None

    def _parse_session_files(self) -> List[Tuple[str, Optional[str], Optional[str]]]:
        """
        解析会话文件列表，返回包含文件路径、时间戳和会话名称的列表。

        Returns:
            会话信息列表，每个元素为 (文件路径, 时间戳, 会话名称)，按时间戳降序排列。
            如果文件没有时间戳，时间戳为 None；如果没有会话名称，会话名称为 None。
        """
        files = self._list_session_files()

        sessions = []
        for file_path in files:
            timestamp = self._extract_timestamp(file_path)
            session_name = self._read_session_name(file_path)
            sessions.append((file_path, timestamp, session_name))

        # 按时间戳降序排列（最新的在前），没有时间戳的排在最后
        sessions.sort(key=lambda x: (x[1] is None, x[1] or ""), reverse=True)

        return sessions

    def _find_sessions_by_commit(
        self, commit_hash: str
    ) -> List[Tuple[str, Optional[str], Optional[str]]]:
        """
        查找与指定commit匹配的会话列表。

        Args:
            commit_hash: 要匹配的commit hash

        Returns:
            匹配的会话列表，每个元素为 (文件路径, 时间戳, 会话名称)，按时间戳降序排列。
        """
        files = self._list_session_files()
        matching_sessions = []

        for file_path in files:
            try:
                # 读取对应的 _commit.json 文件
                commit_file = file_path[:-5] + "_commit.json"
                if not os.path.exists(commit_file):
                    continue

                with open(commit_file, "r", encoding="utf-8") as f:
                    commit_data = json.load(f)

                saved_commit = commit_data.get("current_commit", "")
                # 检查commit是否匹配
                if saved_commit == commit_hash:
                    timestamp = self._extract_timestamp(file_path)
                    session_name = self._read_session_name(file_path)
                    matching_sessions.append((file_path, timestamp, session_name))

            except Exception:
                # 读取失败时跳过该会话
                continue

        # 按时间戳降序排列（最新的在前）
        matching_sessions.sort(key=lambda x: (x[1] is None, x[1] or ""), reverse=True)
        return matching_sessions

    def _prompt_to_restore_matching_sessions(
        self, matching_sessions: List[Tuple[str, Optional[str], Optional[str]]]
    ) -> Optional[str]:
        """
        提示用户选择是否恢复匹配的会话。

        Args:
            matching_sessions: 匹配的会话列表，每个元素为 (文件路径, 时间戳, 会话名称)

        Returns:
            恢复的会话文件路径，如果用户选择不恢复则返回 None
        """
        if not matching_sessions:
            return None

        PrettyOutput.auto_print("\n🔍 检测到与当前commit一致的历史会话：")
        for idx, (file_path, timestamp, session_name) in enumerate(
            matching_sessions, 1
        ):
            time_str = timestamp if timestamp else "(无时间戳)"
            name_str = f" - {session_name}" if session_name else ""
            PrettyOutput.auto_print(
                f"  {idx}. {os.path.basename(file_path)} [{time_str}]{name_str}"
            )

        try:
            while True:
                choice = input(
                    "\n是否恢复会话？（输入序号恢复，直接回车跳过）: "
                ).strip()

                # 直接回车，不恢复
                if not choice:
                    PrettyOutput.auto_print("⏭️  跳过会话恢复，继续正常流程。")
                    return None

                # 验证输入是否为数字
                if not choice.isdigit():
                    PrettyOutput.auto_print("❌ 无效的选择，请输入数字或直接回车跳过。")
                    continue

                choice_idx = int(choice) - 1

                # 验证序号是否在有效范围内
                if choice_idx < 0 or choice_idx >= len(matching_sessions):
                    PrettyOutput.auto_print(
                        f"❌ 无效的选择，请输入1-{len(matching_sessions)}之间的数字，或直接回车跳过。"
                    )
                    continue

                # 输入有效，返回选中的会话文件
                return matching_sessions[choice_idx][0]

        except (EOFError, KeyboardInterrupt):
            PrettyOutput.auto_print("\n⚠️  已取消会话恢复。")
            return None

    def save_session(self) -> bool:
        """Saves the current session state to a file."""
        session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 确定会话名称
        if self.current_session_name:
            # 已有会话名称（从恢复的会话继承），直接使用
            session_name = self.current_session_name
        else:
            # 新建会话，从agent获取原始输入生成名称
            user_input = ""
            if self.agent and hasattr(self.agent, "get_user_origin_input"):
                user_input = self.agent.get_user_origin_input().strip()

            if user_input:
                session_name = self._generate_session_name(user_input)
                PrettyOutput.auto_print(f"📝 生成会话名称: {session_name}")
            else:
                session_name = "未命名会话"

            self.current_session_name = session_name

        # 使用session_name作为文件名前缀
        session_file = os.path.join(
            session_dir,
            f"{session_name}_saved_session_{self.agent_name}_{platform_name}_{model_name}_{timestamp}.json",
        )
        result = self.model.save(session_file)

        # 保存成功后，保存 commit 信息到辅助文件
        if result:
            self._save_commit_info(session_file)
            # 保存Agent运行时状态
            self._save_agent_state(timestamp)
            # 保存任务列表
            self._save_task_lists()
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

            # 获取 start_commit（优先从 agent 属性获取，兼容 user_data）
            start_commit = None
            if self.agent:
                # 优先检查 agent 的 start_commit 属性（CodeAgent 使用这种方式）
                if hasattr(self.agent, "start_commit"):
                    start_commit = self.agent.start_commit
                # 兼容：如果没有属性，尝试从 user_data 获取
                elif hasattr(self.agent, "get_user_data"):
                    start_commit = self.agent.get_user_data("start_commit")

            # 获取元数据
            agent_name = self.agent_name
            platform_name = self.model.platform_name()
            model_name = self.model.name().replace("/", "_").replace("\\", "_")

            # 从会话文件路径中提取时间戳
            import os
            from datetime import datetime

            basename = os.path.basename(session_file)
            parts = (
                basename.replace("saved_session_", "").replace(".json", "").split("_")
            )
            timestamp = parts[-1] if len(parts) >= 4 else None
            if timestamp and "_" in timestamp:
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
            if self.current_session_name:
                commit_info["session_name"] = self.current_session_name

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
                f"*saved_session_{self.agent_name}_{platform_name}_{model_name}*.json",
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
                PrettyOutput.auto_print(
                    "ℹ️  Commit文件存在但缺少current_commit字段，跳过一致性校验"
                )
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
                PrettyOutput.auto_print(f"   保存时的commit: {saved_commit[:12]}")
                PrettyOutput.auto_print(f"   当前的commit:  {current_commit[:12]}")
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
            session_file, timestamp, session_name = sessions[0]
            time_str = timestamp if timestamp else "(无时间戳)"
            name_str = f" [{session_name}]" if session_name else ""
            PrettyOutput.auto_print(
                f"📂 恢复会话{name_str}: {os.path.basename(session_file)} ({time_str})"
            )

            # 检查 commit 一致性
            if not self._check_commit_consistency(session_file):
                PrettyOutput.auto_print("⏸️  已取消恢复会话。")
                return False

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                self.current_session_name = session_name  # 记录会话名称
                # 恢复Agent运行时状态
                self._restore_agent_state()
                # 恢复任务列表
                self._restore_task_lists()
                # 如果是CodeAgent，恢复start_commit信息
                self._restore_start_commit_info()
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 多个会话文件，显示列表让用户选择
        # 检查是否为非交互模式
        if self.non_interactive:
            # 非交互模式：自动恢复最新的会话
            session_file, timestamp, session_name = sessions[0]
            time_str = timestamp if timestamp else "(无时间戳)"
            name_str = f" [{session_name}]" if session_name else ""
            PrettyOutput.auto_print(
                f"🤖 非交互模式：自动恢复最新会话{name_str}: {os.path.basename(session_file)} ({time_str})"
            )

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                self.current_session_name = session_name  # 记录会话名称
                # 恢复Agent运行时状态
                self._restore_agent_state()
                # 恢复任务列表
                self._restore_task_lists()
                # 如果是CodeAgent，恢复start_commit信息
                self._restore_start_commit_info()
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        # 交互模式：显示列表让用户选择
        PrettyOutput.auto_print("📋 找到多个会话文件：")
        for idx, (file_path, timestamp, session_name) in enumerate(sessions, 1):
            time_str = timestamp if timestamp else "(无时间戳)"
            name_str = f" - {session_name}" if session_name else ""
            PrettyOutput.auto_print(
                f"  {idx}. {os.path.basename(file_path)} [{time_str}]{name_str}"
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
            session_file, timestamp, session_name = sessions[choice_idx]
            time_str = timestamp if timestamp else "(无时间戳)"
            name_str = f" [{session_name}]" if session_name else ""
            PrettyOutput.auto_print(
                f"📂 恢复会话{name_str}: {os.path.basename(session_file)} ({time_str})"
            )

            # 检查 commit 一致性
            if not self._check_commit_consistency(session_file):
                PrettyOutput.auto_print("⏸️  已取消恢复会话。")
                return False

            if self.model.restore(session_file):
                self.last_restored_session = session_file  # 记录恢复的会话文件
                self.current_session_name = session_name  # 记录会话名称
                # 恢复Agent运行时状态
                self._restore_agent_state()
                # 恢复任务列表
                self._restore_task_lists()
                # 如果是CodeAgent，恢复start_commit信息
                self._restore_start_commit_info()
                return True
            else:
                PrettyOutput.auto_print("❌ 会话恢复失败。")
                return False

        except (EOFError, KeyboardInterrupt):
            PrettyOutput.auto_print("⚠️ 用户取消恢复。")
            return False

    def _get_session_file_prefix(self) -> str:
        """
        生成会话文件前缀（不含后缀）。

        Returns:
            str: 会话文件前缀，如 "saved_session_Jarvos_normal_gpt4"
        """
        import os

        session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
        os.makedirs(session_dir, exist_ok=True)
        platform_name = self.model.platform_name()
        model_name = self.model.name().replace("/", "_").replace("\\", "_")

        # 使用session_name作为前缀（如果存在）
        if self.current_session_name:
            # 从session_name提取文件名（移除特殊字符）
            import re

            safe_name = re.sub(
                r"[^\u4e00-\u9fa5a-zA-Z0-9_-]", "", self.current_session_name
            )
            if safe_name:
                return f"{safe_name}_saved_session_{self.agent_name}_{platform_name}_{model_name}"

        return f"saved_session_{self.agent_name}_{platform_name}_{model_name}"

    def _save_task_lists(self) -> bool:
        """保存当前 Agent 的任务列表到文件。

        文件命名规则：{prefix}_tasklist.json
        与会话文件保存在同一目录下，便于关联。

        Returns:
            bool: 是否成功保存
        """
        import json
        import os

        try:
            # 检查agent和task_list_manager是否存在
            if not self.agent:
                return True
            if (
                not hasattr(self.agent, "task_list_manager")
                or not self.agent.task_list_manager.task_lists
            ):
                return True  # 没有任务列表，视为成功

            # 构建文件路径
            session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
            os.makedirs(session_dir, exist_ok=True)

            prefix = self._get_session_file_prefix()
            tasklist_file = os.path.join(session_dir, f"{prefix}_tasklist.json")

            # 收集所有任务列表数据
            task_lists_data = {}
            for (
                task_list_id,
                task_list,
            ) in self.agent.task_list_manager.task_lists.items():
                task_lists_data[task_list_id] = task_list.to_dict()

            # 保存到文件
            with open(tasklist_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"task_lists": task_lists_data}, f, ensure_ascii=False, indent=2
                )

            return True
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存任务列表失败: {e}")
            return False

    def _restore_task_lists(self) -> bool:
        """从文件恢复当前 Agent 的任务列表。

        文件命名规则：{prefix}_tasklist.json
        与会话文件保存在同一目录下，便于关联。

        Returns:
            bool: 是否成功恢复
        """
        import json
        import os

        try:
            if not self.agent:
                return True

            # 构建文件路径
            session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
            prefix = self._get_session_file_prefix()
            tasklist_file = os.path.join(session_dir, f"{prefix}_tasklist.json")

            if not os.path.exists(tasklist_file):
                return True  # 文件不存在，视为成功（没有可恢复的任务列表）

            # 从文件加载任务列表数据
            with open(tasklist_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            task_lists_data = data.get("task_lists", {})

            # 导入TaskList（避免循环导入）
            from jarvis.jarvis_agent.task_list import TaskList

            # 清空当前的任务列表，然后从文件中恢复
            self.agent.task_list_manager.task_lists.clear()

            # 逐个恢复任务列表
            for task_list_id, task_list_data in task_lists_data.items():
                task_list = TaskList.from_dict(task_list_data)
                self.agent.task_list_manager.task_lists[task_list_id] = task_list

            return True
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 恢复任务列表失败: {e}")
            return False

    def _save_agent_state(self, timestamp: str) -> None:
        """保存SessionManager和Agent运行时状态到文件。

        Args:
            timestamp: 会话时间戳，用于生成文件名
        """
        import json
        import os

        if not self.agent:
            return

        session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
        os.makedirs(session_dir, exist_ok=True)

        prefix = self._get_session_file_prefix()
        state_file = os.path.join(
            session_dir,
            f"{prefix}_{timestamp}_state.json",
        )

        # 构建要保存的状态数据
        state_data = {
            "session_manager": {
                "prompt": self.prompt,
                "user_data": self.user_data,
                "addon_prompt": self.addon_prompt,
                "conversation_length": self.conversation_length,
                "non_interactive": self.non_interactive,
            },
            "agent_runtime": {
                "addon_prompt_skip_rounds": getattr(
                    self.agent, "_addon_prompt_skip_rounds", 0
                ),
                "no_tool_call_count": getattr(self.agent, "_no_tool_call_count", 0),
                "last_response_content": getattr(
                    self.agent, "_last_response_content", ""
                ),
                "recent_memories": getattr(self.agent, "recent_memories", []),
                "MAX_RECENT_MEMORIES": getattr(self.agent, "MAX_RECENT_MEMORIES", 10),
            },
            "metadata": {
                "agent_name": self.agent_name,
                "platform_name": self.model.platform_name(),
                "model_name": self.model.name().replace("/", "_").replace("\\", "_"),
                "timestamp": timestamp,
            },
        }

        # 如果是CodeAgent，额外保存CodeAgent特定状态
        if hasattr(self.agent, "start_commit"):
            state_data["codeagent"] = {
                "disable_review": getattr(self.agent, "disable_review", False),
                "review_max_iterations": getattr(
                    self.agent, "review_max_iterations", 3
                ),
                "tool_group": getattr(self.agent, "tool_group", "default"),
                "root_dir": getattr(self.agent, "root_dir", os.getcwd()),
                "prefix": getattr(self.agent, "prefix", ""),
                "suffix": getattr(self.agent, "suffix", ""),
            }

        # 保存RulesManager状态（已激活的规则列表）
        if hasattr(self.agent, "rules_manager") and self.agent.rules_manager:
            state_data["rules_manager"] = {
                "loaded_rules": list(
                    getattr(self.agent.rules_manager, "loaded_rules", set())
                ),
                "active_rules": list(
                    getattr(self.agent.rules_manager, "_active_rules", set())
                ),
            }

        # 导入SafeEncoder（避免循环导入）
        from jarvis.jarvis_agent import SafeEncoder

        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2, cls=SafeEncoder)
            PrettyOutput.auto_print("✅ Agent状态已保存")
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 保存Agent状态失败: {e}")

    def _restore_agent_state(self) -> None:
        """从文件恢复SessionManager和Agent运行时状态。"""
        import json
        import os

        if not self.agent:
            return

        try:
            # 提取时间戳
            if not self.last_restored_session:
                return

            session_file = os.path.basename(self.last_restored_session)
            timestamp = self._extract_timestamp(session_file)

            if not timestamp:
                PrettyOutput.auto_print("ℹ️ 会话文件无时间戳，跳过状态恢复")
                return

            # 构建状态文件路径
            session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
            prefix = self._get_session_file_prefix()
            state_file = os.path.join(
                session_dir,
                f"{prefix}_{timestamp}_state.json",
            )

            if not os.path.exists(state_file):
                PrettyOutput.auto_print("ℹ️ 未找到状态文件，跳过状态恢复")
                return

            # 从文件加载状态数据
            with open(state_file, "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # 恢复SessionManager状态
            session_manager_state = state_data.get("session_manager", {})
            if session_manager_state:
                self.prompt = session_manager_state.get("prompt", "")
                self.user_data = session_manager_state.get("user_data", {})
                self.addon_prompt = session_manager_state.get("addon_prompt", "")
                self.conversation_length = session_manager_state.get(
                    "conversation_length", 0
                )
                self.non_interactive = session_manager_state.get(
                    "non_interactive", False
                )
                PrettyOutput.auto_print("✅ SessionManager状态已恢复")

            # 恢复Agent运行时状态
            agent_runtime_state = state_data.get("agent_runtime", {})
            if agent_runtime_state:
                self.agent._addon_prompt_skip_rounds = agent_runtime_state.get(
                    "addon_prompt_skip_rounds", 0
                )
                self.agent._no_tool_call_count = agent_runtime_state.get(
                    "no_tool_call_count", 0
                )
                self.agent._last_response_content = agent_runtime_state.get(
                    "last_response_content", ""
                )
                # 恢复最近记忆队列
                self.agent.recent_memories = agent_runtime_state.get(
                    "recent_memories", []
                )
                self.agent.MAX_RECENT_MEMORIES = agent_runtime_state.get(
                    "MAX_RECENT_MEMORIES", 10
                )
                if self.agent.recent_memories:
                    PrettyOutput.auto_print(
                        f"✅ 已恢复 {len(self.agent.recent_memories)} 条最近记忆"
                    )
                PrettyOutput.auto_print("✅ Agent运行时状态已恢复")

            # 恢复CodeAgent特定状态
            if hasattr(self.agent, "start_commit"):
                codeagent_state = state_data.get("codeagent", {})
                if codeagent_state:
                    self.agent.disable_review = codeagent_state.get(
                        "disable_review", False
                    )
                    self.agent.review_max_iterations = codeagent_state.get(
                        "review_max_iterations", 3
                    )
                    self.agent.tool_group = codeagent_state.get("tool_group", "default")
                    self.agent.root_dir = codeagent_state.get("root_dir", os.getcwd())
                    self.agent.prefix = codeagent_state.get("prefix", "")
                    self.agent.suffix = codeagent_state.get("suffix", "")
                    PrettyOutput.auto_print("✅ CodeAgent配置已恢复")

            # 恢复RulesManager状态（已激活的规则）
            if hasattr(self.agent, "rules_manager") and self.agent.rules_manager:
                rules_manager_state = state_data.get("rules_manager", {})
                if rules_manager_state:
                    # loaded_rules = rules_manager_state.get("loaded_rules", [])  # 未使用，保留以供将来参考
                    active_rules = rules_manager_state.get("active_rules", [])

                    # 重新激活规则
                    reactivated_count = 0
                    for rule_name in active_rules:
                        try:
                            if hasattr(self.agent.rules_manager, "activate_rule"):
                                self.agent.rules_manager.activate_rule(rule_name)
                                reactivated_count += 1
                        except Exception:
                            pass  # 规则可能已不存在，静默失败

                    if reactivated_count > 0:
                        rule_names = ", ".join(active_rules)
                        PrettyOutput.auto_print(
                            f"✅ 已重新激活 {reactivated_count} 个规则: {rule_names}"
                        )

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 恢复Agent状态失败: {e}")

    def _restore_start_commit_info(self) -> None:
        """恢复CodeAgent的start_commit信息。"""
        import json
        import os

        if not self.agent:
            return

        # 只处理CodeAgent（有start_commit属性）
        if not hasattr(self.agent, "start_commit"):
            return

        if not self.last_restored_session:
            return

        try:
            # 使用 _extract_timestamp 方法来提取时间戳
            session_file = os.path.basename(self.last_restored_session)
            timestamp = self._extract_timestamp(session_file)

            # 使用 _get_session_file_prefix() 获取正确的前缀（包含session_name）
            prefix = self._get_session_file_prefix()

            # 根据时间戳确定commit文件名
            if timestamp:
                # 新格式：包含时间戳
                commit_filename = f"{prefix}_{timestamp}_commit.json"
            else:
                # 旧格式：不包含时间戳
                commit_filename = f"{prefix}_commit.json"

            session_dir = os.path.join(os.getcwd(), ".jarvis", "sessions")
            commit_file = os.path.join(session_dir, commit_filename)

            if os.path.exists(commit_file):
                with open(commit_file, "r", encoding="utf-8") as f:
                    commit_data = json.load(f)
                    # 恢复start_commit信息
                    self.agent.start_commit = commit_data.get("start_commit")
                    PrettyOutput.auto_print(
                        f"✅ 已恢复start_commit信息: {self.agent.start_commit[:8] if self.agent.start_commit else 'None'}..."
                    )
            else:
                PrettyOutput.auto_print(f"ℹ️ 未找到对应的commit文件: {commit_filename}")
        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ 恢复commit信息失败: {e}")

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
