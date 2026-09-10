<template>
  <div class="modal-overlay connect-overlay" v-if="visible">
    <div class="modal connect-modal">
      <div class="brand-panel">
        <div class="brand-header">
          <div class="brand-logo-wrap">
            <img src="/icons/jarvis-logo.png" alt="Jarvis" class="brand-logo" />
          </div>
          <div class="brand-title">
            <h1>JARVIS</h1>
            <p>让 AI 从「独自工作」走向「与众共事」</p>
          </div>
        </div>
        <div class="quadrants">
          <div class="quadrant">
            <div class="quadrant-name">单人单 Agent</div>
            <div class="quadrant-value">独当一面</div>
            <div class="quadrant-cap">符号级代码理解 · 影响分析 · 无人值守 · 交叉验证</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">单人多 Agent</div>
            <div class="quadrant-value">一人驱动一个团队</div>
            <div class="quadrant-cap">编排网络 · Agent 间通信 · 多面板同屏操作</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">多人单 Agent</div>
            <div class="quadrant-value">团队共享一个 AI</div>
            <div class="quadrant-cap">多用户认证 · ACL 权限 · 共享协作 · 聊天室</div>
          </div>
          <div class="quadrant">
            <div class="quadrant-name">多人多 Agent</div>
            <div class="quadrant-value">分布式协作网络</div>
            <div class="quadrant-cap">多节点多网关 · 跨节点通信 · 节点级运维</div>
          </div>
        </div>
      </div>
      <div class="form-panel">
        <h2>连接到 Jarvis</h2>
        <div v-if="errorMessage" class="error-message">
          {{ errorMessage }}
        </div>
        <div class="form-group">
          <label>用户名</label>
          <input :value="username" @input="$emit('update:username', $event.target.value)" type="text" placeholder="输入用户名" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input :value="password" @input="$emit('update:password', $event.target.value)" type="password" placeholder="必填" @keydown.enter="$emit('connect')" />
        </div>
        <div class="form-group">
          <label>网关地址</label>
          <input :value="gatewayUrl" @input="$emit('update:gatewayUrl', $event.target.value)" placeholder="127.0.0.1:8000 或 ws://example.com:8080/ws" />
        </div>
        <button class="primary-btn" @click="$emit('connect')" :disabled="connecting">
          {{ connecting ? '连接中...' : '连接' }}
        </button>

        <div class="quickstart">
          <button class="quickstart-toggle" type="button" @click="showQuickStart = !showQuickStart">
            <span>快速开始：安装与部署</span>
            <span class="quickstart-arrow" :class="{ open: showQuickStart }">▾</span>
          </button>
          <div v-show="showQuickStart" class="quickstart-body">
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">1</span>安装 Jarvis</div>
              <pre class="qs-code"><code>bash -c "$(curl -fsSL https://raw.githubusercontent.com/skyfireitdiy/Jarvis/main/scripts/quick-install.sh)"</code></pre>
              <div class="qs-hint">国内用户可将域名替换为 gitee.com/skyfireitdiy/Jarvis</div>
            </div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">2</span>配置模型</div>
              <pre class="qs-code"><code>jqc</code></pre>
              <div class="qs-hint">交互式配置 API Key、模型与模型组</div>
            </div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">3</span>启动 Agent</div>
              <pre class="qs-code"><code>jvs   # 通用 Agent
jca   # 代码 Agent</code></pre>
              <div class="qs-hint">jvs 适合分析、规划、执行；jca 专攻读代码 / 改代码 / 跑验证</div>
            </div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">4</span>启动 Web 服务</div>
              <pre class="qs-code"><code>jarvis-service --gateway-password your_password</code></pre>
              <div class="qs-hint">默认监听 localhost:8000，可用 --host / --port 调整</div>
            </div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">5</span>连接</div>
              <div class="qs-hint">在右侧填写用户名 / 密码（即启动时的 gateway-password）与网关地址即可进入。</div>
            </div>

            <div class="qs-sub">分布式部署</div>
            <div class="topo">
              <div class="topo-node master">
                <div class="topo-node-title">Master 节点</div>
                <div class="topo-node-sub">统一入口 · 调度 · 多用户</div>
              </div>
              <div class="topo-links">
                <span class="topo-line"></span>
                <span class="topo-line"></span>
                <span class="topo-line"></span>
              </div>
              <div class="topo-children">
                <div class="topo-node child"><div class="topo-node-title">Child 1</div><div class="topo-node-sub">运行 Agent</div></div>
                <div class="topo-node child"><div class="topo-node-title">Child 2</div><div class="topo-node-sub">运行 Agent</div></div>
                <div class="topo-node child"><div class="topo-node-title">Child N</div><div class="topo-node-sub">运行 Agent</div></div>
              </div>
            </div>
            <div class="qs-hint">Master 提供统一入口并调度；Child 接入 Master 后在其上运行 Agent，可跨节点分发任务。</div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">M</span>Master：启动</div>
              <pre class="qs-code"><code>jarvis-service --node-mode master \\
  --gateway-host 0.0.0.0 --gateway-port 8000 \\
  --gateway-password your_password</code></pre>
              <div class="qs-hint">启动后在「设置 → 节点连接私钥」获取 node-secret</div>
            </div>
            <div class="qs-step">
              <div class="qs-step-title"><span class="qs-step-no">C</span>Child：接入</div>
              <pre class="qs-code"><code>jarvis-service --node-mode child \\
  --node-id worker-01 \\
  --master-url ws://master-host:8000 \\
  --node-secret your_secret_key</code></pre>
              <div class="qs-hint">node-id 需唯一；node-secret 与 Master 保持一致</div>
            </div>
            <div class="qs-hint"><b>切换模式</b>：通过 --node-mode 在 master / child 间切换（默认单机模式）；重新启动服务即生效。</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  visible: Boolean,
  connecting: Boolean,
  errorMessage: String,
  gatewayUrl: String,
  password: String,
  username: String
})

