FROM python:3.8.20

# 创建工作目录
WORKDIR /workspace

# 拷贝项目文件到/jarvis目录
COPY setup.py /jarvis/
COPY README.md /jarvis/
COPY src/ /jarvis/src/

# 安装项目依赖
RUN pip install -e /jarvis --default-timeout=3600 -i http://mirrors.cloud.tencent.com/pypi/simple --trusted-host mirrors.cloud.tencent.com