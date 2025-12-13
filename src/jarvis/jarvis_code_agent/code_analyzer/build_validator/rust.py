"""
Rust构建验证器模块

提供Rust项目的构建验证功能。
"""

import os
import subprocess
import time

from jarvis.jarvis_utils.output import PrettyOutput

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List
from typing import Optional

from .base import BuildResult
from .base import BuildSystem
from .base import BuildValidatorBase


class RustBuildValidator(BuildValidatorBase):
    """Rust构建验证器（使用cargo test，包括编译和测试）"""

    BUILD_SYSTEM_NAME = "Cargo"
    SUPPORTED_LANGUAGES = ["rust"]

    def validate(self, modified_files: Optional[List[str]] = None) -> BuildResult:
        start_time = time.time()

        # 使用 cargo test 进行构建和测试验证（会自动编译并运行测试，包括文档测试）
        # 设置 RUST_BACKTRACE=1 以启用调用链回溯
        # 设置 RUSTFLAGS="-A warnings" 以屏蔽警告，只显示错误
        cmd = ["cargo", "test", "--", "--nocapture"]

        # 准备环境变量（继承当前环境并设置 RUST_BACKTRACE 和 RUSTFLAGS）
        env = os.environ.copy()
        env["RUST_BACKTRACE"] = "1"
        # 如果已存在 RUSTFLAGS，则追加；否则新建
        if "RUSTFLAGS" in env:
            env["RUSTFLAGS"] = env["RUSTFLAGS"] + " -A warnings"
        else:
            env["RUSTFLAGS"] = "-A warnings"

        # 直接使用 subprocess.run 以支持环境变量
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                timeout=self.timeout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired:
            returncode = -1
            stdout = ""
            stderr = f"命令执行超时（{self.timeout}秒）"
        except FileNotFoundError:
            returncode = -1
            stdout = ""
            stderr = f"命令未找到: {cmd[0]}"
        except Exception as e:
            returncode = -1
            stdout = ""
            stderr = f"执行命令时出错: {str(e)}"

        duration = time.time() - start_time

        success = returncode == 0
        output = stdout + stderr

        if not success:
            # 尝试解析错误信息（包括编译错误和测试失败）
            error_message = self._parse_cargo_errors(output)
            PrettyOutput.auto_print(f"❌ Rust 构建验证失败（耗时 {duration:.2f} 秒）")
            if error_message:
                PrettyOutput.auto_print(f"错误信息：\n{error_message}")
            else:
                PrettyOutput.auto_print(f"输出：\n{output[:500]}")
        else:
            error_message = None
            PrettyOutput.auto_print(f"✅ Rust 构建验证成功（耗时 {duration:.2f} 秒）")

        return BuildResult(
            success=success,
            output=output,
            error_message=error_message,
            build_system=BuildSystem.RUST,
            duration=duration,
        )

    def _parse_cargo_errors(self, output: str, context_lines: int = 20) -> str:
        """解析cargo的错误输出（包括编译错误和测试失败）

        Args:
            output: cargo test 的完整输出
            context_lines: 每个错误周围保留的上下文行数（默认20行）

        Returns:
            提取的错误信息，包含失败测试用例及其上下文
        """
        lines = output.split("\n")
        error_sections = []

        # 1. 查找失败的测试用例
        failed_tests = []
        for i, line in enumerate(lines):
            # 匹配失败的测试用例行，如 "test tests::test_name ... FAILED"
            if "test" in line and "FAILED" in line:
                # 提取测试名称
                if "test " in line:
                    parts = line.split()
                    for j, part in enumerate(parts):
                        if part == "test" and j + 1 < len(parts):
                            test_name = parts[j + 1]
                            if "..." in test_name:
                                test_name = test_name.replace("...", "")
                            failed_tests.append((i, test_name, line))
                            break

        # 2. 为每个失败的测试提取完整输出块
        if failed_tests:
            for test_idx, (line_idx, test_name, test_line) in enumerate(failed_tests):
                # 找到这个测试的开始位置（向上查找，找到 "running" 或测试名称）
                start_idx = max(0, line_idx - 10)
                # 向上查找，找到测试开始标记
                for i in range(line_idx - 1, max(0, line_idx - 100), -1):
                    # 查找 "running" 行，通常格式为 "running 1 test" 或包含测试名称
                    if "running" in lines[i].lower():
                        start_idx = i
                        break
                    # 或者找到前一个测试的结束标记
                    if (
                        i > 0
                        and "test " in lines[i]
                        and ("ok" in lines[i].lower() or "FAILED" in lines[i])
                    ):
                        start_idx = i + 1
                        break

                # 找到这个测试的结束位置（向下查找，找到下一个测试或测试总结）
                end_idx = min(len(lines), line_idx + context_lines)
                # 向下查找，找到测试块的结束
                for i in range(line_idx + 1, min(len(lines), line_idx + 500)):
                    # 遇到下一个测试用例行（格式：test xxx ... ok/FAILED）
                    if "test " in lines[i] and "..." in lines[i]:
                        end_idx = i
                        break
                    # 遇到测试总结行
                    if "test result:" in lines[i].lower():
                        end_idx = i
                        break
                    # 遇到新的 "running" 行，表示下一组测试开始
                    if "running" in lines[i].lower() and i > line_idx + 5:
                        end_idx = i
                        break

                # 提取这个测试的完整输出
                test_output = "\n".join(lines[start_idx:end_idx])
                if test_output.strip():
                    error_sections.append(
                        f"=== 失败的测试: {test_name} ===\n{test_output}"
                    )

        # 3. 如果没有找到失败的测试，查找编译错误
        if not error_sections:
            error_lines = []
            in_error_block = False
            error_start = -1

            for i, line in enumerate(lines):
                # 检测错误开始
                if "error[" in line or (
                    "error:" in line.lower() and "error[" not in line
                ):
                    if not in_error_block:
                        error_start = max(0, i - 2)  # 包含错误前2行上下文
                        in_error_block = True
                elif in_error_block:
                    # 错误块结束条件：空行后跟非错误行，或遇到新的错误
                    if line.strip() == "":
                        # 检查下一行是否是新的错误
                        if i + 1 < len(lines) and (
                            "error[" not in lines[i + 1]
                            and "error:" not in lines[i + 1].lower()
                        ):
                            # 结束当前错误块
                            error_lines.extend(lines[error_start : i + 1])
                            in_error_block = False
                    elif i - error_start > context_lines:
                        # 错误块太长，截断
                        error_lines.extend(lines[error_start:i])
                        in_error_block = False
                        if "error[" in line or "error:" in line.lower():
                            error_start = max(0, i - 2)
                            in_error_block = True

            # 处理最后一个错误块
            if in_error_block:
                error_lines.extend(
                    lines[error_start : min(len(lines), error_start + context_lines)]
                )

            if error_lines:
                error_sections.append("\n".join(error_lines))

        # 4. 如果仍然没有找到错误，查找其他错误模式
        if not error_sections:
            for i, line in enumerate(lines):
                if (
                    "panic" in line.lower()
                    or ("assertion" in line.lower() and "failed" in line.lower())
                    or "thread" in line.lower()
                    and "panicked" in line.lower()
                ):
                    start = max(0, i - 3)
                    end = min(len(lines), i + context_lines)
                    error_sections.append("\n".join(lines[start:end]))
                    break

        # 5. 如果找到了错误信息，返回；否则返回原始输出的前500字符
        if error_sections:
            result = "\n\n".join(error_sections)
            # 限制总长度，避免过长
            if len(result) > 5000:
                result = result[:5000] + "\n... (输出已截断)"
            return result
        else:
            return output[:500]  # 如果没有找到特定错误，返回前500字符
