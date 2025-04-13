FROM python:3.8.20

# 设置中科大镜像源
RUN pip config set global.index-url https://pypi.mirrors.ustc.edu.cn/simple/

# 创建工作目录
WORKDIR /app

# 拷贝项目文件
COPY setup.py .
COPY src/ ./src/
COPY scripts/ ./scripts/

# 安装项目依赖
RUN pip install -e .

# 设置默认运行命令
CMD ["python", "-m", "src.jarvis.jarvis_agent.main"]
