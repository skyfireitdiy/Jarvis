// AutoWorker 插件前端侧边栏视图。
// 约定：纯浏览器 ES module，用 window.Vue 渲染，导出 default 组件，不 import 'vue'。
// 功能：在编辑器左侧管理后端工作目录下的一批任务：
//   - 设置区：配置后端工作目录（localStorage 持久化）；
//   - 任务列表：按状态分组展示，支持创建/编辑/标记完成/放弃；
//   - 右键菜单：创建 Agent 执行该任务（Agent working_dir = 任务子目录）；
//              在工作目录下创建 Agent（Agent working_dir = 插件工作目录；不写提示词、只创建不运行）；
//   - 定时轮询 + 手动刷新。
// 认证：所有读写经宿主 window.__jarvisFetch（自动携带 jarvis 认证），
//       通过插件功能代理端点 /api/plugins/master/function-call 调用插件私有功能层。

const PLUGIN = "autoworker";
// 旧版单工作目录持久化 key（v0.1.0，无节点概念，迁移到 master 节点用）。
const LEGACY_WORKDIR_KEY = "jarvis_autoworker_workdir";
// 每节点工作目录列表持久化 key 前缀：jarvis_autoworker_dirs_<node>（JSON 数组）。
const DIRS_KEY_PREFIX = "jarvis_autoworker_dirs_";
// 每节点当前激活工作目录持久化 key 前缀：jarvis_autoworker_active_<node>。
const ACTIVE_DIR_KEY_PREFIX = "jarvis_autoworker_active_";
// 每节点工作目录历史上限（最近使用在前，超出截断）。
const DIRS_HISTORY_MAX = 10;
// 轮询间隔（毫秒）。
const POLL_INTERVAL = 15000;

// 按节点生成目录列表存储 key
function dirsKey(nodeId) {
  return DIRS_KEY_PREFIX + (String(nodeId || "master").trim() || "master");
}
// 按节点生成激活目录存储 key
function activeDirKey(nodeId) {
  return ACTIVE_DIR_KEY_PREFIX + (String(nodeId || "master").trim() || "master");
}

// 复刻 App.vue 的 gateway 地址解析（侧边栏组件无 props 注入，需自行解析）
function parseGatewayAddress(address) {
  address = (address || "").trim();
  if (!address) return null;
  if (address.includes("://")) {
    try {
      const url = new URL(address);
      return {
        protocol: url.protocol.replace(":", ""),
        host: url.hostname,
        port:
          url.port ||
          (url.protocol === "https:" || url.protocol === "wss:" ? "443" : "80"),
        path: url.pathname,
      };
    } catch {
      return null;
    }
  }
  if (address.includes(":")) {
    const parts = address.split(":");
    if (parts.length === 2) {
      return { protocol: null, host: parts[0], port: parts[1], path: "" };
    }
  }
  return { protocol: null, host: address, port: "8000", path: "" };
}

// 获取当前页面的 HTTP 协议（与 App.vue getHttpProtocol 一致）
function getHttpProtocol() {
  return window.location.protocol === "https:" ? "https" : "http";
}

function gatewayBase() {
  const parsed = parseGatewayAddress(
    localStorage.getItem("jarvis_gateway_url") || "",
  );
  const host = (parsed && parsed.host) || "127.0.0.1";
  const port = (parsed && parsed.port) || "8000";
  // 协议：显式指定（https）则用之；否则用当前页面协议（与 App.vue 一致），
  // 避免 HTTPS 页面请求 http 地址导致混合内容被浏览器阻止。
  const protocol =
    parsed && parsed.protocol === "https" ? "https" : getHttpProtocol();
  return `${protocol}://${host}:${port}`;
}

// 通过 gateway 插件功能代理端点调用插件私有功能
// nodeId 指定目标节点（默认 master）：任务数据与操作都落在该节点上
async function callFunction(functionName, args, nodeId) {
  const authedFetch =
    (typeof window !== "undefined" && window.__jarvisFetch) || fetch;
  const targetNodeId = String(nodeId || "master").trim() || "master";
  const resp = await authedFetch(
    `${gatewayBase()}/api/plugins/${encodeURIComponent(targetNodeId)}/function-call`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plugin: PLUGIN,
        function: functionName,
        arguments: args || {},
      }),
    },
  );
  let result;
  try {
    result = await resp.json();
  } catch (e) {
    throw new Error("网关响应异常", { cause: e });
  }
  if (!result.success) {
    const err = result.error || {};
    throw new Error(err.message || err.code || "调用失败");
  }
  const payload = result.result || {};
  if (payload.success === false) {
    throw new Error(payload.error || "操作失败");
  }
  return payload;
}

