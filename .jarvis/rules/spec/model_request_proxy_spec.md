---
name: model_request_proxy_spec
description: 模型请求通过指定节点代理的功能规范
---

# 模型请求代理功能规范

## 1. 功能概述

### 1.1 目标

实现模型请求通过指定节点代理的功能，支持将Agent的模型请求精确转发到指定节点处理。

**重要：本功能支持所有Platform（OpenAI、Claude等），不限于特定平台。**

### 1.2 使用场景

- 指定节点代理：将特定Agent的模型请求转发到指定节点
- 网络访问代理：通过节点代理访问外部模型服务
- 环境隔离：在不同网络环境中代理模型请求

### 1.3 价值

- 简化配置：通过节点代理访问外部模型服务
- 精确控制：指定特定节点处理特定Agent的请求
- 网络穿透：通过节点代理解决网络访问限制

## 2. 接口定义

### 2.1 复用现有节点网关代理

本方案复用现有的节点网关代理机制，具体实现如下：

#### 现有代理机制

1. **协议支持**：现有 `NODE_HTTP_PROXY_REQUEST` 协议已支持节点间HTTP代理
2. **处理函数**：`_dispatch_node_http_request` 函数处理节点间代理请求
3. **路由机制**：通过 `/node/{node_id}/...` 路径格式访问特定节点

#### 复用方式

1. **Agent配置扩展**：在Agent配置中增加代理节点设置
2. **路径转换**：将模型请求URL转换为节点代理路径格式
3. **协议复用**：利用现有的 `NODE_HTTP_PROXY_REQUEST` 协议进行代理

### 2.2 Agent配置扩展

#### 前端配置

在创建Agent的前端界面中，需要在模型组选择旁边添加模型代理节点配置：

- **配置项名称**：模型代理节点
- **配置说明**：选择模型请求应该通过哪个节点代理出去
- **默认值**：空（不使用代理）
- **UI位置**：在模型组选择下方

在Agent配置中增加代理设置：

```python
class AgentConfig:
    # ... 现有配置 ...
    model_proxy_node: Optional[str] = None  # 代理节点ID，默认为空
```

### 2.3 路径转换规则

#### 原始请求

```
https://aaa.com/v1/chat/completions
```

#### 转换后请求

```
http://网关地址/node/{节点ID}/model_proxy/https://aaa.com/v1/chat/completions
```

#### 路径格式说明

- `node/{node_id}`：现有节点访问路径前缀
- `model_proxy`：新增的模型代理路径标识
- `https://aaa.com/v1/chat/completions`：原始请求URL（需URL编码）

### 2.4 处理流程

1. **请求发起**：Agent发起模型请求
2. **路径检查**：检查 `model_proxy_node` 配置
3. **路径转换**：如果配置了代理节点，转换请求路径
4. **协议复用**：使用现有的 `NODE_HTTP_PROXY_REQUEST` 协议
5. **节点处理**：目标节点接收并处理代理请求
6. **响应返回**：返回代理响应给Agent

### 2.2 请求路径转换

#### 原始请求

```
https://aaa.com/v1/chat/completions
```

#### 转换后请求

```
http://网关地址/node/{节点ID}/model_proxy/https://aaa.com/v1/chat/completions
```

#### 路径格式

```
/node/{node_id}/model_proxy/{original_url}
```

- `node_id`：目标节点ID
- `original_url`：原始请求URL（需要URL编码）

### 2.5 节点处理接口

#### 现有节点处理机制

现有节点通过 `_dispatch_node_http_request` 函数处理HTTP代理请求，该函数接收以下参数：

```python
async def _dispatch_node_http_request(
    method: str,
    path: str,
    query: str,
    headers: Dict[str, Any],
    body: str,
) -> Dict[str, Any]:
```

#### 模型代理处理扩展

在现有处理函数中增加模型代理路径识别和处理逻辑：

```python
async def _dispatch_node_http_request(
    method: str,
    path: str,
    query: str,
    headers: Dict[str, Any],
    body: str,
) -> Dict[str, Any]:
    # 检查是否为模型代理请求
    if path.startswith("/model_proxy/"):
        return await handle_model_proxy_request(
            method=method,
            path=path,
            query=query,
            headers=headers,
            body=body
        )
    
    # 其他请求处理...
```

#### 模型代理处理函数

