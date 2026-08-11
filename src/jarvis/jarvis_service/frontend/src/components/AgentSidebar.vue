<template>
  <aside
    class="agent-sidebar"
    :class="{ collapsed: !visible, 'agent-sidebar-resizing': resizeState.active }"
    :style="sidebarStyle"
  >
    <div class="agent-sidebar-header">
      <h3>Agent 列表</h3>
      <div class="sidebar-header-actions">
        <button class="icon-btn" :class="{ active: isBatchMode }" @click="$emit('toggleBatchMode')" title="批量选择模式">☑</button>
        <button class="icon-btn" @click="$emit('createAgent')" title="创建新 Agent">➕</button>
        <button class="icon-btn" @click="$emit('close')" title="关闭侧边栏">✕</button>
      </div>
    </div>
    <div class="agent-list">
      <template v-for="agentGroup in displayGroups" :key="agentGroup.key">
        <div v-if="agentGroup.isCollapsible && agentGroup.agents.length > 0" class="agent-collapsed-section">
          <button
            class="agent-collapsed-toggle"
            :class="{
              'group-waiting-unread': hasUnreadWaitingAgent(agentGroup.agents),
              'group-waiting-clicked': hasClickedWaitingAgent(agentGroup.agents)
            }"
            @click="toggleGroupCollapse(agentGroup.key)"
          >
            <span class="agent-collapsed-arrow">{{ isGroupCollapsed(agentGroup.key) ? '▶' : '▼' }}</span>
            <span class="agent-collapsed-title">{{ agentGroup.title }}</span>
            <span class="agent-collapsed-count">({{ agentGroup.agents.filter(a => getStatusClass(a) !== 'stopped').length }}/{{ agentGroup.agents.length }})</span>
          </button>
          <div v-if="!isGroupCollapsed(agentGroup.key)">
            <div
              v-for="agent in agentGroup.agents"
              :key="agent.agent_id"
              class="agent-item"
              :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id), 'waiting-input': isWaitingInput(agent), 'waiting-input-unread': isWaitingInput(agent) && !clickedWaitingAgents.has(agent.agent_id) }"
              @click="handleAgentClick(agent, $event)"
            >
              <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
                <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
              </div>
              <div class="agent-info">
                <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'code_agent' ? '👨‍💻' : '🤖' }}</span>
                <span class="agent-name">{{ agent.name }}</span>
                <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
                <span class="agent-node-label" :title="agent.node_id || 'master'">{{ getNodeLabel(agent) }}</span>
                <span class="agent-proxy-node-label" v-if="agent.proxy_node" :title="'代理: ' + agent.proxy_node">{{ getProxyNodeLabel(agent) }}</span>
                <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
                <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
                <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
              </div>
              <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
              <div class="agent-actions">
                <button v-if="getStatusClass(agent) !== 'stopped'" class="icon-btn-small" @click.stop="$emit('viewDiff', agent)" title="查看变更">🔀</button>
                <button v-if="getStatusClass(agent) !== 'stopped'" class="icon-btn-small" @click.stop="$emit('viewRules', agent)" title="查看规则">📜</button>
                <button class="icon-btn-small" @click.stop="$emit('createTerminal', agent)" :disabled="!socket" title="创建终端">💻</button>
                <button class="icon-btn-small" @click.stop="$emit('openEditor', agent)" :disabled="!socket" title="打开编辑器">📝</button>
                <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
                <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
                <button v-if="agent.owner === currentUserId" class="icon-btn-small" @click.stop="$emit('editAccess', agent)" title="权限管理">🔒</button>
                <button class="icon-btn-small stop-btn" @click.stop="$emit('deleteAgent', agent.agent_id)" title="删除 Agent">🗑</button>
              </div>
            </div>
          </div>
        </div>
        <template v-else>
          <div
            v-for="agent in agentGroup.agents"
            :key="agent.agent_id"
            class="agent-item"
            :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id), 'waiting-input': isWaitingInput(agent), 'waiting-input-unread': isWaitingInput(agent) && !clickedWaitingAgents.has(agent.agent_id) }"
            @click="handleAgentClick(agent, $event)"
          >
            <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
              <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
            </div>
            <div class="agent-info">
              <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'code_agent' ? '👨‍💻' : '🤖' }}</span>
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
              <span class="agent-node-label" :title="agent.node_id || 'master'">{{ getNodeLabel(agent) }}</span>
              <span class="agent-proxy-node-label" v-if="agent.proxy_node" :title="'代理: ' + agent.proxy_node">{{ getProxyNodeLabel(agent) }}</span>
              <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
              <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
              <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
            </div>
            <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
            <div class="agent-actions">
              <button v-if="getStatusClass(agent) !== 'stopped'" class="icon-btn-small" @click.stop="$emit('viewDiff', agent)" title="查看变更">🔀</button>
              <button v-if="getStatusClass(agent) !== 'stopped'" class="icon-btn-small" @click.stop="$emit('viewRules', agent)" title="查看规则">📜</button>
              <button v-if="getStatusClass(agent) !== 'stopped'" class="icon-btn-small" @click.stop="$emit('viewTools', agent)" title="查看工具">🔧</button>
              <button class="icon-btn-small" @click.stop="$emit('createTerminal', agent)" :disabled="!socket" title="创建终端">💻</button>
              <button class="icon-btn-small" @click.stop="$emit('openEditor', agent)" :disabled="!socket" title="打开编辑器">📝</button>
              <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
              <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
              <button v-if="agent.owner === currentUserId" class="icon-btn-small" @click.stop="$emit('editAccess', agent)" title="权限管理">🔒</button>
              <button class="icon-btn-small stop-btn" @click.stop="$emit('deleteAgent', agent.agent_id)" title="删除 Agent">🗑</button>
            </div>
          </div>
        </template>
      </template>
      <!-- 批量操作按钮栏 -->
      <div v-if="isBatchMode && agentList.length > 0" class="batch-actions-bar">
        <div class="batch-actions-info">
          已选 {{ selectedCount }} 个
        </div>
        <div class="batch-actions-buttons">
          <button class="icon-btn-small" @click="$emit('toggleSelectAll')" :title="isAllSelected ? '取消全选' : '全选'">
            {{ isAllSelected ? '⬜' : '☑' }}
          </button>
          <button class="icon-btn-small" @click="$emit('batchCopy')" title="批量复制">
            📋
          </button>
          <button class="icon-btn-small" @click="openGroupModal" title="加入分组">
            📁
          </button>
          <button class="icon-btn-small stop-btn" @click="$emit('batchDelete')" title="批量删除">
            🗑
          </button>
          <button class="icon-btn-small" @click="$emit('toggleBatchMode')" title="退出批量模式">
            ✕
          </button>
        </div>
      </div>
      <div v-if="agentList.length === 0" class="agent-empty">
        暂无 Agent，点击 + 创建
      </div>
    </div>
    <div
      v-if="visible && windowWidth > 768"
      class="agent-sidebar-resize-handle"
      @mousedown="$emit('startResize', $event)"
    ></div>
  </aside>

  <!-- 加入分组弹窗 -->
  <Teleport to="body">
    <div v-if="showGroupModal" class="group-modal-overlay" @click.self="closeGroupModal">
      <div class="group-modal">
        <div class="group-modal-header">
          <span>加入分组</span>
          <button class="icon-btn-small" @click="closeGroupModal" title="关闭">✕</button>
        </div>
        <div v-if="agentGroups.length === 0" class="agent-group-empty">暂无分组，请先创建</div>
        <div
          v-for="group in agentGroups"
          :key="group.id"
          class="agent-group-item"
          @click="selectGroup(group.id)"
        >
          <span class="agent-group-item-name">📁 {{ group.name }}</span>
          <span class="agent-group-item-count">({{ group.agentIds?.length || 0 }})</span>
        </div>
        <div class="agent-group-create">
          <input
            v-model="newGroupName"
            class="agent-group-create-input"
            placeholder="新建分组名称"
            @keyup.enter="handleCreateGroup"
          />
          <button class="icon-btn-small" @click="handleCreateGroup" title="创建分组">➕</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, defineProps, defineEmits, onMounted } from 'vue'

