<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal admin-modal">
      <div class="modal-header">
        <h2>系统管理</h2>
        <button class="close-btn" @click="close">×</button>
      </div>
      <div class="admin-tabs">
        <button class="admin-tab" :class="{ active: activeTab === 'users' }" @click="switchTab('users')">用户管理</button>
        <button class="admin-tab" :class="{ active: activeTab === 'groups' }" @click="switchTab('groups')">权限组</button>
        <button class="admin-tab" :class="{ active: activeTab === 'system' }" @click="switchTab('system')">系统配置</button>
      </div>
      <!-- 用户管理 -->
      <div v-if="activeTab === 'users'" class="tab-content">
        <div class="form-group" v-if="showCreateUser">
          <label>创建新用户</label>
          <div class="form-row"><label>用户名</label><input v-model="newUserForm.username" placeholder="输入用户名" /></div>
          <div class="form-row"><label>密码</label><input v-model="newUserForm.password" type="password" placeholder="输入密码" /></div>
          <div class="form-row"><label>显示名</label><input v-model="newUserForm.display_name" placeholder="输入显示名（可选）" /></div>
          <div class="form-row"><label>管理员</label><label class="toggle-switch"><input type="checkbox" v-model="newUserForm.is_admin" class="toggle-input" /><span class="toggle-slider"></span></label></div>
          <div class="btn-group"><button class="ghost-btn" @click="createUser" :disabled="loading">创建</button><button class="ghost-btn" @click="showCreateUser = false">取消</button></div>
        </div>
        <div class="form-group" v-else><button class="ghost-btn" @click="showCreateUser = true">+ 创建用户</button></div>
        <div class="form-group">
          <div v-if="loading" style="text-align:center;padding:16px;color:var(--text-secondary,#888)">加载中...</div>
          <table v-else class="admin-table">
            <thead><tr><th>用户名</th><th>显示名</th><th>管理员</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="user in users" :key="user.user_id">
                <td>{{ user.username }}</td><td>{{ user.display_name || '-' }}</td><td>{{ user.is_admin ? '是' : '否' }}</td>
                <td><div class="btn-group"><button class="btn-sm" @click="openEditUser(user)">编辑</button><button class="btn-sm" @click="openGroupAssign(user)">分配组</button><button class="btn-sm" @click="openResetPassword(user)">重置密码</button><button class="btn-sm danger" @click="deleteUser(user)" :disabled="user.user_id === currentUserId">删除</button></div></td>
              </tr>
              <tr v-if="users.length === 0"><td colspan="4" style="text-align:center;color:var(--text-secondary,#888)">暂无用户</td></tr>
            </tbody>
          </table>
        </div>
        <!-- 用户组分配 -->
        <div class="expand-section" v-if="showGroupAssign && selectedUser">
          <div style="margin-bottom:8px;font-weight:600;font-size:13px">分配组 - {{ selectedUser.username }}</div>
          <div v-if="loadingGroups" style="color:var(--text-secondary,#888);font-size:13px">加载中...</div>
          <div v-else>
            <div class="group-checkbox" v-for="group in allGroups" :key="group.group_id">
              <input type="checkbox" :value="group.group_id" v-model="userGroupIds" />
              <span>{{ group.display_name || group.name }}</span>
              <span v-if="group.description" style="color:var(--text-secondary,#888);font-size:12px;margin-left:4px">({{ group.description }})</span>
            </div>
            <div class="btn-group" style="margin-top:8px">
              <button class="ghost-btn" @click="saveUserGroups" :disabled="loading">保存</button>
              <button class="ghost-btn" @click="showGroupAssign = false">取消</button>
            </div>
          </div>
        </div>
        <!-- 重置密码 -->
        <div class="expand-section" v-if="showResetPassword && selectedUser">
          <div style="margin-bottom:8px;font-weight:600;font-size:13px">重置密码 - {{ selectedUser.username }}</div>
          <div class="form-row"><label>新密码</label><input v-model="resetPasswordForm.new_password" type="password" placeholder="输入新密码" /></div>
          <div class="btn-group">
            <button class="ghost-btn" @click="resetPassword" :disabled="loading">确认重置</button>
            <button class="ghost-btn" @click="showResetPassword = false">取消</button>
          </div>
        </div>
        <!-- 编辑用户 -->
        <div class="expand-section" v-if="showEditUser && selectedEditUser">
          <div style="margin-bottom:8px;font-weight:600;font-size:13px">编辑用户 - {{ selectedEditUser.username }}</div>
          <div class="form-row"><label>显示名</label><input v-model="editUserForm.display_name" placeholder="输入显示名（可选）" /></div>
          <div class="form-row"><label>管理员</label><label class="toggle-switch"><input type="checkbox" v-model="editUserForm.is_admin" class="toggle-input" /><span class="toggle-slider"></span></label></div>
          <div class="form-row"><label>状态</label><select v-model="editUserForm.status"><option value="active">活跃</option><option value="disabled">禁用</option><option value="locked">锁定</option></select></div>
          <div class="btn-group">
            <button class="ghost-btn" @click="updateUser" :disabled="loading">保存</button>
            <button class="ghost-btn" @click="showEditUser = false">取消</button>
          </div>
        </div>
      </div>
      <!-- 权限组管理 -->
      <div v-if="activeTab === 'groups'" class="tab-content">
        <div class="form-group" v-if="showCreateGroup">
          <label>创建新权限组</label>
          <div class="form-row"><label>组名</label><input v-model="newGroupForm.name" placeholder="输入组名" /></div>
          <div class="form-row"><label>描述</label><input v-model="newGroupForm.description" placeholder="输入描述（可选）" /></div>
          <div class="btn-group"><button class="ghost-btn" @click="createGroup" :disabled="loading">创建</button><button class="ghost-btn" @click="showCreateGroup = false">取消</button></div>
        </div>
        <div class="form-group" v-else><button class="ghost-btn" @click="showCreateGroup = true">+ 创建权限组</button></div>
        <div class="form-group">
          <div v-if="loading" style="text-align:center;padding:16px;color:var(--text-secondary,#888)">加载中...</div>
          <table v-else class="admin-table">
            <thead><tr><th>组名</th><th>显示名</th><th>描述</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="group in groups" :key="group.group_id">
                <td>{{ group.name }}</td><td>{{ group.display_name || '-' }}</td><td>{{ group.description || '-' }}</td>
                <td><div class="btn-group"><button class="btn-sm" @click="openEditGroup(group)">编辑</button><button class="btn-sm danger" @click="deleteGroup(group)">删除</button></div></td>
              </tr>
              <tr v-if="groups.length === 0"><td colspan="4" style="text-align:center;color:var(--text-secondary,#888)">暂无权限组</td></tr>
            </tbody>
          </table>
        </div>
        <!-- 编辑组 -->
        <div class="expand-section" v-if="showEditGroup && selectedGroup">
          <div style="margin-bottom:8px;font-weight:600;font-size:13px">编辑组 - {{ selectedGroup.name }}</div>
          <div class="form-row"><label>显示名</label><input v-model="editGroupForm.display_name" placeholder="输入显示名" /></div>
          <div class="form-row"><label>描述</label><input v-model="editGroupForm.description" placeholder="输入描述" /></div>
          <!-- 权限矩阵 -->
          <div class="permission-matrix">
            <div style="margin-bottom:8px;font-weight:600;font-size:13px">权限设置</div>
            <div v-if="loadingGroupPerms" style="color:var(--text-secondary,#888);font-size:13px">加载权限中...</div>
            <table v-else class="perm-table">
              <thead><tr><th>资源</th><th>动作</th><th>权限</th></tr></thead>
              <tbody>
                <template v-for="(actions, resource) in permissionSchema" :key="resource">
                  <tr v-for="(action, idx) in actions" :key="resource + ':' + action">
                    <td v-if="idx === 0" :rowspan="actions.length" class="perm-resource-cell">{{ resourceLabels[resource] || resource }}</td>
                    <td class="perm-action-cell">{{ action }}</td>
                    <td class="perm-value-cell">
                      <select class="perm-select" v-model="editPermissions[resource + ':' + action]">
                        <option value="">无</option>
                        <option value="allow">✓ 允许</option>
                        <option value="deny">✗ 拒绝</option>
                      </select>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <!-- 可访问节点 -->
          <div class="permission-matrix" style="margin-top:12px">
            <div style="margin-bottom:8px;font-weight:600;font-size:13px">可访问节点</div>
            <div style="font-size:12px;color:var(--text-secondary,#888);margin-bottom:8px">空列表=无节点权限，["*"]=所有节点，指定节点ID=限定节点</div>
            <div class="form-row" style="align-items:flex-start">
              <label style="min-width:60px">节点列表</label>
              <div style="flex:1;display:flex;flex-direction:column;gap:6px;align-items:flex-start">
                <label class="checkbox-label" style="margin-bottom:0">
                  <input type="checkbox" :checked="editAccessibleNodes.includes('*')" @change="toggleAllNodesAccess" />
                  <span>所有节点 ("*")</span>
                </label>
                <template v-if="!editAccessibleNodes.includes('*')">
                  <label v-for="node in availableNodeOptions" :key="node.node_id" class="checkbox-label" style="margin-bottom:0">
                    <input type="checkbox" :checked="editAccessibleNodes.includes(node.node_id)" @change="toggleNodeAccess(node.node_id)" />
                    <span>{{ formatNodeOptionLabel(node) }}</span>
                  </label>
                  <label class="checkbox-label" style="margin-bottom:0">
                    <input type="checkbox" :checked="editAccessibleNodes.includes('master')" @change="toggleNodeAccess('master')" />
                    <span>本节点 (master)</span>
                  </label>
                  <div v-if="availableNodeOptions.length === 0" style="font-size:12px;color:var(--text-secondary,#888)">暂无子节点</div>
                </template>
              </div>
            </div>
          </div>
          <div class="btn-group"><button class="ghost-btn" @click="updateGroup" :disabled="loading">保存</button><button class="ghost-btn" @click="showEditGroup = false">取消</button></div>
        </div>
      </div>
      <!-- 系统配置 -->
      <div v-if="activeTab === 'system'" class="tab-content">
        <!-- 重启节点服务 -->
        <div class="form-group" v-if="availableNodeOptions.length > 0">
          <label>重启节点服务</label>
          <div class="restart-service-section">
            <div class="restart-service-row">
              <select v-model="localRestartNodeId" class="node-select">
                <option value="">本节点 (master)</option>
                <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
                  {{ formatNodeOptionLabel(node) }}
                </option>
              </select>
              <span class="form-help">选择要重启服务的节点，默认为本节点</span>
            </div>
            <div class="restart-service-row" v-if="!localRestartNodeId || localRestartNodeId === 'master'">
              <label class="checkbox-label">
                <input type="checkbox" v-model="localRestartFrontendService" />
                <span>同时重启前端服务</span>
              </label>
              <span class="form-help">前端服务重启时间较长，通常只需重启后端</span>
            </div>
            <div class="restart-service-row">
              <button class="ghost-btn" @click="confirmRestartGateway" :disabled="isRestartingGateway">
                {{ isRestartingGateway ? '请稍候...' : (localRestartNodeId ? `重启节点 ${localRestartNodeId} 服务` : '重启本节点服务') }}
              </button>
              <button class="ghost-btn" @click="confirmRestartAllNodes" :disabled="isRestartingGateway">
                一键重启所有节点
              </button>
            </div>
          </div>
        </div>
        <!-- 代码更新 -->
        <div class="form-group">
          <label>代码更新</label>
          <span class="form-help">将所有节点的 Jarvis 代码切换到 main 分支并拉取最新代码</span>
          <button class="ghost-btn" @click="updateCodeToMain" :disabled="isUpdatingCode">
            {{ isUpdatingCode ? '更新中...' : '更新代码到 main 分支' }}
          </button>
        </div>
        <!-- 节点连接私钥 -->
        <div class="form-group">
          <label>节点连接私钥</label>
          <div class="node-secret-section">
            <div class="secret-display">
              <code class="secret-code" v-if="nodeSecret" :title="nodeSecret">{{ maskedNodeSecret }}</code>
              <span class="secret-placeholder" v-else>点击"获取私钥"加载</span>
              <button class="copy-btn" @click="copyNodeSecret" :disabled="!nodeSecret" title="复制私钥">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
              </button>
            </div>
            <div class="secret-actions">
              <button class="ghost-btn" @click="fetchNodeSecret" :disabled="isLoadingSecret">
                {{ isLoadingSecret ? '加载中...' : '获取私钥' }}
              </button>
              <button class="ghost-btn" @click="toggleSecretMask" :disabled="!nodeSecret" title="显示/隐藏">
                {{ showSecret ? '隐藏' : '显示' }}
              </button>
            </div>
            <span class="form-help">此私钥用于子节点连接主网关时的身份认证，请妥善保管</span>
          </div>
        </div>
        <!-- 配置同步 -->
        <div class="form-group" v-if="availableNodeOptions.length > 0">
          <label>配置同步</label>
          <div class="config-sync-section">
            <div class="config-sync-row">
              <span class="config-sync-label">源节点:</span>
              <select v-model="localSyncConfigSourceNode" class="node-select">
                <option value="">本节点 (master)</option>
                <option v-for="node in availableNodeOptions" :key="node.node_id" :value="node.node_id">
                  {{ formatNodeOptionLabel(node) }}
                </option>
              </select>
            </div>
            <div class="config-sync-button">
              <button class="ghost-btn" @click="syncConfig" :disabled="isSyncingConfig">
                {{ isSyncingConfig ? '同步中...' : '同步配置到其他节点' }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-actions">
        <button class="ghost-btn" @click="close">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  auth: { type: Object, default: () => ({}) },
  fetchWithAuth: { type: Function, required: true },
  gatewayUrl: { type: String, default: '127.0.0.1:8000' },
  showToast: { type: Function, default: () => {} },
  getHttpProtocol: { type: Function, default: () => 'http' },
  availableNodeOptions: { type: Array, default: () => [] },
  isRestartingGateway: { type: Boolean, default: false },
  isSyncingConfig: { type: Boolean, default: false },
  isUpdatingCode: { type: Boolean, default: false },
  getToken: { type: Function, default: null },
})

