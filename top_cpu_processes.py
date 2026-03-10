#!/usr/bin/env python3
#
# 获取系统中CPU使用率最高的5个进程
# 该脚本使用ps命令获取进程信息，并按CPU使用率排序输出前5个进程
#
import subprocess
import sys


def get_top_cpu_processes(count=5):
    """
    获取CPU使用率最高的进程列表
    
    Args:
        count (int): 返回的进程数量，默认为5
        
    Returns:
        list: 包含进程信息的列表
    """
    try:
        # 使用ps命令获取进程信息，按CPU使用率排序
        # -eo pid,pcpu,comm: 显示进程ID、CPU使用率、命令名
        # --sort=-pcpu: 按CPU使用率降序排序
        cmd = ["ps", "-eo", "pid,pcpu,comm", "--sort=-pcpu", "--no-headers"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # 解析输出，获取进程信息
        lines = result.stdout.strip().split('\n')
        processes = []
        
        # 只取前count个进程
        for line in lines[:count]:
            if line.strip():
                parts = line.split(None, 2)  # 最多分割成3部分，避免命令名中的空格被误分割
                if len(parts) >= 3:
                    pid = parts[0]
                    cpu_percent = parts[1]
                    command = parts[2]
                    processes.append({
                        "pid": pid,
                        "cpu_percent": cpu_percent,
                        "command": command
                    })
        
        return processes
    except subprocess.CalledProcessError as e:
        print(f"执行ps命令时出错: {e}")
        return []
    except Exception as e:
        print(f"获取进程信息时出错: {e}")
        return []


def main():
    """
    主函数，获取并显示CPU使用率最高的5个进程
    """
    print("系统中CPU使用率最高的5个进程：")
    print("{:<10} {:<10} {}".format("PID", "CPU%", "COMMAND"))
    print("-" * 50)
    
    processes = get_top_cpu_processes(5)
    
    if not processes:
        print("未能获取进程信息")
        sys.exit(1)
    
    for process in processes:
        print("{:<10} {:<10} {}".format(
            process["pid"], 
            process["cpu_percent"], 
            process["command"]
        ))


if __name__ == "__main__":
    main()
