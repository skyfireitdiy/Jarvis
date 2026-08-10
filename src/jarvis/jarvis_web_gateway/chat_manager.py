"""聊天室管理模块。

管理聊天室、客户端注册、私聊会话等状态与逻辑。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from fastapi import WebSocket


class ChatManager:
    """聊天室管理器。

    维护聊天室、客户端、私聊会话等状态，处理所有 chat_* 消息类型。
    """

    def __init__(self) -> None:
        self._chat_rooms: Dict[
            str, Dict[str, Any]
        ] = {}  # room_id -> {name, members: set[client_id], created_by, created_at}
        self._chat_clients: Dict[
            str, Dict[str, Any]
        ] = {}  # client_id -> {name, connection_id, websocket}
        self._chat_private_sessions: Dict[
            str, Dict[str, Any]
        ] = {}  # session_id -> {client_a, client_b, messages: list}
        self._chat_room_seq = 0  # 聊天室ID自增
        self._chat_private_seq = 0  # 私聊会话ID自增
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 客户端注册
    # ------------------------------------------------------------------

    async def register_client(
        self,
        client_id: str,
        name: str,
        connection_id: str,
        websocket: WebSocket,
    ) -> Dict[str, Any]:
        """注册客户端，并广播上线通知。"""
        async with self._lock:
            self._chat_clients[client_id] = {
                "name": name,
                "connection_id": connection_id,
                "websocket": websocket,
                "registered_at": time.time(),
            }
        # 广播上线通知（锁外执行，避免死锁）
        await self.broadcast_to_all(
            {"type": "chat_client_joined", "client_id": client_id, "name": name},
            exclude_client_id=client_id,
        )
        return {"success": True, "client_id": client_id, "name": name}

    async def unregister_client(self, client_id: str) -> None:
        """注销客户端，并清理其所在聊天室，广播下线通知。"""
        client_info = None
        async with self._lock:
            client_info = self._chat_clients.pop(client_id, None)
            # 从所有聊天室中移除
            for room in self._chat_rooms.values():
                room["members"].discard(client_id)
        # 广播下线通知（锁外执行，避免死锁）
        if client_info:
            await self.broadcast_to_all(
                {
                    "type": "chat_client_left",
                    "client_id": client_id,
                    "name": client_info.get("name", ""),
                },
            )

    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取客户端信息。"""
        return self._chat_clients.get(client_id)

    def get_clients(self) -> list[Dict[str, Any]]:
        """获取所有在线客户端列表。"""
        return [
            {"client_id": cid, "name": info["name"]}
            for cid, info in self._chat_clients.items()
        ]

    async def broadcast_to_all(
        self,
        message: Dict[str, Any],
        exclude_client_id: Optional[str] = None,
    ) -> None:
        """向所有在线客户端广播消息。"""
        for client_id, client in self._chat_clients.items():
            if client_id == exclude_client_id:
                continue
            if client and client["websocket"]:
                try:
                    await client["websocket"].send_json(message)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 聊天室
    # ------------------------------------------------------------------

    async def create_room(self, name: str, creator_id: str) -> Dict[str, Any]:
        """创建聊天室。"""
        async with self._lock:
            self._chat_room_seq += 1
            room_id = f"room_{self._chat_room_seq}"
            self._chat_rooms[room_id] = {
                "name": name,
                "members": {creator_id},
                "created_by": creator_id,
                "created_at": time.time(),
            }
        return {"success": True, "room_id": room_id, "name": name}

    def get_rooms(self) -> list[Dict[str, Any]]:
        """获取所有聊天室列表。"""
        return [
            {
                "room_id": rid,
                "name": room["name"],
                "member_count": len(room["members"]),
                "created_by": room["created_by"],
            }
            for rid, room in self._chat_rooms.items()
        ]

    async def join_room(self, room_id: str, client_id: str) -> Dict[str, Any]:
        """加入聊天室。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            room["members"].add(client_id)
        return {"success": True, "room_id": room_id, "name": room["name"]}

    async def leave_room(self, room_id: str, client_id: str) -> Dict[str, Any]:
        """离开聊天室。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            room["members"].discard(client_id)
        return {"success": True, "room_id": room_id}

    async def delete_room(self, room_id: str, client_id: str) -> Dict[str, Any]:
        """删除聊天室（仅创建者可删除）。返回被删除房间的成员列表用于通知。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            if room["created_by"] != client_id:
                return {"success": False, "error": "仅创建者可删除聊天室"}
            members = list(room["members"])
            del self._chat_rooms[room_id]
        return {
            "success": True,
            "room_id": room_id,
            "name": room["name"],
            "members": members,
        }

    def get_room_members(self, room_id: str) -> list[Dict[str, Any]]:
        """获取聊天室成员列表（含详细信息）。"""
        room = self._chat_rooms.get(room_id)
        if not room:
            return []
        members = []
        for cid in room["members"]:
            client = self._chat_clients.get(cid)
            if client:
                members.append({"client_id": cid, "name": client["name"]})
        return members

    # ------------------------------------------------------------------
    # 消息广播
    # ------------------------------------------------------------------

    async def broadcast_to_room(
        self,
        room_id: str,
        message: Dict[str, Any],
        exclude_client_id: Optional[str] = None,
    ) -> None:
        """向聊天室所有成员广播消息。"""
        room = self._chat_rooms.get(room_id)
        if not room:
            return
        for client_id in room["members"]:
            if client_id == exclude_client_id:
                continue
            client = self._chat_clients.get(client_id)
            if client and client["websocket"]:
                try:
                    await client["websocket"].send_json(message)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 私聊
    # ------------------------------------------------------------------

    async def send_private(
        self, sender_id: str, receiver_id: str, content: str
    ) -> Dict[str, Any]:
        """发送私聊消息。"""
        if sender_id not in self._chat_clients:
            return {"success": False, "error": "发送者未注册"}
        if receiver_id not in self._chat_clients:
            return {"success": False, "error": "接收者不在线"}

        # 查找或创建私聊会话
        session_id = self._find_private_session(sender_id, receiver_id)
        if not session_id:
            async with self._lock:
                self._chat_private_seq += 1
                session_id = f"private_{self._chat_private_seq}"
                self._chat_private_sessions[session_id] = {
                    "client_a": sender_id,
                    "client_b": receiver_id,
                    "messages": [],
                }

        # 保存消息
        msg = {
            "sender_id": sender_id,
            "sender_name": self._chat_clients[sender_id]["name"],
            "content": content,
            "timestamp": time.time(),
        }
        self._chat_private_sessions[session_id]["messages"].append(msg)

        # 发送给接收者
        receiver = self._chat_clients[receiver_id]
        if receiver["websocket"]:
            try:
                await receiver["websocket"].send_json(
                    {
                        "type": "chat_private_message",
                        "payload": {
                            "session_id": session_id,
                            "message": msg,
                        },
                    }
                )
            except Exception:
                pass

        return {"success": True, "session_id": session_id, "message": msg}

    def get_private_history(self, client_id: str, other_id: str) -> Dict[str, Any]:
        """获取私聊历史消息。"""
        session_id = self._find_private_session(client_id, other_id)
        if not session_id:
            return {"success": True, "messages": []}
        return {
            "success": True,
            "session_id": session_id,
            "messages": self._chat_private_sessions[session_id]["messages"],
        }

    def _find_private_session(self, client_a: str, client_b: str) -> Optional[str]:
        """查找两个客户端之间的私聊会话。"""
        for sid, session in self._chat_private_sessions.items():
            if (
                session["client_a"] == client_a and session["client_b"] == client_b
            ) or (session["client_a"] == client_b and session["client_b"] == client_a):
                return sid
        return None
