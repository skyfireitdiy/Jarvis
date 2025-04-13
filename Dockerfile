FROM python:3.8.20

# 设置中科大镜像源
RUN pip config set global.index-url https://pypi.mirrors.ustc.edu.cn/simple/

# 创建工作目录
WORKDIR /app

# 拷贝项目文件到/jarvis目录
COPY setup.py /jarvis/
COPY src/ /jarvis/src/
COPY scripts/ /jarvis/scripts/

# 安装项目依赖
RUN pip install -e /jarvis
