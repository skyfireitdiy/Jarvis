<template>
  <!-- 分割容器：flex 布局 + 可拖拽分隔条 -->
  <div
    v-if="node.type === 'split'"
    class="workspace-pane-split"
    :class="node.direction === 'row' ? 'workspace-pane-split-row' : 'workspace-pane-split-column'"
  >
    <div
      v-for="index in [0, 1]"
      :key="index"
      class="workspace-pane-split-child"
      :class="{ 'workspace-pane-split-child-collapsed': isCollapsed(index) }"
      :style="childStyle(index)"
    >
      <!-- 折叠态：只渲染一条窄条标记（内容用 v-show 隐藏，DOM 保留 → Monaco/xterm/Session 零销毁） -->
      <button
        v-if="isCollapsed(index)"
        type="button"
        class="workspace-pane-collapsed-bar"
        :class="collapsedBarClass(index)"
        :title="collapsedBarTitle(index)"
        @click.stop="$emit('toggle-collapse', node, index)"
      >
        <span class="workspace-pane-collapsed-arrow">{{ collapsedBarArrow(index) }}</span>
        <span class="workspace-pane-collapsed-icon">{{ collapsedBarIcon(index) }}</span>
        <span class="workspace-pane-collapsed-label">{{ collapsedBarLabel(index) }}</span>
      </button>
      <WorkspacePaneTree
        v-show="!isCollapsed(index)"
        :node="node.children[index]"
        :activePaneId="activePaneId"
        :maximizedPaneId="maximizedPaneId"
        :canClose="true"
        :getTitle="getTitle"
        :getStatus="getStatus"
        :getSessionTabs="getSessionTabs"
        @activate="(id) => $emit('activate', id)"
        @split="(id, dir) => $emit('split', id, dir)"
        @close="(id) => $emit('close', id)"
        @maximize="(id) => $emit('maximize', id)"
        @collapse="(id) => $emit('collapse', id)"
        @toggle-collapse="(splitNode, index) => $emit('toggle-collapse', splitNode, index)"
        @startResize="(ev, n) => $emit('startResize', ev, n)"
        @activate-session-tab="(id, panelId) => $emit('activate-session-tab', id, panelId)"
        @close-session-tab="(id, panelId) => $emit('close-session-tab', id, panelId)"
        @add-session-tab="(id) => $emit('add-session-tab', id)"
        @session-tab-context-menu="(id, panelId, ev) => $emit('session-tab-context-menu', id, panelId, ev)"
      >
        <template #pane-content="slotProps">
          <slot name="pane-content" v-bind="slotProps" />
        </template>
      </WorkspacePaneTree>
    </div>
    <!-- 折叠时隐藏分隔条（无可拖拽的两侧） -->
    <div
      v-if="!node.collapsed"
      class="workspace-pane-divider"
      :class="node.direction === 'row' ? 'workspace-pane-divider-vertical' : 'workspace-pane-divider-horizontal'"
      @mousedown="$emit('startResize', $event, node)"
    ></div>
  </div>

  <!-- leaf：标题栏 + 内容插槽 -->
  <div
    v-else
    class="workspace-pane-leaf"
    :class="{
      'workspace-pane-leaf-active': node.id === activePaneId,
      'workspace-pane-leaf-maximized': node.id === maximizedPaneId,
    }"
    :data-pane-id="node.id"
    @mousedown="$emit('activate', node.id)"
  >
    <WorkspacePaneHeader
      :node="node"
      :canSplit="canSplit"
      :canClose="canClose"
      :canMaximize="canMaximize"
      :canCollapse="canCollapse"
      :maximized="node.id === maximizedPaneId"
      :getTitle="getTitle"
      :getStatus="getStatus"
      :sessionTabs="getSessionTabs ? getSessionTabs(node) : null"
      :activeSessionPanelId="node.activeSessionPanelId || null"
      @split="(id, dir) => $emit('split', id, dir)"
      @close="(id) => $emit('close', id)"
      @maximize="(id) => $emit('maximize', id)"
      @collapse="(id) => $emit('collapse', id)"
      @activate-session-tab="(id, panelId) => $emit('activate-session-tab', id, panelId)"
      @close-session-tab="(id, panelId) => $emit('close-session-tab', id, panelId)"
      @add-session-tab="(id) => $emit('add-session-tab', id)"
      @session-tab-context-menu="(id, panelId, ev) => $emit('session-tab-context-menu', id, panelId, ev)"
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
  maximizedPaneId: { type: String, default: null },
  canClose: { type: Boolean, default: true },
  canSplit: { type: Boolean, default: true },
  canMaximize: { type: Boolean, default: true },
  canCollapse: { type: Boolean, default: true },
  getTitle: { type: Function, default: null },
  getStatus: { type: Function, default: null },
  getSessionTabs: { type: Function, default: null },
})

defineEmits(['activate', 'split', 'close', 'startResize', 'maximize', 'collapse', 'toggle-collapse', 'activate-session-tab', 'close-session-tab', 'add-session-tab', 'session-tab-context-menu'])

// 折叠窄条的尺寸（与 CSS 保持一致）
const COLLAPSED_BAR_SIZE = '26px'

