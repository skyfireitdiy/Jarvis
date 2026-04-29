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
  color: #e6edf3;
}

.close-btn {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
}

.close-btn:hover {
  color: #e6edf3;
}

.path-header {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.path-btn {
  flex: 1;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.1);
  color: #e6edf3;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.path-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.current-path {
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  color: #e6edf3;
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
  background: rgba(13, 17, 23, 0.8);
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  border-radius: 9px;
  color: #e6edf3;
  font-size: 14px;
}

.dir-search-input:focus {
  outline: none;
  border-color: rgba(88, 166, 255, 0.5);
  background: rgba(13, 17, 23, 0.9);
}

.dir-search-input::placeholder {
  color: #8b949e;
}

.dir-list {
  max-height: 350px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 8px;
  border: 0.5px solid rgba(255, 255, 255, 0.08);
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
  background: rgba(255, 255, 255, 0.05);
}

.dir-item.selected {
  background: rgba(63, 185, 80, 0.15);
  border-color: rgba(63, 185, 80, 0.3);
}

.dir-item.selected:hover {
  background: rgba(63, 185, 80, 0.2);
}

.dir-icon {
  font-size: 18px;
  margin-right: 12px;
}

.dir-name {
  font-size: 14px;
  color: #e6edf3;
  font-weight: 500;
}

.dir-path {
  font-size: 11px;
  color: #8b949e;
  margin-left: auto;
  word-break: break-all;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: #8b949e;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.btn {
  padding: 10px 20px;
  border: 0.5px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.btn.secondary {
  background: transparent;
  color: #8b949e;
}

.btn.secondary:hover {
  background: rgba(255, 255, 255, 0.05);
  color: #e6edf3;
}

.btn.primary {
  background: #238636;
  color: #ffffff;
}

.btn.primary:hover {
  background: #2ea043;
}
</style>