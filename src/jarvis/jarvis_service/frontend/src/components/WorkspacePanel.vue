<template>
  <aside
    v-show="visible"
    class="workspace-panel"
    :class="{ 'workspace-panel-dragging': interaction.active, 'workspace-panel-active': active, 'workspace-panel-embedded': embedded }"
    :style="panelStyle"
    @mousedown="$emit('focus', 'workspace')"
  >
    <div
      class="workspace-panel-header"
      @mousedown="!embedded && $emit('startMove', $event)"
    >
      <div class="workspace-panel-title-group">
        <h3>工作区</h3>
        <span v-if="agents && agents.length" class="workspace-agent-label">当前 Agent</span>
        <select
          v-if="agents && agents.length"
          class="workspace-agent-select"
          :value="activeAgentId || ''"
          title="选择 Agent"
          @mousedown.stop
          @change="$emit('selectAgent', $event.target.value)"
        >
          <option value="" disabled>选择 Agent</option>
          <option v-for="agent in agents" :key="agent.agent_id" :value="agent.agent_id">
            {{ agent.name || agent.agent_id }}
          </option>
        </select>
      </div>
      <div class="workspace-panel-actions">
        <button v-if="!$slots['pane-tree']" class="icon-btn" @click.stop="$emit('save')" :disabled="!activeTab || activeTab.loading" title="保存文件">💾</button>
        <button class="icon-btn close-btn" @click.stop="$emit('close')" title="关闭">✕</button>
      </div>
    </div>
    <div class="workspace-panel-toolbar">
      <span class="workspace-toolbar-status" v-if="activeTab?.loading">加载中...</span>
      <span class="workspace-toolbar-status error" v-else-if="activeTab?.error">{{ activeTab.error }}</span>
      <span class="workspace-toolbar-status" v-else-if="activeTab">{{ activeTab.isDirty ? '未保存修改' : '已保存' }}</span>
      <span class="workspace-toolbar-status" v-else>点击文件树中的文件打开编辑器</span>
      <div class="workspace-toolbar-spacer"></div>
      <button
        v-if="canSplit"
        class="workspace-edit-toggle"
        @click="$emit('splitPane', 'row')"
        title="左右分屏"
      >
        <span class="workspace-edit-toggle-icon">◫</span>
        <span class="workspace-edit-toggle-text">左右分</span>
      </button>
      <button
        v-if="canSplit"
        class="workspace-edit-toggle"
        @click="$emit('splitPane', 'column')"
        title="上下分屏"
      >
        <span class="workspace-edit-toggle-icon">⬓</span>
        <span class="workspace-edit-toggle-text">上下分</span>
      </button>
      <button
        v-if="tabs.length > 0 && !$slots['pane-tree']"
        class="workspace-edit-toggle"
        :class="{ 'editable': isEditable }"
        @click="$emit('toggleEditable')"
        :title="isEditable ? '切换到只读模式' : '切换到编辑模式'"
      >
        <span class="workspace-edit-toggle-icon">{{ isEditable ? '🔓' : '🔒' }}</span>
        <span class="workspace-edit-toggle-text">{{ isEditable ? '可编辑' : '只读' }}</span>
      </button>
    </div>
    <div class="workspace-main">
      <div class="workspace-activity-bar">
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'files' }"
          @click="$emit('setSidebarView', 'files')"
          title="目录树"
        >📁</button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'search' }"
          @click="$emit('setSidebarView', 'search')"
          title="全局搜索"
        >🔎</button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'git' }"
          @click="$emit('setSidebarView', 'git')"
          title="Git"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor" aria-hidden="true">
            <path d="M15.698 7.287 8.712.302a1.03 1.03 0 0 0-1.457 0l-1.45 1.45 1.84 1.84a1.223 1.223 0 0 1 1.55 1.56l1.773 1.774a1.224 1.224 0 0 1 1.267 2.025 1.226 1.226 0 0 1-2.002-1.334L8.58 5.963v4.353a1.228 1.228 0 1 1-1.008-.036V5.887a1.228 1.228 0 0 1-.666-1.608L5.093 2.466l-4.45 4.45a1.03 1.03 0 0 0 0 1.457l6.986 6.986a1.03 1.03 0 0 0 1.457 0l6.612-6.612a1.03 1.03 0 0 0 0-1.46z"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'agents' }"
          @click="$emit('setSidebarView', 'agents')"
          title="Agent 列表"
        >📋</button>
        <button
          class="workspace-activity-button"
          :class="{ active: mainView === 'chat' }"
          @click="$emit('setMainView', 'chat')"
          title="聊天室"
        >💬</button>
        <button
          class="workspace-activity-button"
          :class="{ active: mainView === 'terminal' }"
          @click="$emit('setMainView', 'terminal')"
          title="终端"
        >⌨️</button>
        <button
          class="workspace-activity-button"
          @click="$emit('openSettings')"
          title="设置 (Ctrl+Alt+,)"
        >⚙</button>
        <button
          class="workspace-activity-button"
          @click="$emit('openDocs')"
          title="使用文档 (Ctrl+Alt+Shift+H)"
        >❓</button>
        <button
          v-if="isAdmin"
          class="workspace-activity-button"
          @click="$emit('openAdmin')"
          title="管理 (Ctrl+Alt+Shift+A)"
        >🛡️</button>
      </div>
      <slot name="sidebar"></slot>
      <div class="workspace-panel-content workspace-panel-content-main">
        <!-- 文件标签：只属于「文件视图」，放在主区域顶部（不横跨活动栏/侧边栏）。
             自由分割模式下改由各 file pane 内部渲染（见 App.vue #pane-content），
             此处不再渲染，避免标签栏横跨整个工作区宽度。 -->
        <div class="workspace-tabs" v-if="!$slots['pane-tree'] && mainView === 'file' && tabs.length > 0">
          <div
            v-for="tab in tabs"
            :key="tab.path"
            class="workspace-tab"
            :class="{ active: activeTabPath === tab.path }"
            @click="$emit('activateTab', tab.path)"
          >
            <span class="workspace-tab-name">{{ tab.name }}</span>
            <span v-if="tab.isDirty" class="workspace-tab-dirty">●</span>
            <button class="workspace-tab-close" @click.stop="$emit('closeTab', tab.path)">✕</button>
          </div>
        </div>
        <!-- 自由分割模式：由 App.vue 提供整棵 pane 树（含每个 leaf 的内容），
             此时不再渲染原有的单视图内容，避免两套渲染路径并存。 -->
        <slot name="pane-tree"></slot>
        <template v-if="!$slots['pane-tree']">
        <slot name="main-view"></slot>
        <div v-show="mainView === 'file'" class="workspace-main-file-view">
          <div v-if="diff" class="workspace-diff-view">
            <div class="workspace-diff-header">
              <span class="workspace-diff-title" :title="diff.filePath">{{ diff.filePath }}</span>
              <span v-if="diff.commitHash" class="workspace-diff-hash">{{ diff.commitHash.slice(0, 7) }}</span>
              <span v-if="diff.truncated" class="workspace-diff-truncated">（已截断）</span>
              <button class="workspace-diff-nav" @click="$emit('diffNavPrev')" title="上一个差异">▲</button>
              <button class="workspace-diff-nav" @click="$emit('diffNavNext')" title="下一个差异">▼</button>
              <button class="workspace-diff-toggle" @click="$emit('toggleDiffShowFull')" :title="diff.showFull ? '只显示变更上下文区域' : '显示文件全文'">
                {{ diff.showFull ? '仅上下文' : '全文' }}
              </button>
              <button class="workspace-diff-toggle" @click="$emit('toggleDiffSideBySide')">
                {{ diff.sideBySide ? '内联' : '并排' }}
              </button>
              <button class="workspace-diff-close" @click="$emit('closeDiff')" title="关闭 diff">✕</button>
            </div>
            <div v-if="diff.loading" class="workspace-diff-status">加载 diff...</div>
            <div v-else-if="diff.error" class="workspace-diff-status error">{{ diff.error }}</div>
            <div v-else ref="diffContainerRef" class="workspace-diff-monaco"></div>
          </div>
          <div v-else-if="tabs.length === 0" class="workspace-placeholder">
            <div class="workspace-placeholder-icon">📝</div>
            <div class="workspace-placeholder-title">点击文件树中的文件打开代码编辑器</div>
            <div class="workspace-placeholder-text">支持 Monaco 语法高亮、智能提示、代码折叠、多标签切换与保存。</div>
          </div>
          <div v-else ref="editorContainerRef" class="workspace-monaco-container"></div>
        </div>
        </template>
      </div>
    </div>
    <div
      v-for="direction in resizeDirections"
      :key="direction"
      :class="['workspace-resize-handle', `workspace-resize-${direction}`]"
      @mousedown="$emit('startResize', $event, direction)"
    ></div>
  </aside>