```python
async def handle_model_proxy_request(
    method: str,
    path: str,
    query: str,
    headers: Dict[str, Any],
    body: str,
) -> Dict[str, Any]:
    """处理模型代理请求
    
    Args:
        method: HTTP方法
        path: 请求路径（格式：/model_proxy/{url_encoded_target_url}）
        query: 查询参数
        headers: 请求头
        body: 请求体
        
    Returns:
        Dict[str, Any]: 代理响应
    """
    # 解析目标URL
    target_url = path[len("/model_proxy/"):]
    target_url = urllib.parse.unquote(target_url)
    
    # 构建完整URL（包含查询参数）
    if query:
        target_url = f"{target_url}?{query}"
    
    # 代理请求到目标URL
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=30.0
        )
    
    # 返回响应
    return {
        "success": True,
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text
    }
```

#### 请求转发逻辑

1. **路径识别**：识别 `/model_proxy/` 前缀
2. **URL解析**：解析并解码目标URL
3. **请求转发**：使用httpx转发请求到目标URL
4. **响应处理**：返回标准化的响应格式

## 3. 输入输出说明

### 3.1 Agent配置参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| model_proxy_node | string | 否 | 代理节点ID，默认为空 |

### 3.2 请求参数

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| node_id | string | 是 | 目标节点ID |
| original_url | string | 是 | 原始请求URL（URL编码） |
| method | string | 是 | HTTP方法 |
| headers | object | 是 | 请求头 |
| body | bytes | 否 | 请求体 |

### 3.3 响应参数

| 参数名 | 类型 | 说明 |
|--------|------|------|
| status_code | number | HTTP状态码 |
| headers | object | 响应头 |
| body | bytes | 响应体 |

### 3.4 错误处理

| 错误代码 | 描述 | 处理方式 |
|----------|------|----------|
| NODE_NOT_FOUND | 节点不存在 | 返回404错误 |
| INVALID_URL | URL格式错误 | 返回400错误 |
| PROXY_FAILED | 代理失败 | 返回502错误 |
| TIMEOUT | 请求超时 | 返回504错误 |

## 4. 功能行为

### 4.1 复用现有机制

本方案完全复用现有的节点网关代理机制，具体流程如下：

#### 现有代理机制

1. **协议支持**：`NODE_HTTP_PROXY_REQUEST` 协议已支持节点间HTTP代理
2. **路径格式**：`/node/{node_id}/...` 格式访问特定节点
3. **处理函数**：`_dispatch_node_http_request` 函数处理代理请求

#### 模型代理扩展

1. **路径扩展**：在现有路径格式基础上增加 `/model_proxy/` 标识
2. **处理扩展**：在现有处理函数中增加模型代理识别逻辑
3. **配置扩展**：在Agent配置中增加代理节点设置

### 4.2 完整流程

#### 流程图

```
┌─────────┐     ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent  │     │ Main Gateway│     │ Node Gateway    │     │ External API    │
└────┬────┘     └──────┬──────┘     └────────┬────────┘     └────────┬────────┘
     │                 │                      │                       │
     │ 1.检测配置       │                      │                       │
     │ 2.构造代理路径   │                      │                       │
     │ 3.发送HTTP请求   │                      │                       │
     ├────────────────►│                      │                       │
     │                 │ 4.路由到子节点        │                       │
     │                 ├─────────────────────►│                       │
     │                 │                      │ 5.识别代理路径        │
     │                 │                      │ 6.解码URL             │
     │                 │                      │ 7.转发HTTP请求        │
     │                 │                      ├──────────────────────►│
     │                 │                      │ 8.返回响应            │
     │                 │                      │◄──────────────────────┤
     │                 │ 9.响应回传           │                       │
     │                 │◄─────────────────────┤                       │
     │ 10.返回响应      │                      │                       │
     │◄────────────────┤                      │                       │
```

#### 详细步骤

1. **Agent配置代理节点**：设置 `model_proxy_node` 为代理节点ID
   ```python
   agent_config.model_proxy_node = "node-123"
   ```

2. **Agent检测配置**：Agent发起模型请求前，检测是否配置了代理节点

3. **Agent构造代理路径**：如果配置了代理节点，Agent将请求路径转换为：
   ```
   /node/{节点ID}/model_proxy/{URL编码的目标URL}
   ```
   示例：
   ```
   /node/node-123/model_proxy/https%3A%2F%2Fapi.openai.com%2Fv1%2Fchat%2Fcompletions
   ```

