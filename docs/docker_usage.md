# Docker 使用指南

> 本文档说明如何使用 Jarvis 的 Docker 镜像开箱即用。镜像已预装 Python 环境、
> 依赖与前端构建工具，无需本地安装 Python / Rust。
> 镜像定义见仓库根目录 [`Dockerfile`](../Dockerfile)，编排定义见 [`docker-compose.yml`](../docker-compose.yml)。

## 一、镜像来源与标签

镜像发布在 GitHub Container Registry：

```text
ghcr.io/skyfireitdiy/jarvis
```

标签规则由 [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml)
定义，在推送 `v*` 形式的 Git tag 时自动构建并推送：

| 标签 | 说明 |
| --- | --- |
| `latest` | 最新发布版本 |
| `{{version}}` | 完整语义化版本，如 `6.1.0` |
| `{{major}}.{{minor}}` | 主次版本，如 `6.1` |
| `{{major}}` | 主版本，如 `6` |

## 二、快速开始

### 方式一：docker compose（推荐）

仓库根目录已提供 `docker-compose.yml`，直接启动：

```bash
cd /path/to/your/project
docker compose up -d
```

该编排会：

- 使用镜像 `ghcr.io/skyfireitdiy/jarvis:latest`；
- 以 `user: "1000:${GID:-1000}"` 运行（容器内为 UID 1000 的 `jarvis` 用户，
  组 ID 取宿主机 `GID`，避免容器内创建的文件在宿主机上无法访问）；
- 挂载卷：
  - `.:/workspace`：当前目录挂到容器工作目录；
  - `${HOME}/.jarvis:/home/jarvis/.jarvis`：保留本地 Jarvis 配置（可选）；
  - `${HOME}/.gitconfig:/home/jarvis/.gitconfig:ro`：保留 Git 用户信息（可选，只读）；
- 工作目录为 `/workspace`，开启 `stdin_open` / `tty` 便于交互。

> 若宿主机用户组 ID 不是 1000，可在启动前导出：`export GID=$(id -g)`。

进入容器交互使用：

```bash
docker compose exec jarvis bash
```

### 方式二：docker run

不使用 compose 时可直接运行：

```bash
docker run -it --rm \
  --user "1000:$(id -g)" \
  -v "$PWD:/workspace" \
  -v "$HOME/.jarvis:/home/jarvis/.jarvis" \
  -v "$HOME/.gitconfig:/home/jarvis/.gitconfig:ro" \
  -p 8000:8000 -p 5173:5173 \
  -w /workspace \
  ghcr.io/skyfireitdiy/jarvis:latest
```

容器默认命令为（见 `Dockerfile` 末尾）：

```text
jarvis-service run --gateway-host 0.0.0.0 --gateway-port 8000 \
  --frontend-host 0.0.0.0 --frontend-port 5173
```

即启动 Web 服务（网关 + 前端），监听 `0.0.0.0` 以便容器外访问。

### 方式三：只启动 Gateway（不含前端）

镜像内置 `jarvis-web-gateway`（短命令 `jwg`），可单独启动 Web 网关，
适合只提供 API/网关、或作为分布式部署中的子节点。

```bash
docker run -it --rm \
  -p 8000:8000 \
  ghcr.io/skyfireitdiy/jarvis:latest \
  jwg --host 0.0.0.0 --port 8000
```

`jwg` 支持的参数（见 `src/jarvis/jarvis_web_gateway/cli.py`）：

| 参数 | 说明 |
| --- | --- |
| `--host` / `-h` | 监听地址（默认 `127.0.0.1`，容器内需设为 `0.0.0.0`） |
| `--port` / `-p` | 监听端口（默认 `8000`） |
| `--node-mode` | 节点模式：`master` 或 `child`（默认 `master`） |
| `--node-id` | 当前节点 ID（`child` 模式必填） |
| `--master-url` | 主节点 URL（`child` 模式必填） |
| `--node-secret` | 节点共享密钥（`child` 模式必填） |

