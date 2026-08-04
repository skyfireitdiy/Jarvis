---
name: hacker_news_search
description: 当需要搜索Hacker News内容时触发。每当用户提及"Hacker News"、"HN搜索"、"科技新闻"时触发。不触发：通用网页搜索；代码搜索；非Hacker News的新闻来源。
---
# Hacker News 搜索规则

## 规则简介

本规则用于指导如何用 Hacker News Algolia API 搜索最新之技术资讯与讨论。

## 汝必遵守之原则

### API 使用原则

**要求说明：**

- **必**：用 HTTPS 协议访问 API
- **必**：合理设置请求参数，避不必要之网络请求
- **必**：处理 API 错误响应，含超时与无效请求
- **禁**：于短时间内发送大量请求，避被限流
- **禁**：缓存敏感数据，如用户信息
**性能优化：**
- 适当用分页参数（page 与 hitsPerPage）控制返回结果数量
- 用时间过滤器（numericFilters）获取最新内容
- 避重复请求相同之数据

## 汝必执行之操作

### 操作1：获取 Hacker News 搜索结果

**执行步骤：**

1. 定 API 基础 URL：<https://hn.algolia.com/api/v1>
2. 构搜索请求
   - 基础端点：/search
   - 完整 URL：<https://hn.algolia.com/api/v1/search>
3. 设查询参数
   params = {
   query: 搜索关键词, # 必需参数：搜索文本
   tags: story,show_hn, # 可选：内容类型标签
   page: 0, # 可选：页码，从0开始
   hitsPerPage: 20, # 可选：每页结果数，默认20
   numericFilters: [ # 可选：数值过滤器
   created_at_i > timestamp # 时间过滤
   ]
   }
4. 发 GET 请求
   curl -X GET "<https://hn.algolia.com/api/v1/search?query=Rust&tags=story&page=0&hitsPerPage=10>"
5. 解析响应数据
   - hits: 结果数组，每个结果含标题、URL、作者、分数等
   - nbHits: 总结果数
   - page: 当前页码
   - nbPages: 总页数
**注意事项：**

- API 返回格式为 JSON
- 无需 API Key 或认证
- 默认按相关性排序
- 可用 tags 参数过滤内容类型：story（文章）、comment（评论）、poll（投票）、show_hn（Show HN）

### 操作2：按时间范围搜索

**执行步骤：**

1. 计算时间戳
   - 获取当前时间戳（秒级）
   - 计算过去 24 小时之时间戳：current_timestamp - 86400
2. 构时间过滤请求
   curl -X GET "<https://hn.algolia.com/api/v1/search?query=AI&tags=story&numericFilters=created_at_i>$(($(date +%s)-86400))"
**注意事项：**

- 时间戳为 Unix 时间戳（秒级）
- created_at_i 为帖子之创建时间戳字段

### 操作3：获取最新 Show HN 帖子

**执行步骤：**

1. 构 Show HN 搜索请求
   curl -X GET "<https://hn.algolia.com/api/v1/search?tags=show_hn,story&page=0&hitsPerPage=20>"
**注意事项：**

- show_hn 为 Hacker News 之一标签，用于标识作者展示自己项目之帖子
- 可获取最新发布之有趣项目与技术探索

## 实用示例

### 示例1：搜索 Rust 相关之最新文章

```bash
# 最近24小时之 Rust 文章
curl -X GET "https://hn.algolia.com/api/v1/search?query=Rust&tags=story&numericFilters=created_at_i>$(($(date +%s)-86400))"
```

### 示例2：获取最新之 Show HN 项目

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
   - 增超时时间
   - 查网络连接
   - 稍后重试
2. **无结果返回**
   - 查搜索关键词
   - 扩时间范围
   - 试其他相关关键词
3. **API 限流**
   - 降请求频率
   - 添请求间隔
   - 用更精确之查询减返回数据量

## 最佳实践

1. **关键词选择**
   - 用英文关键词获取更多结果
   - 试同义词与相关术语
   - 结合多个关键词用 AND 逻辑
2. **结果筛选**
   - 优先查看分数（points）高之帖子
   - 关注评论数较多之讨论
   - 用 tags 精确筛选内容类型
3. **时间管理**
   - 用时间过滤器获取最新内容
   - 按需调整时间范围（1小时、24小时、7天）
   - 避重复请求相同数据