4. **Agent发送HTTP请求**：Agent直接发送HTTP请求到主网关

5. **主网关路由**：主网关利用现有路由机制，将请求转发到对应的子节点网关

6. **子节点网关识别代理路径**：子节点网关接收请求，识别 `/model_proxy/` 路径前缀

7. **子节点网关解码URL**：解析并URL解码得到目标URL

8. **子节点网关转发请求**：使用httpx转发HTTP请求到外部API

9. **响应返回**：外部API返回响应，通过子节点网关 -> 主网关 -> Agent 逐级返回

10. **Agent接收响应**：Agent接收最终的模型响应

### 4.3 配置示例

#### Agent配置

```python
# 在Agent配置中设置代理节点
agent_config.model_proxy_node = "node-123"  # 指定代理节点ID

# 如果不设置（默认为空），则使用直连
agent_config.model_proxy_node = None  # 默认值
```

#### 配置文件示例

```yaml
# agent_config.yaml
model_proxy_node: "node-123"  # 代理节点ID
```

#### 请求示例

```python
# 原始请求（由Agent发起）
response = requests.post(
    "https://api.openai.com/v1/chat/completions",
    headers={"Authorization": "Bearer sk-xxx"},
    json={"model": "gpt-3.5-turbo", "messages": [...]}
)

# 转换后请求（自动，由Agent内部处理）
# 实际发送到：http://gateway/node/node-123/model_proxy/https%3A%2F%2Fapi.openai.com%2Fv1%2Fchat%2Fcompletions
```

#### 使用场景

1. **网络代理**：通过节点代理访问外部模型服务
   ```python
   # 配置代理节点
   agent_config.model_proxy_node = "proxy-node-01"
   
   # 所有模型请求将通过proxy-node-01代理
   ```

2. **环境隔离**：在不同网络环境中代理模型请求
   ```python
   # 内网环境配置
   agent_config.model_proxy_node = "internal-node"
   
   # 外网环境配置
   agent_config.model_proxy_node = "external-node"
   ```

3. **精确控制**：指定特定节点处理特定Agent的请求
   ```python
   # Agent A使用节点1
   agent_a_config.model_proxy_node = "node-01"
   
   # Agent B使用节点2
   agent_b_config.model_proxy_node = "node-02"
   ```

### 4.3 节点处理实现

```python
async def handle_model_proxy_request(
    node_id: str,
    original_url: str,
    method: str,
    headers: Dict[str, str],
    body: Optional[bytes] = None
) -> Response:
    # 解码URL
    target_url = urllib.parse.unquote(original_url)
    
    # 构建请求
    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body,
            timeout=30.0
        )
    
    # 返回响应
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )
```
## 5. SSE流式响应支持

### 5.1 问题分析

模型API（如OpenAI）的流式响应使用SSE（Server-Sent Events）格式，需要实时传输给客户端。现有机制存在以下挑战：

1. 现有`_dispatch_node_http_request`函数返回`Dict[str, Any]`，会等待整个响应完成
2. SSE流需要实时传输，不能等待响应完成
3. 需要保持与标准HTTP请求的兼容性

### 5.2 解决方案：HTTP反向代理 + StreamingResponse

**核心思路**：不通过WebSocket协议，而是让节点网关直接作为HTTP反向代理，使用FastAPI的`StreamingResponse`实时转发SSE流。

#### 架构图

```
┌─────────┐     ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Agent  │     │ Main Gateway│     │ Node Gateway    │     │ External API    │
└────┬────┘     └──────┬──────┘     └────────┬────────┘     └────────┬────────┘
     │                 │                      │                       │
     │ HTTP Request    │                      │                       │
     ├────────────────►│                      │                       │
     │                 │ Route to Node        │                       │
     │                 ├─────────────────────►│                       │
     │                 │                      │ HTTP Request          │
     │                 │                      ├──────────────────────►│
     │                 │                      │                       │
     │                 │                      │◄──────────────────────┤
     │                 │                      │ SSE Stream (chunked)  │
     │                 │ StreamingResponse    │                       │
     │                 │◄─────────────────────┤                       │
     │ SSE Stream      │                      │                       │
     │◄────────────────┤                      │                       │
```

#### 关键实现

**节点网关端**：添加HTTP代理端点，支持流式响应

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import httpx

