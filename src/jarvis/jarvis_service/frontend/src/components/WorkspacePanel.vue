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
      </div>
      <div class="workspace-panel-actions">
        <button class="icon-btn close-btn" tabindex="-1" @mousedown.prevent @click.stop="$emit('close')" title="关闭">✕</button>
      </div>
    </div>
    <div class="workspace-main">
      <div class="workspace-activity-bar">
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'agents' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setSidebarView', 'agents')"
          title="Agent 列表 (Space v a)"
        >
          <img class="workspace-activity-icon" src="/icons/jarvis-pet.svg" alt="Agent" />
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'files' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setSidebarView', 'files')"
          title="目录树"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M1.5 4.5A1.5 1.5 0 0 1 3 3h2.4l1.6 1.6H13A1.5 1.5 0 0 1 14.5 6v5.5A1.5 1.5 0 0 1 13 13H3a1.5 1.5 0 0 1-1.5-1.5v-7Z"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'search' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setSidebarView', 'search')"
          title="全局搜索"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5"/>
            <path d="M10.5 10.5 14 14"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: showSidebar && sidebarView === 'git' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setSidebarView', 'git')"
          title="Git (Space v g)"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="5" cy="4" r="1.5"/>
            <circle cx="5" cy="12" r="1.5"/>
            <circle cx="11" cy="8" r="1.5"/>
            <path d="M5 5.5v5"/>
            <path d="M6.5 12H9.5a1.5 1.5 0 0 0 1.5-1.5V9"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: mainView === 'chat' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setMainView', 'chat')"
          title="聊天室"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v6a1.5 1.5 0 0 1-1.5 1.5H6.5L3.5 14v-3H3.5A1.5 1.5 0 0 1 2 9.5v-6Z"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          :class="{ active: mainView === 'terminal' }"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('setMainView', 'terminal')"
          title="终端"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h9A1.5 1.5 0 0 1 14 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9Z"/>
            <path d="M5 6l2 2-2 2"/>
            <path d="M8.5 10H11"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('openSettings')"
          title="设置 (Space v s)"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="8" cy="8" r="1.5"/>
            <circle cx="8" cy="8" r="4.2"/>
            <g stroke-width="2.4">
              <path d="M8 3.8v-2M10.97 5.03l1.41-1.41M12.2 8h2M10.97 10.97l1.41 1.41M8 12.2v2M5.03 10.97l-1.41 1.41M3.8 8h-2M5.03 5.03l-1.41-1.41"/>
            </g>
          </svg>
        </button>
        <button
          v-if="isAdmin"
          class="workspace-activity-button"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('openAdmin')"
          title="管理 (Space m a)"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M8 1.5 13 3.5v4c0 3-2 5.5-5 7-3-1.5-5-4-5-7v-4L8 1.5Z"/>
            <path d="M5.5 8l1.7 1.7L10.5 6"/>
          </svg>
        </button>
        <button
          class="workspace-activity-button"
          tabindex="-1"
          @mousedown.prevent
          @click="$emit('openDocs')"
          title="使用文档 (Space m h)"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="8" cy="8" r="6"/>
            <path d="M6.3 6.4a1.7 1.7 0 1 1 2.8 1.3c-.8.6-1.1 1-1.1 1.8"/>
            <circle cx="8" cy="11.6" r="0.4" fill="currentColor" stroke="none"/>
          </svg>
        </button>
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
            @contextmenu.prevent.stop="$emit('tabContextMenu', tab.path, $event)"
          >
            <span class="workspace-tab-name">{{ tab.name }}</span>
            <span v-if="tab.isDirty" class="workspace-tab-dirty">●</span>
            <button class="workspace-tab-close" tabindex="-1" @mousedown.prevent @click.stop="$emit('closeTab', tab.path)">✕</button>
          </div>
          <!-- 未分割态同样提供保存 / 只读开关（作用于当前激活文件），
               与已分割态各 pane 的工具栏保持一致，避免「未分割时无法切换可编辑」。 -->
          <div class="workspace-pane-actions">
            <button
              class="workspace-pane-action"
              :disabled="!hasActiveTab"
              tabindex="-1"
              @mousedown.prevent
              @click.stop="$emit('save')"
              title="保存当前文件"
            ><span v-html="WORKSPACE_ICONS.save"></span></button>
            <button
              class="workspace-pane-action"
              :class="{ editable: isEditable }"
              :disabled="!hasActiveTab"
              tabindex="-1"
              @mousedown.prevent
              @click.stop="$emit('toggleEditable')"
              :title="isEditable ? '切换到只读模式' : '切换到编辑模式'"
            ><span v-html="isEditable ? WORKSPACE_ICONS.unlock : WORKSPACE_ICONS.lock"></span></button>
          </div>
        </div>
        <!-- 自由分割模式：由 App.vue 提供整棵 pane 树（含每个 leaf 的内容），
             此时不再渲染原有的单视图内容，避免两套渲染路径并存。 -->
        <slot name="pane-tree"></slot>
        <template v-if="!$slots['pane-tree']">
        <!-- 未分割态的区域标题栏：与已分割时各 pane 的标题栏同源（WorkspacePaneHeader），
             保证「未分割也有分屏入口」。由 App.vue 传入（含根 leaf 与分屏回调）。 -->
        <slot name="main-view-header"></slot>
        <slot name="main-view"></slot>
        <div v-show="mainView === 'file'" class="workspace-main-file-view">
          <div v-if="tabs.length === 0" class="workspace-placeholder">
            <div class="workspace-placeholder-icon" v-html="WORKSPACE_ICONS.placeholder"></div>
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