</template>

<script setup>
import { ref, defineProps, defineEmits } from 'vue'

const props = defineProps({
  visible: Boolean,
  active: Boolean,
  embedded: Boolean,
  interaction: Object,
  panelStyle: Object,
  agentName: String,
  agents: Array,
  activeAgentId: String,
  activeTab: Object,
  activeTabPath: String,
  tabs: Array,
  isMaximized: Boolean,
  isEditable: Boolean,
  showSidebar: Boolean,
  sidebarView: String,
  mainView: { type: String, default: 'file' },
  resizeDirections: Array,
  diff: Object,
  canSplit: { type: Boolean, default: false },
  isAdmin: { type: Boolean, default: false }
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'detach',
  'save',
  'close',
  'activateTab',
  'closeTab',
  'toggleEditable',
  'setSidebarView',
  'setMainView',
  'startResize',
  'toggleDiffSideBySide',
  'closeDiff',
  'closeSidebar',
  'toggleDiffShowFull',
  'diffNavPrev',
  'diffNavNext',
  'selectAgent',
  'splitPane',
  'openSettings',
  'openDocs',
  'openAdmin'
])

const editorContainerRef = ref(null)
const diffContainerRef = ref(null)

defineExpose({
  editorContainerRef,
  diffContainerRef
})
</script>

