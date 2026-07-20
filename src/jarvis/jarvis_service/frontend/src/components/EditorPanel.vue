<template>
  <aside
    v-show="visible"
    class="editor-panel"
    :class="{ 'editor-panel-dragging': interaction.active }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'editor')"
  >
    <div
      class="editor-panel-header"
      @mousedown="$emit('startMove', $event)"
      @dblclick.stop="$emit('toggleMaximize')"
    >
      <div class="editor-panel-title-group">
        <h3>编辑器 - {{ agentName || '未选择 Agent' }}</h3>
        <span v-if="activeTab" class="editor-panel-subtitle">{{ activeTab.path }}</span>
      </div>
      <div class="editor-panel-actions">
        <button class="icon-btn" @click.stop="$emit('save')" :disabled="!activeTab || activeTab.loading" title="保存文件">💾</button>
        <button class="icon-btn maximize-btn" @click="$emit('toggleMaximize')" :title="isMaximized ? '还原' : '最大化'">
          {{ isMaximized ? '🗗' : '🗖' }}
        </button>
        <button class="icon-btn" @click="$emit('close')" title="关闭编辑器">✕</button>
      </div>
    </div>
    <div class="editor-tabs" v-if="tabs.length > 0">
      <div
        v-for="tab in tabs"
        :key="tab.path"
        class="editor-tab"
        :class="{ active: activeTabPath === tab.path }"
        @click="$emit('activateTab', tab.path)"
      >
        <span class="editor-tab-name">{{ tab.name }}</span>
        <span v-if="tab.isDirty" class="editor-tab-dirty">●</span>
        <button class="editor-tab-close" @click.stop="$emit('closeTab', tab.path)">✕</button>
      </div>
    </div>
    <div class="editor-panel-toolbar">
      <span class="editor-toolbar-status" v-if="activeTab?.loading">加载中...</span>
      <span class="editor-toolbar-status error" v-else-if="activeTab?.error">{{ activeTab.error }}</span>
      <span class="editor-toolbar-status" v-else-if="activeTab">{{ activeTab.isDirty ? '未保存修改' : '已保存' }}</span>
      <span class="editor-toolbar-status" v-else>点击文件树中的文件打开编辑器</span>
      <div class="editor-toolbar-spacer"></div>
      <button
        v-if="tabs.length > 0"
        class="editor-edit-toggle"
        :class="{ 'editable': isEditable }"
        @click="$emit('toggleEditable')"
        :title="isEditable ? '切换到只读模式' : '切换到编辑模式'"
      >
        <span class="editor-edit-toggle-icon">{{ isEditable ? '🔓' : '🔒' }}</span>
        <span class="editor-edit-toggle-text">{{ isEditable ? '可编辑' : '只读' }}</span>
      </button>
    </div>
    <div class="editor-workspace">
      <div class="editor-activity-bar">
        <button
          class="editor-activity-button"
          :class="{ active: showSidebar && sidebarView === 'files' }"
          @click="$emit('setSidebarView', 'files')"
          title="目录树"
        >📁</button>
        <button
          class="editor-activity-button"
          :class="{ active: showSidebar && sidebarView === 'search' }"
          @click="$emit('setSidebarView', 'search')"
          title="全局搜索"
        >🔎</button>
      </div>
      <slot name="sidebar"></slot>
      <div class="editor-panel-content editor-panel-content-main">
        <div v-if="tabs.length === 0" class="editor-placeholder">
          <div class="editor-placeholder-icon">📝</div>
          <div class="editor-placeholder-title">点击文件树中的文件打开代码编辑器</div>
          <div class="editor-placeholder-text">支持 CodeMirror 6 语法高亮、代码折叠、多标签切换与保存。</div>
        </div>
        <div v-else ref="editorContainerRef" class="editor-codemirror-container"></div>
      </div>
    </div>
    <div
      v-for="direction in resizeDirections"
      :key="direction"
      :class="['editor-resize-handle', `editor-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { ref, defineProps, defineEmits } from 'vue'

