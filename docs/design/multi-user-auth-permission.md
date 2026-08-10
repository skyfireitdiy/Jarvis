# Jarvis 多用户认证与分组权限管理方案文档

## 一、概述

### 1.1 目标

为 Jarvis Web Gateway 引入完整的用户管理体系与细粒度权限控制，实现：

- 独立用户注册/登录，每用户独立密码
- 管理员管理用户的增删改查
- 分组权限管理，权限粒度到 Agent 级别
- 多维度权限控制：Agent操作、终端访问、文件访问、配置同步、聊天室等

### 1.2 设计原则

- **最小权限**：默认无权限，显式授权
- **分组优先**：权限按组分配，用户继承组权限，支持用户级覆盖
- **向后兼容**：现有单Token模式平滑过渡
- **性能优先**：权限检查内存缓存，避免每次请求查库

---

## 二、用户管理

### 2.1 用户模型

```text
User {
  user_id:        str       # 唯一ID，UUID
  username:       str       # 用户名，唯一，3-32字符
  password_hash:  str       # bcrypt哈希
  display_name:   str       # 显示名称
  is_admin:       bool      # 是否管理员（内置角色，不可删除）
  status:         str       # active / disabled / locked
  created_at:     datetime
  updated_at:     datetime
  last_login_at:  datetime
  locked_reason:  str       # 锁定原因（多次失败/管理员锁定）
  login_fail_count: int     # 连续登录失败次数
}
```

### 2.2 初始管理员

系统首次启动时，自动创建初始管理员账户：

- 用户名：`admin`
- 密码：从环境变量 `JARVIS_ADMIN_PASSWORD` 读取，若未设置则生成随机密码并输出到日志
- 首次登录后强制修改密码

### 2.3 用户管理API（仅管理员可用）

| API                                         | 方法   | 说明                                        |
| ------------------------------------------- | ------ | ------------------------------------------- |
| `/api/admin/users`                          | GET    | 列出所有用户（支持分页/搜索）               |
| `/api/admin/users`                          | POST   | 创建用户                                    |
| `/api/admin/users/{user_id}`                | GET    | 获取用户详情                                |
| `/api/admin/users/{user_id}`                | PATCH  | 修改用户信息（重置密码/改状态/改显示名）    |
| `/api/admin/users/{user_id}`                | DELETE | 删除用户（不可删自己/不可删最后一个管理员） |
| `/api/admin/users/{user_id}/password/reset` | POST   | 重置用户密码                                |
| `/api/admin/users/{user_id}/groups`         | GET    | 获取用户所属组列表                          |
| `/api/admin/users/{user_id}/groups`         | PUT    | 设置用户所属组（替换）                      |
| `/api/admin/users/{user_id}/permissions`    | GET    | 获取用户有效权限（含组继承+用户覆盖）       |

### 2.4 用户自助API

| API                  | 方法 | 说明                          |
| -------------------- | ---- | ----------------------------- |
| `/api/auth/login`    | POST | 登录（改为username+password） |
| `/api/auth/logout`   | POST | 登出（注销Token）             |
| `/api/auth/me`       | GET  | 获取当前用户信息              |
| `/api/auth/password` | PUT  | 修改自己密码                  |

### 2.5 登录流程变更

**现有流程**：

```text
POST /api/auth/login {password} → {token: "全局唯一Token"}
```

**新流程**：

```text
POST /api/auth/login {username, password} → {token: "JWT含user_id", expires_in: 86400}
```

Token改为JWT格式，payload含：

```json
{
  "user_id": "uuid",
  "username": "alice",
  "is_admin": false,
  "iat": 1234567890,
  "exp": 1234654290
}
```

---

## 三、分组权限管理

### 3.1 权限组模型

```text
Group {
  group_id:       str       # 唯一ID，UUID（系统组以sys-开头）
  group_name:     str       # 组名，唯一
  description:    str       # 组描述
  is_system:      bool      # 系统内置组，不可删除
  created_at:     datetime
  updated_at:     datetime
}
```

### 3.2 内置权限组

