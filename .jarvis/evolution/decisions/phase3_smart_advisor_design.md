# 阶段3 - 智能顾问模块设计文档

**创建时间**：2026-02-01
**状态**：设计中

## 1. 模块概述

### 1.1 目标

构建智能顾问模块（`jarvis_smart_advisor`），整合现有的知识图谱、智能检索、架构分析、代码审查等能力，为用户提供：

1. **智能问答**：回答项目相关问题
2. **代码审查建议**：生成代码改进建议
3. **架构决策辅助**：提供架构设计建议
4. **最佳实践推荐**：推荐相关的规则和方法论

### 1.2 设计原则

- **整合现有能力**：复用已有模块，避免重复实现
- **轻量级实现**：不引入复杂的外部依赖
- **可扩展性**：支持后续能力扩展
- **高质量输出**：确保建议的准确性和实用性

## 2. 模块架构

### 2.1 目录结构

```text
src/jarvis/jarvis_smart_advisor/
├── __init__.py              # 模块入口
├── advisor.py               # 智能顾问主类
├── qa_engine.py             # 智能问答引擎
├── review_advisor.py        # 代码审查建议器
├── architecture_advisor.py  # 架构决策顾问
└── practice_recommender.py  # 最佳实践推荐器
```

### 2.2 核心类设计

#### SmartAdvisor（主类）

```python
class SmartAdvisor:
    """智能顾问主类

    整合各种顾问能力，提供统一的接口。
    """

    def __init__(self, project_dir: str = "."):
        self.project_dir = project_dir
        self.qa_engine = QAEngine(project_dir)
        self.review_advisor = ReviewAdvisor(project_dir)
        self.architecture_advisor = ArchitectureAdvisor(project_dir)
        self.practice_recommender = PracticeRecommender(project_dir)

    def ask(self, question: str) -> str:
        """智能问答"""
        return self.qa_engine.answer(question)

    def review_code(self, file_path: str) -> List[ReviewSuggestion]:
        """代码审查建议"""
        return self.review_advisor.review(file_path)

    def advise_architecture(self, context: str) -> List[ArchitectureSuggestion]:
        """架构决策建议"""
        return self.architecture_advisor.advise(context)

    def recommend_practices(self, task: str) -> List[Practice]:
        """最佳实践推荐"""
        return self.practice_recommender.recommend(task)
```

## 3. 智能问答引擎设计

### 3.1 问答流程

```text
用户问题 → 问题分析 → 知识检索 → 答案生成 → 返回答案
```

### 3.2 问题分析

1. **问题分类**：
   - 项目结构问题（"这个项目有哪些模块？"）
   - 代码功能问题（"这个函数是做什么的？"）
   - 最佳实践问题（"如何实现XXX？"）
   - 历史决策问题（"为什么选择这个方案？"）

2. **关键词提取**：提取问题中的关键实体（模块名、函数名、概念等）

3. **意图识别**：识别用户的查询意图

### 3.3 知识检索策略

1. **知识图谱检索**：
   - 根据关键词查询相关节点
   - 获取节点的邻居和相关知识
   - 查找知识路径

2. **记忆检索**：
   - 使用SmartRetriever进行语义检索
   - 获取相关的历史记忆

3. **代码检索**：
   - 搜索相关的代码文件
   - 读取代码内容

4. **规则/方法论检索**：
   - 查找相关的规则文件
   - 查找相关的方法论

### 3.4 答案生成

1. **上下文组装**：将检索到的知识组装成上下文
2. **答案生成**：基于上下文生成答案（可选择使用LLM或模板）
3. **来源标注**：标注答案的知识来源

### 3.5 核心数据结构

```python
@dataclass
class Question:
    """问题数据类"""
    text: str                    # 问题文本
    category: str                # 问题类别
    keywords: List[str]          # 关键词
    intent: str                  # 意图
    entities: List[str]          # 实体

@dataclass
class Answer:
    """答案数据类"""
    text: str                    # 答案文本
    confidence: float            # 置信度
    sources: List[str]           # 知识来源
    related_knowledge: List[str] # 相关知识
```