const emit = defineEmits(['update:visible', 'confirmRestartGateway', 'confirmRestartAllNodes', 'syncConfig', 'updateCodeToMain', 'confirmUpdateCodeToMain'])

// 状态
const activeTab = ref('users')
const users = ref([])
const groups = ref([])
const loading = ref(false)
const loadingGroups = ref(false)
const showCreateUser = ref(false)
const showCreateGroup = ref(false)
const showResetPassword = ref(false)
const showEditGroup = ref(false)
const showGroupAssign = ref(false)
const selectedUser = ref(null)
const selectedGroup = ref(null)
const newUserForm = ref({ username: '', password: '', display_name: '', is_admin: false })
const newGroupForm = ref({ name: '', description: '' })
const resetPasswordForm = ref({ new_password: '' })
const showEditUser = ref(false)
const selectedEditUser = ref(null)
const editUserForm = ref({ display_name: '', is_admin: false, status: 'active' })
const editGroupForm = ref({ group_id: '', display_name: '', description: '' })
const userGroupIds = ref([])
const allGroups = ref([])
const editPermissions = ref({})
const editAccessibleNodes = ref([])
const loadingGroupPerms = ref(false)
const localRestartNodeId = ref('')
const localRestartFrontendService = ref(false)
const localSyncConfigSourceNode = ref('')
const nodeSecret = ref('')
const isLoadingSecret = ref(false)
const showSecret = ref(false)

