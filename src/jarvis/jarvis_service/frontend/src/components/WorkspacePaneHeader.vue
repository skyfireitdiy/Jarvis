<template>
  <!-- 工作区区域标题栏：已分割时由每个 leaf 渲染，未分割时由 App.vue 为唯一区域渲染。
       统一两处的标题/状态/分屏/关闭按钮，避免出现「未分割没有分屏入口」的割裂。 -->
  <div class="workspace-pane-leaf-header">
    <span class="workspace-pane-leaf-title">{{ getTitle ? getTitle(node) : (node.view === 'session' ? '会话' : '文件') }}</span>
    <span v-if="getStatus && getStatus(node)" class="workspace-pane-leaf-status">{{ getStatus(node) }}</span>
    <div class="workspace-pane-leaf-actions">
      <button v-if="canSplit" class="workspace-pane-leaf-btn" title="左右分" @click.stop="$emit('split', node.id, 'row')">◫</button>
      <button v-if="canSplit" class="workspace-pane-leaf-btn" title="上下分" @click.stop="$emit('split', node.id, 'column')">⬓</button>
      <button
        v-if="canClose"
        class="workspace-pane-leaf-btn"
        title="关闭此区域"
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
  getTitle: { type: Function, default: null },
  getStatus: { type: Function, default: null },
})

defineEmits(['split', 'close'])
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
</style>
