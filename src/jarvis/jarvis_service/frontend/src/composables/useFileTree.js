// 文件树 组合式函数。
//
// 从 App.vue 的 <script setup> 中拆出（原文件树域 14 个区块，约 1163 行），保持行为完全一致：
// - 核心状态：fileTreeState / fileTreeExpanded / fileTreeLoading / expandedAgents / selectedAgentId /
//   fileTreeSelectedPath / fileTreeSelectedAgentId / showStoppedAgents / stoppedNodeCollapseState /
//   fileTreeContextMenu / fileTreeClipboard / fileTreeUploadInput / fileTreeUploadContext / inputPrompt /
//   fileTreeDragState / fileTreeDropTargetPath
// - 图标常量：FILE_TREE_FOLDER_SVG / FILE_TREE_CTX_ICONS / FILE_TYPE_ICON_MAP / FILE_TYPE_ICON_BY_NAME
// - 节点交互：getFileTypeIcon / handleFileTreeNodeClick / selectFileTreeNode / scrollFileTreeNodeIntoView /
//   focusFileTreeContainer / revealTabInFileTree / toggleAgentExpanded / toggleStoppedNodeCollapse / isStoppedNodeCollapsed
// - 键盘导航：moveFileTreeSelection / handleFileTreeKeydown
// - 右键菜单：closeFileTreeContextMenu / getFileTreeContextDirPath / getFileTreeContextTargetPath /
//   getFileTreeContextDirNode / toWorkingDirRelativePath / copyTextToClipboard / openFileTreeContextMenu /
//   openInputPrompt / cancelInputPrompt / confirmInputPrompt / fileTreeContextActions / buildDirSearchGlob /
//   runFileTreeContextAction
// - 上传下载：uploadFileToDir / readFileAsDataUrl / onFileTreeUploadInputChange / downloadFileFromNode / refreshFileTreeDir
// - 文件 CRUD：createFileOrDirectory / deleteFileOrDirectory / renameFileOrDirectory
// - 复制粘贴：listDirectoryEntries / collectDirectorySnapshot / writeClipboardNode / resolvePasteName /
//   setFileTreeClipboard / pasteFileTreeClipboard
// - 拖拽：handleFileTreeDragStart / handleFileTreeDragEnd / isValidFileTreeDropTarget / handleFileTreeDragOver /
//   handleFileTreeDragLeave / handleFileTreeDrop
// - 路径工具：resolveFileTreeDirNodeByPath / writeFileContent
// - 核心加载：initFileTreeState / loadFileTreeNode / initFileTree / flattenVisibleFileTreeNodes /
//   getVisibleFileTreeNodes / findNode / toggleNodeExpand
//
// 依赖注入（调用方在 setup 中传入，须在其定义之后调用）：
// - agentList：ref(Array)（Agent 列表）
// - getVirtualWorkspaceAgent：函数（按 agentId 取虚拟工作区 Agent）
// - resolveFileTreeAgent：函数（按 agentId 解析文件树 Agent）
// - resolveAgentForPath：函数（按路径解析 Agent）
// - openWorkspaceFile：函数（打开工作区文件）
// - setWorkspaceSidebarView：函数（设置工作区侧边栏视图）
// - removeWorkspaceDir：函数（移除工作区目录）
// - fetchFileContent：函数（读取文件内容）
// - fetchWithAuth：函数（带认证的 fetch）
// - buildNodeHttpUrl：函数（构造节点 HTTP URL）
// - getGatewayAddress：函数（返回 { host, port }）
// - showToast：函数（提示消息）
// - showConfirm：函数（确认对话框）
// - globalSearchFileGlob：ref(string)（全局搜索文件 glob）
// - ensureWorkspaceSidebarFileTree：函数（确保侧边栏文件树可见）
import { computed, nextTick, ref, triggerRef } from 'vue'

