<template>
  <div class="palette-overlay" v-if="visible">
    <div class="palette-panel dir-modal">
      <div class="dir-modal-header">
        <h2>选择工作目录</h2>
        <button class="dir-close-btn" @click="$emit('cancel')">×</button>
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
      <div class="dir-list" ref="dirListRef" v-if="filteredDirs.length > 0">
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
      <div class="dir-modal-actions">
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
const dirListRef = ref(null)

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
  dirListRef
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

.dir-modal {
  max-width: 700px;
  width: 95%;
  max-height: 72vh;
  display: flex;
  flex-direction: column;
}

.dir-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.dir-modal-header h2 {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-primary);
  font-weight: 600;
}

.dir-close-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}

.dir-close-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.path-header {
  display: flex;
  gap: 8px;
  padding: 8px 12px 0;
}

.path-btn {
  flex: 1;
  padding: 6px 10px;
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-sm);
  font-size: 12px;
  cursor: pointer;
}

.path-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-hover);
}

.current-path {
  margin: 8px 12px 0;
  padding: 7px 10px;
  background: var(--color-bg-primary);
  border-radius: var(--tile-radius-sm);
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
  word-break: break-all;
  line-height: 1.4;
}

.dir-search {
  padding: 8px 12px;
}

.dir-search-input {
  width: 100%;
  padding: 7px 10px;
  background: transparent;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-sm);
  color: var(--color-text-primary);
  font-size: 13px;
  font-family: inherit;
}

.dir-search-input:focus {
  outline: none;
  border-color: rgba(32, 200, 255, 0.35);
}

.dir-search-input::placeholder {
  color: var(--color-text-secondary);
}

.dir-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
}

.dir-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  cursor: pointer;
  border-radius: var(--tile-radius-sm);
  color: var(--color-text-primary);
  font-size: 13px;
}

.dir-item:hover {
  background: var(--color-bg-hover);
}

.dir-item.selected {
  background: var(--color-bg-hover);
  box-shadow: inset 0 0 0 1px rgba(32, 200, 255, 0.35);
}

.dir-item.selected:hover {
  background: var(--color-bg-hover);
}

.dir-icon {
  font-size: 14px;
  width: 18px;
  text-align: center;
  flex: none;
}

.dir-name {
  font-size: 13px;
  color: var(--color-text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dir-path {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-left: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 55%;
}

.empty-state {
  text-align: center;
  padding: 24px 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.dir-modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 10px 12px;
  border-top: 1px solid var(--color-border-subtle);
}

.btn {
  padding: 7px 16px;
  border: none;
  border-radius: var(--tile-radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn.secondary {
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-subtle);
}

.btn.secondary:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.btn.primary {
  background: var(--color-accent);
  color: #060911;
}

.btn.primary:hover {
  background: var(--color-accent);
  filter: brightness(1.08);
}
</style>