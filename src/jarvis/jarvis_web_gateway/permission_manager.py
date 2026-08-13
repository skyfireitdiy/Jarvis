"""Jarvis 权限管理模块

职责：权限组管理、权限检查、资源级ACL
数据存储：jarvis_data_dir/auth/ 下5个JSON文件
"""

import os
import json
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

BUILTIN_GROUPS = {
    "sys-admin": {
        "display_name": "System Admin",
        "description": "Full system access",
        "is_builtin": True,
        "permissions": {"*:*": "allow"},
        "accessible_nodes": ["*"],
    },
    "sys-operator": {
        "display_name": "Operator",
        "description": "Agent, Terminal, Timer, Chat management",
        "is_builtin": True,
        "permissions": {
            "agent:create": "allow",
            "agent:delete": "allow",
            "terminal:*": "allow",
            "file:upload": "allow",
            "timer:*": "allow",
            "admin:config": "allow",
            "chat:*": "allow",
        },
        "accessible_nodes": ["*"],
    },
    "sys-developer": {
        "display_name": "Developer",
        "description": "Agent create/delete, Terminal, Chat",
        "is_builtin": True,
        "permissions": {
            "agent:create": "allow",
            "agent:delete": "allow",
            "terminal:*": "allow",
            "file:upload": "allow",
            "chat:*": "allow",
        },
        "accessible_nodes": [],
    },
    "sys-viewer": {
        "display_name": "Viewer",
        "description": "Read-only access",
        "is_builtin": True,
        "permissions": {
            "chat:*": "allow",
        },
        "accessible_nodes": [],
    },
    "sys-chat": {
        "display_name": "Chat User",
        "description": "Chat only access",
        "is_builtin": True,
        "permissions": {"chat:*": "allow"},
        "accessible_nodes": [],
    },
}