> 说明：`jarvis-service run`（容器默认命令）本身也会拉起 `jwg` 进程，
> 因此默认启动方式已包含 Gateway；仅当不需要前端时才用本方式单独启动。

### 方式四：自定义 docker-compose 示例

仓库自带的 `docker-compose.yml` 是最简用法。下面给出两个常见场景的示例，
可直接保存为 `docker-compose.yml` 使用。

#### 示例 1：Gateway + 前端（自定义端口与配置目录）

```yaml
services:
  jarvis:
    image: ghcr.io/skyfireitdiy/jarvis:latest
    container_name: jarvis
    user: "1000:${GID:-1000}"
    ports:
      - "8000:8000"   # Gateway
      - "5173:5173"   # 前端
    volumes:
      - .:/workspace
      - ${HOME}/.jarvis:/home/jarvis/.jarvis
      - ${HOME}/.gitconfig:/home/jarvis/.gitconfig:ro
    working_dir: /workspace
    environment:
      - TERM=${TERM:-xterm-256color}
    stdin_open: true
    tty: true
    restart: unless-stopped
```

#### 示例 2：仅 Gateway，作为子节点接入主节点

```yaml
services:
  jarvis-gateway:
    image: ghcr.io/skyfireitdiy/jarvis:latest
    container_name: jarvis-gateway
    user: "1000:${GID:-1000}"
    ports:
      - "8001:8000"
    command: >
      jwg --host 0.0.0.0 --port 8000
          --node-mode child
          --node-id worker-1
          --master-url http://<主节点地址>:8000
          --node-secret <节点密钥>
    volumes:
      - ${HOME}/.jarvis:/home/jarvis/.jarvis
    restart: unless-stopped
```

> `--master-url` / `--node-secret` 需替换为主节点实际地址与密钥
> （密钥可在主节点通过 `get_node_secret` 获取）。

## 三、首次运行与 API Key 配置

首次运行 `jvs` / `jca` 等命令会启动交互式配置向导，生成 `~/.jarvis/config.yaml`。

在容器场景下，配置文件位于容器内 `/home/jarvis/.jarvis/config.yaml`；
通过 compose / `docker run` 挂载宿主机的 `~/.jarvis` 后，配置会持久化到宿主机，
下次启动可直接复用。

也可以直接编辑宿主机 `~/.jarvis/config.yaml`，示例：

```yaml
llm_group: default
llm_groups:
  default:
    normal_llm: gpt-5
llms:
  gpt-5:
    platform: openai
    model: gpt-5
    max_input_token_count: 128000
    llm_config:
      openai_api_key: "your-api-key-here"
```

更多配置项见 [使用指南](jarvis_book/4.使用指南.md)。

## 四、端口与访问

| 端口 | 用途 |
| --- | --- |
| `8000` | Web 网关（gateway） |
| `5173` | 前端页面 |

容器默认监听 `0.0.0.0`，在 `docker run` 中通过 `-p` 映射到宿主机后，
浏览器访问 `http://localhost:5173` 即可使用。

## 五、常见问题

### 文件权限问题

容器内以 UID 1000 运行。若宿主机用户 UID/GID 不是 1000，容器内创建的文件
可能归属异常。启动前设置 `export GID=$(id -g)`，并确保挂载目录对 UID 1000 可写。

### 网络与代理

容器内需要访问外部 LLM API。若宿主机通过代理联网，注意容器内
`127.0.0.1` 指向容器自身而非宿主机，需改用宿主机可达的代理地址
（如 `--network host` 或 `http://host.docker.internal:<port>`）。

### 无网络 / 内网环境

离线环境请使用离线安装包（见 [离线安装指南](offline_installation.md)），
或在联网机器上构建镜像后导出：

```bash
docker save ghcr.io/skyfireitdiy/jarvis:latest -o jarvis.tar
# 目标机器
docker load -i jarvis.tar
```

### 镜像体积

镜像预装了 clang 工具链、前端依赖与 Python 工具，体积较大；如需精简，
可基于 `Dockerfile` 裁剪不需要的构建阶段。
