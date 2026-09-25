<template>
  <!-- 分割容器：flex 布局 + 可拖拽分隔条 -->
  <div
    v-if="node.type === 'split'"
    class="editor-pane-split"
    :class="node.direction === 'row' ? 'editor-pane-split-row' : 'editor-pane-split-column'"
  >
    <div class="editor-pane-split-child" :style="childStyle(0)">
      <EditorPaneTree
        :node="node.children[0]"
        :activePaneId="activePaneId"
        :canClose="true"
        :getTitle="getTitle"
        @activate="(id) => $emit('activate', id)"
        @split="(id, dir) => $emit('split', id, dir)"
        @close="(id) => $emit('close', id)"
        @startResize="(ev, n) => $emit('startResize', ev, n)"
      >
        <template #pane-content="slotProps">
          <slot name="pane-content" v-bind="slotProps" />
        </template>
      </EditorPaneTree>
    </div>
    <div
      class="editor-pane-divider"
      :class="node.direction === 'row' ? 'editor-pane-divider-vertical' : 'editor-pane-divider-horizontal'"
      @mousedown="$emit('startResize', $event, node)"
    ></div>
    <div class="editor-pane-split-child" :style="childStyle(1)">
      <EditorPaneTree
        :node="node.children[1]"
        :activePaneId="activePaneId"
        :canClose="true"
        :getTitle="getTitle"
        @activate="(id) => $emit('activate', id)"
        @split="(id, dir) => $emit('split', id, dir)"
        @close="(id) => $emit('close', id)"
        @startResize="(ev, n) => $emit('startResize', ev, n)"
      >
        <template #pane-content="slotProps">
          <slot name="pane-content" v-bind="slotProps" />
        </template>
      </EditorPaneTree>
    </div>
  </div>

  <!-- leaf：标题栏 + 内容插槽 -->
  <div
    v-else
    class="editor-pane-leaf"
    :class="{ 'editor-pane-leaf-active': node.id === activePaneId }"
    @mousedown="$emit('activate', node.id)"
  >
    <div class="editor-pane-leaf-header">
      <span class="editor-pane-leaf-title">{{ getTitle ? getTitle(node) : (node.view === 'session' ? '会话' : '文件') }}</span>
      <div class="editor-pane-leaf-actions">
        <button class="editor-pane-leaf-btn" title="左右分" @click.stop="$emit('split', node.id, 'row')">◫</button>
        <button class="editor-pane-leaf-btn" title="上下分" @click.stop="$emit('split', node.id, 'column')">⬓</button>
        <button
          v-if="canClose"
          class="editor-pane-leaf-btn"
          title="关闭此区域"
          @click.stop="$emit('close', node.id)"
        >✕</button>
      </div>
    </div>
    <div class="editor-pane-leaf-body">
      <slot name="pane-content" :pane="node" :active="node.id === activePaneId" />
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  activePaneId: { type: String, default: null },
  canClose: { type: Boolean, default: true },
  getTitle: { type: Function, default: null },
})

defineEmits(['activate', 'split', 'close', 'startResize'])

function childStyle(index) {
  const ratio = props.node.type === 'split' ? props.node.ratio : 0.5
  const size = index === 0 ? ratio : 1 - ratio
  return { flexBasis: `${size * 100}%`, flexGrow: 0, flexShrink: 0 }
}
</script>

<style scoped>
.editor-pane-split {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
}

.editor-pane-split-row {
  flex-direction: row;
}

.editor-pane-split-column {
  flex-direction: column;
}

.editor-pane-split-child {
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.editor-pane-divider {
  flex: 0 0 auto;
  background: var(--color-border-subtle);
  transition: background 0.15s ease;
}

.editor-pane-divider:hover {
  background: var(--color-accent);
}

.editor-pane-divider-vertical {
  width: 4px;
  cursor: ew-resize;
}

.editor-pane-divider-horizontal {
  height: 4px;
  cursor: ns-resize;
}

.editor-pane-leaf {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  border: 1px solid transparent;
}

.editor-pane-leaf-active {
  border-color: var(--color-accent);
}

.editor-pane-leaf-header {
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

.editor-pane-leaf-title {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.editor-pane-leaf-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.editor-pane-leaf-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 3px;
}

.editor-pane-leaf-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.editor-pane-leaf-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  overflow: hidden;
}
</style>