export function useFileTree({
  agentList,
  getVirtualWorkspaceAgent,
  resolveFileTreeAgent,
  resolveAgentForPath,
  openWorkspaceFile,
  setWorkspaceSidebarView,
  removeWorkspaceDir,
  fetchFileContent,
  fetchWithAuth,
  buildNodeHttpUrl,
  getGatewayAddress,
  showToast,
  showConfirm,
  globalSearchFileGlob,
  ensureWorkspaceSidebarFileTree,
}) {
// 文件树状态管理
const fileTreeState = ref(new Map())        // 每个 Agent 的文件树数据：agent_id -> treeData
const fileTreeExpanded = ref(new Map())     // 每个 Agent 的展开状态：agent_id -> Set(expandedPaths)
const fileTreeLoading = ref(new Map())      // 每个 Agent 的加载状态：agent_id -> Set(loadingPaths)
const expandedAgents = ref(new Set())       // 编辑器目录树中展开的 Agent 集合
const selectedAgentId = ref(null)         // 编辑器目录树中选中的 Agent ID
// 编辑器目录树键盘操作：当前光标选中的节点（绝对路径）及其所属 Agent
const fileTreeSelectedPath = ref(null)
const fileTreeSelectedAgentId = ref(null)
const showStoppedAgents = ref(false)      // 是否显示已停止的 Agent
const stoppedNodeCollapseState = ref(new Map()) // 已停止 Agent 节点分组的折叠状态：nodeId -> boolean (true表示折叠)

// 切换 Agent 在目录树中的展开状态
function toggleAgentExpanded(agentId) {
  // 设置选中的 Agent
  selectedAgentId.value = agentId
  
  if (expandedAgents.value.has(agentId)) {
    expandedAgents.value.delete(agentId)
  } else {
    expandedAgents.value.add(agentId)
    // 展开时确保该 Agent 的文件树已初始化
    const agent = agentList.value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (agent && !fileTreeState.value.has(agentId)) {
      initFileTree(agentId, agent.working_dir)
    }
  }
  // 手动触发响应式更新
  triggerRef(expandedAgents)
}

// 切换已停止 Agent 节点分组的折叠状态
function toggleStoppedNodeCollapse(nodeId) {
  const currentState = stoppedNodeCollapseState.value.get(nodeId) || false
  stoppedNodeCollapseState.value.set(nodeId, !currentState)
  triggerRef(stoppedNodeCollapseState)
}

// 检查已停止 Agent 节点分组是否折叠
function isStoppedNodeCollapsed(nodeId) {
  return stoppedNodeCollapseState.value.get(nodeId) || false
}

async function revealTabInFileTree(path) {
  const resolved = resolveAgentForPath(path)
  if (!resolved) return
  const { agentId, agent } = resolved
  const rootDir = String(agent.working_dir).replace(/\/+$/, '')
  const raw = String(path)
  const rel = raw === rootDir ? '' : raw.slice(rootDir.length + 1)
  const segments = rel ? rel.split('/').filter(Boolean) : []

  // 打开侧边栏并切到文件视图
  setWorkspaceSidebarView('files')
  // 展开该 Agent 的节点
  if (!expandedAgents.value.has(agentId)) {
    expandedAgents.value.add(agentId)
  }
  fileTreeSelectedAgentId.value = agentId
  await nextTick()
  // 确保文件树已初始化（setWorkspaceSidebarView 内部也会触发，这里兜底）
  await ensureWorkspaceSidebarFileTree(agent)
  await nextTick()

  // 逐级展开目录：先展开根节点（path=working_dir），再按路径片段逐级向下查找并加载。
  // 根节点默认是收起态，若不展开，其子节点在可见列表中不渲染，后续选中/滚动都会落空。
  let nodes = fileTreeState.value.get(agentId) || []
  const rootNode = nodes.find(n => n.path === rootDir)
  if (rootNode && !rootNode.expanded) {
    await toggleNodeExpand(agentId, rootNode)
    await nextTick()
  }
  let currentPath = rootDir
  for (const seg of segments) {
    currentPath = `${currentPath}/${seg}`
    let node = findNode(nodes, currentPath)
    if (!node) break
    if (!node.expanded) {
      await toggleNodeExpand(agentId, node)
      await nextTick()
    }
    nodes = node.children || []
  }

  // 选中并滚动到目标文件节点
  fileTreeSelectedAgentId.value = agentId
  fileTreeSelectedPath.value = path
  await nextTick()
  scrollFileTreeNodeIntoView(path)
}

// ===== 文件树节点图标：按文件类型区分（自绘 16x16 stroke 线性 SVG，与 agent 图标风格一致）=====
// 目录/文件图标用 currentColor 继承 .folder-icon/.file-icon 的颜色。
const FILE_TREE_FOLDER_SVG = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5v7.5a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5h-4.2a1 1 0 0 0-1 1z"/></svg>'
// 文件树右键菜单图标（自绘 14x14 stroke 线性 SVG，currentColor 继承主题色）
const FILE_TREE_CTX_ICONS = {
  newFile: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.5h5l3 3v10H4z"/><path d="M9 1.5v3h3"/></svg>',
  newFolder: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5v7a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1H8.2L6.7 4.5H2.5a1 1 0 0 0-1 1z"/><path d="M8 7v3M6.5 8.5h3"/></svg>',
  find: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="m10.5 10.5 3.5 3.5"/></svg>',
  refresh: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/><path d="M13.5 2.5v3h-3"/></svg>',
  upload: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 11V3.5M4.5 6 8 2.5 11.5 6"/><path d="M2.5 13.5h11"/></svg>',
  download: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3.5V11M4.5 7.5 8 11l3.5-3.5"/><path d="M2.5 13.5h11"/></svg>',
  copy: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8" rx="1"/><path d="M10.5 5.5v-1a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h1"/></svg>',
  cut: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="4.5" cy="12" r="2"/><circle cx="11.5" cy="12" r="2"/><path d="M6 11 13 3.5M10 11 3 3.5"/></svg>',
  paste: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="10" height="11" rx="1"/><path d="M6 3V2a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v1"/><path d="M6 8h4M6 11h4"/></svg>',
  copyPath: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="9" height="9" rx="1.5"/><path d="M5 12v.5A1.5 1.5 0 0 0 6.5 14h6a1.5 1.5 0 0 0 1.5-1.5v-6A1.5 1.5 0 0 0 12.5 5H12"/></svg>',
  link: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6.5 9.5 9.5 6.5"/><path d="M7 11 5.5 12.5a2.1 2.1 0 0 1-3-3L4 8.2"/><path d="M9 5l1.5-1.5a2.1 2.1 0 0 1 3 3L12 8.2"/></svg>',
  rename: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 13l.8-2.6 7.2-7.2a1.4 1.4 0 0 1 2 2l-7.2 7.2z"/><path d="M3 13h3.5"/></svg>',
  trash: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5"/><path d="M4.5 4.5l.7 8.3a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.3"/><path d="M6.5 7.5v4M9.5 7.5v4"/></svg>',
  removeDir: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.5h10M6.5 4.5V3a1 1 0 0 1 1-1h1a1 1 0 0 1 1 1v1.5"/><path d="M4.5 4.5l.7 8.3a1 1 0 0 0 1 .9h3.6a1 1 0 0 0 1-.9l.7-8.3"/><path d="M6 7.5l4 4M10 7.5l-4 4"/></svg>',
}

const FILE_TYPE_ICON_MAP = {
  // 编程语言
  py: 'python', pyw: 'python',
  cpp: 'cpp', cc: 'cpp', cxx: 'cpp', hpp: 'cpp', hxx: 'cpp',
  c: 'c', h: 'c',
  cs: 'csharp',
  js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript',
  json: 'json',
  java: 'java',
  kt: 'kotlin', kts: 'kotlin',
  go: 'go',
  rs: 'rust',
  rb: 'ruby',
  php: 'php',
  swift: 'swift',
  vue: 'vue',
  svelte: 'svelte',
  ps1: 'powershell', psd1: 'powershell', psm1: 'powershell',
  sh: 'shellcheck', bash: 'shellcheck', zsh: 'shellcheck', fish: 'shellcheck',
  // 标记 / 样式
  html: 'html', htm: 'html',
  css: 'css',
  scss: 'sass', sass: 'sass', less: 'sass',
  xml: 'xml',
  md: 'markdown', markdown: 'markdown',
  toml: 'toml',
  yml: 'yaml', yaml: 'yaml',
  // 配置
  env: 'settings', ini: 'settings', cfg: 'settings', conf: 'settings', properties: 'settings',
  // 数据
  db: 'database', sqlite: 'database', sqlite3: 'database', sql: 'database',
  csv: 'table', tsv: 'table', xls: 'table', xlsx: 'table',
  // 图片
  png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', bmp: 'image', ico: 'image', svg: 'image', avif: 'image',
  // 音视频
  mp3: 'audio', wav: 'audio', ogg: 'audio', flac: 'audio', m4a: 'audio', aac: 'audio',
  mp4: 'video', avi: 'video', mkv: 'video', mov: 'video', webm: 'video', flv: 'video',
  // 文档 / office
  pdf: 'pdf',
  doc: 'word', docx: 'word',
  ppt: 'powerpoint', pptx: 'powerpoint',
  txt: 'document', rtf: 'document',
  log: 'log',
  // 压缩包
  zip: 'zip', tar: 'zip', gz: 'zip', tgz: 'zip', rar: 'zip', '7z': 'zip', bz2: 'zip', xz: 'zip',
  // 二进制 / 可执行
  exe: 'exe', msi: 'exe', dll: 'exe', bin: 'exe', so: 'exe',
  // 字体
  ttf: 'font', otf: 'font', woff: 'font', woff2: 'font', eot: 'font',
  // 安全
  pem: 'lock', key: 'lock', crt: 'lock', p12: 'lock'
}
// 无扩展名但需专属图标的文件名（精确匹配，含点文件）
const FILE_TYPE_ICON_BY_NAME = {
  dockerfile: 'docker',
  makefile: 'settings',
  '.gitignore': 'git',
  '.gitattributes': 'git',
  license: 'document',
  readme: 'document'
}

function getFileTypeIcon(node) {
  if (node.type === 'directory') return FILE_TREE_FOLDER_SVG
  const name = node.name || ''
  const lowerName = name.toLowerCase()
  const dotIdx = lowerName.lastIndexOf('.')
  const ext = dotIdx >= 0 ? lowerName.slice(dotIdx + 1) : ''
  // 先按完整文件名匹配（Dockerfile/Makefile/.gitignore/.env 等）
  let icon = FILE_TYPE_ICON_BY_NAME[lowerName] || ''
  // 再按扩展名匹配（.env → env → settings）
  if (!icon && ext) icon = FILE_TYPE_ICON_MAP[ext] || ''
  if (!icon) {
    // 有扩展名但未匹配到专属图标 → 通用文件图标
    icon = 'document'
  }
  return `<img src="/file-icons/${icon}.svg" alt="" class="file-type-icon">`
}

async function handleFileTreeNodeClick(agentId, node) {
  if (node.type === 'directory') {
    await toggleNodeExpand(agentId, node)
    return
  }

  await openWorkspaceFile(node.path, agentId)
}

// ===== 编辑器目录树键盘操作 =====
// 点击节点时同步光标选中态，使后续方向键从该节点继续移动
function selectFileTreeNode(agentId, node) {
  fileTreeSelectedAgentId.value = agentId
  fileTreeSelectedPath.value = node.path
}

// 将光标选中节点滚动到可视区域内
function scrollFileTreeNodeIntoView(path) {
  nextTick(() => {
    const el = document.querySelector(`.workspace-tree-node[data-node-path="${CSS.escape(path)}"]`)
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' })
  })
}

// 聚焦目录树容器，使方向键/回车可立即生效（优先当前选中 Agent 的树，否则第一个可见的树）
function focusFileTreeContainer() {
  nextTick(() => {
    const agentId = selectedAgentId.value
    let el = agentId
      ? document.querySelector(`.workspace-file-tree-list[data-agent-id="${CSS.escape(agentId)}"]`)
      : null
    if (!el) el = document.querySelector('.workspace-file-tree-list')
    if (el) el.focus()
  })
}

// 在当前 Agent 的可见节点列表中按方向移动光标
function moveFileTreeSelection(agentId, delta) {
  const nodes = getVisibleFileTreeNodes(agentId)
  if (!nodes.length) return
  const currentPath = fileTreeSelectedAgentId.value === agentId ? fileTreeSelectedPath.value : null
  let index = nodes.findIndex((item) => item.node.path === currentPath)
  if (index === -1) {
    index = delta > 0 ? 0 : nodes.length - 1
  } else {
    index = Math.min(nodes.length - 1, Math.max(0, index + delta))
  }
  const target = nodes[index].node
  fileTreeSelectedAgentId.value = agentId
  fileTreeSelectedPath.value = target.path
  scrollFileTreeNodeIntoView(target.path)
}

// 目录树容器键盘事件：上下移动光标，回车展开/折叠目录或打开文件
async function handleFileTreeKeydown(event, agentId) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    moveFileTreeSelection(agentId, event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (event.key === 'Enter') {
    const path = fileTreeSelectedAgentId.value === agentId ? fileTreeSelectedPath.value : null
    if (!path) return
    const nodes = getVisibleFileTreeNodes(agentId)
    const target = nodes.find((item) => item.node.path === path)
    if (!target) return
    event.preventDefault()
    await handleFileTreeNodeClick(agentId, target.node)
  }
}

// node 为目录节点；node 为 null 时表示作用对象是该 Agent 的工作目录根
const fileTreeContextMenu = ref({ visible: false, x: 0, y: 0, agentId: '', node: null })

// 目录树应用内剪贴板：{ mode: 'copy'|'cut', agentId, path, name, kind, content?, children? }
const fileTreeClipboard = ref(null)

// 目录树「上传」：隐藏 file input 与其上下文（记录目标 Agent 与目录）
const fileTreeUploadInput = ref(null)
const fileTreeUploadContext = ref({ agentId: '', dirPath: '' })

// 通用输入弹窗状态（如新建文件/文件夹命名）
const inputPrompt = ref({
  visible: false,
  title: '',
  label: '',
  placeholder: '',
  value: '',
  error: '',
  onConfirm: null,
})

function openInputPrompt({ title, label = '', placeholder = '', value = '', onConfirm }) {
  inputPrompt.value = { visible: true, title, label, placeholder, value, error: '', onConfirm }
}

function cancelInputPrompt() {
  inputPrompt.value = { ...inputPrompt.value, visible: false, onConfirm: null }
}

function confirmInputPrompt() {
  const prompt = inputPrompt.value
  if (!prompt.visible) return
  const result = prompt.onConfirm ? prompt.onConfirm(prompt.value) : null
  // onConfirm 返回字符串表示校验失败，作为错误提示保留弹窗
  if (typeof result === 'string') {
    inputPrompt.value = { ...prompt, error: result }
    return
  }
  inputPrompt.value = { ...prompt, visible: false, onConfirm: null }
}

function closeFileTreeContextMenu() {
  if (fileTreeContextMenu.value.visible) {
    fileTreeContextMenu.value = { ...fileTreeContextMenu.value, visible: false }
  }
}

// 菜单作用目录的绝对路径：目录节点用 node.path，根用 agent.working_dir
function getFileTreeContextDirPath() {
  const menu = fileTreeContextMenu.value
  if (menu.node && menu.node.type === 'directory' && menu.node.path) return menu.node.path
  const agent = resolveFileTreeAgent(menu.agentId)
  return agent?.working_dir || ''
}

// 菜单作用节点的绝对路径：文件节点用 node.path，目录/根用目录路径
function getFileTreeContextTargetPath() {
  const menu = fileTreeContextMenu.value
  if (menu.node && menu.node.type === 'file' && menu.node.path) return menu.node.path
  return getFileTreeContextDirPath()
}

// 菜单作用目录对应的树节点：目录节点返回自身，文件节点/根返回 null（表示工作目录根）
function getFileTreeContextDirNode() {
  const menu = fileTreeContextMenu.value
  if (menu.node && menu.node.type === 'directory') return menu.node
  return null
}

// 绝对路径转相对 working_dir 的路径（不在工作目录内时返回空串）
function toWorkingDirRelativePath(agentId, absPath) {
  const agent = resolveFileTreeAgent(agentId)
  const workingDir = String(agent?.working_dir || '').replace(/\/+$/, '')
  const normalized = String(absPath || '').replace(/\/+$/, '')
  if (!workingDir || !normalized) return ''
  if (normalized === workingDir) return ''
  if (!normalized.startsWith(workingDir + '/')) return ''
  return normalized.slice(workingDir.length + 1)
}

// 复制文本到剪贴板（优先 Clipboard API，非安全上下文回退 execCommand）
async function copyTextToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    if (!document.execCommand('copy')) throw new Error('copy failed')
  } finally {
    document.body.removeChild(textarea)
  }
}

