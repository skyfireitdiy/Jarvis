<!-- 流水线编排大图浮层（点击侧边栏/活动栏「编排查看」的展开按钮打开）。
     结构参照 TopologyOverlay：遮罩 + 面板 + Esc 关闭 + visible prop。 -->
<template>
  <transition name="orch-fade">
    <div v-if="visible" class="orch-overlay" @click.self="close">
      <div class="orch-panel" role="dialog" aria-label="编排查看">
        <div class="orch-header">
          <div class="orch-title">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="3.5" cy="4" r="1.6" stroke="currentColor" stroke-width="1.4"/>
              <circle cx="12.5" cy="4" r="1.6" stroke="currentColor" stroke-width="1.4"/>
              <circle cx="8" cy="12.5" r="1.6" stroke="currentColor" stroke-width="1.4"/>
              <path d="M4.6 5.1 7.1 11.2M11.4 5.1 8.9 11.2M5.1 4h5.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
            <span>编排查看</span>
          </div>
          <button class="orch-close" title="关闭 (Esc)" @click="close">✕</button>
        </div>
        <div class="orch-body">
          <OrchestrationView
            :pipelines="pipelines"
            :activeId="activeId"
            mode="full"
            @select="$emit('select', $event)"
            @jump-agent="$emit('jump-agent', $event)"
          />
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import OrchestrationView from './OrchestrationView.vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  pipelines: { type: Array, default: () => [] },
  activeId: { type: String, default: '' },
})

const emit = defineEmits(['update:visible', 'close', 'select', 'jump-agent'])

function close() {
  emit('update:visible', false)
  emit('close')
}

function onKeydown(e) {
  if (e.key === 'Escape' && props.visible) {
    e.stopPropagation()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.orch-overlay {
  position: fixed;
  inset: 0;
  z-index: 2600;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 8, 16, 0.72);
  backdrop-filter: blur(3px);
}
.orch-panel {
  width: min(92vw, 1400px);
  height: min(88vh, 900px);
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  overflow: hidden;
  background: rgba(10, 16, 26, 0.98);
  border: 1px solid rgba(32, 200, 255, 0.28);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.6), 0 0 40px rgba(32, 200, 255, 0.12);
}
.orch-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(90, 120, 160, 0.22);
  color: #d8e2f0;
}
.orch-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; color: #eaf6ff; }
.orch-close {
  width: 28px; height: 28px;
  border-radius: 8px;
  border: 1px solid rgba(90, 120, 160, 0.28);
  background: rgba(20, 30, 46, 0.7);
  color: #9db0c8;
  cursor: pointer;
}
.orch-close:hover { color: #ff5d6c; border-color: rgba(255, 93, 108, 0.5); }
.orch-body { flex: 1; min-height: 0; }

.orch-fade-enter-active, .orch-fade-leave-active { transition: opacity 0.18s ease; }
.orch-fade-enter-from, .orch-fade-leave-to { opacity: 0; }
</style>
