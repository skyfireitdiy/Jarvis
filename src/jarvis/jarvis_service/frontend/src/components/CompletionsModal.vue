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