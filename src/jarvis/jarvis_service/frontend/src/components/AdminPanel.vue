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
        <button class="admin-tab" :class="{ active: activeTab === 'account' }" @click="switchTab('account')">我的账户</button>
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
                <td><div class="btn-group"><button class="btn-sm" @click="openGroupAssign(user)">分配组</button><button class="btn-sm" @click="openResetPassword(user)">重置密码</button><button class="btn-sm danger" @click="deleteUser(user)" :disabled="user.user_id === currentUserId">删除</button></div></td>
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
            <div v-else>
              <div class="perm-resource" v-for="(actions, resource) in permissionSchema" :key="resource">
                <div class="perm-resource-header">{{ resourceLabels[resource] || resource }}</div>
                <div class="perm-actions">
                  <div class="perm-action" v-for="action in actions" :key="action">
                    <span class="perm-action-name">{{ action }}</span>
                    <select class="perm-select" v-model="editPermissions[resource + ':' + action]">
                      <option value="">未设置</option>
                      <option value="allow">允许</option>
                      <option value="deny">拒绝</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="btn-group"><button class="ghost-btn" @click="updateGroup" :disabled="loading">保存</button><button class="ghost-btn" @click="showEditGroup = false">取消</button></div>
        </div>
      </div>
      <!-- 我的账户 -->
      <div v-if="activeTab === 'account'" class="tab-content">
        <div class="form-group">
          <label>当前用户</label>
          <div style="font-size:14px">{{ currentUserInfo?.username || '-' }}<span v-if="currentUserInfo?.display_name" style="color:var(--text-secondary,#888);margin-left:8px">({{ currentUserInfo.display_name }})</span></div>
        </div>
        <div class="form-group">
          <label>修改密码</label>
          <div class="form-row"><label>旧密码</label><input v-model="changePasswordForm.old_password" type="password" placeholder="输入旧密码" /></div>
          <div class="form-row"><label>新密码</label><input v-model="changePasswordForm.new_password" type="password" placeholder="输入新密码" /></div>
          <div class="form-row"><label>确认密码</label><input v-model="changePasswordForm.confirm_password" type="password" placeholder="再次输入新密码" /></div>
          <button class="ghost-btn" @click="changePassword" :disabled="loading">修改密码</button>
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
  getHttpProtocol: { type: Function, default: () => 'http' }
})

const emit = defineEmits(['update:visible'])

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
const editGroupForm = ref({ group_id: '', display_name: '', description: '' })
const userGroupIds = ref([])
const allGroups = ref([])
const changePasswordForm = ref({ old_password: '', new_password: '', confirm_password: '' })
const editPermissions = ref({})
const loadingGroupPerms = ref(false)

// 权限Schema：资源→动作列表
const permissionSchema = {
  '*': ['*'],
  'agent': ['*', 'create', 'read', 'execute', 'delete'],
  'terminal': ['*', 'read', 'execute'],
  'timer': ['*', 'read', 'create', 'delete'],
  'chat': ['*', 'read', 'send'],
  'admin': ['*', 'users', 'permissions'],
}
const resourceLabels = {
  '*': '全部',
  'agent': 'Agent',
  'terminal': '终端',
  'timer': '定时任务',
  'chat': '聊天',
  'admin': '管理',
}

// 计算属性
const currentUserId = computed(() => props.auth?.userInfo?.user_id || '')
const currentUserInfo = computed(() => props.auth?.userInfo || null)

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

function openResetPassword(user) {
  selectedUser.value = user
  resetPasswordForm.value = { new_password: '' }
  showResetPassword.value = true
  showGroupAssign.value = false
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
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/permissions/groups/${group.group_id}/permissions`))
    const result = await resp.json()
    if (result.success) {
      // 将permissions对象转为扁平的key→value映射
      const perms = result.data.permissions || {}
      const flat = {}
      for (const [key, val] of Object.entries(perms)) {
        flat[key] = val
      }
      editPermissions.value = flat
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

async function changePassword() {
  const form = changePasswordForm.value
  if (!form.old_password || !form.new_password) { props.showToast('旧密码和新密码不能为空', 'error'); return }
  if (form.new_password !== form.confirm_password) { props.showToast('两次输入的新密码不一致', 'error'); return }
  loading.value = true
  try {
    const resp = await props.fetchWithAuth(buildApiUrl(`/api/users/${currentUserId.value}/change-password`), {
      method: 'POST', body: JSON.stringify({ old_password: form.old_password, new_password: form.new_password })
    })
    const result = await resp.json()
    if (result.success) { props.showToast('密码修改成功', 'success'); changePasswordForm.value = { old_password: '', new_password: '', confirm_password: '' } }
    else props.showToast(result.error?.message || '修改失败', 'error')
  } catch (e) { props.showToast('修改失败: ' + e.message, 'error') }
  finally { loading.value = false }
}
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
.perm-resource {
  margin-bottom: 12px;
}
.perm-resource-header {
  font-size: 13px; font-weight: 600; color: var(--accent, #89b4fa);
  margin-bottom: 6px; padding: 4px 0;
}
.perm-actions {
  display: flex; flex-wrap: wrap; gap: 8px 16px;
  padding-left: 12px;
}
.perm-action {
  display: flex; align-items: center; gap: 6px; font-size: 12px;
}
.perm-action-name {
  color: var(--text-secondary, #a6adc8); min-width: 70px;
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
</style>