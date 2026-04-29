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
