<!-- 快捷键一览浮层：从动作注册表派生，展示分组 / 快捷键 / 功能 / 触发条件 -->
<template>
  <transition name="shortcut-fade">
    <div v-if="visible" class="shortcut-overlay" @click.self="close">
      <div class="shortcut-panel" role="dialog" aria-label="快捷键一览">
        <div class="shortcut-header">
          <div class="shortcut-title">
            <span class="shortcut-title-ico">⌨️</span>
            <span>快捷键一览</span>
            <span class="shortcut-sub">共 {{ total }} 个操作 · {{ groups.length }} 个分组</span>
          </div>
          <div class="shortcut-header-actions">
            <input
              v-model="query"
              class="shortcut-search"
              type="text"
              placeholder="搜索功能 / 快捷键…"
              spellcheck="false"
            />
            <button class="shortcut-close" title="关闭 (Esc)" @click="close">✕</button>
          </div>
        </div>

        <div class="shortcut-body">
          <div v-if="!groups.length" class="shortcut-empty">没有匹配的快捷键</div>
          <section v-for="g in groups" :key="g.group" class="shortcut-group">
            <div class="shortcut-group-title">{{ g.group }}</div>
            <table class="shortcut-table">
              <thead>
                <tr>
                  <th class="col-key">快捷键</th>
                  <th class="col-name">功能</th>
                  <th class="col-cond">触发条件 / 场景</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in g.actions" :key="a.id">
                  <td class="col-key">
                    <span class="shortcut-keys">
                      <kbd v-for="(k, i) in keyParts(a.shortcut)" :key="i">{{ k }}</kbd>
                    </span>
                  </td>
                  <td class="col-name">
                    <span class="shortcut-icon">{{ a.icon }}</span>
                    <span class="shortcut-label">{{ a.label }}</span>
                    <span v-if="a.en" class="shortcut-en">{{ a.en }}</span>
                  </td>
                  <td class="col-cond">{{ a.condition || '无特殊条件' }}</td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ACTIONS, groupActions } from '../actions/registry.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['update:visible', 'close'])

const query = ref('')

// 仅展示带快捷键的动作
// 同键动作（如 F2 在「当前 Agent」与「节点」两个场景复用）由注册表的 shortcutScope 区分：
// 一览表按 group 分组展示，各行的「触发条件 / 场景」列已说明适用场景，不会产生歧义。
const shortcutActions = computed(() => ACTIONS.filter(a => a && a.shortcut))

const total = computed(() => shortcutActions.value.length)

const groups = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = q
    ? shortcutActions.value.filter(a => {
        const haystack = [a.label, a.en, a.shortcut, a.condition, a.group, a.shortcutScope]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
        return haystack.includes(q)
      })
    : shortcutActions.value
  return groupActions(list)
})

// 把 "Ctrl+Alt+Shift+D" 拆成按键标签数组，便于逐个渲染 kbd
function keyParts(shortcut) {
  if (!shortcut) return []
  return String(shortcut)
    .split('+')
    .map(p => p.trim())
    .filter(Boolean)
}

function close() {
  emit('update:visible', false)
  emit('close')
}
</script>

<style scoped>
.shortcut-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(2, 6, 14, 0.72);
  backdrop-filter: blur(2px);
}
.shortcut-panel {
  display: flex;
  flex-direction: column;
  width: min(880px, 92vw);
  max-height: 86vh;
  background: var(--color-bg-panel, #0b1420);
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.22));
  border-radius: var(--tile-radius-md, 12px);
  box-shadow: 0 20px 60px rgba(0, 40, 80, 0.55);
  overflow: hidden;
}
.shortcut-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.18));
}
.shortcut-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #e6f4ff);
}
.shortcut-title-ico {
  font-size: 16px;
}
.shortcut-sub {
  font-size: 11px;
  font-weight: 400;
  color: var(--color-text-secondary, #8a9bb0);
}
.shortcut-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.shortcut-search {
  width: 200px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--color-text-primary, #e6f4ff);
  background: var(--color-bg-input, rgba(255, 255, 255, 0.05));
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.22));
  border-radius: var(--tile-radius-xs, 6px);
  outline: none;
}
.shortcut-search:focus {
  border-color: rgba(32, 200, 255, 0.6);
}
.shortcut-close {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.22));
  border-radius: var(--tile-radius-xs, 6px);
  background: transparent;
  color: var(--color-text-secondary, #8a9bb0);
  cursor: pointer;
  font-size: 12px;
}
.shortcut-close:hover {
  background: var(--color-bg-hover, rgba(255, 255, 255, 0.08));
  color: var(--color-text-primary, #e6f4ff);
}
.shortcut-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 16px 16px;
}
.shortcut-empty {
  padding: 32px 0;
  text-align: center;
  font-size: 12px;
  color: var(--color-text-secondary, #8a9bb0);
}
.shortcut-group {
  margin-top: 14px;
}
.shortcut-group-title {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 6px 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--color-text-secondary, #8a9bb0);
  background: var(--color-bg-panel, #0b1420);
}
.shortcut-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.shortcut-table th {
  text-align: left;
  font-weight: 500;
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--color-text-secondary, #8a9bb0);
  padding: 4px 8px;
  border-bottom: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.14));
}
.shortcut-table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--color-border-subtle, rgba(255, 255, 255, 0.05));
  color: var(--color-text-primary, #e6f4ff);
  vertical-align: middle;
}
.shortcut-table tr:hover td {
  background: var(--color-bg-hover, rgba(255, 255, 255, 0.04));
}
.col-key {
  width: 210px;
  white-space: nowrap;
}
.col-cond {
  width: 260px;
  color: var(--color-text-secondary, #8a9bb0);
}
.shortcut-keys {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.shortcut-keys kbd {
  display: inline-block;
  padding: 1px 6px;
  font-family: inherit;
  font-size: 11px;
  line-height: 1.6;
  color: var(--color-text-primary, #e6f4ff);
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--color-border-subtle, rgba(32, 200, 255, 0.3));
  border-bottom-width: 2px;
  border-radius: var(--tile-radius-xs, 6px);
}
.shortcut-icon {
  margin-right: 6px;
}
.shortcut-en {
  margin-left: 8px;
  font-size: 10px;
  color: var(--color-text-secondary, #8a9bb0);
}
.shortcut-fade-enter-active,
.shortcut-fade-leave-active {
  transition: opacity 0.16s ease;
}
.shortcut-fade-enter-from,
.shortcut-fade-leave-to {
  opacity: 0;
}
</style>