// 自绘 16x16 stroke 线性 SVG 图标（currentColor 继承主题色），与全局风格一致
const WORKSPACE_ICONS = {
  save: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 2.5h9l1.5 1.5v9.5a1 1 0 0 1-1 1h-10a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M5 2.5v4h5v-4M5 13.5v-5h6v5"/></svg>',
  lock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>',
  unlock: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.9-.8"/></svg>',
  placeholder: '<svg viewBox="0 0 16 16" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.5h8v13l-1.5-1-1.5 1-1.5-1-1.5 1-1.5-1z"/><path d="M6 5.5h4M6 8h4M6 10.5h2.5"/></svg>',
}

const props = defineProps({
  visible: Boolean,
  active: Boolean,
  embedded: Boolean,
  interaction: Object,
  panelStyle: Object,
  agentName: String,
  activeTab: Object,
  activeTabPath: String,
  tabs: Array,
  isMaximized: Boolean,
  showSidebar: Boolean,
  sidebarView: String,
  mainView: { type: String, default: 'file' },
  resizeDirections: Array,
  isAdmin: { type: Boolean, default: false },
  isEditable: { type: Boolean, default: false },
  hasActiveTab: { type: Boolean, default: false }
})

const emit = defineEmits([
  'focus',
  'startMove',
  'toggleMaximize',
  'save',
  'close',
  'activateTab',
  'closeTab',
  'tabContextMenu',
  'toggleEditable',
  'setSidebarView',
  'setMainView',
  'startResize',
  'closeSidebar',
  'openSettings',
  'openDocs',
  'openAdmin'
])

const editorContainerRef = ref(null)

defineExpose({
  editorContainerRef
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
/* 未分割态标签栏右侧的保存 / 只读按钮（与已分割态 pane 工具栏同款） */
.workspace-pane-actions {
  position: sticky;
  right: 0;
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 2px;
  padding-left: 6px;
  background: var(--color-bg-secondary, #1e1e1e);
}
.workspace-pane-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.workspace-pane-action:hover:not(:disabled) {
  background: var(--color-bg-hover, rgba(255, 255, 255, 0.08));
}
.workspace-pane-action.editable {
  color: var(--color-accent, #4a9eff);
}
.workspace-pane-action:disabled {
  opacity: 0.4;
  cursor: default;
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

/* Agent 图标：使用主图标（Jarvis 吉祥物），需缩放到与 emoji 图标视觉一致 */
.workspace-activity-icon {
  width: 20px;
  height: 20px;
  display: block;
  object-fit: contain;
}

.workspace-panel-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.workspace-panel-content-main {
  /* 标签固定在顶部，内容区各自滚动（Monaco/嵌入视图内部都有自己的滚动容器），
     因此这里不整体滚动，避免标签随内容一起滚走。 */
  overflow: hidden;
}

/* 主区域文件视图：占满主区域，内部由占位 / Monaco 容器各自撑开 */
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