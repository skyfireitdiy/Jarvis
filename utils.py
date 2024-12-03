def print_colored(text: str, color: str = "white") -> None:
    """打印彩色文本"""
    colors = {
        "red": "\033[91m",
        "green": "\033[92m",
        "blue": "\033[94m",
        "yellow": "\033[93m",
        "white": "\033[0m",
        "cyan": "\033[96m",
        "magenta": "\033[95m"
    }
    print(f"{colors.get(color, colors['white'])}{text}{colors['white']}") 