function isCollapsed(index) {
  return !!props.node.collapsed && props.node.collapsed.side === index
}
function childStyle(index) {
  if (props.node.type !== 'split') return { flexBasis: '50%', flexGrow: 0, flexShrink: 0 }
  if (isCollapsed(index)) {
    const vertical = props.node.direction === 'row'
    return vertical
      ? { flexBasis: COLLAPSED_BAR_SIZE, width: COLLAPSED_BAR_SIZE, flexGrow: 0, flexShrink: 0 }
      : { flexBasis: COLLAPSED_BAR_SIZE, height: COLLAPSED_BAR_SIZE, flexGrow: 0, flexShrink: 0 }
  }
  // 另一侧被折叠时，本侧占满剩余空间
  if (props.node.collapsed) return { flexBasis: '100%', flexGrow: 1, flexShrink: 1 }
  const ratio = props.node.ratio
  const size = index === 0 ? ratio : 1 - ratio
  return { flexBasis: `${size * 100}%`, flexGrow: 0, flexShrink: 0 }
}

// 折叠子树中「最靠近折叠条」的 leaf：展开时以它为激活目标，并据此显示类型图标/标题
function edgeLeaf(node, direction) {
  if (!node) return null
  if (node.type === 'leaf') return node
  // 折叠条在左/上 → 取子树最左/最上的 leaf；在右/下 → 取最右/最下的 leaf
  const wantFirst = direction === 'left' || direction === 'up'
  return edgeLeaf(node.children[wantFirst ? 0 : 1], direction)
}
// 折叠条所在方向：row 分割的 side 0 在左、side 1 在右；column 分割的 side 0 在上、side 1 在下
function collapsedDirection(index) {
  const row = props.node.direction === 'row'
  if (row) return index === 0 ? 'left' : 'right'
  return index === 0 ? 'up' : 'down'
}
function collapsedBarClass(index) {
  const dir = collapsedDirection(index)
  return [
    `workspace-pane-collapsed-bar-${props.node.direction === 'row' ? 'vertical' : 'horizontal'}`,
    `workspace-pane-collapsed-bar-${dir}`,
  ]
}
// 箭头指向「展开方向」：折叠条在左 → 向右展开；在上 → 向下展开
function collapsedBarArrow(index) {
  const dir = collapsedDirection(index)
  return { left: '▸', right: '◂', up: '▾', down: '▴' }[dir]
}
function collapsedBarLeaf(index) {
  return edgeLeaf(props.node.children[index], collapsedDirection(index))
}
// 内容类型图标：终端与 Session 必须一眼可区分
const VIEW_ICONS = {
  terminal: '>_',
  session: '◉',
  file: '📄',
  chat: '💬',
  diff: '±',
  empty: '·',
}
const VIEW_LABELS = {
  terminal: '终端',
  session: '会话',
  file: '编辑器',
  chat: '聊天',
  diff: 'diff',
  empty: '空区域',
}
function collapsedBarIcon(index) {
  const leaf = collapsedBarLeaf(index)
  if (!leaf) return '·'
  if (typeof leaf.view === 'string' && leaf.view.startsWith('plugin-pane:')) return '🧩'
  return VIEW_ICONS[leaf.view] || '·'
}
function collapsedBarLabel(index) {
  const leaf = collapsedBarLeaf(index)
  if (!leaf) return ''
  if (typeof leaf.view === 'string' && leaf.view.startsWith('plugin-pane:')) return '插件面板'
  return VIEW_LABELS[leaf.view] || ''
}
function collapsedBarTitle(index) {
  const leaf = collapsedBarLeaf(index)
  if (!leaf) return '展开'
  const title = props.getTitle ? props.getTitle(leaf) : ''
  const type = collapsedBarLabel(index)
  return `展开：${title || type}${title && type ? `（${type}）` : ''}`
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
.workspace-pane-split-child-collapsed {
  flex: 0 0 auto;
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
/* 折叠窄条：很小的标记，点击展开。竖条（左右分割）/ 横条（上下分割）形态本身即可区分方向。 */
.workspace-pane-collapsed-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 0;
  background: var(--color-bg-secondary, #252526);
  color: var(--color-text-secondary);
  cursor: pointer;
  overflow: hidden;
  transition: background 0.15s ease, color 0.15s ease;
}
.workspace-pane-collapsed-bar:hover {
  background: var(--color-bg-hover, #2a2d2e);
  color: var(--color-text-primary);
  border-color: var(--color-accent);
}
.workspace-pane-collapsed-bar-vertical {
  flex-direction: column;
  width: 100%;
}
.workspace-pane-collapsed-bar-horizontal {
  flex-direction: row;
  height: 100%;
}
.workspace-pane-collapsed-arrow {
  font-size: 11px;
  line-height: 1;
  opacity: 0.75;
}
.workspace-pane-collapsed-icon {
  font-size: 12px;
  line-height: 1;
}
/* 类型文字：竖条里竖排（writing-mode），横条里横排 */
.workspace-pane-collapsed-bar-vertical .workspace-pane-collapsed-label {
  writing-mode: vertical-rl;
  font-size: 10px;
  letter-spacing: 1px;
  white-space: nowrap;
}
.workspace-pane-collapsed-bar-horizontal .workspace-pane-collapsed-label {
  font-size: 10px;
  letter-spacing: 1px;
  white-space: nowrap;
}
.workspace-pane-collapsed-label {
  color: inherit;
  opacity: 0.8;
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
/* 临时最大化：把该 leaf 用 fixed 提升为全屏浮层（DOM 不移动，Monaco/xterm 实例零重建）。
   还原即移除本 class，无缝嵌回原布局。 */
.workspace-pane-leaf-maximized {
  position: fixed;
  inset: 0;
  z-index: 2500;
  width: auto;
  height: auto;
  background: var(--color-bg-primary, #1e1e1e);
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