// 分组折叠状态管理 - 使用对象存储，避免 Set 响应式问题
const collapsedGroupsMap = ref({})

// 追踪已点击过的等待输入Agent - 从localStorage恢复状态
const CLICKED_WAITING_STORAGE_KEY = 'jarvis_clicked_waiting_agents'

// 从localStorage加载已点击状态
function loadClickedWaitingAgents() {
  try {
    const stored = localStorage.getItem(CLICKED_WAITING_STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored)
      return new Set(Array.isArray(parsed) ? parsed : [])
    }
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to load clicked waiting agents:', e)
  }
  return new Set()
}

// 保存已点击状态到localStorage
function saveClickedWaitingAgents(set) {
  try {
    localStorage.setItem(CLICKED_WAITING_STORAGE_KEY, JSON.stringify([...set]))
  } catch (e) {
    console.warn('[AGENT_SIDEBAR] Failed to save clicked waiting agents:', e)
  }
}

const clickedWaitingAgents = ref(loadClickedWaitingAgents())

function isGroupCollapsed(groupKey) {
  return !!collapsedGroupsMap.value[groupKey]
}

function toggleGroupCollapse(groupKey) {
  if (collapsedGroupsMap.value[groupKey]) {
    collapsedGroupsMap.value[groupKey] = false
  } else {
    collapsedGroupsMap.value[groupKey] = true
  }
}

