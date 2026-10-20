<template>
  <!-- 工作区区域标题栏：已分割时由每个 leaf 渲染，未分割时由 App.vue 为唯一区域渲染。
       统一两处的标题/状态/分屏/关闭按钮，避免出现「未分割没有分屏入口」的割裂。 -->
  <div class="workspace-pane-leaf-header">
    <!-- session 多 tab：该 pane 承载多个 Agent 会话时渲染 tab 栏 -->
    <div v-if="node.view === 'session' && sessionTabs && sessionTabs.length > 0" class="workspace-pane-session-tabs" @mousedown.stop>
      <div
        v-for="tab in sessionTabs"
        :key="tab.panelId"
        class="workspace-pane-session-tab"
        :class="{ active: tab.panelId === activeSessionPanelId }"
        :title="tab.label"
        @click.stop="$emit('activate-session-tab', node.id, tab.panelId)"
        @contextmenu.prevent.stop="$emit('session-tab-context-menu', node.id, tab.panelId, $event)"
      >
        <span class="workspace-pane-session-tab-name">{{ tab.label }}</span>
        <button
          class="workspace-pane-session-tab-close"
          tabindex="-1"
          :title="`关闭 ${tab.label}`"
          @mousedown.prevent
          @click.stop="$emit('close-session-tab', node.id, tab.panelId)"
        >✕</button>
      </div>
      <button
        class="workspace-pane-session-tab-add"
        tabindex="-1"
        title="追加空标签页（从侧边栏选择 Agent 放入）"
        @mousedown.prevent
        @click.stop="$emit('add-session-tab', node.id)"
      >+</button>
    </div>
    <template v-else>
      <span class="workspace-pane-leaf-title">{{ getTitle ? getTitle(node) : (node.view === 'session' ? '会话' : '文件') }}</span>
      <span v-if="getStatus && getStatus(node)" class="workspace-pane-leaf-status">{{ getStatus(node) }}</span>
    </template>
    <div class="workspace-pane-leaf-actions">
      <button
        v-if="canMaximize"
        tabindex="-1"
        class="workspace-pane-leaf-btn"
        :title="maximized ? '还原区域' : '最大化区域'"
        @mousedown.prevent
        @click.stop="$emit('maximize', node.id)"
      >{{ maximized ? '⤡' : '⛶' }}</button>
      <button
        v-if="canCollapse"
        tabindex="-1"
        class="workspace-pane-leaf-btn"
        title="折叠此区域（内容保留，Space p c 可切换）"
        @mousedown.prevent
        @click.stop="$emit('collapse', node.id)"
      >⏷</button>
      <button v-if="canSplit" tabindex="-1" class="workspace-pane-leaf-btn" title="左右分" @mousedown.prevent @click.stop="$emit('split', node.id, 'row')">◫</button>
      <button v-if="canSplit" tabindex="-1" class="workspace-pane-leaf-btn" title="上下分" @mousedown.prevent @click.stop="$emit('split', node.id, 'column')">⬓</button>
      <button
        v-if="canClose"
        tabindex="-1"
        class="workspace-pane-leaf-btn"
        title="关闭此区域"
        @mousedown.prevent
        @click.stop="$emit('close', node.id)"
      >✕</button>
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  canSplit: { type: Boolean, default: true },
  canClose: { type: Boolean, default: true },
  canMaximize: { type: Boolean, default: true },
  canCollapse: { type: Boolean, default: true },
  maximized: { type: Boolean, default: false },
  getTitle: { type: Function, default: null },
  getStatus: { type: Function, default: null },
  // session 多 tab：tab 列表 [{ panelId, label }] 与当前激活 tab
  sessionTabs: { type: Array, default: null },
  activeSessionPanelId: { type: String, default: null },
})

defineEmits(['split', 'close', 'maximize', 'collapse', 'activate-session-tab', 'close-session-tab', 'add-session-tab', 'session-tab-context-menu'])
</script>

<style scoped>
.workspace-pane-leaf-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 8px;
  min-height: 24px;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
  flex-shrink: 0;
}

.workspace-pane-leaf-title {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.workspace-pane-leaf-status {
  margin-left: auto;
  margin-right: 8px;
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.workspace-pane-leaf-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.workspace-pane-leaf-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 3px;
}

.workspace-pane-leaf-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

/* session 多 tab 栏 */
.workspace-pane-session-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.workspace-pane-session-tabs::-webkit-scrollbar {
  display: none;
}

.workspace-pane-session-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  white-space: nowrap;
  max-width: 160px;
  flex-shrink: 0;
}

.workspace-pane-session-tab:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.workspace-pane-session-tab.active {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.workspace-pane-session-tab-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.workspace-pane-session-tab-close {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 10px;
  line-height: 1;
  padding: 1px 2px;
  border-radius: 2px;
}

.workspace-pane-session-tab-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.workspace-pane-session-tab-add {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 1px 4px;
  border-radius: 3px;
  flex-shrink: 0;
}

.workspace-pane-session-tab-add:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}
</style>
