/**
 * 对话历史存储工具模块
 * 使用 localStorage 存储对话历史，支持分页加载、删除和管理
 */

const STORAGE_KEY = "jarvis_chat_history";
const METADATA_KEY = "jarvis_chat_metadata";
const MAX_MESSAGES_PER_PAGE = 50;
const MAX_TOTAL_MESSAGES = 1000;
// 存储体积上限阈值（3MB）：超出后 pruneHistory 会按时间删除最旧消息，
// 避免撑爆移动端 ~5MB 的 localStorage 配额导致 setItem 抛 QuotaExceededError。
const MAX_STORAGE_SIZE_BYTES = 3 * 1024 * 1024;

/**
 * 生成唯一ID
 */
function generateId() {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * 获取所有历史消息
 */
function getAllMessages() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return [];
    return JSON.parse(data);
  } catch (error) {
    console.error("[historyStorage] Failed to load messages:", error);
    return [];
  }
}

/**
 * 保存所有消息到存储
 */
function saveAllMessages(messages) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to save messages:", error);
    return false;
  }
}

/**
 * 保存单条消息
 * @param {Object} message - 消息对象
 * @returns {boolean} - 是否保存成功
 */
function saveMessage(message) {
  try {
    const messages = getAllMessages();

    // 检查是否已存在相同ID的消息
    const existingIndex = messages.findIndex((m) => m.id === message.id);
    if (existingIndex >= 0) {
      // 更新现有消息
      messages[existingIndex] = message;
    } else {
      // 添加新消息到末尾
      message.id = message.id || generateId();
      message.storageTimestamp = Date.now();
      messages.push(message);
    }

    // 限制总消息数量
    if (messages.length > MAX_TOTAL_MESSAGES) {
      const removeCount = messages.length - MAX_TOTAL_MESSAGES;
      messages.splice(0, removeCount);
    }

    saveAllMessages(messages);
    pruneHistory({ removeOrphans: false });
    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to save message:", error);
    return false;
  }
}

/**
 * 批量保存消息
 * @param {Array} messages - 消息数组
 * @returns {boolean} - 是否保存成功
 */
function saveMessages(messages) {
  try {
    const allMessages = getAllMessages();
    const existingIds = new Set(allMessages.map((m) => m.id));

    messages.forEach((msg) => {
      if (!msg.id) {
        msg.id = generateId();
        msg.storageTimestamp = Date.now();
      }
      if (!existingIds.has(msg.id)) {
        allMessages.push(msg);
      }
    });

    // 限制总消息数量
    if (allMessages.length > MAX_TOTAL_MESSAGES) {
      const removeCount = allMessages.length - MAX_TOTAL_MESSAGES;
      allMessages.splice(0, removeCount);
    }

    saveAllMessages(allMessages);
    pruneHistory({ removeOrphans: false });
    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to save messages:", error);
    return false;
  }
}

/**
 * 读取历史消息（分页）
 * @param {number} count - 要读取的消息数量
 * @param {number} offset - 偏移量（从末尾往前算）
 * @param {string} agentId - 可选，只返回指定 Agent ID 的消息
 * @returns {Array} - 消息数组（按时间倒序）
 */
function loadHistory(
  count = MAX_MESSAGES_PER_PAGE,
  offset = 0,
  agentId = null,
) {
  try {
    let messages = getAllMessages();
    if (messages.length === 0) return [];

    // 如果指定了 agentId，只返回该 Agent 的消息
    if (agentId) {
      messages = messages.filter((msg) => msg.agent_id === agentId);
    }

    // 从末尾往前取，跳过 offset 条，取 count 条
    const start = Math.max(0, messages.length - offset - count);
    const end = messages.length - offset;
    const result = messages.slice(start, end);

    return result;
  } catch (error) {
    console.error("[historyStorage] Failed to load history:", error);
    return [];
  }
}

/**
 * 获取历史消息总数
 * @param {string} agentId - 可选，只返回指定 Agent ID 的消息数量
 * @returns {number} - 消息总数
 */
