# 修复重复步骤和空输出问题 - Product Requirement Document

## Overview
- **Summary**: 修复数据代理系统中存在的两个关键问题：1) 执行过程中步骤无限重复；2) 每个步骤的输出只显示固定文案，不包含真实计算结果。
- **Purpose**: 确保系统能够按计划顺序执行步骤，并在每个步骤完成后正确展示计算结果，提高用户体验和系统可靠性。
- **Target Users**: 使用数据代理系统进行数据分析的用户和开发者

## Goals
- 修复步骤重复执行的问题，确保每个步骤只执行一次
- 修复 AnalysisAgent 和 VisualizationAgent 输出为空的问题
- 确保每个步骤的 output 字段都包含真实的计算结果
- 确保系统有明确的终止条件

## Non-Goals (Out of Scope)
- 不重构整个系统架构
- 不添加新的分析功能
- 不修改前端界面（除非后端输出格式需要）

## Background & Context
根据日志输出分析，系统存在以下问题：
1. **步骤重复执行**: 每次执行完一个步骤后，系统会重新回到 plan_agent，并且重复发送之前的步骤完成消息
2. **无计算结果**: AnalysisAgent 的 insights 被硬编码为 ["Analysis completed successfully"]，execution_result 也没有正确保存真实结果

## Functional Requirements
- **FR-1**: 确保每个步骤只执行一次，不会无限重复
- **FR-2**: AnalysisAgent 必须正确保存和返回真实的计算结果
- **FR-3**: VisualizationAgent 必须正确保存和返回图表信息
- **FR-4**: 确保系统在所有步骤完成后能够正确终止
- **FR-5**: 每个步骤的 output 字段都必须包含该步骤的计算结果

## Non-Functional Requirements
- **NFR-1**: 修复后系统执行流程必须清晰可见
- **NFR-2**: 计算结果必须以可解析的格式展示
- **NFR-3**: 修复不能影响系统的其他功能

## Constraints
- **Technical**: 必须在现有 LangGraph 框架基础上修复
- **Business**: 需要保持与现有前端界面的兼容性
- **Dependencies**: 依赖现有的 states.py、output_utils.py 等模块

## Assumptions
- SearchAgent 已经正确返回结果，无需修改
- 系统的状态管理机制（MemorySaver）工作正常
- 现有日志系统可以正常记录执行过程

## Acceptance Criteria

### AC-1: 步骤不重复执行
- **Given**: 用户提交一个数据分析请求
- **When**: 系统生成执行计划并开始执行
- **Then**: 每个步骤只执行一次，不会无限循环
- **Verification**: `programmatic`
- **Notes**: 检查日志中每个步骤的执行记录是否唯一

### AC-2: AnalysisAgent 返回真实计算结果
- **Given**: AnalysisAgent 执行了数据分析任务
- **When**: 步骤执行完成
- **Then**: insights 字段包含从结果中提取的关键信息，execution_result 包含完整的计算结果
- **Verification**: `programmatic`
- **Notes**: 检查返回的 AnalysisResult 对象是否包含真实数据

### AC-3: VisualizationAgent 返回图表信息
- **Given**: VisualizationAgent 执行了可视化任务
- **When**: 步骤执行完成
- **Then**: chart_path 和 chart_title 等字段包含真实的图表信息
- **Verification**: `programmatic`
- **Notes**: 检查返回的 VisualizationResult 对象是否包含真实图表信息

### AC-4: 系统正确终止
- **Given**: 所有计划步骤都已执行完成
- **When**: 最后一个步骤执行完毕
- **Then**: 系统正确终止，不会继续循环
- **Verification**: `programmatic`
- **Notes**: 检查执行流程是否正常结束

### AC-5: Output 包含计算结果
- **Given**: 任意一个执行步骤完成
- **When**: 查看该步骤的输出
- **Then**: output 字段包含该步骤的真实计算结果，而不是固定文案
- **Verification**: `human-judgment`
- **Notes**: 需要人工验证输出内容的可读性和正确性

## Open Questions
- [ ] 是否需要修改其他 Agent（如 ManageAgent、KnowledgeAgent）的输出逻辑？
- [ ] 前端界面是否需要调整来适配新的输出格式？
