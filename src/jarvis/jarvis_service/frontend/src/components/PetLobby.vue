<template>
  <div class="pet-lobby" ref="stageRef" @click="onStageClick">
    <!-- 地板风格背景 -->
    <div class="pet-lobby-floor"></div>
    <!-- 地板上的 Slogan：做旧、斑驳的沧桑质感 -->
    <div class="pet-lobby-slogan" aria-hidden="true">
      <span class="pet-lobby-slogan-text">独当一面，与众共事</span>
    </div>
    <div class="pet-lobby-glow pet-lobby-glow-a"></div>
    <div class="pet-lobby-glow pet-lobby-glow-b"></div>

    <!-- 左上角：网关信息仪表（时间 + 连接状态 + 网关地址 + 节点 + 用户），风格与节点拓扑一致，不拦截交互 -->
    <div class="pet-lobby-dash" aria-hidden="true">
      <div class="lobby-dash-time">{{ dashTime }}</div>
      <div class="lobby-dash-date">{{ dashDate }}</div>
      <div class="lobby-dash-divider"></div>
      <div class="lobby-dash-row">
        <span class="lobby-dash-dot" :class="'is-' + connectionStatus"></span>
        <span class="lobby-dash-label">{{ connectionLabel || '未知' }}</span>
      </div>
      <div class="lobby-dash-row">
        <span class="lobby-dash-label">网关</span>
        <span class="lobby-dash-value">{{ gatewayAddress || '—' }}</span>
      </div>
      <div class="lobby-dash-row">
        <span class="lobby-dash-label">节点</span>
        <span class="lobby-dash-value">{{ nodeOnlineStat.online }}/{{ nodeOnlineStat.total }}</span>
      </div>
      <div v-if="agentStatusStat.length" class="lobby-dash-row">
        <span class="lobby-dash-label">Agent</span>
        <span class="lobby-dash-agents">
          <span v-for="s in agentStatusStat" :key="s.state" class="lobby-dash-agent-item" :title="s.label">
            <span class="lobby-dash-agent-dot" :style="{ background: s.color }"></span>
            <span class="lobby-dash-agent-num">{{ s.count }}</span>
          </span>
        </span>
      </div>
      <div v-if="currentUserName" class="lobby-dash-row">
        <span class="lobby-dash-label">用户</span>
        <span class="lobby-dash-value">{{ currentUserName }}</span>
      </div>
    </div>

    <!-- 节点与连线层：参考大屏「网络拓扑」风格（机箱造型 + 连线），位于地板之上、宠物之下 -->
    <div class="pet-lobby-topology" aria-hidden="true">
      <svg class="pet-lobby-links" :width="stageSize.w" :height="stageSize.h" :viewBox="`0 0 ${stageSize.w} ${stageSize.h}`">
        <defs>
          <linearGradient id="lobby-line" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#20c8ff" stop-opacity="0.9" />
            <stop offset="100%" stop-color="#20c8ff" stop-opacity="0.25" />
          </linearGradient>
          <linearGradient id="lobby-center-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#e8d089" />
            <stop offset="100%" stop-color="#c99a34" />
          </linearGradient>
          <filter id="lobby-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="2.4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <!-- 连线：master → 各节点 -->
        <g class="lobby-links-master">
          <line
            v-for="link in nodeLinks"
            :key="link.key"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :stroke="link.offline ? 'rgba(255,93,108,0.35)' : 'url(#lobby-line)'"
            :stroke-width="1.6"
            :stroke-dasharray="link.offline ? '6 5' : ''"
            class="lobby-link"
            :class="{ 'is-flow': !link.offline }"
          />
        </g>

        <!-- 连线：Agent 宠物 → 其所属节点（随宠物移动实时更新） -->
        <g class="lobby-links-agent">
          <line
            v-for="link in agentLinks"
            :key="link.key"
            :x1="link.x1"
            :y1="link.y1"
            :x2="link.x2"
            :y2="link.y2"
            :stroke="link.color"
            stroke-width="1"
            stroke-dasharray="3 3"
            opacity="0.7"
          />
        </g>

        <!-- 节点：服务器机箱造型（master 金色居中，其余按状态着色） -->
        <g
          v-for="n in nodeItems"
          :key="n.node_id"
          class="lobby-node"
          :class="['st-' + n.state, { 'is-center': n.isMaster, active: n.active }]"
          @click.stop="onNodeClick(n)"
          @contextmenu.prevent.stop="onNodeContextMenu(n, $event)"
        >
          <!-- 机箱主体 -->
          <rect
            :x="n.x - n.rw"
            :y="n.y - n.rh"
            :width="n.rw * 2"
            :height="n.rh * 2"
            rx="6"
            :fill="n.fill"
            :stroke="n.color"
            :stroke-width="n.isMaster ? 1.6 : 1.3"
            class="lobby-node-body"
          />
          <!-- 顶部插槽 -->
          <line
            :x1="n.x - n.rw + 6" :y1="n.y - n.rh + 7"
            :x2="n.x + n.rw - 6" :y2="n.y - n.rh + 7"
            :stroke="n.color" stroke-width="1.4" opacity="0.6"
          />
          <!-- 散热格栅 -->
          <line
            v-for="k in 3" :key="'g' + k"
            :x1="n.x - n.rw + 8" :y1="n.y - n.rh + 6 + k * 4.6"
            :x2="n.x + n.rw - 16" :y2="n.y - n.rh + 6 + k * 4.6"
            :stroke="n.color" stroke-width="1" opacity="0.35"
          />
          <!-- 指示灯 -->
          <circle :cx="n.x + n.rw - 10" :cy="n.y - 2" r="2.4" :fill="n.color" class="lobby-node-led" />
          <circle :cx="n.x + n.rw - 10" :cy="n.y + 5" r="2.4" :fill="n.color" opacity="0.4" />
          <!-- 底部状态条 -->
          <rect
            :x="n.x - n.rw + 6" :y="n.y + n.rh - 8"
            :width="n.rw * 2 - 12" :height="3" rx="1.5"
            :fill="n.color" opacity="0.5"
          />
          <text :x="n.x" :y="n.y + n.rh + 16" text-anchor="middle" class="lobby-node-label">{{ n.short }}</text>
          <text :x="n.x" :y="n.y + n.rh + 29" text-anchor="middle" class="lobby-node-count">{{ n.agentCount }} agent</text>
          <text
            v-if="n.version"
            :x="n.x"
            :y="n.y + n.rh + 41"
            text-anchor="middle"
            class="lobby-node-version"
            :class="{ mismatch: n.versionMismatch }"
          >{{ n.version }}</text>
        </g>
      </svg>
    </div>

    <!-- 右上角：游走开关 + 精灵显示模式开关 -->
    <div class="pet-lobby-toggles">
      <button
        class="pet-lobby-roam-toggle"
        :class="{ off: !roaming }"
        :title="roaming ? '点击停止宠物游走' : '点击开启宠物游走'"
        @click.stop="roaming = !roaming"
      >
        <span class="pet-lobby-roam-icon">{{ roaming ? '🔄' : '⏸' }}</span>
        <span class="pet-lobby-roam-label">{{ roaming ? '游走中' : '已静止' }}</span>
      </button>

      <!-- 显示/隐藏 Agent 精灵：控制所有 Agent 精灵的显示与隐藏（按钮文案为将要执行的操作） -->
      <button
        class="pet-lobby-display-toggle"
        :class="{ off: petsHidden }"
        :title="petsHidden ? '点击显示 Agent 精灵' : '点击隐藏 Agent 精灵'"
        @click.stop="toggleAllPets()"
      >
        <span class="pet-lobby-display-icon">{{ petsHidden ? '👁' : '🙈' }}</span>
        <span class="pet-lobby-display-label">{{ petsHidden ? '显示Agent精灵' : '隐藏Agent精灵' }}</span>
      </button>

      <!-- 全部输出显隐：一键切换（全部隐藏 ↔ 全部显示），按钮文案为将要执行的操作 -->
      <button
        class="pet-lobby-display-toggle"
        :title="allOutputsHidden ? '显示所有 Agent 的输出' : '隐藏所有 Agent 的输出'"
        @click.stop="toggleAllOutputs()"
      >
        <span class="pet-lobby-display-icon">{{ allOutputsHidden ? '💬' : '🚫' }}</span>
        <span class="pet-lobby-display-label">{{ allOutputsHidden ? '显示全部输出' : '隐藏全部输出' }}</span>
      </button>

      <!-- 安装浏览器插件：打开安装指引弹层（内含下载按钮）；有新版本时显示红点 -->
      <button
        class="pet-lobby-display-toggle pet-lobby-install-toggle"
        :class="{ 'has-update': extensionVersion.outdated }"
        title="安装浏览器插件"
        @click.stop="openInstallExtensionDialog()"
      >
        <span class="pet-lobby-display-icon">🧩</span>
        <span class="pet-lobby-display-label">安装浏览器插件</span>
        <span v-if="extensionVersion.outdated" class="pet-lobby-update-dot" title="插件有新版本"></span>
      </button>
    </div>

    <!-- 无 Agent 时的空状态引导：新用户第一次进入大厅时给出明确的下一步 -->
    <!-- 需等首次列表拉取完成再判断，否则有 Agent 时会先闪现再消失 -->
    <div v-if="agentsLoaded && !hasAnyAgent" class="pet-lobby-empty">
      <div class="pet-lobby-empty-title">还没有 Agent</div>
      <div class="pet-lobby-empty-desc">
        Agent 是 Jarvis 里的 AI 助手，每个 Agent 都是一只可以对话的宠物。<br />
        创建第一个 Agent 后，它就会出现在这片大厅里。
      </div>
      <div class="pet-lobby-empty-actions">
        <button class="pet-lobby-empty-btn primary" type="button" @click="createFirstAgent">
          ➕ 创建第一个 Agent
        </button>
        <button class="pet-lobby-empty-btn" type="button" @click="emit('openOnboarding', 'welcome')">
          🎓 查看新手引导
        </button>
      </div>
      <div class="pet-lobby-empty-hint">
        提示：按 <b>Ctrl+P</b> 打开命令面板，可以搜索并执行几乎所有操作。
      </div>
    </div>
    <!-- 宠物群 -->
    <div
      v-for="pet in petAgents"
      v-show="showPets"
      :key="pet.agentId"
      class="lobby-pet"
      :class="[pet.classes, { active: pet.active, dragging: pet.dragging, dimmed: activePetId && activePetId !== pet.agentId, 'is-code-agent': pet.agentType === 'code_agent' }]"
      :style="{ left: pet.x + 'px', top: pet.y + 'px' }"
      @pointerdown="onPetPointerDown(pet, $event)"
      @dblclick="onPetDblClick(pet)"
      @contextmenu.prevent.stop="onPetContextMenu(pet, $event)"
    >
      <div class="lobby-pet-inner">
        <div class="lobby-pet-body">
          <div class="lobby-pet-head">
            <div class="lobby-pet-ear l"></div>
            <div class="lobby-pet-ear r"></div>
            <div class="lobby-pet-eye l"><div class="lobby-pet-pupil"></div></div>
            <div class="lobby-pet-eye r"><div class="lobby-pet-pupil"></div></div>
            <div class="lobby-pet-mouth"></div>
          </div>
          <div class="lobby-pet-tail"></div>
        </div>
        <div class="lobby-pet-shadow"></div>
      </div>
      <div class="lobby-pet-name"><span class="lobby-pet-type">{{ pet.agentType === 'code_agent' ? '💻' : '🤖' }}</span>{{ pet.name }}</div>
      <div class="lobby-pet-status" :class="pet.statusClass"></div>

      <!-- 输出气泡 + 输入/确认控件：堆叠在宠物下方 -->
      <div
        v-show="!isOutputHidden(pet.agentId) || pet.active || pet.inputMode === 'confirm'"
        class="lobby-pet-stack"
        :class="{ 'stack-above': pet.panelAbove }"
        :style="{ left: pet.stackLeft + 'px', width: pet.stackWidth + 'px', maxHeight: pet.stackMaxH + 'px' }"
        @pointerdown.stop
        @click.stop
        @dblclick.stop
      >
        <!-- 输出气泡：常驻显示（markdown 渲染）；点击气泡同样激活该 Agent -->
        <div v-if="pet.output && !isOutputHidden(pet.agentId)" class="lobby-pet-output-wrap">
          <div
            class="lobby-pet-output message-body markdown-content"
            :data-pet-output="pet.agentId"
            v-html="pet.output"
            @click.stop="onPetClick(pet)"
            @scroll="onOutputScroll(pet, $event)"
          ></div>
          <button
            class="lobby-pet-copy"
            :class="{ copied: pet.copied }"
            :title="pet.copied ? '已复制' : '复制输出'"
            @click.stop="copyPetOutput(pet)"
          >{{ pet.copied ? '✓' : '⧉' }}</button>
        </div>

        <!-- 确认控件：需要确认时直接显示（无需点击） -->
        <div v-if="pet.inputMode === 'confirm'" class="lobby-pet-panel">
          <div class="lobby-pet-confirm">
            <div class="lobby-pet-confirm-msg">{{ pet.confirmMessage || '请确认' }}</div>
            <div class="lobby-pet-confirm-actions" :class="{ 'default-yes': pet.confirmDefault !== false }">
              <button class="lobby-pet-confirm-btn yes" @click="submitConfirm(pet, true)">确认</button>
              <button class="lobby-pet-confirm-btn no" @click="submitConfirm(pet, false)">取消</button>
            </div>
          </div>
        </div>

        <!-- 输入面板：单击展开（多行/单行，按状态自动选择） -->
        <div v-else-if="pet.active" class="lobby-pet-panel">
          <!-- 多行输入 -->
          <div v-if="pet.inputMode === 'multi'" class="lobby-pet-input-row lobby-pet-input-row-multi">
            <textarea
              class="lobby-pet-textarea"
              rows="3"
              :data-pet-input="pet.agentId"
              :placeholder="pet.inputTip || '输入内容 (Ctrl+Enter / Ctrl+D 发送)'"
              v-model="pet.inputText"
              @keydown="handlePetKeydown(pet, $event)"
              @keyup="handlePetCtrlKeyup($event)"
              @input="handlePetInput(pet, $event)"
              @pointerdown.stop="onInputPointerDown(pet)"
            ></textarea>
            <button v-if="isMobile" class="lobby-pet-at" @click="insertAtSymbol(pet)" title="插入 @ 触发补全">@</button>
            <button class="lobby-pet-complete" @click="completePet(pet)" title="完成（发送空消息）">完成</button>
            <button class="lobby-pet-send" @click="submitPet(pet)" title="发送 (Ctrl+Enter)">➤</button>
          </div>

          <!-- 单行输入 -->
          <div v-else class="lobby-pet-input-row">
            <input
              class="lobby-pet-input"
              :type="pet.isPassword ? 'password' : 'text'"
              :data-pet-input="pet.agentId"
              :placeholder="pet.inputTip || '输入内容 (Enter 发送)'"
              v-model="pet.inputText"
              @keydown="handlePetSingleKeydown(pet, $event)"
              @keyup="handlePetCtrlKeyup($event)"
              @input="handlePetInput(pet, $event)"
              @pointerdown.stop="onInputPointerDown(pet)"
            />
            <button class="lobby-pet-complete" @click="completePet(pet)" title="完成（发送空消息）">完成</button>
            <button class="lobby-pet-send" @click="submitPet(pet)" title="发送 (Enter)">➤</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右键菜单：宠物（对当前 Agent 的操作）/ 节点（节点操作） -->
    <div
      v-if="contextMenu.visible"
      class="lobby-context-menu"
      :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      @pointerdown.stop
      @click.stop
      @contextmenu.prevent.stop
    >
      <div class="lobby-context-title">{{ contextMenu.name }}</div>
      <div class="lobby-context-items">
        <button
          v-for="act in contextMenuActions"
          :key="act.id"
          class="lobby-context-item"
          :disabled="act.enabled === false"
          @click="onContextAction(act)"
        >
          <span class="lobby-context-icon">{{ act.icon }}</span>
          <span class="lobby-context-label">{{ act.label }}</span>
        </button>
      </div>
    </div>

    <!-- 节点重命名弹层：确定后同步到设置中的节点名称映射 -->
    <div
      v-if="renameDialog.visible"
      class="lobby-rename-mask"
      @pointerdown.stop
      @click.stop="closeRenameDialog"
    >
      <div class="lobby-rename-dialog" @click.stop>
        <div class="lobby-rename-title">重命名节点</div>
        <div class="lobby-rename-sub">{{ renameDialog.nodeId }}</div>
        <input
          ref="renameInputRef"
          class="lobby-rename-input"
          type="text"
          placeholder="输入显示名称（留空恢复为节点 ID）"
          v-model="renameDialog.value"
          @keydown.enter.prevent="confirmRename"
          @keydown.esc.prevent="closeRenameDialog"
        />
        <div class="lobby-rename-actions">
          <button class="lobby-rename-btn cancel" @click="closeRenameDialog">取消</button>
          <button class="lobby-rename-btn ok" @click="confirmRename">确定</button>
        </div>
      </div>
    </div>

    <!-- 宠物「添加到分组」弹层：选择已有分组或新建分组 -->
    <div
      v-if="groupDialog.visible"
      class="lobby-rename-mask"
      @pointerdown.stop
      @click.stop="closeGroupDialog"
    >
      <div class="lobby-rename-dialog" @click.stop>
        <div class="lobby-rename-title">添加到分组</div>
        <div class="lobby-rename-sub">{{ groupDialog.agentName }}</div>
        <div class="lobby-group-list">
          <button
            v-for="g in agentGroups"
            :key="g.id"
            class="lobby-group-item"
            @click="pickGroup(g.id)"
          >
            <span class="lobby-group-name">{{ g.name }}</span>
            <span class="lobby-group-count">{{ (g.agentIds || []).length }}</span>
          </button>
          <div v-if="agentGroups.length === 0" class="lobby-group-empty">暂无分组，可在下方新建</div>
        </div>
        <div class="lobby-group-create">
          <input
            class="lobby-rename-input"
            type="text"
            placeholder="新建分组名称"
            v-model="groupDialog.newGroupName"
            @keydown.enter.prevent="createGroupAndAdd"
            @keydown.esc.prevent="closeGroupDialog"
          />
          <button
            class="lobby-rename-btn ok"
            :disabled="!String(groupDialog.newGroupName || '').trim()"
            @click="createGroupAndAdd"
          >新建并加入</button>
        </div>
      </div>
    </div>

    <!-- 宠物「从分组移出」弹层：列出该 Agent 所在分组，点击即移出 -->
    <div
      v-if="removeGroupDialog.visible"
      class="lobby-rename-mask"
      @pointerdown.stop
      @click.stop="closeRemoveGroupDialog"
    >
      <div class="lobby-rename-dialog" @click.stop>
        <div class="lobby-rename-title">从分组移出</div>
        <div class="lobby-rename-sub">{{ removeGroupDialog.agentName }}</div>
        <div class="lobby-group-list">
          <button
            v-for="g in removeGroupOptions"
            :key="g.id"
            class="lobby-group-item"
            @click="pickRemoveGroup(g.id)"
          >
            <span class="lobby-group-name">{{ g.name }}</span>
            <span class="lobby-group-count">移出</span>
          </button>
          <div v-if="removeGroupOptions.length === 0" class="lobby-group-empty">该 Agent 当前不在任何分组中</div>
        </div>
      </div>
    </div>

    <!-- 安装浏览器插件弹层：安装说明 + 下载插件包按钮 -->
    <div
      v-if="installDialog.visible"
      class="lobby-rename-mask"
      @pointerdown.stop
      @click.stop="closeInstallDialog"
    >
      <div class="lobby-install-dialog" @click.stop>
        <div class="lobby-rename-title">安装浏览器插件</div>
        <div class="lobby-rename-sub">Jarvis Browser Bridge · 让 Agent 操作用你真实浏览器中的网页</div>
        <div class="lobby-install-steps">
          <div class="lobby-install-step">
            <span class="lobby-install-step-no">1</span>
            <span class="lobby-install-step-text">点击下方「下载插件包」，得到 zip 压缩包并解压到本地目录。</span>
          </div>
          <div class="lobby-install-step">
            <span class="lobby-install-step-no">2</span>
            <span class="lobby-install-step-text">打开 Chrome/Edge，访问 <code>chrome://extensions</code>，开启右上角「开发者模式」。</span>
          </div>
          <div class="lobby-install-step">
            <span class="lobby-install-step-no">3</span>
            <span class="lobby-install-step-text">点击「加载已解压的扩展程序」，选择刚才解压出来的目录。</span>
          </div>
          <div class="lobby-install-step">
            <span class="lobby-install-step-no">4</span>
            <span class="lobby-install-step-text">在浏览器中登录 Jarvis 网页（扩展会自动复用登录态，无需手填 Token）。</span>
          </div>
          <div class="lobby-install-step">
            <span class="lobby-install-step-no">5</span>
            <span class="lobby-install-step-text">点击工具栏扩展图标，在「添加网关地址」中填写网关地址（如本页地址）并连接。</span>
          </div>
        </div>
        <div v-if="installDialog.error" class="lobby-install-error">{{ installDialog.error }}</div>

        <div v-if="extensionVersion.outdated" class="lobby-install-update">
          <span class="lobby-install-update-icon">⬆</span>
          <span>检测到插件有新版本（当前 {{ extensionVersion.current.join('、') }} → 最新 {{ extensionVersion.latest }}），请重新下载并重新加载扩展。</span>
        </div>
        <div v-else-if="extensionVersion.latest" class="lobby-install-version">
          <span v-if="extensionVersion.current.length">当前插件版本 {{ extensionVersion.current.join('、') }} · 最新版本 {{ extensionVersion.latest }}</span>
          <span v-else>最新插件版本 {{ extensionVersion.latest }}（暂未检测到已连接的插件）</span>
        </div>

        <!-- 风险提示与免责声明：插件申请了高敏感权限，下载前必须让用户明确知悉 -->
        <div class="lobby-install-risk">
          <div class="lobby-install-risk-head">
            <span class="lobby-install-risk-icon">⚠</span>
            <span>高风险提示 · 请务必阅读后再下载</span>
          </div>
          <div class="lobby-install-risk-body">
            <p>
              本插件申请了 <strong>28 项浏览器权限</strong>，其中 <strong>8 项为高敏感权限</strong>：
              <code>cookies</code>、<code>webRequest</code>、<code>management</code>、<code>nativeMessaging</code>、
              <code>proxy</code>、<code>privacy</code>、<code>browsingData</code>、<code>contentSettings</code>。
            </p>
            <p>
              安装后，Agent 将获得<strong>对你浏览器的完整操作能力</strong>：可像你本人一样操作任意已登录网页
              （点击、输入、上传、截图、执行脚本），读取与改写网络流量，管理扩展与站点权限，
              并访问书签、历史、下载、Cookie、密码等<strong>全部浏览器数据</strong>。
            </p>
            <p>具体而言，连接到本网关的 Agent 将<strong>具备以下能力</strong>：</p>
            <ul>
              <li>读取、修改、删除你在各网站的 <strong>Cookie（含登录凭证）</strong>，等同于<strong>接管你的全部登录态</strong>；</li>
              <li>读取并改写你的<strong>全部网络请求</strong>（可阻断或重定向），可注入、篡改任意网页内容；</li>
              <li>查看、启用、禁用甚至 <strong>卸载你安装的其他扩展</strong>；</li>
              <li>与<strong>本机应用</strong>通信，并<strong>修改系统代理设置</strong>（影响全部网络流量）；</li>
              <li>修改隐私开关，以及 <strong>清除浏览历史、缓存、Cookie、保存的密码</strong>；</li>
              <li>修改站点级权限（摄像头、麦克风、地理位置、弹窗等），可<strong>静默开启摄像头/麦克风授权</strong>；</li>
              <li>在页面主世界执行任意 JS，<strong>绕过页面 CSP 与同源策略</strong>读取页面内数据。</li>
            </ul>
            <p class="lobby-install-risk-warn">
              上述能力叠加后，等同于<strong>「把你的浏览器（含全部账号与数据）完全交给 Agent」</strong>。
              其中 <strong>清除浏览数据、卸载扩展、删除 Cookie</strong> 等操作<strong>不可逆</strong>，一旦执行无法恢复。
            </p>
            <p>
              <strong>免责声明：</strong>本插件按「现状」提供，仅用于你本人授权范围内的浏览器自动化。
              请仅在你<strong>完全信任</strong>所连接的网关与 Agent 的前提下使用。
              因授权、误操作或第三方滥用导致的账号泄露、资金损失、数据丢失、配置损坏等后果，
              由使用者自行承担，本项目及作者不承担任何责任。
              若不接受上述风险，请<strong>立即关闭本弹窗，不要下载或安装</strong>。
            </p>
          </div>
        </div>

        <div class="lobby-rename-actions">
          <button class="lobby-rename-btn cancel" @click="closeInstallDialog">关闭</button>
          <button
            class="lobby-rename-btn ok"
            :disabled="installDialog.downloading"
            @click="downloadExtension()"
          >{{ installDialog.downloading ? '下载中…' : '下载插件包' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { normalizeNodeStatus, normalizeAgentStatus } from './topology.js'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  agentsLoaded: { type: Boolean, default: false },
  nodes: { type: Array, default: () => [] },
  getStatusClass: { type: Function, default: null },
  getInputState: { type: Function, default: null },
  getLatestOutput: { type: Function, default: null },
  historyNav: { type: Function, default: null },
  getNodeDisplayName: { type: Function, default: null },
  // 右键菜单动作（复用命令面板「当前 Agent」组），由父组件按当前 Agent 计算后传入
  contextActions: { type: Array, default: () => [] },
  // 节点右键菜单动作，由父组件传入（便于后续扩展更多节点功能）
  nodeActions: { type: Array, default: () => [] },
  // 现有 Agent 分组列表（用于宠物右键「添加到分组」）
  agentGroups: { type: Array, default: () => [] },
  // 网关地址（host:port），用于左上角仪表展示
  gatewayAddress: { type: String, default: '' },
  // 连接状态与文案（online/connecting/reconnecting/offline + 中文标签）
  connectionStatus: { type: String, default: '' },
  connectionLabel: { type: String, default: '' },
  // 当前登录用户名（优先显示名）
  currentUserName: { type: String, default: '' },
  // 下载浏览器扩展包（异步函数，返回 { filename, blob }），由父组件注入以复用鉴权与网关地址
  downloadExtension: { type: Function, default: null },
  // 查询扩展版本（异步函数，返回 { latestVersion, sessions }），用于检测插件更新
  checkExtensionVersion: { type: Function, default: null },
})