// 权限Schema：资源→动作列表
const permissionSchema = {
  '*': ['*'],
  'agent': ['*', 'create', 'delete'],
  'terminal': ['*', 'read', 'execute'],
  'timer': ['*', 'read', 'create', 'delete'],
  'chat': ['*', 'read', 'send'],
  'admin': ['*', 'users', 'permissions', 'config'],
  'node': ['*', 'access'],
}
const resourceLabels = {
  '*': '全部',
  'agent': 'Agent',
  'terminal': '终端',
  'timer': '定时任务',
  'chat': '聊天',
  'admin': '管理',
  'node': '节点',
}

// 计算属性
const currentUserId = computed(() => props.auth?.userInfo?.user_id || '')
// 辅助函数
function getGatewayAddress() {
  const parts = (props.gatewayUrl || '127.0.0.1:8000').split(':')
  return { host: parts[0] || '127.0.0.1', port: parts[1] || '8000' }
}

function buildApiUrl(path) {
  const { host, port } = getGatewayAddress()
  const proto = props.getHttpProtocol ? props.getHttpProtocol() : 'http'
  return `${proto}://${host}:${port}${path}`
}

function close() {
  emit('update:visible', false)
}

function switchTab(tab) {
  activeTab.value = tab
  showCreateUser.value = false
  showCreateGroup.value = false
  showResetPassword.value = false
  showEditGroup.value = false
  showGroupAssign.value = false
}

