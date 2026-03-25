# Data Agent 项目架构分析与优化方案

## 1. 项目概述

本项目是一个基于LangGraph框架构建的多智能体数据分析系统，支持数据检索、分析建模、可视化和报告生成等功能。

## 2. 现有架构分析

### 2.1 核心组件

#### 2.1.1 智能体 (Agents)

| Agent名称 | 功能描述 | 输入 | 输出 | 使用工具 |
|-----------|---------|------|------|---------|
| **IntentRecognitionAgent** | 识别用户意图类型 | 用户问题 | 意图类型(SMALLTALK/ASK_DATA/ANALYSIS_MODELING/VISUALIZATION/REPORT) + 置信度 | 意图识别提示模板 |
| **SmallTalkAgent** | 处理闲聊类问题 | 用户问题 | 闲聊回复 | 闲聊提示模板 |
| **PlanAgent** | 生成和执行计划 | 用户问题+检索信息 | 结构化计划+步骤执行 | 子Agent转移工具+RAG检索 |
| **SearchAgent** | 数据检索 | 数据查询请求 | 检索到的数据 | 数据文件读取工具+Python执行+MCP服务 |
| **AnalysisAgent** | 数据分析建模 | 数据+分析指令 | 分析结果+生成代码 | Python执行+AutoSTAT工具 |
| **VisualizationAgent** | 数据可视化 | 数据+可视化指令 | 图表+生成代码 | Python执行(matplotlib/plotly) |
| **ReportAgent** | 报告生成 | 分析结果+可视化 | 完整报告 | 报告模板 |
| **GenerateAgent** | 内容生成 | 生成请求 | 生成内容 | 生成提示模板 |
| **ManageAgent** | 管理功能 | 管理请求 | 管理操作结果 | 管理工具 |
| **KnowledgeAgent** | 知识库问答 | 知识查询 | 知识回答 | RAG知识库 |

#### 2.1.2 状态管理 (States)

- **PlanState**: 主流程状态，包含：
  - 用户问题、历史消息、当前计划
  - 执行步骤、意图信息
  - 各Agent的标准输出结果
  - 报告生成工作流状态

- **StepState**: 单步执行状态

#### 2.1.3 工作流构建 (Graph Builder)

**现有流程图**:

```
START
  │
  ▼
intent_recognition_agent
  │
  ├──→ SMALLTALK ──→ small_talk_agent ──→ __end__
  │
  ├──→ REPORT ──→ report_workflow_router
  │                     │
  │                     ├─→ start_report_workflow
  │                     │         │
  │                     │         ▼
  │                     │    plan_report_requirements
  │                     │         │
  │                     │         ▼
  │                     │    analysis_agent
  │                     │         │
  │                     │         ▼
  │                     │    after_analysis_router
  │                     │         │
  │                     │         ▼
  │                     │    visualization_agent
  │                     │         │
  │                     │         ▼
  │                     │    after_visualization_router
  │                     │         │
  │                     │         ▼
  │                     │    report_agent ──→ __end__
  │
  └──→ 其他 ──→ plan_agent
                      │
                      ├─ 生成初始计划
                      │      │
                      │      ├─ 有问题需确认 ──→ ask_user
                      │      │                        │
                      │      │                        ▼
                      │      │                  plan_agent (继续)
                      │      │
                      │      ▼
                      │  执行步骤循环
                      │      │
                      │      ├─ 执行当前步骤
                      │      │      │
                      │      │      ▼
                      │      │  transfer_to_{agent}
                      │      │
                      │      ├─ 还有步骤 ──→ plan_agent (need_replan=False)
                      │      │
                      │      └─ 无更多步骤 ──→ 决策：生成报告或直接结束
                      │                          │
                      │                          ├─ 生成报告 ──→ report_agent ──→ __end__
                      │                          │
                      │                          └─ 直接结束 ──→ __end__
                      │
                      └─ 重新计划 (need_replan=True)
                               │
                               ▼
                         plan_agent (replan)
```

### 2.2 现有问题识别

#### 2.2.1 意图识别模块问题
1. 意图识别准确率依赖LLM输出格式，缺乏验证和纠错机制
2. 没有意图分类的训练/测试数据
3. 置信度评估较为简单

#### 2.2.2 计划生成与执行问题
1. PlanAgent虽然有计划生成功能，但缺乏严格的步骤执行跟踪
2. 没有标准化的JSON输出格式记录每个步骤的执行信息
3. 动态调整机制不够完善

#### 2.2.3 代码处理问题
1. 生成的Python代码没有自动整理成可执行的.py文件
2. 前端没有Python沙盒执行区域

#### 2.2.4 工作流问题
1. graph builder中一些节点链路不够清晰
2. 缺少完整的执行状态跟踪

## 3. 优化方案

### 3.1 架构改进要点

1. **增强意图识别**: 添加意图验证、多级分类、置信度阈值
2. **完善计划执行**: 标准化JSON输出、详细执行跟踪
3. **代码沙盒**: 自动保存代码、前端执行环境
4. **优化graph结构**: 更清晰的节点和边
5. **决策终止流程**: 完善结果综合展示

### 3.2 具体改进

详见后续实施步骤。

---

## 附录：Agent详细分析

### IntentRecognitionAgent
- **实现位置**: `src/agents/intent_recognition_agent.py`
- **当前问题**: JSON解析可能失败，缺少意图验证
- **优化方向**: 添加更多意图类型、增强验证、提高准确率

### PlanAgent
- **实现位置**: `src/agents/plan_agent.py`
- **当前问题**: 步骤执行跟踪不够详细，无标准JSON输出
- **优化方向**: 添加步骤执行引擎、标准输出格式、动态调整

### 其他Agent
- 基本功能完善，但需要统一输出格式
