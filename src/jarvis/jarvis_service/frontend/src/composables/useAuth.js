import { ref } from "vue";

/**
 * 认证相关逻辑 Composable
 * 包含登录、Token管理、认证检查等功能
 */
export function useAuth() {
  // 认证状态
  const auth = ref({
    password: "",
    token: "",
  });

  // 免登录开关
  const autoLoginEnabled = ref(
    localStorage.getItem("jarvis_auto_login") === "true",
  );

  /**
   * 使用密码登录获取Token
   * @param {string} password - 登录密码
   * @returns {Promise<boolean>} - 登录是否成功
   */
  async function loginWithPassword(password) {
    try {
      // 这里需要调用实际的API，暂时使用模拟实现
      // 实际实现需要从App.vue中导入getGatewayAddress和getHttpProtocol
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      const result = await response.json();
      if (!response.ok || !result.success || !result.data?.token) {
        throw new Error(result.error?.message || "登录失败");
      }

      // 保存Token
      auth.value.token = result.data.token;

      // 如果免登录开启，将Token保存到localStorage
      if (autoLoginEnabled.value) {
        localStorage.setItem("jarvis_auth_token", result.data.token);
        console.log("[AUTH] Token saved to localStorage (auto login enabled)");
      }

      // 登录成功后清除密码
      auth.value.password = "";
      console.log("[AUTH] Login successful, token saved, password cleared");
      return true;
    } catch (error) {
      console.error("[AUTH] Login failed:", error);
      throw error;
    }
  }

  /**
   * 检查是否有认证Token
   * @returns {boolean} - 是否有Token
   */
  function hasAuthToken() {
    return Boolean(auth.value.token);
  }

  /**
   * 获取当前有效的Token
   * @returns {string|null} - Token或null
   */
  function getAuthToken() {
    // 优先返回内存中的Token
    if (auth.value.token) {
      return auth.value.token;
    }
    // 其次尝试从localStorage获取
    const savedToken = localStorage.getItem("jarvis_auth_token");
    if (savedToken) {
      auth.value.token = savedToken;
      return savedToken;
    }
    return null;
  }

  /**
   * 从localStorage加载已保存的Token
   * @returns {boolean} - 是否成功加载Token
   */
  function loadSavedToken() {
    const savedToken = localStorage.getItem("jarvis_auth_token");
    if (savedToken) {
      auth.value.token = savedToken;
      console.log("[AUTH] Loaded saved token from localStorage");
      return true;
    }
    return false;
  }

  /**
   * 带认证的fetch函数
   * @param {string} url - 请求URL
   * @param {object} options - fetch选项
   * @returns {Promise<Response>} - fetch响应
   */
  async function fetchWithAuth(url, options = {}) {
    if (!hasAuthToken()) {
      throw new Error("尚未登录，已阻止向后端发送请求");
    }

    // 复制options避免修改原始对象
    const fetchOptions = {
      ...options,
      headers: {
        ...options.headers,
        "Content-Type":
          "Content-Type" in (options.headers || {})
            ? options.headers["Content-Type"]
            : "application/json",
      },
    };

    // 如果有Token，添加到Authorization Header
    if (auth.value.token) {
      fetchOptions.headers["Authorization"] = `Bearer ${auth.value.token}`;
    }

    const response = await fetch(url, fetchOptions);

    // 检查401未授权错误
    if (response.status === 401) {
      console.log("[AUTH] Received 401 Unauthorized, showing login modal");
      auth.value.token = "";
      // 这里需要触发显示登录模态框，暂时只清除Token
    }

    return response;
  }

  /**
   * 保存免登录设置
   */
  function saveAutoLoginSetting() {
    localStorage.setItem("jarvis_auto_login", autoLoginEnabled.value);
    console.log("[SETTINGS] Auto login setting saved:", autoLoginEnabled.value);
    // 如果关闭免登录，清除已保存的token
    if (!autoLoginEnabled.value) {
      localStorage.removeItem("jarvis_auth_token");
      console.log("[SETTINGS] Saved token cleared (auto login disabled)");
    }
  }

  /**
   * 构建WebSocket协议列表（包含Token）
   * @returns {string[]} - 协议列表
   */
  function buildWebSocketProtocols() {
    const token = String(auth.value?.token || "").trim();
    if (!token) {
      return ["jarvis-ws"];
    }
    return ["jarvis-ws", `jarvis-token.${encodeURIComponent(token)}`];
  }

  return {
    // 状态
    auth,
    autoLoginEnabled,

    // 方法
    loginWithPassword,
    hasAuthToken,
    getAuthToken,
    loadSavedToken,
    fetchWithAuth,
    saveAutoLoginSetting,
    buildWebSocketProtocols,
  };
}