@app.api_route("/model_proxy/{target_url:path}", methods=["GET", "POST"])
async def model_proxy(target_url: str, request: Request):
    """模型代理端点，支持SSE流式响应"""
    # 解码目标URL
    from urllib.parse import unquote
    target_url = unquote(target_url)
    
    # 获取请求体
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)  # 移除host头
    
    # 判断是否为流式请求
    is_stream = False
    if body:
        try:
            import json
            req_data = json.loads(body)
            is_stream = req_data.get("stream", False)
        except:
            pass
    
    # 代理请求到外部API
    async with httpx.AsyncClient() as client:
        if is_stream:
            # 流式响应：使用StreamingResponse
            async def stream_generator():
                async with client.stream(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    timeout=300.0
                ) as response:
                    async for chunk in response.aiter_bytes():
                        yield chunk
            
            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应：正常返回
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
```

**Agent端**：直接HTTP请求到代理端点

```python
import httpx

async def make_model_request(model_url: str, data: dict):
    """发起模型请求"""
    if agent_config.model_proxy_node:
        # 构造代理URL
        from urllib.parse import quote
        proxy_url = f"http://gateway/node/{agent_config.model_proxy_node}/model_proxy/{quote(model_url, safe='')}"
    else:
        proxy_url = model_url
    
    # 判断是否为流式请求
    if data.get("stream", False):
        # 流式请求
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", proxy_url, json=data) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]  # 去掉"data: "前缀
    else:
        # 非流式请求
        async with httpx.AsyncClient() as client:
            response = await client.post(proxy_url, json=data)
            return response.json()
```

### 5.3 优势

1. **简单直接**：复用标准HTTP协议，无需复杂的WebSocket传输
2. **兼容性好**：与现有模型API客户端完全兼容
3. **实时传输**：使用StreamingResponse实现真正的流式传输
4. **改动最小**：只需在节点网关添加一个端点

### 5.4 验收标准

1. **流式请求识别**：正确识别请求中的`stream=true`参数
2. **SSE格式保持**：保持原始SSE格式不变
3. **实时传输**：数据块实时传输，不等待响应完成
4. **非流式兼容**：非流式请求正常工作
5. **错误处理**：流式传输中断时正确处理

## 6. 验收标准
        await websocket.send_json({
            "type": "MODEL_STREAM_CHUNK",
            "stream_id": stream_id,
            "chunk": chunk
        })
    
    # 发送结束标记
    await websocket.send_json({
        "type": "MODEL_STREAM_END",
        "stream_id": stream_id
    })
```

#### Agent端实现

```python
async def make_model_request(url, data, stream=False):
    """发起模型请求"""
    if stream and agent_config.model_proxy_node:
        # 流式请求通过代理
        proxy_url = f"/node/{agent_config.model_proxy_node}/model_proxy/{url_encode(url)}"
        
        # 发起请求
        response = await send_request(proxy_url, {**data, "stream": True})
        
        if response.get("stream"):
            # 返回流式迭代器
            return stream_iterator(response["stream_id"])
    
    # 非流式请求或直连
    return await direct_request(url, data)

async def stream_iterator(stream_id):
    """流式数据迭代器"""
    while True:
        chunk = await receive_stream_chunk(stream_id)
        if chunk is None:  # 结束标记
            break
        yield chunk
```

### 5.5 验收标准

1. **流式请求识别**：正确识别请求中的`stream=true`参数
2. **流式响应传输**：流式响应能实时传输到Agent
3. **数据完整性**：流式数据块完整无丢失
4. **结束标记**：流式响应正确发送结束标记
5. **错误处理**：流式传输中断时正确处理错误

## 6. 验收标准

## 5. 验收标准

### 5.1 复用机制验收

1. **协议复用**：正确复用现有的 `NODE_HTTP_PROXY_REQUEST` 协议
2. **路径格式**：正确使用 `/node/{node_id}/model_proxy/...` 路径格式
3. **处理函数**：正确扩展 `_dispatch_node_http_request` 函数
4. **配置扩展**：正确扩展Agent配置，增加 `model_proxy_node` 字段

### 5.2 功能验收

1. **配置生效**：Agent能正确配置代理节点ID
2. **路径转换**：请求URL能正确转换为代理路径格式
3. **节点处理**：节点能正确识别和处理模型代理请求
4. **请求转发**：节点能正确代理请求到目标URL
5. **响应返回**：响应能正确返回给Agent

