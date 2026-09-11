<template>
  <div class="palette-overlay" v-if="visible">
    <div class="palette-panel completions-modal">
      <div class="completions-modal-header">
        <h3>插入补全</h3>
        <button class="completions-close-btn" @click="$emit('close')">✕</button>
      </div>
      <div class="completions-search">
        <input
          type="text"
          :value="searchText"
          @input="$emit('update:searchText', $event.target.value)"
          placeholder="搜索补全..."
          ref="searchInput"
          @keydown="$emit('keydown', $event)"
        />
      </div>
      <div class="completions-list" ref="listRef">
        <div
          v-for="(item, index) in filteredCompletions"
          :key="index"
          :ref="el => { if (el) itemRefs[index] = el }"
          class="completion-item"
          :class="[`completion-${item.type}`, { 'selected': selectedIndex === index }]"
          @click="$emit('select', item)"
        >
          <div class="completion-value">{{ item.display }}</div>
          <div class="completion-desc">{{ item.description }}</div>
        </div>
        <div v-if="filteredCompletions.length === 0" class="completion-empty">
          没有找到匹配的补全
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  visible: Boolean,
  searchText: String,
  filteredCompletions: {
    type: Array,
    default: () => []
  },
  selectedIndex: {
    type: Number,
    default: -1
  }
})

const emit = defineEmits(['update:visible', 'update:searchText', 'close', 'select', 'keydown'])

const searchInput = ref(null)
const listRef = ref(null)
const itemRefs = ref([])

watch(() => props.visible, (newVal) => {
  if (newVal) {
    setTimeout(() => {
      searchInput.value?.focus()
    }, 100)
  }
})

// 暴露refs供父组件使用
defineExpose({
  searchInput,
  listRef,
  itemRefs
})
</script>

<style scoped>
.palette-overlay {
  position: fixed;
  inset: 0;
  background: rgba(4, 8, 16, 0.55);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  z-index: 3000;
  padding: 12vh 20px 20px;
}

.palette-panel {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  box-shadow: var(--tile-shadow, 0 8px 30px rgba(0, 120, 190, 0.25));
  overflow: hidden;
  width: 100%;
}

.completions-modal {
  max-width: 520px;
  max-height: 62vh;
  display: flex;
  flex-direction: column;
}

.completions-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.completions-modal-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.completions-close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}

.completions-close-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.completions-search {
  padding: 8px 12px;
}

.completions-search input {
  width: 100%;
  padding: 7px 10px;
  background: transparent;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-sm);
  color: var(--color-text-primary);
  font-size: 13px;
  font-family: inherit;
}

.completions-search input:focus {
  outline: none;
  border-color: rgba(32, 200, 255, 0.35);
}

.completions-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
}

.completion-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 10px;
  border-radius: var(--tile-radius-sm);
  cursor: pointer;
}

.completion-item:hover {
  background: var(--color-bg-hover);
}

.completion-item.selected {
  background: var(--color-bg-hover);
  box-shadow: inset 0 0 0 1px rgba(32, 200, 255, 0.35);
}

.completion-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
}

.completion-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.completion-item.completion-replace .completion-desc {
  color: var(--color-accent);
}

.completion-item.completion-command .completion-desc {
  color: var(--color-warning);
}

.completion-item.completion-rule .completion-desc {
  color: var(--color-success);
}

.completion-empty {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 14px;
}

.error-message {
  background-color: var(--color-error);
  color: var(--color-text-primary);
  padding: 12px 16px;
  border-radius: var(--tile-radius-xs);
  margin-bottom: 16px;
  font-size: 14px;
  text-align: center;
}
</style>