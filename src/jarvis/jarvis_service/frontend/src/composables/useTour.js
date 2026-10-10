// 新手引导 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（Issue #118 Step 8），保持行为完全一致：
// - 常量：ONBOARDING_KEY_PREFIX / LEGACY_ONBOARDING_KEY / ONBOARDING_AUTO_DELAY
// - 状态：activeTourId / activeTourSteps / showOnboarding / onboardingTimer
// - 标记读写：onboardingKey / hasSeenTour / markTourSeen / resetOnboardingMarks
// - 步骤常量：WELCOME_TOUR_STEPS / LOBBY_TOUR_STEPS / AGENT_TOUR_STEPS /
//   PANEL_TOUR_STEPS / SIDEBAR_TOUR_STEPS / getTourSteps
// - 触发/关闭：maybeStartTour / finishTour / startOnboarding / clearOnboardingTimer
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - showToast：finishTour 完成欢迎引导时提示（getter 形式，内部调用时才求值）
// - openWorkspaceAgentList：startOnboarding 的 sidebar 场景需先打开编辑器并切到
//   Agent 列表视图（getter 形式，定义晚于本 composable 调用点，避免 TDZ）
import { computed, ref } from 'vue'
export function useTour({ showToast, openWorkspaceAgentList }) {
  // 按场景触发的多套引导：首次进入大厅 / 首次创建出 Agent / 首次打开 Panel 时各自弹出一次；
  // 每套引导看过即写入独立标记，可通过命令面板「重置新手引导」清除标记后重新触发。
  const ONBOARDING_KEY_PREFIX = 'jarvis_onboarding_'
  // 旧版单一引导标记：老用户已看过，视为 welcome 已看过，避免重复打扰
  const LEGACY_ONBOARDING_KEY = 'jarvis_onboarding_done_v1'
  const ONBOARDING_AUTO_DELAY = 800
  // 当前进行中的引导场景（null 表示未激活）
  const activeTourId = ref(null)
  const activeTourSteps = computed(() => (activeTourId.value ? getTourSteps(activeTourId.value) : []))
  const showOnboarding = computed({
    get: () => activeTourId.value !== null,
    set: (visible) => {
      if (!visible && activeTourId.value) finishTour()
    },
  })
  let onboardingTimer = null

  function clearOnboardingTimer() {
    if (onboardingTimer) {
      clearTimeout(onboardingTimer)
      onboardingTimer = null
    }
  }

  function onboardingKey(tourId) {
    return `${ONBOARDING_KEY_PREFIX}${tourId}_v1`
  }

  function hasSeenTour(tourId) {
    try {
      if (localStorage.getItem(onboardingKey(tourId)) === '1') return true
      if (tourId === 'welcome' && localStorage.getItem(LEGACY_ONBOARDING_KEY) === '1') return true
      return false
    } catch (err) {
      return true
    }
  }

  function markTourSeen(tourId) {
    try {
      localStorage.setItem(onboardingKey(tourId), '1')
    } catch (err) {
      /* 隐私模式下写入失败可忽略 */
    }
  }

  // 各场景的引导步骤。target 命中不到元素时组件会自动退化为居中卡片
  function getTourSteps(tourId) {
    if (tourId === 'welcome') return WELCOME_TOUR_STEPS
    if (tourId === 'lobby') return LOBBY_TOUR_STEPS()
    if (tourId === 'agent') return AGENT_TOUR_STEPS()
    if (tourId === 'panel') return PANEL_TOUR_STEPS()
    if (tourId === 'sidebar') return SIDEBAR_TOUR_STEPS()
    return []
  }

  // 介绍页：单步、无 target（居中卡片），介绍 Jarvis 的定位与核心概念
  const WELCOME_TOUR_STEPS = [
    {
      id: 'welcome',
      icon: '👋',
      title: '欢迎使用 Jarvis',
      desc: 'Jarvis 让 AI 从「独自工作」走向「与众共事」：你不再只驱动一个助手，而是同时调度多个 Agent，让它们各司其职、互相协作。',
      hint: '四种协作形态随你组合：单人单 Agent（专注一件事）、单人多 Agent（并行推进）、多人单 Agent（共享同一个助手）、多人多 Agent（团队各带各的兵）。',
    },
    {
      id: 'welcome-concepts',
      icon: '🧭',
      title: '五个核心概念',
      desc: 'Agent：可被派活的 AI 助手，分通用 Agent（分析、规划、执行）与代码 Agent（读代码、改代码、跑验证）。节点：Agent 运行所在的机器。网关：连接你与所有节点的服务端。',
      hint: '宠物大厅：没有打开面板时，所有 Agent 以宠物形态在此活动。命令面板：按 Ctrl+P（Mac 为 ⌘+P）搜索并执行几乎所有操作。',
    },
    {
      id: 'welcome-toolbar',
      icon: '🧰',
      title: '右上角工具条',
      desc: '右上角常驻一条工具条：💬 打开聊天室、💻 打开终端面板、⌘ 打开命令面板（Ctrl+P）、⚙ 打开设置；管理员还会看到 🛡️ 管理入口。Agent 列表在编辑器面板的侧边栏中（Ctrl+A 打开）。',
      hint: '工具条可拖动（拖到屏幕左/右边缘会自动收起，露出窄边条点击即可展开）；长按左下角的主宠物，可用一句话快速创建 Agent（Ctrl+Alt+N）。',
    },
    {
      id: 'welcome-command-palette',
      icon: '⌘',
      title: '命令面板',
      desc: '按 Ctrl+P（Mac 为 ⌘+P）或点工具条的 ⌘ 打开命令面板：动作按分组排列（当前 Agent、执行、界面、网关、管理、账号、节点、大厅等），输入关键词即可搜索，回车执行。',
      hint: '很多动作带快捷键（如 Ctrl+N 新建 Agent、Ctrl+Alt+K 中断当前 Agent）；命令面板是「几乎所有操作」的统一入口，记不住快捷键时用它最方便。',
    },
    {
      id: 'welcome-more',
      icon: '🧩',
      title: '更多入口',
      desc: '命令面板里还藏着不少实用能力：隐藏/显示宠物（Ctrl+Alt+B）、隐藏/显示全部输出、刷新与同步 Agent 状态、退出登录；管理员还可重启网关/节点、打开管理面板，以及在设置弹窗中编辑配置文件。',
      hint: '「安装浏览器插件」可让 Jarvis 操作你浏览器中的网页；「查看网络拓扑」可看节点连接全貌。配置文件编辑（需 admin:config 权限）位于设置弹窗的「配置文件编辑」区，支持表单与纯文本两种方式。',
    },
    {
      id: 'welcome-start',
      icon: '🚀',
      title: '开始使用',
      desc: '在编辑器面板侧边栏的 Agent 列表中用「➕」创建第一个 Agent（也可按 Ctrl+N）；双击宠物打开对话面板，在底部输入框描述需求后发送（单行模式按 Enter，或按 Ctrl+Enter / Ctrl+D）。',
      hint: '随时可在命令面板（Ctrl+P）里搜索「引导」重新查看，或搜索「重置新手引导」让各场景引导重新触发。',
    },
  ]

  // 大厅场景：无任何可见 Panel 时展示
  function LOBBY_TOUR_STEPS() {
    return [
      {
        id: 'lobby-dashboard',
        icon: '📊',
        title: '大厅仪表盘',
        desc: '这里实时显示当前时间、网关连接状态与地址、在线节点数，以及按状态分类的 Agent 数量，一眼掌握全局。',
        hint: '网关离线时宠物会停止响应，先检查大厅左上角仪表盘的连接状态。',
        target: '.pet-lobby-dash',
        placement: 'bottom',
      },
      {
        id: 'lobby-pet',
        icon: '🐾',
        title: '宠物就是 Agent',
        desc: '每只宠物对应一个 Agent：拖动可调整位置，双击打开它的对话面板，宠物上方会滚动显示它的最新输出。',
        hint: '需要你确认或输入时，宠物会高亮提醒；右键宠物可打开快捷操作菜单。',
        target: '.lobby-pet',
        placement: 'bottom',
      },
      {
        id: 'lobby-at-completion',
        icon: '@',
        title: '在宠物输入框用 @ 引用',
        desc: '当宠物等待输入时，可直接在它下方的输入框回复，无需打开面板。输入 @ 同样会弹出补全列表，可引用文件、规则、内置命令与替换变量。',
        hint: '补全列表支持上下键选择、回车插入、Esc 取消；输入文件名可搜索并引用文件内容，省去手动粘贴。',
        target: '.lobby-pet',
        placement: 'bottom',
      },
      {
        id: 'lobby-topology',
        icon: '🕸',
        title: '节点与拓扑',
        desc: '大厅里的机箱代表各个节点，连线表示它们与 master 网关的连接关系；节点下方显示名称、Agent 数量与版本。',
        hint: '在命令面板（Ctrl+P）中搜索「网络拓扑」可打开全屏拓扑大图，更清楚地查看节点间关系。',
        target: '.lobby-node',
        placement: 'bottom',
      },
      {
        id: 'lobby-create',
        icon: '➕',
        title: '创建 Agent',
        desc: '在编辑器面板侧边栏的 Agent 列表中用「➕」创建 Agent（也可按 Ctrl+N），选择节点、Agent 类型与工作目录即可创建；还可以双击大厅中的节点，直接在指定节点上创建。',
        hint: '代码 Agent（jca）擅长读代码、改代码、跑验证；通用 Agent（jvs）适合分析、规划与执行。长按左下角的主宠物可用一句话快速创建 Agent（Ctrl+Alt+N）。',
        target: '.workspace-activity-bar',
        placement: 'bottom',
      },
      {
        id: 'lobby-quick-create',
        icon: '🐾',
        title: '一句话创建 Agent',
        desc: '长按左下角的主宠物（或按 Ctrl+Alt+N），输入一句话描述任务，回车即可创建 Agent 并立即开始执行；除任务外全部使用默认参数，适合快速起一个任务。',
        hint: '长按主宠物约 0.6 秒即可触发；需要自定义节点、类型、工作目录等参数时，改用「➕」的完整创建窗口。',
        target: '.pet-float',
        placement: 'top',
      },
      {
        id: 'lobby-pet-menu',
        icon: '🖱',
        title: '宠物右键菜单',
        desc: '在宠物上右键，可快速执行查看变更、查看规则、查看工具、创建终端、打开编辑器、重命名、复制、权限管理、无损重生、删除等操作，无需先进面板。',
        hint: '菜单内容与命令面板的「当前 Agent」组一致，另含「添加到分组 / 从分组移出」；选中哪只宠物就作用于哪个 Agent。',
        target: '.lobby-pet',
        placement: 'bottom',
      },
      {
        id: 'lobby-node-menu',
        icon: '🖧',
        title: '节点右键菜单',
        desc: '在大厅的节点上右键，可创建 Agent、打开终端、更新代码、重启服务或重命名节点。',
        hint: '更新代码与重启服务会影响该节点上运行的 Agent，操作前请确认。',
        target: '.lobby-node',
        placement: 'bottom',
      },
    ]
  }

  // Agent 场景：首次创建出 Agent 后展示
  function AGENT_TOUR_STEPS() {
    return [
      {
        id: 'agent-status',
        icon: '🚦',
        title: 'Agent 状态',
        desc: '宠物与面板上的颜色表示 Agent 状态：运行中、等待输入、等待确认、空闲、已停止。等待输入时会高亮提醒你处理。',
        hint: '命令面板中的「奔赴等待输入的 Agent」可一键跳到最需要你的那只宠物。',
        target: '.workspace-activity-bar',
        placement: 'bottom',
      },
      {
        id: 'agent-sidebar',
        icon: '📋',
        title: 'Agent 列表',
        desc: '在编辑器面板侧边栏的 Agent 列表中，可查看全部 Agent、批量选择、按节点或自定义分组浏览。',
        hint: '侧边栏中可批量复制、批量删除、加入分组；单个 Agent 的重命名/复制/权限管理/无损重生/删除在命令面板（Ctrl+P）的「当前 Agent」组中。',
        target: '.workspace-activity-bar',
        placement: 'bottom',
      },
      {
        id: 'agent-manage',
        icon: '🛠',
        title: '管理单个 Agent',
        desc: '在命令面板（Ctrl+P）的「当前 Agent」组中：重命名可改显示名；复制会按同样配置再建一个；权限管理控制谁能读、谁能交互；无损重生保留会话重建进程；删除则彻底移除。',
        hint: '「无损重生」与「权限管理」仅对 Agent 属主可见；「人工介入」可随时中断当前 Agent 并接管。',
        target: '.workspace-activity-bar',
        placement: 'bottom',
      },
      {
        id: 'agent-groups',
        icon: '🗂',
        title: '自定义分组',
        desc: 'Agent 多了以后，可在编辑器侧边栏的「管理分组」中把 Agent 归入自定义分组，分组可折叠，便于按项目或用途归类。',
        hint: 'Agent 停止后会自动从分组中移除，避免分组里堆积无效条目。',
        target: '.workspace-activity-bar',
        placement: 'bottom',
      },
    ]
  }

  // Panel 场景：首次打开对话面板后展示
  function PANEL_TOUR_STEPS() {
    return [
      {
        id: 'panel-input',
        icon: '💬',
        title: '在面板中对话',
        desc: '面板底部是输入框：单行模式下按 Enter 直接发送，多行模式下按 Ctrl+Enter 或 Ctrl+D 发送（回车用于换行）。Agent 的输出会实时流式显示在上方。',
        hint: '按住右 Ctrl 键可语音输入。',
        target: '.session-panel',
        placement: 'top',
      },
      {
        id: 'panel-at-completion',
        icon: '@',
        title: '用 @ 快速引用',
        desc: '在输入框输入 @ 会弹出补全列表，可快速引用四类内容：📄 文件（继续输入文件名即可搜索）、📚 规则（内置/文件/YAML 规则）、⚙️ 内置命令（如 Summary、Commit、Review）、📝 提示词模板（如 sdd/1.spec）。上下键选择、回车插入，Esc 取消。',
        hint: '引用文件时会把文件内容带给 Agent，省去手动粘贴；引用规则可临时为本次对话加载指定规则。宠物大厅的输入框同样支持 @。',
        target: '.session-panel',
        placement: 'top',
      },
      {
        id: 'panel-confirm',
        icon: '✅',
        title: '确认卡片',
        desc: 'Agent 需要你拍板时会弹出确认条，按 y 确认、n 取消，Enter 触发默认选项；等待多行输入时可用 Ctrl+C 发送完成信号。',
        hint: '确认卡片就在面板内，不会跳出去打断其他 Agent。',
        target: '.session-panel',
        placement: 'top',
      },
      {
        id: 'panel-context-menu',
        icon: '🖱',
        title: '面板右键菜单',
        desc: '在面板空白处右键，可查看变更（diff）、规则、工具，以及打开终端与代码编辑器，随时检视 Agent 的工作现场。',
        hint: '这些入口也可在命令面板（Ctrl+P）的「当前 Agent」组中找到。',
        target: '.session-panel',
        placement: 'top',
      },
      {
        id: 'panel-layout',
        icon: '🪟',
        title: '关闭面板',
        desc: '按 Ctrl+W 关闭当前焦点所在的面板，回到宠物大厅；编辑器内可左右/上下分割出多个区域，每个区域独立承载文件、会话、终端或聊天。',
        hint: '编辑器内按 Ctrl+\\ 左右分割、Ctrl+- 上下分割；分割后 Ctrl+W 关闭当前激活的区域。',
        target: '.session-panel',
        placement: 'top',
      },
      {
        id: 'panel-auto',
        icon: '🔁',
        title: '自动滚动与朗读',
        desc: '面板可开启自动滚动，让输出始终跟随最新内容；也可开启自动朗读，用语音播报 Agent 的回复。',
        hint: '两者都能在命令面板的「当前 Agent」组中随时切换。',
        target: '.session-panel',
        placement: 'top',
      },
    ]
  }

  // 侧边栏场景：首次打开编辑器内的 Agent 列表视图后展示
  function SIDEBAR_TOUR_STEPS() {
    return [
      {
        id: 'sidebar-list',
        icon: '📋',
        title: 'Agent 列表',
        desc: '编辑器侧边栏按节点与自定义分组列出全部 Agent，每项显示类型、名称、状态与工作目录；点击即可在编辑器中打开它。',
        hint: '等待输入的 Agent 会高亮闪烁，提醒你及时处理。',
        target: '.workspace-sidebar-agents',
        placement: 'right',
      },
      {
        id: 'sidebar-context-menu',
        icon: '🖱',
        title: 'Agent 右键菜单',
        desc: '在任一 Agent 项上右键，可就地执行查看变更、创建终端、打开编辑器、重命名、复制、权限管理、无损重生、删除等操作，无需先打开面板。',
        hint: '菜单内容与命令面板（Ctrl+P）的「当前 Agent」组一致，作用于被右键的那个 Agent。',
        target: '.workspace-sidebar-agents .agent-item',
        placement: 'right',
      },
      {
        id: 'sidebar-batch',
        icon: '☑',
        title: '批量操作',
        desc: '点击侧边栏顶部的「☑」进入批量选择模式，可勾选多个 Agent 后批量复制、加入分组或删除。',
        hint: '批量删除不可恢复，操作前请确认选中的 Agent。',
        target: '.workspace-sidebar-agents',
        placement: 'right',
      },
      {
        id: 'sidebar-groups',
        icon: '📁',
        title: '管理分组',
        desc: '点击侧边栏顶部的「📁」可重命名或删除自定义分组；分组可折叠，便于按项目或用途归类 Agent。',
        hint: 'Agent 停止后会自动从分组中移除，避免分组里堆积无效条目。',
        target: '.workspace-sidebar-agents',
        placement: 'right',
      },
      {
        id: 'sidebar-orchestrate',
        icon: '🧩',
        title: '编排：批量创建 Agent',
        desc: '点击侧边栏顶部的「🧩」，选择节点与编排文件（YAML）后解析，会为文件中每个 Agent 生成一个可编辑表单，确认后一键批量创建。',
        hint: '每个 Agent 可单独设置名称、类型、工作目录、模型组、目标节点等；任务描述填写后 Agent 启动即执行（无交互模式下必填）。',
        target: '.workspace-sidebar-agents',
        placement: 'right',
      },
    ]
  }

  // 清除全部引导标记（命令面板「重置新手引导」），下次进入对应场景会重新触发
  function resetOnboardingMarks() {
    try {
      const keys = []
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i)
        if (key && key.startsWith(ONBOARDING_KEY_PREFIX)) keys.push(key)
      }
      keys.forEach(key => localStorage.removeItem(key))
      localStorage.removeItem(LEGACY_ONBOARDING_KEY)
    } catch (err) {
      /* 隐私模式下读取失败可忽略 */
    }
  }

  // 场景触发：已有引导进行中或该场景已看过时跳过；延迟等待目标元素挂载后再展示
  function maybeStartTour(tourId) {
    if (activeTourId.value) return
    if (hasSeenTour(tourId)) return
    clearOnboardingTimer()
    onboardingTimer = setTimeout(() => {
      onboardingTimer = null
      if (activeTourId.value) return
      if (hasSeenTour(tourId)) return
      activeTourId.value = tourId
    }, ONBOARDING_AUTO_DELAY)
  }

  // 关闭/完成：记录当前场景已看过并收起
  function finishTour() {
    const tourId = activeTourId.value
    clearOnboardingTimer()
    if (tourId) markTourSeen(tourId)
    activeTourId.value = null
    if (tourId === 'welcome') showToast()('引导完成，开始使用 Jarvis 吧', 'success')
  }

  // 手动打开指定场景引导（命令面板），不写标记
  function startOnboarding(tourId = 'welcome') {
    clearOnboardingTimer()
    activeTourId.value = tourId
    // 侧边栏场景需先打开编辑器并切到 Agent 列表视图，否则引导目标不可见
    if (tourId === 'sidebar') openWorkspaceAgentList()()
  }

  return {
    activeTourId,
    activeTourSteps,
    showOnboarding,
    maybeStartTour,
    finishTour,
    startOnboarding,
    resetOnboardingMarks,
    clearOnboardingTimer,
  }
}