// 处理Agent点击事件，记录点击状态
function handleAgentClick(agent, event) {
  // 如果是等待输入状态，记录点击
  if (props.isWaitingInput(agent)) {
    clickedWaitingAgents.value.add(agent.agent_id)
    // 持久化到localStorage
    saveClickedWaitingAgents(clickedWaitingAgents.value)
    // 触发响应式更新
    clickedWaitingAgents.value = new Set(clickedWaitingAgents.value)
  }
  // 触发父组件的点击事件
  emit('agentClick', agent, event)
}

// 判断组内是否有未点击的等待输入Agent（闪烁）
function hasUnreadWaitingAgent(agents) {
  return agents.some(agent =>
    props.isWaitingInput(agent) && !clickedWaitingAgents.value.has(agent.agent_id)
  )
}

// 判断组内是否有已点击的等待输入Agent（背景色）
function hasClickedWaitingAgent(agents) {
  return agents.some(agent =>
    props.isWaitingInput(agent) && clickedWaitingAgents.value.has(agent.agent_id)
  )
}

const props = defineProps({
  visible: Boolean,
  resizeState: Object,
  sidebarStyle: Object,
  isBatchMode: Boolean,
  displayGroups: Array,
  currentAgentId: String,
  selectedCount: Number,
  agentList: Array,
  windowWidth: Number,
  isAllSelected: Boolean,
  socket: [Object, null],
  agentStatuses: Map,  // Agent状态映射 (agent_id -> {execution_status})
  getStatusClass: Function,
  getStatusText: Function,
  getNodeLabel: Function,
  getProxyNodeLabel: Function,
  isSelected: Function,
  isWaitingInput: Function,
  agentGroups: { type: Array, default: () => [] },
  currentUserId: { type: String, default: '' }
})

// 分组弹窗状态
const showGroupModal = ref(false)
const newGroupName = ref('')

function openGroupModal() {
  newGroupName.value = ''
  showGroupModal.value = true
}

function closeGroupModal() {
  showGroupModal.value = false
}

function selectGroup(groupId) {
  emit('addToGroup', groupId)
  closeGroupModal()
}

function handleCreateGroup() {
  const name = newGroupName.value.trim()
  if (!name) return
  emit('createGroupWithAgents', name)
  newGroupName.value = ''
  closeGroupModal()
}

// 初始化时折叠所有分组 - 只在首次初始化时设置，避免后续数据更新覆盖用户操作
watch(() => props.displayGroups, (newGroups) => {
  if (!newGroups || newGroups.length === 0) return
  // 只在 collapsedGroupsMap 为空时初始化折叠状态
  if (Object.keys(collapsedGroupsMap.value).length === 0) {
    newGroups.forEach(group => {
      if (group.isCollapsible) {
        collapsedGroupsMap.value[group.key] = true
      }
    })
  }
}, { immediate: true })

const emit = defineEmits([
  'close',
  'toggleBatchMode',
  'createAgent',
  'agentClick',
  'toggleSelectAgent',
  'createTerminal',
  'renameAgent',
  'copyAgent',
  'deleteAgent',
  'toggleSelectAll',
  'batchCopy',
  'batchDelete',
  'addToGroup',
  'createGroupWithAgents',
  'startResize',
  'viewDiff',
  'viewRules',
  'viewTools',
  'openEditor',
  'editAccess',
])

// 监听 agentStatuses 变化，当 agent 状态从等待输入变为非等待输入时清除点击标记
// 使用 ref 来跟踪上一次的状态
const previousStatusMap = ref(new Map())