## 4. 代码审查建议器设计

### 4.1 审查流程

```text
代码文件 → 代码分析 → 问题检测 → 建议生成 → 返回建议
```

### 4.2 分析维度

1. **复杂度分析**：使用jarvis_arch_analyzer
2. **代码风格**：使用静态分析工具（ruff、mypy）
3. **最佳实践**：对比规则库
4. **历史问题**：检索类似代码的历史问题

### 4.3 建议数据结构

```python
@dataclass
class ReviewSuggestion:
    """审查建议数据类"""
    file_path: str               # 文件路径
    line_range: Tuple[int, int]  # 行号范围
    category: str                # 建议类别
    severity: str                # 严重程度（info/warning/error）
    message: str                 # 建议内容
    suggestion: str              # 改进建议
    reference: Optional[str]     # 参考规则/最佳实践
```

## 5. 架构决策顾问设计

### 5.1 决策流程

```text
决策上下文 → 历史决策检索 → 方案分析 → 建议生成 → 返回建议
```

### 5.2 决策维度

1. **技术选型**：推荐技术栈
2. **架构模式**：推荐设计模式
3. **模块划分**：建议模块结构
4. **风险评估**：评估潜在风险

### 5.3 建议数据结构

```python
@dataclass
class ArchitectureSuggestion:
    """架构建议数据类"""
    category: str                # 建议类别
    suggestion: str              # 建议内容
    rationale: str               # 理由
    pros: List[str]              # 优点
    cons: List[str]              # 缺点
    references: List[str]        # 参考资料
    confidence: float            # 置信度
```

## 6. 最佳实践推荐器设计

### 6.1 推荐流程

```text
任务描述 → 任务分析 → 实践检索 → 排序过滤 → 返回推荐
```

### 6.2 推荐来源

1. **规则库**：`.jarvis/rules/` + `builtin/rules/`
2. **方法论库**：`.jarvis/methodologies/`
3. **知识图谱**：相关的最佳实践节点
4. **历史记忆**：成功案例的记忆

### 6.3 推荐数据结构

```python
@dataclass
class Practice:
    """最佳实践数据类"""
    name: str                    # 实践名称
    description: str             # 描述
    source_type: str             # 来源类型（rule/methodology/memory）
    source_path: Optional[str]   # 来源路径
    relevance: float             # 相关性得分
    tags: List[str]              # 标签
```

## 7. 实现计划

### Phase 1: 基础框架（任务1.3）

- 创建模块目录结构
- 实现SmartAdvisor主类
- 实现基础数据结构

### Phase 2: 智能问答（任务1.3续）

- 实现QAEngine
- 集成知识图谱检索
- 集成智能检索

### Phase 3: 代码审查建议（任务2.3）

- 实现ReviewAdvisor
- 集成架构分析
- 集成静态分析

### Phase 4: 架构决策辅助（任务3.3）

- 实现ArchitectureAdvisor
- 集成历史决策检索

### Phase 5: 最佳实践推荐（任务4.3）

- 实现PracticeRecommender
- 集成规则和方法论系统

### Phase 6: 集成测试（任务5）

- 单元测试
- 集成测试
- 验收测试

## 8. 验收标准

1. **智能问答**：能回答项目相关问题，准确率≥80%
2. **代码审查建议**：建议有价值，采纳率≥70%
3. **架构决策辅助**：能提供有效的架构建议
4. **最佳实践推荐**：推荐相关性高
5. **测试覆盖率**：≥80%

## 9. 依赖模块

- `jarvis_knowledge_graph`: 知识图谱
- `jarvis_memory_organizer.smart_retrieval`: 智能检索
- `jarvis_arch_analyzer`: 架构分析
- `jarvis_code_analysis`: 代码审查
- `jarvis_rule_generator`: 规则系统
- `jarvis_methodology_generator`: 方法论系统