function getTotalCount(agentId = null) {
  try {
    let messages = getAllMessages();

    // 如果指定了 agentId，只计算该 Agent 的消息
    if (agentId) {
      messages = messages.filter((msg) => msg.agent_id === agentId);
    }

    return messages.length;
  } catch (error) {
    console.error("[historyStorage] Failed to get count:", error);
    return 0;
  }
}

/**
 * 删除所有历史消息
 * @returns {boolean} - 是否删除成功
 */
function clearHistory() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(METADATA_KEY);
    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to clear history:", error);
    return false;
  }
}

/**
 * 清除指定 Agent 的历史记录
 * @param {string} agentId - Agent ID
 * @returns {boolean} - 是否清除成功
 */
function clearHistoryForAgent(agentId) {
  try {
    const allMessages = getAllMessages();
    const filteredMessages = allMessages.filter(
      (msg) => msg.agent_id !== agentId,
    );

    if (filteredMessages.length !== allMessages.length) {
      saveAllMessages(filteredMessages);
      return true;
    }

    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to clear agent history:", error);
    return false;
  }
}

/**
 * 获取历史元数据
 * @returns {Object} - 元数据对象
 */
function getMetadata() {
  try {
    const data = localStorage.getItem(METADATA_KEY);
    if (!data) {
      return {
        totalCount: 0,
        lastUpdated: null,
        storageSize: 0,
      };
    }
    return JSON.parse(data);
  } catch (error) {
    console.error("[historyStorage] Failed to load metadata:", error);
    return {
      totalCount: 0,
      lastUpdated: null,
      storageSize: 0,
    };
  }
}

/**
 * 更新历史元数据
 */
function updateMetadata() {
  try {
    const messages = getAllMessages();
    const metadata = {
      totalCount: messages.length,
      lastUpdated: Date.now(),
      storageSize: JSON.stringify(messages).length,
    };
    localStorage.setItem(METADATA_KEY, JSON.stringify(metadata));
    return metadata;
  } catch (error) {
    console.error("[historyStorage] Failed to update metadata:", error);
    return null;
  }
}

/**
 * 获取指定 Agent 的历史记录
 * @param {string} agentId - Agent ID
 * @returns {Array} - 该 Agent 的消息数组
 */
function getHistoryForAgent(agentId) {
  try {
    const allMessages = getAllMessages();
    const agentMessages = allMessages.filter((msg) => msg.agent_id === agentId);
    return agentMessages;
  } catch (error) {
    console.error("[historyStorage] Failed to get agent history:", error);
    return [];
  }
}

/**
 * 设置指定 Agent 的历史记录
 * @param {string} agentId - Agent ID
 * @param {Array} data - 消息数组
 * @returns {boolean} - 是否设置成功
 */
function setHistoryForAgent(agentId, data) {
  try {
    const allMessages = getAllMessages();
    // 移除该 Agent 的旧消息
    const otherMessages = allMessages.filter((msg) => msg.agent_id !== agentId);
    // 添加新消息
    const newMessages = data.map((msg) => ({
      ...msg,
      agent_id: agentId,
      id: msg.id || generateId(),
      storageTimestamp: msg.storageTimestamp || Date.now(),
    }));
    const combined = [...otherMessages, ...newMessages];
    saveAllMessages(combined);
    pruneHistory({ removeOrphans: false });
    return true;
  } catch (error) {
    console.error("[historyStorage] Failed to set agent history:", error);
    return false;
  }
}

/**
 * 获取存储使用情况
 * @returns {Object} - 存储信息
 */