| 组名             | group_id        | 说明                                          |
| ---------------- | --------------- | --------------------------------------------- |
| `administrators` | `sys-admin`     | 超级管理员，拥有所有权限，不可修改            |
| `operators`      | `sys-operator`  | 运维人员，可管理Agent/节点/终端，不可管理用户 |
| `developers`     | `sys-developer` | 开发人员，可创建Agent/编辑代码/使用终端       |
| `viewers`        | `sys-viewer`    | 只读用户，仅可查看Agent状态/日志              |
| `chat-users`     | `sys-chat`      | 聊天室用户，仅可使用聊天功能                  |

### 3.3 权限组管理API（仅管理员）

| API                                        | 方法   | 说明                         |
| ------------------------------------------ | ------ | ---------------------------- |
| `/api/admin/groups`                        | GET    | 列出所有组                   |
| `/api/admin/groups`                        | POST   | 创建自定义组                 |
| `/api/admin/groups/{group_id}`             | GET    | 获取组详情                   |
| `/api/admin/groups/{group_id}`             | PATCH  | 修改组信息                   |
| `/api/admin/groups/{group_id}`             | DELETE | 删除自定义组（系统组不可删） |
| `/api/admin/groups/{group_id}/permissions` | GET    | 获取组权限配置               |
| `/api/admin/groups/{group_id}/permissions` | PUT    | 设置组权限配置               |
| `/api/admin/groups/{group_id}/members`     | GET    | 获取组成员列表               |

---

## 四、权限体系设计

### 4.1 权限分类

权限分为**全局权限**和**资源级权限**两层：

#### 4.1.1 全局权限（Global Permissions）

控制用户是否可以使用某类功能：

| 权限标识               | 说明                                             | 默认值 |
| ---------------------- | ------------------------------------------------ | ------ |
| `agent.create`         | 创建Agent                                        | deny   |
| `agent.list_all`       | 查看所有用户的Agent（否则仅可见自己的+被授权的） | deny   |
| `agent.delete_own`     | 删除自己创建的Agent                              | deny   |
| `agent.delete_any`     | 删除任意Agent                                    | deny   |
| `agent.stop_own`       | 停止自己创建的Agent                              | deny   |
| `agent.stop_any`       | 停止任意Agent                                    | deny   |
| `agent.regenerate_own` | 重生自己的Agent                                  | deny   |
| `agent.regenerate_any` | 重生任意Agent                                    | deny   |
| `terminal.open`        | 打开终端                                         | deny   |
| `terminal.list`        | 查看终端列表                                     | deny   |
| `terminal.delete_own`  | 删除自己创建的终端                               | deny   |
| `terminal.delete_any`  | 删除任意终端                                     | deny   |
| `file.read`            | 读取文件内容                                     | deny   |
| `file.write`           | 写入/编辑文件                                    | deny   |
| `file.browse`          | 浏览目录结构                                     | deny   |
| `config.sync`          | 同步节点配置                                     | deny   |
| `config.view`          | 查看节点配置                                     | deny   |
| `node.view`            | 查看节点状态                                     | deny   |
| `node.restart`         | 重启节点服务                                     | deny   |
| `node.code_update`     | 更新节点代码                                     | deny   |
| `node.secret`          | 获取节点连接密钥                                 | deny   |
| `timer.create`         | 创建定时任务                                     | deny   |
| `timer.list`           | 查看定时任务                                     | deny   |
| `timer.delete_own`     | 删除自己创建的定时任务                           | deny   |
| `timer.delete_any`     | 删除任意定时任务                                 | deny   |
| `chat.join`            | 加入聊天室                                       | deny   |
| `chat.create_room`     | 创建聊天室                                       | deny   |
| `chat.delete_own_room` | 删除自己创建的聊天室                             | deny   |
| `chat.send_message`    | 发送聊天消息                                     | deny   |
| `chat.private_message` | 发送私聊消息                                     | deny   |
| `group.create`         | 创建Agent通信群组                                | deny   |
| `group.join`           | 加入群组                                         | deny   |
| `group.manage_own`     | 管理自己创建的群组                               | deny   |
| `data.read`            | 读取KV存储数据                                   | deny   |
| `data.write`           | 写入KV存储数据                                   | deny   |
| `data.delete`          | 删除KV存储数据                                   | deny   |
| `user.manage`          | 用户管理（增删改查）                             | deny   |
| `group.manage`         | 权限组管理                                       | deny   |
| `permission.manage`    | 权限分配管理                                     | deny   |
| `model.view`           | 查看模型组配置                                   | deny   |
| `completion.use`       | 使用代码补全                                     | deny   |
| `search.use`           | 使用全局搜索                                     | deny   |