<style scoped>
.workspace-panel {
  position: fixed;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  box-shadow: var(--tile-shadow);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  user-select: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.workspace-panel-active {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 1px var(--color-accent), 0 0 12px rgba(32, 200, 255, 0.15);
}

.workspace-panel-dragging {
  transition: none;
}

.workspace-panel-embedded {
  position: relative !important;
  width: 100% !important;
  height: 100% !important;
  top: auto !important;
  left: auto !important;
  border-radius: 4px;
}

.workspace-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 10px;
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
  cursor: move;
  gap: 8px;
  min-height: 28px;
}

.workspace-panel-title-group {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.workspace-panel-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.workspace-agent-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.workspace-agent-select {
  max-width: 220px;
  font-size: 12px;
  padding: 2px 4px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  background: var(--color-bg-secondary, var(--color-bg-primary));
  color: var(--color-text-primary);
  cursor: pointer;
}

.workspace-panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workspace-panel-actions .close-btn {
  width: 22px;
  height: 22px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-hover);
  border: none;
  border-radius: var(--tile-radius-xs);
  color: #8ba3b8;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  flex-shrink: 0;
}

.workspace-panel-actions .close-btn:hover {
  background: var(--color-bg-tertiary);
  color: #e6edf3;
}

.workspace-tabs {
  display: flex;
  align-items: stretch;
  gap: 2px;
  padding: 4px 4px 0;
  background: var(--color-bg-primary);
  overflow-x: auto;
  flex-shrink: 0;
}

.workspace-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 220px;
  padding: 6px 10px;
  border: none;
  border-bottom: none;
  border-radius: var(--tile-radius-xs) var(--tile-radius-xs) 0 0;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
}

.workspace-tab.active {
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.workspace-tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-tab-dirty {
  color: #ff8520;
  font-size: 10px;
}

.workspace-tab-close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 0;
}

.workspace-panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 30px;
  padding: 0 10px;
  border-top: 1px solid var(--color-border-subtle);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
}

.workspace-toolbar-status {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.workspace-toolbar-status.error {
  color: var(--color-error);
}

.workspace-toolbar-spacer {
  flex: 1;
}

.workspace-edit-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: none;
  border-radius: var(--tile-radius-xs);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease-out;
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);

}

