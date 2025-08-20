# -*- coding: utf-8 -*-
import platform
import subprocess

from jarvis.jarvis_utils.output import OutputType, PrettyOutput


def copy_to_clipboard(text: str) -> None:
    """将文本复制到剪贴板，支持Windows、macOS和Linux

    参数:
        text: 要复制的文本
    """
    PrettyOutput.print("--- 剪贴板内容开始 ---", OutputType.INFO)
    print(text)
    PrettyOutput.print("--- 剪贴板内容结束 ---", OutputType.INFO)

    system = platform.system()

    # Windows系统
    if system == "Windows":
        try:
            # 使用Windows的clip命令
            process = subprocess.Popen(
                ["clip"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except Exception as e:
            PrettyOutput.print(f"使用Windows clip命令时出错: {e}", OutputType.WARNING)

    # macOS系统
    elif system == "Darwin":
        try:
            process = subprocess.Popen(
                ["pbcopy"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except Exception as e:
            PrettyOutput.print(f"使用macOS pbcopy命令时出错: {e}", OutputType.WARNING)

    # Linux系统
    else:
        # 尝试使用 xsel
        try:
            process = subprocess.Popen(
                ["xsel", "-b", "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except FileNotFoundError:
            pass  # xsel 未安装，继续尝试下一个
        except Exception as e:
            PrettyOutput.print(f"使用xsel时出错: {e}", OutputType.WARNING)

        # 尝试使用 xclip
        try:
            process = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if process.stdin:
                process.stdin.write(text.encode("utf-8"))
                process.stdin.close()
            return
        except FileNotFoundError:
            PrettyOutput.print(
                "xsel 和 xclip 均未安装, 无法复制到剪贴板", OutputType.WARNING
            )
        except Exception as e:
            PrettyOutput.print(f"使用xclip时出错: {e}", OutputType.WARNING)
