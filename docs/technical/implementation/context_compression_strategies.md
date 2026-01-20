# 上下文压缩策略文档

## 当前已实现的策略

### 1. **摘要压缩（Summary Compression）**
- **实现位置**: `Agent._summarize_and_clear_history()`
- **触发条件**:
  - 剩余token低于输入窗口的25%时自动触发
  - 对话轮次达到阈值时触发
  - LLM主动输出 `!!!SUMMARY!!!` 标记时触发
  - 用户手动触发
- **压缩方式**: 使用LLM生成对话摘要，保留关键信息
- **保留内容**:
  - 原始任务目标（`original_user_input`）
  - 用户固定内容（`pin_content`）
  - 最近记忆（`recent_memories`）
  - 任务列表状态
  - Git diff统计信息

### 2. **Token阈值触发**
- **实现位置**: `AgentRunLoop.run()`
- **阈值**: 剩余token < 输入窗口的25%
- **优点**: 自动触发，无需人工干预

### 3. **对话轮次阈值**
- **实现位置**: `AgentRunLoop.run()`
- **配置**: `conversation_turn_threshold`
- **优点**: 防止对话过长，定期清理

### 4. **Git Diff截断**
- **实现位置**: `AgentRunLoop._check_diff_token_limit()`
- **限制**: diff内容最多占用输入窗口的10%
- **策略**: 按行截断，保留前面的内容

### 5. **消息截断**
- **实现位置**: `BasePlatform._truncate_message_if_needed()`
- **策略**: 当消息过长时，保留前面的内容，在句子边界截断

### 6. **工具输出截断**
- **实现位置**: `ToolRegistry._format_tool_output()`
- **策略**: 根据剩余token数量动态截断工具输出

### 7. **关键信息保留**
- **实现位置**: `Agent._handle_history_with_summary()`
- **保留内容**:
  - 原始任务目标（最高优先级）
  - 用户固定内容
  - 最近记忆
  - 任务列表状态

### 8. **滑动窗口压缩（Sliding Window Compression）** ✅ 已实现
- **实现位置**: `Agent._sliding_window_compression()`
- **触发条件**:
  - 剩余token低于输入窗口的25%时自动触发（在完整摘要压缩之前尝试）
  - 消息数量超过窗口大小的2倍时执行
- **配置**: 通过环境变量 `sliding_window_size` 设置窗口大小（默认9条：用户/工具消息4条+助手消息5条，奇数以避免连续的同role消息）
- **压缩方式**:
  - 保留系统消息（始终不压缩）
  - 保留最近的用户/工具消息4条和助手消息5条（共9条，完整保留，奇数以避免连续的同role消息）
  - 压缩更早的对话（使用临时模型生成摘要）
  - 将压缩摘要作为一条用户消息插入历史
- **优点**:
  - 保留最近的完整上下文，压缩历史
  - 比完整摘要压缩更轻量，不会清空所有历史
  - 自动触发，无需人工干预
- **使用场景**: 适合长期运行的对话，在token不足时先尝试滑动窗口压缩，如果仍不足再执行完整摘要压缩

## 其他可能的策略

### 8. **滑动窗口压缩（Sliding Window Compression）** ✅ 已实现
- **实现位置**: `Agent._sliding_window_compression()`
- **触发条件**: 
  - 剩余token低于输入窗口的25%时自动触发（在完整摘要压缩之前尝试）
  - 消息数量超过窗口大小的2倍时执行
- **配置**: 通过环境变量 `sliding_window_size` 设置窗口大小（默认9条：用户/工具消息4条+助手消息5条，奇数以避免连续的同role消息）
- **压缩方式**: 
  - 保留系统消息（始终不压缩）
  - 保留最近的N轮对话（完整保留）
  - 压缩更早的对话（使用临时模型生成摘要）
  - 将压缩摘要作为一条用户消息插入历史
- **优点**: 
  - 保留最近的完整上下文，压缩历史
  - 比完整摘要压缩更轻量，不会清空所有历史
  - 自动触发，无需人工干预
- **缺点**: 可能丢失重要的历史信息（但比完全删除好）

### 9. **重要性评分压缩（Importance Scoring）** ✅ 已实现
- **实现位置**: `Agent._importance_scoring_compression()` 和 `Agent._score_message_importance()`
- **触发条件**: 
  - 剩余token低于输入窗口的25%时自动触发（在滑动窗口压缩之前尝试）
  - 消息数量超过10条时执行
- **配置**: 通过环境变量 `importance_score_threshold` 设置评分阈值（默认3.0）
- **评分维度**:
  - **基础评分**:
    - 用户输入：5.0分（高优先级）
    - 助手响应：2.0分（中优先级）
    - 系统消息：1.0分（低优先级，但始终保留）
  - **关键词加分**:
    - 重要关键词（错误、失败、修复、完成、任务等）：每个+0.5分
    - 工具调用相关：+2.0分
    - 错误和修复相关：+2.0分
    - 任务完成相关：+1.5分
    - 用户标记的重要内容（<Pin>、重要、关键等）：+3.0分
