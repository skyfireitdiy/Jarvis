# -*- coding: utf-8 -*-
"""守护进程（jarvis-daemon）连接管理：会话注册、能力查询与调用、结果回传。

用户机器上的 jarvis-daemon 通过 WebSocket 主动连出到网关的
``/api/daemon/ws``（子协议 ``jarvis-daemon``），网关侧用本模块维护会话，
并把 Agent 的能力调用请求下发给守护进程执行。

与浏览器扩展（``browser_extension_manager``）是两条完全独立的链路：
端点、子协议、会话表互不共用。

协议（与 daemon/internal/wsclient/client.go 对齐）：
    - 首帧 ``hello``（含 client_id / node_id / hostname / platform / daemon_version）
    - 网关回 ``hello_ack``（含 session_id / heartbeat_interval；可选 ``daemon_update``）
    - 心跳 ``ping`` / ``pong``
    - 能力查询 ``capability.list`` → ``capability.list.result``
    - 能力调用 ``capability.call`` → ``capability.call.result``
    - 自更新回执 ``daemon.update.status``（daemon → 网关，单向，网关只记录不回复）
    - 兼容旧信封 ``command`` → ``result``
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import WebSocket

from jarvis import __version__ as JARVIS_VERSION

logger = logging.getLogger(__name__)

# 会话心跳超时（秒）：超过该时长未收到任何消息则清理会话
HEARTBEAT_TIMEOUT = 60.0

# 单次能力调用默认超时（秒）
DEFAULT_CALL_TIMEOUT = 30.0

# 能力列表查询默认超时（秒）
DEFAULT_LIST_TIMEOUT = 15.0

# 守护进程连接使用的 WS 子协议
DAEMON_SUBPROTOCOL = "jarvis-daemon"

# ---------------------------------------------------------------------------
# daemon 自更新（T5）：网关侧「最新版本」数据来源
#
# 「最新版本」= **网关自身版本**（``jarvis.__version__``）。daemon 必须与网关
# 保持同版本，故网关在握手时把自身版本下发给 daemon，由 daemon 自行比对并
# 无条件自动更新（无开关、无环境变量）。
#
#   JARVIS_DAEMON_RELEASE_BASE_URL Release 下载根地址，默认指向本仓库。
#   JARVIS_DAEMON_ASSETS           可选，JSON 字符串，显式映射
#                                  "os/arch" → {"asset": "...", "sha256": "...", "size": N}；
#                                  缺省时按产物命名规则自动拼装（无 sha256）。
# ---------------------------------------------------------------------------

# 本仓库 owner/repo（来源：pyproject.toml:144 Homepage / README.md:268）。
DAEMON_RELEASE_OWNER_REPO = "skyfireitdiy/Jarvis"

# 默认下载根地址：https://github.com/<owner>/<repo>/releases/download
DAEMON_RELEASE_BASE_URL = os.environ.get(
    "JARVIS_DAEMON_RELEASE_BASE_URL",
    f"https://github.com/{DAEMON_RELEASE_OWNER_REPO}/releases/download",
).rstrip("/")

# 最新版本号 = 网关自身版本；daemon 与网关始终保持同版本。
DAEMON_LATEST_VERSION = str(JARVIS_VERSION or "").strip()

# 支持的平台/架构（与 .github/workflows/release-daemon.yml 的构建矩阵一致，无 macOS）。
DAEMON_SUPPORTED_OS = ("linux", "windows")
DAEMON_SUPPORTED_ARCH = ("amd64", "arm64")


def _load_daemon_assets() -> Dict[str, Dict[str, Any]]:
    """解析 ``JARVIS_DAEMON_ASSETS`` 环境变量为显式产物映射。

    期望格式（JSON 字符串）::

        {"linux/amd64": {"asset": "jarvis-daemon_linux_amd64.tar.gz",
                         "sha256": "…", "size": 12345678}}

    解析失败仅告警并返回空字典（不抛异常，避免影响守护进程连接）。
    """
    raw = os.environ.get("JARVIS_DAEMON_ASSETS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("[DAEMON] JARVIS_DAEMON_ASSETS 解析失败，忽略：%s", exc)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("[DAEMON] JARVIS_DAEMON_ASSETS 不是对象，忽略")
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for key, value in parsed.items():
        if isinstance(value, dict):
            result[str(key)] = value
    return result


# 显式产物映射（os/arch → {asset, sha256, size}）；缺省为空，按命名规则拼装。
DAEMON_ASSETS: Dict[str, Dict[str, Any]] = _load_daemon_assets()


def _daemon_asset_name(os_name: str, arch: str) -> str:
    """按 Release 产物命名规则拼装产物名（见 release-daemon.yml:100-107）。

    Linux → ``jarvis-daemon_linux_<arch>.tar.gz``；
    Windows → ``jarvis-daemon_windows_<arch>.zip``；
    其他平台（含 macOS）→ 空串（无产物）。
    """
    if os_name == "linux":
        return f"jarvis-daemon_linux_{arch}.tar.gz"
    if os_name == "windows":
        return f"jarvis-daemon_windows_{arch}.zip"
    return ""


def _resolve_daemon_platform(source: Any) -> Tuple[str, str]:
    """从会话（或 hello 帧）中解析 (os, arch)，统一小写。

    取值优先级：
      os:   build_info.os → system_info.os_name → system_info.platform → platform
      arch: build_info.arch → system_info.arch → system_info.machine

    无法判定时对应项返回空串（调用方据此跳过更新判断）。
    """
    if not isinstance(source, dict):
        return "", ""
    build_info = source.get("build_info") or {}
    if not isinstance(build_info, dict):
        build_info = {}
    system_info = source.get("system_info") or {}
    if not isinstance(system_info, dict):
        system_info = {}

    os_name = (
        str(
            build_info.get("os")
            or system_info.get("os_name")
            or system_info.get("platform")
            or source.get("platform")
            or ""
        )
        .strip()
        .lower()
    )
    arch = (
        str(
            build_info.get("arch")
            or system_info.get("arch")
            or system_info.get("machine")
            or ""
        )
        .strip()
        .lower()
    )

    # 归一化常见别名，避免 daemon 用 "x86_64"/"aarch64" 上报时匹配不到产物。
    arch_alias = {
        "x86_64": "amd64",
        "x64": "amd64",
        "aarch64": "arm64",
    }
    arch = arch_alias.get(arch, arch)
    return os_name, arch


def _normalize_version(value: Any) -> str:
    """归一化版本号用于比对：去空白、去前导 ``v``/``V``。

    daemon 的版本来自 git tag（形如 ``v5.0.5``），网关自身版本为 ``6.0.0``
    （不带 v）。两侧格式不一致，直接字符串比较会永远判定为「版本不同」，
    导致 daemon 反复下载并重启。故比对前统一归一化。
    """
    text = str(value or "").strip()
    if text[:1] in ("v", "V"):
        text = text[1:].strip()
    return text


def _release_tag(version: Any) -> str:
    """把版本号转成 GitHub Release 的 tag。

    为什么需要：网关自身版本为 ``6.0.1``（不带 v），而 Release tag 由
    ``release-daemon.yml`` 的 ``github.ref_name`` 注入，实际形如 ``v6.0.1``。
    直接用版本号拼下载地址会得到 ``/download/6.0.1/...``，GitHub 返回 404。
    故先归一化（去掉可能已有的 v 前缀，避免拼出 ``vv6.0.1``）再补 ``v``。
    """
    return f"v{_normalize_version(version)}"


def _build_daemon_update(
    daemon_version: str, os_name: str, arch: str
) -> Optional[Dict[str, Any]]:
    """构造 hello_ack 的 ``daemon_update`` 字段。

    返回 None 表示「不下发」（网关自身版本缺失，或平台/架构无法判定）——
    此时 hello_ack 不携带该键，与旧行为完全一致。
    否则返回固定字段的 dict（字段名与设计文档 3.2 逐字一致）。
    """
    latest = DAEMON_LATEST_VERSION
    if not latest:
        # 网关自身版本缺失 → 不下发任何更新信息。
        return None
    if not os_name or not arch:
        # 平台/架构无法判定（旧版 daemon）→ 跳过更新判断，不打扰连接。
        return None

    current = str(daemon_version or "").strip()
    info: Dict[str, Any] = {
        "available": False,
        "latest_version": latest,
        "current_version": current,
        "url": "",
        "sha256": "",
        "size": 0,
        "asset": "",
        "note": "",
    }

    # 版本一致（归一化后）→ 已是最新，available=false 并说明原因。
    if _normalize_version(current) == _normalize_version(latest):
        info["note"] = "already up to date"
        return info

    # 平台/架构不受支持（如 macOS）→ available=false 并说明。
    if os_name not in DAEMON_SUPPORTED_OS or arch not in DAEMON_SUPPORTED_ARCH:
        info["note"] = f"no release asset for {os_name}/{arch}"
        return info

    # 显式映射优先，否则按命名规则拼装。
    explicit = DAEMON_ASSETS.get(f"{os_name}/{arch}") or {}
    asset = str(explicit.get("asset") or "").strip() or _daemon_asset_name(
        os_name, arch
    )
    if not asset:
        info["note"] = f"no release asset for {os_name}/{arch}"
        return info

    info["available"] = True
    info["asset"] = asset
    info["url"] = f"{DAEMON_RELEASE_BASE_URL}/{_release_tag(latest)}/{asset}"
    info["sha256"] = str(explicit.get("sha256") or "").strip()
    try:
        info["size"] = int(explicit.get("size") or 0)
    except (TypeError, ValueError):
        info["size"] = 0
    if not info["sha256"]:
        # 未配置 sha256：daemon 侧会跳过校验并记警告（见设计文档 3.4）。
        info["note"] = "sha256 not configured; daemon will skip verification"
    return info


class DaemonCapabilityManager:
    """管理守护进程连接与能力调用。

    会话注册表：session_id -> {
        websocket, user_id, client_id, node_id, hostname, platform,
        daemon_version, capabilities, connected_at, last_seen
    }

    ``user_id`` 由网关从 WS 子协议中的 token 解析得到，用于多用户隔离：
    能力查询/调用前必须校验会话归属，避免任意有效 token 跨用户执行本机能力。
    """

    def __init__(self) -> None:
        # session_id -> 会话信息
        self._sessions: Dict[str, Dict[str, Any]] = {}
        # request_id -> Future，用于按 id 匹配能力调用响应
        self._pending_calls: Dict[str, asyncio.Future] = {}
        # session_id -> Future，用于匹配无 id 的能力列表响应
        self._pending_lists: Dict[str, asyncio.Future] = {}
        # 心跳巡检任务
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # 会话生命周期
    # ------------------------------------------------------------------
    def _ensure_cleanup_task(self) -> None:
        """惰性启动心跳超时巡检任务。"""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            self._cleanup_task = loop.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """周期性清理心跳超时的会话。"""
        try:
            while True:
                await asyncio.sleep(10)
                now = time.time()
                stale: List[str] = []
                for session_id, session in list(self._sessions.items()):
                    last_seen = session.get("last_seen") or session.get(
                        "connected_at", now
                    )
                    if now - last_seen > HEARTBEAT_TIMEOUT:
                        stale.append(session_id)
                for session_id in stale:
                    logger.warning("[DAEMON] session heartbeat timeout: %s", session_id)
                    await self.disconnect(session_id)
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - 防御性
            logger.exception("[DAEMON] cleanup loop error: %s", exc)

    async def handle_daemon_websocket(
        self,
        websocket: WebSocket,
        user_id: Optional[str] = None,
    ) -> None:
        """处理守护进程 WebSocket 连接：注册会话、收发消息、断开清理。

        注意：鉴权在 app.py 的端点层完成，本方法不做权限校验；
        ``user_id`` 由端点层从 token 解析后传入，用于后续会话归属校验。
        """
        # 守护进程使用自定义子协议，必须回显否则客户端会断开
        await websocket.accept(subprotocol=DAEMON_SUBPROTOCOL)
        session_id = str(uuid.uuid4())
        self._ensure_cleanup_task()
        try:
            # 首帧必须是 hello
            try:
                first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            except Exception:
                await self._send_error(
                    websocket, "INVALID_MESSAGE", "first message must be hello"
                )
                await websocket.close(code=4400)
                return
            if not isinstance(first, dict) or first.get("type") != "hello":
                await self._send_error(
                    websocket, "INVALID_MESSAGE", "first message must be hello"
                )
                await websocket.close(code=4400)
                return

            client_id = str(first.get("client_id") or "").strip() or session_id
            # 守护进程上报的是自身（用户侧服务）的系统信息；浏览器信息由浏览器
            # 扩展另行上报，不在此处理。兼容旧版：旧版把 hostname/platform 放在
            # browser_info 里，故仍保留该回退路径。
            system_info = first.get("system_info") or {}
            if not isinstance(system_info, dict):
                system_info = {}
            browser_info = first.get("browser_info") or {}
            if not isinstance(browser_info, dict):
                browser_info = {}
            hostname = str(
                system_info.get("hostname") or browser_info.get("hostname") or ""
            ).strip()
            # 终端名称：由用户在 Jarvis 网页设置页配置，前端推送给 daemon，
            # daemon 在 hello 中携带。用于让网关/Agent 以用户可读的名称识别终端。
            # 为空时回退 hostname（旧版 daemon 不带该字段）。
            terminal_name = str(first.get("name") or "").strip() or hostname
            now = time.time()
            # 同一台机器上的 daemon 重启后 client_id 会变（含 PID），旧连接在心跳
            # 超时（最长约 70s）前仍留在会话表里，导致 list_sessions 出现幽灵条目、
            # 能力调用可能被路由到已失效的旧连接。这里以 (user_id, hostname) 作为
            # 稳定身份，在注册新会话前主动清理同机器的旧会话。
            # hostname 为空时无法可靠识别身份，不做清理以免误杀。
            if hostname:
                await self._replace_stale_sessions(session_id, user_id, hostname)
            # 守护进程可在 hello 中直接携带能力列表（新版 daemon 会这么做）。
            # 这样会话一注册就带有能力，无需再依赖运行时 capability.list 往返；
            # 旧版 daemon 不带该字段时回退为空列表，仍可通过主动查询获取。
            hello_capabilities = first.get("capabilities")
            if not isinstance(hello_capabilities, list):
                hello_capabilities = []
            # 守护进程可在 hello 中携带构建信息（版本/编译时间/Go 版本/目标平台）。
            # 编译时间取自 daemon exe 的 mtime（见 daemon/internal/buildinfo）。
            # 旧版 daemon 不带该字段时回退为空字典。
            hello_build_info = first.get("build_info")
            if not isinstance(hello_build_info, dict):
                hello_build_info = {}
            self._sessions[session_id] = {
                "websocket": websocket,
                "user_id": user_id,
                "client_id": client_id,
                "node_id": str(first.get("node_id") or "").strip() or client_id,
                "hostname": str(
                    system_info.get("hostname") or browser_info.get("hostname") or ""
                ).strip(),
                "name": terminal_name,
                "platform": str(
                    system_info.get("os_name")
                    or system_info.get("platform")
                    or browser_info.get("platform")
                    or ""
                ).strip(),
                "system_info": system_info,
                "daemon_version": first.get("extension_version"),
                "build_info": hello_build_info,
                "capabilities": hello_capabilities,
                "connected_at": now,
                "last_seen": now,
                # 自更新进度（daemon.update.status 回执写入；未回执时为 None）。
                "update_state": None,
            }
            logger.info(
                "[DAEMON] session connected: session_id=%s client_id=%s node_id=%s user_id=%s",
                session_id,
                client_id,
                self._sessions[session_id]["node_id"],
                user_id,
            )
            # 诊断日志：便于端到端排查「系统信息是否收到」。
            # 若此处 system_info 为空，说明 daemon 未上报或上报字段名不符；
            # 若此处有值但 /api/daemon/sessions 看不到，问题在返回层。
            logger.info(
                "[DAEMON] hello system_info: received=%s hostname=%r platform=%r fields=%d",
                bool(system_info),
                self._sessions[session_id]["hostname"],
                self._sessions[session_id]["platform"],
                len(system_info),
            )

            # 自更新判断：把「最新版本」与 daemon 上报的版本/架构比对，
            # 结果随 hello_ack 下发（只增不改，旧 daemon 忽略即可）。
            # 未配置最新版本或平台无法判定时返回 None → 不携带该键，
            # 保证旧字段与旧行为完全不变。
            daemon_os, daemon_arch = _resolve_daemon_platform(
                self._sessions[session_id]
            )
            daemon_update = _build_daemon_update(
                self._sessions[session_id].get("daemon_version") or "",
                daemon_os,
                daemon_arch,
            )
            hello_ack: Dict[str, Any] = {
                "type": "hello_ack",
                "session_id": session_id,
                "heartbeat_interval": 20,
            }
            if daemon_update is not None:
                hello_ack["daemon_update"] = daemon_update
                logger.info(
                    "[DAEMON] update check: session_id=%s current=%s latest=%s "
                    "os=%s arch=%s available=%s note=%s",
                    session_id,
                    daemon_update.get("current_version"),
                    daemon_update.get("latest_version"),
                    daemon_os,
                    daemon_arch,
                    daemon_update.get("available"),
                    daemon_update.get("note"),
                )
            await websocket.send_json(hello_ack)

            # 消息循环
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, dict):
                    continue
                session = self._sessions.get(session_id)
                if session is not None:
                    session["last_seen"] = time.time()
                msg_type = message.get("type")
                if msg_type == "capability.list.result":
                    self._handle_capability_list_result(session_id, message)
                elif msg_type == "capability.call.result":
                    self._handle_capability_call_result(message)
                elif msg_type == "daemon.update.status":
                    # 自更新进度回执（单向）：仅记录日志并更新会话字段，
                    # **绝不回复**（daemon 不等待，旧网关 debug 忽略亦兼容）。
                    state = str(message.get("state") or "").strip()
                    version = str(message.get("version") or "").strip()
                    error = str(message.get("error") or "").strip()
                    if session is not None:
                        session["update_state"] = {
                            "state": state,
                            "version": version,
                            "error": error,
                            "updated_at": time.time(),
                        }
                    logger.info(
                        "[DAEMON] update status: session_id=%s state=%s version=%s error=%s",
                        session_id,
                        state or "?",
                        version or "?",
                        error or "",
                    )
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "hello":
                    # 重连后重新握手：刷新会话信息
                    if session is not None:
                        session["client_id"] = (
                            str(message.get("client_id") or "").strip() or client_id
                        )
                        session["node_id"] = (
                            str(message.get("node_id") or "").strip()
                            or session["client_id"]
                        )
                else:
                    logger.debug("[DAEMON] unknown message type: %s", msg_type)
        except Exception as exc:
            logger.info(
                "[DAEMON] session closed: session_id=%s reason=%s",
                session_id,
                exc,
            )
        finally:
            await self.disconnect(session_id)

    def _handle_capability_list_result(
        self, session_id: str, message: Dict[str, Any]
    ) -> None:
        """缓存能力列表并唤醒等待中的查询。"""
        capabilities = message.get("capabilities")
        if not isinstance(capabilities, list):
            capabilities = []
        session = self._sessions.get(session_id)
        if session is not None:
            session["capabilities"] = capabilities
        future = self._pending_lists.get(session_id)
        if future is not None and not future.done():
            future.set_result(capabilities)

    def _handle_capability_call_result(self, message: Dict[str, Any]) -> None:
        """把能力调用结果投递给等待中的 Future。"""
        request_id = message.get("id")
        if not request_id:
            return
        future = self._pending_calls.get(request_id)
        if future is not None and not future.done():
            future.set_result(message)

    async def _replace_stale_sessions(
        self,
        new_session_id: str,
        user_id: Optional[str],
        hostname: str,
    ) -> None:
        """清理同一台机器（同 user_id + 同 hostname）遗留的旧会话。

        daemon 重启后 ``client_id`` 会变（含 PID），旧连接在心跳超时前仍留在
        会话表中。以 ``(user_id, hostname)`` 作为稳定身份，在注册新会话前把
        旧会话一并断开，避免幽灵条目与调用错路由。
        """
        stale: List[str] = []
        for session_id, session in list(self._sessions.items()):
            if session_id == new_session_id:
                continue
            if session.get("user_id") != user_id:
                continue
            if str(session.get("hostname") or "").strip() != hostname:
                continue
            stale.append(session_id)
        for session_id in stale:
            logger.info(
                "[DAEMON] replace stale session: old=%s new=%s hostname=%s",
                session_id,
                new_session_id,
                hostname,
            )
            await self.disconnect(session_id)

    async def disconnect(self, session_id: str) -> None:
        """关闭并移除会话，失败所有等待中的调用。"""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        websocket = session.get("websocket")
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass
        # 该会话下所有未完成调用立即失败
        for request_id, future in list(self._pending_calls.items()):
            if future.done():
                continue
            if getattr(future, "_daemon_session", None) == session_id:
                future.set_exception(
                    RuntimeError(f"daemon session disconnected: {session_id}")
                )
                self._pending_calls.pop(request_id, None)
        list_future = self._pending_lists.pop(session_id, None)
        if list_future is not None and not list_future.done():
            list_future.set_exception(
                RuntimeError(f"daemon session disconnected: {session_id}")
            )
        logger.info("[DAEMON] session removed: %s", session_id)

    # ------------------------------------------------------------------
    # 会话归属校验
    # ------------------------------------------------------------------
    def check_session_access(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> tuple[bool, str]:
        """校验调用方是否有权访问指定守护进程会话。

        规则：
        - 会话不存在 → 拒绝；
        - ``user_id`` 为空、为 ``system`` 或 ``is_admin`` 为真 → 放行（网关内部/管理员）；
        - 否则要求会话的 ``user_id`` 与调用方一致。

        Returns:
            (是否允许, 拒绝原因)；允许时原因为空字符串。
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False, f"daemon session not found: {session_id}"
        if not user_id or user_id == "system" or is_admin:
            return True, ""
        if session.get("user_id") != user_id:
            return False, "forbidden: daemon session belongs to another user"
        return True, ""

    # ------------------------------------------------------------------
    # 能力查询与调用
    # ------------------------------------------------------------------
    async def list_capabilities(
        self,
        session_id: str,
        timeout: float = DEFAULT_LIST_TIMEOUT,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        """查询指定守护进程的能力列表。

        Raises:
            RuntimeError: 会话不存在、无访问权限、连接已失效或查询超时。
        """
        allowed, reason = self.check_session_access(session_id, user_id, is_admin)
        if not allowed:
            raise RuntimeError(reason)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError(f"daemon session not found: {session_id}")
        websocket = session.get("websocket")
        if websocket is None:
            raise RuntimeError(f"daemon session has no connection: {session_id}")

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_lists[session_id] = future
        try:
            logger.info("[DAEMON] list capabilities session_id=%s", session_id)
            await websocket.send_json({"type": "capability.list"})
            try:
                capabilities = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"daemon capability list timed out: session_id={session_id}, "
                    f"timeout={timeout}s"
                ) from exc
            return list(capabilities or [])
        finally:
            self._pending_lists.pop(session_id, None)

    async def call_capability(
        self,
        session_id: str,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = DEFAULT_CALL_TIMEOUT,
        user_id: Optional[str] = None,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """调用指定守护进程的一项能力并等待结果。

        Returns:
            dict: {"success": bool, "data": any, "error": str}

        Raises:
            RuntimeError: 会话不存在、无访问权限、连接已失效或调用超时。
        """
        allowed, reason = self.check_session_access(session_id, user_id, is_admin)
        if not allowed:
            raise RuntimeError(reason)
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError(f"daemon session not found: {session_id}")
        websocket = session.get("websocket")
        if websocket is None:
            raise RuntimeError(f"daemon session has no connection: {session_id}")

        call_id = f"call-{uuid.uuid4()}"
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        # 记录归属会话，便于断线时批量失败
        setattr(future, "_daemon_session", session_id)
        self._pending_calls[call_id] = future
        try:
            logger.info(
                "[DAEMON] call capability session_id=%s name=%s call_id=%s",
                session_id,
                name,
                call_id,
            )
            await websocket.send_json(
                {
                    "type": "capability.call",
                    "id": call_id,
                    "name": name,
                    "params": params or {},
                }
            )
            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"daemon capability call timed out: session_id={session_id}, "
                    f"name={name}, timeout={timeout}s"
                ) from exc
            if not isinstance(response, dict):
                raise RuntimeError(
                    f"invalid daemon capability response: session_id={session_id}, "
                    f"name={name}"
                )
            return {
                "success": bool(response.get("success")),
                "data": response.get("data"),
                "error": response.get("error") or "",
            }
        finally:
            self._pending_calls.pop(call_id, None)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出当前在线的守护进程会话；传入 user_id 时仅返回该用户的会话。"""
        result: List[Dict[str, Any]] = []
        for session_id, session in self._sessions.items():
            if user_id is not None and session.get("user_id") != user_id:
                continue
            result.append(
                {
                    "session_id": session_id,
                    "client_id": session.get("client_id"),
                    "user_id": session.get("user_id"),
                    "node_id": session.get("node_id"),
                    "hostname": session.get("hostname"),
                    "name": session.get("name") or session.get("hostname"),
                    "platform": session.get("platform"),
                    "system_info": session.get("system_info") or {},
                    "daemon_version": session.get("daemon_version"),
                    "build_info": session.get("build_info") or {},
                    "capabilities": session.get("capabilities") or [],
                    "connected_at": session.get("connected_at"),
                    "update_state": session.get("update_state"),
                }
            )
        return result

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取单个会话信息（不含 websocket 对象）。"""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session_id,
            "client_id": session.get("client_id"),
            "user_id": session.get("user_id"),
            "node_id": session.get("node_id"),
            "hostname": session.get("hostname"),
            "name": session.get("name") or session.get("hostname"),
            "platform": session.get("platform"),
            "system_info": session.get("system_info") or {},
            "daemon_version": session.get("daemon_version"),
            "build_info": session.get("build_info") or {},
            "capabilities": session.get("capabilities") or [],
            "connected_at": session.get("connected_at"),
            "update_state": session.get("update_state"),
        }

    # ------------------------------------------------------------------
    # 工具函数
    # ------------------------------------------------------------------
    @staticmethod
    async def _send_error(websocket: WebSocket, code: str, message: str) -> None:
        try:
            await websocket.send_json(
                {"type": "error", "payload": {"code": code, "message": message}}
            )
        except Exception:
            pass


# 全局单例，供 app.py 与工具层共用
daemon_capability_manager = DaemonCapabilityManager()