#### 4.1.2 资源级权限（Resource Permissions）

在全局权限之上，对特定资源实例进行细粒度控制。当前仅Agent支持资源级权限：

```json
{
  "resource_type": "agent",
  "resource_id": "agent-uuid",
  "permissions": {
    "agent.view": true,
    "agent.chat": true,
    "agent.edit_config": false,
    "agent.stop": false,
    "agent.delete": false,
    "agent.read_log": true,
    "agent.read_session": true,
    "agent.write_session": false
  }
}
```

**Agent资源级权限项**：

| 权限标识              | 说明               |
| --------------------- | ------------------ |
| `agent.view`          | 查看Agent详情      |
| `agent.chat`          | 与Agent对话        |
| `agent.edit_config`   | 修改Agent配置      |
| `agent.stop`          | 停止Agent          |
| `agent.delete`        | 删除Agent          |
| `agent.read_log`      | 查看Agent日志      |
| `agent.read_session`  | 查看Agent会话历史  |
| `agent.write_session` | 写入/修改Agent会话 |

**权限继承规则**：

- Agent创建者自动获得该Agent的所有资源级权限
- `agent.delete_any` 全局权限可覆盖 `agent.delete` 资源级权限
- `agent.stop_any` 全局权限可覆盖 `agent.stop` 资源级权限
- 资源级权限仅对非创建者生效

#### 4.1.3 权限计算优先级

```text
1. 管理员绕过：is_admin=true → 全部允许
2. 显式拒绝：用户级 deny → 最终拒绝
3. 显式允许：用户级 allow → 最终允许
4. 组继承允许：任一所属组 allow → 允许
5. 资源级允许：资源ACL中 allow → 允许
6. 默认拒绝：无匹配规则 → 拒绝
```

---

## 五、内置组权限映射

### 5.1 administrators（sys-admin）

全部权限 = `allow`，不可修改。

### 5.2 operators（sys-operator）

| 权限                   | 值    |
| ---------------------- | ----- |
| `agent.create`         | allow |
| `agent.list_all`       | allow |
| `agent.delete_own`     | allow |
| `agent.delete_any`     | allow |
| `agent.stop_own`       | allow |
| `agent.stop_any`       | allow |
| `agent.regenerate_own` | allow |
| `agent.regenerate_any` | allow |
| `terminal.open`        | allow |
| `terminal.list`        | allow |
| `terminal.delete_own`  | allow |
| `terminal.delete_any`  | allow |
| `file.read`            | allow |
| `file.write`           | allow |
| `file.browse`          | allow |
| `config.sync`          | allow |
| `config.view`          | allow |
| `node.view`            | allow |
| `node.restart`         | allow |
| `node.code_update`     | allow |
| `node.secret`          | allow |
| `timer.create`         | allow |
| `timer.list`           | allow |
| `timer.delete_own`     | allow |
| `timer.delete_any`     | allow |
| `chat.join`            | allow |
| `chat.create_room`     | allow |
| `chat.delete_own_room` | allow |
| `chat.send_message`    | allow |
| `chat.private_message` | allow |
| `group.create`         | allow |
| `group.join`           | allow |
| `group.manage_own`     | allow |
| `data.read`            | allow |
| `data.write`           | allow |
| `data.delete`          | allow |
| `model.view`           | allow |
| `completion.use`       | allow |
| `search.use`           | allow |

### 5.3 developers（sys-developer）