const props = defineProps({
  visible: Boolean,
  interaction: Object,
  panelStyle: Object,
  agentName: String,
  activeTab: Object,
  activeTabPath: String,
  tabs: Array,
  isMaximized: Boolean,
  isEditable: Boolean,
  showSidebar: Boolean,
  sidebarView: String,
  resizeDirections: Array
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'save',
  'close',
  'activateTab',
  'closeTab',
  'toggleEditable',
  'setSidebarView',
  'startResize'
])

const editorContainerRef = ref(null)

defineExpose({
  editorContainerRef
})
</script>

<style scoped>
.editor-panel {
  position: fixed;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
}

.editor-panel-dragging {
  transition: none;
}

.editor-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  cursor: move;
  gap: 8px;
  min-height: 32px;
}

.editor-panel-title-group {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.editor-panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.editor-panel-subtitle {
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

.editor-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-tabs {
  display: flex;
  align-items: stretch;
  gap: 2px;
  padding: 4px 4px 0;
  background: var(--color-bg-primary);
  overflow-x: auto;
}

.editor-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 220px;
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
}

.editor-tab.active {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.editor-tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.editor-tab-dirty {
  color: #f2cc60;
  font-size: 10px;
}

.editor-tab-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 0;
}

.editor-panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.editor-toolbar-status {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.editor-toolbar-status.error {
  color: var(--color-error);
}

.editor-toolbar-spacer {
  flex: 1;
}

.editor-edit-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: none;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease-out;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  backdrop-filter: blur(20px);
}

.editor-edit-toggle:hover {
  background: var(--color-bg-hover);
}

.editor-edit-toggle:active {
  transform: scale(0.96);
}

.editor-edit-toggle.editable {
  background: rgba(0, 255, 136, 0.15);
  color: var(--color-success);
}

.editor-edit-toggle.editable:hover {
  background: rgba(0, 255, 136, 0.25);
}

.editor-edit-toggle-icon {
  font-size: 12px;
}

.editor-edit-toggle-text {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.editor-workspace {
  flex: 1;
  min-height: 0;
  display: flex;
  background: var(--color-bg-primary);
}

.editor-activity-bar {
  width: 44px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-right: 1px solid var(--color-border);
  background: var(--color-bg-primary);
}

.editor-activity-button {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.editor-activity-button:hover,
.editor-activity-button.active {
  color: var(--color-text-primary);
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.editor-panel-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.editor-panel-content-main {
  overflow: auto;
}

.editor-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  color: var(--color-text-secondary);
  text-align: center;
}

.editor-placeholder-icon {
  font-size: 48px;
  opacity: 0.6;
}

.editor-placeholder-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.editor-placeholder-text {
  font-size: 13px;
  line-height: 1.6;
  max-width: 320px;
}

.editor-codemirror-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.editor-resize-handle {
  position: absolute;
  background: transparent;
  z-index: 10;
}

.editor-resize-n,
.editor-resize-s {
  left: 10px;
  right: 10px;
  height: 6px;
  cursor: ns-resize;
}

.editor-resize-n {
  top: 0;
}

.editor-resize-s {
  bottom: 0;
}

.editor-resize-e,
.editor-resize-w {
  top: 10px;
  bottom: 10px;
  width: 6px;
  cursor: ew-resize;
}

.editor-resize-e {
  right: 0;
}

.editor-resize-w {
  left: 0;
}

.editor-resize-ne,
.editor-resize-nw,
.editor-resize-se,
.editor-resize-sw {
  width: 14px;
  height: 14px;
}

.editor-resize-ne {
  top: 0;
  right: 0;
  cursor: nesw-resize;
}

.editor-resize-nw {
  top: 0;
  left: 0;
  cursor: nwse-resize;
}

.editor-resize-se {
  bottom: 0;
  right: 0;
  cursor: nwse-resize;
}

.editor-resize-sw {
  bottom: 0;
  left: 0;
  cursor: nesw-resize;
}
</style>