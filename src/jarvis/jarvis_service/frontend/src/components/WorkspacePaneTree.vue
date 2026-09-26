<template>
  <!-- 分割容器：flex 布局 + 可拖拽分隔条 -->
  <div
    v-if="node.type === 'split'"
    class="workspace-pane-split"
    :class="node.direction === 'row' ? 'workspace-pane-split-row' : 'workspace-pane-split-column'"
  >
    <div class="workspace-pane-split-child" :style="childStyle(0)">
      <WorkspacePaneTree
        :node="node.children[0]"
        :activePaneId="activePaneId"
        :canClose="true"
        :getTitle="getTitle"
        :getStatus="getStatus"
        @activate="(id) => $emit('activate', id)"
        @split="(id, dir) => $emit('split', id, dir)"
        @close="(id) => $emit('close', id)"
        @startResize="(ev, n) => $emit('startResize', ev, n)"
      >
        <template #pane-content="slotProps">
          <slot name="pane-content" v-bind="slotProps" />
        </template>
      </WorkspacePaneTree>
    </div>
    <div
      class="workspace-pane-divider"
      :class="node.direction === 'row' ? 'workspace-pane-divider-vertical' : 'workspace-pane-divider-horizontal'"
      @mousedown="$emit('startResize', $event, node)"
    ></div>
    <div class="workspace-pane-split-child" :style="childStyle(1)">
      <WorkspacePaneTree
        :node="node.children[1]"
        :activePaneId="activePaneId"
        :canClose="true"
        :getTitle="getTitle"
        :getStatus="getStatus"
        @activate="(id) => $emit('activate', id)"
        @split="(id, dir) => $emit('split', id, dir)"
        @close="(id) => $emit('close', id)"
        @startResize="(ev, n) => $emit('startResize', ev, n)"
      >
        <template #pane-content="slotProps">
          <slot name="pane-content" v-bind="slotProps" />
        </template>
      </WorkspacePaneTree>
    </div>
  </div>

  <!-- leaf：标题栏 + 内容插槽 -->
  <div
    v-else
    class="workspace-pane-leaf"
    :class="{ 'workspace-pane-leaf-active': node.id === activePaneId }"
    @mousedown="$emit('activate', node.id)"
  >
    <WorkspacePaneHeader
      :node="node"
      :canSplit="canSplit"
      :canClose="canClose"
      :getTitle="getTitle"
      :getStatus="getStatus"
      @split="(id, dir) => $emit('split', id, dir)"
      @close="(id) => $emit('close', id)"
    />
    <div class="workspace-pane-leaf-body">
      <slot name="pane-content" :pane="node" :active="node.id === activePaneId" />
    </div>
  </div>
</template>

<script setup>
import { defineProps, defineEmits } from 'vue'
import WorkspacePaneHeader from './WorkspacePaneHeader.vue'

const props = defineProps({
  node: { type: Object, required: true },
  activePaneId: { type: String, default: null },
  canClose: { type: Boolean, default: true },
  canSplit: { type: Boolean, default: true },
  getTitle: { type: Function, default: null },
  getStatus: { type: Function, default: null },
})

defineEmits(['activate', 'split', 'close', 'startResize'])

function childStyle(index) {
  const ratio = props.node.type === 'split' ? props.node.ratio : 0.5
  const size = index === 0 ? ratio : 1 - ratio
  return { flexBasis: `${size * 100}%`, flexGrow: 0, flexShrink: 0 }
}
</script>

<style scoped>
.workspace-pane-split {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
}

.workspace-pane-split-row {
  flex-direction: row;
}

.workspace-pane-split-column {
  flex-direction: column;
}

.workspace-pane-split-child {
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.workspace-pane-divider {
  flex: 0 0 auto;
  background: var(--color-border-subtle);
  transition: background 0.15s ease;
}

.workspace-pane-divider:hover {
  background: var(--color-accent);
}

.workspace-pane-divider-vertical {
  width: 4px;
  cursor: ew-resize;
}

.workspace-pane-divider-horizontal {
  height: 4px;
  cursor: ns-resize;
}

.workspace-pane-leaf {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  min-height: 0;
  width: 100%;
  height: 100%;
  border: 1px solid transparent;
}

.workspace-pane-leaf-active {
  border-color: var(--color-accent);
}

.workspace-pane-leaf-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  overflow: hidden;
}
</style>