// 在目录树节点/工作目录根上右键：就地弹出菜单（视口坐标 + 边界收敛）
function openFileTreeContextMenu(agent, node, event) {
  if (!agent || !event) return
  const MENU_W = 220
  const MENU_H = 420
  let x = event.clientX
  let y = event.clientY
  if (x + MENU_W > window.innerWidth) x = Math.max(window.innerWidth - MENU_W, 0)
  if (y + MENU_H > window.innerHeight) y = Math.max(window.innerHeight - MENU_H, 0)
  fileTreeContextMenu.value = {
    visible: true,
    x,
    y,
    agentId: agent.agent_id,
    node: node || null,
  }
  // 点击菜单外部时关闭（一次性监听，避免常驻 document 监听）
  nextTick(() => {
    document.addEventListener('pointerdown', closeFileTreeContextMenu, { once: true })
  })
}

const fileTreeContextActions = computed(() => {
  const hasAgent = Boolean(fileTreeContextMenu.value.agentId)
  const hasNode = Boolean(fileTreeContextMenu.value.node)
  // 粘贴可用性：剪贴板存在，且与目标节点相同（同节点跨目录允许，跨节点不支持）
  const menuNodeId = String(resolveFileTreeAgent(fileTreeContextMenu.value.agentId)?.node_id || '').trim()
  const canPaste = hasAgent && Boolean(fileTreeClipboard.value)
    && (!fileTreeClipboard.value.nodeId || !menuNodeId || fileTreeClipboard.value.nodeId === menuNodeId)
  // 「移除」仅对「打开目录」产生的虚拟目录会话可用（真实 Agent 不在此处移除）
  const isVirtualDir = resolveFileTreeAgent(fileTreeContextMenu.value.agentId)?.virtual === true
  // 「下载」仅对文件节点可用（目录/根不支持）
  const isFileNode = fileTreeContextMenu.value.node?.type === 'file'
  return [
    { id: 'new-file', label: '新建文件', icon: FILE_TREE_CTX_ICONS.newFile, enabled: hasAgent },
    { id: 'new-folder', label: '新建文件夹', icon: FILE_TREE_CTX_ICONS.newFolder, enabled: hasAgent },
    { id: 'find-in-folder', label: '在当前目录下查找', icon: FILE_TREE_CTX_ICONS.find, enabled: hasAgent },
    { id: 'refresh', label: '刷新', icon: FILE_TREE_CTX_ICONS.refresh, enabled: hasAgent },
    { id: 'upload', label: '上传', icon: FILE_TREE_CTX_ICONS.upload, enabled: hasAgent },
    { id: 'download', label: '下载', icon: FILE_TREE_CTX_ICONS.download, enabled: isFileNode },
    { id: 'copy', label: '复制', icon: FILE_TREE_CTX_ICONS.copy, enabled: hasNode },
    { id: 'cut', label: '剪切', icon: FILE_TREE_CTX_ICONS.cut, enabled: hasNode },
    { id: 'paste', label: '粘贴', icon: FILE_TREE_CTX_ICONS.paste, enabled: canPaste },
    { id: 'copy-path', label: '复制路径', icon: FILE_TREE_CTX_ICONS.copyPath, enabled: hasAgent },
    { id: 'copy-relative-path', label: '复制相对路径', icon: FILE_TREE_CTX_ICONS.link, enabled: hasAgent },
    { id: 'rename', label: '重命名', icon: FILE_TREE_CTX_ICONS.rename, enabled: hasNode },
    { id: 'delete', label: '删除', icon: FILE_TREE_CTX_ICONS.trash, enabled: hasNode },
    { id: 'remove-dir', label: '移除目录', icon: FILE_TREE_CTX_ICONS.removeDir, enabled: isVirtualDir },
  ]
})

