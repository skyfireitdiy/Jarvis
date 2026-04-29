<template>
  <aside
    v-show="visible"
    class="terminal-panel"
    :class="{ 'terminal-panel-dragging': interaction.active }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'terminal')"
  >
    <div class="terminal-panel-header" @mousedown="$emit('startMove', $event)" @dblclick.stop="$emit('toggleMaximize')">
      <div class="terminal-panel-title-group">
        <h3>终端</h3>
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
        <button class="icon-btn" @click="$emit('createTerminal')" :disabled="!socket" title="新建终端">➕</button>
        <button class="icon-btn maximize-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭面板">✕</button>
      </div>
    </div>

    <!-- 终端标签栏 -->
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
  interaction: Object,
  panelStyle: Object,
  nodeOptions: Array,
  selectedNodeId: String,
  socket: [Object, null],
  isMaximized: Boolean,
  sessions: Array,
  activeId: String,
  resizeDirections: Array,
  formatNodeLabel: Function
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'update:selectedNodeId',
  'createTerminal',
  'close',
  'switch',
  'closeTerminal',
  'setHostRef',
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

.terminal-panel {
  position: fixed;
  background: rgba(13, 17, 23, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.terminal-panel-dragging {
  user-select: none;
}

.terminal-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  background: rgba(22, 27, 34, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px 6px 0 0;
  cursor: move;
  min-height: 32px;
}

.terminal-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
}

.terminal-panel-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.terminal-node-select {
  height: 32px;
  min-width: 168px;
  max-width: 240px;
  padding: 0 32px 0 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: #e5e7eb;
  font-size: 13px;
  line-height: 32px;
  outline: none;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.terminal-node-select:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.2);
}

.terminal-node-select:focus {
  border-color: rgba(96, 165, 250, 0.9);
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

.terminal-node-select option {
  color: #111827;
}

.terminal-panel-actions {
  display: flex;
  gap: 8px;
}

.terminal-tabs {
  display: flex;
  gap: 2px;
  padding: 4px;
  background: rgba(0, 0, 0, 0.3);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.terminal-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(48, 54, 61, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
}

.terminal-tab:hover {
  background: rgba(56, 139, 253, 0.1);
  color: #58a6ff;
}

.terminal-tab.active {
  background: rgba(56, 139, 253, 0.2);
  color: #58a6ff;
  border-color: rgba(56, 139, 253, 0.3);
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
  background: rgba(248, 81, 73, 0.2);
  color: #f85149;
  border-radius: 3px;
  cursor: pointer;
}

.terminal-tab-close:hover {
  background: rgba(248, 81, 73, 0.4);
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
  color: #8b949e;
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