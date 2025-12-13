"""
构建系统检测器模块

提供构建系统自动检测功能。
"""

import os
import re
import subprocess

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from typing import Optional
from typing import Tuple

from .base import BuildSystem


class BuildSystemDetector:
    """构建系统检测器"""

    def __init__(self, project_root: str):
        self.project_root = project_root

    def _get_file_statistics(self) -> str:
        """获取文件数量统计信息

        使用loc工具获取文件统计信息。

        Returns:
            loc工具输出的原始字符串，失败时返回空字符串
        """
        try:
            # 调用loc工具获取统计信息
            result = subprocess.run(
                ["loc"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            else:
                return ""
        except FileNotFoundError:
            # loc工具未安装，返回空字符串
            PrettyOutput.auto_print("⚠️ loc工具未安装，无法获取文件统计信息")
            return ""
        except Exception as e:
            # 其他错误，返回空字符串
            PrettyOutput.auto_print(f"⚠️ 调用loc工具失败: {e}")
            return ""

    def _get_git_root_file_list(self, max_files: int = 100) -> str:
        """获取git根目录的文件列表（限制数量）

        先识别git根目录，然后列出根目录下的文件列表。

        Args:
            max_files: 最大返回文件数量

        Returns:
            文件列表的字符串表示，每行一个文件，失败时返回空字符串
        """
        try:
            # 先识别git根目录
            git_root_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if git_root_result.returncode != 0:
                # 如果不是git仓库，尝试直接读取当前目录
                git_root = self.project_root
            else:
                git_root = git_root_result.stdout.strip()

            # 列出git根目录下的文件
            file_list: List[str] = []

            # 使用git ls-files获取git跟踪的文件列表
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                files = result.stdout.strip().split("\n")
                # 只取根目录下的文件（不包含子目录）
                for file_path in files:
                    if not file_path.strip():
                        continue
                    # 只取根目录下的文件（不包含路径分隔符）
                    if "/" not in file_path:
                        file_list.append(file_path)
                        if len(file_list) >= max_files:
                            break
            else:
                # 如果git命令失败，尝试直接读取根目录
                try:
                    for item in os.listdir(git_root):
                        item_path = os.path.join(git_root, item)
                        if os.path.isfile(item_path) and not item.startswith("."):
                            file_list.append(item)
                            if len(file_list) >= max_files:
                                break
                except Exception:
                    pass

            # 返回格式化的字符串
            if file_list:
                return "\n".join(file_list)
            else:
                return ""
        except Exception as e:
            # 发生错误时返回空字符串
            PrettyOutput.auto_print(f"⚠️ 获取git根目录文件列表失败: {e}")
            return ""

    def _get_supported_build_systems(self) -> List[str]:
        """获取当前支持的构建系统列表

        Returns:
            构建系统名称列表
        """
        return [
            "rust (Cargo.toml)",
            "go (go.mod)",
            "java_maven (pom.xml)",
            "java_gradle (build.gradle/build.gradle.kts)",
            "nodejs (package.json)",
            "python (setup.py/pyproject.toml/requirements.txt等)",
            "c_cmake (CMakeLists.txt)",
            "c_makefile (Makefile)",
            "unknown (未知/未识别)",
        ]

    def detect_with_llm(self) -> Optional[List[Tuple[BuildSystem, float]]]:
        """使用LLM检测构建系统（基于文件统计和文件列表）

        Returns:
            检测到的构建系统列表（带概率），按概率从大到小排序，如果无法检测则返回None
            格式: [(BuildSystem, probability), ...]
        """
        # 检查配置文件中是否已有保存的构建系统
        from jarvis.jarvis_code_agent.build_validation_config import (
            BuildValidationConfig,
        )

        config = BuildValidationConfig(self.project_root)
        saved_system = config.get_selected_build_system()
        if saved_system:
            try:
                saved_enum = BuildSystem(saved_system)
                PrettyOutput.auto_print(
                    f"ℹ️ 使用配置文件中保存的构建系统: {saved_system}"
                )
                return [(saved_enum, 1.0)]
            except ValueError:
                # 配置文件中保存的构建系统无效，继续检测
                pass

        # 获取文件统计信息
        file_stats = self._get_file_statistics()

        # 获取git根目录文件列表
        root_files = self._get_git_root_file_list(max_files=50)

        # 获取支持的构建系统列表
        supported_systems = self._get_supported_build_systems()

        # 构建上下文
        stats_text = file_stats if file_stats else "  (无统计信息)"
        # 格式化文件列表，每行前面加 "  - "
        if root_files:
            files_lines = root_files.split("\n")[:30]  # 限制前30个文件
            files_text = "\n".join([f"  - {f}" for f in files_lines])
        else:
            files_text = "  (无文件列表)"
        systems_text = "\n".join([f"  - {sys}" for sys in supported_systems])

        context = f"""请根据以下信息判断项目的构建系统：

文件数量统计（按扩展名，前20项）：
{stats_text}

Git根目录文件列表（前30项）：
{files_text}

当前支持的构建系统：
{systems_text}

请仔细分析文件统计信息和文件列表，判断项目使用的构建系统。
对于每个可能的构建系统，请给出一个概率值（0.0-1.0之间），表示该构建系统的可能性。
如果无法确定，可以返回 "unknown"。

请使用以下格式回答（必须包含且仅包含以下标记，多个构建系统用换行分隔）：
- 如果判断为Rust项目，回答: <BUILD_SYSTEM>rust:0.95</BUILD_SYSTEM>
- 如果判断为Go项目，回答: <BUILD_SYSTEM>go:0.90</BUILD_SYSTEM>
- 如果判断为Java Maven项目，回答: <BUILD_SYSTEM>java_maven:0.85</BUILD_SYSTEM>
- 如果判断为Java Gradle项目，回答: <BUILD_SYSTEM>java_gradle:0.80</BUILD_SYSTEM>
- 如果判断为Node.js项目，回答: <BUILD_SYSTEM>nodejs:0.75</BUILD_SYSTEM>
- 如果判断为Python项目，回答: <BUILD_SYSTEM>python:0.70</BUILD_SYSTEM>
- 如果判断为CMake项目，回答: <BUILD_SYSTEM>c_cmake:0.65</BUILD_SYSTEM>
- 如果判断为Makefile项目，回答: <BUILD_SYSTEM>c_makefile:0.60</BUILD_SYSTEM>
- 如果无法确定，回答: <BUILD_SYSTEM>unknown:0.50</BUILD_SYSTEM>

格式说明：
- 每个构建系统一行，格式为 <BUILD_SYSTEM>系统名称:概率值</BUILD_SYSTEM>
- 概率值范围：0.0-1.0，数值越大表示可能性越高
- 可以返回多个构建系统，每个一行，按概率从高到低排序
- 示例：
  <BUILD_SYSTEM>python:0.85</BUILD_SYSTEM>
  <BUILD_SYSTEM>nodejs:0.30</BUILD_SYSTEM>

请严格按照协议格式回答，不要添加其他内容。
"""

        try:
            # 使用cheap平台进行判断
            from jarvis.jarvis_platform.registry import PlatformRegistry

            platform = PlatformRegistry().get_cheap_platform()

            PrettyOutput.auto_print("🤖 正在使用LLM判断构建系统...")
            response = platform.chat_until_success(context)

            # 解析响应
            detected_systems_with_prob: List[Tuple[BuildSystem, float]] = []
            unknown_probabilities: List[float] = []  # 收集无效构建系统的概率

            # 提取所有BUILD_SYSTEM标记
            matches = re.findall(r"<BUILD_SYSTEM>(.*?)</BUILD_SYSTEM>", response)

            for match in matches:
                match = match.strip()
                # 解析格式：系统名称:概率值
                if ":" in match:
                    parts = match.split(":", 1)
                    system_str = parts[0].strip()
                    try:
                        prob_str = parts[1].strip()
                        probability = float(prob_str)
                        # 确保概率在0.0-1.0之间
                        probability = max(0.0, min(1.0, probability))

                        try:
                            system_enum = BuildSystem(system_str)
                            detected_systems_with_prob.append(
                                (system_enum, probability)
                            )
                        except ValueError:
                            # 无效的构建系统名称，转换为unknown
                            unknown_probabilities.append(probability)
                    except (ValueError, IndexError):
                        # 如果解析失败，尝试不带概率的格式（向后兼容）
                        try:
                            system_enum = BuildSystem(system_str)
                            # 默认概率为0.5
                            detected_systems_with_prob.append((system_enum, 0.5))
                        except ValueError:
                            # 无效的构建系统名称，转换为unknown（默认概率0.5）
                            unknown_probabilities.append(0.5)
                else:
                    # 不带概率的格式（向后兼容）
                    try:
                        system_enum = BuildSystem(match)
                        # 默认概率为0.5
                        detected_systems_with_prob.append((system_enum, 0.5))
                    except ValueError:
                        # 无效的构建系统名称，转换为unknown（默认概率0.5）
                        unknown_probabilities.append(0.5)

            # 如果有无效的构建系统，将它们合并为unknown
            if unknown_probabilities:
                # 使用平均概率，或者如果只有一个，直接使用
                avg_prob = (
                    sum(unknown_probabilities) / len(unknown_probabilities)
                    if unknown_probabilities
                    else 0.5
                )
                # 检查是否已经有unknown，如果有则取最大概率
                existing_unknown = None
                for i, (sys, prob) in enumerate(detected_systems_with_prob):
                    if sys == BuildSystem.UNKNOWN:
                        existing_unknown = i
                        break

                if existing_unknown is not None:
                    # 如果已有unknown，取最大概率
                    max_prob = max(
                        detected_systems_with_prob[existing_unknown][1], avg_prob
                    )
                    detected_systems_with_prob[existing_unknown] = (
                        BuildSystem.UNKNOWN,
                        max_prob,
                    )
                else:
                    # 如果没有unknown，添加一个
                    detected_systems_with_prob.append((BuildSystem.UNKNOWN, avg_prob))

            if detected_systems_with_prob:
                # 按概率从大到小排序
                detected_systems_with_prob.sort(key=lambda x: x[1], reverse=True)
                return detected_systems_with_prob
            else:
                # 如果没有找到有效的构建系统，返回unknown
                return [(BuildSystem.UNKNOWN, 0.5)]

        except Exception as e:
            PrettyOutput.auto_print(f"⚠️ LLM判断构建系统失败: {e}，使用unknown")
            return [(BuildSystem.UNKNOWN, 0.5)]

    def detect_with_llm_and_confirm(self) -> Optional[List[BuildSystem]]:
        """使用LLM检测构建系统，并让用户确认

        Returns:
            用户确认后的构建系统列表，如果用户取消则返回None
        """

        # 检查是否处于非交互模式
        def _is_non_interactive() -> bool:
            try:
                from jarvis.jarvis_utils.config import is_non_interactive

                return bool(is_non_interactive())
            except Exception:
                return False

        detected_systems_with_prob = self.detect_with_llm()

        if not detected_systems_with_prob:
            return None

        # 提取构建系统列表（按概率排序）
        detected_systems = [sys for sys, _ in detected_systems_with_prob]

        # 非交互模式：直接选择概率最高的构建系统
        if _is_non_interactive():
            system, prob = detected_systems_with_prob[0]
            PrettyOutput.auto_print(
                f"ℹ️ 非交互模式：自动选择概率最高的构建系统: {system.value} (概率: {prob:.2%})"
            )
            from jarvis.jarvis_code_agent.build_validation_config import (
                BuildValidationConfig,
            )

            config = BuildValidationConfig(self.project_root)
            config.set_selected_build_system(system.value)
            return detected_systems

        # 如果检测到unknown，直接使用，不询问用户
        if len(detected_systems) == 1 and detected_systems[0] == BuildSystem.UNKNOWN:
            prob = detected_systems_with_prob[0][1]
            PrettyOutput.auto_print(
                f"ℹ️ LLM判断：无法确定构建系统（unknown，概率: {prob:.2%}），直接使用unknown"
            )
            from jarvis.jarvis_code_agent.build_validation_config import (
                BuildValidationConfig,
            )

            config = BuildValidationConfig(self.project_root)
            config.set_selected_build_system("unknown")
            return detected_systems

        # 显示检测结果（按概率从大到小排序）
        PrettyOutput.auto_print("\n🤖 LLM判断结果（按概率从大到小排序）：")
        for idx, (system, prob) in enumerate(detected_systems_with_prob, start=1):
            PrettyOutput.auto_print(f"  {idx}. {system.value} (概率: {prob:.2%})")

        # 显示检测结果
        if len(detected_systems) == 1:
            system, prob = detected_systems_with_prob[0]
            from jarvis.jarvis_code_agent.build_validation_config import (
                BuildValidationConfig,
            )
            from jarvis.jarvis_utils.input import user_confirm

            config = BuildValidationConfig(self.project_root)

            if user_confirm(
                f"是否确认使用 {system.value} 作为构建系统？(概率: {prob:.2%})",
                default=True,
            ):
                config.set_selected_build_system(system.value)
                return detected_systems
            else:
                # 用户不确认，让用户选择（传入带概率的信息以保持排序）
                return self._let_user_select_build_system_with_prob(
                    detected_systems_with_prob
                )
        else:
            # 检测到多个构建系统，让用户选择（传入带概率的信息以保持排序）
            return self._let_user_select_build_system_with_prob(
                detected_systems_with_prob
            )

    def _let_user_select_build_system_with_prob(
        self, detected_systems_with_prob: List[Tuple[BuildSystem, float]]
    ) -> Optional[List[BuildSystem]]:
        """让用户选择构建系统（带概率信息，按概率排序）

        Args:
            detected_systems_with_prob: 检测到的构建系统列表（带概率），已按概率排序

        Returns:
            用户选择的构建系统列表，如果用户取消则返回None
        """

        # 检查是否处于非交互模式
        def _is_non_interactive() -> bool:
            try:
                from jarvis.jarvis_utils.config import is_non_interactive

                return bool(is_non_interactive())
            except Exception:
                return False

        from jarvis.jarvis_code_agent.build_validation_config import (
            BuildValidationConfig,
        )

        config = BuildValidationConfig(self.project_root)

        # 非交互模式：直接选择概率最高的构建系统
        if _is_non_interactive():
            if detected_systems_with_prob:
                selected, prob = detected_systems_with_prob[0]
                PrettyOutput.auto_print(
                    f"ℹ️ 非交互模式：自动选择概率最高的构建系统: {selected.value} (概率: {prob:.2%})"
                )
                config.set_selected_build_system(selected.value)
                return [selected]
            else:
                PrettyOutput.auto_print("ℹ️ 非交互模式：未检测到构建系统，使用unknown")
                config.set_selected_build_system("unknown")
                return [BuildSystem.UNKNOWN]

        PrettyOutput.auto_print("\n请选择构建系统（按概率从大到小排序）：")
        for idx, (system, prob) in enumerate(detected_systems_with_prob, start=1):
            PrettyOutput.auto_print(f"  {idx}. {system.value} (概率: {prob:.2%})")
        PrettyOutput.auto_print(
            f"  {len(detected_systems_with_prob) + 1}. 取消（使用unknown）"
        )

        while True:
            try:
                choice = input(
                    f"\n请选择 (1-{len(detected_systems_with_prob) + 1}): "
                ).strip()
                choice_num = int(choice)

                if 1 <= choice_num <= len(detected_systems_with_prob):
                    selected, prob = detected_systems_with_prob[choice_num - 1]
                    # 保存用户选择
                    config.set_selected_build_system(selected.value)
                    PrettyOutput.auto_print(
                        f"ℹ️ 用户选择构建系统: {selected.value} (概率: {prob:.2%})"
                    )
                    return [selected]
                elif choice_num == len(detected_systems_with_prob) + 1:
                    PrettyOutput.auto_print("ℹ️ 用户取消选择，使用unknown")
                    config.set_selected_build_system("unknown")
                    return [BuildSystem.UNKNOWN]
                else:
                    PrettyOutput.auto_print(
                        f"无效选择，请输入 1-{len(detected_systems_with_prob) + 1}"
                    )
            except ValueError:
                PrettyOutput.auto_print("请输入有效的数字")
            except (KeyboardInterrupt, EOFError):
                PrettyOutput.auto_print("\n用户取消，使用unknown")
                config.set_selected_build_system("unknown")
                return [BuildSystem.UNKNOWN]

    def _let_user_select_build_system(
        self, detected_systems: Optional[List[BuildSystem]] = None
    ) -> Optional[List[BuildSystem]]:
        """让用户选择构建系统（兼容旧接口）

        Args:
            detected_systems: 检测到的构建系统列表，如果为None则显示所有支持的构建系统

        Returns:
            用户选择的构建系统列表，如果用户取消则返回None
        """

        # 检查是否处于非交互模式
        def _is_non_interactive() -> bool:
            try:
                from jarvis.jarvis_utils.config import is_non_interactive

                return bool(is_non_interactive())
            except Exception:
                return False

        from jarvis.jarvis_code_agent.build_validation_config import (
            BuildValidationConfig,
        )

        config = BuildValidationConfig(self.project_root)

        if detected_systems is None:
            # 显示所有支持的构建系统
            all_systems = [
                BuildSystem.RUST,
                BuildSystem.GO,
                BuildSystem.JAVA_MAVEN,
                BuildSystem.JAVA_GRADLE,
                BuildSystem.NODEJS,
                BuildSystem.PYTHON,
                BuildSystem.C_CMAKE,
                BuildSystem.C_MAKEFILE,
                BuildSystem.UNKNOWN,
            ]
            detected_systems = all_systems

        # 非交互模式：直接选择第一个构建系统（或unknown）
        if _is_non_interactive():
            if detected_systems and detected_systems[0] != BuildSystem.UNKNOWN:
                selected_system: BuildSystem = detected_systems[0]
                PrettyOutput.auto_print(
                    f"ℹ️ 非交互模式：自动选择构建系统: {selected_system.value}"
                )
                config.set_selected_build_system(selected_system.value)
                return [selected_system]
            else:
                PrettyOutput.auto_print("ℹ️ 非交互模式：未检测到构建系统，使用unknown")
                config.set_selected_build_system("unknown")
                return [BuildSystem.UNKNOWN]

        PrettyOutput.auto_print("\n请选择构建系统：")
        for idx, system in enumerate(detected_systems, start=1):
            PrettyOutput.auto_print(f"  {idx}. {system.value}")
        PrettyOutput.auto_print(f"  {len(detected_systems) + 1}. 取消（使用unknown）")

        while True:
            try:
                choice = input(f"\n请选择 (1-{len(detected_systems) + 1}): ").strip()
                choice_num = int(choice)

                if 1 <= choice_num <= len(detected_systems):
                    selected_build_system: BuildSystem = detected_systems[
                        choice_num - 1
                    ]
                    # 保存用户选择
                    config.set_selected_build_system(selected_build_system.value)
                    PrettyOutput.auto_print(
                        f"ℹ️ 用户选择构建系统: {selected_build_system.value}"
                    )
                    return [selected_build_system]
                elif choice_num == len(detected_systems) + 1:
                    PrettyOutput.auto_print("ℹ️ 用户取消选择，使用unknown")
                    config.set_selected_build_system("unknown")
                    return [BuildSystem.UNKNOWN]
                else:
                    PrettyOutput.auto_print(
                        f"无效选择，请输入 1-{len(detected_systems) + 1}"
                    )
            except ValueError:
                PrettyOutput.auto_print("请输入有效的数字")
            except (KeyboardInterrupt, EOFError):
                PrettyOutput.auto_print("\n用户取消，使用unknown")
                config.set_selected_build_system("unknown")
                return [BuildSystem.UNKNOWN]
