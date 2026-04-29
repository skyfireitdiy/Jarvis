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
  width: 100%;
}

.buffer-modal {
  max-width: min(720px, 100%);
  padding: 0;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.buffer-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(35, 134, 54, 0.1);
  border-bottom: 1px solid rgba(48, 54, 61, 0.6);
}

.buffer-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: #3fb950;
  display: flex;
  align-items: center;
  gap: 6px;
}

.buffer-panel-actions {
  display: flex;
  gap: 8px;
}

.buffer-panel-btn {
  padding: 6px 12px;
  background: rgba(48, 54, 61, 0.8);
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: 6px;
  color: #8b949e;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-panel-btn:hover {
  background: rgba(56, 139, 253, 0.15);
  border-color: rgba(56, 139, 253, 0.5);
  color: #58a6ff;
}

.buffer-panel-btn.close-btn:hover {
  background: rgba(248, 81, 73, 0.15);
  border-color: rgba(248, 81, 73, 0.5);
  color: #f85149;
}

.buffer-panel-content {
  padding: 0;
  display: flex;
  flex-direction: column;
}

.buffer-edit-textarea {
  width: 100%;
  min-height: 220px;
  max-height: min(60vh, 520px);
  background: rgba(13, 17, 23, 0.8);
  border: none;
  padding: 14px 16px;
  color: #e6edf3;
  font-size: 14px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  resize: vertical;
  box-sizing: border-box;
  outline: none;
}

.buffer-edit-textarea::placeholder {
  color: #8b949e;
}

.buffer-panel-footer {
  padding: 12px 16px;
  background: rgba(13, 17, 23, 0.6);
  border-top: 1px solid rgba(48, 54, 61, 0.6);
  display: flex;
  justify-content: flex-end;
}

.buffer-save-btn {
  padding: 8px 16px;
  background: rgba(56, 139, 253, 0.15);
  border: 1px solid rgba(56, 139, 253, 0.5);
  border-radius: 6px;
  color: #58a6ff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.buffer-save-btn:hover:not(:disabled) {
  background: rgba(56, 139, 253, 0.25);
  border-color: rgba(56, 139, 253, 0.8);
  transform: translateY(-1px);
}

.buffer-save-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>