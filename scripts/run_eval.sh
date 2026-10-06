#!/bin/bash
# shellcheck disable=SC2218  # 误报：辅助函数(check_prereq/echo_*)均定义于 setup/run_eval 之前
# =============================================================================
# Jarvis Terminal-Bench 2.0 评测环境搭建与运行脚本
#
# 功能：
#   1. 用 uv 创建隔离的 Harbor 评测虚拟环境（避免污染系统 Python）
#   2. 安装 harbor（Terminal-Bench 2.0 评测框架）
#   3. 下载 terminal-bench@2.0 数据集到本地缓存
#   4. 运行 harbor run，用 jarvis_eval 适配层评测 Jarvis
#
# 用法：
#   # 只搭建环境（创建 venv + 安装 harbor + 下载数据集）
#   ./scripts/run_eval.sh setup
#
#   # 运行评测（需先 export OPENAI_API_KEY=sk-xxx）
#   OPENAI_API_KEY=sk-xxx ./scripts/run_eval.sh run [--n-concurrent N] [--n-tasks N]
#
#   # 查看 harbor run 帮助
#   ./scripts/run_eval.sh help
#
# 说明：
#   - 完整评测需要真实 LLM API key（通过 --ae 透传给容器内的 jca 进程）
#   - 评测容器内会 pip install jarvis-ai-assistant（PyPI 发布版），
#     若需用本机最新源码评测，请先发布到 PyPI 或调整适配层 install()
# =============================================================================
set -euo pipefail

# ===== 配置 =====
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${EVAL_VENV_DIR:-$HOME/.jarvis-eval-venv}"
HARBOR_VERSION="${HARBOR_VERSION:-harbor}"
# 评测容器内安装的 jarvis-ai-assistant 版本；latest=PyPI 最新版，可指定如 6.0.10
JCA_VERSION="${JCA_VERSION:-latest}"
# 置 1 时强制重建离线 wheelhouse（否则缓存命中即跳过，发新版本后需置 1 更新）
JCA_FORCE_REBUILD="${JCA_FORCE_REBUILD:-0}"

# 本机代理环境变量会导致 pip/uv 安装失败，安装时直连
PROXY_UNSET="env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY"

# ===== 颜色输出 =====
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
echo_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
echo_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
echo_err() { echo -e "${RED}[ERROR]${NC} $1"; }

# ===== 前置检查 =====
check_prereq() {
	if ! command -v uv >/dev/null 2>&1; then
		echo_err "未找到 uv，请先安装：curl -LsSf https://astral.sh/uv/install.sh | sh"
		exit 1
	fi
	if ! command -v docker >/dev/null 2>&1; then
		echo_err "未找到 docker，Terminal-Bench 2.0 评测需要 Docker 隔离环境"
		exit 1
	fi
	if ! docker info >/dev/null 2>&1; then
		echo_err "Docker daemon 未运行，请先启动 docker"
		exit 1
	fi
}

