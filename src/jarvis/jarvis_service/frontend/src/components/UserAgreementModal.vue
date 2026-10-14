<template>
  <!-- 用户协议弹窗（首次打开前端页面时展示；不同意则不能使用软件） -->
  <div
    v-if="visible"
    class="user-agreement-overlay modal-overlay"
  >
    <div class="user-agreement-modal">
      <div class="user-agreement-header">
        <h2>用户协议</h2>
      </div>
      <div class="user-agreement-body">
        <p class="user-agreement-warning">
          <strong>重要提示：</strong>Jarvis 是一个具有<strong>较高权限</strong>的 Agent 系统，它可以读取、创建、修改甚至删除您机器上的文件，执行终端命令，访问网络，以及调度其他 Agent 完成各类任务。请在使用前仔细阅读并理解本协议。
        </p>
        <ol class="user-agreement-list">
          <li>
            <strong>权限与能力</strong>：本系统具备文件读写、命令执行、网络访问、进程管理、浏览器控制、后台服务调度等较高权限能力。您授予系统在您指定的工作目录与范围内执行这些操作的权限。
          </li>
          <li>
            <strong>使用风险</strong>：系统执行的操作由您本人或您授权的 Agent 发起，操作结果可能对您的文件、数据与系统产生不可逆影响。请确保您了解并接受由此产生的风险。
          </li>
          <li>
            <strong>第三方内容</strong>：系统支持安装第三方插件、接入第三方服务与脚本。这些内容的可靠性、安全性与合法性由提供方负责，本系统仅提供运行环境，不对其造成的任何损失承担责任。
          </li>
          <li>
            <strong>责任声明</strong>：因使用本系统（包括但不限于误操作、插件缺陷、恶意脚本、网络异常）导致的任何直接或间接损失，本系统作者与维护者不承担法律责任。
          </li>
          <li>
            <strong>数据与隐私</strong>：您应妥善保管您的账号凭据与 Token。请勿将敏感信息（如密码、密钥）明文输入到系统对话中，除非您明确信任当前会话的 Agent 与运行环境。
          </li>
          <li>
            <strong>合规使用</strong>：您承诺不将本系统用于任何违反法律法规、侵犯他人权益或危害网络安全的用途。因违规使用产生的一切后果由您自行承担。
          </li>
        </ol>
        <p class="user-agreement-footer">
          点击下方「同意并继续」即表示您已阅读、理解并同意本协议的全部内容。
        </p>
      </div>
      <div class="user-agreement-actions">
        <button
          class="btn primary user-agreement-agree"
          @click="$emit('agree')"
        >
          同意并继续
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
})
defineEmits(['agree'])
</script>

<style scoped>
.user-agreement-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  /* 高于 ConnectModal(9999) 与所有现有弹窗，保证协议必须最先处理 */
  z-index: 10001;
}

.user-agreement-modal {
  width: min(640px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-color, #1e1e2e);
  color: var(--text-color, #e6e6e6);
  border: 1px solid var(--border-color, #3a3a4a);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.user-agreement-header {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-color, #3a3a4a);
}

.user-agreement-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-color, #e6e6e6);
}

.user-agreement-body {
  padding: 18px 24px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
}

.user-agreement-warning {
  padding: 12px 14px;
  margin: 0 0 16px;
  background: rgba(255, 193, 7, 0.12);
  border-left: 4px solid #ffc107;
  border-radius: 6px;
  color: var(--text-color, #e6e6e6);
}

.user-agreement-list {
  margin: 0;
  padding-left: 20px;
}

.user-agreement-list li {
  margin-bottom: 10px;
}

.user-agreement-footer {
  margin: 16px 0 0;
  color: var(--text-muted, #9a9aa8);
  font-size: 12px;
}

.user-agreement-actions {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color, #3a3a4a);
  display: flex;
  justify-content: flex-end;
}

.user-agreement-agree {
  min-width: 140px;
}
</style>
