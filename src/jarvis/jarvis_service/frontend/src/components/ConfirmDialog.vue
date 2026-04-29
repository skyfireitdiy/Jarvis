<template>
  <article v-if="visible" class="message message-confirm">
    <div class="confirm-box">
      <p class="confirm-message">{{ message }}</p>
      <div class="confirm-actions">
        <template v-if="defaultConfirm">
          <button ref="cancelBtnRef" class="confirm-btn" @click="handleCancel">取消</button>
          <button ref="confirmBtnRef" class="confirm-btn default" @click="handleConfirm">确认</button>
        </template>
        <template v-else>
          <button ref="confirmBtnRef" class="confirm-btn" @click="handleConfirm">确认</button>
          <button ref="cancelBtnRef" class="confirm-btn default" @click="handleCancel">取消</button>
        </template>
      </div>
    </div>
  </article>
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
.message-confirm {
  background: rgba(33, 38, 45, 0.85);
  border: 0.5px solid rgba(88, 166, 255, 0.3);
}

.confirm-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.confirm-message {
  margin: 0;
  color: #e6edf3;
  font-size: 13px;
}

.confirm-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.confirm-btn {
  padding: 9px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 0.5px solid rgba(255, 255, 255, 0.1);
  background: rgba(33, 38, 45, 0.8);
  color: #e6edf3;
}

.confirm-btn:hover {
  background: rgba(48, 54, 61, 0.9);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-1px);
}

.confirm-btn.default {
  background: #238636;
  border-color: rgba(255, 255, 255, 0.2);
  font-weight: 700;
}

.confirm-btn.default:hover {
  background: #2ea043;
  border-color: rgba(255, 255, 255, 0.25);
}
</style>
