<template>
  <aside
    v-show="visible"
    class="terminal-panel"
    :class="{ 'terminal-panel-dragging': interaction.active, 'terminal-panel-active': active, 'terminal-panel-embedded': embedded }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'terminal')"
  >
    <div class="terminal-panel-header" @mousedown="!embedded && $emit('startMove', $event)">
      <!-- 终端标签栏与标题栏合一：标签在左，节点选择与新建恒靠右 -->
      <div class="terminal-tabs" v-if="sessions.length > 0">
        <div
          v-for="session in sessions"
          :key="session.terminal_id"
          class="terminal-tab"
          :class="{ active: activeId === session.terminal_id }"
          @click="$emit('switch', session.terminal_id)"
        >
          <span class="terminal-tab-title">{{ session.interpreter }}</span>
          <button class="terminal-tab-close" @click.stop="$emit('closeTerminal', session.terminal_id)">✕</button>
        </div>
      </div>
      <div class="terminal-panel-actions">
        <select
          v-if="nodeOptions.length > 0"
          :value="selectedNodeId"
          class="terminal-node-select"
          @mousedown.stop
          @click.stop
          @change="$emit('update:selectedNodeId', $event.target.value)"
        >
          <option v-for="node in nodeOptions" :key="node.node_id" :value="node.node_id">
            {{ formatNodeLabel(node) }}
          </option>
        </select>
        <button class="terminal-create-btn" @click="$emit('createTerminal')" :disabled="!socket" title="新建终端">➕</button>
        <button class="terminal-create-btn" @click="$emit('close')" title="关闭面板">✕</button>
      </div>
    </div>

    <!-- 终端内容区域 -->
    <div class="terminal-content">
      <div v-if="sessions.length === 0" class="terminal-empty">
        暂无终端，点击 + 创建
      </div>
      <div
        v-else
        v-for="session in sessions"
        :key="session.terminal_id"
        v-show="activeId === session.terminal_id"
        class="terminal-host-wrapper"
      >
        <div :ref="el => $emit('setHostRef', session.terminal_id, el)" class="terminal-host"></div>
      </div>
    </div>
    <div
      v-for="direction in resizeDirections"
      :key="direction"
      :class="['terminal-resize-handle', `terminal-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  visible: Boolean,
  active: Boolean,
  embedded: Boolean,
  interaction: Object,
  panelStyle: Object,
  nodeOptions: Array,
  selectedNodeId: String,
  socket: [Object, null],
  sessions: Array,
  activeId: String,
  resizeDirections: Array,
  formatNodeLabel: Function
})

const emit = defineEmits([
  'focus',
  'startMove',
  'update:selectedNodeId',
  'createTerminal',
  'close',
  'detach',
  'switch',
  'closeTerminal',
  'setHostRef',
  'startResize'
])
</script>

<style scoped>
.terminal-panel {
  position: fixed;
  background: rgba(9, 16, 28, 0.86);
  border: 1px solid var(--color-border-subtle);
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.terminal-panel-active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent), 0 0 12px rgba(32, 200, 255, 0.15);
}

.terminal-panel-dragging {
  user-select: none;
}

.terminal-panel-embedded {
  position: relative !important;
  width: 100% !important;
  height: 100% !important;
  top: auto !important;
  left: auto !important;
  border-radius: 4px;
}

.terminal-panel-header {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 6px;
  padding: 2px 6px;
  background:
    linear-gradient(160deg, rgba(32, 200, 255, 0.10) 0%, transparent 46%),
    var(--color-bg-tertiary);
  border-bottom: 1px solid var(--color-border-subtle);
  border-left: 2px solid var(--color-accent);
  border-radius: var(--tile-radius-xs) var(--tile-radius-xs) 0 0;
  cursor: move;
  min-height: 24px;
}

.terminal-node-select {
  height: 24px;
  min-width: 140px;
  max-width: 220px;
  padding: 0 24px 0 8px;
  border: none;
  border-radius: var(--tile-radius-xs);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: 12px;
  outline: none;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.terminal-node-select:hover {
  background: var(--color-bg-hover);
  border-color: var(--color-accent);
}

.terminal-node-select:focus {
  border-color: var(--color-accent);
  box-shadow: var(--tile-shadow);
  background: var(--color-bg-tertiary);
}

.terminal-node-select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.terminal-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  margin-left: auto;
}

/* 新建终端按钮：与紧凑标题栏同高、同配色 */
.terminal-create-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.terminal-create-btn:hover:not(:disabled) {
  background: var(--color-accent-subtle);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.terminal-create-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 标签栏与标题栏合一：不再单独占一行 */
.terminal-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  background: transparent;
  border-bottom: none;
}

.terminal-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  background: var(--color-bg-secondary);
  border: 1px solid transparent;
  border-radius: var(--tile-radius-xs);
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.terminal-tab:hover {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
}

.terminal-tab.active {
  background: var(--color-accent-subtle);
  color: var(--color-accent);
  border-color: var(--color-accent);
  box-shadow: 0 0 12px rgba(32, 200, 255, 0.15);
}

.terminal-tab-title {
  font-weight: 500;
}

.terminal-tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: var(--color-error-subtle);
  color: var(--color-error);
  border-radius: 3px;
  cursor: pointer;
}

.terminal-tab-close:hover {
  background: var(--color-error);
  color: var(--color-text-primary);
}

.terminal-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.terminal-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.terminal-host-wrapper {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.terminal-host {
  width: 100%;
  height: 100%;
}

/* 终端调整大小手柄 */
.terminal-resize-handle {
  position: absolute;
  z-index: 2;
}

.terminal-resize-n,
.terminal-resize-s {
  left: 8px;
  right: 8px;
  height: 8px;
}

.terminal-resize-n {
  top: -4px;
  cursor: ns-resize;
}

.terminal-resize-s {
  bottom: -4px;
  cursor: ns-resize;
}

.terminal-resize-e,
.terminal-resize-w {
  top: 8px;
  bottom: 8px;
  width: 8px;
}

.terminal-resize-e {
  right: -4px;
  cursor: ew-resize;
}

.terminal-resize-w {
  left: -4px;
  cursor: ew-resize;
}

.terminal-resize-ne,
.terminal-resize-nw,
.terminal-resize-se,
.terminal-resize-sw {
  width: 12px;
  height: 12px;
}

.terminal-resize-ne {
  top: -6px;
  right: -6px;
  cursor: nesw-resize;
}

.terminal-resize-nw {
  top: -6px;
  left: -6px;
  cursor: nwse-resize;
}

.terminal-resize-se {
  right: -6px;
  bottom: -6px;
  cursor: nwse-resize;
}

.terminal-resize-sw {
  left: -6px;
  bottom: -6px;
  cursor: nesw-resize;
}

/* 移动端隐藏调整大小手柄 */
@media (max-width: 768px) {
  .terminal-resize-handle {
    display: none;
  }
}
</style>