const emit = defineEmits(['selectAgent', 'sendInput', 'complete', 'openCompletions', 'activePetChange', 'activeNodeChange', 'createAgentOnNode', 'contextAgent', 'contextRun', 'nodeContextRun', 'renameNode', 'addAgentToGroup', 'removeAgentFromGroup', 'openOnboarding'])

// 宠物尺寸常量（与 CSS 中的 .lobby-pet 宽高保持一致）
const PET_W = 72
const PET_H = 82
const PET_SPEED = 0.55 // 像素/帧，约 33px/秒
const MIN_DIST = 96 // 宠物之间最小间距，用于斥力避让
const EDGE_PAD = 12
const PANEL_H = 150 // 交互面板高度（粗略值，用于判断面板朝上/朝下）
const STACK_GAP = 4 // 堆叠容器与宠物本体的间距（与 CSS 的 calc(100% + 4px) 一致）

const stageRef = ref(null)
const stageSize = ref({ w: 0, h: 0 })
const petAgents = ref([])
const activePetId = ref(null)
// 选中的节点 id：节点操作（创建 Agent / 打开终端 / 更新代码 / 重启服务）据此作用于该节点
const activeNodeId = ref(null)
// 是否允许宠物自由游走：持久化到 localStorage（默认开启）
const ROAMING_KEY = 'jarvis.petLobby.roaming'
function loadRoaming() {
  try {
    return localStorage.getItem(ROAMING_KEY) !== '0'
  } catch (e) {
    /* localStorage 不可用时回退默认值 */
  }
  return true
}
const roaming = ref(loadRoaming())
watch(roaming, (on) => {
  try {
    localStorage.setItem(ROAMING_KEY, on ? '1' : '0')
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
})

// 宠物位置持久化：按 agentId 记录 { x, y }
// 大厅组件在打开/关闭 Panel 时会被 v-if 卸载重建（App.vue 的 hasNoPanel），
// 若无持久化，重建后每只宠物都会重新随机取位，导致位置跳变。
const POSITIONS_KEY = 'jarvis.petLobby.positions'
function loadPositions() {
  try {
    const raw = localStorage.getItem(POSITIONS_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const result = {}
    for (const [agentId, pos] of Object.entries(parsed)) {
      if (!pos || typeof pos !== 'object') continue
      const x = Number(pos.x)
      const y = Number(pos.y)
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue
      result[agentId] = { x, y }
    }
    return result
  } catch (e) {
    /* localStorage 不可用或数据损坏时回退为空 */
  }
  return {}
}
const petPositions = loadPositions()
// 位置只在组件卸载时（即离开大厅、被 App.vue 的 v-if 卸载）统一落盘一次：
// 游走过程中每帧都在移动，逐帧或定时写 localStorage 都是不必要的磁盘开销。
function savePositions() {
  try {
    localStorage.setItem(POSITIONS_KEY, JSON.stringify(petPositions))
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
}
function rememberPosition(pet) {
  if (!pet || !pet.agentId) return
  petPositions[pet.agentId] = { x: pet.x, y: pet.y }
}
// 清理已不存在 Agent 的位置记录，避免 localStorage 无限增长
function prunePositions(validIds) {
  for (const agentId of Object.keys(petPositions)) {
    if (!validIds.has(agentId)) delete petPositions[agentId]
  }
}

// 移动端判断：与 CSS 断点（max-width: 768px）保持一致，用于按需显示移动端专用控件
const MOBILE_BREAKPOINT = 768
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth <= MOBILE_BREAKPOINT)
function updateIsMobile() {
  isMobile.value = window.innerWidth <= MOBILE_BREAKPOINT
}

// 精灵显示：petsHidden=是否隐藏全部精灵，持久化到 localStorage
// 输出显隐完全由单个 Agent 的 hiddenOutputIds 控制（不再有全局输出开关）
const DISPLAY_MODE_KEY = 'jarvis.petLobby.displayMode'
function loadPetsHidden() {
  try {
    // 兼容旧版三态：all / no-output / hidden
    return localStorage.getItem(DISPLAY_MODE_KEY) === 'hidden'
  } catch (e) {
    /* localStorage 不可用时回退默认值 */
  }
  return false
}
const petsHidden = ref(loadPetsHidden())
const showPets = computed(() => !petsHidden.value)
watch(petsHidden, (hidden) => {
  try {
    localStorage.setItem(DISPLAY_MODE_KEY, hidden ? 'hidden' : 'all')
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
})
// 显示 / 隐藏 Agent 精灵：切换所有 Agent 精灵的显示与隐藏
function toggleAllPets() {
  petsHidden.value = !petsHidden.value
}
// 是否所有 Agent 的输出都已隐藏：用于「全部输出显隐」按钮的文案与图标
// 无宠物时视为未隐藏，按钮显示「隐藏全部输出」
const allOutputsHidden = computed(() => {
  const pets = petAgents.value
  if (!pets.length) return false
  return pets.every(p => hiddenOutputIds.value.has(p.agentId))
})
// 全部输出显隐：已全部隐藏则全部显示，否则全部隐藏
function toggleAllOutputs() {
  if (allOutputsHidden.value) {
    if (hiddenOutputIds.value.size) {
      hiddenOutputIds.value = new Set()
      saveHiddenOutputs()
    }
  } else {
    hiddenOutputIds.value = new Set(petAgents.value.map(p => p.agentId))
    saveHiddenOutputs()
  }
}

// 单个 Agent 的输出显隐：独立控制并持久化
const HIDDEN_OUTPUTS_KEY = 'jarvis.petLobby.hiddenOutputs'
function loadHiddenOutputs() {
  try {
    const raw = localStorage.getItem(HIDDEN_OUTPUTS_KEY)
    const arr = raw ? JSON.parse(raw) : []
    if (Array.isArray(arr)) return new Set(arr.filter(id => typeof id === 'string'))
  } catch (e) {
    /* localStorage 不可用或数据损坏时回退空集 */
  }
  return new Set()
}
const hiddenOutputIds = ref(loadHiddenOutputs())
// 曾经出现过的 agentId：用于判断哪些持久化项对应的 Agent 已被删除
const seenAgentIds = new Set()
function saveHiddenOutputs() {
  try {
    localStorage.setItem(HIDDEN_OUTPUTS_KEY, JSON.stringify([...hiddenOutputIds.value]))
  } catch (e) {
    /* 忽略写入失败（隐私模式等） */
  }
}
// 某 Agent 的输出是否被单独隐藏
function isOutputHidden(agentId) {
  return hiddenOutputIds.value.has(agentId)
}
// 切换某 Agent 的输出显隐（供命令面板/右键菜单调用）
function toggleAgentOutput(agentId) {
  if (!agentId) return
  const next = new Set(hiddenOutputIds.value)
  if (next.has(agentId)) next.delete(agentId)
  else next.add(agentId)
  hiddenOutputIds.value = next
  saveHiddenOutputs()
}

let rafId = null
let resizeObserver = null

// ===== 节点与连线（参考大屏「网络拓扑」风格）=====
// 节点状态配色（与大屏 TopologyOverlay 保持一致）
const NODE_COLORS = { online: '#34d99b', offline: '#ff5d6c', unknown: '#8a9bb0' }
const AGENT_COLORS = { running: '#20c8ff', waiting: '#ffb347', idle: '#8a9bb0', stopped: '#ff5d6c' }

function nodeColor(state) {
  if (state === 'online') return NODE_COLORS.online
  if (state === 'offline') return NODE_COLORS.offline
  return NODE_COLORS.unknown
}
function agentColor(state) {
  return AGENT_COLORS[state] || AGENT_COLORS.idle
}

// 节点在大厅中的坐标：master 居中，其余节点均匀分布在圆周上
const nodeLayout = computed(() => {
  const list = Array.isArray(props.nodes) ? props.nodes : []
  const w = stageSize.value.w
  const h = stageSize.value.h
  const cx = w / 2
  const cy = h / 2
  // 圆周半径：随舞台尺寸自适应，留出边距
  const radius = Math.max(Math.min(w, h) * 0.32, 120)
  const result = new Map()
  const master = list.find(n => n && n.node_id === 'master')
  if (master) {
    result.set('master', { node_id: 'master', x: cx, y: cy })
  }
  const others = list.filter(n => n && n.node_id && n.node_id !== 'master')
  const count = others.length
  others.forEach((n, i) => {
    // 从正上方开始，顺时针均匀分布
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(count, 1)
    result.set(n.node_id, {
      node_id: n.node_id,
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    })
  })
  return result
})

// 节点列表（带坐标、状态、配色、机箱尺寸），供模板渲染
const nodeItems = computed(() => {
  const list = Array.isArray(props.nodes) ? props.nodes : []
  const agentList = Array.isArray(props.agents) ? props.agents : []
  // master 版本作为基准：与之不一致的节点视为未更新，需高亮提示
  const masterVersion = (() => {
    const master = list.find(n => n && n.node_id === 'master')
    return master && master.version ? String(master.version) : ''
  })()
  return list
    .filter(n => n && n.node_id && nodeLayout.value.has(n.node_id))
    .map(n => {
      const pos = nodeLayout.value.get(n.node_id)
      const state = normalizeNodeStatus(n.status)
      const isMaster = n.node_id === 'master'
      const color = isMaster && state !== 'offline' && state !== 'unknown'
        ? '#ffd75e'
        : nodeColor(state)
      const name = props.getNodeDisplayName
        ? props.getNodeDisplayName(n.node_id)
        : (isMaster ? 'master' : n.node_id)
      const short = (() => {
        const s = String(name || '')
        if (s === 'master') return 'master'
        return s.length > 10 ? s.slice(0, 9) + '…' : s
      })()
      // 该节点上的 agent 数（不含已停止）
      const agentCount = agentList.filter(a => {
        const nid = String(a?.node_id || '').trim() || 'master'
        return nid === n.node_id && a.status !== 'stopped'
      }).length
      // 机箱尺寸：master 略大
      const rw = isMaster ? 38 : 30
      const rh = isMaster ? 33 : 26
      // 节点版本：child 由心跳上报，master 由网关补充；缺失时留空不显示
      const version = n.version ? String(n.version) : ''
      // 与 master 版本不一致（且双方都有版本）时高亮，提示该节点未更新
      const versionMismatch = !!version && !!masterVersion && version !== masterVersion
      return {
        node_id: n.node_id,
        x: pos.x,
        y: pos.y,
        state,
        color,
        isMaster,
        short,
        agentCount,
        version,
        versionMismatch,
        rw,
        rh,
        active: activeNodeId.value === n.node_id,
        fill: state === 'offline'
          ? 'rgba(255,93,108,0.10)'
          : (isMaster ? 'url(#lobby-center-fill)' : 'rgba(8,18,30,0.7)'),
      }
    })
})

// 节点在线统计：state 由 normalizeNodeStatus 归一为 online/offline/unknown
const nodeOnlineStat = computed(() => {
  const list = nodeItems.value
  const online = list.filter(n => n.state === 'online').length
  return { online, total: list.length }
})
// Agent 状态统计：按 normalizeAgentStatus 归一为 running/waiting/idle/stopped 计数
// 注意：统计须基于 props.agents 全量（petAgents 已过滤掉 stopped 的 Agent）
const AGENT_STAT_ORDER = ['running', 'waiting', 'idle', 'stopped']
const AGENT_STAT_LABEL = { running: '运行', waiting: '等待', idle: '空闲', stopped: '停止' }
const agentStatusStat = computed(() => {
  const counts = { running: 0, waiting: 0, idle: 0, stopped: 0 }
  for (const agent of (props.agents || [])) {
    const state = normalizeAgentStatus(props.getStatusClass ? props.getStatusClass(agent) : '')
    if (counts[state] !== undefined) counts[state] += 1
  }
  return AGENT_STAT_ORDER
    .filter(state => counts[state] > 0)
    .map(state => ({ state, label: AGENT_STAT_LABEL[state], count: counts[state], color: agentColor(state) }))
})

// 是否已有任意 Agent：为 false 时在大厅展示空状态引导
const hasAnyAgent = computed(() => (props.agents || []).length > 0)

// 空状态「创建第一个 Agent」：在第一个在线节点上创建（无节点时交由父组件兜底）
function createFirstAgent() {
  const nodes = nodeItems.value || []
  const target = nodes.find(n => n.state === 'online') || nodes[0]
  emit('createAgentOnNode', target ? target.node_id : '')
}

// 节点间连线：master → 其余节点
const nodeLinks = computed(() => {
  const links = []
  const master = nodeLayout.value.get('master')
  if (!master) return links
  const stateById = new Map(nodeItems.value.map(n => [n.node_id, n.state]))
  for (const [id, pos] of nodeLayout.value) {
    if (id === 'master') continue
    links.push({
      key: `node-${id}`,
      x1: master.x,
      y1: master.y,
      x2: pos.x,
      y2: pos.y,
      offline: stateById.get(id) === 'offline',
    })
  }
  return links
})

// Agent 与所属节点的连线：宠物中心 → 节点坐标（颜色取 agent 状态色）
const agentLinks = computed(() => {
  const links = []
  // 精灵隐藏时不绘制 agent→节点连线
  if (!showPets.value) return links
  for (const pet of petAgents.value) {
    const agent = (props.agents || []).find(a => a.agent_id === pet.agentId)
    const nodeId = String(agent?.node_id || '').trim() || 'master'
    const pos = nodeLayout.value.get(nodeId)
    if (!pos) continue
    const state = normalizeAgentStatus(props.getStatusClass ? props.getStatusClass(agent) : '')
    links.push({
      key: `agent-${pet.agentId}`,
      x1: pet.x + PET_W / 2,
      y1: pet.y + PET_H / 2,
      x2: pos.x,
      y2: pos.y,
      color: agentColor(state),
    })
  }
  return links
})

function randBetween(min, max) {
  return min + Math.random() * (max - min)
}

function clampPos(x, y) {
  const maxX = Math.max(stageSize.value.w - PET_W - EDGE_PAD, EDGE_PAD)
  const maxY = Math.max(stageSize.value.h - PET_H - EDGE_PAD, EDGE_PAD)
  return {
    x: Math.min(Math.max(x, EDGE_PAD), maxX),
    y: Math.min(Math.max(y, EDGE_PAD), maxY),
  }
}

function pickTarget() {
  const maxX = Math.max(stageSize.value.w - PET_W - EDGE_PAD, EDGE_PAD)
  const maxY = Math.max(stageSize.value.h - PET_H - EDGE_PAD, EDGE_PAD)
  return {
    x: randBetween(EDGE_PAD, maxX),
    y: randBetween(EDGE_PAD, maxY),
  }
}

// 复制某只宠物的输出内容（取渲染后的纯文本）
async function copyPetOutput(pet) {
  if (!pet || !pet.output) return
  const holder = document.createElement('div')
  holder.innerHTML = pet.output
  const text = (holder.textContent || '').trim()
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch (err) {
    try {
      const textArea = document.createElement('textarea')
      textArea.value = text
      textArea.style.position = 'fixed'
      textArea.style.opacity = '0'
      document.body.appendChild(textArea)
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    } catch (fallbackErr) {
      console.error('[PET-COPY] 复制失败:', fallbackErr)
      return
    }
  }
  pet.copied = true
  if (pet.copyTimer) clearTimeout(pet.copyTimer)
  pet.copyTimer = setTimeout(() => { pet.copied = false }, 1200)
}

// 判断当前焦点是否允许被宠物输入框接管：
// 有模态弹窗打开、或用户正在其它输入控件（input/textarea/contenteditable）中操作时不抢焦点。
function canStealPetFocus() {
  const overlays = document.querySelectorAll('.el-overlay, .modal-overlay, .dialog-overlay, .diff-modal-overlay')
  for (const el of overlays) {
    const style = window.getComputedStyle(el)
    if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') return false
  }
  const active = document.activeElement
  if (!active || active === document.body) return true
  const tagName = String(active.tagName || '').toLowerCase()
  if (tagName === 'input' || tagName === 'textarea' || active.isContentEditable) return false
  return true
}

// 聚焦某只宠物的输入框（多行/单行按当前 inputMode 自动匹配）
// force=true 用于显式切换焦点（如刚激活宠物），跳过「用户正在其它输入框」的保护
// 输入框仅在 pet.active 且 inputMode !== 'confirm' 时渲染；面板展开/inputMode 切换会替换元素，
// 单次 nextTick 可能早于元素出现，故在若干帧内重试直到聚焦成功。
function focusPetInput(agentId, force = false) {
  if (!agentId) return
  if (!force && !canStealPetFocus()) return
  let attempts = 0
  const tryFocus = () => {
    const el = stageRef.value && stageRef.value.querySelector(`[data-pet-input="${agentId}"]`)
    if (el) {
      if (document.activeElement !== el) el.focus()
      // 已成功聚焦（或元素已存在但被其它控件抢占）即结束重试
      if (document.activeElement === el) return
    }
    // 元素尚未渲染（面板刚展开 / inputMode 切换中）时继续重试，最多约 10 帧
    if (attempts++ < 10) requestAnimationFrame(tryFocus)
  }
  nextTick(tryFocus)
}

// 刷新某只宠物的输入态与最新输出
function refreshPetData(pet) {
  if (!pet) return
  const state = props.getInputState ? props.getInputState(pet.agentId) : null
  if (state) {
    // 输入模式变化会替换输入控件（textarea ↔ input），原焦点元素被销毁，
    // 需在渲染后把焦点交还给输入框，否则等待单行输入时焦点丢失
    const modeChanged = pet.inputMode !== state.mode
    pet.inputMode = state.mode
    if (modeChanged && pet.active) focusPetInput(pet.agentId)
    // 是否有待处理的输入请求：展开宠物时据此决定是否自动聚焦输入框
    pet.hasInputRequest = !!state.hasRequest
    pet.inputTip = state.tip
    pet.isPassword = state.isPassword
    pet.confirmMessage = state.confirmMessage
    pet.confirmDefault = state.confirmDefault
    // 首次进入或 preset 变化时填充输入框
    if (state.preset && !pet.inputText) {
      pet.inputText = state.preset
    }
  }
  const latest = props.getLatestOutput ? props.getLatestOutput(pet.agentId) : null
  const nextOutput = latest ? latest.html : ''
  const outputChanged = nextOutput !== pet.output
  pet.output = nextOutput
  layoutPetStack(pet)
  // 流式输出：内容更新后若用户未上滚，自动滚到底部
  if (outputChanged && pet.outputAutoScroll) {
    scrollOutputToBottom(pet.agentId)
  }
}

// 输出滚动到底部（等待 DOM 更新后执行）
function scrollOutputToBottom(agentId) {
  nextTick(() => {
    const el = stageRef.value && stageRef.value.querySelector(`[data-pet-output="${agentId}"]`)
    if (el) el.scrollTop = el.scrollHeight
  })
}

// 用户手动滚动输出框：接近底部时恢复自动滚动，否则暂停（避免打断用户查看历史）
function onOutputScroll(pet, event) {
  const el = event.target
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  pet.outputAutoScroll = atBottom
}

// 计算堆叠容器（输出/输入/确认）的位置与尺寸，确保始终落在舞台可视范围内
// 水平：以宠物中心对齐，并夹取到舞台左右边界内
// 垂直：优先放下方，下方空间不足则放上方，并限制最大高度避免溢出
function layoutPetStack(pet) {
  if (!pet) return
  const w = stageSize.value.w
  const h = stageSize.value.h
  if (!w || !h) return
  // 宽度与 CSS 的 min(560px, 62vw) 对齐，且不超出舞台可用宽度
  const width = Math.max(160, Math.min(560, w * 0.62, w - EDGE_PAD * 2))
  pet.stackWidth = width
  // 水平：理想居中于宠物，夹取到 [EDGE_PAD, w - width - EDGE_PAD]
  const cx = pet.x + PET_W / 2
  const idealLeft = cx - width / 2
  const clampedLeft = Math.min(Math.max(idealLeft, EDGE_PAD), Math.max(w - width - EDGE_PAD, EDGE_PAD))
  // left 相对宠物左上角（stack 为 absolute，父级是宠物）
  pet.stackLeft = clampedLeft - pet.x
  // 垂直：下方 / 上方可用空间
  const belowSpace = h - (pet.y + PET_H + STACK_GAP)
  const aboveSpace = pet.y - STACK_GAP
  const useAbove = belowSpace < PANEL_H && aboveSpace > belowSpace
  pet.panelAbove = useAbove
  const avail = Math.max(useAbove ? aboveSpace : belowSpace, 120)
  pet.stackMaxH = Math.min(avail, h - EDGE_PAD * 2)
}

// 依据 agents 同步宠物实例：新增的补位，消失的移除，已有的保留位置
function syncPets() {
  const list = Array.isArray(props.agents) ? props.agents : []
  const existing = new Map(petAgents.value.map(p => [p.agentId, p]))
  const next = []
  for (const agent of list) {
    const agentId = agent.agent_id
    if (!agentId) continue
    // 已停止的 Agent 不显示宠物
    if (agent.status === 'stopped') continue
    let pet = existing.get(agentId)
    if (!pet) {
      // 优先复用上次记录的位置（组件因打开/关闭 Panel 被卸载重建时保持位置不变），
      // 无记录或记录越界时才随机取位
      const saved = petPositions[agentId]
      const start = saved ? clampPos(saved.x, saved.y) : pickTarget()
      pet = {
        agentId,
        name: agent.name || agent.agent_id,
        agentType: agent.agent_type || 'agent',
        x: start.x,
        y: start.y,
        target: pickTarget(),
        faceLeft: false,
        statusClass: '',
        classes: '',
        active: false,
        typing: false,
        dragging: false,
        inputMode: 'multi',
        hasInputRequest: false,
        inputText: '',
        inputTip: '',
        isPassword: false,
        confirmMessage: '',
        confirmDefault: true,
        output: '',
        panelAbove: false,
        stackLeft: 0,
        stackWidth: 0,
        stackMaxH: 0,
        outputAutoScroll: true,
        copied: false,
        copyTimer: null,
      }
    } else {
      pet.name = agent.name || agent.agent_id
      pet.agentType = agent.agent_type || 'agent'
    }
    const statusClass = props.getStatusClass ? props.getStatusClass(agent) : ''
    pet.statusClass = statusClass
    pet.classes = `status-${statusClass}${pet.faceLeft ? ' face-left' : ''}`
    refreshPetData(pet)
    next.push(pet)
  }
  petAgents.value = next
  // 若当前展开的宠物已消失，重置 activePetId
  if (activePetId.value && !next.some(p => p.agentId === activePetId.value)) {
    activePetId.value = null
  }
  // 清理已被删除 Agent 的位置记录（stopped 仍存在，不清理）
  // 仅在拿到过非空 agent 列表后才清理，避免初始加载（列表暂为空）时误删
  if (list.length > 0) {
    prunePositions(new Set(next.map(p => p.agentId)))
  }
  // 清理已被删除 Agent 的输出隐藏持久化数据（stopped 仍存在，不清理）
  // 仅在拿到过非空 agent 列表后才清理，避免初始加载（列表暂为空）时误删
  if (list.length > 0) {
    for (const a of list) {
      if (a && a.agent_id) seenAgentIds.add(a.agent_id)
    }
    let hiddenChanged = false
    const pruned = new Set()
    for (const id of hiddenOutputIds.value) {
      if (seenAgentIds.has(id)) pruned.add(id)
      else hiddenChanged = true
    }
    if (hiddenChanged) {
      hiddenOutputIds.value = pruned
      saveHiddenOutputs()
    }
  }
}

// 单帧：所有宠物向各自目标点移动，并做斥力避让
function step() {
  const pets = petAgents.value
  // 精灵隐藏时不渲染也不移动，直接跳过全部计算，降低资源消耗
  if (!showPets.value) {
    rafId = requestAnimationFrame(step)
    return
  }
  const n = pets.length
  // 计算两两斥力偏移
  const pushX = new Array(n).fill(0)
  const pushY = new Array(n).fill(0)
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const dx = pets[j].x - pets[i].x
      const dy = pets[j].y - pets[i].y
      const dist = Math.hypot(dx, dy) || 0.001
      if (dist < MIN_DIST) {
        const force = (MIN_DIST - dist) / MIN_DIST
        const ux = dx / dist
        const uy = dy / dist
        pushX[i] -= ux * force * 2.2
        pushY[i] -= uy * force * 2.2
        pushX[j] += ux * force * 2.2
        pushY[j] += uy * force * 2.2
      }
    }
  }

  for (let i = 0; i < n; i++) {
    const pet = pets[i]
    // 正在输入、展开交互面板或拖动中的宠物不移动
    if (pet.active || pet.typing || pet.dragging) continue
    if (!roaming.value) continue
    const dx = pet.target.x - pet.x
    const dy = pet.target.y - pet.y
    const dist = Math.hypot(dx, dy)
    if (dist < 6) {
      pet.target = pickTarget()
    } else {
      pet.x += (dx / dist) * PET_SPEED + pushX[i]
      pet.y += (dy / dist) * PET_SPEED + pushY[i]
    }
    const clamped = clampPos(pet.x, pet.y)
    pet.x = clamped.x
    pet.y = clamped.y
    // 位置变化后按节流写回持久化记录
    rememberPosition(pet)
    const faceLeft = dx < -1
    if (faceLeft !== pet.faceLeft) {
      pet.faceLeft = faceLeft
      pet.classes = `status-${pet.statusClass}${faceLeft ? ' face-left' : ''}`
    }
  }

  rafId = requestAnimationFrame(step)
}

function measureStage() {
  const el = stageRef.value
  if (!el) return
  stageSize.value = { w: el.clientWidth, h: el.clientHeight }
  // 舞台尺寸变化后重算堆叠容器位置，避免输入/输出框溢出可视范围
  for (const pet of petAgents.value) layoutPetStack(pet)
}

// 点击大厅空白处：取消所有宠物的选中/展开状态，让它们恢复飘动
function onStageClick(event) {
  // 点击任意处都先关闭右键菜单
  closeContextMenu()
  // 仅当点击目标是舞台本身（空白区域）时才处理；宠物及其面板已 stop 冒泡
  if (event.target !== stageRef.value) return
  // 点击空白处取消节点选中
  activeNodeId.value = null
  for (const pet of petAgents.value) {
    if (pet.active) closePanel(pet)
  }
}

// ===== 右键菜单（宠物 / 节点共用） =====
// 菜单状态：坐标相对舞台左上角；kind 区分来源；name 用于标题
const contextMenu = ref({ visible: false, x: 0, y: 0, kind: 'pet', agentId: null, nodeId: null, name: '' })

// 节点菜单内置动作：在节点上创建 Agent / 更新代码 / 重启服务（后续可在此追加更多节点功能）
const NODE_MENU_ACTIONS = [
  { id: 'node-create-agent', icon: '➕', label: '创建 Agent' },
  { id: 'node-open-terminal', icon: '⌨️', label: '打开终端' },
  { id: 'node-update-code', icon: '🔄', label: '更新代码' },
  { id: 'node-restart-service', icon: '♻️', label: '重启服务' },
  { id: 'node-rename', icon: '✏️', label: '重命名' },
]
const nodeMenuActions = computed(() => {
  const extra = props.nodeActions || []
  return [...NODE_MENU_ACTIONS, ...extra]
})

// 宠物菜单内置动作：添加到分组 / 从分组移出（后续可在此追加更多宠物功能）
const PET_MENU_ACTIONS = [
  { id: 'pet-add-to-group', icon: '📁', label: '添加到分组' },
  { id: 'pet-remove-from-group', icon: '📂', label: '从分组移出' },
]
const petMenuActions = computed(() => [...(props.contextActions || []), ...PET_MENU_ACTIONS])

// 当前菜单项：按 kind 取对应来源
const contextMenuActions = computed(() =>
  contextMenu.value.kind === 'node' ? nodeMenuActions.value : petMenuActions.value
)

function closeContextMenu() {
  if (contextMenu.value.visible) contextMenu.value.visible = false
}

// 估算菜单尺寸并做边界钳制，避免超出舞台（两列布局，宽度与 CSS min-width 对齐）
function placeContextMenu(event, itemCount) {
  const stage = stageRef.value
  if (!stage) return null
  const rect = stage.getBoundingClientRect()
  const MENU_W = 320
  const rows = Math.max(1, Math.ceil(itemCount / 2))
  const MENU_H = Math.min(44 + rows * 33, rect.height * 0.6)
  let x = event.clientX - rect.left
  let y = event.clientY - rect.top
  if (x + MENU_W > rect.width) x = Math.max(rect.width - MENU_W, 0)
  if (y + MENU_H > rect.height) y = Math.max(rect.height - MENU_H, 0)
  return { x, y }
}

// 在宠物上右键：通知父组件切换当前 Agent 并准备动作，再就地弹出菜单
function onPetContextMenu(pet, event) {
  if (!pet) return
  // 取消待执行的单击判定：避免右键后 250ms 误触发 onPetClick 而改变选中状态
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  // 先请求父组件把「当前 Agent」切到该宠物（决定菜单动作与可用性）
  emit('contextAgent', pet.agentId)
  const pos = placeContextMenu(event, petMenuActions.value.length)
  if (!pos) return
  contextMenu.value = {
    visible: true,
    x: pos.x,
    y: pos.y,
    kind: 'pet',
    agentId: pet.agentId,
    nodeId: null,
    name: pet.name || pet.agentId,
  }
}

// 在节点上单击：选中该节点（节点操作快捷键据此作用于该节点）；再次点击同一节点则取消选中
function onNodeClick(node) {
  if (!node) return
  activeNodeId.value = activeNodeId.value === node.node_id ? null : node.node_id
}

// 在节点上右键：弹出节点操作菜单
function onNodeContextMenu(node, event) {
  if (!node) return
  // 右键同时选中该节点，使节点操作快捷键与菜单作用于同一节点
  activeNodeId.value = node.node_id
  const pos = placeContextMenu(event, nodeMenuActions.value.length)
  if (!pos) return
  contextMenu.value = {
    visible: true,
    x: pos.x,
    y: pos.y,
    kind: 'node',
    agentId: null,
    nodeId: node.node_id,
    name: node.short || node.node_id,
  }
}

// ===== 节点重命名弹层 =====
// 确定后 emit('renameNode', { nodeId, name })，由父组件写入设置中的节点名称映射
const renameDialog = ref({ visible: false, nodeId: '', value: '' })
const renameInputRef = ref(null)

function openRenameDialog(nodeId, currentName) {
  if (!nodeId) return
  // 已打开时不重复触发（F2 连按、快捷键与右键菜单并发时避免重置输入内容）
  if (renameDialog.value.visible) return
  renameDialog.value = {
    visible: true,
    nodeId,
    value: currentName && currentName !== nodeId ? currentName : '',
  }
  nextTick(() => {
    const el = renameInputRef.value
    if (el) {
      el.focus()
      el.select()
    }
  })
}

function closeRenameDialog() {
  if (renameDialog.value.visible) renameDialog.value.visible = false
}

function confirmRename() {
  const nodeId = renameDialog.value.nodeId
  const name = String(renameDialog.value.value || '').trim()
  if (nodeId) emit('renameNode', { nodeId, name })
  closeRenameDialog()
}

// ===== 宠物「添加到分组」弹层 =====
// 选择已有分组，或新建分组；确定后 emit('addAgentToGroup', { agentId, groupId } | { agentId, newGroupName })
const groupDialog = ref({ visible: false, agentId: '', agentName: '', newGroupName: '' })

function openGroupDialog(agentId, agentName) {
  if (!agentId) return
  groupDialog.value = { visible: true, agentId, agentName: agentName || agentId, newGroupName: '' }
}

function closeGroupDialog() {
  if (groupDialog.value.visible) groupDialog.value.visible = false
}

// 加入已有分组
function pickGroup(groupId) {
  const agentId = groupDialog.value.agentId
  if (agentId && groupId) emit('addAgentToGroup', { agentId, groupId })
  closeGroupDialog()
}

// 新建分组并加入
function createGroupAndAdd() {
  const agentId = groupDialog.value.agentId
  const name = String(groupDialog.value.newGroupName || '').trim()
  if (!agentId || !name) return
  emit('addAgentToGroup', { agentId, newGroupName: name })
  closeGroupDialog()
}

// ===== 宠物「从分组移出」弹层 =====
// 只列出该 Agent 当前所在的分组，点击即移出
const removeGroupDialog = ref({ visible: false, agentId: '', agentName: '' })

// 该 Agent 当前所在的分组列表
const removeGroupOptions = computed(() => {
  const agentId = removeGroupDialog.value.agentId
  if (!agentId) return []
  return (props.agentGroups || []).filter(g => (g.agentIds || []).includes(agentId))
})

function openRemoveGroupDialog(agentId, agentName) {
  if (!agentId) return
  removeGroupDialog.value = { visible: true, agentId, agentName: agentName || agentId }
}

function closeRemoveGroupDialog() {
  if (removeGroupDialog.value.visible) removeGroupDialog.value.visible = false
}

// 从指定分组移出
function pickRemoveGroup(groupId) {
  const agentId = removeGroupDialog.value.agentId
  if (agentId && groupId) emit('removeAgentFromGroup', { agentId, groupId })
  closeRemoveGroupDialog()
}

// ===== 安装浏览器插件弹层 =====
// 展示安装步骤说明，并提供「下载插件包」按钮（实际下载由父组件注入的 downloadExtension 完成）
const installDialog = ref({ visible: false, downloading: false, error: '' })

function openInstallExtensionDialog() {
  installDialog.value = { visible: true, downloading: false, error: '' }
  refreshExtensionVersion()
}

function closeInstallDialog() {
  if (installDialog.value.visible) installDialog.value.visible = false
}

async function downloadExtension() {
  if (installDialog.value.downloading) return
  if (typeof props.downloadExtension !== 'function') {
    installDialog.value.error = '当前环境不支持下载，请从源码目录 browser_extension/ 手动加载'
    return
  }
  installDialog.value.downloading = true
  installDialog.value.error = ''
  try {
    await props.downloadExtension()
  } catch (e) {
    installDialog.value.error = (e && e.message) ? e.message : '下载失败，请稍后重试'
  } finally {
    installDialog.value.downloading = false
  }
}

// ===== 扩展版本检测 =====
// 网关打包版本与在线扩展版本比对：任一缺失时不判定为需升级
const extensionVersion = ref({ latest: '', current: [], outdated: false, checked: false })

function isVersionOutdated(current, latest) {
  if (!current || !latest) return false
  return String(current).trim() !== String(latest).trim()
}

async function refreshExtensionVersion() {
  if (typeof props.checkExtensionVersion !== 'function') return
  let info = null
  try {
    info = await props.checkExtensionVersion()
  } catch (e) {
    // 轮询场景下异常不得中断定时器，也不应影响弹层展示
    return
  }
  if (!info) {
    extensionVersion.value = { latest: '', current: [], outdated: false, checked: true }
    return
  }
  const latest = info.latestVersion || ''
  const current = (info.sessions || [])
    .map(s => (s && s.extension_version) ? String(s.extension_version) : '')
    .filter(Boolean)
  extensionVersion.value = {
    latest,
    current,
    outdated: current.some(v => isVersionOutdated(v, latest)),
    checked: true
  }
}

// 扩展版本轮询：挂载后立即检测一次，之后每 5 分钟复查，
// 使「安装浏览器插件」按钮上的更新红点无需打开弹层即可生效
const EXTENSION_VERSION_POLL_MS = 5 * 60 * 1000
let extensionVersionTimer = null

function startExtensionVersionPolling() {
  refreshExtensionVersion()
  extensionVersionTimer = setInterval(
    refreshExtensionVersion,
    EXTENSION_VERSION_POLL_MS,
  )
}

function stopExtensionVersionPolling() {
  if (extensionVersionTimer) {
    clearInterval(extensionVersionTimer)
    extensionVersionTimer = null
  }
}

// 点击菜单项：按菜单来源分派给父组件执行，然后关闭菜单
function onContextAction(act) {
  if (!act || act.enabled === false) return
  if (contextMenu.value.kind === 'node') {
    if (act.id === 'node-rename') {
      // 重命名在大厅内弹输入框，不走父组件的节点动作分发
      openRenameDialog(contextMenu.value.nodeId, contextMenu.value.name)
    } else {
      emit('nodeContextRun', { action: act, nodeId: contextMenu.value.nodeId })
    }
  } else if (act.id === 'pet-add-to-group') {
    // 添加到分组在大厅内弹分组选择框
    openGroupDialog(contextMenu.value.agentId, contextMenu.value.name)
  } else if (act.id === 'pet-remove-from-group') {
    // 从分组移出在大厅内弹分组列表（仅该 Agent 所在分组）
    openRemoveGroupDialog(contextMenu.value.agentId, contextMenu.value.name)
  } else {
    emit('contextRun', act)
  }
  closeContextMenu()
}

// 拖动状态
const DRAG_THRESHOLD = 4 // 超过该位移视为拖动而非点击
let dragState = null // { pet, startX, startY, offsetX, offsetY, moved }

function onPetPointerDown(pet, event) {
  // 仅响应鼠标左键 / 触摸 / 笔
  if (event.button !== undefined && event.button !== 0) return
  const stage = stageRef.value
  if (!stage) return
  // 触摸/笔：阻止浏览器接管手势（滚动、缩放），否则 pointermove 会被 pointercancel 打断
  if (event.pointerType && event.pointerType !== 'mouse') {
    event.preventDefault()
  }
  const rect = stage.getBoundingClientRect()
  dragState = {
    pet,
    startX: event.clientX,
    startY: event.clientY,
    offsetX: event.clientX - rect.left - pet.x,
    offsetY: event.clientY - rect.top - pet.y,
    moved: false,
    rect,
    pointerId: event.pointerId,
    target: event.currentTarget,
  }
  // 捕获指针：手指移出宠物元素后仍能持续收到 pointermove，移动端拖动更顺畅
  if (event.pointerId !== undefined && event.currentTarget && event.currentTarget.setPointerCapture) {
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch (e) {
      /* 忽略不支持捕获的场景 */
    }
  }
  window.addEventListener('pointermove', onPetPointerMove)
  window.addEventListener('pointerup', onPetPointerUp)
  window.addEventListener('pointercancel', onPetPointerCancel)
}

function onPetPointerMove(event) {
  if (!dragState) return
  const { pet } = dragState
  const dx = event.clientX - dragState.startX
  const dy = event.clientY - dragState.startY
  if (!dragState.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
  dragState.moved = true
  pet.dragging = true
  // 拖动时取消待执行的单击
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  const rect = dragState.rect
  const nx = event.clientX - rect.left - dragState.offsetX
  const ny = event.clientY - rect.top - dragState.offsetY
  const clamped = clampPos(nx, ny)
  pet.x = clamped.x
  pet.y = clamped.y
  pet.target = { x: clamped.x, y: clamped.y }
  // 拖动过程中同步重算堆叠容器位置，保证输入/输出框始终在可视范围内
  layoutPetStack(pet)
  // 触摸拖动时阻止页面滚动
  if (event.cancelable && event.pointerType && event.pointerType !== 'mouse') {
    event.preventDefault()
  }
}

function releasePointerCapture() {
  if (!dragState) return
  const { pointerId, target } = dragState
  if (pointerId !== undefined && target && target.releasePointerCapture) {
    try {
      target.releasePointerCapture(pointerId)
    } catch (e) {
      /* 已释放或未捕获时忽略 */
    }
  }
}

function onPetPointerUp() {
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('pointercancel', onPetPointerCancel)
  if (!dragState) return
  const { pet, moved } = dragState
  releasePointerCapture()
  dragState = null
  if (pet.dragging) {
    pet.dragging = false
    // 拖动结束时记录落点，避免下次挂载回到旧位置
    rememberPosition(pet)
    // 松开后从当前位置继续飘动
    pet.target = pickTarget()
    return
  }
  // 未发生拖动：视为单击
  if (!moved) onPetClick(pet)
}

// 指针被浏览器取消（如触摸被系统手势抢占）时，安全复位，避免 dragState 悬挂
function onPetPointerCancel() {
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('pointercancel', onPetPointerCancel)
  if (!dragState) return
  const { pet } = dragState
  releasePointerCapture()
  dragState = null
  if (pet.dragging) {
    pet.dragging = false
    rememberPosition(pet)
    pet.target = pickTarget()
  }
}

// 单击：延时判定，避免与双击冲突（双击时取消单击动作）
// 语义为「总是选中并展开」；取消选中只通过点击舞台空白处（onStageClick）
let clickTimer = null
function onPetClick(pet) {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  clickTimer = setTimeout(() => {
    clickTimer = null
    if (activePetId.value === pet.agentId && pet.active) return
    openPanel(pet)
  }, 250)
}

// 双击：进入该 Agent 的详细视图（取消待执行的单击）
function onPetDblClick(pet) {
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  closePanel(pet)
  emit('selectAgent', pet.agentId)
}

function openPanel(pet, focusInput = false) {
  // 同一时刻只展开一只
  if (activePetId.value && activePetId.value !== pet.agentId) {
    const prev = petAgents.value.find(p => p.agentId === activePetId.value)
    if (prev) closePanel(prev)
  }
  activePetId.value = pet.agentId
  pet.active = true
  pet.typing = false
  // 激活即打开该 Agent 的输出显示：仅 pet.active 只能让 stack 容器显示，
  // 输出气泡仍受 isOutputHidden 拦截，故需把该 Agent 移出隐藏集合（取消激活时不回滚）
  if (hiddenOutputIds.value.has(pet.agentId)) {
    const next = new Set(hiddenOutputIds.value)
    next.delete(pet.agentId)
    hiddenOutputIds.value = next
    saveHiddenOutputs()
  }
  refreshPetData(pet)
  // 聚焦输入框的两种情形：
  // 1) 键盘方向键选中（focusInput=true）：键盘导航意图明确，始终把焦点交给输入框；
  // 2) 鼠标点开且该 Agent 有待处理的输入请求：此时才自动聚焦，避免打断用户查看输出。
  if (focusInput) {
    focusPetInput(pet.agentId, true)
  } else if (pet.hasInputRequest && pet.inputMode !== 'confirm') {
    focusPetInput(pet.agentId, true)
  }
}

function closePanel(pet) {
  if (!pet) return
  pet.active = false
  pet.typing = false
  // 保留 pet.inputText：收起面板（如点击空白处取消激活）不应丢失用户未发送的草稿
  if (activePetId.value === pet.agentId) activePetId.value = null
}

// 退出当前宠物选中状态（供父组件 ESC 快捷键调用）：
// 无选中时返回 false，便于父组件判断 ESC 是否已被消费
function closeActivePanel() {
  closeContextMenu()
  if (!activePetId.value) return false
  const pet = petAgents.value.find(p => p.agentId === activePetId.value)
  if (pet) closePanel(pet)
  else activePetId.value = null
  return true
}

// 激活状态下「隐藏该 Agent 输出并取消选中」（供父组件 Ctrl+W 调用）：
// 与 toggleAgentOutput 不同，这里是幂等置为隐藏，重复按下不会把输出重新显示出来
function hideActiveOutputAndClose() {
  const agentId = activePetId.value
  if (!agentId) return false
  if (!hiddenOutputIds.value.has(agentId)) {
    const next = new Set(hiddenOutputIds.value)
    next.add(agentId)
    hiddenOutputIds.value = next
    saveHiddenOutputs()
  }
  const pet = petAgents.value.find(p => p.agentId === agentId)
  if (pet) closePanel(pet)
  else activePetId.value = null
  return true
}

function onInputPointerDown(pet) {
  pet.typing = true
}

// 多行输入框快捷键，与 Agent Panel 保持一致：
// Ctrl+Enter / Ctrl+D 发送；Enter 换行；上下箭头在首/末行时翻阅历史；Ctrl+C 空输入时发送完成信号
function handlePetKeydown(pet, event) {
  if (handlePetCtrlKeydown(pet, event)) return
  if (event.key === '@') {
    // 复用 @ 按钮逻辑：先把 @ 真正写入输入框，再触发补全。
    // 这样取消补全时 @ 会保留在输入框中（父组件对 lobby 来源不会补插 @）
    event.preventDefault()
    insertAtSymbol(pet)
    return
  }
  if (event.ctrlKey && (event.key === 'Enter' || event.key.toLowerCase() === 'd')) {
    event.preventDefault()
    submitPet(pet)
    return
  }
  if (event.key === 'ArrowUp' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    const textarea = event.target
    if (isCursorAtFirstLine(textarea)) {
      event.preventDefault()
      if (props.historyNav) {
        const val = props.historyNav(pet.agentId, 'up', pet.inputText || '')
        if (typeof val === 'string') pet.inputText = val
      }
    }
    return
  }
  if (event.key === 'ArrowDown' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    const textarea = event.target
    if (isCursorAtLastLine(textarea)) {
      event.preventDefault()
      if (props.historyNav) {
        const val = props.historyNav(pet.agentId, 'down', pet.inputText || '')
        if (typeof val === 'string') pet.inputText = val
      }
    }
    return
  }
  if (event.ctrlKey && event.key === 'c') {
    const hasText = (pet.inputText || '').trim().length > 0
    // 仅当没有选中文本且输入为空时，才拦截 Ctrl+C 发送完成信号
    const hasSelection = event.target.selectionStart !== event.target.selectionEnd
    if (!hasText && !hasSelection && pet.inputMode === 'multi') {
      event.preventDefault()
      emit('complete', pet.agentId)
    }
  }
}

// 单行输入框快捷键：Enter 发送；@ 打开补全
function handlePetSingleKeydown(pet, event) {
  if (handlePetCtrlKeydown(pet, event)) return
  if (event.key === '@') {
    // 与多行输入一致：先写入 @ 再触发补全，取消补全时 @ 得以保留
    event.preventDefault()
    insertAtSymbol(pet)
    return
  }
  if (event.key === 'Enter' && !event.ctrlKey && !event.altKey && !event.metaKey) {
    event.preventDefault()
    submitPet(pet)
  }
}

// 右 Ctrl 快速双击：发送（与 Agent Panel 行为一致）
const DOUBLE_TAP_MS = 300 // 双击判定窗口
const QUICK_TAP_MS = 250  // 单次「快速按下」判定
let ctrlDownTime = 0
let lastQuickTapTime = 0

function handlePetCtrlKeydown(pet, event) {
  if (event.code !== 'ControlRight') return false
  event.preventDefault()
  const now = Date.now()
  // 上一轮是快速单击，且间隔在双击窗口内 → 判定为双击发送
  if (lastQuickTapTime && now - lastQuickTapTime < DOUBLE_TAP_MS) {
    lastQuickTapTime = 0
    submitPet(pet)
    return true
  }
  ctrlDownTime = now
  return true
}

function handlePetCtrlKeyup(event) {
  if (event.code !== 'ControlRight') return
  event.preventDefault()
  // 按下时间很短视为「快速单击」，为下一次双击判定做记录
  if (ctrlDownTime && Date.now() - ctrlDownTime < QUICK_TAP_MS) {
    lastQuickTapTime = Date.now()
  } else {
    lastQuickTapTime = 0
  }
  ctrlDownTime = 0
}

// 输入变化：检测是否刚输入 @（含中文输入法），触发补全
function handlePetInput(pet, event) {
  const target = event.target
  const cursorPosition = target.selectionStart
  const textBeforeCursor = target.value.substring(0, cursorPosition)
  if (textBeforeCursor.endsWith('@')) {
    emit('openCompletions', pet.agentId, cursorPosition - 1)
  }
}

// 移动端「@」按钮：在光标处插入 @ 并触发补全（等价于手动输入 @）
function insertAtSymbol(pet) {
  if (!pet) return
  const el = stageRef.value && stageRef.value.querySelector(`[data-pet-input="${pet.agentId}"]`)
  const value = pet.inputText || ''
  const start = el && typeof el.selectionStart === 'number' ? el.selectionStart : value.length
  const end = el && typeof el.selectionEnd === 'number' ? el.selectionEnd : value.length
  const next = value.substring(0, start) + '@' + value.substring(end)
  pet.inputText = next
  pet.typing = true
  const atPos = start
  requestAnimationFrame(() => {
    const target = stageRef.value && stageRef.value.querySelector(`[data-pet-input="${pet.agentId}"]`)
    if (target) {
      try { target.setSelectionRange(atPos + 1, atPos + 1) } catch (e) { /* ignore */ }
      target.focus()
    }
  })
  emit('openCompletions', pet.agentId, atPos)
}

function isCursorAtFirstLine(textarea) {
  const pos = textarea.selectionStart
  return !textarea.value.substring(0, pos).includes('\n')
}

function isCursorAtLastLine(textarea) {
  const pos = textarea.selectionEnd
  return !textarea.value.substring(pos).includes('\n')
}

function submitPet(pet) {
  const text = pet.inputMode === 'single' ? pet.inputText : pet.inputText.trim()
  if (pet.inputMode !== 'single' && !text) return
  emit('sendInput', pet.agentId, text, pet.inputMode)
  pet.inputText = ''
  pet.typing = false
  refreshPetData(pet)
}

// 完成：与 Panel 的「完成」按钮一致，发送完成信号（由父组件处理）
function completePet(pet) {
  if (!pet || !pet.agentId) return
  emit('complete', pet.agentId)
  refreshPetData(pet)
}

function submitConfirm(pet, confirmed) {
  emit('sendInput', pet.agentId, confirmed ? 'y' : 'n', 'confirm')
  refreshPetData(pet)
}

// 仪表盘时间：独立 1s 定时器刷新（refreshLoop 在精灵隐藏时会提前返回，不能依赖它）
const dashNow = ref(new Date())
let dashTimer = null
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
function pad2(n) {
  return String(n).padStart(2, '0')
}
const dashTime = computed(() => {
  const d = dashNow.value
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
})
const dashDate = computed(() => {
  const d = dashNow.value
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${WEEKDAYS[d.getDay()]}`
})

// 定时刷新：状态灯、输出气泡、输入态（输出/确认常驻显示，需对所有宠物刷新）
let refreshTimer = null
function refreshLoop() {
  // 精灵隐藏时无需刷新任何宠物数据
  if (!showPets.value) return
  for (const pet of petAgents.value) {
    const agent = (props.agents || []).find(a => a.agent_id === pet.agentId)
    if (agent && props.getStatusClass) {
      const statusClass = props.getStatusClass(agent)
      if (statusClass !== pet.statusClass) {
        pet.statusClass = statusClass
        pet.classes = `status-${statusClass}${pet.faceLeft ? ' face-left' : ''}`
      }
    }
    // 正在输入时不覆盖输入框内容，但仍刷新输出/确认态
    if (!pet.typing) {
      // 输出被隐藏且未展开交互面板时，跳过较重的输出（markdown）刷新；
      // 已激活（展开交互面板）的宠物仍需刷新，保证其输出面板实时更新
      if (!isOutputHidden(pet.agentId) || pet.active) {
        refreshPetData(pet)
      } else {
        layoutPetStack(pet)
      }
    }
  }
}

onMounted(() => {
  measureStage()
  syncPets()
  updateIsMobile()
  rafId = requestAnimationFrame(step)
  refreshTimer = setInterval(refreshLoop, 800)
  dashTimer = setInterval(() => { dashNow.value = new Date() }, 1000)
  startExtensionVersionPolling()
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('resize', closeContextMenu)
  window.addEventListener('resize', updateIsMobile)
  window.addEventListener('blur', closeContextMenu)
  if (typeof ResizeObserver !== 'undefined' && stageRef.value) {
    resizeObserver = new ResizeObserver(() => measureStage())
    resizeObserver.observe(stageRef.value)
  }
})

// 当前应响应确认快捷键的宠物：确认面板无需展开即显示，
// 故优先取已展开的那只，否则取第一只处于确认态的宠物
function activeConfirmPet() {
  const confirming = petAgents.value.filter(p => p.inputMode === 'confirm')
  if (confirming.length === 0) return null
  if (activePetId.value) {
    const active = confirming.find(p => p.agentId === activePetId.value)
    if (active) return active
  }
  return confirming[0]
}

// 是否正在弹层内输入（重命名/新建分组等），此时不应响应确认快捷键
function isTypingInDialog(e) {
  const el = e.target
  if (!el || !el.tagName) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || el.isContentEditable
}

// 全局按键：Esc 关闭右键菜单与弹层；确认态下 y/n/Enter 响应确认（与 Panel 一致）
function onGlobalKeydown(e) {
  if (e.key === 'Escape') {
    closeContextMenu()
    closeRenameDialog()
    closeGroupDialog()
    closeRemoveGroupDialog()
    return
  }
  // 弹层内输入时不拦截，避免误触发确认
  if (isTypingInDialog(e)) return
  if (e.ctrlKey || e.altKey || e.metaKey) return
  const pet = activeConfirmPet()
  if (!pet) return
  if (e.key === 'y' || e.key === 'Y') {
    e.preventDefault()
    submitConfirm(pet, true)
    return
  }
  if (e.key === 'n' || e.key === 'N') {
    e.preventDefault()
    submitConfirm(pet, false)
    return
  }
  if (e.key === 'Enter') {
    e.preventDefault()
    submitConfirm(pet, pet.confirmDefault !== false)
  }
}

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = null
  // 离开大厅（组件卸载）时统一落盘一次宠物位置
  savePositions()
  window.removeEventListener('pointermove', onPetPointerMove)
  window.removeEventListener('pointerup', onPetPointerUp)
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('resize', closeContextMenu)
  window.removeEventListener('resize', updateIsMobile)
  window.removeEventListener('blur', closeContextMenu)
  dragState = null
  if (clickTimer) {
    clearTimeout(clickTimer)
    clickTimer = null
  }
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (dashTimer) {
    clearInterval(dashTimer)
    dashTimer = null
  }
  stopExtensionVersionPolling()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})

// agents 变化时同步宠物实例
watch(() => props.agents, () => syncPets(), { deep: false })

// 选中的宠物变化时通知父组件（用于「当前 Agent」相关菜单）
// immediate: 组件挂载时同步一次（清空父组件中可能残留的旧选中态）
watch(activePetId, (id) => {
  emit('activePetChange', id || null)
}, { immediate: true })

// 选中的节点变化时通知父组件（用于「节点」相关快捷键与命令面板）
// immediate: 组件挂载时同步一次（清空父组件中可能残留的旧选中态）
watch(activeNodeId, (id) => {
  emit('activeNodeChange', id || null)
}, { immediate: true })

// 供父组件写回补全文本：把 @ 及后续搜索词替换为补全值，并同步 DOM 光标
function insertCompletionText(agentId, text, cursorPos, hasAtSymbol) {
  const pet = petAgents.value.find(p => p.agentId === agentId)
  if (!pet) return
  const value = pet.inputText || ''
  let start
  let end
  if (hasAtSymbol && typeof cursorPos === 'number' && cursorPos >= 0 && cursorPos <= value.length) {
    // cursorPos 指向 @ 符号所在位置：替换掉该 @
    start = cursorPos
    end = cursorPos + 1
  } else {
    // 无 @ 可删：在记录的光标处插入，未记录时追加到末尾
    start = (typeof cursorPos === 'number' && cursorPos >= 0 && cursorPos <= value.length) ? cursorPos : value.length
    end = start
  }
  const inserted = `'${text}'`
  const next = value.substring(0, start) + inserted + value.substring(end)
  pet.inputText = next
  pet.typing = true
  const newPos = start + inserted.length
  requestAnimationFrame(() => {
    const el = stageRef.value && stageRef.value.querySelector(`[data-pet-input="${agentId}"]`)
    if (el) {
      el.value = next
      try { el.setSelectionRange(newPos, newPos) } catch (e) { /* ignore */ }
      el.focus()
    }
  })
}

// 供父组件清除节点选中（如执行完节点操作后）
function closeActiveNode() {
  activeNodeId.value = null
}

// 供父组件调用：按方向选中 Agent（Ctrl+Alt+方向键）
// 有选中：以当前选中宠物的中心为基准，选该方向上「横向/纵向偏移最小、再按垂直/水平距离最近」的宠物。
// 无选中：从该方向的反向边缘开始——→ 取全场最左的第一只、← 取最右、↓ 取最上、↑ 取最下，
//         之后连续按同一方向即可依次向该方向推进。
// 返回 true 表示已消费该请求（大厅无宠物时返回 false，交由父组件走区域焦点跳转）
function selectAgentInDirection(dir) {
  const pets = petAgents.value
  if (!pets.length) return false
  const cx = (pet) => pet.x + PET_W / 2
  const cy = (pet) => pet.y + PET_H / 2
  const current = pets.find(p => p.agentId === activePetId.value) || null

  let best = null
  let bestPrimary = Infinity
  let bestSecondary = Infinity
  for (const pet of pets) {
    if (current && pet.agentId === current.agentId) continue
    let primary
    let secondary
    if (!current) {
      // 无选中：不做方向过滤，直接按「该方向的反向边缘」排序，取第一只
      // left → 取最右（x 最大）；right → 取最左（x 最小）；up → 取最下（y 最大）；down → 取最上（y 最小）
      if (dir === 'left') {
        primary = -cx(pet)
        secondary = cy(pet)
      } else if (dir === 'right') {
        primary = cx(pet)
        secondary = cy(pet)
      } else if (dir === 'up') {
        primary = -cy(pet)
        secondary = cx(pet)
      } else {
        primary = cy(pet)
        secondary = cx(pet)
      }
    } else {
      const dx = cx(pet) - cx(current)
      const dy = cy(pet) - cy(current)
      if (dir === 'left') {
        if (dx >= 0) continue
        primary = -dx
        secondary = Math.abs(dy)
      } else if (dir === 'right') {
        if (dx <= 0) continue
        primary = dx
        secondary = Math.abs(dy)
      } else if (dir === 'up') {
        if (dy >= 0) continue
        primary = -dy
        secondary = Math.abs(dx)
      } else {
        if (dy <= 0) continue
        primary = dy
        secondary = Math.abs(dx)
      }
    }
    if (primary < bestPrimary || (primary === bestPrimary && secondary < bestSecondary)) {
      best = pet
      bestPrimary = primary
      bestSecondary = secondary
    }
  }
  // 该方向上没有宠物：保持当前选中不变
  if (!best) return true
  // 与单击一致：选中并展开面板（同一时刻只展开一只）；键盘选中后聚焦输入框
  openPanel(best, true)
  return true
}

// 供父组件调用：按方向选中节点（Ctrl+Shift+方向键）
// 有选中：以当前选中节点为基准，选该方向上「横向/纵向偏移最小、再按垂直/水平距离最近」的节点。
// 无选中：从该方向的反向边缘开始——→ 取最左的第一只、← 取最右、↓ 取最上、↑ 取最下。
// 返回 true 表示已消费该请求（大厅无节点时返回 false）
function selectNodeInDirection(dir) {
  const nodes = nodeItems.value
  if (!nodes.length) return false
  const current = nodes.find(n => n.node_id === activeNodeId.value) || null

  let best = null
  let bestPrimary = Infinity
  let bestSecondary = Infinity
  for (const node of nodes) {
    if (current && node.node_id === current.node_id) continue
    let primary
    let secondary
    if (!current) {
      // 无选中：不做方向过滤，直接按「该方向的反向边缘」排序，取第一只
      if (dir === 'left') {
        primary = -node.x
        secondary = node.y
      } else if (dir === 'right') {
        primary = node.x
        secondary = node.y
      } else if (dir === 'up') {
        primary = -node.y
        secondary = node.x
      } else {
        primary = node.y
        secondary = node.x
      }
    } else {
      const dx = node.x - current.x
      const dy = node.y - current.y
      if (dir === 'left') {
        if (dx >= 0) continue
        primary = -dx
        secondary = Math.abs(dy)
      } else if (dir === 'right') {
        if (dx <= 0) continue
        primary = dx
        secondary = Math.abs(dy)
      } else if (dir === 'up') {
        if (dy >= 0) continue
        primary = -dy
        secondary = Math.abs(dx)
      } else {
        if (dy <= 0) continue
        primary = dy
        secondary = Math.abs(dx)
      }
    }
    if (primary < bestPrimary || (primary === bestPrimary && secondary < bestSecondary)) {
      best = node
      bestPrimary = primary
      bestSecondary = secondary
    }
  }
  // 该方向上没有节点：保持当前选中不变
  if (!best) return true
  activeNodeId.value = best.node_id
  return true
}

// 供父组件调用：重命名节点（不传 nodeId 时取当前选中的节点）
// 返回 true 表示已消费该请求（无节点或弹层已打开时返回 false）
function renameActiveNode(nodeId) {
  const targetId = nodeId || activeNodeId.value
  if (!targetId) return false
  if (renameDialog.value.visible) return true
  const node = (props.nodes || []).find(n => n.node_id === targetId)
  openRenameDialog(targetId, (node && (node.short || node.name)) || targetId)
  return true
}

defineExpose({ insertCompletionText, toggleAgentOutput, isOutputHidden, openInstallExtensionDialog, closeActivePanel, hideActiveOutputAndClose, closeActiveNode, renameActiveNode, selectAgentInDirection, selectNodeInDirection, toggleAllOutputs })
</script>

<style scoped>
.pet-lobby {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--tile-radius, 12px);
}

/* 地板风格背景：透视网格 */
.pet-lobby-floor {
  position: absolute;
  inset: -20%;
  background-image:
    linear-gradient(rgba(32, 200, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(32, 200, 255, 0.08) 1px, transparent 1px);
  background-size: 56px 56px, 56px 56px;
  mask-image: radial-gradient(circle at 50% 55%, #000 0%, transparent 78%);
  -webkit-mask-image: radial-gradient(circle at 50% 55%, #000 0%, transparent 78%);
  animation: lobbyFloorDrift 40s linear infinite;
  pointer-events: none;
}

@keyframes lobbyFloorDrift {
  from { background-position: 0 0, 0 0; }
  to { background-position: 56px 56px, 56px 56px; }
}

/* 节点与连线层：位于地板之上、宠物之下，不拦截交互 */
.pet-lobby-topology {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  /* 主角是 Agent：整体弱化节点与连线，避免喧宾夺主 */
  opacity: 0.4;
}

.pet-lobby-links {
  position: absolute;
  left: 0;
  top: 0;
  overflow: visible;
}

.lobby-link {
  stroke-linecap: round;
}

.lobby-link.is-flow {
  stroke-dasharray: 8 6;
  animation: lobby-flow 1.2s linear infinite;
}

@keyframes lobby-flow {
  to { stroke-dashoffset: -14; }
}

/* 节点：服务器机箱造型（参考大屏拓扑，但整体弱化以突出 Agent） */
.lobby-node {
  /* 容器层整体 pointer-events: none（不拦截宠物交互），此处单独恢复节点可点击 */
  pointer-events: auto;
  cursor: pointer;
  /* 禁用双击时的默认选中高亮 */
  user-select: none;
  -webkit-user-select: none;
}
.lobby-node-body {
  transition: filter 0.15s ease;
}

/* 选中的节点：机箱描边加粗发光 + 轻微放大，明确当前节点操作的作用对象 */
.lobby-node.active .lobby-node-body {
  stroke-width: 2.6;
  filter: drop-shadow(0 0 6px currentColor) brightness(1.25);
}
.lobby-node.active .lobby-node-label {
  fill: rgba(220, 245, 255, 0.95);
  font-weight: 600;
}
.lobby-node.active .lobby-node-count {
  fill: rgba(200, 235, 255, 0.8);
}

.lobby-node-led {
  filter: drop-shadow(0 0 2px currentColor);
  animation: lobby-led-blink 2.2s ease-in-out infinite;
}

@keyframes lobby-led-blink {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 0.25; }
}

.lobby-node-label {
  font-size: 11px;
  fill: rgba(180, 220, 240, 0.55);
  pointer-events: none;
}

.lobby-node-count {
  font-size: 10px;
  fill: rgba(150, 190, 210, 0.45);
  pointer-events: none;
}

.lobby-node-version {
  font-size: 9px;
  fill: rgba(150, 190, 210, 0.4);
  pointer-events: none;
}

/* 版本与 master 不一致：标红提示该节点未更新 */
.lobby-node-version.mismatch {
  fill: #ff5d6c;
  font-weight: 600;
}

.lobby-node.is-center .lobby-node-label {
  fill: rgba(255, 232, 154, 0.7);
}

.lobby-node.is-center .lobby-node-count {
  fill: rgba(255, 232, 154, 0.6);
  opacity: 0.9;
}

.lobby-node.is-center .lobby-node-version {
  fill: rgba(255, 232, 154, 0.5);
}

/* 地板上的 Slogan：刻在地面、经年磨损的沧桑质感 */
.pet-lobby-slogan {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%) perspective(600px) rotateX(52deg);
  transform-origin: center center;
  pointer-events: none;
  user-select: none;
  z-index: 1;
  opacity: 0.5;
}

.pet-lobby-slogan-text {
  display: block;
  font-size: clamp(28px, 5.2vw, 72px);
  font-weight: 800;
  letter-spacing: 0.22em;
  white-space: nowrap;
  /* 文字本体：低对比的灰蓝，像被岁月磨淡的刻痕 */
  color: rgba(120, 160, 190, 0.32);
  /* 上方高光 + 下方阴影，营造凹陷雕刻感 */
  text-shadow:
    0 1px 0 rgba(0, 0, 0, 0.55),
    0 -1px 1px rgba(150, 200, 230, 0.12),
    0 0 18px rgba(32, 200, 255, 0.08);
  /* 用噪点/划痕遮罩制造斑驳脱落 */
  -webkit-mask-image:
    repeating-linear-gradient(96deg, #000 0 3px, rgba(0,0,0,0.35) 3px 5px, #000 5px 11px),
    radial-gradient(ellipse 140% 90% at 42% 46%, #000 30%, rgba(0,0,0,0.25) 62%, transparent 88%);
  -webkit-mask-composite: source-in;
  mask-image:
    repeating-linear-gradient(96deg, #000 0 3px, rgba(0,0,0,0.35) 3px 5px, #000 5px 11px),
    radial-gradient(ellipse 140% 90% at 42% 46%, #000 30%, rgba(0,0,0,0.25) 62%, transparent 88%);
  mask-composite: intersect;
  animation: lobbySloganWeather 9s ease-in-out infinite alternate;
}

/* 沧桑感：明暗与磨损缓慢呼吸，仿佛光影掠过旧地砖 */
@keyframes lobbySloganWeather {
  from {
    opacity: 0.72;
    text-shadow:
      0 1px 0 rgba(0, 0, 0, 0.55),
      0 -1px 1px rgba(150, 200, 230, 0.12),
      0 0 18px rgba(32, 200, 255, 0.08);
  }
  to {
    opacity: 1;
    text-shadow:
      0 1px 0 rgba(0, 0, 0, 0.7),
      0 -1px 1px rgba(150, 200, 230, 0.2),
      0 0 26px rgba(32, 200, 255, 0.14);
  }
}

/* 叠加一层极淡的划痕/污渍纹理，强化做旧痕迹 */
.pet-lobby-slogan::after {
  content: '';
  position: absolute;
  inset: -10% -6%;
  background:
    repeating-linear-gradient(78deg, transparent 0 6px, rgba(0, 0, 0, 0.18) 6px 7px, transparent 7px 15px),
    repeating-linear-gradient(-64deg, transparent 0 9px, rgba(180, 210, 230, 0.06) 9px 10px, transparent 10px 22px);
  mix-blend-mode: overlay;
  pointer-events: none;
}

.pet-lobby-glow {
  position: absolute;
  width: 50vmax;
  height: 50vmax;
  border-radius: 50%;
  filter: blur(48px);
  opacity: 0.4;
  pointer-events: none;
}
.pet-lobby-glow-a {
  top: -20%;
  left: -12%;
  background: radial-gradient(circle, rgba(32, 200, 255, 0.22) 0%, transparent 62%);
}
.pet-lobby-glow-b {
  bottom: -24%;
  right: -14%;
  background: radial-gradient(circle, rgba(54, 255, 124, 0.16) 0%, transparent 62%);
}

/* ===== 左上角仪表（当前时间 + 网关地址）：与节点拓扑同风格，弱化处理 ===== */
.pet-lobby-dash {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(8, 18, 30, 0.55);
  border: 1px solid rgba(32, 200, 255, 0.18);
  backdrop-filter: blur(4px);
  pointer-events: none;
  user-select: none;
  opacity: 0.55;
  font-variant-numeric: tabular-nums;
}
.lobby-dash-time {
  font-size: 20px;
  line-height: 1.1;
  letter-spacing: 1px;
  color: rgba(180, 220, 240, 0.8);
}
.lobby-dash-date {
  margin-top: 2px;
  font-size: 10px;
  color: rgba(150, 190, 210, 0.5);
}
.lobby-dash-divider {
  height: 1px;
  margin: 7px 0 6px;
  background: linear-gradient(90deg, rgba(32, 200, 255, 0.28), transparent);
}
.lobby-dash-row {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  line-height: 1.6;
  color: rgba(150, 190, 210, 0.55);
}
.lobby-dash-label {
  flex: none;
  opacity: 0.75;
}
.lobby-dash-value {
  color: rgba(180, 220, 240, 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lobby-dash-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #8a9bb0;
  opacity: 0.7;
  flex: none;
}
/* 连接状态配色：与顶栏状态点语义一致 */
.lobby-dash-dot.is-online {
  background: #34d99b;
}
.lobby-dash-dot.is-connecting,
.lobby-dash-dot.is-reconnecting {
  background: #ffb347;
}
.lobby-dash-dot.is-offline {
  background: #ff5d6c;
}
/* Agent 各状态数量：彩色圆点 + 数字，紧凑排列 */
.lobby-dash-agents {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.lobby-dash-agent-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.lobby-dash-agent-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  opacity: 0.8;
  flex: none;
}
.lobby-dash-agent-num {
  color: rgba(180, 220, 240, 0.7);
}

/* ===== 右上角开关组（游走 + 精灵显示模式） ===== */
.pet-lobby-toggles {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pet-lobby-roam-toggle,
.pet-lobby-display-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  color: #d6f2ff;
  background: rgba(10, 24, 38, 0.86);
  border: 1px solid rgba(32, 200, 255, 0.4);
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.pet-lobby-roam-toggle:hover,
.pet-lobby-display-toggle:hover {
  background: rgba(16, 40, 60, 0.95);
  border-color: rgba(32, 200, 255, 0.75);
}
.pet-lobby-roam-toggle.off,
.pet-lobby-display-toggle.off {
  color: #9fb4c4;
  border-color: rgba(120, 140, 160, 0.45);
}
.pet-lobby-roam-icon,
.pet-lobby-display-icon {
  font-size: 13px;
  line-height: 1;
}

/* 移动端：顶部空间有限，开关组仅显示图标，隐藏文字 */
@media (max-width: 768px) {
  .pet-lobby-toggles {
    gap: 6px;
  }
  .pet-lobby-roam-toggle,
  .pet-lobby-display-toggle {
    padding: 6px 8px;
  }
  .pet-lobby-roam-label,
  .pet-lobby-display-label {
    display: none;
  }
  .pet-lobby-roam-icon,
  .pet-lobby-display-icon {
    font-size: 15px;
  }
}

/* ===== 无 Agent 时的空状态引导 ===== */
.pet-lobby-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 30;
  width: min(420px, 86vw);
  padding: 22px 24px;
  text-align: center;
  background: rgba(9, 16, 28, 0.86);
  border: 1px solid rgba(32, 200, 255, 0.28);
  border-radius: var(--tile-radius, 10px);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}
.pet-lobby-empty-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-accent, #20c8ff);
  letter-spacing: 0.02em;
}
.pet-lobby-empty-desc {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: #b9cddd;
}
.pet-lobby-empty-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 16px;
}
.pet-lobby-empty-btn {
  padding: 8px 16px;
  font-size: 13px;
  font-family: inherit;
  color: #d6f2ff;
  background: rgba(10, 24, 38, 0.9);
  border: 1px solid rgba(32, 200, 255, 0.4);
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, filter 0.2s ease;
}
.pet-lobby-empty-btn:hover {
  background: rgba(16, 40, 60, 0.95);
  border-color: rgba(32, 200, 255, 0.8);
}
.pet-lobby-empty-btn.primary {
  color: #060911;
  font-weight: 700;
  background: var(--gradient-accent, linear-gradient(135deg, #20c8ff 0%, #36ff7c 100%));
  border-color: transparent;
}
.pet-lobby-empty-btn.primary:hover {
  filter: brightness(1.08);
}
.pet-lobby-empty-hint {
  margin-top: 14px;
  font-size: 12px;
  color: #8ba3b8;
}
.pet-lobby-empty-hint b {
  color: var(--color-accent, #20c8ff);
}
/* ===== 迷你宠物 ===== */
.lobby-pet {
  position: absolute;
  width: 72px;
  height: 82px;
  cursor: pointer;
  user-select: none;
  pointer-events: auto;
  /* 移动端：禁用浏览器默认触摸手势（滚动/缩放），否则拖动会被系统手势打断 */
  touch-action: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  transition: filter 0.25s ease, opacity 0.25s ease;
  /* 每个宠物建立独立 stacking context，使「本体 + 输出/输入框」作为整体参与层级比较，
     避免 A 的窗口覆盖 B 的宠物、B 的窗口又覆盖 A 的宠物的交叉覆盖 */
  z-index: 1;
}
.lobby-pet:hover {
  filter: brightness(1.15);
}
.lobby-pet.active {
  z-index: 20;
}
/* 有宠物被激活时，其余宠物及其输出/输入框变暗，突出当前交互对象 */
.lobby-pet.dimmed {
  opacity: 0.38;
  filter: brightness(0.55) saturate(0.6);
}
.lobby-pet.dimmed:hover {
  opacity: 0.7;
  filter: brightness(0.9) saturate(0.8);
}
.lobby-pet.dragging {
  cursor: grabbing;
  z-index: 20;
  filter: brightness(1.2);
}

.lobby-pet-inner {
  position: relative;
  width: 100%;
  height: 100%;
}

.lobby-pet-body {
  position: absolute;
  left: 50%;
  bottom: 12px;
  width: 52px;
  height: 46px;
  transform: translateX(-50%);
  animation: lobbyPetBob 2.6s ease-in-out infinite;
}

@keyframes lobbyPetBob {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(-3px); }
}

.lobby-pet-head {
  position: absolute;
  left: 50%;
  top: 0;
  width: 42px;
  height: 37px;
  transform: translateX(-50%);
  background: linear-gradient(160deg, #2ee6ff 0%, #1a9fd6 55%, #0e6f9e 100%);
  border-radius: 50% 50% 46% 46%;
  box-shadow: 0 0 10px rgba(32, 200, 255, 0.45), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.18);
}

.lobby-pet-ear {
  position: absolute;
  top: -8px;
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-bottom: 12px solid #23b9e8;
  filter: drop-shadow(0 0 3px rgba(32, 200, 255, 0.5));
}
.lobby-pet-ear.l { left: 2px; transform: rotate(-18deg); }
.lobby-pet-ear.r { right: 2px; transform: rotate(18deg); }

.lobby-pet-eye {
  position: absolute;
  top: 14px;
  width: 7px;
  height: 8px;
  border-radius: 50%;
  background: #06131f;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.75);
  animation: lobbyPetBlink 4.2s infinite;
}
.lobby-pet-eye.l { left: 10px; }
.lobby-pet-eye.r { right: 10px; }

.lobby-pet-pupil {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(234, 252, 255, 0.9);
  transform: translate(-50%, -50%);
}

@keyframes lobbyPetBlink {
  0%, 92%, 100% { transform: scaleY(1); }
  95% { transform: scaleY(0.1); }
}

.lobby-pet-mouth {
  position: absolute;
  left: 50%;
  top: 27px;
  width: 10px;
  height: 5px;
  transform: translateX(-50%);
  border-bottom: 1.5px solid rgba(6, 19, 31, 0.75);
  border-radius: 0 0 4px 4px;
}

.lobby-pet-tail {
  position: absolute;
  right: -8px;
  bottom: 6px;
  width: 19px;
  height: 19px;
  border: 2px solid #23b9e8;
  border-color: #23b9e8 transparent transparent transparent;
  border-radius: 50%;
  transform-origin: 0% 100%;
  animation: lobbyPetTail 1.6s ease-in-out infinite;
  filter: drop-shadow(0 0 3px rgba(32, 200, 255, 0.45));
}

@keyframes lobbyPetTail {
  0%, 100% { transform: rotate(0deg); }
  50% { transform: rotate(-16deg); }
}

.lobby-pet-shadow {
  position: absolute;
  left: 50%;
  bottom: 8px;
  width: 44px;
  height: 8px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  filter: blur(2px);
  pointer-events: none;
}

/* 朝向翻转 */
.lobby-pet.face-left .lobby-pet-body {
  transform: translateX(-50%) scaleX(-1);
}

.lobby-pet-name {
  position: absolute;
  left: 50%;
  bottom: -4px;
  transform: translateX(-50%);
  max-width: 88px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: rgba(180, 220, 245, 0.85);
  text-shadow: 0 0 6px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}

/* 类型图标：CodeAgent 💻 / 普通 Agent 🤖，与侧边栏列表保持一致 */
.lobby-pet-type {
  margin-right: 3px;
  font-size: 10px;
  line-height: 1;
  opacity: 0.9;
}

/* CodeAgent 的轻量区分：名字偏青绿 + 头顶一圈淡光环（不喧宾夺主） */
.lobby-pet.is-code-agent .lobby-pet-name {
  color: rgba(150, 240, 220, 0.92);
}
.lobby-pet.is-code-agent .lobby-pet-head {
  box-shadow: 0 0 10px rgba(46, 230, 200, 0.5), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.18);
}

/* 状态灯 */
.lobby-pet-status {
  position: absolute;
  right: 4px;
  top: 4px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #6b8299;
  box-shadow: 0 0 6px rgba(0, 0, 0, 0.5);
}
.lobby-pet-status.running { background: #36ff7c; box-shadow: 0 0 8px rgba(54, 255, 124, 0.8); }
.lobby-pet-status.waiting_multi,
.lobby-pet-status.waiting_confirm,
.lobby-pet-status.waiting_single { background: #ffab3d; box-shadow: 0 0 8px rgba(255, 171, 61, 0.9); animation: lobbyStatusPulse 1.4s ease-in-out infinite; }
.lobby-pet-status.stopped { background: #6b8299; }

@keyframes lobbyStatusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ===== 按状态区分宠物形象 ===== */

/* 运行中：蓝色、尾巴轻摇、常态呼吸 */
.lobby-pet.status-running .lobby-pet-head {
  background: linear-gradient(160deg, #2ee6ff 0%, #1a9fd6 55%, #0e6f9e 100%);
}

/* 等待多行输入：琥珀色、耳朵竖起、眼睛睁大、光晕脉冲 */
.lobby-pet.status-waiting_multi .lobby-pet-head {
  background: linear-gradient(160deg, #ffd479 0%, #f2a52c 55%, #b76a0a 100%);
  box-shadow: 0 0 14px rgba(255, 171, 61, 0.7), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.22);
  animation: lobbyPetWaitGlow 1.6s ease-in-out infinite;
}
.lobby-pet.status-waiting_multi .lobby-pet-ear {
  border-bottom-color: #f2a52c;
  filter: drop-shadow(0 0 4px rgba(255, 171, 61, 0.7));
}
.lobby-pet.status-waiting_multi .lobby-pet-ear.l { transform: rotate(-4deg); }
.lobby-pet.status-waiting_multi .lobby-pet-ear.r { transform: rotate(4deg); }
.lobby-pet.status-waiting_multi .lobby-pet-eye {
  width: 8px;
  height: 9px;
  animation: none;
}
.lobby-pet.status-waiting_multi .lobby-pet-tail {
  border-color: #f2a52c transparent transparent transparent;
  filter: drop-shadow(0 0 4px rgba(255, 171, 61, 0.6));
  animation-duration: 0.9s;
}
.lobby-pet.status-waiting_multi .lobby-pet-mouth {
  width: 8px;
  height: 7px;
  border: 1.5px solid rgba(6, 19, 31, 0.75);
  border-radius: 50%;
}

/* 等待确认（单行/确认）：橙红、耳朵笔直、眼睛圆睁、脉冲更急促 */
.lobby-pet.status-waiting_single .lobby-pet-head,
.lobby-pet.status-waiting_confirm .lobby-pet-head {
  background: linear-gradient(160deg, #ff9d6b 0%, #f2603a 55%, #a82f14 100%);
  box-shadow: 0 0 16px rgba(255, 110, 70, 0.75), inset 0 -3px 6px rgba(0, 0, 0, 0.25),
    inset 0 2px 4px rgba(255, 255, 255, 0.22);
  animation: lobbyPetWaitGlow 1s ease-in-out infinite;
}
.lobby-pet.status-waiting_single .lobby-pet-ear,
.lobby-pet.status-waiting_confirm .lobby-pet-ear {
  border-bottom-color: #f2603a;
  filter: drop-shadow(0 0 4px rgba(255, 110, 70, 0.75));
}
.lobby-pet.status-waiting_single .lobby-pet-ear.l,
.lobby-pet.status-waiting_confirm .lobby-pet-ear.l { transform: rotate(0deg); }
.lobby-pet.status-waiting_single .lobby-pet-ear.r,
.lobby-pet.status-waiting_confirm .lobby-pet-ear.r { transform: rotate(0deg); }
.lobby-pet.status-waiting_single .lobby-pet-eye,
.lobby-pet.status-waiting_confirm .lobby-pet-eye {
  width: 9px;
  height: 10px;
  animation: none;
}
.lobby-pet.status-waiting_single .lobby-pet-pupil,
.lobby-pet.status-waiting_confirm .lobby-pet-pupil {
  width: 4px;
  height: 4px;
}
.lobby-pet.status-waiting_single .lobby-pet-tail,
.lobby-pet.status-waiting_confirm .lobby-pet-tail {
  border-color: #f2603a transparent transparent transparent;
  filter: drop-shadow(0 0 4px rgba(255, 110, 70, 0.65));
  animation-duration: 0.7s;
}
.lobby-pet.status-waiting_single .lobby-pet-mouth,
.lobby-pet.status-waiting_confirm .lobby-pet-mouth {
  width: 9px;
  height: 8px;
  border: 1.5px solid rgba(6, 19, 31, 0.8);
  border-radius: 50%;
}

/* 已停止：灰蓝、眼睛闭合、尾巴静止（通常不显示，保留兜底） */
.lobby-pet.status-stopped .lobby-pet-head {
  background: linear-gradient(160deg, #8fa4b5 0%, #6b8299 55%, #47596b 100%);
  box-shadow: 0 0 6px rgba(120, 150, 175, 0.3), inset 0 -3px 6px rgba(0, 0, 0, 0.3);
}
.lobby-pet.status-stopped .lobby-pet-ear {
  border-bottom-color: #6b8299;
  filter: none;
}
.lobby-pet.status-stopped .lobby-pet-eye {
  height: 2px;
  border-radius: 2px;
  background: #06131f;
  animation: none;
}
.lobby-pet.status-stopped .lobby-pet-pupil { display: none; }
.lobby-pet.status-stopped .lobby-pet-tail {
  border-color: #6b8299 transparent transparent transparent;
  filter: none;
  animation: none;
}
.lobby-pet.status-stopped .lobby-pet-body { animation: none; }

@keyframes lobbyPetWaitGlow {
  0%, 100% { filter: brightness(1); }
  50% { filter: brightness(1.25); }
}

/* ===== 输出气泡 + 输入/确认控件堆叠容器 ===== */
/* left / width / max-height 由 JS（layoutPetStack）动态计算，确保始终落在舞台可视范围内 */
.lobby-pet-stack {
  position: absolute;
  top: calc(100% + 4px);
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: default;
  z-index: 6;
  overflow-y: auto;
  overflow-x: hidden;
  touch-action: pan-y;
}
.lobby-pet-stack.stack-above {
  top: auto;
  bottom: calc(100% + 4px);
  flex-direction: column-reverse;
}

.lobby-pet-panel {
  width: 100%;
  background: rgba(10, 24, 38, 0.96);
  border: 1px solid rgba(32, 200, 255, 0.35);
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.55), 0 0 16px rgba(32, 200, 255, 0.18);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: default;
  /* 面板内允许纵向触摸滚动（宠物本体已设 touch-action:none，需在此恢复） */
  touch-action: pan-y;
}

/* 输出气泡（markdown） */
.lobby-pet-output-wrap {
  position: relative;
  width: 100%;
}
.lobby-pet-copy {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  font-size: 12px;
  line-height: 1;
  color: #9fd8ef;
  background: rgba(10, 24, 38, 0.85);
  border: 1px solid rgba(32, 200, 255, 0.35);
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.35;
  transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.lobby-pet-output-wrap:hover .lobby-pet-copy {
  opacity: 1;
}
.lobby-pet-copy:hover {
  color: #dff1fb;
  border-color: rgba(32, 200, 255, 0.7);
}
.lobby-pet-copy.copied {
  opacity: 1;
  color: #34d99b;
  border-color: rgba(52, 217, 155, 0.7);
}
.lobby-pet-output {
  width: 100%;
  box-sizing: border-box;
  min-height: 120px;
  max-height: 60vh;
  overflow-y: auto;
  touch-action: pan-y;
  background: rgba(10, 24, 38, 0.94);
  border: 1px solid rgba(32, 200, 255, 0.28);
  border-radius: 10px;
  padding: 10px 32px 10px 12px;
  word-break: break-word;
  box-shadow: 0 8px 26px rgba(0, 0, 0, 0.5);
  font-family: 'Consolas', 'Microsoft YaHei', sans-serif;
}
/* markdown 正文排版复用全局 .message-body.markdown-content 样式，与 Panel 保持一致 */

/* 输入行 */
.lobby-pet-input-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
/* 移动端：多行输入框与按钮分成两行，避免按钮挤压输入框宽度 */
@media (max-width: 768px) {
  .lobby-pet-input-row-multi {
    flex-wrap: wrap;
  }
  .lobby-pet-input-row-multi .lobby-pet-textarea {
    flex: 1 1 100%;
  }
  .lobby-pet-input-row-multi .lobby-pet-at,
  .lobby-pet-input-row-multi .lobby-pet-complete,
  .lobby-pet-input-row-multi .lobby-pet-send {
    flex: 0 0 auto;
  }
  /* 按钮行右对齐：把换行后的首个按钮推到右侧，其余按钮紧随其后 */
  .lobby-pet-input-row-multi > button:first-of-type {
    margin-left: auto;
  }
}
.lobby-pet-textarea,
.lobby-pet-input {
  flex: 1;
  min-width: 0;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(32, 200, 255, 0.3);
  border-radius: 6px;
  color: #e6f6ff;
  font-size: 12px;
  font-family: inherit;
  padding: 5px 7px;
  resize: none;
  outline: none;
  /* 输入框内恢复触摸选择/滚动（宠物本体已设 touch-action:none） */
  touch-action: auto;
}
.lobby-pet-textarea:focus,
.lobby-pet-input:focus {
  border-color: rgba(32, 200, 255, 0.7);
  box-shadow: 0 0 8px rgba(32, 200, 255, 0.25);
}
.lobby-pet-send {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-radius: 6px;
  border: 1px solid rgba(32, 200, 255, 0.4);
  background: rgba(32, 200, 255, 0.15);
  color: #7ee7ff;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.lobby-pet-send:hover { background: rgba(32, 200, 255, 0.3); }

.lobby-pet-complete {
  flex: 0 0 auto;
  height: 30px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid rgba(54, 255, 124, 0.4);
  background: rgba(54, 255, 124, 0.15);
  color: #a6ffcb;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  white-space: nowrap;
}
.lobby-pet-complete:hover { background: rgba(54, 255, 124, 0.3); }

/* 移动端「@」按钮：与完成按钮同尺寸，便于触屏点击 */
.lobby-pet-at {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-radius: 6px;
  border: 1px solid rgba(32, 200, 255, 0.4);
  background: rgba(32, 200, 255, 0.15);
  color: #7ee7ff;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
}
.lobby-pet-at:hover { background: rgba(32, 200, 255, 0.3); }

/* 确认气泡 */
.lobby-pet-confirm {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lobby-pet-confirm-msg {
  font-size: 12px;
  color: #ffd79a;
  background: rgba(255, 171, 61, 0.12);
  border-radius: 6px;
  padding: 6px 8px;
}
.lobby-pet-confirm-actions {
  display: flex;
  gap: 6px;
}
/* 默认按钮始终置于右侧：default-yes 时「确认」在右，否则「取消」在右 */
.lobby-pet-confirm-actions .lobby-pet-confirm-btn.yes { order: 1; }
.lobby-pet-confirm-actions .lobby-pet-confirm-btn.no { order: 2; }
.lobby-pet-confirm-actions.default-yes .lobby-pet-confirm-btn.yes { order: 2; }
.lobby-pet-confirm-actions.default-yes .lobby-pet-confirm-btn.no { order: 1; }
.lobby-pet-confirm-btn {
  flex: 1;
  padding: 5px 0;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 12px;
}
.lobby-pet-confirm-btn.yes {
  background: rgba(54, 255, 124, 0.18);
  border-color: rgba(54, 255, 124, 0.5);
  color: #a6ffcb;
}
.lobby-pet-confirm-btn.no {
  background: rgba(255, 90, 90, 0.15);
  border-color: rgba(255, 90, 90, 0.45);
  color: #ffb3b3;
}
/* Agent 右键菜单：对当前 Agent 的操作 */
.lobby-context-menu {
  position: absolute;
  z-index: 60;
  min-width: 300px;
  max-width: 380px;
  max-height: 60vh;
  overflow-y: auto;
  padding: 4px;
  border-radius: 10px;
  background: rgba(12, 22, 34, 0.96);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.lobby-context-title {
  padding: 6px 10px 8px;
  font-size: 12px;
  font-weight: 600;
  color: #9fe4ff;
  border-bottom: 1px solid rgba(32, 200, 255, 0.18);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 菜单项两列排布，避免一列过长 */
.lobby-context-items {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px;
}
.lobby-context-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #d7e8f5;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.lobby-context-item:hover:not(:disabled) {
  background: rgba(32, 200, 255, 0.16);
}
.lobby-context-item:disabled {
  opacity: 0.4;
  cursor: default;
}
.lobby-context-icon {
  width: 18px;
  text-align: center;
}
.lobby-context-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 节点重命名弹层 */
/* 与其它弹层（命令面板/设置等）同为 z-index 3000；PetLobby 在 DOM 中位于其后，
   同层级时后出现者在上，故可覆盖命令面板，保证从命令面板触发时弹层可见可输入 */
.lobby-rename-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 10, 18, 0.55);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}
.lobby-rename-dialog {
  width: min(360px, 86vw);
  padding: 16px;
  border-radius: 12px;
  background: rgba(12, 22, 34, 0.98);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
}
.lobby-rename-title {
  font-size: 14px;
  font-weight: 600;
  color: #9fe4ff;
}
.lobby-rename-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #7f93a6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lobby-rename-input {
  width: 100%;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(32, 200, 255, 0.3);
  background: rgba(6, 14, 24, 0.9);
  color: #d7e8f5;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.lobby-rename-input:focus {
  border-color: rgba(32, 200, 255, 0.7);
}
.lobby-rename-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
.lobby-rename-btn {
  padding: 6px 16px;
  border-radius: 8px;
  border: 1px solid transparent;
  font-size: 13px;
  cursor: pointer;
}
.lobby-rename-btn.cancel {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.18);
  color: #b6c6d4;
}
.lobby-rename-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.08);
}
.lobby-rename-btn.ok {
  background: rgba(32, 200, 255, 0.9);
  color: #04121c;
  font-weight: 600;
}
.lobby-rename-btn.ok:hover {
  background: rgba(32, 200, 255, 1);
}
.lobby-rename-btn.ok:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* 安装浏览器插件弹层：比通用弹层更大，保证高风险提示无需翻页即可读完 */
.lobby-install-dialog {
  width: min(760px, 94vw);
  max-height: 92vh;
  overflow-y: auto;
  padding: 20px 24px;
  border-radius: 12px;
  background: rgba(12, 22, 34, 0.98);
  border: 1px solid rgba(32, 200, 255, 0.35);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.55);
}
.lobby-install-steps {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.lobby-install-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #c3d6e4;
}
.lobby-install-step-no {
  flex: none;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  border-radius: 50%;
  background: rgba(32, 200, 255, 0.18);
  border: 1px solid rgba(32, 200, 255, 0.5);
  color: #9fe4ff;
  font-size: 11px;
  text-align: center;
  line-height: 16px;
}
.lobby-install-step-text code {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(6, 14, 24, 0.9);
  color: #9fe4ff;
  font-size: 12px;
}
.lobby-install-error {
  margin-top: 12px;
  font-size: 12px;
  color: #ff8b96;
}

/* 安装插件按钮：有新版本时的红点提示（定位在按钮右上角） */
.pet-lobby-install-toggle {
  position: relative;
}
.pet-lobby-update-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff5d6c;
  box-shadow: 0 0 0 2px rgba(10, 24, 38, 0.86);
}
/* 弹层内的版本信息与升级提示 */
.lobby-install-version {
  margin-top: 12px;
  font-size: 12px;
  color: #7f93a6;
}
.lobby-install-update {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #ffd7a1;
  background: rgba(255, 170, 60, 0.12);
  border: 1px solid rgba(255, 170, 60, 0.4);
}
.lobby-install-update-icon {
  flex: none;
  color: #ffb347;
}
/* 下载弹窗内的风险提示与免责声明（高敏感权限） */
.lobby-install-risk {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.65;
  color: #ffc9cf;
  background: rgba(255, 70, 90, 0.12);
  border: 1px solid rgba(255, 70, 90, 0.55);
  box-shadow: 0 0 0 1px rgba(255, 70, 90, 0.15) inset;
}
.lobby-install-risk-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #ff8b96;
}
.lobby-install-risk-icon {
  flex: none;
  font-size: 14px;
}
.lobby-install-risk-body {
  margin-top: 8px;
}
.lobby-install-risk-body p {
  margin: 0 0 6px;
}
.lobby-install-risk-body ul {
  margin: 0 0 6px;
  padding-left: 18px;
}
.lobby-install-risk-body li {
  margin-bottom: 2px;
}
.lobby-install-risk-body code {
  padding: 0 3px;
  border-radius: 3px;
  font-size: 11px;
  color: #ffd7dc;
  background: rgba(255, 70, 90, 0.18);
}
.lobby-install-risk-body strong {
  color: #ffb0b8;
}
.lobby-install-risk-warn {
  color: #ff9aa5;
}
.lobby-group-list {
  max-height: 220px;
  overflow-y: auto;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lobby-group-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: #d7e8f5;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}
.lobby-group-item:hover {
  background: rgba(32, 200, 255, 0.16);
  border-color: rgba(32, 200, 255, 0.5);
}
.lobby-group-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lobby-group-count {
  flex: none;
  font-size: 12px;
  color: #7f93a6;
}
.lobby-group-empty {
  padding: 8px 2px;
  font-size: 12px;
  color: #7f93a6;
}
.lobby-group-create {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.lobby-group-create .lobby-rename-input {
  margin-top: 0;
  flex: 1;
}
.lobby-group-create .lobby-rename-btn {
  flex: none;
  white-space: nowrap;
}
</style>
