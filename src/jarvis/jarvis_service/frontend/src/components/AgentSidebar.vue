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
          <button class="agent-collapsed-toggle" @click="toggleGroupCollapse(agentGroup.key)">
            <span class="agent-collapsed-arrow">{{ isGroupCollapsed(agentGroup.key) ? '▶' : '▼' }}</span>
            <span class="agent-collapsed-title">{{ agentGroup.title }}</span>
            <span class="agent-collapsed-count">({{ agentGroup.agents.filter(a => getStatusClass(a) !== 'stopped').length }}/{{ agentGroup.agents.length }})</span>
          </button>
          <div v-if="!isGroupCollapsed(agentGroup.key)">
            <div
              v-for="agent in agentGroup.agents"
              :key="agent.agent_id"
              class="agent-item"
              :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id) }"
              @click="$emit('agentClick', agent, $event)"
            >
              <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
                <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
              </div>
              <div class="agent-info">
                <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'codeagent' ? '👨‍💻' : '🤖' }}</span>
                <span class="agent-name">{{ agent.name }}</span>
                <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
                <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
                <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
                <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
              </div>
              <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
              <div class="agent-actions">
                <button class="icon-btn-small" @click.stop="$emit('viewDiff', agent)" title="查看变更">🔀</button>
                <button class="icon-btn-small" @click.stop="$emit('createTerminal', agent)" :disabled="!socket" title="创建终端">💻</button>
                <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
                <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
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
            :class="{ active: currentAgentId === agent.agent_id, selected: isSelected(agent.agent_id) }"
            @click="$emit('agentClick', agent, $event)"
          >
            <div v-if="isBatchMode" class="agent-checkbox" @click.stop>
              <input type="checkbox" :checked="isSelected(agent.agent_id)" @change="$emit('toggleSelectAgent', agent.agent_id)">
            </div>
            <div class="agent-info">
              <span class="agent-type-icon" :title="agent.agent_type">{{ agent.agent_type === 'codeagent' ? '👨‍💻' : '🤖' }}</span>
              <span class="agent-name">{{ agent.name }}</span>
              <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
              <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
              <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
              <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
            </div>
            <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
            <div class="agent-actions">
              <button class="icon-btn-small" @click.stop="$emit('viewDiff', agent)" title="查看变更">🔀</button>
              <button class="icon-btn-small" @click.stop="$emit('createTerminal', agent)" :disabled="!socket" title="创建终端">💻</button>
              <button class="icon-btn-small" @click.stop="$emit('renameAgent', agent)" title="重命名">✏</button>
              <button class="icon-btn-small" @click.stop="$emit('copyAgent', agent)" title="复制 Agent">📋</button>
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
</template>

<script setup>
import { ref, watch, defineProps, defineEmits, onMounted } from 'vue'

// 分组折叠状态管理 - 使用对象存储，避免 Set 响应式问题
const collapsedGroupsMap = ref({})
const collapsedGroupsVersion = ref(0)

// 初始化时折叠所有分组
onMounted(() => {
  // 等待 displayGroups 加载后初始化折叠状态
  if (props.displayGroups) {
    props.displayGroups.forEach(group => {
      if (group.isCollapsible) {
        collapsedGroupsMap.value[group.key] = true
      }
    })
    collapsedGroupsVersion.value++
  }
})

function isGroupCollapsed(groupKey) {
  return !!collapsedGroupsMap.value[groupKey]
}

function toggleGroupCollapse(groupKey) {
  if (collapsedGroupsMap.value[groupKey]) {
    delete collapsedGroupsMap.value[groupKey]
  } else {
    collapsedGroupsMap.value[groupKey] = true
  }
  // 触发响应式更新
  collapsedGroupsVersion.value++
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
  getStatusClass: Function,
  getStatusText: Function,
  getNodeLabel: Function,
  isSelected: Function
})

// 监听 displayGroups 变化，只添加新分组，不覆盖已有折叠状态
watch(() => props.displayGroups, (newGroups) => {
  if (!newGroups) return

  // 只添加新分组到折叠状态，保留用户已设置的折叠/展开状态
  let hasNewGroup = false
  newGroups.forEach(group => {
    if (group.isCollapsible && !collapsedGroupsMap.value[group.key]) {
      collapsedGroupsMap.value[group.key] = true
      hasNewGroup = true
    }
  })
  if (hasNewGroup) {
    collapsedGroupsVersion.value++
  }
}, { immediate: false })

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
  'startResize',
  'viewDiff'
])

// 监听currentAgentId变化，自动展开对应节点分组
watch(() => props.currentAgentId, (newAgentId) => {
  if (!newAgentId || !props.agentList) return

  const agent = props.agentList.find(a => a.agent_id === newAgentId)
  if (!agent) return

  // 获取节点标签
  const nodeLabel = props.getNodeLabel(agent)
  const groupKey = `node-${nodeLabel}`

  // 如果该分组是折叠的，则展开它
  if (collapsedGroups.value.has(groupKey)) {
    collapsedGroups.value.delete(groupKey)
    collapsedGroups.value = new Set(collapsedGroups.value)
  }
})
</script>

<style scoped>
.icon-btn {
  background: var(--color-bg-tertiary);
  border: 0.5px solid var(--color-border);
  border-radius: 8px;
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
  border-right: 0.5px solid var(--color-border);
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
  border-bottom: 0.5px solid var(--color-border);
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
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  color: var(--color-text-secondary);
  cursor: pointer;
  text-align: left;
}

.agent-collapsed-toggle:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
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
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  cursor: pointer;
  position: relative;
}

.agent-item:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-border-active);
}

.agent-item.active {
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.agent-item.selected {
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
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
  border-top: 1px solid var(--color-border);
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
  box-shadow: 0 0 0 2px rgba(63, 185, 80, 0.2);
}

.agent-status-dot.stopped {
  background: #f85149;
  box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.2);
}

.agent-status-dot.waiting_multi {
  background: #d29922;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-status-dot.waiting_single {
  background: #d29922;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
}

.agent-status-dot.waiting_confirm {
  background: #d29922;
  box-shadow: 0 0 0 2px rgba(210, 153, 34, 0.2);
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
  border: 0.5px solid var(--color-border);
  border-radius: 4px;
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
</style>