watch(() => props.agentStatuses, (newStatuses) => {
  if (!newStatuses) return

  // 遍历所有 agent，检查状态变化
  props.agentList?.forEach(agent => {
    const agentId = agent.agent_id
    const currentStatus = newStatuses.get(agentId)
    const previousStatus = previousStatusMap.value.get(agentId)

    // 如果当前状态存在
    if (currentStatus) {
      const executionStatus = currentStatus.execution_status
      const isWaiting = executionStatus === 'waiting_multi' || executionStatus === 'waiting_single' || executionStatus === 'waiting_confirm'

      // 如果之前是等待输入状态，现在不是了，清除点击标记
      if (previousStatus) {
        const prevExecutionStatus = previousStatus.execution_status
        const wasWaiting = prevExecutionStatus === 'waiting_multi' || prevExecutionStatus === 'waiting_single' || prevExecutionStatus === 'waiting_confirm'

        if (wasWaiting && !isWaiting) {
          if (clickedWaitingAgents.value.has(agentId)) {
            clickedWaitingAgents.value.delete(agentId)
            // 持久化到localStorage
            saveClickedWaitingAgents(clickedWaitingAgents.value)
            // 触发响应式更新
            clickedWaitingAgents.value = new Set(clickedWaitingAgents.value)
            console.log(`[AGENT_SIDEBAR] Cleared clicked mark for agent ${agentId} (status changed from ${prevExecutionStatus} to ${executionStatus})`)
          }
        }
      }

      // 更新上一次的状态
      previousStatusMap.value.set(agentId, { ...currentStatus })
    }
  })
}, { deep: true })

// 监听currentAgentId变化，自动展开对应节点分组
watch(() => props.currentAgentId, (newAgentId) => {
  if (!newAgentId || !props.agentList) return

  const agent = props.agentList.find(a => a.agent_id === newAgentId)
  if (!agent) return

  // 获取节点标签
  const nodeLabel = props.getNodeLabel(agent)
  const groupKey = `node-${nodeLabel}`

  // 如果该分组是折叠的，则展开它
  if (collapsedGroupsMap.value[groupKey]) {
    collapsedGroupsMap.value[groupKey] = false
  }
})
</script>

<style scoped>
.icon-btn {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius);
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  color: var(--color-text-secondary);
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.icon-btn:active:not(:disabled) {
  transform: translateY(0);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn.active {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
  border-color: var(--color-border-active);
}

.agent-sidebar {
  position: relative;
  width: 320px;
  min-width: 0;
  background: var(--color-bg-secondary);
  border-right: 0.5px solid var(--color-border-subtle);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;
}

.agent-sidebar.collapsed {
  width: 0;
  border-right: none;
  overflow: hidden;
}

.agent-sidebar-resizing {
  user-select: none;
}

.agent-sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: -4px;
  width: 8px;
  height: 100%;
  cursor: ew-resize;
  z-index: 5;
}

.agent-sidebar-resize-handle::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: transparent;
  transition: background 0.15s ease;
}

.agent-sidebar-resize-handle:hover::after,
.agent-sidebar-resizing .agent-sidebar-resize-handle::after {
  background: var(--color-accent-glow);
}

.agent-sidebar-header {
  padding: 12px;
  border-bottom: 0.5px solid var(--color-border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--color-bg-tertiary);
}

.sidebar-header-actions {
  display: flex;
  gap: 8px;
}

.agent-sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-collapsed-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-collapsed-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  text-align: left;
}

.agent-collapsed-toggle:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* 组内有已点击的等待输入Agent - 背景色 */
.agent-collapsed-toggle.group-waiting-clicked {
  background: rgba(210, 153, 34, 0.35);
}

/* 组内有未点击的等待输入Agent - 呼吸灯闪烁 */
.agent-collapsed-toggle.group-waiting-unread {
  animation: group-breathing 2s ease-in-out infinite;
}

@keyframes group-breathing {
  0%, 100% {
    background: rgba(210, 153, 34, 0.35);
  }
  50% {
    background: rgba(210, 153, 34, 0.65);
  }
}

.agent-collapsed-arrow {
  width: 16px;
  color: var(--color-accent);
}

.agent-collapsed-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.agent-collapsed-count {
  font-size: 12px;
  color: var(--color-text-muted);
}

