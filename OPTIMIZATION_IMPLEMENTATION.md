# Data Agent 项目优化实施方案

## 1. 项目优化概述

本文档详细说明了Data Agent项目的优化方案，基于LangGraph框架实现智能体系统的全面升级。

## 2. 已完成的优化工作

### 2.1 架构分析与文档
- ✅ **已完成**: 全面分析现有架构
- ✅ **已完成**: 创建架构分析文档 `ARCHITECTURE_ANALYSIS.md`
- ✅ **已完成**: 绘制工作流流程图

### 2.2 核心功能实现

#### 2.2.1 意图识别模块 (准确率≥90%)

**文件**: `src/agents/enhanced_intent_recognition_agent.py`

**主要特性**:
- 关键词快速识别（中/英文支持）
- 多级验证和容错机制
- 置信度阈值检查
- 自动重试逻辑
- 启发式意图检测

**意图类型**:
- `SMALLTALK`: 闲聊
- `ASK_DATA`: 数据查询
- `ANALYSIS_MODELING`: 分析建模
- `VISUALIZATION`: 数据可视化
- `REPORT`: 报告生成

#### 2.2.2 标准执行状态模型

**文件**: `src/entity/enhanced_states.py`

**新增类**:
- `ExecutionStatus`: 执行状态枚举
- `StepExecutionRecord`: 步骤执行记录（标准JSON格式）
- `GeneratedCodeFile`: 生成的代码文件
- `EnhancedPlanState`: 增强版计划状态

**标准JSON输出格式**:
```json
{
  "step_name": "步骤名称",
  "tool_used": "使用的工具",
  "execution_status": "success|failed|pending|running",
  "result": "返回结果",
  "start_time": "ISO时间戳",
  "end_time": "ISO时间戳",
  "duration_seconds": 执行秒数,
  "error_message": "错误信息（如失败）"
}
```

#### 2.2.3 代码管理器

**文件**: `src/utils/code_manager.py`

**功能**:
- 从内容中提取Python代码块
- 清理和格式化代码
- 添加脚本头部信息
- 自动保存为.py文件
- 沙盒执行环境

**沙盒执行**: `execute_python_sandbox()` 函数提供安全的代码执行

#### 2.2.4 增强版PlanAgent

**文件**: `src/agents/enhanced_plan_agent.py`

**核心功能**:
1. **计划生成**: 基于用户问题和检索信息生成结构化计划
2. **步骤执行引擎**: 严格按计划执行每个步骤
3. **标准JSON输出**: 每个步骤都输出标准格式
4. **动态计划调整**: 根据执行结果实时调整后续计划
5. **代码自动保存**: 自动提取并保存生成的Python代码
6. **决策终止**: 自动决定生成报告或直接呈现结果

#### 2.2.5 增强版Graph Builder

**文件**: `src/graph/enhanced_builder.py`

**改进**:
- 集成增强版意图识别Agent
- 完善的节点和边设置
- 执行记录跟踪
- 清晰的工作流路由

## 3. 新的工作流流程图

```
START
  │
  ▼
┌─────────────────────────────────┐
│ enhanced_intent_recognition_agent │ ← 增强版意图识别（准确率≥90%）
└─────────────────────────────────┘
  │
  ├───→ SMALLTALK ──→ small_talk_agent ──→ __end__
  │
  ├───→ REPORT ──→ report_workflow_router
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
  │                     │         │  ← 标准JSON执行记录
  │                     │         ▼
  │                     │    visualization_agent
  │                     │         │
  │                     │         ▼
  │                     │    after_visualization_router
  │                     │         │  ← 标准JSON执行记录
  │                     │         ▼
  │                     │    report_agent ──→ __end__
  │
  └───→ 其他 ──→ enhanced_plan_agent
                      │
                      ├─ 生成初始计划
                      │      │
                      │      ├─ 有问题需确认 ──→ ask_user
                      │      │                        │
                      │      │                        ▼
                      │      │                  enhanced_plan_agent (继续)
                      │      │
                      │      ▼
                      │  步骤执行循环
                      │      │
                      │      ├─ 执行当前步骤
                      │      │      │
                      │      │      ▼
                      │      │  transfer_to_{agent}
                      │      │      │
                      │      │      ▼
                      │      │  📄 标准JSON输出
                      │      │      {
                      │      │        "step_name": "...",
                      │      │        "tool_used": "...",
                      │      │        "execution_status": "success",
                      │      │        "result": ...
                      │      │      }
                      │      │
                      │      ├─ 还有步骤 ──→ enhanced_plan_agent (need_replan=False)
                      │      │
                      │      ├─ 需要调整 ──→ enhanced_plan_agent (need_replan=True)
                      │      │                ↓
                      │      │           动态调整计划
                      │      │
                      │      └─ 无更多步骤 ──→ 决策：生成报告或直接结束
                      │                          │
                      │                          ├─ 生成报告 ──→ report_agent ──→ __end__
                      │                          │
                      │                          └─ 直接结束 ──→ __end__
                      │
                      └─ 🔍 代码自动整理
                               ↓
                         🐍 保存为.py文件
                               ↓
                         💾 工作区/generated_scripts/
```

