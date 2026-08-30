"""Jarvis 用户管理模块

职责：用户CRUD、密码验证、用户状态管理
数据存储：jarvis_data_dir/auth/users.json
"""

import os
import re
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import bcrypt

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
MAX_LOGIN_FAIL = 5


class UserManager:
    """用户管理器，负责用户CRUD、密码验证、用户状态管理"""

    def __init__(self, data_dir: str):
        self._data_dir = os.path.join(data_dir, "auth")
        os.makedirs(self._data_dir, exist_ok=True)
        self._users_file = os.path.join(self._data_dir, "users.json")
        self._users: dict = {}
        self._load_data()
        self._ensure_admin_user()

    def _load_data(self) -> None:
        if os.path.exists(self._users_file):
            try:
                with open(self._users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._users = data.get("users", {})
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load {self._users_file}: {e}")
                self._users = {}
        else:
            self._users = {}

    def _save_data(self) -> None:
        try:
            with open(self._users_file, "w", encoding="utf-8") as f:
                json.dump({"users": self._users}, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Failed to save {self._users_file}: {e}")

    def _ensure_admin_user(self) -> None:
        """首次启动时创建admin用户"""
        for user in self._users.values():
            if user.get("is_admin"):
                return
        admin_password = os.environ.get("JARVIS_ADMIN_PASSWORD")
        if not admin_password:
            admin_password = uuid.uuid4().hex[:16]
            logger.warning(
                f"No JARVIS_ADMIN_PASSWORD set, generated random admin password: {admin_password}"
            )
        self.create_user(
            username="admin",
            password=admin_password,
            display_name="Administrator",
            is_admin=True,
        )

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt(rounds=12)
        ).decode("utf-8")

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    def _sanitize_user(self, user: dict) -> dict:
        """返回不含password_hash的用户信息"""
        result = {k: v for k, v in user.items() if k != "password_hash"}
        return result

    def create_user(
        self,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        is_admin: bool = False,
    ) -> dict:
        """创建用户，验证用户名唯一性，bcrypt哈希密码"""
        if not USERNAME_PATTERN.match(username):
            raise ValueError(
                "Username must be 3-32 chars, only letters, digits, underscore"
            )
        for user in self._users.values():
            if user.get("username") == username:
                raise ValueError(f"Username already exists: {username}")
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        user = {
            "user_id": user_id,
            "username": username,
            "password_hash": self._hash_password(password),
            "display_name": display_name or username,
            "is_admin": is_admin,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_login_at": None,
            "locked_reason": None,
            "login_fail_count": 0,
        }
        self._users[user_id] = user
        self._save_data()
        logger.info(f"Created user: {username} (id={user_id})")
        return self._sanitize_user(user)

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """验证用户名密码，处理登录失败计数和锁定"""
        user = None
        for u in self._users.values():
            if u.get("username") == username:
                user = u
                break
        if user is None:
            return None
        if user.get("status") == "locked":
            return None
        if not self._verify_password(password, user.get("password_hash", "")):
            user["login_fail_count"] = user.get("login_fail_count", 0) + 1
            self._save_data()
            return None
        # 登录成功
        user["login_fail_count"] = 0
        user["last_login_at"] = datetime.now(timezone.utc).isoformat()
        self._save_data()
        return self._sanitize_user(user)

    def get_user(self, user_id: str) -> Optional[dict]:
        """返回用户信息（不含password_hash）"""
        user = self._users.get(user_id)
        if user is None:
            return None
        return self._sanitize_user(user)

    def get_user_by_username(self, username: str) -> Optional[dict]:
        """按用户名查找用户"""
        for user in self._users.values():
            if user.get("username") == username:
                return self._sanitize_user(user)
        return None

    def update_user(self, user_id: str, **kwargs) -> Optional[dict]:
        """可修改：display_name, status, is_admin"""
        user = self._users.get(user_id)
        if user is None:
            return None
        allowed = {"display_name", "status", "is_admin"}
        for key, value in kwargs.items():
            if key in allowed:
                user[key] = value
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_data()
        return self._sanitize_user(user)

    def reset_password(self, user_id: str, new_password: str) -> bool:
        """管理员重置密码"""
        user = self._users.get(user_id)
        if user is None:
            return False
        user["password_hash"] = self._hash_password(new_password)
        user["login_fail_count"] = 0
        user["status"] = "active"
        user["locked_reason"] = None
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_data()
        return True

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> bool:
        """用户自助改密，需验证旧密码"""
        user = self._users.get(user_id)
        if user is None:
            return False
        if not self._verify_password(old_password, user.get("password_hash", "")):
            return False
        user["password_hash"] = self._hash_password(new_password)
        user["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_data()
        return True

    def delete_user(self, user_id: str, current_user_id: Optional[str] = None) -> bool:
        """不可删自己，不可删最后一个管理员"""
        user = self._users.get(user_id)
        if user is None:
            return False
        if current_user_id and user_id == current_user_id:
            raise ValueError("Cannot delete yourself")
        if user.get("is_admin"):
            admin_count = sum(1 for u in self._users.values() if u.get("is_admin"))
            if admin_count <= 1:
                raise ValueError("Cannot delete the last admin user")
        del self._users[user_id]
        self._save_data()
        logger.info(f"Deleted user: {user.get('username')} (id={user_id})")
        return True

    def list_users(
        self, search: Optional[str] = None, offset: int = 0, limit: int = 50
    ) -> list:
        """支持搜索和分页"""
        users = list(self._users.values())
        if search:
            search_lower = search.lower()
            users = [
                u
                for u in users
                if search_lower in u.get("username", "").lower()
                or search_lower in u.get("display_name", "").lower()
            ]
        users.sort(key=lambda u: u.get("created_at", ""))
        result = [self._sanitize_user(u) for u in users[offset : offset + limit]]
        return result