| 权限                   | 值    |
| ---------------------- | ----- |
| `agent.create`         | allow |
| `agent.list_all`       | deny  |
| `agent.delete_own`     | allow |
| `agent.delete_any`     | deny  |
| `agent.stop_own`       | allow |
| `agent.stop_any`       | deny  |
| `agent.regenerate_own` | allow |
| `agent.regenerate_any` | deny  |
| `terminal.open`        | allow |
| `terminal.list`        | allow |
| `terminal.delete_own`  | allow |
| `terminal.delete_any`  | deny  |
| `file.read`            | allow |
| `file.write`           | allow |
| `file.browse`          | allow |
| `config.sync`          | deny  |
| `config.view`          | allow |
| `node.view`            | allow |
| `node.restart`         | deny  |
| `node.code_update`     | deny  |
| `node.secret`          | deny  |
| `timer.create`         | allow |
| `timer.list`           | allow |
| `timer.delete_own`     | allow |
| `timer.delete_any`     | deny  |
| `chat.join`            | allow |
| `chat.create_room`     | allow |
| `chat.delete_own_room` | allow |
| `chat.send_message`    | allow |
| `chat.private_message` | allow |
| `group.create`         | allow |
| `group.join`           | allow |
| `group.manage_own`     | allow |
| `data.read`            | allow |
| `data.write`           | allow |
| `data.delete`          | deny  |
| `model.view`           | allow |
| `completion.use`       | allow |

### 5.4 viewers（sys-viewer）

| 权限                   | 值    |
| ---------------------- | ----- |
| `agent.create`         | deny  |
| `agent.list_all`       | allow |
| `agent.delete_own`     | deny  |
| `agent.delete_any`     | deny  |
| `agent.stop_own`       | deny  |
| `agent.stop_any`       | deny  |
| `agent.regenerate_own` | deny  |
| `agent.regenerate_any` | deny  |
| `terminal.open`        | deny  |
| `terminal.list`        | deny  |
| `terminal.delete_own`  | deny  |
| `terminal.delete_any`  | deny  |
| `file.read`            | allow |
| `file.write`           | deny  |
| `file.browse`          | allow |
| `config.sync`          | deny  |
| `config.view`          | deny  |
| `node.view`            | allow |
| `node.restart`         | deny  |
| `node.code_update`     | deny  |
| `node.secret`          | deny  |
| `timer.create`         | deny  |
| `timer.list`           | allow |
| `timer.delete_own`     | deny  |
| `timer.delete_any`     | deny  |
| `chat.join`            | deny  |
| `chat.create_room`     | deny  |
| `chat.delete_own_room` | deny  |
| `chat.send_message`    | deny  |
| `chat.private_message` | deny  |
| `group.create`         | deny  |
| `group.join`           | deny  |
| `group.manage_own`     | deny  |
| `data.read`            | allow |
| `data.write`           | deny  |
| `data.delete`          | deny  |
| `model.view`           | allow |
| `completion.use`       | deny  |
| `search.use`           | allow |

### 5.5 chat-users（sys-chat）

| 权限                   | 值    |
| ---------------------- | ----- |
| `agent.create`         | deny  |
| `agent.list_all`       | deny  |
| `agent.delete_own`     | deny  |
| `agent.delete_any`     | deny  |
| `agent.stop_own`       | deny  |
| `agent.stop_any`       | deny  |
| `agent.regenerate_own` | deny  |
| `agent.regenerate_any` | deny  |
| `terminal.open`        | deny  |
| `terminal.list`        | deny  |
| `terminal.delete_own`  | deny  |
| `terminal.delete_any`  | deny  |
| `file.read`            | deny  |
| `file.write`           | deny  |
| `file.browse`          | deny  |
| `config.sync`          | deny  |
| `config.view`          | deny  |
| `node.view`            | deny  |
| `node.restart`         | deny  |
| `node.code_update`     | deny  |
| `node.secret`          | deny  |
| `timer.create`         | deny  |
| `timer.list`           | deny  |
| `timer.delete_own`     | deny  |
| `timer.delete_any`     | deny  |
| `chat.join`            | allow |
| `chat.create_room`     | allow |
| `chat.delete_own_room` | allow |
| `chat.send_message`    | allow |
| `chat.private_message` | allow |
| `group.create`         | deny  |
| `group.join`           | deny  |
| `group.manage_own`     | deny  |
| `data.read`            | deny  |
| `data.write`           | deny  |
| `data.delete`          | deny  |
| `model.view`           | deny  |