.agent-item {
  padding: 6px;
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  cursor: pointer;
  position: relative;
}

.agent-item:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-active);
}

.agent-item.active {
  background: #3b82f640;
  border-color: var(--color-border-active);
}

.agent-item.selected {
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.agent-item.waiting-input {
  background: rgba(210, 153, 34, 0.35);
}

/* 激活+等待输入组合状态 - 使用紫色背景 */
.agent-item.active.waiting-input {
  background: rgba(139, 92, 246, 0.35);
}

/* 未点击的等待输入状态 - 呼吸灯效果 */
.agent-item.waiting-input-unread {
  animation: breathing 2s ease-in-out infinite;
}

@keyframes breathing {
  0%, 100% {
    background: rgba(210, 153, 34, 0.35);
  }
  50% {
    background: rgba(210, 153, 34, 0.65);
  }
}

.agent-checkbox {
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}

.agent-checkbox input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: var(--color-accent);
}

.batch-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-subtle);
  gap: 12px;
}

.batch-actions-info {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
}

.group-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.group-modal {
  width: 320px;
  max-width: 90vw;
  max-height: 70vh;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.group-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.agent-group-empty {
  font-size: 12px;
  color: var(--color-text-muted);
  padding: 4px 0;
}

.agent-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  border-radius: var(--tile-radius-xs);
  cursor: pointer;
  transition: background 0.15s ease;
}

.agent-group-item:hover {
  background: var(--color-bg-hover);
}

.agent-group-item-name {
  font-size: 12px;
  color: var(--color-text-primary);
}

.agent-group-item-count {
  font-size: 11px;
  color: var(--color-text-muted);
}

.agent-group-create {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
}

.agent-group-create-input {
  flex: 1;
  font-size: 12px;
  padding: 4px 6px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs);
  color: var(--color-text-primary);
  outline: none;
}

.agent-group-create-input:focus {
  border-color: var(--color-border-active);
}

.agent-item .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--color-bg-hover);
  margin-left: 8px;
}

.agent-item .agent-status.running {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
}

.agent-item .agent-status.stopped {
  background: rgba(0, 255, 136, 0.15);
  color: var(--color-success);
}

.agent-item .agent-status.waiting_multi {
  background: rgba(255, 170, 0, 0.15);
  color: var(--color-warning);
}

.agent-item .agent-status.waiting_single {
  background: rgba(255, 71, 87, 0.15);
  color: var(--color-error);
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 2px;
}

.agent-type {
  font-size: 16px;
}

.agent-status {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.agent-status.running {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.agent-status.stopped {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.agent-status-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 4px;
  flex-shrink: 0;
}

.agent-status-dot.running {
  background: #3fb950;
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.stopped {
  background: #f85149;
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_multi {
  background: #d29922;
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_single {
  background: #d29922;
  box-shadow: var(--tile-shadow);
}

.agent-status-dot.waiting_confirm {
  background: #d29922;
  box-shadow: var(--tile-shadow);
}

.agent-llm-group {
  font-size: 10px;
  color: #666;
  background: rgba(108, 117, 125, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
}

.agent-port {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-left: auto;
}

.agent-type-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.agent-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.agent-dir {
  font-size: 10px;
  color: var(--color-text-secondary);
  word-break: break-all;
  line-height: 1.3;
}

.agent-actions {
  display: flex;
  gap: 3px;
  margin-top: 4px;
  justify-content: flex-end;
}

.icon-btn-small {
  background: var(--color-bg-tertiary);
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 12px;
  cursor: pointer;
  padding: 3px 6px;
  color: var(--color-text-secondary);
  transition: all 0.2s ease;
}

.icon-btn-small:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
  transform: translateY(-1px);
}

.icon-btn-small:active {
  transform: translateY(0);
}

.icon-btn-small:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.agent-actions .icon-btn-small.stop-btn:hover {
  background: rgba(255, 71, 87, 0.15);
  color: var(--color-error);
}

.agent-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 14px;
  padding: 20px;
}

.agent-node-label {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--tile-radius);
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  border: none;
  margin-left: 4px;
}

.agent-proxy-node-label {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: var(--tile-radius);
  background: rgba(56, 132, 255, 0.1); /* 浅蓝色背景 */
  color: #3884ff; /* 蓝色文字 */
  border: none;
  margin-left: 4px;
}
</style>