// 把绝对路径转为相对 working_dir 的 glob（用于「在当前目录下查找」）
function buildDirSearchGlob(agentId, dirPath) {
  const agent = resolveFileTreeAgent(agentId)
  const workingDir = String(agent?.working_dir || '').replace(/\/$/, '')
  const normalizedDir = String(dirPath || '').replace(/\/$/, '')
  if (!workingDir || !normalizedDir || normalizedDir === workingDir) return ''
  if (!normalizedDir.startsWith(workingDir + '/')) return ''
  const relative = normalizedDir.slice(workingDir.length + 1)
  return relative ? `${relative}/**` : ''
}

// 执行目录树右键菜单动作
async function runFileTreeContextAction(action) {
  if (!action || action.enabled === false) return
  const menu = { ...fileTreeContextMenu.value }
  const agent = resolveFileTreeAgent(menu.agentId)
  closeFileTreeContextMenu()
  if (!agent) return

  if (action.id === 'remove-dir') {
    removeWorkspaceDir(agent.agent_id)
    return
  }

  if (action.id === 'new-file' || action.id === 'new-folder') {
    const kind = action.id === 'new-file' ? 'file' : 'directory'
    const label = kind === 'file' ? '文件' : '文件夹'
    const dirPath = getFileTreeContextDirPath() || agent.working_dir
    openInputPrompt({
      title: `新建${label}`,
      label: `${label}名称`,
      placeholder: `请输入新${label}名称`,
      value: '',
      onConfirm: (rawName) => {
        const trimmedName = String(rawName || '').trim()
        if (!trimmedName) return '名称不能为空'
        if (trimmedName.includes('/') || trimmedName.includes('\\')) return '名称不能包含路径分隔符'
        const absPath = `${String(dirPath).replace(/\/$/, '')}/${trimmedName}`
        createFileOrDirectory(agent.agent_id, absPath, kind)
          .then(() => refreshFileTreeDir(agent.agent_id, menu.node))
          .then(() => (kind === 'file' ? openWorkspaceFile(absPath, agent.agent_id) : null))
          .then(() => showToast(`${label}已创建`, 'success'))
          .catch((error) => showToast(error.message || `创建${label}失败`, 'error'))
        return null
      },
    })
    return
  }

  if (action.id === 'find-in-folder') {
    const dirPath = getFileTreeContextDirPath()
    globalSearchFileGlob.value = buildDirSearchGlob(agent.agent_id, dirPath)
    setWorkspaceSidebarView('search')
    nextTick(() => {
      const input = document.querySelector('.workspace-global-search-input')
      if (input) input.focus()
    })
    return
  }

  if (action.id === 'refresh') {
    await refreshFileTreeDir(agent.agent_id, menu.node)
    return
  }

  if (action.id === 'upload') {
    // 上传目标目录：目录节点用自身路径，文件节点/根回退到工作目录
    const dirPath = getFileTreeContextDirPath() || agent.working_dir
    if (!dirPath) {
      showToast('无法确定上传目录', 'error')
      return
    }
    uploadFileToDir(agent.agent_id, dirPath)
    return
  }

  if (action.id === 'download') {
    const targetPath = getFileTreeContextTargetPath()
    if (!targetPath) return
    await downloadFileFromNode(agent.agent_id, targetPath)
    return
  }

  if (action.id === 'copy' || action.id === 'cut') {
    const node = menu.node
    if (!node || !node.path) return
    await setFileTreeClipboard(action.id === 'cut' ? 'cut' : 'copy', agent.agent_id, node)
    return
  }

  if (action.id === 'paste') {
    const destDir = getFileTreeContextDirPath()
    if (!destDir) return
    await pasteFileTreeClipboard(agent.agent_id, destDir)
    await refreshFileTreeDir(agent.agent_id, getFileTreeContextDirNode())
    return
  }

  if (action.id === 'copy-path') {
    const targetPath = getFileTreeContextTargetPath()
    if (!targetPath) return
    try {
      await copyTextToClipboard(targetPath)
      showToast('路径已复制', 'success')
    } catch (error) {
      showToast('复制路径失败', 'error')
    }
    return
  }

  if (action.id === 'copy-relative-path') {
    const targetPath = getFileTreeContextTargetPath()
    if (!targetPath) return
    const relativePath = toWorkingDirRelativePath(agent.agent_id, targetPath)
    if (!relativePath) {
      showToast('该路径不在工作目录内，无法生成相对路径', 'error')
      return
    }
    try {
      await copyTextToClipboard(relativePath)
      showToast('相对路径已复制', 'success')
    } catch (error) {
      showToast('复制相对路径失败', 'error')
    }
    return
  }

  if (action.id === 'rename') {
    const node = menu.node
    if (!node || !node.path) return
    const isDir = node.type === 'directory'
    const parentPath = String(node.path).replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '/'
    openInputPrompt({
      title: `重命名${isDir ? '文件夹' : '文件'}`,
      label: '新名称',
      placeholder: `请输入新的${isDir ? '文件夹' : '文件'}名称`,
      value: node.name || '',
      onConfirm: (rawName) => {
        const trimmedName = String(rawName || '').trim()
        if (!trimmedName) return '名称不能为空'
        if (trimmedName.includes('/') || trimmedName.includes('\\')) return '名称不能包含路径分隔符'
        if (trimmedName === node.name) return null
        const newAbsPath = `${parentPath.replace(/\/$/, '')}/${trimmedName}`
        renameFileOrDirectory(agent.agent_id, node.path, newAbsPath)
          .then(() => refreshFileTreeDir(agent.agent_id, menu.node))
          .then(() => showToast('重命名成功', 'success'))
          .catch((error) => showToast(error.message || '重命名失败', 'error'))
        return null
      },
    })
    return
  }

  if (action.id === 'delete') {
    const node = menu.node
    if (!node || !node.path) return
    const isDir = node.type === 'directory'
    const confirmMessage = isDir
      ? `确定要删除文件夹 "${node.name}" 及其全部内容吗？此操作不可恢复。`
      : `确定要删除文件 "${node.name}" 吗？此操作不可恢复。`
    showConfirm(
      confirmMessage,
      () => {
        deleteFileOrDirectory(agent.agent_id, node.path, isDir)
          .then(() => refreshFileTreeDir(agent.agent_id, menu.node))
          .then(() => showToast('已删除', 'success'))
          .catch((error) => showToast(error.message || '删除失败', 'error'))
      },
      () => {},
      false
    )
  }
}