// 打开时加载数据
watch(() => props.visible, (val) => {
  if (val) {
    loadUsers()
    loadGroups()
  } else {
    showCreateUser.value = false
    showCreateGroup.value = false
    showResetPassword.value = false
    showEditGroup.value = false
    showGroupAssign.value = false
  }
})

// ===== API 调用 =====
async function loadUsers() {
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl('/api/users'))
    const result = await resp.json()
    if (result.success) users.value = result.data.users || []
    else props.showToast(result.error?.message || '加载用户失败', 'error')
  } catch (e) { props.showToast('加载用户失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function loadGroups() {
  try {
    const resp = await props.fetchWithAuth(buildApiUrl('/api/permissions/groups'))
    const result = await resp.json()
    if (result.success) groups.value = result.data.groups || []
    else props.showToast(result.error?.message || '加载权限组失败', 'error')
  } catch (e) { props.showToast('加载权限组失败: ' + e.message, 'error') }
}

async function createUser() {
  if (!newUserForm.value.username || !newUserForm.value.password) {
    props.showToast('用户名和密码不能为空', 'error'); return
  }
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl('/api/users'), {
      method: 'POST', body: JSON.stringify(newUserForm.value)
    })
    const result = await resp.json()
    if (result.success) {
      props.showToast('用户创建成功', 'success')
      newUserForm.value = { username: '', password: '', display_name: '', is_admin: false }
      showCreateUser.value = false
      loadUsers()
    } else props.showToast(result.error?.message || '创建失败', 'error')
  } catch (e) { props.showToast('创建失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function deleteUser(user) {
  if (user.user_id === currentUserId.value) { props.showToast('不能删除自己', 'error'); return }
  if (!confirm(`确定删除用户 ${user.username}？`)) return
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/users/${user.user_id}`), { method: 'DELETE' })
    const result = await resp.json()
    if (result.success) { props.showToast('用户已删除', 'success'); loadUsers() }
    else props.showToast(result.error?.message || '删除失败', 'error')
  } catch (e) { props.showToast('删除失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

function openEditUser(user) {
  selectedEditUser.value = user
  editUserForm.value = { display_name: user.display_name || '', is_admin: !!user.is_admin, status: user.status || 'active' }
  showEditUser.value = true
  showResetPassword.value = false
  showGroupAssign.value = false
}

async function updateUser() {
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/users/${selectedEditUser.value.user_id}`), {
      method: 'PUT', body: JSON.stringify(editUserForm.value)
    })
    const result = await resp.json()
    if (result.success) { props.showToast('用户已更新', 'success'); showEditUser.value = false; await loadUsers() }
    else props.showToast(result.error?.message || '更新失败', 'error')
  } catch (e) { props.showToast('更新失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

function openResetPassword(user) {
  selectedUser.value = user
  resetPasswordForm.value = { new_password: '' }
  showResetPassword.value = true
  showGroupAssign.value = false
  showEditUser.value = false
}

async function resetPassword() {
  if (!resetPasswordForm.value.new_password) { props.showToast('新密码不能为空', 'error'); return }
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/users/${selectedUser.value.user_id}/reset-password`), {
      method: 'POST', body: JSON.stringify(resetPasswordForm.value)
    })
    const result = await resp.json()
    if (result.success) { props.showToast('密码已重置', 'success'); showResetPassword.value = false }
    else props.showToast(result.error?.message || '重置失败', 'error')
  } catch (e) { props.showToast('重置失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function openGroupAssign(user) {
  selectedUser.value = user
  showGroupAssign.value = true
  showResetPassword.value = false
  showEditUser.value = false
  loadingGroups.value = true
  try {
    const [groupsResp, userGroupsResp] = await Promise.all([
      props.fetchWithAuth(buildApiUrl('/api/permissions/groups')),
      props.fetchWithAuth(buildApiUrl(`/api/permissions/user/${user.user_id}/groups`))
    ])
    const groupsResult = await groupsResp.json()
    const userGroupsResult = await userGroupsResp.json()
    if (groupsResult.success) allGroups.value = groupsResult.data.groups || []
    if (userGroupsResult.success) userGroupIds.value = (userGroupsResult.data.groups || []).map(g => g.group_id)
  } catch (e) { props.showToast('加载组信息失败', 'error') }
  finally { loadingGroups.value = false }
}

async function saveUserGroups() {
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/user/${selectedUser.value.user_id}/groups`), {
      method: 'PUT', body: JSON.stringify({ group_ids: userGroupIds.value })
    })
    const result = await resp.json()
    if (result.success) { props.showToast('组分配已保存', 'success'); showGroupAssign.value = false }
    else props.showToast(result.error?.message || '保存失败', 'error')
  } catch (e) { props.showToast('保存失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function createGroup() {
  if (!newGroupForm.value.name) { props.showToast('组名不能为空', 'error'); return }
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl('/api/permissions/groups'), {
      method: 'POST', body: JSON.stringify(newGroupForm.value)
    })
    const result = await resp.json()
    if (result.success) {
      props.showToast('权限组创建成功', 'success')
      newGroupForm.value = { name: '', description: '' }
      showCreateGroup.value = false; loadGroups()
    } else props.showToast(result.error?.message || '创建失败', 'error')
  } catch (e) { props.showToast('创建失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function openEditGroup(group) {
  selectedGroup.value = group
  editGroupForm.value = { group_id: group.group_id, display_name: group.display_name || '', description: group.description || '' }
  showEditGroup.value = true
  // 加载组权限
  loadingGroupPerms.value = true
  editPermissions.value = {}
  editAccessibleNodes.value = []
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/groups/${group.group_id}/permissions`))
    const result = await resp.json()
    if (result.success) {
      // 将permissions对象转为扁平的key→value映射
      const perms = result.data.permissions || {}
      const accessibleNodes = perms.accessible_nodes || []
      const flat = {}
      for (const [key, val] of Object.entries(perms)) {
        if (key !== 'accessible_nodes') flat[key] = val
      }
      editPermissions.value = flat
      editAccessibleNodes.value = Array.isArray(accessibleNodes) ? [...accessibleNodes] : []
    }
  } catch (e) { props.showToast('加载权限失败', 'error') }
  finally { loadingGroupPerms.value = false }
}

async function updateGroup() {
  loading.value = true
  try {
    const { group_id, ...updateData } = editGroupForm.value
    // 更新组基本信息
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/groups/${group_id}`), {
      method: 'PUT', body: JSON.stringify(updateData)
    })
    const result = await resp.json()
    if (!result.success) { props.showToast(result.error?.message || '更新失败', 'error'); return }
    // 保存权限（过滤掉空值）
    const perms = {}
    for (const [key, val] of Object.entries(editPermissions.value)) {
      if (val) perms[key] = val
    }
    perms.accessible_nodes = editAccessibleNodes.value
    const permResp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/groups/${group_id}/permissions`), {
      method: 'PUT', body: JSON.stringify({ permissions: perms })
    })
    const permResult = await permResp.json()
    if (permResult.success) { props.showToast('权限组已更新', 'success'); showEditGroup.value = false; loadGroups() }
    else props.showToast(permResult.error?.message || '权限更新失败', 'error')
  } catch (e) { props.showToast('更新失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

async function deleteGroup(group) {
  if (!confirm(`确定删除权限组 ${group.name}？`)) return
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/groups/${group.group_id}`), { method: 'DELETE' })
    const result = await resp.json()
    if (result.success) { props.showToast('权限组已删除', 'success'); loadGroups() }
    else props.showToast(result.error?.message || '删除失败', 'error')
  } catch (e) { props.showToast('删除失败: ' + e.message, 'error') }
  finally { loading.value = false }
}