function getStorageInfo() {
  try {
    const messages = getAllMessages();
    const totalSize = JSON.stringify(messages).length;
    const metadata = getMetadata();

    return {
      totalCount: messages.length,
      totalSize: totalSize,
      totalSizeFormatted: formatBytes(totalSize),
      lastUpdated: metadata.lastUpdated
        ? new Date(metadata.lastUpdated).toLocaleString()
        : "从未",
      maxMessages: MAX_TOTAL_MESSAGES,
      maxStorageSize: MAX_STORAGE_SIZE_BYTES,
    };
  } catch (error) {
    console.error("[historyStorage] Failed to get storage info:", error);
    return {
      totalCount: 0,
      totalSize: 0,
      totalSizeFormatted: "0 B",
      lastUpdated: "未知",
      maxMessages: MAX_TOTAL_MESSAGES,
      maxStorageSize: MAX_STORAGE_SIZE_BYTES,
    };
  }
}

/**
 * 定期清理历史消息：
 * 1. 若 removeOrphans 为 true，先移除 agent_id 缺失的孤儿消息
 *    （删除 Agent 后残留、无法归属的消息）；
 * 2. 若存储体积仍超过 MAX_STORAGE_SIZE_BYTES，则按 storageTimestamp 升序
 *    删除最旧消息，直到体积回落到阈值以内。
 * 写入路径（saveMessage/saveMessages/setHistoryForAgent）自动触发时只做
 * 体积清理（removeOrphans=false），避免误删无 agent_id 的合法消息；
 * 删除/重生 Agent 后显式调用（removeOrphans=true）才清理孤儿。
 * @param {Object} [options] - { removeOrphans: boolean }
 * @returns {Object} 清理统计：{ removedOrphans, removedBySize, totalRemoved, remainingCount, remainingSize }
 */
function pruneHistory(options = {}) {
  const { removeOrphans = true } = options;
  try {
    const allMessages = getAllMessages();
    if (allMessages.length === 0) {
      return {
        removedOrphans: 0,
        removedBySize: 0,
        totalRemoved: 0,
        remainingCount: 0,
        remainingSize: JSON.stringify([]).length,
      };
    }

    // 1. 清理孤儿消息（无 agent_id），仅显式调用时执行
    let messages = allMessages;
    let removedOrphans = 0;
    if (removeOrphans) {
      messages = allMessages.filter(
        (msg) => msg.agent_id != null && msg.agent_id !== "",
      );
      removedOrphans = allMessages.length - messages.length;
    }

    // 2. 按体积阈值删除最旧消息
    let removedBySize = 0;
    let size = JSON.stringify(messages).length;
    while (messages.length > 0 && size > MAX_STORAGE_SIZE_BYTES) {
      // 取 storageTimestamp 最小（最旧）的消息删除；缺失时间戳视为最旧
      let oldestIndex = 0;
      for (let i = 1; i < messages.length; i++) {
        const a = messages[oldestIndex].storageTimestamp || 0;
        const b = messages[i].storageTimestamp || 0;
        if (b < a) oldestIndex = i;
      }
      messages.splice(oldestIndex, 1);
      removedBySize++;
      size = JSON.stringify(messages).length;
    }

    if (removedOrphans > 0 || removedBySize > 0) {
      saveAllMessages(messages);
    }

    return {
      removedOrphans,
      removedBySize,
      totalRemoved: removedOrphans + removedBySize,
      remainingCount: messages.length,
      remainingSize: size,
    };
  } catch (error) {
    console.error("[historyStorage] Failed to prune history:", error);
    return {
      removedOrphans: 0,
      removedBySize: 0,
      totalRemoved: 0,
      remainingCount: getAllMessages().length,
      remainingSize: JSON.stringify(getAllMessages()).length,
    };
  }
}

/**
 * 格式化字节数
 */
function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

// 导出所有方法
export default {
  saveMessage,
  saveMessages,
  loadHistory,
  getTotalCount,
  clearHistory,
  clearHistoryForAgent,
  getHistoryForAgent,
  setHistoryForAgent,
  getMetadata,
  updateMetadata,
  getStorageInfo,
  pruneHistory,
  MAX_MESSAGES_PER_PAGE,
  MAX_TOTAL_MESSAGES,
  MAX_STORAGE_SIZE_BYTES,
};