---

## 六、权限检查流程

### 6.1 请求处理流程

```text
客户端请求 → JWT解析 → 获取user_id → 权限检查 → 执行/拒绝
```

详细步骤：

1. **Token解析**：从请求Header提取Bearer Token，验证JWT签名与有效期
2. **用户加载**：从JWT payload获取user_id，加载用户信息与权限缓存
3. **权限检查**：根据请求的API路径与操作类型，匹配所需权限标识
4. **资源级检查**（如涉及特定Agent）：检查用户对该资源的ACL
5. **决策**：允许则继续，拒绝则返回403

### 6.2 权限检查中间件

在 `gateway.py` 的 `_check_auth` 基础上扩展为 `_check_auth_and_permission`：

```python
async def _check_auth_and_permission(
    self,
    request,
    required_permission: str,
    resource_type: str = None,
    resource_id: str = None
) -> tuple[bool, Optional[dict]]:
    """检查认证与权限

    Returns:
        (allowed, user_info)
    """
    # 1. 认证检查
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return False, None

    # 2. JWT验证
    payload = validate_jwt_token(token)
    if not payload:
        return False, None

    user_id = payload["user_id"]
    user = user_store.get_user(user_id)
    if not user or user.status != "active":
        return False, None

    # 3. 管理员绕过
    if user.is_admin:
        return True, {"user_id": user_id, "username": user.username, "is_admin": True}

    # 4. 全局权限检查
    if not permission_manager.check_permission(user_id, required_permission):
        return False, None

    # 5. 资源级权限检查
    if resource_type and resource_id:
        if not permission_manager.check_resource_permission(
            user_id, resource_type, resource_id, required_permission
        ):
            return False, None

    return True, {"user_id": user_id, "username": user.username, "is_admin": False}
```

### 6.3 API与权限映射表

| API路径                       | 方法   | 所需权限                                         | 资源类型   |
| ----------------------------- | ------ | ------------------------------------------------ | ---------- |
| `/api/agents`                 | POST   | `agent.create`                                   | -          |
| `/api/agents`                 | GET    | - (仅可见自己的+被授权的)                        | -          |
| `/api/agents/{id}`            | GET    | -                                                | agent.view |
| `/api/agents/{id}`            | DELETE | `agent.delete_own` 或 `agent.delete_any`         | agent      |
| `/api/agents/{id}/stop`       | POST   | `agent.stop_own` 或 `agent.stop_any`             | agent      |
| `/api/agents/{id}/regenerate` | POST   | `agent.regenerate_own` 或 `agent.regenerate_any` | agent      |
| `/api/terminals`              | POST   | `terminal.open`                                  | -          |
| `/api/terminals`              | GET    | `terminal.list`                                  | -          |
| `/api/terminals/{id}`         | DELETE | `terminal.delete_own` 或 `terminal.delete_any`   | -          |
| `/api/file-content`           | GET    | `file.read`                                      | -          |
| `/api/file-write`             | POST   | `file.write`                                     | -          |
| `/api/directories`            | GET    | `file.browse`                                    | -          |
| `/api/node/status`            | GET    | `node.view`                                      | -          |
| `/api/node/secret`            | GET    | `node.secret`                                    | -          |
| `/api/node/restart`           | POST   | `node.restart`                                   | -          |
| `/api/node/code-update`       | POST   | `node.code_update`                               | -          |
| `/api/timers`                 | POST   | `timer.create`                                   | -          |
| `/api/timers`                 | GET    | `timer.list`                                     | -          |
| `/api/timers/{id}`            | DELETE | `timer.delete_own` 或 `timer.delete_any`         | -          |
| `/api/chat/register`          | POST   | `chat.join`                                      | -          |
| `/api/chat/create_room`       | POST   | `chat.create_room`                               | -          |
| `/api/chat/delete_room`       | POST   | `chat.delete_own_room`                           | -          |
| `/api/chat/message`           | POST   | `chat.send_message`                              | -          |
| `/api/chat/private_message`   | POST   | `chat.private_message`                           | -          |
| `/api/groups`                 | POST   | `group.create`                                   | -          |
| `/api/groups/{id}/join`       | POST   | `group.join`                                     | -          |
| `/api/data/read`              | POST   | `data.read`                                      | -          |
| `/api/data/write`             | POST   | `data.write`                                     | -          |
| `/api/data/delete`            | POST   | `data.delete`                                    | -          |
| `/api/admin/users`            | \*     | `user.manage`                                    | -          |
| `/api/admin/groups`           | \*     | `group.manage`                                   | -          |
| `/api/admin/permissions`      | \*     | `permission.manage`                              | -          |
| `/api/model-groups`           | GET    | `model.view`                                     | -          |
| `/api/completions`            | POST   | `completion.use`                                 | -          |
| `/api/search`                 | POST   | `search.use`                                     | -          |

