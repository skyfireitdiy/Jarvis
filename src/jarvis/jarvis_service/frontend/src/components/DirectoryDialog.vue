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