// ===== 系统配置功能 =====

function formatNodeOptionLabel(node) {
  const nodeId = String(node?.node_id || '').trim()
  const status = String(node?.status || node?.runtime_status || '').trim()
  const label = String(node?.label || node?.agent_label || '').trim()
  const isStopped = !status || status === 'stopped' || status === 'stop' || status === 'terminated'
  if (!isStopped && label) return `${nodeId} (${status}) - ${label}`
  return status ? `${nodeId} (${status})` : nodeId
}

function toggleAllNodesAccess() {
  if (editAccessibleNodes.value.includes('*')) {
    editAccessibleNodes.value = []
  } else {
    editAccessibleNodes.value = ['*']
  }
}

function toggleNodeAccess(nodeId) {
  const idx = editAccessibleNodes.value.indexOf(nodeId)
  if (idx >= 0) {
    editAccessibleNodes.value.splice(idx, 1)
  } else {
    editAccessibleNodes.value.push(nodeId)
  }
}

function confirmRestartGateway() {
  emit('confirmRestartGateway', { nodeId: localRestartNodeId.value, restartFrontend: localRestartFrontendService.value })
}

function confirmRestartAllNodes() {
  emit('confirmRestartAllNodes')
}

function syncConfig() {
  emit('syncConfig', { sourceNodeId: localSyncConfigSourceNode.value })
}

