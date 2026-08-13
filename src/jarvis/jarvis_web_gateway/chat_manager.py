"""聊天室管理模块。

管理聊天室、客户端注册、私聊会话等状态与逻辑。
支持聊天室持久化，网关重启后自动恢复。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import WebSocket


class ChatManager:
    """聊天室管理器。

    维护聊天室、客户端、私聊会话等状态，处理所有 chat_* 消息类型。
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._data_dir = data_dir
        self._chat_rooms: Dict[
            str, Dict[str, Any]
        ] = {}  # room_id -> {name, members: set[user_id], created_by, created_at}
        self._chat_clients: Dict[
            str, Dict[str, Any]
        ] = {}  # client_id -> {name, connection_id, websocket, user_id}
        self._chat_private_sessions: Dict[
            str, Dict[str, Any]
        ] = {}  # session_id -> {client_a, client_b, messages: list}
        self._chat_room_seq = 0  # 聊天室ID自增
        self._chat_private_seq = 0  # 私聊会话ID自增
        self._lock = asyncio.Lock()
        # 启动时加载持久化数据
        self._load_rooms()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _get_rooms_file(self) -> str:
        """获取聊天室持久化文件路径。"""
        if not self._data_dir:
            return ""
        return os.path.join(self._data_dir, "chat_rooms.json")

    def _load_rooms(self) -> None:
        """从JSON文件加载聊天室数据。"""
        filepath = self._get_rooms_file()
        if not filepath or not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            max_seq = 0
            for room_id, room_data in data.items():
                members = set(room_data.get("members", []))
                self._chat_rooms[room_id] = {
                    "name": room_data.get("name", "未命名"),
                    "members": members,  # user_id集合
                    "created_by": room_data.get("created_by", ""),
                    "created_at": room_data.get("created_at", 0),
                }
                # 恢复自增序列号
                try:
                    seq = int(room_id.split("_")[1]) if "_" in room_id else 0
                    if seq > max_seq:
                        max_seq = seq
                except (ValueError, IndexError):
                    pass
            self._chat_room_seq = max_seq
            print(f"[CHAT] Loaded {len(self._chat_rooms)} rooms from {filepath}")
        except Exception as e:
            print(f"[CHAT] Failed to load rooms: {e}")

    def _save_rooms(self) -> None:
        """将聊天室数据保存到JSON文件。"""
        filepath = self._get_rooms_file()
        if not filepath:
            return
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            data = {}
            for room_id, room in self._chat_rooms.items():
                data[room_id] = {
                    "name": room["name"],
                    "members": list(room["members"]),  # set转list序列化
                    "created_by": room["created_by"],
                    "created_at": room["created_at"],
                }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[CHAT] Failed to save rooms: {e}")

    def get_user_rooms(self, user_id: str) -> List[str]:
        """获取用户已加入的聊天室ID列表。"""
        joined = []
        for room_id, room in self._chat_rooms.items():
            if user_id in room["members"]:
                joined.append(room_id)
        return joined

    # ------------------------------------------------------------------
    # 客户端注册
    # ------------------------------------------------------------------

    async def register_client(
        self,
        client_id: str,
        name: str,
        connection_id: str,
        websocket: WebSocket,
        user_id: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """注册客户端，并广播上线通知。"""
        print(f"[CHAT REGISTER] client_id={client_id} name={name} user_id={user_id}")
        async with self._lock:
            self._chat_clients[client_id] = {
                "name": name,
                "display_name": display_name or name,
                "connection_id": connection_id,
                "websocket": websocket,
                "registered_at": time.time(),
                "user_id": user_id,
            }
        # 广播上线通知（锁外执行，避免死锁）
        await self.broadcast_to_all(
            {
                "type": "chat_client_joined",
                "payload": {
                    "client_id": client_id,
                    "name": name,
                    "display_name": display_name or name,
                },
            },
            exclude_client_id=client_id,
        )
        return {
            "success": True,
            "client_id": client_id,
            "name": name,
            "display_name": display_name or name,
        }

    async def unregister_client(self, client_id: str) -> None:
        """注销客户端，并广播下线通知。
        注意：不将user_id从room members中移除，保持持久化成员关系。
        """
        client_info = None
        async with self._lock:
            client_info = self._chat_clients.pop(client_id, None)
            # 不从聊天室members中移除user_id，保持持久化
        # 广播下线通知（锁外执行，避免死锁）
        if client_info:
            await self.broadcast_to_all(
                {
                    "type": "chat_client_left",
                    "payload": {
                        "client_id": client_id,
                        "name": client_info.get("name", ""),
                    },
                },
            )

    def get_client(self, client_id: str) -> Optional[Dict[str, Any]]:
        """获取客户端信息。"""
        return self._chat_clients.get(client_id)

    def get_client_by_user_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """通过user_id获取在线客户端信息。优先返回最新注册的client。"""
        latest = None
        for cid, info in self._chat_clients.items():
            if info.get("user_id") == user_id:
                if latest is None or info.get("registered_at", 0) > latest.get("registered_at", 0):
                    latest = {"client_id": cid, **info}
        return latest

    def get_clients(self) -> list[Dict[str, Any]]:
        """获取所有在线客户端列表。"""
        return [
            {
                "client_id": cid,
                "name": info["name"],
                "display_name": info.get("display_name", info["name"]),
            }
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

    async def create_room(
        self, name: str, creator_id: str, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """创建聊天室。members使用user_id。"""
        member_id = user_id or creator_id
        async with self._lock:
            self._chat_room_seq += 1
            room_id = f"room_{self._chat_room_seq}"
            self._chat_rooms[room_id] = {
                "name": name,
                "members": {member_id},
                "created_by": member_id,
                "created_at": time.time(),
            }
            self._save_rooms()
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
        """加入聊天室。将user_id加入members。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            # 从client_id查user_id
            client = self._chat_clients.get(client_id)
            user_id = client.get("user_id") if client else None
            member_id = user_id or client_id
            print(f"[CHAT JOIN] room={room_id} client_id={client_id} user_id={user_id} member_id={member_id} existing_members={room['members']}")
            room["members"].add(member_id)
            self._save_rooms()
        return {"success": True, "room_id": room_id, "name": room["name"]}

    async def leave_room(self, room_id: str, client_id: str) -> Dict[str, Any]:
        """离开聊天室。将user_id从members移除。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            # 从client_id查user_id
            client = self._chat_clients.get(client_id)
            user_id = client.get("user_id") if client else None
            member_id = user_id or client_id
            room["members"].discard(member_id)
            self._save_rooms()
        return {"success": True, "room_id": room_id}

    async def delete_room(self, room_id: str, client_id: str) -> Dict[str, Any]:
        """删除聊天室（仅创建者可删除）。返回被删除房间的成员列表用于通知。"""
        async with self._lock:
            room = self._chat_rooms.get(room_id)
            if not room:
                return {"success": False, "error": "聊天室不存在"}
            # 从client_id查user_id比较created_by
            client = self._chat_clients.get(client_id)
            user_id = client.get("user_id") if client else None
            member_id = user_id or client_id
            if room["created_by"] != member_id:
                return {"success": False, "error": "仅创建者可删除聊天室"}
            members = list(room["members"])
            del self._chat_rooms[room_id]
            self._save_rooms()
        return {
            "success": True,
            "room_id": room_id,
            "name": room["name"],
            "members": members,
        }

    def get_room_members(self, room_id: str) -> list[Dict[str, Any]]:
        """获取聊天室成员列表（含详细信息）。members存user_id，需查在线client。"""
        room = self._chat_rooms.get(room_id)
        if not room:
            return []
        members = []
        for uid in room["members"]:
            # 查在线客户端
            client = self.get_client_by_user_id(uid)
            if client:
                members.append(
                    {
                        "client_id": client["client_id"],
                        "name": client["name"],
                        "user_id": uid,
                    }
                )
            else:
                # 离线用户也显示
                members.append({"user_id": uid, "name": uid, "online": False})
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
        """向聊天室所有成员广播消息。members存user_id，需查在线client。"""
        room = self._chat_rooms.get(room_id)
        if not room:
            print(f"[CHAT BROADCAST] room {room_id} not found")
            return
        # 获取排除者的user_id
        exclude_user_id = None
        if exclude_client_id:
            ex_client = self._chat_clients.get(exclude_client_id)
            exclude_user_id = ex_client.get("user_id") if ex_client else None
        print(f"[CHAT BROADCAST] room={room_id} members={room['members']} exclude_uid={exclude_user_id}")
        for uid in room["members"]:
            if uid == exclude_user_id:
                print(f"[CHAT BROADCAST] skip excluded uid={uid}")
                continue
            # 查在线客户端
            client = self.get_client_by_user_id(uid)
            print(f"[CHAT BROADCAST] uid={uid} client_found={client is not None} has_ws={client.get('websocket') is not None if client else 'N/A'}")
            if client and client.get("websocket"):
                try:
                    await client["websocket"].send_json(message)
                    print(f"[CHAT BROADCAST] sent to uid={uid} client_id={client.get('client_id')}")
                except Exception as e:
                    print(f"[CHAT BROADCAST] FAILED to send to uid={uid}: {e}")

    # ------------------------------------------------------------------
    # 私聊
    # ------------------------------------------------------------------

    async def send_private(
        self, sender_id: str, receiver_id: str, content: str, image_url: str = ""
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
            "sender_display_name": self._chat_clients[sender_id].get(
                "display_name", self._chat_clients[sender_id]["name"]
            ),
            "content": content,
            "timestamp": time.time(),
        }
        if image_url:
            msg["image_url"] = image_url
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