defineEmits(['update:visible', 'update:gatewayUrl', 'update:password', 'update:username', 'connect'])

const showQuickStart = ref(false)
</script>

<style scoped>
.modal-overlay.connect-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: var(--app-height, 100dvh);
  background: var(--color-bg-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  box-sizing: border-box;
  overflow: hidden;
  /* 向外扩出安全区，避免真机圆角/刘海处露出下层页面 */
  margin: calc(-1 * env(safe-area-inset-top, 0px)) calc(-1 * env(safe-area-inset-right, 0px))
          calc(-1 * env(safe-area-inset-bottom, 0px)) calc(-1 * env(safe-area-inset-left, 0px));
  padding: calc(20px + env(safe-area-inset-top, 0px)) calc(20px + env(safe-area-inset-right, 0px))
           calc(20px + env(safe-area-inset-bottom, 0px)) calc(20px + env(safe-area-inset-left, 0px));
}

/* 深空背景：径向光晕 + 网格纹理 */
.modal-overlay.connect-overlay::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 18% 22%, rgba(32, 200, 255, 0.16), transparent 45%),
    radial-gradient(circle at 82% 78%, rgba(54, 255, 124, 0.10), transparent 45%);
  pointer-events: none;
}

.modal-overlay.connect-overlay::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(32, 200, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(32, 200, 255, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(circle at 50% 50%, #000 0%, transparent 78%);
  -webkit-mask-image: radial-gradient(circle at 50% 50%, #000 0%, transparent 78%);
  pointer-events: none;
}

.modal {
  position: relative;
  z-index: 1;
  background: rgba(9, 16, 28, 0.86);
  border: 1px solid var(--color-border-subtle);
  border-radius: 16px;
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(32, 200, 255, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  width: 100%;
  max-width: 880px;
  display: flex;
  overflow: hidden;
  animation: cm-pop 0.42s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes cm-pop {
  from { opacity: 0; transform: translateY(14px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.brand-panel {
  flex: 1;
  min-width: 0;
  padding: 40px 34px;
  background:
    linear-gradient(160deg, rgba(32, 200, 255, 0.10) 0%, transparent 42%),
    rgba(6, 9, 17, 0.55);
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 30px;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-logo-wrap {
  position: relative;
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-logo-wrap::before {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(32, 200, 255, 0.35), transparent 68%);
  filter: blur(4px);
}

.brand-logo {
  position: relative;
  width: 46px;
  height: 46px;
  object-fit: contain;
  flex-shrink: 0;
  filter: drop-shadow(0 0 10px rgba(32, 200, 255, 0.55));
}

.brand-title h1 {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  letter-spacing: 0.14em;
  background: var(--gradient-accent);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
}

.brand-title p {
  margin: 6px 0 0 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.quadrants {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.quadrant {
  position: relative;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(18, 30, 50, 0.45);
  border: 1px solid var(--color-border-subtle);
  border-left: 2px solid var(--color-accent);
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease,
    background 0.2s ease;
}

.quadrant:hover {
  transform: translateX(3px);
  background: rgba(32, 200, 255, 0.08);
  border-color: var(--color-border);
  box-shadow: 0 6px 22px rgba(0, 120, 190, 0.22);
}

.quadrant-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.quadrant-value {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-success);
}

.quadrant-cap {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

.form-panel {
  width: 400px;
  flex-shrink: 0;
  padding: 40px 34px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-left: 1px solid var(--color-border-subtle);
  background: rgba(6, 9, 17, 0.35);
}

.connect-modal h2 {
  margin: 0 0 24px 0;
  font-size: 21px;
  font-weight: 600;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
}

.error-message {
  background: var(--color-error-subtle);
  border: 1px solid var(--color-error);
  border-radius: var(--tile-radius);
  padding: 12px;
  margin-bottom: 16px;
  color: var(--color-error);
  font-size: 14px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  letter-spacing: 0.01em;
}

.form-group input {
  width: 100%;
  padding: 11px 14px;
  background: rgba(6, 9, 17, 0.85);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius);
  color: var(--color-text-primary);
  font-size: 14px;
  box-sizing: border-box;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.form-group input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(32, 200, 255, 0.14);
}

.form-group input::placeholder {
  color: var(--color-text-secondary);
}

.primary-btn {
  width: 100%;
  padding: 11px 20px;
  background: var(--gradient-accent);
  border: none;
  border-radius: var(--tile-radius);
  color: #060911;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
  cursor: pointer;
  margin-top: 8px;
  box-shadow: 0 6px 20px rgba(32, 200, 255, 0.28);
  transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
}

.primary-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
  box-shadow: 0 10px 28px rgba(32, 200, 255, 0.4);
}

.primary-btn:active:not(:disabled) {
  transform: translateY(0);
}

.primary-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 快速开始 */
.quickstart {
  margin-top: 20px;
  border-top: 1px solid var(--color-border-subtle);
  padding-top: 14px;
}

.quickstart-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: transparent;
  border: none;
  padding: 4px 0;
  color: var(--color-accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.quickstart-arrow {
  transition: transform 0.2s ease;
}

.quickstart-arrow.open {
  transform: rotate(180deg);
}

.quickstart-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-height: 320px;
  overflow-y: auto;
  padding-right: 4px;
}

.qs-step-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 6px;
}

.qs-step-no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-accent-subtle);
  color: var(--color-accent);
  font-size: 11px;
  flex-shrink: 0;
}

.qs-code {
  margin: 0;
  padding: 9px 11px;
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--tile-radius-xs);
  overflow-x: auto;
}

.qs-code code {
  font-family: 'Consolas', 'Microsoft YaHei', monospace;
  font-size: 12px;
  color: var(--color-success);
  white-space: pre;
}

.qs-hint {
  margin-top: 5px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}

/* 分布式拓扑图 */
.qs-sub {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: 0.02em;
}

.topo {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 10px;
  border-radius: var(--tile-radius);
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid var(--color-border-subtle);
  overflow: hidden;
}

.topo-node {
  padding: 8px 14px;
  border-radius: 8px;
  text-align: center;
  min-width: 96px;
}

.topo-node-title {
  font-size: 12px;
  font-weight: 700;
}

.topo-node-sub {
  margin-top: 2px;
  font-size: 10px;
  color: var(--color-text-secondary);
}

.topo-node.master {
  background: var(--color-accent-subtle);
  border: 1px solid var(--color-accent);
  color: var(--color-accent);
  box-shadow: 0 0 0 0 rgba(32, 200, 255, 0.5);
  animation: topo-pulse 2.4s ease-in-out infinite;
}

.topo-node.child {
  background: rgba(18, 30, 50, 0.7);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-primary);
  animation: topo-fade-in 0.5s ease both;
}

.topo-node.child:nth-child(1) { animation-delay: 0.05s; }
.topo-node.child:nth-child(2) { animation-delay: 0.2s; }
.topo-node.child:nth-child(3) { animation-delay: 0.35s; }

.topo-links {
  display: flex;
  gap: 64px;
  height: 22px;
  align-items: flex-start;
}

.topo-line {
  width: 1px;
  height: 100%;
  background: linear-gradient(180deg, var(--color-accent), rgba(32, 200, 255, 0.15));
  transform-origin: top;
  animation: topo-flow 1.6s ease-in-out infinite;
}

.topo-line:nth-child(2) { animation-delay: 0.25s; }
.topo-line:nth-child(3) { animation-delay: 0.5s; }

.topo-children {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}

@keyframes topo-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(32, 200, 255, 0.45); }
  50% { box-shadow: 0 0 0 6px rgba(32, 200, 255, 0); }
}

@keyframes topo-flow {
  0%, 100% { opacity: 0.35; transform: scaleY(0.75); }
  50% { opacity: 1; transform: scaleY(1); }
}

@keyframes topo-fade-in {
  from { opacity: 0; transform: translateY(-6px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 768px) {
  .modal-overlay.connect-overlay {
    padding: calc(16px + env(safe-area-inset-top, 0px)) calc(16px + env(safe-area-inset-right, 0px))
             calc(16px + env(safe-area-inset-bottom, 0px)) calc(16px + env(safe-area-inset-left, 0px));
  }

  .modal {
    max-width: 480px;
    max-height: calc(var(--app-height, 100dvh) - 32px);
    overflow-y: auto;
    display: block;
  }

  .brand-panel {
    padding: 28px 24px;
    gap: 20px;
  }

  .quadrants {
    gap: 10px;
  }

  .quadrant-cap {
    display: none;
  }

  .form-panel {
    width: 100%;
    padding: 28px 24px;
    border-left: none;
    border-top: 1px solid var(--color-border-subtle);
  }
}

@media (prefers-reduced-motion: reduce) {
  .modal {
    animation: none;
  }

  .quadrant,
  .quickstart-arrow,
  .primary-btn {
    transition: none;
  }

  .topo-node.master,
  .topo-node.child,
  .topo-line {
    animation: none;
  }
}
</style>