- **压缩方式**: 
  - 保留系统消息（始终不压缩）
  - 保留高分消息（评分 >= 阈值）
  - 压缩低分消息为摘要
  - 保留最近5条低分消息作为上下文
- **优点**: 
  - 智能识别重要消息，保留关键信息
  - 比滑动窗口压缩更精细，能保留分散的重要消息
  - 自动触发，无需人工干预
- **缺点**: 评分算法可能需要根据实际场景调整

### 10. **分层压缩（Hierarchical Compression）**
- **描述**: 对不同类型的内容使用不同的压缩策略
- **分层策略**:
  - **系统提示词**: 保持不变（最高优先级）
  - **用户输入**: 保留完整内容
  - **工具调用**: 保留调用和关键结果，压缩详细输出
  - **LLM响应**: 压缩中间过程，保留决策和结论
- **优点**: 针对性强，保留最重要的信息

### 11. **增量摘要（Incremental Summarization）** ✅ 已实现
- **实现位置**: `Agent._incremental_summarization_compression()`
- **触发条件**: 
  - 剩余token低于输入窗口的25%时自动触发（在重要性评分压缩之后，滑动窗口压缩之前尝试）
  - 消息数量超过2个chunk时执行
- **配置**: 通过环境变量 `incremental_summary_chunk_size` 设置chunk大小（默认20轮）
- **压缩方式**: 
  - 将对话历史分成多个chunk（每个chunk包含N轮对话）
  - 对前面的chunks进行摘要压缩
  - 保留最后一个chunk的完整内容（不压缩）
  - 系统消息始终保留，不参与分块
- **优点**: 
  - 避免一次性压缩大量内容，保持摘要质量
  - 保留最近对话的完整上下文
  - 分块压缩，每个chunk的摘要质量更高
- **缺点**: 如果chunk数量很多，可能会产生多个摘要消息

### 12. **语义聚类压缩（Semantic Clustering）**
- **描述**: 将相似的消息聚类，只保留每个聚类的代表性消息
- **实现思路**:
  ```python
  def semantic_clustering_compression(messages):
      clusters = cluster_by_similarity(messages)
      representatives = [select_representative(cluster) for cluster in clusters]
      return representatives
  ```
- **优点**: 去除冗余信息，保留多样性

### 13. **关键事件提取（Key Event Extraction）** ✅ 已实现
- **实现位置**: `Agent._key_event_extraction_compression()` 和 `Agent._is_key_event()`
- **触发条件**: 
  - 剩余token低于输入窗口的25%时自动触发（在重要性评分压缩之后，增量摘要压缩之前尝试）
  - 消息数量超过10条时执行
- **关键事件类型**:
  - **任务开始/完成**: 包含 `!!!COMPLETE!!!`、`!!!SUMMARY!!!`、任务完成等标记
  - **重要决策点**: 包含"决定"、"选择"、"方案"、"策略"、"计划"、"设计"、"架构"等关键词，且内容较长（>100字符）
  - **错误和修复**: 包含"错误"、"失败"、"异常"、"bug"、"修复"、"解决"、"问题"、"调试"、"排查"等关键词
  - **关键工具调用结果**: 包含工具调用标记、执行成功/失败信息
  - **用户标记的重要内容**: 包含 `<Pin>` 标记或"重要"、"关键"、"必须"、"注意"等关键词
  - **用户输入**: 所有用户输入消息（通常都是关键事件）
- **压缩方式**: 
  - 保留系统消息（始终不压缩）
  - 完整保留关键事件消息（按时间顺序）
  - 压缩非关键事件消息为摘要
  - 保留最近5条非关键消息作为上下文
- **优点**: 
  - 智能识别关键事件，保留重要决策和结果
  - 保留错误和修复信息，便于问题排查
  - 保留工具调用结果，维持执行上下文
  - 自动触发，无需人工干预
- **缺点**: 事件识别规则可能需要根据实际场景调整

### 14. **时间衰减压缩（Time Decay Compression）**
- **描述**: 根据消息的时间距离，使用不同的压缩强度
- **策略**: 
  - 最近的消息：不压缩或轻度压缩
  - 中等时间的消息：中度压缩
  - 很久的消息：重度压缩或删除
- **实现思路**:
  ```python
  def time_decay_compression(messages, current_time):
      for msg in messages:
          age = current_time - msg.timestamp
          compression_ratio = calculate_compression_ratio(age)
          compressed_msg = compress(msg, compression_ratio)
  ```

### 15. **主题分割压缩（Topic Segmentation）**
- **描述**: 将对话按主题分割，压缩已完成的主题，保留当前主题
- **实现思路**:
  ```python
  def topic_segmentation_compression(history):
      topics = segment_by_topic(history)
      current_topic = topics[-1]
      completed_topics = topics[:-1]
      compressed = [summarize_topic(topic) for topic in completed_topics]
      return compressed + current_topic
  ```

### 16. **问答对压缩（Q&A Pair Compression）**
- **描述**: 识别问答对，只保留问题和最终答案，压缩中间过程
- **实现思路**:
  ```python
  def qa_pair_compression(history):
      qa_pairs = extract_qa_pairs(history)
      compressed = [compress_qa_pair(pair) for pair in qa_pairs]
      return compressed
  ```

