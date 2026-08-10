# Jarvis 多用户认证系统实施指导文档

> 本文档为 Agent 编码指导，描述如何将当前单Token认证系统改造为多用户JWT认证系统。
> 配合 `docs/design/multi-user-auth-permission.md` 方案文档使用。

## 一、当前系统认证架构

### 1.1 认证流程（现状）

```text
用户输入密码 → POST /api/auth/login {password} → 验证JARVIS_GATEWAY_PASSWORD
→ 返回全局唯一Token(UUID) → 前端存localStorage(jarvis_auth_token)
→ 后续请求Bearer Token → validate_gateway_token()比对环境变量
```

### 1.2 关键文件与行号

| 文件               | 关键位置                       | 说明                           |
| ------------------ | ------------------------------ | ------------------------------ |
| `token_manager.py` | 全文65行                       | Token生成/验证，UUID存环境变量 |
| `gateway.py`       | L63-90 `_check_auth`           | WebSocket认证入口              |
| `gateway.py`       | L92-129 `_check_auth_fallback` | CLI密码回退认证                |
| `app.py`           | L1495-1547 `verify_token`      | HTTP API Token验证依赖         |
| `app.py`           | L1559-1630 `login`             | 登录路由，验证密码返回Token    |
| `app.py`           | L1339-1341                     | 启动时生成Token存环境变量      |
| `app.py`           | L1640-1660                     | WebSocket路由，无Token验证     |
| `agent_manager.py` | L125-142 `create_agent`        | 无owner_id参数                 |
| `chat_manager.py`  | L21-33 `__init__`              | 客户端/房间无user_id关联       |
| `App.vue`          | L1228-1254 `loginWithPassword` | 前端登录逻辑                   |
| `App.vue`          | L1274-1287                     | Token加载/存储                 |
| `ConnectModal.vue` | L14, L33                       | 密码输入框                     |

### 1.3 核心问题

1. **无用户概念**：全局共享一个Token，无法区分用户身份
2. **Token无过期**：UUID Token永久有效，重启才失效
3. **无权限控制**：持有Token即拥有全部权限
4. **资源无归属**：Agent/Terminal/Timer无owner_id，无法做\_own权限判断

---

## 二、实施顺序与依赖关系

```text
P1: jwt_utils.py (无依赖)
  ↓
P2: user_manager.py (依赖jwt_utils)
  ↓
P3: permission_manager.py (依赖user_manager)
  ↓
P4: 修改 gateway.py + token_manager.py (依赖jwt_utils)
  ↓
P5: 修改 app.py 认证+路由 (依赖P1-P4全部)
  ↓
P6: 修改 agent_manager.py + chat_manager.py (依赖P5)
  ↓
P7: 修改前端 App.vue + ConnectModal.vue (依赖P5)
```

---

## 三、新增文件详细设计

### 3.1 `src/jarvis/jarvis_web_gateway/jwt_utils.py`

**职责**：JWT Token签发、验证、黑名单管理

**需实现的函数**：

1. `generate_jwt_token(user_id: str, username: str, is_admin: bool) -> str`
   - 使用 `JARVIS_JWT_SECRET` 环境变量作为签名密钥
   - 未设置则随机生成（存内存，重启失效）
   - payload含：`user_id`, `username`, `is_admin`, `iat`, `exp`, `jti`
   - 有效期从 `JARVIS_JWT_EXPIRE_HOURS` 读取，默认24小时

2. `validate_jwt_token(token: str) -> Optional[dict]`
   - 验证签名和有效期
   - 检查Token是否在黑名单中
   - 返回payload字典或None

3. `revoke_token(token: str) -> None`
   - 将Token的jti加入黑名单
   - 黑名单存内存dict，定期清理过期条目

4. `cleanup_revoked_tokens() -> None`
   - 清理黑名单中已过期的条目

**依赖**：`PyJWT` 库（需添加到requirements）

**环境变量**：

- `JARVIS_JWT_SECRET`：签名密钥
- `JARVIS_JWT_EXPIRE_HOURS`：有效期（默认24）