function updateCodeToMain() {
  emit('confirmUpdateCodeToMain')
}

async function fetchNodeSecret() {
  if (isLoadingSecret.value) return
  isLoadingSecret.value = true
  try {
    const token = props.getToken ? props.getToken() : null
    if (!token) { props.showToast('请先登录', 'error'); return }
    const apiProtocol = window.location.protocol === 'https:' ? 'https' : 'http'
    const apiUrl = `${apiProtocol}://${props.gatewayUrl}/api/node/secret`
    const response = await fetch(apiUrl, { headers: { 'Authorization': `Bearer ${token}` } })
    const result = await response.json()
    if (result.success && result.data?.node_secret) {
      nodeSecret.value = result.data.node_secret
    } else {
      props.showToast(result.error?.message || '获取私钥失败', 'error')
    }
  } catch (error) {
    props.showToast('获取私钥异常: ' + error.message, 'error')
  } finally {
    isLoadingSecret.value = false
  }
}

function toggleSecretMask() {
  showSecret.value = !showSecret.value
}

async function copyNodeSecret() {
  if (!nodeSecret.value) { props.showToast('私钥内容为空', 'error'); return }
  try {
    await navigator.clipboard.writeText(nodeSecret.value)
    props.showToast('已复制到剪贴板', 'success')
  } catch (error) {
    try {
      const textArea = document.createElement('textarea')
      textArea.value = nodeSecret.value
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
      props.showToast('已复制到剪贴板', 'success')
    } catch (fallbackErr) {
      props.showToast('复制失败，请手动复制', 'error')
    }
  }
}