# ===== 构建离线 wheelhouse（本机预下载依赖，供容器离线安装） =====
# 容器内直连 PyPI 下载大包（playwright 38MB 等）网络不稳，易中途超时/损坏。
# 在本机用与容器相同的 Python 3.12 预下载所有依赖到 wheelhouse，评测时
# 上传容器并用 --no-index --find-links 完全离线安装，彻底绕开该问题。
build_wheelhouse() {
	local wh_dir="${JARVIS_WHEELHOUSE_DIR:-$HOME/.cache/harbor/wheelhouse}"
	# marker 记录实际构建的版本（不依赖版本号文件名，发新版本后仍能正确判断）
	local wh_marker="$wh_dir/.built"
	if [ -f "$wh_marker" ] && [ "$JCA_FORCE_REBUILD" != "1" ]; then
		echo_info "wheelhouse 已存在，跳过构建: $wh_dir ($(cat "$wh_marker"))"
		return 0
	fi
	echo_info "构建离线 wheelhouse: $wh_dir (JCA_VERSION=$JCA_VERSION)"
	local wh_venv="$HOME/.cache/harbor/wh-venv"
	if [ ! -x "$wh_venv/bin/python" ]; then
		uv venv "$wh_venv" --python 3.12
		$PROXY_UNSET uv pip install --python "$wh_venv/bin/python" pip
	fi
	mkdir -p "$wh_dir"
	# 用 Python 3.12 下载依赖，确保 wheel 平台/ABI 与容器（Ubuntu 24.04 + 3.12）兼容
	# 默认取 PyPI 最新版（JCA_VERSION=latest），也可指定具体版本
	local jca_spec="jarvis-ai-assistant"
	[ "$JCA_VERSION" != "latest" ] && jca_spec="jarvis-ai-assistant==$JCA_VERSION"
	$PROXY_UNSET "$wh_venv/bin/python" -m pip download \
		--no-cache-dir --dest "$wh_dir" "$jca_spec"
	# jieba 仅提供 sdist，离线构建需 setuptools/wheel
	$PROXY_UNSET "$wh_venv/bin/python" -m pip download \
		--no-cache-dir --dest "$wh_dir" setuptools wheel
	# 从下载的 wheel 文件名解析实际版本写入 marker
	local built_ver wheel_files=("$wh_dir"/jarvis_ai_assistant-*.whl)
	if [ -e "${wheel_files[0]}" ]; then
		built_ver="$(basename "${wheel_files[0]}" .whl | sed -E 's/jarvis_ai_assistant-([0-9][^-]*).*/\1/')"
	else
		built_ver="$JCA_VERSION"
	fi
	echo "$built_ver" >"$wh_marker"
	echo_info "wheelhouse 构建完成: $wh_dir (jarvis-ai-assistant $built_ver)"
}

# ===== 1. 创建 venv 并安装 harbor =====
setup() {
	check_prereq
	if [ ! -x "$VENV_DIR/bin/harbor" ]; then
		echo_info "创建评测虚拟环境: $VENV_DIR"
		uv venv "$VENV_DIR" --python 3.14
		echo_info "安装 harbor ($HARBOR_VERSION)..."
		$PROXY_UNSET uv pip install --python "$VENV_DIR/bin/python" "$HARBOR_VERSION"
	else
		echo_info "评测虚拟环境已存在，跳过创建: $VENV_DIR"
	fi
	echo_info "harbor 版本: $("$VENV_DIR/bin/harbor" --version)"

	echo_info "下载 terminal-bench@2.0 数据集到本地缓存..."
	"$VENV_DIR/bin/harbor" download "terminal-bench@2.0" --cache
	echo_info "数据集下载完成（缓存于 ~/.cache/harbor/tasks）"

	# 构建离线 wheelhouse（本机预下载依赖，供容器离线安装）
	build_wheelhouse
}

# ===== 从 ~/.jarvis/config.yaml 读取指定模型组信息 =====
# 输出格式: platform|model|api_base|api_key
read_model_group() {
	local group="$1"
	local cfg="$HOME/.jarvis/config.yaml"
	if [ ! -f "$cfg" ]; then
		echo_err "未找到配置文件: $cfg"
		return 1
	fi
	# 用 harbor-venv 的 python 解析 YAML（系统 python3 可能无 pyyaml）
	if [ ! -x "$VENV_DIR/bin/python" ]; then
		echo_err "评测虚拟环境未就绪，请先运行 setup"
		return 1
	fi
	"$VENV_DIR/bin/python" -c "
import sys, yaml
group = '$group'
with open('$cfg') as f:
    cfg = yaml.safe_load(f)
groups = cfg.get('llm_groups', {})
if group not in groups:
    sys.exit(2)
g = groups[group]
llm_name = g.get('normal_llm') or g.get('cheap_llm') or g.get('smart_llm')
llms = cfg.get('llms', {})
m = llms.get(llm_name, {})
lc = m.get('llm_config', {}) or {}
platform = m.get('platform', '')
model = m.get('model', '')
api_base = lc.get('openai_api_base', '') or lc.get('OPENAI_API_BASE', '')
api_key = lc.get('openai_api_key', '') or lc.get('OPENAI_API_KEY', '')
print(f'{platform}|{model}|{api_base}|{api_key}')
" 2>/dev/null
}

