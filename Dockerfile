FROM python:3.8.20

# 设置中科大镜像源并增加超时和重试参数
RUN pip config set global.index-url https://pypi.mirrors.ustc.edu.cn/simple/ && \
    pip config set global.timeout 60 && \
    pip config set global.retries 5

# 创建工作目录
WORKDIR /app

# 拷贝项目文件到/jarvis目录
COPY setup.py /jarvis/
COPY README.md /jarvis/
COPY src/ /jarvis/src/

# 安装项目依赖
RUN pip install -e /jarvis --default-timeout=100 --retries 5