function uploadFileToDir(agentId, dirPath) {
  fileTreeUploadContext.value = { agentId, dirPath }
  const input = fileTreeUploadInput.value
  if (!input) return
  // 重置 value，允许重复选择同一个文件
  input.value = ''
  input.click()
}

// 读取本地文件为 dataURL（后端 /file-upload 支持 dataURL 前缀，二进制安全）
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })
}

// 隐藏 file input 变更：逐个上传到目标目录（保留原文件名），完成后刷新目录树
async function onFileTreeUploadInputChange(event) {
  const input = event?.target
  const files = Array.from(input?.files || [])
  const { agentId, dirPath } = fileTreeUploadContext.value
  if (input) input.value = ''
  if (!files.length || !agentId || !dirPath) return
  const agent = resolveFileTreeAgent(agentId)
  if (!agent || !agent.node_id) {
    showToast('找不到目标 Agent 节点', 'error')
    return
  }
  const { host, port } = getGatewayAddress()
  const targetNodeId = String(agent.node_id).trim()
  const baseDir = String(dirPath).replace(/\/+$/, '')
  let okCount = 0
  const errors = []
  for (const file of files) {
    try {
      const data = await readFileAsDataUrl(file)
      const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-upload'), {
        method: 'POST',
        body: JSON.stringify({ path: `${baseDir}/${file.name}`, data, node_id: targetNodeId })
      })
      const result = await response.json()
      if (!response.ok || !result.success) {
        throw new Error(result.error?.message || '上传失败')
      }
      okCount += 1
    } catch (error) {
      errors.push(`${file.name}: ${error.message || '上传失败'}`)
    }
  }
  await refreshFileTreeDir(agentId, getFileTreeContextDirNode())
  if (errors.length === 0) {
    showToast(`已上传 ${okCount} 个文件`, 'success')
  } else if (okCount > 0) {
    showToast(`已上传 ${okCount} 个文件，${errors.length} 个失败：${errors[0]}`, 'error')
  } else {
    showToast(errors[0] || '上传失败', 'error')
  }
}