### 17. **工具调用链压缩（Tool Call Chain Compression）**
- **描述**: 压缩工具调用的中间步骤，只保留调用链的起点和终点
- **实现思路**:
  ```python
  def tool_call_chain_compression(history):
      chains = extract_tool_call_chains(history)
      compressed = [compress_chain(chain) for chain in chains]
      return compressed
  ```

### 18. **向量检索压缩（Vector Retrieval Compression）**
- **描述**: 使用向量检索，只保留与当前任务最相关的历史消息
- **实现思路**:
  ```python
  def vector_retrieval_compression(history, current_context):
      embeddings = embed_messages(history)
      current_embedding = embed(current_context)
      relevant = retrieve_top_k(embeddings, current_embedding, k=20)
      return relevant
  ```

### 19. **结构化信息提取（Structured Information Extraction）**
- **描述**: 提取结构化信息（任务列表、决策树、状态机），压缩非结构化内容
- **实现思路**:
  ```python
  def structured_extraction_compression(history):
      structured = extract_structured_info(history)
      unstructured = extract_unstructured(history)
      compressed_unstructured = summarize(unstructured)
      return structured + compressed_unstructured
  ```

### 20. **自适应压缩（Adaptive Compression）** ✅ 已实现
- **实现位置**: `Agent._adaptive_compression()` 和 `Agent._detect_task_type()`
- **触发条件**: 
  - 剩余token低于输入窗口的25%时自动触发（作为主要压缩策略）
  - 自动检测任务类型并选择最适合的压缩策略
- **任务类型识别**:
  - **代码任务（code）**: 
    - Agent类型为CodeAgent
    - 对话中包含代码相关工具调用（edit_file、read_code、execute_script等）
    - 包含文件操作、代码修改等关键词
  - **分析任务（analysis）**: 
    - 对话中包含分析相关工具调用（search、rg、fd、grep、retrieve_memory等）
    - 包含检索、查询、分析等关键词
  - **对话任务（conversation）**: 
    - 主要是短的用户输入和响应
    - 问答式交互
  - **混合任务（mixed）**: 
    - 包含多种类型的工具调用
  - **未知类型（unknown）**: 
    - 无法明确识别的任务类型
- **策略选择**（优先使用滑动窗口压缩）:
  - **代码任务**: 
    1. 滑动窗口（保留最近对话，优先）
    2. 关键事件提取（保留代码变更和工具调用）
    3. 增量摘要（分块压缩）
  - **分析任务**: 
    1. 滑动窗口（保留最近对话，优先）
    2. 重要性评分（保留数据和结论）
    3. 增量摘要（分块压缩）
  - **对话任务**: 
    1. 滑动窗口（保留问答对，优先）
    2. 重要性评分（保留重要消息）
    3. 增量摘要（分块压缩）
  - **混合任务**: 
    1. 滑动窗口（保留最近对话，优先）
    2. 增量摘要（分块压缩）
    3. 重要性评分（保留重要消息）
  - **未知类型**: 
    1. 滑动窗口（保留最近对话，优先）
    2. 重要性评分（通用策略）
    3. 增量摘要（分块压缩）
- **优点**: 
  - 根据任务类型自动选择最适合的压缩策略
  - 最大化保留任务相关的关键信息
  - 智能识别任务类型，无需人工配置
  - 自动回退机制，确保压缩成功
- **缺点**: 任务类型识别可能需要根据实际场景调整

## 策略组合建议

### 推荐组合1：基础组合
- 摘要压缩（主要策略）
- Token阈值触发（自动触发）
- 关键信息保留（确保不丢失）

### 推荐组合2：高级组合 ✅ 已实现
- 摘要压缩（主要策略）
- 重要性评分压缩（优先保留重要信息）✅
- 关键事件提取（保留关键决策）✅
- 增量摘要压缩（分块压缩，保持质量）✅
- 滑动窗口压缩（保留最近上下文）✅

### 推荐组合3：智能组合 ✅ 已实现
- 自适应压缩（根据任务类型选择）✅
- 增量摘要（定期压缩）✅
- 关键事件提取（保留关键决策）✅
- 关键信息保留（确保不丢失）✅

## 实施优先级

### 高优先级（立即实施）
1. ✅ 摘要压缩（已实现）
2. ✅ Token阈值触发（已实现）
3. ✅ 关键信息保留（已实现）
4. ✅ 滑动窗口压缩（已实现）

### 中优先级（短期实施）
5. ✅ 重要性评分压缩（已实现）
6. ✅ 增量摘要（已实现）
7. ✅ 关键事件提取（已实现）

### 低优先级（长期优化）
8. 语义聚类压缩
9. 向量检索压缩
10. ✅ 自适应压缩（已实现）

## 注意事项

1. **压缩质量**: 压缩后的内容应该保持语义完整性
2. **关键信息**: 必须确保原始任务目标、关键决策不被丢失
3. **性能考虑**: 压缩操作本身不应该消耗过多token
4. **可恢复性**: 压缩后的内容应该能够通过会话文件恢复
5. **用户体验**: 压缩过程应该对用户透明，不影响任务执行
