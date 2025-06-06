# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="jarvis-ai-assistant",
    version="0.1.197",
    author="skyfire",
    author_email="skyfireitdiy@hotmail.com",
    description="An AI assistant that uses various tools to interact with the system",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/skyfireitdiy/Jarvis",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    package_data={
        "jarvis": [
            "jarvis_data/huggingface.tar.gz",
            "jarvis_data/config_schema.json"
        ],
    },
    install_requires=[
        "requests==2.32.3",
        "colorama==0.4.6",
        "prompt_toolkit==3.0.50",
        "yaspin==2.4.0",
        "pygments==2.19.1",
        "fuzzywuzzy==0.18.0",
        "fastapi==0.115.12",
        "uvicorn==0.33.0",
        "rich==14.0.0",
        "transformers==4.46.3",
        "torch==2.4.1",
        "python-Levenshtein==0.25.1",
        "pillow==10.2.0",
        "openai==1.78.1",
        "tabulate==0.9.0",
        "pyte==0.8.2",
    ],
    extras_require={
        "dev": ["pytest", "black", "isort", "mypy", "build", "twine"]
    },
    entry_points={
        "console_scripts": [
            "jarvis=jarvis.jarvis_agent.jarvis:main",
            "jarvis-code-agent=jarvis.jarvis_code_agent.code_agent:main",
            "jca=jarvis.jarvis_code_agent.code_agent:main",
            "jarvis-smart-shell=jarvis.jarvis_smart_shell.main:main",
            "jss=jarvis.jarvis_smart_shell.main:main",
            "jarvis-platform-manager=jarvis.jarvis_platform_manager.main:main",
            "jarvis-code-review=jarvis.jarvis_code_analysis.code_review:main",
            "jarvis-git-commit=jarvis.jarvis_git_utils.git_commiter:main", 
            "jgc=jarvis.jarvis_git_utils.git_commiter:main",
            "jarvis-dev=jarvis.jarvis_dev.main:main",
            "jarvis-git-squash=jarvis.jarvis_git_squash.main:main",
            "jarvis-multi-agent=jarvis.jarvis_multi_agent.main:main",
            "jarvis-agent=jarvis.jarvis_agent.main:main",
            "jarvis-tool=jarvis.jarvis_tools.cli.main:main",
            "jarvis-git-details=jarvis.jarvis_git_details.main:main",
            "jarvis-methodology=jarvis.jarvis_methodology.main:main",
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
)