.workspace-edit-toggle:hover {
  background: var(--color-bg-hover);
}

.workspace-edit-toggle:active {
  transform: scale(0.96);
}

.workspace-edit-toggle.editable {
  background: rgba(54, 255, 124, 0.15);
  color: var(--color-success);
}

.workspace-edit-toggle.editable:hover {
  background: rgba(54, 255, 124, 0.25);
}

.workspace-edit-toggle-icon {
  font-size: 12px;
}

.workspace-edit-toggle-text {
  font-size: 11px;
  letter-spacing: 0.02em;
}

.workspace-main {
  flex: 1;
  min-height: 0;
  display: flex;
  background: var(--color-bg-primary);
}

.workspace-activity-bar {
  width: 44px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 8px 4px;
  border-right: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.workspace-activity-button {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  line-height: 1;
  border: 1px solid transparent;
  border-radius: var(--tile-radius);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s ease-out;
}

.workspace-activity-button:hover,
.workspace-activity-button.active {
  color: var(--color-text-primary);
  background: var(--color-accent-subtle);
  border-color: var(--color-border-active);
}

.workspace-panel-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.workspace-panel-content-main {
  /* 标签固定在顶部，内容区各自滚动（Monaco/diff/嵌入视图内部都有自己的滚动容器），
     因此这里不整体滚动，避免标签随内容一起滚走。 */
  overflow: hidden;
}

/* 主区域文件视图：占满主区域，内部仍由 diff / 占位 / Monaco 容器各自撑开 */
.workspace-main-file-view {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.workspace-placeholder {
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

.workspace-placeholder-icon {
  font-size: 48px;
  opacity: 0.6;
}

.workspace-placeholder-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.workspace-placeholder-text {
  font-size: 13px;
  line-height: 1.6;
  max-width: 320px;
}

.workspace-monaco-container {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.workspace-diff-view {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workspace-diff-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
  font-size: 12px;
  flex-shrink: 0;
}

.workspace-diff-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
}

.workspace-diff-hash {
  color: var(--color-text-secondary);
  font-family: monospace;
}

.workspace-diff-truncated {
  color: var(--color-warning, #e6a23c);
}

.workspace-diff-toggle,
.workspace-diff-close {
  flex-shrink: 0;
  padding: 2px 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.workspace-diff-toggle:hover,
.workspace-diff-close:hover {
  color: var(--color-text-primary);
  border-color: var(--color-text-secondary);
}

.workspace-diff-nav {
  flex-shrink: 0;
  padding: 2px 6px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 10px;
  line-height: 1.4;
  cursor: pointer;
}

.workspace-diff-nav:hover {
  color: var(--color-text-primary);
  border-color: var(--color-text-secondary);
}

.workspace-diff-status {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.workspace-diff-status.error {
  color: var(--color-danger, #f56c6c);
}

.workspace-diff-monaco {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.workspace-resize-handle {
  position: absolute;
  background: transparent;
  z-index: 10;
}

.workspace-resize-n,
.workspace-resize-s {
  left: 10px;
  right: 10px;
  height: 6px;
  cursor: ns-resize;
}

.workspace-resize-n {
  top: 0;
}

.workspace-resize-s {
  bottom: 0;
}

.workspace-resize-e,
.workspace-resize-w {
  top: 10px;
  bottom: 10px;
  width: 6px;
  cursor: ew-resize;
}

.workspace-resize-e {
  right: 0;
}

.workspace-resize-w {
  left: 0;
}

.workspace-resize-ne,
.workspace-resize-nw,
.workspace-resize-se,
.workspace-resize-sw {
  width: 14px;
  height: 14px;
}

.workspace-resize-ne {
  top: 0;
  right: 0;
  cursor: nesw-resize;
}

.workspace-resize-nw {
  top: 0;
  left: 0;
  cursor: nwse-resize;
}

.workspace-resize-se {
  bottom: 0;
  right: 0;
  cursor: nwse-resize;
}

.workspace-resize-sw {
  bottom: 0;
  left: 0;
  cursor: nesw-resize;
}
</style>