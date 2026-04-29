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
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal {
  background: rgba(22, 27, 34, 0.95);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
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
  color: #e6edf3;
}

.icon-btn {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.icon-btn:hover {
  color: #e6edf3;
}

.completions-search {
  margin-bottom: 16px;
}

.completions-search input {
  width: 100%;
  padding: 12px 16px;
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.completions-search input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
}

.completions-list {
  flex: 1;
  overflow-y: auto;
  max-height: 400px;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  background: rgba(13, 17, 23, 0.6);
}

.completion-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
}

.completion-item:last-child {
  border-bottom: none;
}

.completion-item:hover {
  background: rgba(88, 166, 255, 0.1);
}

.completion-item.selected {
  background: rgba(88, 166, 255, 0.25);
}

.completion-value {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
  font-family: 'SF Mono', Monaco, Consolas, 'Courier New', monospace;
}

.completion-desc {
  font-size: 12px;
  color: #8b949e;
}

.completion-item.completion-replace .completion-desc {
  color: #58a6ff;
}

.completion-item.completion-command .completion-desc {
  color: #d29922;
}

.completion-item.completion-rule .completion-desc {
  color: #3fb950;
}

.completion-empty {
  padding: 24px;
  text-align: center;
  color: #8b949e;
  font-size: 14px;
}

.error-message {
  background-color: #f85149;
  color: white;
  padding: 12px 16px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  text-align: center;
}
</style>