/**
 * Agent WebSocket连接管理
 * 负责Agent的WebSocket连接、重连、消息处理等功能
 */

// 连接到指定的Agent（建立独立的WebSocket连接）
export async function connectToAgent(agent, options = {}, retryCount = 0) {
  const {
    gatewayUrl,
    authToken,
    getGatewayAddress,
    buildAgentWebSocketUrl,
    buildWebSocketProtocols,
    handleMessage,
    allOutputs,
    sockets,
    agentConnecting,
  } = options;

  const agentId = agent.agent_id;
  const maxRetries = 12; // 最多重试12次
  const retryDelay = 2000; // 2秒重试间隔
  const connectionTimeout = 10000; // 10秒连接超时（适应Agent启动时间）

  // 检查是否已有连接
  if (sockets.value.has(agentId)) {
    const existingWs = sockets.value.get(agentId);
    // 检查现有连接是否仍然有效
    if (existingWs && existingWs.readyState === WebSocket.OPEN) {
      console.log(`[AGENT] Already connected to ${agent.name || agentId}`);
      // 已连接，发送get_status请求以同步当前状态
      console.log(
        `[AGENT] Requesting status update for ${agent.name || agentId}`,
      );
      existingWs.send(JSON.stringify({ type: "get_status", payload: {} }));
      return;
    }
    // 连接已断开或正在关闭，确保完全关闭后再清理
    console.log(
      `[AGENT] Previous connection to ${agent.name || agentId} was not OPEN, cleaning up...`,
    );

    // 等待旧连接完全关闭（避免与后端连接冲突）
    if (existingWs && existingWs.readyState !== WebSocket.CLOSED) {
      console.log(
        `[AGENT] Waiting for old connection to close (state: ${existingWs.readyState})`,
      );
      existingWs.close();
      // 等待最多1秒让连接完全关闭
      await new Promise((resolve) => {
        if (existingWs.readyState === WebSocket.CLOSED) {
          resolve();
          return;
        }
        const checkInterval = setInterval(() => {
          if (existingWs.readyState === WebSocket.CLOSED) {
            clearInterval(checkInterval);
            resolve();
          }
        }, 50);
        // 最多等待1秒
        setTimeout(() => {
          clearInterval(checkInterval);
          resolve();
        }, 1000);
      });
    }

    // 清理旧连接
    sockets.value.delete(agentId);
    console.log(`[AGENT] Old connection cleaned up`);
  }

  console.log(`[AGENT] Connecting to ${agent.name || agentId}`);

  const { host, port } = getGatewayAddress(gatewayUrl);
  const url = buildAgentWebSocketUrl(
    host,
    agentId,
    null,
    port,
    String(agent?.node_id || "master").trim(),
  );

  agentConnecting.value = true;

  // 返回Promise，等待连接真正建立
  return new Promise((resolve, reject) => {
    try {
      const ws = new WebSocket(url, buildWebSocketProtocols(authToken));
      let connectionHandled = false; // 防止重复处理连接结果

      // 设置连接超时
      const timeoutId = setTimeout(() => {
        if (connectionHandled) return;
        connectionHandled = true;

        console.error(
          `[AGENT ${agentId}] Connection timeout after ${connectionTimeout}ms`,
        );
        ws.close();

        // 等待连接关闭后再重试
        const retryWithCleanup = async () => {
          // 清理可能存在的旧连接
          const oldWs = sockets.value.get(agentId);
          if (oldWs && oldWs !== ws && oldWs.readyState !== WebSocket.CLOSED) {
            console.log(
              `[AGENT ${agentId}] Cleaning up old connection before retry`,
            );
            oldWs.close();
            await new Promise((resolve) => {
              const check = setInterval(() => {
                if (oldWs.readyState === WebSocket.CLOSED) {
                  clearInterval(check);
                  resolve();
                }
              }, 50);
              setTimeout(() => {
                clearInterval(check);
                resolve();
              }, 500);
            });
            sockets.value.delete(agentId);
          }

          if (retryCount < maxRetries) {
            console.log(
              `[AGENT ${agentId}] Retrying... (${retryCount + 1}/${maxRetries})`,
            );
            agentConnecting.value = false;
            setTimeout(() => {
              connectToAgent(agent, options, retryCount + 1)
                .then(resolve)
                .catch(reject);
            }, retryDelay);
          } else {
            agentConnecting.value = false;
            const error = new Error(
              `Connection failed after ${maxRetries} retries`,
            );
            console.error(`[AGENT ${agentId}]`, error.message);
            reject(error);
          }
        };

        retryWithCleanup();
      }, connectionTimeout); // 结束setTimeout

      // 绑定消息处理
      ws.onmessage = (event) => {
        let message = null;
        try {
          message = JSON.parse(event.data);
        } catch (error) {
          console.warn(`[AGENT ${agentId}] message parse failed`, event.data);
          return;
        }
        console.log(`[AGENT ${agentId}] message`, message);
        handleMessage(message, agentId);
      };

      ws.onopen = () => {
        if (connectionHandled) {
          console.log(
            `[AGENT ${agentId}] Connection already handled, ignoring onopen`,
          );
          return;
        }
        connectionHandled = true;

        clearTimeout(timeoutId);
        console.log(`[AGENT ${agentId}] Connected to ${url}`);
        agentConnecting.value = false;

        // 保存连接
        sockets.value.set(agentId, ws);

        // 初始化消息记录
        if (!allOutputs.value.has(agentId)) {
          allOutputs.value.set(agentId, []);
        }

        // 标记连接已完成（在onclose中用于判断是否需要重试）
        ws._connectionCompleted = true;

        // 连接成功，resolve Promise
        resolve(ws);
      };

      ws.onclose = (event) => {
        if (connectionHandled) {
          console.log(
            `[AGENT ${agentId}] Connection already handled, ignoring onclose`,
          );
          return;
        }
        connectionHandled = true;

        clearTimeout(timeoutId);
        console.log(
          `[AGENT ${agentId}] Disconnected, code: ${event.code}, reason: ${event.reason}`,
        );

        sockets.value.delete(agentId);
        if (agentConnecting.value) agentConnecting.value = false;

        // 如果连接未完成就关闭，视为失败，触发重试
        if (!ws._connectionCompleted && retryCount < maxRetries) {
          console.log(
            `[AGENT ${agentId}] Connection closed before completion, retrying... (${retryCount + 1}/${maxRetries})`,
          );

          // 等待当前连接完全关闭后再重试（避免与后端连接冲突）
          const retryAfterClose = async () => {
            if (ws.readyState !== WebSocket.CLOSED) {
              console.log(
                `[AGENT ${agentId}] Waiting for connection to fully close...`,
              );
              await new Promise((resolve) => {
                const check = setInterval(() => {
                  if (ws.readyState === WebSocket.CLOSED) {
                    clearInterval(check);
                    resolve();
                  }
                }, 50);
                setTimeout(() => {
                  clearInterval(check);
                  resolve();
                }, 500);
              });
            }

            console.log(
              `[AGENT ${agentId}] Retrying... (${retryCount + 1}/${maxRetries})`,
            );
            connectToAgent(agent, options, retryCount + 1)
              .then(resolve)
              .catch(reject);
          };

          setTimeout(retryAfterClose, retryDelay);
        }
      };

      ws.onerror = (error) => {
        if (connectionHandled) {
          console.log(
            `[AGENT ${agentId}] Connection already handled, ignoring onerror`,
          );
          return;
        }
        connectionHandled = true;

        clearTimeout(timeoutId);
        console.error(`[AGENT ${agentId}] Connection error:`, error);
        if (agentConnecting.value) agentConnecting.value = false;

        // 触发重试
        if (retryCount < maxRetries) {
          console.log(
            `[AGENT ${agentId}] Error occurred, retrying... (${retryCount + 1}/${maxRetries})`,
          );

          // 关闭并等待连接完全关闭后再重试
          const retryAfterError = async () => {
            ws.close();
            if (ws.readyState !== WebSocket.CLOSED) {
              console.log(
                `[AGENT ${agentId}] Waiting for connection to fully close...`,
              );
              await new Promise((resolve) => {
                const check = setInterval(() => {
                  if (ws.readyState === WebSocket.CLOSED) {
                    clearInterval(check);
                    resolve();
                  }
                }, 50);
                setTimeout(() => {
                  clearInterval(check);
                  resolve();
                }, 500);
              });
            }

            connectToAgent(agent, options, retryCount + 1)
              .then(resolve)
              .catch(reject);
          };

          setTimeout(retryAfterError, retryDelay);
        } else {
          const err = new Error(
            `Connection failed after ${maxRetries} retries`,
          );
          reject(err);
        }
      };
    } catch (error) {
      console.error(`[AGENT ${agentId}] Failed to connect:`, error);
      agentConnecting.value = false;

      if (retryCount < maxRetries) {
        console.log(
          `[AGENT ${agentId}] Exception occurred, retrying... (${retryCount + 1}/${maxRetries})`,
        );
        setTimeout(() => {
          connectToAgent(agent, options, retryCount + 1)
            .then(resolve)
            .catch(reject);
        }, retryDelay);
      } else {
        reject(error);
      }
    }
  });
}