### 6.4 \_own vs_any 判断逻辑

对于 `xxx_own` / `xxx_any` 类权限，检查流程：

```text
1. 用户有 xxx_any 权限？ → 允许操作任意资源
2. 用户有 xxx_own 权限？ → 检查资源是否为用户创建
   - 是 → 允许
   - 否 → 拒绝(403)
3. 均无 → 拒绝(403)
```

需在数据模型中添加 `created_by` 字段标识资源创建者：

- Agent：`agent_manager.py` 的 `create_agent` 需记录 `owner_id`
- Terminal：需记录 `owner_id`

---

## 七、数据存储设计

### 7.1 存储方案

采用JSON文件存储（与现有 `auth_store` 一致），存于 `jarvis_data_dir/auth/` 目录：

```text
jarvis_data_dir/auth/
├── users.json              # 用户数据
├── groups.json             # 权限组数据
├── group_permissions.json  # 组权限配置
├── user_groups.json        # 用户-组关联
├── user_permissions.json   # 用户级权限覆盖
├── resource_acl.json       # 资源级ACL
└── tokens_blacklist.json   # Token黑名单（登出/吊销）
```

### 7.2 数据结构

**users.json**：

```json
{
  "users": {
    "uuid-1": {
      "user_id": "uuid-1",
      "username": "admin",
      "password_hash": "$2b$12$...",
      "display_name": "Administrator",
      "is_admin": true,
      "status": "active",
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-01T00:00:00Z",
      "last_login_at": "2025-01-01T00:00:00Z",
      "locked_reason": null,
      "login_fail_count": 0
    }
  }
}
```

**groups.json**：

```json
{
  "groups": {
    "sys-admin": {
      "group_id": "sys-admin",
      "group_name": "administrators",
      "description": "超级管理员",
      "is_system": true,
      "created_at": "2025-01-01T00:00:00Z"
    }
  }
}
```

**group_permissions.json**：

```json
{
  "sys-admin": {
    "*": "allow"
  },
  "sys-developer": {
    "agent.create": "allow",
    "agent.list_all": "deny",
    "terminal.open": "allow"
  }
}
```

**user_groups.json**：

```json
{
  "uuid-2": ["sys-developer"],
  "uuid-3": ["sys-viewer", "sys-chat"]
}
```

**user_permissions.json**（用户级覆盖，优先级高于组权限）：

```json
{
  "uuid-2": {
    "node.view": "deny"
  }
}
```

**resource_acl.json**：

```json
{
  "agent": {
    "agent-uuid-1": {
      "owner_id": "uuid-2",
      "acl": {
        "uuid-3": {
          "agent.view": true,
          "agent.chat": true,
          "agent.edit_config": false
        }
      }
    }
  }
}
```

### 7.3 内存缓存

启动时加载全部权限数据到内存，变更时同步写回文件：