// 下载节点上的文件到本地浏览器（走 /file-content，仅支持文本 ≤10MB）
async function downloadFileFromNode(agentId, filePath) {
  const agent = resolveFileTreeAgent(agentId)
  if (!agent || !agent.node_id) {
    showToast('找不到目标 Agent 节点', 'error')
    return
  }
  const { host, port } = getGatewayAddress()
  const targetNodeId = String(agent.node_id).trim()
  try {
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-content'), {
      method: 'POST',
      body: JSON.stringify({ path: filePath, node_id: targetNodeId })
    })
    const result = await response.json()
    if (!response.ok || !result.success || !result.data) {
      throw new Error(result.error?.message || '下载失败')
    }
    const content = result.data.content || ''
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const objectUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = String(filePath).split('/').filter(Boolean).pop() || 'download.txt'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(objectUrl)
    showToast('已开始下载', 'success')
  } catch (error) {
    showToast(error.message || '下载失败', 'error')
  }
}

// 刷新指定目录节点（node 为 null 时刷新工作目录根）
async function refreshFileTreeDir(agentId, node) {
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) return
  if (!node) {
    fileTreeState.value.delete(agentId)
    initFileTreeState(agentId)
    await initFileTree(agentId, agent.working_dir)
    triggerRef(fileTreeState)
    return
  }
  node.loaded = false
  node.children = []
  await loadFileTreeNode(agentId, node)
  triggerRef(fileTreeState)
}

async function createFileOrDirectory(agentId, absPath, kind) {
  const { host, port } = getGatewayAddress()
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-create'), {
    method: 'POST',
    body: JSON.stringify({ path: absPath, content: '', kind, node_id: targetNodeId })
  })
  const result = await response.json()
  if (!response.ok || !result.success) {
    throw new Error(result.error?.message || '创建失败')
  }
  return result.data
}

// 调用后端删除文件/目录接口（目录需 recursive 才可递归删除）
async function deleteFileOrDirectory(agentId, absPath, recursive = false) {
  const { host, port } = getGatewayAddress()
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-delete'), {
    method: 'POST',
    body: JSON.stringify({ path: absPath, recursive, node_id: targetNodeId })
  })
  const result = await response.json()
  if (!response.ok || !result.success) {
    throw new Error(result.error?.message || '删除失败')
  }
  return result.data
}

// 调用后端重命名/移动文件/目录接口（不覆盖已存在路径）
async function renameFileOrDirectory(agentId, absPath, newAbsPath) {
  const { host, port } = getGatewayAddress()
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) {
    throw new Error(`找不到Agent: ${agentId}`)
  }
  if (!agent.node_id) {
    throw new Error(`Agent没有node_id: ${agentId}`)
  }
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-rename'), {
    method: 'POST',
    body: JSON.stringify({ path: absPath, new_path: newAbsPath, node_id: targetNodeId })
  })
  const result = await response.json()
  if (!response.ok || !result.success) {
    throw new Error(result.error?.message || '重命名失败')
  }
  return result.data
}

async function listDirectoryEntries(agentId, dirPath) {
  const { host, port } = getGatewayAddress()
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) throw new Error(`找不到Agent: ${agentId}`)
  if (!agent.node_id) throw new Error(`Agent没有node_id: ${agentId}`)
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(
    buildNodeHttpUrl(host, port, targetNodeId, `directories?path=${encodeURIComponent(dirPath)}`)
  )
  const result = await response.json()
  if (!response.ok || !result.success) {
    throw new Error(result.error?.message || '读取目录失败')
  }
  return result.data.items || []
}

// 递归收集目录内容（文件读取内容，目录保留结构）
async function collectDirectorySnapshot(agentId, dirPath) {
  const entries = await listDirectoryEntries(agentId, dirPath)
  const children = []
  for (const entry of entries) {
    if (entry.type === 'directory') {
      children.push({
        name: entry.name,
        kind: 'directory',
        children: await collectDirectorySnapshot(agentId, entry.path),
      })
    } else {
      const content = await fetchFileContent(entry.path, agentId)
      children.push({ name: entry.name, kind: 'file', content })
    }
  }
  return children
}

// 把剪贴板节点写入目标目录（文件写入内容，目录递归重建）
async function writeClipboardNode(agentId, destDir, node) {
  const absPath = `${String(destDir).replace(/\/$/, '')}/${node.name}`
  if (node.kind === 'directory') {
    await createFileOrDirectory(agentId, absPath, 'directory')
    for (const child of node.children || []) {
      await writeClipboardNode(agentId, absPath, child)
    }
    return
  }
  await writeFileContent(agentId, absPath, node.content ?? '')
}

// 在目标目录中生成不冲突的名称：name.ext -> name (副本).ext -> name (副本 2).ext
async function resolvePasteName(agentId, destDir, name) {
  const existing = new Set((await listDirectoryEntries(agentId, destDir)).map(i => i.name))
  if (!existing.has(name)) return name
  const dotIndex = name.lastIndexOf('.')
  const hasExt = dotIndex > 0
  const base = hasExt ? name.slice(0, dotIndex) : name
  const ext = hasExt ? name.slice(dotIndex) : ''
  let candidate = `${base} (副本)${ext}`
  let counter = 2
  while (existing.has(candidate)) {
    candidate = `${base} (副本 ${counter})${ext}`
    counter++
  }
  return candidate
}

// 复制/剪切：把节点内容存入应用内剪贴板
async function setFileTreeClipboard(mode, agentId, node) {
  if (!node || !node.path) return
  const kind = node.type === 'directory' ? 'directory' : 'file'
  // 记录来源节点：粘贴时以 node_id 判定是否跨节点（同节点跨目录允许，跨节点不支持）
  const sourceNodeId = String(resolveFileTreeAgent(agentId)?.node_id || '').trim()
  try {
    if (kind === 'directory') {
      const children = await collectDirectorySnapshot(agentId, node.path)
      fileTreeClipboard.value = { mode, agentId, nodeId: sourceNodeId, path: node.path, name: node.name, kind, children }
    } else {
      const content = await fetchFileContent(node.path, agentId)
      fileTreeClipboard.value = { mode, agentId, nodeId: sourceNodeId, path: node.path, name: node.name, kind, content }
    }
    showToast(mode === 'cut' ? '已剪切，可在目标目录粘贴' : '已复制，可在目标目录粘贴', 'success')
  } catch (error) {
    showToast(error.message || '复制失败', 'error')
  }
}