---

### 3.2 `src/jarvis/jarvis_web_gateway/user_manager.py`

**职责**：用户CRUD、密码验证、用户状态管理

**需实现的类 `UserManager`**：

1. `__init__(self, data_dir: str)`
   - 初始化数据目录 `jarvis_data_dir/auth/`
   - 加载 `users.json` 到内存
   - 若无数据文件，创建初始admin用户

2. `create_user(self, username: str, password: str, display_name: str = None, is_admin: bool = False) -> dict`
   - 验证用户名唯一性（3-32字符，仅字母数字下划线）
   - bcrypt哈希密码（cost=12）
   - 返回用户信息（不含password_hash）

3. `authenticate(self, username: str, password: str) -> Optional[dict]`
   - 查找用户，验证bcrypt密码
   - 检查用户状态（active/locked）
   - 登录成功：重置login_fail_count，更新last_login_at
   - 登录失败：递增login_fail_count，达到5次则锁定
   - 返回用户信息或None

4. `get_user(self, user_id: str) -> Optional[dict]`
   - 返回用户信息（不含password_hash）

5. `update_user(self, user_id: str, **kwargs) -> Optional[dict]`
   - 可修改：display_name, status, is_admin

6. `reset_password(self, user_id: str, new_password: str) -> bool`
   - 管理员重置密码

7. `change_password(self, user_id: str, old_password: str, new_password: str) -> bool`
   - 用户自助改密，需验证旧密码

8. `delete_user(self, user_id: str) -> bool`
   - 不可删自己，不可删最后一个管理员

9. `list_users(self, search: str = None, offset: int = 0, limit: int = 50) -> list`
   - 支持搜索和分页

10. `_ensure_admin_user(self) -> None`
    - 首次启动时创建admin用户
    - 密码从 `JARVIS_ADMIN_PASSWORD` 读取，未设置则随机生成并输出到日志