# ===== 2. 运行评测 =====
run_eval() {
	setup
	# 优先从 ~/.jarvis/config.yaml 的 ds 模型组读取模型信息
	MODEL_GROUP="${EVAL_MODEL_GROUP:-ds}"
	INFO="$(read_model_group "$MODEL_GROUP")" || {
		rc=$?
		if [ "$rc" -eq 2 ]; then
			echo_err "config.yaml 中不存在模型组: $MODEL_GROUP"
		else
			echo_err "从 config.yaml 读取模型组 $MODEL_GROUP 失败"
		fi
		exit 1
	}
	IFS='|' read -r PLATFORM MODEL API_BASE API_KEY <<<"$INFO"
	if [ -z "$API_KEY" ]; then
		echo_err "模型组 $MODEL_GROUP 未配置 API key"
		exit 1
	fi
	echo_info "使用模型组 $MODEL_GROUP: platform=$PLATFORM model=$MODEL base=$API_BASE"

	# 透传给容器内 jca 的环境变量
	AE_ARGS=(--ae "OPENAI_API_KEY=$API_KEY")
	[ -n "$API_BASE" ] && AE_ARGS+=(--ae "OPENAI_API_BASE=$API_BASE")
	[ -n "$MODEL" ] && AE_ARGS+=(--ae "JARVIS_MODEL=$MODEL")
	[ -n "$PLATFORM" ] && AE_ARGS+=(--ae "JARVIS_PLATFORM=$PLATFORM")
	# deepseek-flash 等推理模型默认进入 thinking 长推理，导致请求超时且
	# content 为空。本机 config.yaml 已配置 thinking disabled，但容器内 jca
	# 用环境变量构建模型配置时不会自动带上，需显式透传 OPENAI_EXTRA_BODY 禁用。
	if [ -z "${OPENAI_EXTRA_BODY:-}" ]; then
		AE_ARGS+=(--ae 'OPENAI_EXTRA_BODY={"thinking":{"type":"disabled"}}')
	fi
	# 额外透传用户已设置的其他 API key / 代理变量
	for var in OPENAI_API_BASE OPENAI_BASE_URL \
		ANTHROPIC_API_KEY ANTHROPIC_BASE_URL \
		API_BASE_URL HTTP_PROXY HTTPS_PROXY NO_PROXY; do
		if [ -n "${!var:-}" ]; then
			AE_ARGS+=(--ae "$var=${!var}")
		fi
	done
	echo_info "启动 Terminal-Bench 2.0 评测（jarvis 适配层）..."
	# shellcheck disable=SC2068
	# JARVIS_WHEELHOUSE_DIR 供 install() 读取本机离线 wheelhouse（Harbor 主进程环境）
	JARVIS_WHEELHOUSE_DIR="${JARVIS_WHEELHOUSE_DIR:-$HOME/.cache/harbor/wheelhouse}" \
		PYTHONPATH="$PROJECT_DIR/src" "$VENV_DIR/bin/harbor" run \
		--dataset terminal-bench@2.0 \
		-a jarvis.jarvis_eval.harbor_agent:JarvisInstalledAgent \
		"${AE_ARGS[@]}" \
		"$@"
}

# ===== 3. 帮助 =====
show_help() {
	"$VENV_DIR/bin/harbor" run --help 2>/dev/null || true
}

# ===== 入口 =====
case "${1:-}" in
setup) setup ;;
run)
	shift
	run_eval "$@"
	;;
help)
	check_prereq
	show_help
	;;
*)
	echo "用法: $0 {setup|run|help}"
	echo "  setup   搭建评测环境（创建 venv + 安装 harbor + 下载数据集）"
	echo "  run     运行评测（需先 export OPENAI_API_KEY 等）"
	echo "  help    查看 harbor run 参数"
	exit 1
	;;
esac