### 5.3 配置验收

1. **默认行为**：默认配置（空值）时使用直连，不进行代理
2. **配置生效**：代理节点ID配置正确生效
3. **动态更新**：配置修改后立即生效
4. **配置验证**：配置格式正确，支持字符串类型

### 5.4 错误处理验收

1. **节点不存在**：当指定的代理节点不存在时返回正确错误
2. **URL格式错误**：当目标URL格式错误时返回正确错误
3. **代理失败**：当代理请求失败时返回正确错误
4. **超时处理**：当请求超时时返回正确错误
5. **错误格式**：错误信息格式与现有错误处理机制一致

### 5.5 兼容性验收

1. **向后兼容**：不影响现有功能，未配置代理时行为不变
2. **协议兼容**：与现有节点通信协议完全兼容
3. **配置兼容**：与现有Agent配置格式兼容
4. **接口兼容**：与现有HTTP接口格式兼容

## 6. 实现计划

### 6.1 实现阶段

| 阶段 | 任务 | 预计工期 | 依赖 |
|------|------|----------|------|
| 阶段1 | 在Agent配置中增加`model_proxy_node`字段 | 0.5天 | 无 |
| 阶段2 | 在请求处理中实现路径转换逻辑 | 1天 | 阶段1 |
| 阶段3 | 在节点处理函数中增加`/model_proxy/`路径识别 | 1天 | 无 |
| 阶段4 | 实现模型代理请求转发功能 | 1天 | 阶段3 |
| 阶段5 | 添加必要的错误处理和日志记录 | 0.5天 | 阶段4 |
| 阶段6 | 测试和验证 | 1天 | 阶段2, 阶段5 |

### 6.2 里程碑

- **里程碑1**：配置扩展完成 - Agent配置增加`model_proxy_node`字段
- **里程碑2**：路径转换完成 - 请求处理中实现路径转换逻辑
- **里程碑3**：节点处理完成 - 节点处理函数增加`/model_proxy/`路径识别
- **里程碑4**：代理功能完成 - 模型代理请求转发功能实现
- **里程碑5**：错误处理完成 - 错误处理和日志记录添加
- **里程碑6**：测试验证完成 - 功能测试和验证通过

### 6.3 风险评估

| 风险 | 影响 | 概率 | 风险等级 | 应对措施 |
|------|------|------|----------|----------|
| 配置兼容性问题 | 高 | 低 | 中 | 充分测试配置格式，确保向后兼容 |
| 路径转换错误 | 高 | 中 | 高 | 详细测试各种URL格式，添加边界检查 |
| 节点处理异常 | 中 | 中 | 中 | 添加完善的错误处理和日志记录 |
| 性能问题 | 低 | 低 | 低 | 使用异步处理，优化连接池 |

## 7. 附录

### 7.1 术语表

| 术语 | 定义 |
|------|------|
| 代理节点 | 处理模型代理请求的节点 |
| 原始URL | 客户端请求的原始目标URL |
| 网关地址 | Jarvis网关的访问地址 |

### 7.2 参考文档

#### 现有实现参考

- **节点协议**：`src/jarvis/jarvis_web_gateway/node_protocol.py`
  - `NODE_HTTP_PROXY_REQUEST`：现有节点HTTP代理协议
  - `NODE_HTTP_PROXY_RESPONSE`：现有节点HTTP代理响应协议

- **节点管理**：`src/jarvis/jarvis_web_gateway/node_manager.py`
  - `NodeConnectionManager`：节点连接管理器
  - `_handle_node_http_proxy_request`：现有节点HTTP代理处理函数
  - `_dispatch_node_http_request`：现有节点HTTP请求分发函数

- **代理管理**：`src/jarvis/jarvis_web_gateway/agent_proxy_manager.py`
  - `AgentProxyManager`：Agent代理管理器
  - `proxy_http_request`：现有HTTP代理请求函数

- **Agent配置**：`src/jarvis/jarvis_agent/config.py`
  - Agent配置结构定义

#### 外部参考

- OpenAI API文档：https://platform.openai.com/docs/api-reference
- HTTP代理最佳实践：https://developer.mozilla.org/en-US/docs/Web/HTTP/Proxy_servers_and_tunneling
- httpx文档：https://www.python-httpx.org/