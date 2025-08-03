# jarvis_stats 模块测试说明

本目录包含 jarvis_stats 模块的完整测试套件。

## 测试文件结构

- `test_stats.py` - StatsManager 类的单元测试
- `test_storage.py` - StatsStorage 类的单元测试  
- `test_visualizer.py` - StatsVisualizer 类的单元测试
- `test_integration.py` - 模块集成测试

## 运行测试

### 运行所有测试
```bash
pytest tests/jarvis_stats/
```

### 运行特定测试文件
```bash
pytest tests/jarvis_stats/test_stats.py
```

### 运行特定测试类或方法
```bash
pytest tests/jarvis_stats/test_stats.py::TestStatsManager::test_increment_basic
```

### 查看测试覆盖率
```bash
pytest tests/jarvis_stats/ --cov=jarvis.jarvis_stats --cov-report=html
```

## 测试覆盖范围

### StatsManager 测试
- 初始化和配置
- 增加计数（基本、带标签、带分组、带单位）
- 数据查询（时间范围、标签过滤、聚合）
- 数据显示（表格、图表、摘要）
- 数据导出和导入
- 并发操作
- 错误处理

### StatsStorage 测试
- 存储初始化
- 数据添加和读取
- 标签过滤
- 时间范围查询
- 数据聚合（按小时、按天）
- 数据清除
- 数据导出导入
- 并发写入
- 文件损坏恢复

### StatsVisualizer 测试
- 折线图绘制
- 柱状图绘制
- 表格显示
- 摘要显示
- 空数据处理
- 终端兼容性
- 错误处理

### 集成测试
- 完整工作流程
- 数据持久化
- 可视化集成
- 导出导入工作流
- 多指标分析
- 大数据集性能
- 并发操作
- 边界情况

## 注意事项

1. 测试使用临时目录，不会影响实际数据
2. 可视化相关测试使用了 mock，不需要实际的终端环境
3. 测试会自动清理创建的临时文件和目录