class PermissionManager:
    """权限管理器，负责权限组管理、权限检查、资源级ACL"""

    def __init__(self, data_dir: str):
        self._data_dir = os.path.join(data_dir, "auth")
        os.makedirs(self._data_dir, exist_ok=True)
        self._groups_file = os.path.join(self._data_dir, "groups.json")
        self._group_permissions_file = os.path.join(
            self._data_dir, "group_permissions.json"
        )
        self._user_groups_file = os.path.join(self._data_dir, "user_groups.json")
        self._user_permissions_file = os.path.join(
            self._data_dir, "user_permissions.json"
        )
        self._resource_acl_file = os.path.join(self._data_dir, "resource_acl.json")
        self._groups: dict = {}
        self._group_permissions: dict = {}
        self._user_groups: dict = {}
        self._user_permissions: dict = {}
        self._resource_acl: dict = {}
        self._permission_cache: dict = {}
        self._user_manager = None  # 注入UserManager引用，用于is_admin检查
        self._load_data()
        self._ensure_builtin_groups()

    def _load_json(self, filepath: str) -> dict:
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Failed to load {filepath}: {e}")
        return {}

    def _save_json(self, filepath: str, data: dict) -> None:
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Failed to save {filepath}: {e}")

    def _load_data(self) -> None:
        self._groups = self._load_json(self._groups_file)
        self._group_permissions = self._load_json(self._group_permissions_file)
        self._user_groups = self._load_json(self._user_groups_file)
        self._user_permissions = self._load_json(self._user_permissions_file)
        self._resource_acl = self._load_json(self._resource_acl_file)

    def _save_groups(self) -> None:
        self._save_json(self._groups_file, self._groups)

    def _save_group_permissions(self) -> None:
        self._save_json(self._group_permissions_file, self._group_permissions)

    def _save_user_groups(self) -> None:
        self._save_json(self._user_groups_file, self._user_groups)

    def _save_user_permissions(self) -> None:
        self._save_json(self._user_permissions_file, self._user_permissions)

    def _save_resource_acl(self) -> None:
        self._save_json(self._resource_acl_file, self._resource_acl)

    def _ensure_builtin_groups(self) -> None:
        for group_id, group_def in BUILTIN_GROUPS.items():
            # 确保组定义存在并更新
            if group_id not in self._groups:
                self._groups[group_id] = {
                    "group_id": group_id,
                    "name": group_id,
                    "display_name": group_def["display_name"],
                    "description": group_def["description"],
                    "is_builtin": True,
                    "accessible_nodes": group_def.get("accessible_nodes", []),
                }
            else:
                # 已存在的内置组：更新元数据（不覆盖用户自定义字段）
                existing = self._groups[group_id]
                existing["display_name"] = group_def["display_name"]
                existing["description"] = group_def["description"]
                existing["is_builtin"] = True
                if "accessible_nodes" not in existing:
                    existing["accessible_nodes"] = group_def.get("accessible_nodes", [])
            # 强制同步内置组权限（覆盖旧配置）
            perms = group_def["permissions"]
            self._group_permissions[group_id] = (
                {k: v for k, v in perms.items()} if isinstance(perms, dict) else {}
            )
        self._save_groups()
        self._save_group_permissions()

    def _match_permission(self, pattern: str, permission: str) -> bool:
        if pattern == "*:*":
            return True
        if pattern == permission:
            return True
        parts = pattern.split(":")
        if len(parts) == 2 and parts[1] == "*":
            return permission.startswith(parts[0] + ":")
        return False

    def set_user_manager(self, user_manager) -> None:
        """注入UserManager引用，用于is_admin检查。"""
        self._user_manager = user_manager
        self._permission_cache.clear()  # 清缓存，确保重新计算

    def check_permission(self, user_id: str, permission: str) -> bool:
        # admin用户跳过所有权限检查
        if self._user_manager and user_id:
            user = self._user_manager.get_user(user_id)
            if user and user.get("is_admin", False):
                return True
        cache_key = f"{user_id}:{permission}"
        if cache_key in self._permission_cache:
            return self._permission_cache[cache_key]
        result = self._compute_permission(user_id, permission)
        self._permission_cache[cache_key] = result
        return result

    def _compute_permission(self, user_id: str, permission: str) -> bool:
        user_overrides = self._user_permissions.get(user_id, {})
        for pattern, decision in user_overrides.items():
            if self._match_permission(pattern, permission):
                # 支持布尔值(True/False)和字符串("allow"/"deny")
                if decision is False or decision == "deny":
                    return False
                if decision is True or decision == "allow":
                    return True
        user_group_ids = self._user_groups.get(user_id, [])
        for group_id in user_group_ids:
            group_perms = self._group_permissions.get(group_id, {})
            for pattern, decision in group_perms.items():
                if self._match_permission(pattern, permission):
                    if decision == "allow":
                        return True
        return False

    def check_resource_permission(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
        owner_id: Optional[str] = None,
    ) -> bool:
        if owner_id and user_id == owner_id:
            return True
        resource_acls = self._resource_acl.get(resource_type, {})
        acl = resource_acls.get(resource_id, {})
        user_acl = acl.get(user_id, [])
        if permission in user_acl or "*" in user_acl:
            return True
        return self.check_permission(user_id, f"{resource_type}:{permission}")

    def get_user_permissions(self, user_id: str) -> dict:
        result = {"allowed": [], "denied": []}
        user_group_ids = self._user_groups.get(user_id, [])
        for group_id in user_group_ids:
            group_perms = self._group_permissions.get(group_id, {})
            for pattern, decision in group_perms.items():
                if decision == "allow" and pattern not in result["allowed"]:
                    result["allowed"].append(pattern)
        user_overrides = self._user_permissions.get(user_id, {})
        for pattern, decision in user_overrides.items():
            if decision == "allow" and pattern not in result["allowed"]:
                result["allowed"].append(pattern)
            elif decision == "deny":
                result["denied"].append(pattern)
                if pattern in result["allowed"]:
                    result["allowed"].remove(pattern)
        return result

    # --- 组管理方法 ---

    def create_group(
        self, name: str, display_name: str, description: str = ""
    ) -> Optional[dict]:
        group_id = str(uuid.uuid4())
        self._groups[group_id] = {
            "group_id": group_id,
            "name": name,
            "display_name": display_name,
            "description": description,
            "is_builtin": False,
        }
        self._group_permissions[group_id] = {}
        self._save_groups()
        self._save_group_permissions()
        logger.info(f"Created group: {name} (id={group_id})")
        return self._groups[group_id]

    def update_group(self, group_id: str, **kwargs) -> Optional[dict]:
        group = self._groups.get(group_id)
        if group is None:
            return None
        allowed = {"display_name", "description", "accessible_nodes"}
        for key, value in kwargs.items():
            if key in allowed:
                group[key] = value
        self._save_groups()
        return group

    def delete_group(self, group_id: str) -> bool:
        group = self._groups.get(group_id)
        if group is None:
            return False
        if group.get("is_builtin"):
            logger.warning(f"Cannot delete builtin group: {group_id}")
            return False
        del self._groups[group_id]
        self._group_permissions.pop(group_id, None)
        for uid, gids in self._user_groups.items():
            if group_id in gids:
                gids.remove(group_id)
        self._save_groups()
        self._save_group_permissions()
        self._save_user_groups()
        self.invalidate_cache()
        return True

    def get_group(self, group_id: str) -> Optional[dict]:
        return self._groups.get(group_id)

    def list_groups(self) -> list:
        return list(self._groups.values())

    # --- 组权限方法 ---

    def get_group_permissions(self, group_id: str) -> Optional[dict]:
        perms = self._group_permissions.get(group_id)
        if perms is None:
            return None
        group = self._groups.get(group_id, {})
        result = dict(perms)
        result["accessible_nodes"] = group.get("accessible_nodes", [])
        return result

    def set_group_permissions(self, group_id: str, permissions: dict) -> Optional[dict]:
        if group_id not in self._groups:
            return None
        # 提取accessible_nodes，不存入group_permissions
        accessible_nodes = permissions.pop("accessible_nodes", None)
        if accessible_nodes is not None:
            self._groups[group_id]["accessible_nodes"] = accessible_nodes
            self._save_groups()
        self._group_permissions[group_id] = permissions
        self._save_group_permissions()
        self.invalidate_cache()
        return self.get_group_permissions(group_id)

    # --- 用户组方法 ---

    def get_user_groups(self, user_id: str) -> list:
        group_ids = self._user_groups.get(user_id, [])
        return [self._groups[gid] for gid in group_ids if gid in self._groups]

    def set_user_groups(self, user_id: str, group_ids: list) -> list:
        self._user_groups[user_id] = group_ids
        self._save_user_groups()
        self.invalidate_cache(user_id)
        return self.get_user_groups(user_id)

    # --- 用户权限覆盖 ---

    def get_user_overrides(self, user_id: str) -> dict:
        return self._user_permissions.get(user_id, {})

    def set_user_overrides(self, user_id: str, overrides: dict) -> dict:
        self._user_permissions[user_id] = overrides
        self._save_user_permissions()
        self.invalidate_cache(user_id)
        return self._user_permissions[user_id]

    # --- 资源ACL方法 ---

    def set_resource_acl(self, resource_type: str, resource_id: str, acl: dict) -> dict:
        if resource_type not in self._resource_acl:
            self._resource_acl[resource_type] = {}
        self._resource_acl[resource_type][resource_id] = acl
        self._save_resource_acl()
        return self._resource_acl[resource_type][resource_id]

    def get_resource_acl(self, resource_type: str, resource_id: str) -> dict:
        return self._resource_acl.get(resource_type, {}).get(resource_id, {})

    def delete_resource_acl(self, resource_type: str, resource_id: str) -> bool:
        if resource_type not in self._resource_acl:
            return False
        if resource_id not in self._resource_acl[resource_type]:
            return False
        del self._resource_acl[resource_type][resource_id]
        self._save_resource_acl()
        return True

    # --- 节点访问检查 ---

    def check_node_access(self, user_id: str, node_id: str) -> bool:
        """检查用户是否有权访问指定节点。

        Args:
            user_id: 用户ID
            node_id: 目标节点ID

        Returns:
            True=有权限，False=无权限
        """
        if user_id == "system":
            return True
        user_group_ids = self._user_groups.get(user_id, [])
        for group_id in user_group_ids:
            group = self._groups.get(group_id, {})
            accessible_nodes = group.get("accessible_nodes", [])
            if "*" in accessible_nodes:
                return True
            if node_id in accessible_nodes:
                return True
        return False

    def get_user_accessible_nodes(self, user_id: str) -> list:
        """获取用户可访问的所有节点ID列表。

        Args:
            user_id: 用户ID

        Returns:
            节点ID列表，["*"]表示所有节点
        """
        if user_id == "system":
            return ["*"]
        result = []
        has_all = False
        user_group_ids = self._user_groups.get(user_id, [])
        for group_id in user_group_ids:
            group = self._groups.get(group_id, {})
            accessible_nodes = group.get("accessible_nodes", [])
            if "*" in accessible_nodes:
                has_all = True
                break
            for nid in accessible_nodes:
                if nid not in result:
                    result.append(nid)
        if has_all:
            return ["*"]
        return result

    # --- 缓存失效 ---

    def invalidate_cache(self, user_id: Optional[str] = None) -> None:
        if user_id is None:
            self._permission_cache.clear()
        else:
            keys_to_remove = [
                k for k in self._permission_cache if k.startswith(f"{user_id}:")
            ]
            for k in keys_to_remove:
                del self._permission_cache[k]
