<template>
  <transition name="cmd-fade">
    <div v-if="visible" class="cmd-overlay" @click.self="close" @keydown.stop>
      <div class="cmd-panel" role="dialog" aria-label="命令面板">
        <div class="cmd-search">
          <span class="cmd-search-ico">⌘</span>
          <input
            ref="inputEl"
            class="cmd-input"
            v-model="query"
            type="text"
            :placeholder="isAgentMode ? '搜索 Agent…' : title"
            autocomplete="off"
            spellcheck="false"
            @keydown="onInputKeydown"
            @blur="onInputBlur"
          />
          <span class="cmd-esc-hint">Esc</span>
        </div>

        <div class="cmd-list">
          <template v-if="groups.length > 0">
            <div v-for="g in groups" :key="g.group" class="cmd-group">
              <div class="cmd-group-title">{{ g.group }}</div>
              <button
                v-for="entry in g.actions"
                :key="entry.action.id"
                class="cmd-item"
                :class="{ 'is-active': entry.flatIndex === activeIndex, 'is-disabled': entry.disabled }"
                :disabled="entry.disabled"
                :ref="el => setItemRef(el, entry.flatIndex)"
                @click="run(entry.action)"
                @mousemove="onItemHover(entry.flatIndex)"
              >
                <span class="cmd-item-ico">{{ entry.action.icon }}</span>
                <span class="cmd-item-label">
                  <span class="cmd-item-title">{{ entry.action.label }}<span v-if="entry.action.en" class="cmd-item-en">{{ entry.action.en }}</span></span>
                  <span v-if="entry.action.meta" class="cmd-item-meta">{{ entry.action.meta }}</span>
                </span>
                <span v-if="entry.action.shortcut" class="cmd-item-shortcut">{{ entry.action.shortcut }}</span>
              </button>
            </div>
          </template>
          <div v-else class="cmd-empty">{{ isAgentMode ? '无匹配 Agent' : '无匹配命令' }}</div>
        </div>

        <div class="cmd-footer">
          <span><b>↑↓</b> 选择</span>
          <span><b>Enter</b> 执行</span>
          <span><b>Esc</b> 关闭</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { filterActions, groupActions } from '../actions/registry.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  actions: { type: Array, default: () => [] },
  ctx: { type: Object, default: () => ({}) },
  title: { type: String, default: '搜索命令…' },
})

const emit = defineEmits(['update:visible', 'run', 'close'])

const query = ref('')
const activeIndex = ref(0)
const inputEl = ref(null)
const itemRefs = new Map()

function isDisabled(action) {
  if (typeof action.enabled === 'function') return !action.enabled(props.ctx || {})
  // Agent 切换条目直接携带布尔 disabled，避免与上面的 enabled 回调判断冲突
  return action?.disabled === true
}

// ===== Agent 切换模式：输入 a> 或 A> 时，列表改为展示 Agent =====
const AGENT_PREFIX = /^\s*a>\s*/i
const isAgentMode = computed(() => AGENT_PREFIX.test(query.value))
const agentQuery = computed(() => query.value.replace(AGENT_PREFIX, ''))

function agentStatusIcon(agent) {
  const ctx = props.ctx || {}
  if (typeof ctx.isWaitingInput === 'function' && ctx.isWaitingInput(agent)) return '🚨'
  const status = typeof ctx.getStatusClass === 'function' ? ctx.getStatusClass(agent) : 'running'
  if (status === 'stopped') return '○'
  return '●'
}

// 将 Agent 列表转换为动作对象，复用命令面板的渲染与键盘导航
const agentEntries = computed(() => {
  const ctx = props.ctx || {}
  const list = Array.isArray(ctx.agentList) ? ctx.agentList : []
  const opened = ctx.openedAgentIds instanceof Set ? ctx.openedAgentIds : new Set()
  const q = agentQuery.value.trim().toLowerCase()
  const isOpened = agent => opened.has(agent?.agent_id)
  return list
    .filter(agent => {
      if (!q) return true
      const nodeLabel = typeof ctx.getAgentNodeLabel === 'function' ? ctx.getAgentNodeLabel(agent) : ''
      const haystack = [agent?.name, agent?.agent_id, nodeLabel].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(q)
    })
    // 已在 Panel 中打开的（激活的）排在前面，其余保持原顺序
    .sort((a, b) => (isOpened(b) ? 1 : 0) - (isOpened(a) ? 1 : 0))
    .map(agent => {
      const nodeLabel = typeof ctx.getAgentNodeLabel === 'function' ? ctx.getAgentNodeLabel(agent) : ''
      const active = agent?.agent_id === ctx.currentAgentId
      const metaParts = []
      if (nodeLabel) metaParts.push(`🖥 ${nodeLabel}`)
      if (agent?.proxy_node) metaParts.push(`🔀 代理 ${agent.proxy_node}`)
      if (agent?.llm_group) metaParts.push(`🧠 ${agent.llm_group}`)
      if (agent?.quick_mode) metaParts.push('⚡ 极速')
      if (agent?.worktree) metaParts.push('🌿 worktree')
      if (agent?.working_dir) metaParts.push(`📁 ${agent.working_dir}`)
      return {
        id: `agent-switch:${agent.agent_id}`,
        label: agent?.name || agent?.agent_id,
        en: agent?.agent_id,
        group: '切换 Agent',
        icon: agentStatusIcon(agent),
        keywords: [nodeLabel],
        meta: metaParts.join('   '),
        disabled: active,
        run: (c) => c.switchToAgent && c.switchToAgent(agent),
      }
    })
})

