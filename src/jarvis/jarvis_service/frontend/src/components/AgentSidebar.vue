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
          <button class="agent-collapsed-toggle" @click="$emit('toggleStoppedAgents')">
            <span class="agent-collapsed-arrow">{{ showStopped ? '▼' : '▶' }}</span>
            <span class="agent-collapsed-title">{{ agentGroup.title }}</span>
            <span class="agent-collapsed-count">{{ agentGroup.agents.length }}</span>
          </button>
          <div v-if="showStopped">
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
                <span class="agent-type">{{ agent.name || (agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'codeagent' ? '👨‍💻' : '❓') }}</span>
                <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
                <span class="agent-node" v-if="getNodeLabel(agent)" :title="`节点: ${getNodeLabel(agent)}`">🧭 {{ getNodeLabel(agent) }}</span>
                <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
                <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
                <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
              </div>
              <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
              <div class="agent-actions">
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
              <span class="agent-type">{{ agent.name || (agent.agent_type === 'agent' ? '🤖' : agent.agent_type === 'codeagent' ? '👨‍💻' : '❓') }}</span>
              <span class="agent-status-dot" :class="getStatusClass(agent)" :title="getStatusText(agent)"></span>
              <span class="agent-node" v-if="getNodeLabel(agent)" :title="`节点: ${getNodeLabel(agent)}`">🧭 {{ getNodeLabel(agent) }}</span>
              <span class="agent-llm-group" v-if="agent.llm_group">🔹 {{ agent.llm_group }}</span>
              <span class="agent-worktree" v-if="agent.worktree" title="已启用 worktree">🌿</span>
              <span class="agent-quick-mode" v-if="agent.quick_mode" title="极速模式">⚡</span>
            </div>
            <div class="agent-dir">{{ agent.working_dir || '未提供工作目录' }}</div>
            <div class="agent-actions">
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
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  visible: Boolean,
  resizeState: Object,
  sidebarStyle: Object,
  isBatchMode: Boolean,
  displayGroups: Array,
  showStopped: Boolean,
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

const emit = defineEmits([
  'close',
  'toggleBatchMode',
  'createAgent',
  'agentClick',
  'toggleStoppedAgents',
  'toggleSelectAgent',
  'createTerminal',
  'renameAgent',
  'copyAgent',
  'deleteAgent',
  'toggleSelectAll',
  'batchCopy',
  'batchDelete',
  'startResize'
])
</script>

<style scoped>
.icon-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
  padding: 0;
  color: #8b949e;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
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
  background: rgba(56, 139, 253, 0.3);
  color: #58a6ff;
  border-color: rgba(56, 139, 253, 0.5);
}

.agent-sidebar {
  position: relative;
  width: 320px;
  min-width: 0;
  background: rgba(22, 27, 34, 0.95);
  border-right: 0.5px solid rgba(255, 255, 255, 0.08);
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
  background: rgba(88, 166, 255, 0.6);
}

.agent-sidebar-header {
  padding: 12px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.02);
}

.sidebar-header-actions {
  display: flex;
  gap: 8px;
}

.agent-sidebar-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
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
  background: rgba(255, 255, 255, 0.02);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  color: #8b949e;
  cursor: pointer;
  text-align: left;
}

.agent-collapsed-toggle:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e6edf3;
}

.agent-collapsed-arrow {
  width: 16px;
  color: #58a6ff;
}

.agent-collapsed-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.agent-collapsed-count {
  font-size: 12px;
  color: #6e7681;
}

.agent-item {
  padding: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  cursor: pointer;
  position: relative;
}

.agent-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
}

.agent-item.active {
  background: rgba(56, 139, 253, 0.15);
  border-color: rgba(56, 139, 253, 0.4);
}

.agent-item.selected {
  background: rgba(139, 92, 246, 0.15);
  border-color: rgba(139, 92, 246, 0.4);
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
  accent-color: #58a6ff;
}

.batch-actions-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: rgba(22, 27, 34, 0.9);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  gap: 12px;
}

.batch-actions-info {
  font-size: 13px;
  color: #8b949e;
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
}

.agent-item .agent-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  margin-left: 8px;
}

.agent-item .agent-status.running {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
}

.agent-item .agent-status.stopped {
  background: rgba(63, 185, 80, 0.2);
  color: #3fb950;
}

.agent-item .agent-status.waiting_multi {
  background: rgba(210, 153, 34, 0.2);
  color: #d29922;
}

.agent-item .agent-status.waiting_single {
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
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
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-left: 8px;
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
  background: #f85149;
  box-shadow: 0 0 0 2px rgba(248, 81, 73, 0.2);
}

.agent-llm-group {
  font-size: 11px;
  color: #666;
  background: rgba(108, 117, 125, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.agent-port {
  font-size: 12px;
  color: #8b949e;
  margin-left: auto;
}

.agent-dir {
  font-size: 11px;
  color: #8b949e;
  word-break: break-all;
  line-height: 1.4;
}

.agent-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
  justify-content: flex-end;
}

.icon-btn-small {
  background: rgba(255, 255, 255, 0.05);
  border: 0.5px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
  color: #8b949e;
  transition: all 0.2s ease;
}

.icon-btn-small:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
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
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
}

.agent-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8b949e;
  font-size: 14px;
  padding: 20px;
}
</style>
