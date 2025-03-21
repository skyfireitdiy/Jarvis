from setuptools import setup, find_packages
from setuptools.command.install import install
import subprocess

# 自定义安装命令
class CustomInstallCommand(install):
    def run(self):
        # 先运行默认的安装逻辑
        install.run(self)
        # 安装完成后执行 playwright install
        subprocess.check_call(["playwright", "install"])

setup(
    name="jarvis-ai-assistant",
    version="0.1.131",
    author="skyfire",
    author_email="skyfireitdiy@hotmail.com",
    description="An AI assistant that uses various tools to interact with the system",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/skyfireitdiy/Jarvis",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "requests>=2.25.1",
        "pyyaml>=5.1",
        "colorama>=0.4.6",
        "prompt_toolkit>=3.0.0",
        "openai>=1.20.0",
        "playwright>=1.41.1",
        "numpy>=1.19.5",
        "faiss-cpu>=1.8.0",
        "sentence-transformers>=2.2.2",
        "bs4>=0.0.1",
        "PyMuPDF>=1.21.0",
        "python-docx>=0.8.11",
        "tiktoken>=0.3.0",
        "tqdm>=4.65.0",
        "docx>=0.2.4",
        "yaspin>=2.5.0",
        "rich>=13.3.1",
        "pygments>=2.15.0",
        "fuzzywuzzy>=0.18.0",
        "python-Levenshtein>=0.25.0",
        "jedi>=0.17.2",
        "psutil>=7.0.0",
        "fastapi>=0.115.4",
        "uvicorn>=0.33.0",
        "python-pptx>=1.0.0",
        "pandas>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "jarvis=jarvis.jarvis_agent:main",
            "jarvis-code-agent=jarvis.jarvis_code_agent.code_agent:main",
            "jca=jarvis.jarvis_code_agent.code_agent:main",
            "jarvis-codebase=jarvis.jarvis_codebase.main:main",
            "jarvis-rag=jarvis.jarvis_rag.main:main",
            "jarvis-smart-shell=jarvis.jarvis_smart_shell.main:main",
            "jss=jarvis.jarvis_smart_shell.main:main",
            "jarvis-platform-manager=jarvis.jarvis_platform_manager.main:main",
            "jarvis-git-commit=jarvis.jarvis_tools.git_commiter:main",
            "jarvis-code-review=jarvis.jarvis_tools.code_review:main",
            "jgc=jarvis.jarvis_tools.git_commiter:main",
            "jarvis-dev=jarvis.jarvis_dev.main:main",
            "jarvis-git-squash=jarvis.jarvis_git_squash.main:main",
            "jarvis-multi-agent=jarvis.jarvis_multi_agent:main",
            "jarvis-agent=jarvis.jarvis_agent.main:main",
            "jarvis-tool=jarvis.jarvis_tools.registry:main",
            "jarvis-ask-codebase=jarvis.jarvis_tools.ask_codebase:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    cmdclass={
        'install': CustomInstallCommand,  # 注册自定义安装命令
    },
)
