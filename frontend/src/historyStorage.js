/**
 * 对话历史存储工具模块
 * 使用 localStorage 存储对话历史，支持分页加载、删除和管理
 */

const STORAGE_KEY = 'jarvis_chat_history'
const METADATA_KEY = 'jarvis_chat_metadata'
const MAX_MESSAGES_PER_PAGE = 50
const MAX_TOTAL_MESSAGES = 1000

/**
 * 生成唯一ID
 */
function generateId() {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

/**
 * 获取所有历史消息
 */
function getAllMessages() {
  try {
    const data = localStorage.getItem(STORAGE_KEY)
    if (!data) return []
    return JSON.parse(data)
  } catch (error) {
    console.error('[historyStorage] Failed to load messages:', error)
    return []
  }
}

/**
 * 保存所有消息到存储
 */
function saveAllMessages(messages) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
    return true
  } catch (error) {
    console.error('[historyStorage] Failed to save messages:', error)
    return false
  }
}

/**
 * 保存单条消息
 * @param {Object} message - 消息对象
 * @returns {boolean} - 是否保存成功
 */
function saveMessage(message) {
  try {
    const messages = getAllMessages()
    
    // 检查是否已存在相同ID的消息
    const existingIndex = messages.findIndex(m => m.id === message.id)
    if (existingIndex >= 0) {
      // 更新现有消息
      messages[existingIndex] = message
    } else {
      // 添加新消息到末尾
      message.id = message.id || generateId()
      message.storageTimestamp = Date.now()
      messages.push(message)
    }
    
    // 限制总消息数量
    if (messages.length > MAX_TOTAL_MESSAGES) {
      const removeCount = messages.length - MAX_TOTAL_MESSAGES
      messages.splice(0, removeCount)
      console.log(`[historyStorage] Removed ${removeCount} old messages to stay within limit`)
    }
    
    saveAllMessages(messages)
    return true
  } catch (error) {
    console.error('[historyStorage] Failed to save message:', error)
    return false
  }
}

/**
 * 批量保存消息
 * @param {Array} messages - 消息数组
 * @returns {boolean} - 是否保存成功
 */
function saveMessages(messages) {
  try {
    const allMessages = getAllMessages()
    const existingIds = new Set(allMessages.map(m => m.id))
    
    messages.forEach(msg => {
      if (!msg.id) {
        msg.id = generateId()
        msg.storageTimestamp = Date.now()
      }
      if (!existingIds.has(msg.id)) {
        allMessages.push(msg)
      }
    })
    
    // 限制总消息数量
    if (allMessages.length > MAX_TOTAL_MESSAGES) {
      const removeCount = allMessages.length - MAX_TOTAL_MESSAGES
      allMessages.splice(0, removeCount)
      console.log(`[historyStorage] Removed ${removeCount} old messages to stay within limit`)
    }
    
    saveAllMessages(allMessages)
    return true
  } catch (error) {
    console.error('[historyStorage] Failed to save messages:', error)
    return false
  }
}

/**
 * 读取历史消息（分页）
 * @param {number} count - 要读取的消息数量
 * @param {number} offset - 偏移量（从末尾往前算）
 * @returns {Array} - 消息数组（按时间倒序）
 */
function loadHistory(count = MAX_MESSAGES_PER_PAGE, offset = 0) {
  try {
    const messages = getAllMessages()
    if (messages.length === 0) return []
    
    // 从末尾往前取，跳过 offset 条，取 count 条
    const start = Math.max(0, messages.length - offset - count)
    const end = messages.length - offset
    const result = messages.slice(start, end)
    
    console.log(`[historyStorage] Loaded ${result.length} messages (offset: ${offset}, total: ${messages.length})`)
    return result
  } catch (error) {
    console.error('[historyStorage] Failed to load history:', error)
    return []
  }
}

/**
 * 获取历史消息总数
 * @returns {number} - 消息总数
 */
function getTotalCount() {
  try {
    const messages = getAllMessages()
    return messages.length
  } catch (error) {
    console.error('[historyStorage] Failed to get count:', error)
    return 0
  }
}

/**
 * 删除所有历史消息
 * @returns {boolean} - 是否删除成功
 */
function clearHistory() {
  try {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(METADATA_KEY)
    console.log('[historyStorage] History cleared')
    return true
  } catch (error) {
    console.error('[historyStorage] Failed to clear history:', error)
    return false
  }
}

/**
 * 获取历史元数据
 * @returns {Object} - 元数据对象
 */
function getMetadata() {
  try {
    const data = localStorage.getItem(METADATA_KEY)
    if (!data) {
      return {
        totalCount: 0,
        lastUpdated: null,
        storageSize: 0
      }
    }
    return JSON.parse(data)
  } catch (error) {
    console.error('[historyStorage] Failed to load metadata:', error)
    return {
      totalCount: 0,
      lastUpdated: null,
      storageSize: 0
    }
  }
}

/**
 * 更新历史元数据
 */
function updateMetadata() {
  try {
    const messages = getAllMessages()
    const metadata = {
      totalCount: messages.length,
      lastUpdated: Date.now(),
      storageSize: JSON.stringify(messages).length
    }
    localStorage.setItem(METADATA_KEY, JSON.stringify(metadata))
    return metadata
  } catch (error) {
    console.error('[historyStorage] Failed to update metadata:', error)
    return null
  }
}

/**
 * 获取存储使用情况
 * @returns {Object} - 存储信息
 */
function getStorageInfo() {
  try {
    const messages = getAllMessages()
    const totalSize = JSON.stringify(messages).length
    const metadata = getMetadata()
    
    return {
      totalCount: messages.length,
      totalSize: totalSize,
      totalSizeFormatted: formatBytes(totalSize),
      lastUpdated: metadata.lastUpdated ? new Date(metadata.lastUpdated).toLocaleString() : '从未',
      maxMessages: MAX_TOTAL_MESSAGES
    }
  } catch (error) {
    console.error('[historyStorage] Failed to get storage info:', error)
    return {
      totalCount: 0,
      totalSize: 0,
      totalSizeFormatted: '0 B',
      lastUpdated: '未知',
      maxMessages: MAX_TOTAL_MESSAGES
    }
  }
}

/**
 * 格式化字节数
 */
function formatBytes(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

// 导出所有方法
export default {
  saveMessage,
  saveMessages,
  loadHistory,
  getTotalCount,
  clearHistory,
  getMetadata,
  updateMetadata,
  getStorageInfo,
  MAX_MESSAGES_PER_PAGE,
  MAX_TOTAL_MESSAGES
}