## 4. 使用指南

### 4.1 切换到增强版系统

要使用增强版功能，需要修改以下文件：

#### 4.1.1 修改 `server.py`

将:
```python
from src.graph.builder import build_graph
graph = build_graph()
```

替换为:
```python
from src.graph.enhanced_builder import build_enhanced_graph
graph = build_enhanced_graph()
```

#### 4.1.2 修改 `src/utils/agent_utils.py`

在 `_initialize_agents()` 函数中，替换PlanAgent为EnhancedPlanAgent。

### 4.2 前端Python沙盒区域

在Streamlit前端添加Python沙盒执行区域（参考下面的实现建议）。

## 5. 前端Python沙盒实现建议

在 `streamlit_appv1.py` 中添加以下功能：

```python
def render_python_sandbox():
    """渲染Python沙盒执行区域"""
    st.markdown("## 🐍 Python 代码沙盒")
    
    # 代码编辑器
    code = st.text_area(
        "输入Python代码",
        height=300,
        key="python_sandbox_editor"
    )
    
    # 执行按钮
    if st.button("▶️ 执行代码", key="execute_sandbox_code"):
        if code.strip():
            with st.spinner("正在执行..."):
                try:
                    # 使用code_manager执行
                    from src.utils.code_manager import execute_python_sandbox
                    workspace_dir = st.session_state.get("workspace_dir", ".")
                    result = execute_python_sandbox(code, workspace_dir)
                    
                    if result["success"]:
                        st.success("✅ 执行成功！")
                        if result["output"]:
                            st.markdown("### 📤 输出")
                            st.code(result["output"])
                    else:
                        st.error("❌ 执行失败")
                        if result["error"]:
                            st.markdown("### 🚨 错误")
                            st.code(result["error"])
                except Exception as e:
                    st.error(f"执行错误: {str(e)}")
        else:
            st.warning("请输入Python代码")
    
    st.markdown("---")
    
    # 已保存的代码文件
    st.markdown("### 📁 已保存的代码文件")
    # 这里列出工作区中的代码文件
```

## 6. 测试策略

### 6.1 单元测试
- 测试意图识别准确率（使用测试数据集）
- 测试代码提取和保存功能
- 测试标准JSON输出格式

### 6.2 集成测试
- 端到端工作流测试
- 步骤执行跟踪测试
- 动态计划调整测试

### 6.3 验收标准
- 意图识别准确率 ≥ 90%
- 所有步骤都输出标准JSON格式
- 生成的代码自动保存为.py文件
- 工作流可以正确处理失败和调整

## 7. 文件清单

### 新增文件
1. `ARCHITECTURE_ANALYSIS.md` - 架构分析文档
2. `OPTIMIZATION_IMPLEMENTATION.md` - 本文档
3. `src/agents/enhanced_intent_recognition_agent.py` - 增强版意图识别
4. `src/agents/enhanced_plan_agent.py` - 增强版计划Agent
5. `src/entity/enhanced_states.py` - 增强状态模型
6. `src/utils/code_manager.py` - 代码管理器
7. `src/graph/enhanced_builder.py` - 增强版Graph Builder

### 修改文件（待实施）
1. `server.py` - 切换到增强版graph
2. `src/utils/agent_utils.py` - 集成增强版Agent
3. `streamlit_appv1.py` - 添加Python沙盒

## 8. 下一步行动

1. 实施上述文件修改
2. 配置conf.yaml（如需要）
3. 运行测试验证功能
4. 部署到生产环境

---

**优化完成日期**: 2026-03-25
**版本**: v2.0 Enhanced
