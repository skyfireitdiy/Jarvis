"""Jarvis TUI 入口点"""

from jarvis.jarvis_tui.app import JarvisTUI


def main():
    """启动Jarvis TUI应用"""
    app = JarvisTUI()
    app.run()


if __name__ == "__main__":
    main()