**数据存储**：`jarvis_data_dir/auth/users.json`

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
      "last_login_at": null,
      "locked_reason": null,
      "login_fail_count": 0
    }
  }
}
```

**依赖**：`bcrypt` 库（需添加到requirements）

**环境变量**：

- `JARVIS_ADMIN_PASSWORD`：初始admin密码（未设置则随机生成）

---

### 3.3 `src/jarvis/jarvis_web_gateway/permission_manager.py`

**职责**：权限组管理、权限检查、资源级ACL

**需实现的类 `PermissionManager`**：

1. `__init__(self, data_dir: str)`
   - 加载5个JSON文件：groups.json, group_permissions.json, user_groups.json, user_permissions.json, resource_acl.json
   - 初始化5个内置组（sys-admin, sys-operator, sys-developer, sys-viewer, sys-chat）
   - 权限缓存：`_permission_cache: dict`，用户权限变更时失效

2. `check_permission(self, user_id: str, permission: str) -> bool`
   - 判定优先级：用户级显式拒绝 → 用户级显式允许 → 组继承允许 → 默认拒绝
   - 先查缓存，未命中则计算并缓存

3. `check_resource_permission(self, user_id: str, resource_type: str, resource_id: str, permission: str) -> bool`
   - 创建者自动全部允许 → 检查resource_acl.json

4. `get_user_permissions(self, user_id: str) -> dict`
   - 返回用户有效权限（含组继承+用户覆盖）

5. 组管理方法：
   - `create_group(self, name, display_name, description) -> dict`
   - `update_group(self, group_id, **kwargs) -> dict`
   - `delete_group(self, group_id) -> bool`（不可删内置组）
   - `get_group(self, group_id) -> dict`
   - `list_groups(self) -> list`

6. 组权限方法：
   - `get_group_permissions(self, group_id) -> dict`
   - `set_group_permissions(self, group_id, permissions: dict) -> dict`

7. 用户组方法：
   - `get_user_groups(self, user_id) -> list`
   - `set_user_groups(self, user_id, group_ids: list) -> list`

8. 用户权限覆盖：
   - `get_user_overrides(self, user_id) -> dict`
   - `set_user_overrides(self, user_id, overrides: dict) -> dict`

9. 资源ACL方法：
   - `set_resource_acl(self, resource_type, resource_id, acl: dict) -> dict`
   - `get_resource_acl(self, resource_type, resource_id) -> dict`
   - `delete_resource_acl(self, resource_type, resource_id) -> bool`

10. `invalidate_cache(self, user_id: str = None)`
    - user_id=None时清全量缓存
    - 指定user_id时只清该用户缓存

**数据存储**：`jarvis_data_dir/auth/` 下5个JSON文件

**内置组权限映射**（见方案文档第五章）：

| 内置组        | 权限范围                                                  |
| ------------- | --------------------------------------------------------- |
| sys-admin     | 全部权限（_:_）                                           |
| sys-operator  | agent:_, terminal:_, timer:_, chat:_                      |
| sys-developer | agent:create,agent:read,agent:execute, terminal:_, chat:_ |
| sys-viewer    | agent:read, terminal:read, chat:\*                        |
| sys-chat      | chat:\*                                                   |

**权限格式**：`resource:action`，如 `agent:create`, `terminal:write`, `admin:users`

**权限覆盖格式**：

```json
{
  "user_id_1": {
    "agent:delete": "deny",
    "admin:users": "allow"
  }
}
```

---

## 四、现有文件修改详细指导

### 4.1 `src/jarvis/jarvis_web_gateway/token_manager.py`

**修改目标**：保留旧函数签名兼容，新增JWT验证入口

**修改点**：

1. **L1-5 导入区**：新增 `from .jwt_utils import validate_jwt_token, generate_jwt_token`

2. **L26-44 `validate_gateway_token`**：修改为优先尝试JWT验证

   ```python
   # 原逻辑：比对环境变量JARVIS_AUTH_TOKEN
   # 新逻辑：先尝试JWT验证，失败再回退环境变量比对
   def validate_gateway_token(token: str) -> Optional[dict]:
       # 优先JWT验证
       payload = validate_jwt_token(token)
       if payload:
           return payload
       # 回退：环境变量比对（CLI Gateway用）
       env_token = os.environ.get('JARVIS_AUTH_TOKEN')
       if env_token and token == env_token:
           return {'user_id': 'system', 'username': 'gateway', 'is_admin': True}
       return None
   ```

3. **L15-23 `generate_gateway_token`**：保留不变（CLI Gateway仍需UUID Token）

4. **新增函数 `validate_token_with_user`**：

   ```python
   def validate_token_with_user(token: str) -> Optional[dict]:
       """验证Token并返回用户信息，用于HTTP API认证"""
       payload = validate_jwt_token(token)
       if payload:
           return payload
       # 回退旧Token
       env_token = os.environ.get('JARVIS_AUTH_TOKEN')
       if env_token and token == env_token:
           return {'user_id': 'system', 'username': 'gateway', 'is_admin': True}
       return None
   ```

---

### 4.2 `src/jarvis/jarvis_gateway/gateway.py`

**修改目标**：WebSocket认证改用JWT

**修改点**：

1. **L1-10 导入区**：新增 `from jarvis_web_gateway.jwt_utils import validate_jwt_token`

2. **L63-90 `_check_auth`**：修改Token验证逻辑

   ```python
   # 原逻辑：调用validate_gateway_token比对环境变量
   # 新逻辑：调用validate_jwt_token验证JWT
   async def _check_auth(self, websocket, client_id):
       token = websocket.query_params.get('token')
       if not token:
           # 尝试从headers获取
           token = websocket.headers.get('X-Jarvis-Token')
       if not token:
           return False
       payload = validate_jwt_token(token)
       if payload:
           self._client_users[client_id] = payload  # 存储用户信息
           return True
       # 回退旧Token
       env_token = os.environ.get('JARVIS_AUTH_TOKEN')
       if env_token and token == env_token:
           self._client_users[client_id] = {'user_id': 'system', 'username': 'gateway', 'is_admin': True}
           return True
       return False
   ```

3. **新增实例变量 `self._client_users: dict`**：在 `__init__` 中初始化，存储 client_id → user_info 映射

4. **新增方法 `get_client_user(self, client_id) -> Optional[dict]`**：获取WebSocket连接的用户信息

#### 4.3.5 WebSocket认证修改

1. **L1640-1660 WebSocket路由**：添加Token验证
   - 从query_params提取token并验证JWT
   - 验证失败关闭连接（code=4001）
   - 将user_info存入websocket.state.user
   - 5个WebSocket端点均需同样修改：`/ws`, `/ws/agent/{id}`, `/ws/terminal/{id}`, `/ws/chat`, `/ws/screenshot`

---

### 4.4 `src/jarvis/jarvis_web_gateway/agent_manager.py`

**修改目标**：Agent资源归属owner_id

**修改点**：

1. **L125-142 `create_agent`**：新增 `owner_id` 参数

   ```python
   # 原签名：async def create_agent(self, agent_type, working_dir, ...)
   # 新签名：async def create_agent(self, agent_type, working_dir, owner_id=None, ...)
   # 在_agent_info中新增：'owner_id': owner_id
   ```

2. **Agent信息结构新增字段**：
   - `owner_id: str` - 创建者user_id
   - `owner_name: str` - 创建者username（冗余，便于前端显示）

3. **新增方法 `get_agents_by_owner(self, owner_id: str) -> list`**：获取某用户创建的所有Agent

4. **`list_agents` 方法**：非admin用户只能看到自己的Agent（需配合app.py路由层过滤）

---

### 4.5 `src/jarvis/jarvis_web_gateway/chat_manager.py`

**修改目标**：聊天室关联user_id

**修改点**：

1. **L39-46 `register_client`**：新增 `user_id`, `username` 参数

   ```python
   # 原签名：def register_client(self, client_id, client_name)
   # 新签名：def register_client(self, client_id, client_name, user_id=None, username=None)
   # _clients结构新增：'user_id': user_id, 'username': username
   ```

2. **L21-33 `__init__` 中 `_chat_rooms`**：房间结构新增 `owner_id` 字段
   - `create_room` 方法新增 `owner_id` 参数
   - `delete_room` 方法验证owner_id（仅创建者可删）

3. **`join_room` / `leave_room`**：记录user_id而非仅client_name

4. **广播事件新增user_id字段**：
   - `chat_message`: 新增 `user_id` 字段
   - `chat_client_joined` / `chat_client_left`: 新增 `user_id` 字段

---

## 五、前端修改详细指导

### 5.1 `src/jarvis/jarvis_service/frontend/src/App.vue`

**修改目标**：登录改为用户名+密码，Token改为JWT，新增用户信息管理

**修改点**：

1. **L1190 `auth` 响应式对象**：新增username字段

   ```javascript
   // 原：auth: reactive({ password: '' })
   // 新：auth: reactive({ username: '', password: '' })
   ```

2. **L1228-1254 `loginWithPassword`**：改为发送username+password，存储JWT和用户信息

   ```javascript
   async function loginWithPassword(username, password) {
     const response = await fetch(
       `${getHttpProtocol()}://${host}:${port}/api/auth/login`,
       {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ username, password }),
       },
     );
     const result = await response.json();
     if (result.token) {
       localStorage.setItem("jarvis_auth_token", result.token);
       localStorage.setItem("jarvis_user_info", JSON.stringify(result.user));
       // ... 原有逻辑
     }
   }
   ```

3. **L1274-1287 Token加载**：同时加载用户信息

   ```javascript
   const savedToken = localStorage.getItem("jarvis_auth_token");
   const savedUserInfo = localStorage.getItem("jarvis_user_info");
   if (savedToken && savedUserInfo) {
     userInfo.value = JSON.parse(savedUserInfo);
   }
   ```

4. **新增响应式变量**：
   - `userInfo: ref(null)` - 当前登录用户信息
   - `isAdmin: computed(() => userInfo.value?.is_admin ?? false)`

5. **WebSocket连接**：URL添加token参数

   ```javascript
   // 原：ws://host:port/ws
   // 新：ws://host:port/ws?token=jwt_token
   ```

6. **401处理（L1316）**：清除token和用户信息，显示登录框

   ```javascript
   localStorage.removeItem("jarvis_auth_token");
   localStorage.removeItem("jarvis_user_info");
   userInfo.value = null;
   ```

7. **新增API调用**：
   - `GET /api/auth/me` - 获取当前用户信息（页面刷新时验证Token有效性）
   - `POST /api/auth/logout` - 注销
   - `POST /api/auth/change-password` - 修改密码

---

### 5.2 `src/jarvis/jarvis_service/frontend/src/components/ConnectModal.vue`

**修改目标**：登录框改为用户名+密码

**修改点**：

1. **L14 密码输入框**：新增username输入框

   ```html
   <!-- 新增 -->
   <div class="form-group">
     <label>Username</label>
     <input v-model="username" type="text" placeholder="Enter username" />
   </div>
   <!-- 原有密码框保留 -->
   <div class="form-group">
     <label>Password</label>
     <input v-model="password" type="password" placeholder="Enter password" />
   </div>
   ```

2. **新增props/emits**：
   - prop: `username` (双向绑定)
   - emit: `update:username`

3. **登录按钮逻辑**：emit时同时传递username和password

---

### 5.3 前端用户管理UI（新增）

**修改目标**：为管理员提供用户/权限管理界面

**新增组件**：

1. **`src/jarvis/jarvis_service/frontend/src/components/UserManagement.vue`**
   - 用户列表（表格：用户名/显示名/状态/组/操作）
   - 创建用户弹窗（username + password + display_name + is_admin）
   - 编辑用户弹窗（display_name + status + 组分配）
   - 重置密码弹窗
   - 删除确认
   - 仅 `is_admin=true` 或有 `admin:users` 权限时可见

2. **`src/jarvis/jarvis_service/frontend/src/components/PermissionManagement.vue`**
   - 权限组列表（表格：组名/显示名/成员数/操作）
   - 组权限编辑（checkbox矩阵：资源×动作）
   - 组成员管理（添加/移除用户）
   - 仅 `is_admin=true` 或有 `admin:permissions` 权限时可见

3. **App.vue 集成**：
   - 新增顶部导航栏用户菜单（头像/用户名下拉）
   - 下拉菜单项：用户信息、修改密码、用户管理（admin）、权限管理（admin）、注销
   - 新增路由/Tab：用户管理、权限管理
   - `userInfo` ref驱动UI权限控制（v-if="isAdmin"）

4. **修改密码弹窗**：
   - 所有用户可用
   - 旧密码 + 新密码 + 确认密码
   - 调用 `POST /api/auth/change-password`

---

### 5.4 VSCode插件认证适配

**文件**：`src/jarvis/jarvis_vscode_extension/src/extension.ts`（6369行）

**修改目标**：登录改为username+password，Token改为JWT

**修改点**：

1. **L122-125 `ChatPanelState` 接口**：新增username字段

   ```typescript
   // 原：password: string; token: string;
   // 新：username: string; password: string; token: string;
   ```

2. **L322-325 初始状态**：新增username默认值

   ```typescript
   // 原：password: "", token: "",
   // 新：username: "", password: "", token: "",
   ```

3. **L204-226 `AgentListViewMessage` 接口**：新增username字段

   ```typescript
   // 原：password?: string;
   // 新：username?: string; password?: string;
   ```

4. **L1442-1452 `getLeftLoginHtml` 登录表单**：新增username输入框

   ```html
   <!-- 在gatewayUrl和password之间新增 -->
   <div class="form-group">
     <label for="username">用户名</label>
     <input
       id="username"
       type="text"
       value="${escapeHtml(this.panelState.username)}"
       placeholder="admin"
     />
   </div>
   ```

5. **L1457-1484 登录脚本**：发送username+password

   ```javascript
   // 原：vscode.postMessage({ type: 'connect', gatewayUrl, password })
   // 新：vscode.postMessage({ type: 'connect', gatewayUrl, username, password })
   // 获取username：const username = document.getElementById('username');
   ```

6. **`connectFromLeftView` 方法**：改为username+password登录

   ```typescript
   // 原：POST /api/auth/login { password }
   // 新：POST /api/auth/login { username, password }
   // 存储返回的JWT token和用户信息
   ```

7. **L1174 API请求Authorization头**：保持不变（Bearer + JWT token格式兼容）

8. **WebSocket连接**：URL添加token参数

   ```typescript
   // 原：ws://host:port/ws
   // 新：ws://host:port/ws?token=jwt_token
   ```

9. **新增用户信息存储**：
   - `panelState` 新增 `userInfo: { user_id, username, display_name, is_admin } | null`
   - 登录成功后存储userInfo
   - 401响应时清除token和userInfo

10. **设置面板新增**（L913-974 settingsPanelMarkup）：
    - 显示当前登录用户名
    - 修改密码按钮
    - 注销按钮

---

## 六、依赖与部署

### 6.1 Python依赖新增

在 `requirements.txt` 或 `pyproject.toml` 中添加：

```text
PyJWT>=2.8.0
bcrypt>=4.0.0
```

### 6.2 环境变量

| 变量名                    | 必需 | 默认值   | 说明                              |
| ------------------------- | ---- | -------- | --------------------------------- |
| `JARVIS_JWT_SECRET`       | 否   | 随机生成 | JWT签名密钥，生产环境必须设置     |
| `JARVIS_JWT_EXPIRE_HOURS` | 否   | 24       | JWT有效期（小时）                 |
| `JARVIS_ADMIN_PASSWORD`   | 否   | 随机生成 | 初始admin密码，首次启动输出到日志 |

### 6.3 数据目录

首次启动自动创建 `jarvis_data_dir/auth/` 目录及以下文件：

```text
auth/
  users.json          # 用户数据
  groups.json         # 权限组定义
  group_permissions.json  # 组权限映射
  user_groups.json    # 用户-组关系
  user_permissions.json   # 用户权限覆盖
  resource_acl.json   # 资源级ACL