// 返回本地当天日期（YYYY-MM-DD），用作 <input type="date"> 的默认值。
// 注意：不能用 toISOString()，它会先转 UTC，东八区等时区可能相差一天。
function todayStr() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// 状态展示与排序权重
const STATUS_LABELS = {
  pending: "待执行",
  running: "执行中",
  completed: "已完成",
  abandoned: "已放弃",
};
const STATUS_COLORS = {
  pending: "#d29922",
  running: "#58a6ff",
  completed: "#3fb950",
  abandoned: "#888",
};
const STATUS_ORDER = ["running", "pending", "completed", "abandoned"];

export default {
  name: "AutoWorkerSidebarView",
  props: {
    workingDir: { type: String, default: "" },
  },
  data() {
    return {
      // 状态映射暴露到实例，供模板使用（模板无法访问模块作用域变量）
      STATUS_LABELS,
      STATUS_COLORS,
      // 节点列表与当前节点（master 恒在列）
      nodes: [],
      nodeId: "master",
      // 当前节点的后端工作目录列表（localStorage 按节点持久化）
      dirs: [],
      dirInput: "",
      // 当前激活的后端工作目录（任务子目录的父目录）
      workdir: "",
      workdirEditing: false,
      // 当前活跃 Agent（用于提示）
      agentName: "",
      // 任务列表与视图状态
      tasks: [],
      loading: false,
      error: "",
      message: "",
      // 详情/编辑
      selected: null,
      editForm: { title: "", description: "", tags: "", due_date: todayStr() },
      // 手动添加关键信息（note）输入
      noteInput: "",
      // 新建任务表单
      creating: false,
      createForm: { title: "", description: "", tags: "", due_date: todayStr() },
      // 右键菜单
      menuVisible: false,
      menuStyle: {},
      menuItem: null,
      busy: false,
    };
  },
  computed: {
    groupedTasks() {
      const groups = {};
      for (const s of STATUS_ORDER) groups[s] = [];
      for (const t of this.tasks) {
        const s = STATUS_LABELS[t.status] ? t.status : "pending";
        groups[s].push(t);
      }
      return STATUS_ORDER.filter((s) => groups[s].length > 0).map((s) => ({
        status: s,
        label: STATUS_LABELS[s],
        color: STATUS_COLORS[s],
        items: groups[s],
      }));
    },
  },
  mounted() {
    this.initNodes();
    this.restoreWorkdir();
    this.refreshAgentName();
    if (this.workdir) this.refresh();
    // 订阅宿主 agent_changed 事件：切换 Agent 时同步刷新顶部名称
    const on = typeof window !== "undefined" && window.__jarvisOn;
    if (typeof on === "function") {
      this._offAgentChanged = on("agent_changed", () => {
        this.refreshAgentName();
      });
    }
    // 定时轮询（有工作目录时）
    this._pollTimer = setInterval(() => {
      if (this.workdir && !this.loading && !this.selected) this.refresh(true);
    }, POLL_INTERVAL);
    // 点击别处 / 按 Esc 关闭右键菜单
    this._onDocClick = () => this.closeItemMenu();
    this._onDocKeydown = (e) => {
      if (e.key === "Escape") this.closeItemMenu();
    };
    document.addEventListener("click", this._onDocClick);
    document.addEventListener("keydown", this._onDocKeydown);
  },
  beforeUnmount() {
    if (typeof this._offAgentChanged === "function") this._offAgentChanged();
    if (this._pollTimer) clearInterval(this._pollTimer);
    document.removeEventListener("click", this._onDocClick);
    document.removeEventListener("keydown", this._onDocKeydown);
  },
  watch: {
    workingDir() {
      this.refreshAgentName();
    },
  },
  methods: {
    // ---- 节点管理 ----
    // 加载节点列表（__jarvisGetNodes，master 恒在列），并恢复上次选中的节点
    initNodes() {
      const getNodes =
        typeof window !== "undefined" && window.__jarvisGetNodes;
      if (typeof getNodes !== "function") {
        this.nodes = [{ node_id: "master", status: "running" }];
        return;
      }
      try {
        const list = getNodes() || [];
        const nodes = Array.isArray(list)
          ? list.filter((n) => n && String(n.node_id || "").trim())
          : [];
        // 确保 master 恒在列
        if (!nodes.some((n) => n.node_id === "master")) {
          nodes.unshift({ node_id: "master", status: "running" });
        }
        this.nodes = nodes;
      } catch {
        this.nodes = [{ node_id: "master", status: "running" }];
        return;
      }
      // 恢复上次选中的节点（若仍存在）
      let savedNode = "master";
      try {
        savedNode = (localStorage.getItem("jarvis_autoworker_node") || "master").trim() || "master";
      } catch {
        /* 忽略 */
      }
      if (this.nodes.some((n) => n.node_id === savedNode)) {
        this.nodeId = savedNode;
      } else {
        this.nodeId = this.nodes[0]?.node_id || "master";
      }
    },
    // 切换节点：保存选择并加载该节点的目录
    onNodeChange(nodeId) {
      this.nodeId = String(nodeId || "master").trim() || "master";
      try {
        localStorage.setItem("jarvis_autoworker_node", this.nodeId);
      } catch {
        /* 忽略 */
      }
      this.loadDirs();
    },
    // 节点展示名：优先宿主自定义名，否则回退 node_id
    nodeLabel(node) {
      if (!node) return "master";
      return (node.display_name || node.name || node.node_id || "master");
    },
    // 按节点 ID 取展示名（模板用，避免模板内写复杂表达式）
    nodeLabelById(nodeId) {
      const target = String(nodeId || "master").trim() || "master";
      const found = this.nodes.find((n) => n && n.node_id === target);
      return this.nodeLabel(found || { node_id: target });
    },
    // ---- 工作目录（按节点多目录）管理 ----
    // 恢复当前节点的目录列表与激活目录（含旧版单目录迁移）
    restoreWorkdir() {
      this.loadDirs();
    },
    // 从 localStorage 加载当前节点目录列表与激活目录
    loadDirs() {
      // 旧版单目录迁移：仅 master 节点且从未初始化过新结构时迁移
      let dirs = [];
      try {
        const raw = localStorage.getItem(dirsKey(this.nodeId));
        if (raw) {
          const parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) {
            dirs = parsed
              .filter((d) => typeof d === "string" && d.trim())
              .slice(0, DIRS_HISTORY_MAX);
          }
        }
      } catch {
        dirs = [];
      }
      // 旧版单目录迁移（仅当 master 且新结构为空时）
      if (this.nodeId === "master" && dirs.length === 0) {
        try {
          const legacy = (localStorage.getItem(LEGACY_WORKDIR_KEY) || "").trim();
          if (legacy) {
            dirs = [legacy];
            localStorage.setItem(dirsKey("master"), JSON.stringify(dirs));
            localStorage.removeItem(LEGACY_WORKDIR_KEY);
          }
        } catch {
          /* 忽略 */
        }
      }
      this.dirs = dirs;
      // 激活目录：优先存过的，否则取列表第一个
      let active = "";
      try {
        active = (localStorage.getItem(activeDirKey(this.nodeId)) || "").trim();
      } catch {
        active = "";
      }
      if (!active || !dirs.includes(active)) {
        active = dirs[0] || "";
      }
      this.workdir = active;
      this.dirInput = "";
      this.selected = null;
      this.refresh();
    },
    // 添加一个工作目录到当前节点：去重置顶（已存在则移到最前）、截断到历史上限
    addDir() {
      const value = (this.dirInput || "").trim();
      if (!value) {
        this.error = "请填写后端工作目录";
        return;
      }
      this.error = "";
      this.dirs = [value, ...this.dirs.filter((d) => d !== value)].slice(
        0,
        DIRS_HISTORY_MAX,
      );
      this.saveDirs();
      this.dirInput = "";
      // 首次添加时自动激活
      if (!this.workdir) {
        this.workdir = value;
        this.saveActiveDir();
        this.selected = null;
        this.refresh();
      }
    },
    // 切换当前激活的工作目录（同时把该目录移到历史最前）
    useDir(dir) {
      if (!dir || !this.dirs.includes(dir)) return;
      this.workdir = dir;
      this.dirs = [dir, ...this.dirs.filter((d) => d !== dir)].slice(
        0,
        DIRS_HISTORY_MAX,
      );
      this.saveDirs();
      this.saveActiveDir();
      this.selected = null;
      this.refresh();
    },
    // 从当前节点移除一个工作目录
    removeDir(dir) {
      if (!dir) return;
      this.dirs = this.dirs.filter((d) => d !== dir);
      this.saveDirs();
      if (this.workdir === dir) {
        this.workdir = this.dirs[0] || "";
        this.saveActiveDir();
        this.selected = null;
        this.refresh();
      }
    },
    saveDirs() {
      try {
        localStorage.setItem(dirsKey(this.nodeId), JSON.stringify(this.dirs));
      } catch {
        /* 忽略存储失败 */
      }
    },
    saveActiveDir() {
      try {
        if (this.workdir) {
          localStorage.setItem(activeDirKey(this.nodeId), this.workdir);
        } else {
          localStorage.removeItem(activeDirKey(this.nodeId));
        }
      } catch {
        /* 忽略存储失败 */
      }
    },
    toggleWorkdirEdit() {
      this.workdirEditing = !this.workdirEditing;
    },
    // 用宿主提供的目录选择弹窗挑选工作目录（含节点）
    async pickWorkdir() {
      const pick =
        typeof window !== "undefined" && window.__jarvisPickDirectoryWithNode;
      if (typeof pick !== "function") {
        this.error = "宿主未提供目录选择通道";
        return;
      }
      try {
        const res = await pick();
        if (res && res.path) {
          // 选择的节点可能不同于当前节点：同步切换节点
          if (res.nodeId && res.nodeId !== this.nodeId) {
            this.nodeId = res.nodeId;
            try {
              localStorage.setItem("jarvis_autoworker_node", this.nodeId);
            } catch {
              /* 忽略 */
            }
            this.loadDirs();
          }
          this.dirInput = res.path;
        }
      } catch (e) {
        this.error = String((e && e.message) || e);
      }
    },
    // ---- Agent 信息 ----
    refreshAgentName() {
      const getInfo =
        typeof window !== "undefined" && window.__jarvisGetActiveAgentInfo;
      if (typeof getInfo !== "function") {
        this.agentName = "";
        return;
      }
      try {
        const info = getInfo() || {};
        this.agentName = (info && info.agentName) || "";
      } catch {
        this.agentName = "";
      }
    },
    // ---- 任务列表 ----
    async refresh(silent) {
      if (!this.workdir) {
        this.tasks = [];
        return;
      }
      if (!silent) {
        this.loading = true;
        this.error = "";
        this.message = "";
      }
      try {
        const payload = await callFunction("list_tasks", {
          workdir: this.workdir,
        }, this.nodeId);
        this.tasks = Array.isArray(payload.data) ? payload.data : [];
        // 同步刷新当前选中任务的详情（若仍在列表）
        if (this.selected) {
          const found = this.tasks.find((t) => t.id === this.selected.id);
          if (found) this.selected = found;
        }
      } catch (e) {
        if (!silent) this.error = String((e && e.message) || e);
      } finally {
        if (!silent) this.loading = false;
      }
    },
    fmtDate(s) {
      if (!s) return "";
      try {
        return new Date(s).toLocaleString();
      } catch {
        return s;
      }
    },
    tagsText(tags) {
      return Array.isArray(tags) ? tags.join(", ") : "";
    },
    // ---- 详情 / 编辑 ----
    openTask(task) {
      this.selected = task;
      this.editForm = {
        title: task.title || "",
        description: task.description || "",
        tags: this.tagsText(task.tags),
        due_date: task.due_date || todayStr(),
      };
      this.message = "";
      this.error = "";
    },
    back() {
      this.selected = null;
    },
    async saveTask() {
      if (!this.selected) return;
      if (!this.editForm.title.trim()) {
        this.error = "标题不能为空";
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = "";
      try {
        await callFunction("update_task", {
          workdir: this.workdir,
          task_id: this.selected.id,
          title: this.editForm.title.trim(),
          description: this.editForm.description,
          tags: this.editForm.tags,
          due_date: this.editForm.due_date,
        }, this.nodeId);
        this.message = "已保存";
        await this.refresh(true);
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 新建任务 ----
    toggleCreate() {
      this.creating = !this.creating;
      if (this.creating) {
        this.createForm = { title: "", description: "", tags: "", due_date: todayStr() };
        this.error = "";
      }
    },
    async createTask() {
      if (!this.createForm.title.trim()) {
        this.error = "标题不能为空";
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = "";
      try {
        const payload = await callFunction("create_task", {
          workdir: this.workdir,
          title: this.createForm.title.trim(),
          description: this.createForm.description,
          tags: this.createForm.tags,
          due_date: this.createForm.due_date,
        }, this.nodeId);
        const created = payload.data || {};
        this.message = `已创建任务 ${created.id || ""}`;
        this.creating = false;
        await this.refresh(true);
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 状态标记（手动兜底）----
    async markStatus(task, status) {
      this.closeItemMenu();
      if (!task) return;
      this.busy = true;
      this.error = "";
      this.message = "";
      try {
        await callFunction("set_status", {
          workdir: this.workdir,
          task_id: task.id,
          status: status,
        }, this.nodeId);
        this.message = `任务 ${task.id} 已标记为${STATUS_LABELS[status] || status}`;
        await this.refresh(true);
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 软删除 ----
    async deleteTask(task) {
      this.closeItemMenu();
      if (!task) return;
      if (!window.confirm(`确定删除任务 ${task.id}「${task.title || ""}」？\n数据将保留（软删除），可从列表移除。`)) {
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = "";
      try {
        await callFunction("delete_task", {
          workdir: this.workdir,
          task_id: task.id,
        }, this.nodeId);
        this.message = `任务 ${task.id} 已删除`;
        // 若删除的是当前详情页任务，返回列表
        if (this.selected && this.selected.id === task.id) {
          this.selected = null;
        }
        await this.refresh(true);
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 手动添加关键信息（note）----
    async addNote(task) {
      this.closeItemMenu();
      if (!task) return;
      const content = (this.noteInput || "").trim();
      if (!content) {
        this.error = "请填写关键信息内容";
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = "";
      try {
        await callFunction("add_note", {
          workdir: this.workdir,
          task_id: task.id,
          content: content,
        }, this.nodeId);
        this.message = `已为任务 ${task.id} 保存关键信息`;
        this.noteInput = "";
        await this.refresh(true);
      } catch (e) {
        this.error = String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // ---- 复制文本（关键信息等）----
    async copyText(text, label) {
      if (!text) return;
      const done = () => {
        this.message = `${label || "内容"}已复制`;
        setTimeout(() => {
          if (this.message === `${label || "内容"}已复制`) this.message = "";
        }, 2000);
      };
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          done();
          return;
        }
        // 降级：textarea + execCommand
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (ok) {
          done();
        } else {
          this.error = "复制失败，请手动选中复制";
        }
      } catch (e) {
        this.error = String((e && e.message) || e);
      }
    },
    // ---- 右键菜单 ----
    openItemMenu(task, event) {
      this.menuItem = task;
      const menuWidth = 160;
      const menuHeight = 150;
      let left = event.clientX;
      let top = event.clientY;
      if (left + menuWidth > window.innerWidth - 8) {
        left = window.innerWidth - menuWidth - 8;
      }
      if (left < 8) left = 8;
      if (top + menuHeight > window.innerHeight - 8) {
        top = window.innerHeight - menuHeight - 8;
      }
      if (top < 8) top = 8;
      this.menuStyle = { left: left + "px", top: top + "px" };
      this.menuVisible = true;
    },
    closeItemMenu() {
      this.menuVisible = false;
      this.menuItem = null;
    },
    // 生成执行该任务的提示词
    buildTaskPrompt(task) {
      const lines = [
        `请执行任务 ${task.id}：${task.title || ""}`,
      ];
      if (task.description) {
        lines.push("", "任务描述：", task.description);
      }
      if (Array.isArray(task.tags) && task.tags.length) {
        lines.push("", `标签：${task.tags.join(", ")}`);
      }
      if (task.due_date) {
        lines.push(`截止时间：${task.due_date}`);
      }
      lines.push(
        "",
        "说明：",
        "- 你当前的工作目录即为本任务目录。",
        "- 可使用 task_manager 工具查看/更新本任务、保存关键信息（add_note）。",
        "- 完成后请用 task_manager 把本任务状态标记为 completed。",
      );
      return lines.join("\n");
    },
    // 创建 Agent 执行该任务（Agent working_dir = 任务子目录）
    async createAgentForTask(task) {
      this.closeItemMenu();
      if (!task) return;
      // 优先使用「打开创建 Agent 弹窗（带预填）」通道，让用户确认/编辑后再创建；
      // 宿主未提供新通道时回退到直接创建通道（向后兼容）。
      const openModal =
        typeof window !== "undefined" && window.__jarvisOpenCreateAgentModal;
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof openModal !== "function" && typeof create !== "function") {
        this.error = "宿主未提供创建通道，无法创建 Agent";
        return;
      }
      const taskDir = (task.task_dir || "").trim();
      if (!taskDir) {
        this.error = "任务目录未知，请先刷新";
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = `正在为任务 ${task.id} 创建 Agent…`;
      try {
        const prefill = {
          workingDir: taskDir,
          task: this.buildTaskPrompt(task),
          name: `${task.id} ${task.title || ""}`.trim(),
          nodeId: this.nodeId,
        };
        let created = false;
        if (typeof openModal === "function") {
          const res = await openModal(prefill);
          created = !!(res && res.confirmed);
          if (!created) {
            this.message = "已取消";
            return;
          }
        } else {
          const res = await create(prefill);
          created = !!(res && res.success);
          if (!created) {
            this.error = "失败: " + ((res && res.error) || "创建失败");
            return;
          }
        }
        if (created) {
          // 标记为执行中
          try {
            await callFunction("set_status", {
              workdir: this.workdir,
              task_id: task.id,
              status: "running",
            }, this.nodeId);
          } catch {
            /* 标记失败不阻塞创建结果提示 */
          }
          this.message = `已创建 Agent 执行任务 ${task.id}`;
          await this.refresh(true);
        }
      } catch (e) {
        this.error = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // 在工作目录下创建 Agent（Agent working_dir = 插件工作目录，而非任务子目录）。
    // 不写入任务提示词、只创建不运行：创建空闲 Agent，运行留给用户自行触发。
    async createAgentInWorkdir(task) {
      this.closeItemMenu();
      // 优先使用「打开创建 Agent 弹窗（带预填）」通道，让用户确认/编辑后再创建；
      // 宿主未提供新通道时回退到直接创建通道（向后兼容）。
      const openModal =
        typeof window !== "undefined" && window.__jarvisOpenCreateAgentModal;
      const create =
        typeof window !== "undefined" && window.__jarvisCreateAgentForTask;
      if (typeof openModal !== "function" && typeof create !== "function") {
        this.error = "宿主未提供创建通道，无法创建 Agent";
        return;
      }
      const workdir = (this.workdir || "").trim();
      if (!workdir) {
        this.error = "工作目录未设置，请先配置";
        return;
      }
      this.busy = true;
      this.error = "";
      this.message = "正在在工作目录下创建 Agent…";
      try {
        const prefill = {
          workingDir: workdir,
          task: "",
          name: task ? `${task.id} ${task.title || ""}`.trim() : "",
          nodeId: this.nodeId,
        };
        if (typeof openModal === "function") {
          const res = await openModal(prefill);
          if (res && res.confirmed) {
            this.message = "已在工作目录下创建 Agent（未运行，请自行触发）";
          } else {
            this.message = "已取消";
          }
        } else {
          const res = await create({ ...prefill, runTask: false });
          if (res && res.success) {
            this.message = "已在工作目录下创建 Agent（未运行，请自行触发）";
          } else {
            this.error = "失败: " + ((res && res.error) || "创建失败");
          }
        }
      } catch (e) {
        this.error = "失败: " + String((e && e.message) || e);
      } finally {
        this.busy = false;
      }
    },
    // 把任务交给当前活跃 Agent（发送提示词）
    async handleInCurrentAgent(task) {
      this.closeItemMenu();
      if (!task) return;
      const send =
        typeof window !== "undefined" && window.__jarvisSendToActiveAgent;
      if (typeof send !== "function") {
        this.error = "宿主未提供发送通道";
        return;
      }
      const res = send(this.buildTaskPrompt(task));
      if (res && res.success) {
        this.message = `已把任务 ${task.id} 的提示词发送给当前 Agent`;
      } else {
        this.error = "失败: " + ((res && res.error) || "发送失败");
      }
    },
    statusBtnStyle(status) {
      return {
        color: STATUS_COLORS[status] || "#ddd",
        border: `1px solid ${STATUS_COLORS[status] || "#444"}`,
      };
    },
  },
  template: `
  <div style="padding:12px;font-size:13px;color:#ddd;overflow:auto;height:100%;box-sizing:border-box;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
      <strong style="font-size:14px;">任务</strong>
      <div style="display:flex;align-items:center;gap:6px;">
        <button @click="toggleWorkdirEdit" title="设置节点与工作目录"
          style="padding:2px 6px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">设置</button>
        <button @click="refresh()" title="刷新"
          style="padding:2px 6px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">🔄</button>
      </div>
    </div>

    <!-- 节点选择 -->
    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
      <span style="font-size:11px;color:#888;white-space:nowrap;">节点:</span>
      <select v-model="nodeId" @change="onNodeChange(nodeId)"
        style="flex:1;min-width:0;padding:3px 6px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <option v-for="n in nodes" :key="n.node_id" :value="n.node_id">{{ nodeLabel(n) }}</option>
      </select>
    </div>

    <div style="font-size:11px;color:#888;margin-bottom:4px;" :title="workdir || ''">
      工作目录: {{ workdir || '未设置' }}
    </div>
    <div style="font-size:11px;color:#58a6ff;margin-bottom:10px;">
      当前 Agent: <span :title="agentName || ''">{{ agentName || '未选择 Agent' }}</span>
    </div>

    <!-- 设置区：节点下的工作目录管理 -->
    <div v-if="workdirEditing" style="margin-bottom:10px;padding:8px;background:#252526;border-radius:6px;">
      <div style="font-size:11px;color:#888;margin-bottom:4px;">
        节点 {{ nodeLabelById(nodeId) }} 的工作目录（任务子目录的父目录）
      </div>
      <!-- 已有目录列表：最近使用历史（最多 10 条，最近使用在前） -->
      <div v-if="dirs.length" style="margin-bottom:6px;">
        <div v-for="d in dirs" :key="d"
          style="display:flex;align-items:center;gap:6px;padding:3px 6px;margin-bottom:3px;background:#1e1e1e;border-radius:4px;">
          <span style="flex:1;min-width:0;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            :style="d === workdir ? { color: '#58a6ff' } : { color: '#ddd' }" :title="d">{{ d }}</span>
          <button @click="useDir(d)" :disabled="d === workdir"
            style="padding:2px 6px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:11px;">使用</button>
          <button @click="removeDir(d)"
            style="padding:2px 6px;background:#333;color:#f85149;border:none;border-radius:4px;cursor:pointer;font-size:11px;">删除</button>
        </div>
      </div>
      <div v-else style="font-size:11px;color:#888;margin-bottom:6px;">该节点暂无工作目录，请添加。</div>
      <!-- 添加目录 -->
      <div style="display:flex;gap:6px;">
        <input v-model="dirInput" type="text" placeholder="如 /home/user/tasks"
          @keydown.enter.prevent="addDir"
          style="flex:1;min-width:0;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <button @click="pickWorkdir" title="用目录选择弹窗挑选"
          style="padding:5px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:12px;">选择</button>
      </div>
      <div style="display:flex;gap:6px;margin-top:6px;">
        <button @click="addDir" style="padding:4px 10px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">添加</button>
        <button @click="workdirEditing = false" style="padding:4px 8px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:11px;">完成</button>
      </div>
    </div>

    <!-- 消息 -->
    <div v-if="message" style="margin-bottom:8px;padding:6px;background:#1f6feb33;border-radius:4px;font-size:12px;">{{ message }}</div>
    <div v-if="error" style="margin-bottom:8px;padding:6px;background:#f8514933;border-radius:4px;font-size:12px;color:#f85149;">{{ error }}</div>

    <!-- 未设置工作目录 -->
    <div v-if="!workdir" style="color:#888;padding:20px;text-align:center;">
      请先点击右上角「设置」配置当前节点的工作目录。
    </div>

    <!-- 列表视图 -->
    <div v-else-if="!selected">
      <div style="display:flex;gap:6px;margin-bottom:10px;">
        <button @click="toggleCreate"
          style="padding:4px 10px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">+ 新建任务</button>
      </div>

      <!-- 新建表单 -->
      <div v-if="creating" style="margin-bottom:10px;padding:8px;background:#252526;border-radius:6px;">
        <input v-model="createForm.title" type="text" placeholder="标题（必填）"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <textarea v-model="createForm.description" rows="2" placeholder="描述"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;"></textarea>
        <input v-model="createForm.tags" type="text" placeholder="标签（逗号分隔）"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <input v-model="createForm.due_date" type="date" placeholder="截止日期"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <div style="display:flex;gap:6px;">
          <button @click="createTask" :disabled="busy"
            style="padding:5px 12px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">创建</button>
          <button @click="creating = false"
            style="padding:5px 10px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:12px;">取消</button>
        </div>
      </div>

      <div v-if="loading" style="color:#888;padding:20px;text-align:center;">加载中…</div>
      <div v-else-if="tasks.length === 0" style="color:#888;padding:20px;text-align:center;">暂无任务</div>

      <div v-for="g in groupedTasks" :key="g.status" style="margin-bottom:12px;">
        <div :style="{color:g.color,fontSize:'11px',fontWeight:'600',marginBottom:'4px'}">
          {{ g.label }} ({{ g.items.length }})
        </div>
        <div v-for="t in g.items" :key="t.id"
          @click="openTask(t)" @contextmenu.prevent="openItemMenu(t, $event)"
          style="padding:8px;margin-bottom:6px;background:#252526;border-radius:6px;cursor:pointer;border-left:3px solid #58a6ff;">
          <div style="display:flex;justify-content:space-between;">
            <span style="color:#888;">{{ t.id }}</span>
            <span :style="{color: STATUS_COLORS[t.status] || '#888', fontSize:'11px'}">{{ STATUS_LABELS[t.status] || t.status }}</span>
          </div>
          <div style="margin-top:2px;font-weight:600;">{{ t.title }}</div>
          <div v-if="tagsText(t.tags)" style="font-size:11px;color:#888;margin-top:2px;">{{ tagsText(t.tags) }}</div>
          <div v-if="t.due_date" style="font-size:11px;color:#d29922;margin-top:2px;">截止 {{ t.due_date }}</div>
        </div>
      </div>
    </div>

    <!-- 详情视图 -->
    <div v-else>
      <button @click="back()" style="margin-bottom:8px;padding:4px 10px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;">← 返回</button>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0;font-size:14px;">{{ selected.id }}</h3>
        <span :style="{color: STATUS_COLORS[selected.status] || '#888', fontSize:'12px'}">{{ STATUS_LABELS[selected.status] || selected.status }}</span>
      </div>
      <div style="font-size:11px;color:#888;margin:4px 0;">创建 {{ fmtDate(selected.created_at) }} · 更新 {{ fmtDate(selected.updated_at) }}</div>

      <!-- 编辑表单 -->
      <div style="margin:8px 0;">
        <input v-model="editForm.title" type="text" placeholder="标题（必填）"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <textarea v-model="editForm.description" rows="4" placeholder="描述"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;"></textarea>
        <input v-model="editForm.tags" type="text" placeholder="标签（逗号分隔）"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <input v-model="editForm.due_date" type="date" placeholder="截止日期"
          style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:5px 8px;background:#1e1e1e;color:#ddd;border:1px solid #444;border-radius:4px;font-size:12px;">
        <button @click="saveTask" :disabled="busy"
          style="padding:5px 12px;background:#1f6feb;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">保存</button>
      </div>

      <!-- 执行操作 -->
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
        <button @click="createAgentForTask(selected)" :disabled="busy"
          style="padding:5px 10px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">创建 Agent 执行</button>
        <button @click="handleInCurrentAgent(selected)"
          style="padding:5px 10px;background:#333;color:#ddd;border:none;border-radius:4px;cursor:pointer;font-size:12px;">交给当前 Agent</button>
      </div>

      <!-- 手动兜底标记 -->
      <div style="font-size:11px;color:#888;margin-bottom:4px;">标记状态</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <button v-for="s in ['pending','running','completed','abandoned']" :key="s"
          @click="markStatus(selected, s)" :disabled="busy"
          :style="statusBtnStyle(s)"
          style="padding:4px 8px;background:transparent;border-radius:4px;cursor:pointer;font-size:11px;">
          {{ STATUS_LABELS[s] }}
        </button>
      </div>

      <!-- 危险操作 -->
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;">
        <button @click="deleteTask(selected)" :disabled="busy"
          style="padding:4px 10px;background:transparent;color:#f85149;border:1px solid #f85149;border-radius:4px;cursor:pointer;font-size:11px;">删除任务</button>
      </div>

      <!-- notes -->
      <div style="font-size:12px;font-weight:600;margin:12px 0 6px;">关键信息 ({{ (selected.notes || []).length }})</div>
      <div style="display:flex;gap:6px;margin-bottom:8px;align-items:flex-start;">
        <textarea v-model="noteInput" @keydown.ctrl.enter="addNote(selected)" :disabled="busy"
          rows="3" placeholder="输入关键信息（支持多行，Ctrl+Enter 或点击添加）…"
          style="flex:1;min-width:0;background:#1e1e1e;border:1px solid #333;border-radius:4px;padding:5px 8px;color:#ddd;font-size:12px;outline:none;resize:vertical;line-height:1.5;"></textarea>
        <button @click="addNote(selected)" :disabled="busy || !(noteInput || '').trim()"
          style="padding:5px 10px;background:#238636;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;white-space:nowrap;">添加</button>
      </div>
      <div v-for="(n, i) in (selected.notes || [])" :key="i" style="background:#1e1e1e;padding:6px;border-radius:6px;margin-bottom:6px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;">
          <div style="font-size:11px;color:#888;">{{ fmtDate(n.time) }}</div>
          <button @click="copyText(n.content, '关键信息')"
            style="padding:1px 6px;background:transparent;color:#58a6ff;border:1px solid #58a6ff55;border-radius:3px;cursor:pointer;font-size:10px;white-space:nowrap;">复制</button>
        </div>
        <div style="white-space:pre-wrap;font-size:12px;margin-top:2px;user-select:text;-webkit-user-select:text;">{{ n.content }}</div>
      </div>
      <div v-if="!(selected.notes || []).length" style="font-size:11px;color:#888;">暂无</div>

      <div style="font-size:11px;color:#888;margin-top:10px;word-break:break-all;">
        任务目录: {{ selected.task_dir }}
      </div>
    </div>

    <!-- 列表项右键菜单 -->
    <div v-if="menuVisible" :style="menuStyle"
      style="position:fixed;z-index:9999;background:#2d2d30;border:1px solid #454545;border-radius:6px;box-shadow:0 4px 12px #0008;padding:4px;min-width:140px;">
      <div @click="createAgentForTask(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">创建 Agent 执行该任务</div>
      <div @click="createAgentInWorkdir(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">在工作目录下创建 Agent</div>
      <div @click="handleInCurrentAgent(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#ddd;cursor:pointer;border-radius:4px;white-space:nowrap;">交给当前 Agent{{ agentName ? '（' + agentName + '）' : '' }}</div>
      <div @click="markStatus(menuItem, 'completed')"
        style="padding:6px 10px;font-size:12px;color:#3fb950;cursor:pointer;border-radius:4px;white-space:nowrap;">标记完成</div>
      <div @click="markStatus(menuItem, 'abandoned')"
        style="padding:6px 10px;font-size:12px;color:#f85149;cursor:pointer;border-radius:4px;white-space:nowrap;">标记放弃</div>
      <div @click="deleteTask(menuItem)"
        style="padding:6px 10px;font-size:12px;color:#f85149;cursor:pointer;border-radius:4px;white-space:nowrap;">删除任务</div>
    </div>
  </div>
  `,
};