const maskedNodeSecret = computed(() => {
  if (!nodeSecret.value) return ''
  if (showSecret.value) return nodeSecret.value
  const secret = nodeSecret.value
  if (secret.length <= 16) return '*'.repeat(secret.length)
  return `${secret.slice(0, 8)}${'*'.repeat(secret.length - 16)}${secret.slice(-8)}`
})
</script>

<style scoped>
/* 模态框 - 复用App.vue风格 */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.admin-modal {
  background: var(--bg-secondary, #1e1e2e); color: var(--text-primary, #cdd6f4);
  border-radius: 12px; width: 80%; max-width: 1200px; max-height: 90vh;
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; border-bottom: 1px solid var(--border-color, #45475a);
}
.modal-header h2 { margin: 0; font-size: 18px; }
.close-btn {
  background: none; border: none; color: var(--text-secondary, #a6adc8);
  font-size: 20px; cursor: pointer; padding: 4px 8px; border-radius: 4px;
  transition: all 0.2s;
}
.close-btn:hover { color: var(--text-primary, #cdd6f4); background: rgba(255,255,255,0.1); }

/* Tab导航 */
.admin-tabs {
  display: flex; border-bottom: 1px solid var(--border-color, #45475a);
  padding: 0 24px;
}
.admin-tab {
  padding: 10px 20px; cursor: pointer; border: none; background: none;
  color: var(--text-secondary, #a6adc8); font-size: 14px;
  border-bottom: 2px solid transparent; transition: all 0.2s;
}
.admin-tab:hover { color: var(--text-primary, #cdd6f4); }
.admin-tab.active { color: var(--accent, #89b4fa); border-bottom-color: var(--accent, #89b4fa); }

/* Tab内容区 */
.tab-content {
  flex: 1; overflow-y: auto; padding: 20px 24px;
}

/* 表单组 */
.form-group {
  margin-bottom: 16px;
}
.form-group > label:first-child {
  display: block; font-size: 13px; font-weight: 600;
  color: var(--text-secondary, #a6adc8); margin-bottom: 8px;
}
.form-row {
  display: flex; gap: 12px; margin-bottom: 10px; align-items: center;
}
.form-row > label {
  font-size: 13px; color: var(--text-secondary, #a6adc8); min-width: 60px; flex-shrink: 0;
}
.form-row input {
  flex: 1; padding: 6px 10px; border-radius: 6px;
  border: 1px solid var(--border-color, #45475a);
  background: var(--bg-primary, #11111b); color: var(--text-primary, #cdd6f4);
  font-size: 13px; outline: none; transition: border-color 0.2s;
}
.form-row input:focus { border-color: var(--accent, #89b4fa); }

/* 按钮组 */
.btn-group { display: flex; gap: 8px; margin-top: 8px; }
.ghost-btn {
  padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border-color, #45475a);
  background: none; color: var(--text-primary, #cdd6f4); font-size: 13px;
  cursor: pointer; transition: all 0.2s;
}
.ghost-btn:hover { background: rgba(137,180,250,0.1); border-color: var(--accent, #89b4fa); }
.ghost-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm {
  padding: 3px 10px; border-radius: 4px; border: 1px solid var(--border-color, #45475a);
  background: none; color: var(--text-primary, #cdd6f4); font-size: 12px;
  cursor: pointer; transition: all 0.2s;
}
.btn-sm:hover { background: rgba(137,180,250,0.1); }
.btn-sm.danger { color: #f38ba8; border-color: rgba(243,139,168,0.3); }
.btn-sm.danger:hover { background: rgba(243,139,168,0.1); }

/* 表格 */
.admin-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.admin-table th {
  text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border-color, #45475a);
  color: var(--text-secondary, #a6adc8); font-weight: 500;
}
.admin-table td {
  padding: 8px 12px; border-bottom: 1px solid rgba(69,71,90,0.3);
}
.admin-table tr:hover { background: rgba(137,180,250,0.05); }

/* 展开区域 */
.expand-section {
  background: var(--bg-primary, #11111b); border-radius: 8px; padding: 16px; margin-top: 16px;
  border: 1px solid var(--border-color, #45475a);
}

/* 组勾选 */
.group-checkbox {
  display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 13px;
}
.group-checkbox input[type="checkbox"] { width: 16px; height: 16px; cursor: pointer; }

/* 开关 */
.toggle-switch {
  position: relative; display: inline-block; width: 36px; height: 20px; cursor: pointer;
}
.toggle-input { opacity: 0; width: 0; height: 0; }
.toggle-slider {
  position: absolute; top: 0; left: 0; right: 0; bottom: 0;
  background: var(--border-color, #45475a); border-radius: 20px; transition: 0.3s;
}
.toggle-slider:before {
  content: ''; position: absolute; height: 14px; width: 14px;
  left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s;
}
.toggle-input:checked + .toggle-slider { background: var(--accent, #89b4fa); }
.toggle-input:checked + .toggle-slider:before { transform: translateX(16px); }

/* 权限矩阵 */
.permission-matrix {
  margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--border-color, #45475a);
}
.perm-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.perm-table th {
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border-color, #45475a);
  color: var(--text-secondary, #a6adc8); font-weight: 500; font-size: 12px;
}
.perm-table td {
  padding: 4px 10px; border-bottom: 1px solid rgba(69,71,90,0.2);
}
.perm-resource-cell {
  font-weight: 600; color: var(--accent, #89b4fa); vertical-align: middle;
  border-right: 1px solid var(--border-color, #45475a);
}
.perm-action-cell {
  color: var(--text-secondary, #a6adc8);
}
.perm-value-cell {
  text-align: center;
}
.perm-select {
  padding: 2px 6px; border-radius: 4px; font-size: 12px;
  border: 1px solid var(--border-color, #45475a);
  background: var(--bg-primary, #11111b); color: var(--text-primary, #cdd6f4);
  cursor: pointer; outline: none;
}
.perm-select:focus { border-color: var(--accent, #89b4fa); }
.perm-select option[value="allow"] { color: #a6e3a1; }
.perm-select option[value="deny"] { color: #f38ba8; }

/* 模态操作区 */
.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 24px;
}

/* 帮助文本 */
.form-help {
  display: block;
  margin: 0;
  padding: 0;
  font-size: 12px;
  color: var(--text-secondary, #a6adc8);
  line-height: 1.4;
}

/* 配置同步区域 */
.config-sync-section {
  margin-top: 16px;
  padding: 16px;
  background: transparent;
  border-radius: 6px;
  border: none;
}
.config-sync-row {
  margin-bottom: 16px;
}
.config-sync-row:last-child {
  margin-bottom: 0;
}
.config-sync-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #cdd6f4);
}
.config-sync-section .node-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary, #1e1e2e);
  border: none;
  border-radius: 6px;
  color: var(--text-primary, #cdd6f4);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.config-sync-section .node-select:hover {
  border-color: var(--border-color, #45475a);
}
.config-sync-section .node-select:focus {
  outline: none;
  border-color: var(--accent, #89b4fa);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.config-sync-button {
  margin-top: 16px;
}

/* 复选框标签 */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary, #1e1e2e);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  color: var(--text-primary, #cdd6f4);
}
.checkbox-label:hover {
  background: var(--bg-secondary, #1e1e2e);
}
.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent, #89b4fa);
}

/* 私钥显示区域 */
.node-secret-section {
  margin-top: 12px;
  padding: 16px;
  background: transparent;
  border-radius: 6px;
  border: none;
}
.secret-display {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  background: var(--bg-primary, #11111b);
  border-radius: 6px;
  border: none;
}
.secret-code {
  flex: 1;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
  font-size: 13px;
  color: var(--text-primary, #cdd6f4);
  word-break: break-all;
  min-width: 0;
}
.secret-placeholder {
  flex: 1;
  font-size: 13px;
  color: var(--text-secondary, #a6adc8);
  font-style: italic;
}
.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 6px;
  background: var(--bg-tertiary, #313244);
  border: 0.5px solid var(--border-color, #45475a);
  border-radius: 4px;
  color: var(--text-secondary, #a6adc8);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.copy-btn:hover:not(:disabled) {
  background: var(--bg-secondary, #1e1e2e);
  color: var(--accent, #89b4fa);
  border-color: var(--accent, #89b4fa);
}
.copy-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.secret-actions {
  display: flex;
  gap: 8px;
}
.secret-actions .ghost-btn {
  padding: 8px 16px;
  font-size: 13px;
}

/* 重启节点服务区域 */
.restart-service-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.restart-service-row {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 8px;
}

/* 节点选择器（重启区域） */
.restart-service-section .node-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary, #1e1e2e);
  border: none;
  border-radius: 6px;
  color: var(--text-primary, #cdd6f4);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.restart-service-section .node-select:hover {
  border-color: var(--border-color, #45475a);
}
.restart-service-section .node-select:focus {
  outline: none;
  border-color: var(--accent, #89b4fa);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
</style>