```

### 6.4 首次启动流程

1. 检查 `auth/users.json` 是否存在
2. 不存在则创建目录和初始文件
3. 创建admin用户（密码从环境变量或随机生成）
4. 创建5个内置权限组
5. 将admin用户加入sys-admin组
6. 输出admin密码到日志（仅首次）

---

## 七、验证清单

### 7.1 后端验证

- [ ] `POST /api/auth/login` 用username+password登录返回JWT
- [ ] `GET /api/auth/me` 用JWT获取当前用户信息
- [ ] `POST /api/auth/logout` 注销后Token失效
- [ ] `POST /api/users` 创建用户（需admin权限）
- [ ] 非admin用户访问admin接口返回403
- [ ] JWT过期后请求返回401
- [ ] WebSocket连接带token参数可认证
- [ ] WebSocket连接无token或无效token被拒绝
- [ ] Agent创建时记录owner_id
- [ ] 非owner用户删除Agent返回403（无agent:delete权限时）

### 7.2 前端验证

- [ ] 登录框显示username+password两个输入框
- [ ] 登录成功后显示用户名
- [ ] Token过期后自动跳转登录框
- [ ] WebSocket连接正常（带token参数）
- [ ] 聊天室功能正常（user_id关联）
- [ ] 页面刷新后自动恢复登录状态（JWT未过期时）

### 7.3 权限验证

- [ ] sys-admin组用户可执行所有操作
- [ ] sys-viewer组用户只能查看，不能创建/删除
- [ ] sys-chat组用户只能使用聊天功能
- [ ] 用户级deny覆盖组级allow
- [ ] 资源owner可管理自己的资源