// 粘贴：把剪贴板内容写入目标目录
async function pasteFileTreeClipboard(agentId, destDir) {
  const clip = fileTreeClipboard.value
  if (!clip) return
  // 以 node_id 判定：同节点跨目录允许；跨节点需要文件内容传输，暂不支持
  const targetNodeId = String(resolveFileTreeAgent(agentId)?.node_id || '').trim()
  if (clip.nodeId && targetNodeId && clip.nodeId !== targetNodeId) {
    showToast('暂不支持跨节点粘贴', 'error')
    return
  }
  const normalizedDest = String(destDir).replace(/\/+$/, '')
  const sourceParent = String(clip.path).replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '/'
  if (clip.mode === 'cut' && sourceParent === normalizedDest) {
    showToast('源与目标目录相同，无需粘贴', 'info')
    return
  }
  try {
    if (clip.mode === 'cut') {
      const targetPath = `${normalizedDest}/${clip.name}`
      await renameFileOrDirectory(agentId, clip.path, targetPath)
      fileTreeClipboard.value = null
      showToast('已移动', 'success')
    } else {
      const finalName = await resolvePasteName(agentId, normalizedDest, clip.name)
      await writeClipboardNode(agentId, normalizedDest, { ...clip, name: finalName })
      showToast('已粘贴', 'success')
    }
  } catch (error) {
    showToast(error.message || '粘贴失败', 'error')
  }
}

const fileTreeDragState = ref(null)
// 当前高亮的放置目标目录路径（用于视觉反馈）
const fileTreeDropTargetPath = ref('')

// 拖拽开始：记录源节点信息（不做任何后端读取，避免拖拽卡顿）
function handleFileTreeDragStart(event, agentId, node) {
  if (!node || !node.path) return
  const sourceNodeId = String(resolveFileTreeAgent(agentId)?.node_id || '').trim()
  fileTreeDragState.value = {
    agentId,
    nodeId: sourceNodeId,
    path: node.path,
    name: node.name,
    kind: node.type === 'directory' ? 'directory' : 'file',
  }
  fileTreeDropTargetPath.value = ''
  if (event.dataTransfer) {
    // 部分浏览器要求设置数据才会触发 drop
    event.dataTransfer.effectAllowed = 'copyMove'
    try { event.dataTransfer.setData('text/plain', node.path) } catch (e) { /* 忽略 */ }
  }
}

// 拖拽结束：清理状态与高亮
function handleFileTreeDragEnd() {
  fileTreeDragState.value = null
  fileTreeDropTargetPath.value = ''
}

// 放置目标是否为合法目录：同节点、非源自身、非源目录的子孙、且不是源所在目录本身
function isValidFileTreeDropTarget(targetDirPath) {
  const drag = fileTreeDragState.value
  if (!drag || !targetDirPath) return false
  const normalizedTarget = String(targetDirPath).replace(/\/+$/, '')
  const normalizedSource = String(drag.path).replace(/\/+$/, '')
  // 不能放到自身（目录拖到自己上）
  if (normalizedTarget === normalizedSource) return false
  // 不能放到源所在目录（原地无变化）
  const sourceParent = normalizedSource.split('/').slice(0, -1).join('/') || '/'
  if (normalizedTarget === sourceParent) return false
  // 目录不能拖进自己的子孙目录（会导致自嵌套）
  if (drag.kind === 'directory' && normalizedTarget.startsWith(normalizedSource + '/')) return false
  return true
}

// 拖到目录节点/根节点上方：高亮（仅合法目标）
function handleFileTreeDragOver(event, dirPath) {
  const drag = fileTreeDragState.value
  if (!drag) return
  // 跨节点直接拒绝（不显示可放置反馈）
  const targetNodeId = String(resolveFileTreeAgent(drag.agentId)?.node_id || '').trim()
  if (drag.nodeId && targetNodeId && drag.nodeId !== targetNodeId) return
  if (!isValidFileTreeDropTarget(dirPath)) return
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = (event.ctrlKey || event.metaKey) ? 'copy' : 'move'
  }
  fileTreeDropTargetPath.value = String(dirPath).replace(/\/+$/, '')
}

// 离开放置目标：清除高亮（仅当离开的正是当前高亮目标）
function handleFileTreeDragLeave(dirPath) {
  const normalized = String(dirPath || '').replace(/\/+$/, '')
  if (fileTreeDropTargetPath.value === normalized) fileTreeDropTargetPath.value = ''
}

// 放置：按住 Ctrl/⌘ 为复制，否则为移动；同目录树内操作
async function handleFileTreeDrop(event, agentId, destDir) {
  event.preventDefault()
  const drag = fileTreeDragState.value
  fileTreeDropTargetPath.value = ''
  if (!drag) return
  // 硬约束：仅同一目录树（同 node_id）内允许
  const targetNodeId = String(resolveFileTreeAgent(agentId)?.node_id || '').trim()
  if (drag.nodeId && targetNodeId && drag.nodeId !== targetNodeId) {
    showToast('仅支持在同一目录树内拖放', 'error')
    fileTreeDragState.value = null
    return
  }
  if (!isValidFileTreeDropTarget(destDir)) {
    fileTreeDragState.value = null
    return
  }
  const normalizedDest = String(destDir).replace(/\/+$/, '')
  const isCopy = event.ctrlKey || event.metaKey
  fileTreeDragState.value = null
  try {
    if (isCopy) {
      // 复制：读取源内容（目录递归）→ 以不冲突的名称写入目标目录
      const snapshot = drag.kind === 'directory'
        ? { kind: 'directory', children: await collectDirectorySnapshot(agentId, drag.path) }
        : { kind: 'file', content: await fetchFileContent(drag.path, agentId) }
      const finalName = await resolvePasteName(agentId, normalizedDest, drag.name)
      await writeClipboardNode(agentId, normalizedDest, { ...snapshot, name: finalName })
      showToast('已复制', 'success')
    } else {
      // 移动：复用 file-rename（不覆盖已存在路径）
      const targetPath = `${normalizedDest}/${drag.name}`
      await renameFileOrDirectory(agentId, drag.path, targetPath)
      showToast('已移动', 'success')
    }
    // 刷新目标目录；移动时源目录也需刷新
    await refreshFileTreeDir(agentId, resolveFileTreeDirNodeByPath(agentId, normalizedDest))
    if (!isCopy) {
      const sourceParent = String(drag.path).replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '/'
      if (sourceParent !== normalizedDest) {
        await refreshFileTreeDir(agentId, resolveFileTreeDirNodeByPath(agentId, sourceParent))
      }
    }
  } catch (error) {
    showToast(error.message || (isCopy ? '复制失败' : '移动失败'), 'error')
  }
}