// 过滤 + 扁平化（用连续索引做键盘导航，与分组展示解耦）
const flatEntries = computed(() => {
  let flatIndex = 0
  const matched = isAgentMode.value
    ? agentEntries.value
    : filterActions(props.actions, query.value)
  return matched.map(action => ({
    action,
    disabled: isDisabled(action),
    flatIndex: flatIndex++,
  }))
})

const entryById = computed(() => new Map(flatEntries.value.map(e => [e.action.id, e])))

// 按分组组织，元素引用扁平条目（保留 flatIndex）
const groups = computed(() =>
  groupActions(flatEntries.value.map(e => e.action)).map(g => ({
    group: g.group,
    actions: g.actions.map(a => entryById.value.get(a.id)).filter(Boolean),
  }))
)

function setItemRef(el, index) {
  if (el) itemRefs.set(index, el)
  else itemRefs.delete(index)
}

function move(delta) {
  const total = flatEntries.value.length
  if (total === 0) return
  let next = activeIndex.value
  for (let i = 0; i < total; i++) {
    next = (next + delta + total) % total
    if (!flatEntries.value[next]?.disabled) break
  }
  activeIndex.value = next
  scrollActiveIntoView()
}

function scrollActiveIntoView() {
  nextTick(() => {
    const el = itemRefs.get(activeIndex.value)
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' })
    }
  })
}

function onItemHover(index) {
  activeIndex.value = index
}

function run(action) {
  if (!action || isDisabled(action)) return
  emit('run', action)
}

function close() {
  emit('update:visible', false)
  emit('close')
}

// 全局 Escape：无论焦点在输入框还是面板其它位置，一次 Esc 即关闭。
// 使用 window 捕获阶段，确保先于其它 keydown 处理，且不受 overlay @keydown.stop 影响。
function handleGlobalEscape(event) {
  if (!props.visible) return
  if (event.key === 'Escape' || event.code === 'Escape' || event.keyCode === 27) {
    event.preventDefault()
    event.stopPropagation()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', handleGlobalEscape, true))
onBeforeUnmount(() => window.removeEventListener('keydown', handleGlobalEscape, true))

// 输入框失焦：某些输入法/浏览器在输入框聚焦时按 Esc 不会派发 keydown，
// 只触发 blur（用户表现为“第一次 Esc 焦点消失”）。因此在焦点真正离开面板时关闭，
// 确保一次 Esc 即关闭。延迟到事件循环末检查，避免点击面板内选项时误关。
function onInputBlur() {
  setTimeout(() => {
    if (!props.visible) return
    const overlay = document.querySelector('.cmd-overlay')
    const active = document.activeElement
    if (overlay && active && overlay.contains(active)) return
    close()
  }, 0)
}

function onInputKeydown(event) {
  // 带 Ctrl/Alt/Meta 修饰键时交由全局快捷键处理，不做列表导航
  if (event.ctrlKey || event.altKey || event.metaKey) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const entry = flatEntries.value[activeIndex.value]
    if (entry && !entry.disabled) run(entry.action)
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

watch(
  () => props.visible,
  visible => {
    if (visible) {
      query.value = ''
      activeIndex.value = 0
      itemRefs.clear()
      nextTick(() => inputEl.value?.focus())
    } else {
      itemRefs.clear()
    }
  },
  { immediate: true }
)

watch(query, () => {
  activeIndex.value = 0
})

defineExpose({ focus: () => inputEl.value?.focus() })
</script>

<style scoped>
.cmd-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 12vh;
  background: rgba(4, 8, 16, 0.55);
  backdrop-filter: blur(2px);
}

.cmd-panel {
  width: min(560px, 92vw);
  max-height: 62vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius, 10px);
  box-shadow: var(--tile-shadow, 0 8px 30px rgba(0, 120, 190, 0.25));
  overflow: hidden;
}

.cmd-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.cmd-search-ico {
  color: var(--color-accent);
  font-size: 14px;
  opacity: 0.85;
}

.cmd-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--color-text-primary);
  font-size: 14px;
  font-family: inherit;
}

.cmd-input::placeholder {
  color: var(--color-text-secondary);
}

.cmd-esc-hint {
  font-size: 10px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  padding: 1px 5px;
  opacity: 0.8;
}

.cmd-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.cmd-group-title {
  padding: 6px 8px 2px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-secondary);
  opacity: 0.75;
}

.cmd-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  background: transparent;
  border: none;
  border-radius: var(--tile-radius-sm, 6px);
  color: var(--color-text-primary);
  font-size: 13px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

.cmd-item.is-active {
  background: var(--color-bg-hover);
  box-shadow: inset 0 0 0 1px rgba(32, 200, 255, 0.35);
}

.cmd-item.is-disabled {
  color: var(--color-text-secondary);
  opacity: 0.45;
  cursor: not-allowed;
}

.cmd-item-ico {
  width: 18px;
  text-align: center;
  font-size: 14px;
  flex: none;
}

.cmd-item-label {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.cmd-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cmd-item-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cmd-item-en {
  margin-left: 8px;
  font-size: 11px;
  color: var(--color-text-secondary);
  opacity: 0.7;
}

.cmd-item-shortcut {
  font-size: 10px;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: 4px;
  padding: 1px 5px;
  flex: none;
}

.cmd-empty {
  padding: 24px 12px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.cmd-footer {
  display: flex;
  gap: 14px;
  padding: 7px 12px;
  border-top: 1px solid var(--color-border-subtle);
  font-size: 11px;
  color: var(--color-text-secondary);
}

.cmd-footer b {
  color: var(--color-text-primary);
  font-weight: 600;
}

.cmd-fade-enter-active,
.cmd-fade-leave-active {
  transition: opacity 0.14s ease;
}

.cmd-fade-enter-from,
.cmd-fade-leave-to {
  opacity: 0;
}
</style>