```python
class PermissionManager:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._users = {}           # user_id -> User
        self._groups = {}          # group_id -> Group
        self._group_perms = {}     # group_id -> {perm: allow/deny}
        self._user_groups = {}     # user_id -> [group_id]
        self._user_perms = {}      # user_id -> {perm: allow/deny}
        self._resource_acl = {}    # resource_type -> {resource_id -> {user_id -> {perm: bool}}}
        self._user_cache = {}      # user_id -> computed effective permissions (lazy)
        self._load_all()

    def check_permission(self, user_id: str, permission: str) -> bool:
        """检查用户全局权限"""
        # 1. 用户级显式拒绝
        user_overrides = self._user_perms.get(user_id, {})
        if user_overrides.get(permission) == "deny":
            return False

        # 2. 用户级显式允许
        if user_overrides.get(permission) == "allow":
            return True

        # 3. 组继承
        for group_id in self._user_groups.get(user_id, []):
            group_perms = self._group_perms.get(group_id, {})
            if group_perms.get(permission) == "allow":
                return True

        # 4. 默认拒绝
        return False

    def check_resource_permission(
        self, user_id: str, resource_type: str,
        resource_id: str, permission: str
    ) -> bool:
        """检查资源级权限"""
        resource = self._resource_acl.get(resource_type, {}).get(resource_id)
        if not resource:
            return False

        # 创建者自动全部允许
        if resource.get("owner_id") == user_id:
            return True

        # 检查ACL
        user_acl = resource.get("acl", {}).get(user_id, {})
        return user_acl.get(permission, False)

    def invalidate_cache(self, user_id: str = None):
        """权限变更时清除缓存"""
        if user_id:
            self._user_cache.pop(user_id, None)
        else:
            self._user_cache.clear()
```

---

## 八、部署与初始化

### 8.1 首次启动

1. 系统首次启动时，自动创建 `admin` 用户，密码从 `JARVIS_ADMIN_PASSWORD` 读取，未设置则随机生成并输出到日志
2. 首次登录后强制修改密码
3. 所有请求必须携带有效JWT Token

### 8.2 Agent归属

- 现有Agent的 `owner_id` 默认设为 `admin`
- 管理员可手动分配Agent给其他用户

### 8.3 前端适配

**ConnectModal.vue 变更**：

- 新增 `username` 输入框（已有，保留）
- `password` 输入框改为用户密码（非全局密码）
- 登录请求改为 `{username, password}`
- 存储返回的JWT Token

**App.vue 变更**：

- `authStore` 改为存储 `{token, user_id, username, is_admin}`
- 所有API请求携带JWT Token

---

## 九、安全考量

### 9.1 密码安全

- 密码使用 bcrypt 哈希存储（cost factor=12）
- 密码策略：最少8字符，建议含大小写+数字+特殊字符
- 连续5次登录失败锁定账户30分钟
- 管理员可手动锁定/解锁账户

### 9.2 Token安全

- JWT签名密钥从 `JARVIS_JWT_SECRET` 环境变量读取，未设置则随机生成（重启后失效）
- Token有效期24小时（可配置）
- 支持Token黑名单（登出时加入）
- 黑名单定期清理过期条目

### 9.3 权限提升防护

- 用户不可自行修改所属组、权限、is_admin状态
- 管理员不可删除自己或最后一个管理员账户
- 权限变更立即生效（清除缓存）
- 所有权限变更操作记录审计日志

### 9.4 API安全

- 所有 `/api/admin/*` 接口需 `user.manage` / `group.manage` / `permission.manage` 权限
- 敏感操作（删除用户、重置密码、修改权限）需二次确认
- API返回403时附带权限标识，便于前端精确提示

---

## 十、实施计划

### 10.1 实施阶段

