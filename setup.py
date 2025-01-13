from setuptools import setup, find_packages

setup(
    name="jarvis-ai-assistant",
    version="0.1.30",
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
    ],
    entry_points={
        "console_scripts": [
            "jarvis=jarvis.main:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
) 