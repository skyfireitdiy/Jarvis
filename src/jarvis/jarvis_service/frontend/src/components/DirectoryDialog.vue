<template>
  <div class="modal-overlay" v-if="visible">
    <div class="modal dir-modal">
      <div class="modal-header">
        <h2>选择工作目录</h2>
        <button class="close-btn" @click="$emit('cancel')">×</button>
      </div>
      <div class="path-header">
        <button class="path-btn" @click="$emit('refresh', currentPath)">🔄 刷新</button>
        <button class="path-btn" @click="$emit('go-parent')">⬆</button>
      </div>
      <div class="current-path">{{ currentPath }}</div>
      <div class="dir-search">
        <input
          ref="searchInput"
          :value="searchText"
          @input="$emit('update:searchText', $event.target.value)"
          type="text"
          class="dir-search-input"
          placeholder="🔍 搜索目录..."
          @keydown="$emit('search-keydown', $event)"
        />
      </div>
      <div class="dir-list" v-if="filteredDirs.length > 0">
        <div
          v-for="dir in filteredDirs"
          :key="dir.path"
          class="dir-item"
          :class="{ selected: selectedDir === dir.path }"
          @click="$emit('select', dir.path); $emit('enter', dir.path, false)"
        >
          <div class="dir-icon">📁</div>
          <div class="dir-name">{{ dir.name }}</div>
          <div class="dir-path">{{ dir.path }}</div>
        </div>
      </div>
      <div class="empty-state" v-else>
        <p>该目录下没有子目录</p>
      </div>
      <div class="modal-actions">
        <button class="btn secondary" @click="$emit('cancel')">取消</button>
        <button class="btn primary" @click="$emit('confirm')">确认</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  visible: Boolean,
  currentPath: String,
  selectedDir: String,
  searchText: String,
  filteredDirs: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:visible', 'update:searchText', 'cancel', 'confirm', 'refresh', 'go-parent', 'select', 'enter', 'search-keydown'])

const searchInput = ref(null)

watch(() => props.visible, (newVal) => {
  if (newVal) {
    setTimeout(() => {
      searchInput.value?.focus()
    }, 100)
  }
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

.dir-modal {
  max-width: 700px;
  width: 95%;
  min-height: 500px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--color-text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.close-btn:hover {
  color: var(--color-text-primary);
}

.path-header {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.path-btn {
  flex: 1;
  padding: 8px 12px;
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.path-btn:hover {
  background: var(--color-bg-tertiary);
  transform: translateY(-1px);
}

.current-path {
  padding: 12px 14px;
  background: var(--color-bg-primary);
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  color: var(--color-text-primary);
  margin-bottom: 16px;
  word-break: break-all;
  line-height: 1.4;
}

.dir-search {
  margin-bottom: 16px;
}

.dir-search-input {
  width: 100%;
  padding: 12px 16px;
  background: var(--color-bg-primary);
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  color: var(--color-text-primary);
  font-size: 14px;
}

.dir-search-input:focus {
  outline: none;
  border-color: var(--color-accent);
  background: var(--color-bg-primary);
}

.dir-search-input::placeholder {
  color: var(--color-text-secondary);
}

.dir-list {
  max-height: 350px;
  overflow-y: auto;
  background: var(--color-bg-primary);
  border-radius: 8px;
  border: 0.5px solid var(--color-border);
  margin-bottom: 20px;
}

.dir-item {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  cursor: pointer;
  border-radius: 6px;
  margin: 4px;
}

.dir-item:hover {
  background: var(--color-bg-tertiary);
}

.dir-item.selected {
  background: var(--color-accent-subtle);
  border-color: var(--color-accent);
}

.dir-item.selected:hover {
  background: var(--color-accent-subtle);
}

.dir-icon {
  font-size: 18px;
  margin-right: 12px;
}

.dir-name {
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 500;
}

.dir-path {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-left: auto;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: var(--color-text-secondary);
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn {
  padding: 10px 20px;
  border: 0.5px solid var(--color-border);
  border-radius: 9px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.btn.secondary {
  background: transparent;
  color: var(--color-text-secondary);
}

.btn.secondary:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.btn.primary {
  background: var(--color-success);
  color: var(--color-text-primary);
}

.btn.primary:hover {
  background: var(--color-success);
}
</style>