| 阶段 | 内容                    | 涉及文件                                            | 预估工时 |
| ---- | ----------------------- | --------------------------------------------------- | -------- |
| P1   | 用户管理模块            | 新增 `user_manager.py`，修改 `app.py`、`gateway.py` | 3天      |
| P2   | JWT认证改造             | 修改 `gateway.py`、`app.py`，新增 `jwt_utils.py`    | 2天      |
| P3   | 权限组与权限管理        | 新增 `permission_manager.py`，修改 `app.py`         | 3天      |
| P4   | 资源级权限（Agent ACL） | 修改 `agent_manager.py`、`app.py`                   | 2天      |
| P5   | API权限拦截             | 修改 `app.py` 所有路由，添加权限检查                | 3天      |
| P6   | 前端适配                | 修改 `ConnectModal.vue`、`App.vue`                  | 2天      |
| P7   | 测试与文档              | 单元测试、集成测试、用户文档                        | 2天      |

#### 总计约17个工作日

### 10.2 新增文件清单

| 文件                                          | 说明                          |
| --------------------------------------------- | ----------------------------- |
| `jarvis_web_gateway/user_manager.py`          | 用户管理器（CRUD、密码验证）  |
| `jarvis_web_gateway/permission_manager.py`    | 权限管理器（权限检查、缓存）  |
| `jarvis_web_gateway/jwt_utils.py`             | JWT工具（签发、验证、黑名单） |
| `jarvis_data_dir/auth/users.json`             | 用户数据存储                  |
| `jarvis_data_dir/auth/groups.json`            | 权限组数据存储                |
| `jarvis_data_dir/auth/group_permissions.json` | 组权限配置                    |
| `jarvis_data_dir/auth/user_groups.json`       | 用户-组关联                   |
| `jarvis_data_dir/auth/user_permissions.json`  | 用户级权限覆盖                |
| `jarvis_data_dir/auth/resource_acl.json`      | 资源级ACL                     |
| `jarvis_data_dir/auth/tokens_blacklist.json`  | Token黑名单                   |

### 10.3 修改文件清单

| 文件                                                      | 修改内容                                        |
| --------------------------------------------------------- | ----------------------------------------------- |
| `jarvis_web_gateway/app.py`                               | 所有路由添加权限检查，新增admin API             |
| `jarvis_gateway/gateway.py`                               | `_check_auth` 改为 `_check_auth_and_permission` |
| `jarvis_web_gateway/agent_manager.py`                     | `create_agent` 添加 `owner_id` 字段             |
| `jarvis_web_gateway/chat_manager.py`                      | `created_by` 改为 `owner_id`                    |
| `jarvis_service/frontend/src/App.vue`                     | 权限状态管理、功能入口控制                      |
| `jarvis_service/frontend/src/components/ConnectModal.vue` | 登录表单改为username+password                   |

---

## 十一、环境变量

| 变量名                         | 说明                       | 默认值               |
| ------------------------------ | -------------------------- | -------------------- |
| `JARVIS_ADMIN_PASSWORD`        | 初始管理员密码（首次启动） | 随机生成             |
| `JARVIS_JWT_SECRET`            | JWT签名密钥                | 随机生成（重启失效） |
| `JARVIS_JWT_EXPIRE_HOURS`      | JWT有效期（小时）          | 24                   |
| `JARVIS_LOCK_FAIL_COUNT`       | 登录失败锁定阈值           | 5                    |
| `JARVIS_LOCK_DURATION_MINUTES` | 锁定时长（分钟）           | 30                   |

---

## 十二、总结

本方案为 Jarvis Web Gateway 设计了完整的多用户认证与分组权限管理体系：

1. **独立用户系统**：每用户独立账户密码，JWT Token认证，支持管理员管理
2. **分组权限**：5个内置组（admin/operator/developer/viewer/chat-user）+ 自定义组
3. **细粒度权限**：42项全局权限 + 8项Agent资源级权限，覆盖全部API
4. **权限优先级**：管理员绕过 → 用户级拒绝 → 用户级允许 → 组继承 → 资源ACL → 默认拒绝
5. **安全加固**：bcrypt密码、JWT签名、失败锁定、权限提升防护
   权限粒度已细化到Agent级别，支持对单个Agent的查看/对话/配置/停止/删除/日志/会话等8项操作控制，满足多用户协作场景下的权限隔离需求。
