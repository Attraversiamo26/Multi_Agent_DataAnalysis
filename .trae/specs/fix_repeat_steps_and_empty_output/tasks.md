# 修复重复步骤和空输出问题 - The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: 修复 AnalysisAgent 输出没有计算结果的问题
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改 AnalysisAgent，让它从 results 中提取真实的计算结果
  - 收集所有有意义的工具调用结果（跳过 terminate 工具）
  - 从结果中提取关键统计信息（如 row_count、column_count、total_routes 等）作为 insights
  - 将完整的计算结果保存到 execution_result 字段中
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: AnalysisResult 对象的 execution_result 字段不为空
  - `programmatic` TR-1.2: AnalysisResult 对象的 insights 字段包含从结果中提取的信息
  - `human-judgement` TR-1.3: 输出结果包含真实的计算数据，而不是固定文案
- **Notes**: 需要修改 src/agents/analysis_agent.py

## [x] Task 2: 修复 VisualizationAgent 输出没有图表信息的问题
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改 VisualizationAgent，让它从 results 中提取图表信息
  - 提取 chart_path 和 title 并保存到 VisualizationResult 中
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: VisualizationResult 对象的 chart_path 字段包含真实的图表路径
  - `programmatic` TR-2.2: VisualizationResult 对象的 chart_title 字段包含真实的图表标题
  - `human-judgement` TR-2.3: 输出结果包含真实的图表信息
- **Notes**: 需要修改 src/agents/visualization_agent.py

## [x] Task 3: 修复步骤重复消息的问题
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 修改 enhanced_plan_agent.py，避免每次返回 plan_agent 时都重复发送开始执行消息
  - 将 "🚀 开始执行计划..." 消息的发送移到只在第一次生成计划时执行
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-3.1: 检查日志中开始执行消息只出现一次
  - `human-judgement` TR-3.2: 前端界面中开始执行消息不会重复显示
- **Notes**: 需要修改 src/agents/enhanced_plan_agent.py

## [ ] Task 4: 验证系统能够正确终止
- **Priority**: P1
- **Depends On**: Task 1, Task 2, Task 3
- **Description**: 
  - 验证当所有步骤执行完成后，系统能够正确终止
  - 检查 enhanced_plan_agent.py 中的终止逻辑是否正确
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: 验证执行流程在所有步骤完成后正常结束
  - `human-judgement` TR-4.2: 验证不会出现无限循环
- **Notes**: 可能需要通过实际测试来验证

## [x] Task 5: 综合测试所有修复
- **Priority**: P1
- **Depends On**: Task 1, Task 2, Task 3, Task 4
- **Description**: 
  - 运行完整的测试用例，验证所有修复都正常工作
  - 检查每个步骤的输出都包含真实结果
  - 检查步骤不会重复执行
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: 所有测试用例通过
  - `human-judgement` TR-5.2: 人工验证输出结果的正确性和可读性
- **Notes**: 需要准备测试数据和测试用例