function resolveFileTreeDirNodeByPath(agentId, dirPath) {
  const agent = resolveFileTreeAgent(agentId)
  const workingDir = String(agent?.working_dir || '').replace(/\/+$/, '')
  const normalized = String(dirPath || '').replace(/\/+$/, '')
  if (!workingDir || !normalized || normalized === workingDir) return null
  const nodes = fileTreeState.value.get(agentId) || []
  const stack = [...nodes]
  while (stack.length) {
    const node = stack.pop()
    if (node.type === 'directory' && String(node.path).replace(/\/+$/, '') === normalized) return node
    if (Array.isArray(node.children) && node.children.length) stack.push(...node.children)
  }
  return null
}

// 写入文件内容（粘贴用，覆盖目标路径）
async function writeFileContent(agentId, absPath, content) {
  const { host, port } = getGatewayAddress()
  const agent = resolveFileTreeAgent(agentId)
  if (!agent) throw new Error(`找不到Agent: ${agentId}`)
  if (!agent.node_id) throw new Error(`Agent没有node_id: ${agentId}`)
  const targetNodeId = String(agent.node_id).trim()
  const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, 'file-write'), {
    method: 'POST',
    body: JSON.stringify({ path: absPath, content, node_id: targetNodeId })
  })
  const result = await response.json()
  if (!response.ok || !result.success) {
    throw new Error(result.error?.message || '写入文件失败')
  }
  return result.data
}

function initFileTreeState(agentId) {
  if (!fileTreeState.value.has(agentId)) {
    fileTreeState.value.set(agentId, [])
    fileTreeExpanded.value.set(agentId, new Set())
    fileTreeLoading.value.set(agentId, new Set())
  }
}

// 加载文件树节点的子目录
async function loadFileTreeNode(agentId, node) {
  const loadingSet = fileTreeLoading.value.get(agentId)
  if (!loadingSet) return
  
  // 标记为加载中
  loadingSet.add(node.path)
  
  try {
    const { host, port } = getGatewayAddress()
    // 使用当前Agent的node_id，而不是编辑器会话的node_id
    // 虚拟目录会话（未创建 Agent 时直接打开某节点的目录）不在 agentList 中，从其 agent 信息里取 node_id
    const agent = agentList.value.find(a => a.agent_id === agentId) || getVirtualWorkspaceAgent(agentId)
    if (!agent) {
      console.error('[FILETREE] 找不到Agent:', agentId)
      return
    }
    if (!agent.node_id) {
      console.error('[FILETREE] Agent没有node_id:', agent)
      return
    }
    const targetNodeId = String(agent.node_id).trim()
    const response = await fetchWithAuth(buildNodeHttpUrl(host, port, targetNodeId, `directories?path=${encodeURIComponent(node.path)}`))
    
    if (!response.ok) {
      const error = await response.json()
      console.error('[FILETREE] 加载目录失败:', error)
      return
    }
    
    const result = await response.json()
    if (result.success && result.data) {
      // 转换为树节点格式
      const children = (result.data.items || []).map(item => {
        // 文件节点不需要 children 和 loaded 字段
        if (item.type === 'file') {
          return {
            name: item.name,
            path: item.path,
            type: 'file'
          }
        }
        // 目录节点需要 children 和 loaded 字段
        return {
          name: item.name,
          path: item.path,
          type: 'directory',
          expanded: false,
          loaded: false,
          children: []
        }
      })
      
      // 更新节点的子节点
      node.children = children
      node.loaded = true
    }
  } catch (error) {
    console.error('[FILETREE] 加载目录出错:', error)
  } finally {
    // 移除加载状态
    loadingSet.delete(node.path)
  }
}

// 初始化文件树（加载根目录）
async function initFileTree(agentId, rootPath) {
  initFileTreeState(agentId)
  
  // 创建根节点
  const rootNode = {
    name: rootPath.split('/').pop() || rootPath,
    path: rootPath,
    type: 'directory',
    expanded: false,
    loaded: false,
    children: []
  }
  
  // 加载根目录的内容
  await loadFileTreeNode(agentId, rootNode)
  
  // 保存到状态
  fileTreeState.value.set(agentId, [rootNode])
}

function flattenVisibleFileTreeNodes(nodes, depth = 0) {
  const visibleNodes = []

  for (const node of nodes) {
    visibleNodes.push({ node, depth })

    if (node.expanded && node.children && node.children.length > 0) {
      visibleNodes.push(...flattenVisibleFileTreeNodes(node.children, depth + 1))
    }
  }

  return visibleNodes
}

function getVisibleFileTreeNodes(agentId) {
  const treeNodes = fileTreeState.value.get(agentId) || []
  return flattenVisibleFileTreeNodes(treeNodes)
}

// 递归查找节点
function findNode(nodes, path) {
  for (const node of nodes) {
    if (node.path === path) {
      return node
    }
    if (node.children && node.children.length > 0) {
      const found = findNode(node.children, path)
      if (found) return found
    }
  }
  return null
}

// 切换节点展开/收缩
async function toggleNodeExpand(agentId, node) {
  const expandedSet = fileTreeExpanded.value.get(agentId)
  if (!expandedSet) return
  
  if (node.expanded) {
    // 收缩
    node.expanded = false
    expandedSet.delete(node.path)
  } else {
    // 展开
    node.expanded = true
    expandedSet.add(node.path)
    
    // 如果未加载过子节点，则加载
    if (!node.loaded) {
      await loadFileTreeNode(agentId, node)
    }
  }
}

  return {
    // 状态（供 App.vue 保留代码/template 访问）
    fileTreeState,
    fileTreeExpanded,
    fileTreeLoading,
    expandedAgents,
    selectedAgentId,
    fileTreeSelectedPath,
    fileTreeSelectedAgentId,
    fileTreeContextMenu,
    fileTreeUploadInput,
    inputPrompt,
    fileTreeDropTargetPath,
    // 节点交互
    getFileTypeIcon,
    handleFileTreeNodeClick,
    selectFileTreeNode,
    focusFileTreeContainer,
    revealTabInFileTree,
    toggleAgentExpanded,
    toggleStoppedNodeCollapse,
    isStoppedNodeCollapsed,
    // 键盘导航
    handleFileTreeKeydown,
    // 右键菜单
    copyTextToClipboard,
    openFileTreeContextMenu,
    cancelInputPrompt,
    confirmInputPrompt,
    fileTreeContextActions,
    runFileTreeContextAction,
    // 上传下载
    readFileAsDataUrl,
    onFileTreeUploadInputChange,
    // 拖拽
    handleFileTreeDragStart,
    handleFileTreeDragEnd,
    handleFileTreeDragOver,
    handleFileTreeDragLeave,
    handleFileTreeDrop,
    // 核心加载
    initFileTree,
    getVisibleFileTreeNodes,
  }
}