#!/usr/bin/env bash
#
# jarvis-daemon 跨平台构建脚本。
#
# 默认产出 Linux 与 Windows 的服务程序（amd64 / arm64 各一份），
# 全部为 CGO_ENABLED=0 静态链接，可直接投放到目标机器运行。
#
# 用法：
#   ./scripts/build.sh                          # 构建全部默认目标
#   ./scripts/build.sh --version 5.0.5          # 指定版本号
#   ./scripts/build.sh --targets linux/amd64    # 只构建指定目标
#   ./scripts/build.sh --output /tmp/out        # 自定义输出目录
#   ./scripts/build.sh --clean                  # 构建前清空输出目录
#
# 产物位于 dist/，命名规则 jarvis-daemon_<goos>_<goarch>[.exe]，
# 并生成 dist/SHA256SUMS 供校验。
#
# 说明：daemon 自带 install / uninstall / start / stop / restart / status
# 子命令，构建脚本只负责产出二进制，服务注册由二进制自身完成。

set -euo pipefail

# 脚本所在目录与 daemon 模块根目录（脚本位于 <daemon>/scripts/）。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${MODULE_DIR}/.." && pwd)"

# 默认构建矩阵：Linux 与 Windows 各两个架构。
DEFAULT_TARGETS=(
  "linux/amd64"
  "linux/arm64"
  "windows/amd64"
  "windows/arm64"
)

OUTPUT_DIR="${MODULE_DIR}/dist"
VERSION=""
TARGETS=()
CLEAN=0

# 打印用法。
usage() {
  cat <<'EOF'
用法: build.sh [选项]

选项:
  --version <版本号>   注入的版本号（默认自动探测）
  --targets <列表>     逗号分隔的目标，如 linux/amd64,windows/amd64
                       默认: linux/amd64,linux/arm64,windows/amd64,windows/arm64
  --output <目录>      产物输出目录（默认 <daemon>/dist）
  --clean              构建前清空输出目录
  -h, --help           显示本帮助

版本号探测顺序:
  --version 参数 > 环境变量 VERSION > 仓库根 pyproject.toml > git describe --tags
EOF
}

# 解析命令行参数。
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      [[ -n "${VERSION}" ]] || { echo "错误: --version 需要参数" >&2; exit 2; }
      shift 2
      ;;
    --targets)
      [[ -n "${2:-}" ]] || { echo "错误: --targets 需要参数" >&2; exit 2; }
      IFS=',' read -r -a TARGETS <<< "$2"
      shift 2
      ;;
    --output)
      [[ -n "${2:-}" ]] || { echo "错误: --output 需要参数" >&2; exit 2; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --clean)
      CLEAN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "错误: 未知参数 $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# 检查 Go 工具链。
if ! command -v go >/dev/null 2>&1; then
  echo "错误: 未找到 go 命令。" >&2
  echo "若已安装 Go，请先执行: export PATH=\$PATH:/usr/local/go/bin" >&2
  exit 1
fi

# 探测版本号：参数 > 环境变量 > pyproject.toml > git tag。
detect_version() {
  # --version 参数已写入 VERSION；环境变量 VERSION 作为次优先来源。
  if [[ -n "${VERSION}" ]]; then
    echo "${VERSION}"
    return
  fi
  local pyproject="${REPO_ROOT}/pyproject.toml"
  if [[ -f "${pyproject}" ]]; then
    local v
    v="$(grep -m1 -E '^version[[:space:]]*=' "${pyproject}" \
      | sed -E 's/^version[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/')"
    if [[ -n "${v}" ]]; then
      echo "${v}"
      return
    fi
  fi
  if command -v git >/dev/null 2>&1; then
    local tag
    tag="$(git -C "${REPO_ROOT}" describe --tags --always 2>/dev/null || true)"
    if [[ -n "${tag}" ]]; then
      echo "${tag}"
      return
    fi
  fi
  echo "0.0.0-dev"
}

VERSION="$(detect_version)"

# 未显式指定目标时使用默认矩阵。
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=("${DEFAULT_TARGETS[@]}")
fi

if [[ "${CLEAN}" -eq 1 ]]; then
  rm -rf "${OUTPUT_DIR}"
fi
mkdir -p "${OUTPUT_DIR}"

echo "==> jarvis-daemon 构建"
echo "    模块目录: ${MODULE_DIR}"
echo "    输出目录: ${OUTPUT_DIR}"
echo "    版本号:   ${VERSION}"
echo "    目标:     ${TARGETS[*]}"
echo

# 逐个目标构建。
built=()
for target in "${TARGETS[@]}"; do
  goos="${target%%/*}"
  goarch="${target##*/}"
  if [[ -z "${goos}" || -z "${goarch}" || "${goos}" == "${goarch}" ]]; then
    echo "错误: 非法目标 '${target}'，应为 <goos>/<goarch>" >&2
    exit 2
  fi

  ext=""
  if [[ "${goos}" == "windows" ]]; then
    ext=".exe"
  fi
  out="${OUTPUT_DIR}/jarvis-daemon_${goos}_${goarch}${ext}"

  echo "--> 构建 ${goos}/${goarch}"
  # CGO_ENABLED=0 保证静态链接，不依赖目标机 glibc 版本；
  # -trimpath 去除本地路径；-s -w 去掉符号表与调试信息。
  CGO_ENABLED=0 GOOS="${goos}" GOARCH="${goarch}" \
    go build -trimpath \
      -ldflags "-s -w -X main.version=${VERSION}" \
      -o "${out}" ./cmd/jarvis-daemon

  built+=("${out}")
done

# 生成校验和文件。
echo
echo "==> 生成校验和"
(
  cd "${OUTPUT_DIR}"
  # 只对本次构建的产物计算，避免把历史文件混入。
  for f in "${built[@]}"; do
    basename "${f}"
  done | xargs sha256sum > SHA256SUMS
)
echo "    ${OUTPUT_DIR}/SHA256SUMS"

# 汇总产物。
echo
echo "==> 构建完成，产物如下:"
for f in "${built[@]}"; do
  size="$(du -h "${f}" | cut -f1)"
  printf '    %-48s %s\n' "$(basename "${f}")" "${size}"
done

echo
echo "提示: 部署到目标机器后，用 '<二进制> install' 注册为系统服务，"
echo "      Linux 为 systemd 用户服务，Windows 为登录时计划任务。"
