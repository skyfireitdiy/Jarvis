<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal completions-modal">
      <div class="modal-header">
        <h3>插入补全</h3>
        <button class="icon-btn" @click="$emit('close')">✕</button>
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
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: var(--color-bg-secondary);
  border: 0.5px solid var(--color-border);
  border-radius: 14px;
  padding: 28px;
  width: 100%;
}

.completions-modal {
  max-width: 520px;
  max-height: 600px;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.icon-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.icon-btn:hover {
  color: var(--color-text-primary);
}

.completions-search {
  margin-bottom: 16px;
}

.completions-search input {
  width: 100%;
  padding: 12px 16px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.completions-search input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-primary);
}

.completions-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
  border: 0.5px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-bg-primary);
}

.completion-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border-bottom: 0.5px solid var(--color-border);
  cursor: pointer;
}

.completion-item:last-child {
  border-bottom: none;
}

.completion-item:hover {
  background: var(--color-accent-subtle);
}

.completion-item.selected {
  background: var(--color-accent-subtle);
}

.completion-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
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
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  text-align: center;
}
</style>