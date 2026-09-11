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
            :placeholder="title"
            autocomplete="off"
            spellcheck="false"
            @keydown="onInputKeydown"
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
                <span class="cmd-item-label">{{ entry.action.label }}<span v-if="entry.action.en" class="cmd-item-en">{{ entry.action.en }}</span></span>
                <span v-if="entry.action.shortcut" class="cmd-item-shortcut">{{ entry.action.shortcut }}</span>
              </button>
            </div>
          </template>
          <div v-else class="cmd-empty">无匹配命令</div>
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
import { computed, nextTick, ref, watch } from 'vue'
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
  return typeof action.enabled === 'function' ? !action.enabled(props.ctx || {}) : false
}

// 过滤 + 扁平化（用连续索引做键盘导航，与分组展示解耦）
const flatEntries = computed(() => {
  let flatIndex = 0
  return filterActions(props.actions, query.value).map(action => ({
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

function onInputKeydown(event) {
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
