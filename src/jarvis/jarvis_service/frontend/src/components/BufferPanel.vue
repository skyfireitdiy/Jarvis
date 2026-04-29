<template>
  <div class="modal-overlay" v-if="visible && hasBufferedInput" @click.self="$emit('close')">
    <div class="modal buffer-modal">
      <div class="buffer-panel-header">
        <span class="buffer-panel-title">📝 输入缓存</span>
        <div class="buffer-panel-actions">
          <button
            class="buffer-panel-btn"
            @click="$emit('load')"
            title="加载到输入框"
          >
            ↙ 加载
          </button>
          <button
            class="buffer-panel-btn"
            @click="$emit('clear')"
            title="清空缓存"
          >
            🗑
          </button>
          <button
            class="buffer-panel-btn close-btn"
            @click="$emit('close')"
            title="关闭面板"
          >
            ✕
          </button>
        </div>
      </div>
      <div class="buffer-panel-content">
        <textarea
          :value="editText"
          @input="$emit('update:editText', $event.target.value)"
          class="buffer-edit-textarea"
          placeholder="缓存内容..."
          @keydown.ctrl.enter="$emit('save')"
        ></textarea>
        <div class="buffer-panel-footer">
          <button
            class="buffer-save-btn"
            @click="$emit('save')"
            :disabled="!editText.trim()"
          >
            保存修改 (Ctrl+Enter)
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: Boolean,
  hasBufferedInput: Boolean,
  editText: {
    type: String,
    default: ''
  }
})

defineEmits(['update:visible', 'update:editText', 'close', 'load', 'clear', 'save'])
</script>