# Hacker News 搜索规则

## 规则简介

本规则用于指导如何使用 Hacker News Algolia API 搜索最新的技术资讯和讨论。

## 你必须遵守的原则

### API 使用原则

**要求说明：**

- **必须**：使用 HTTPS 协议访问 API
- **必须**：合理设置请求参数，避免不必要的网络请求
- **必须**：处理 API 错误响应，包括超时和无效请求
- **禁止**：在短时间内发送大量请求，避免被限流
- **禁止**：缓存敏感数据，如用户信息

**性能优化：**

- 适当使用分页参数（page 和 hitsPerPage）控制返回结果数量
- 使用时间过滤器（numericFilters）获取最新内容
- 避免重复请求相同的数据

## 你必须执行的操作

### 操作1：获取 Hacker News 搜索结果

**执行步骤：**

1. 确定 API 基础 URL
   https://hn.algolia.com/api/v1

2. 构造搜索请求
   - 基础端点：/search
   - 完整 URL：https://hn.algolia.com/api/v1/search

3. 设置查询参数
   params = {
       query: 搜索关键词,      # 必需参数：搜索文本
       tags: story,show_hn, # 可选：内容类型标签
       page: 0,                # 可选：页码，从0开始
       hitsPerPage: 20,        # 可选：每页结果数，默认20
       numericFilters: [      # 可选：数值过滤器
           created_at_i > timestamp  # 时间过滤
       ]
   }

4. 发送 GET 请求
   curl -X GET "https://hn.algolia.com/api/v1/search?query=Rust&tags=story&page=0&hitsPerPage=10"

5. 解析响应数据
   - hits: 结果数组，每个结果包含标题、URL、作者、分数等
   - nbHits: 总结果数
   - page: 当前页码
   - nbPages: 总页数

**注意事项：**

- API 返回格式为 JSON
- 无需 API Key 或认证
- 默认按相关性排序
- 可使用 tags 参数过滤内容类型：story（文章）、comment（评论）、poll（投票）、show_hn（Show HN）

### 操作2：按时间范围搜索

**执行步骤：**

1. 计算时间戳
   - 获取当前时间戳（秒级）
   - 计算过去 24 小时的时间戳：current_timestamp - 86400

2. 构造时间过滤请求
   curl -X GET "https://hn.algolia.com/api/v1/search?query=AI&tags=story&numericFilters=created_at_i>$(($(date +%s)-86400))"

**注意事项：**

- 时间戳为 Unix 时间戳（秒级）
- created_at_i 为帖子的创建时间戳字段

### 操作3：获取最新 Show HN 帖子

**执行步骤：**

1. 构造 Show HN 搜索请求
   curl -X GET "https://hn.algolia.com/api/v1/search?tags=show_hn,story&page=0&hitsPerPage=20"

**注意事项：**

- show_hn 是 Hacker News 的一个标签，用于标识作者展示自己项目的帖子
- 可以获取最新发布的有趣项目和技术探索

## 实用示例

### 示例1：搜索 Rust 相关的最新文章

```bash
# 最近24小时的 Rust 文章
curl -X GET "https://hn.algolia.com/api/v1/search?query=Rust&tags=story&numericFilters=created_at_i>$(($(date +%s)-86400))"
```

### 示例2：获取最新的 Show HN 项目

```bash
# 最新20个 Show HN 项目
curl -X GET "https://hn.algolia.com/api/v1/search?tags=show_hn,story&page=0&hitsPerPage=20"
```

### 示例3：搜索特定技术栈

```bash
# 搜索 Go 语言相关内容
curl -X GET "https://hn.algolia.com/api/v1/search?query=Go&tags=story&page=0&hitsPerPage=10"
```

## 错误处理

### 常见错误及处理

1. **请求超时**
   - 增加超时时间
   - 检查网络连接
   - 稍后重试

2. **无结果返回**
   - 检查搜索关键词
   - 扩大时间范围
   - 尝试其他相关关键词

3. **API 限流**
   - 降低请求频率
   - 添加请求间隔
   - 使用更精确的查询减少返回数据量

## 最佳实践

1. **关键词选择**
   - 使用英文关键词获取更多结果
   - 尝试同义词和相关术语
   - 结合多个关键词使用 AND 逻辑

2. **结果筛选**
   - 优先查看分数（points）高的帖子
   - 关注评论数较多的讨论
   - 使用 tags 精确筛选内容类型

3. **时间管理**
   - 使用时间过滤器获取最新内容
   - 根据需要调整时间范围（1小时、24小时、7天）
   - 避免重复请求相同数据
