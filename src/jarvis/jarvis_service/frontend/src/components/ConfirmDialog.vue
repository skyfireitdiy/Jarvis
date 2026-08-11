<template>
  <div v-if="visible" class="modal-overlay">
    <div class="confirm-modal">
      <p class="confirm-message">{{ message }}</p>
      <div class="confirm-actions">
        <template v-if="defaultConfirm">
          <button ref="cancelBtnRef" class="ghost-btn" @click="handleCancel">取消</button>
          <button ref="confirmBtnRef" class="ghost-btn default" @click="handleConfirm">确认</button>
        </template>
        <template v-else>
          <button ref="confirmBtnRef" class="ghost-btn" @click="handleConfirm">确认</button>
          <button ref="cancelBtnRef" class="ghost-btn default" @click="handleCancel">取消</button>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  message: {
    type: String,
    default: ''
  },
  defaultConfirm: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['confirm', 'cancel', 'update:visible'])

const confirmBtnRef = ref(null)
const cancelBtnRef = ref(null)

function handleConfirm() {
  emit('confirm')
  emit('update:visible', false)
}

function handleCancel() {
  emit('cancel')
  emit('update:visible', false)
}

function handleKeydown(event) {
  if (!props.visible) return

  if (event.key === 'Enter') {
    const isDefaultConfirm = confirmBtnRef.value?.classList.contains('default')
    if (isDefaultConfirm) {
      handleConfirm()
    } else {
      handleCancel()
    }
  } else if (event.key === 'y' || event.key === 'Y') {
    handleConfirm()
  } else if (event.key === 'n' || event.key === 'N') {
    handleCancel()
  }
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    document.addEventListener('keydown', handleKeydown)
    nextTick(() => {
      if (props.defaultConfirm && confirmBtnRef.value) {
        confirmBtnRef.value.focus()
      } else if (!props.defaultConfirm && cancelBtnRef.value) {
        cancelBtnRef.value.focus()
      }
    })
  } else {
    document.removeEventListener('keydown', handleKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2100 !important;
}

.confirm-modal {
  background: var(--bg-secondary, #1e1e2e);
  color: var(--text-primary, #cdd6f4);
  border-radius: 12px;
  padding: 24px;
  min-width: 320px;
  max-width: 480px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.confirm-message {
  margin: 0 0 16px 0;
  color: var(--text-primary, #cdd6f4);
  font-size: 14px;
  line-height: 1.5;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.ghost-btn {
  padding: 8px 18px;
  border-radius: 6px;
  border: 1px solid var(--border-color, #45475a);
  background: none;
  color: var(--text-primary, #cdd6f4);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.ghost-btn:hover {
  background: rgba(137, 180, 250, 0.1);
  border-color: var(--accent, #89b4fa);
}

.ghost-btn.default {
  background: #238636;
  border-color: #238636;
  color: white;
  font-weight: 600;
}

.ghost-btn.default:hover {
  background: #2ea043;
  border-color: #2ea043;
}
</style>