# 用户问题处理流程完整文档

## 概述
本文档系统性地梳理了从用户问题提交到最终响应交付的完整流程，包含所有流程节点、状态转换、前端展示内容、后端处理逻辑、代码调用位置和使用模板。

---

## 完整流程文档表格

| 流程节点 | 状态描述 | 前端展示内容 | 后端处理逻辑 | 代码调用位置 | 使用模板 | 目的/功能 | 返回结果 |
|---------|---------|------------|------------|------------|---------|---------|---------|
| **1. 用户输入** | 用户在前端界面提交问题 | 前端聊天界面输入框 | 接收用户输入 | `streamlit_appv1.py` | 无 | 接收用户问题 | 用户问题文本 |
| **2. 前端发送请求** | 前端通过 API 发送请求到后端 | 无（后台处理） | 调用 DataAgentClient.get_assistant_response() | `streamlit_appv1.py:DataAgentClient` | 无 | 向后端发送用户问题 | SSE 流式响应 |
| **3. 后端接收请求** | 服务器接收并初始化工作流 | 无（后台处理） | 创建会话工作区，初始化状态，调用 graph.astream() | `server.py:400-463` | 无 | 初始化后端工作流 | 初始化的 PlanState |
| **4. START 节点** | 工作流开始 | 无（后台处理） | LangGraph 框架内部处理 | `enhanced_builder.py:251` | 无 | 启动工作流 | 路由到 intent_recognition_agent |
| **5. 增强版意图识别** | 识别用户意图类型 | 💭 执行过程折叠框 → 1. 意图识别 | 调用 EnhancedIntentRecognitionAgent.run() | `enhanced_intent_recognition_agent.py:210-282` | `intent_recognition_agent.md` | 识别用户问题意图 | intent_type, intent_confidence, intent |
| **6. 意图路由** | 根据意图类型路由 | 💭 执行过程折叠框 | 检查 intent_type，决定下一个节点 | `enhanced_builder.py:39-51` | 无 | 路由到正确的 Agent | 路由决策 |
| **7. SMALLTALK 路由** | 闲聊意图处理 | 📊 结果返回 | 调用 small_talk_agent | `enhanced_builder.py:45-46` | `small_talk_agent.md` | 处理闲聊问题 | 闲聊回复 |
| **8. REPORT 路由** | 报告意图处理 | 💭 执行过程折叠框 | 路由到 report_workflow_router | `enhanced_builder.py:47-48` | 无 | 启动报告流程 | 路由到 report_workflow_router |
| **9. 其他意图路由** | 数据/分析/可视化意图 | 💭 执行过程折叠框 | 路由到 plan_agent | `enhanced_builder.py:50-51` | 无 | 进入计划执行 | 路由到 plan_agent |
| **10. 计划 Agent 运行** | 执行计划生成和步骤执行 | 💭 执行过程折叠框 + 📊 结果返回 | 调用 EnhancedPlanAgent.run() | `enhanced_plan_agent.py:362-761` | `plan_agent.md` | 生成计划并执行 | 完整执行结果 |
| **11. 生成初始计划** | LLM 生成执行计划 | 💭 执行过程折叠框 | 调用 _generate_initial_plan() | `enhanced_plan_agent.py:433-475` | `plan_agent.md` | 生成执行计划 | Plan 对象 |
| **12. 发送计划消息** | 发送计划相关消息 | 💭 执行过程折叠框 | 多次调用 push_message() | `enhanced_plan_agent.py:414-471` | 无 | 通知用户计划进度 | 多条消息 |
| **13. 发送计划 JSON** | 发送完整计划 JSON | 💭 执行过程折叠框 → 2. 执行步骤 | push_message() 发送 ```json``` | `enhanced_plan_agent.py:468-471` | 无 | 发送完整计划 | Plan JSON |
| **14. 步骤执行循环** | 执行单个步骤 | 💭 执行过程折叠框 | 调用 _execute_single_step() | `enhanced_plan_agent.py:501-503` | 无 | 执行步骤 | execution_record, step_result |
| **15. 发送步骤开始消息** | 通知步骤开始 | 💭 执行过程折叠框 | push_message() 发送开始通知 | `enhanced_plan_agent.py:150-153` | 无 | 通知步骤开始 | 步骤开始消息 |
| **16. 调用 Handoff 工具** | 调用目标 Agent | 💭 执行过程折叠框 | 调用 tool.ainvoke() | `enhanced_plan_agent.py:163-169` | `agent_utils.py:42-63` | 执行具体任务 | Agent 结果 |
| **17. 处理 Agent 结果** | 解析返回结果 | 💭 执行过程折叠框 | 调用 _process_agent_result() | `enhanced_plan_agent.py:183` | 无 | 处理结果 | action_res, results |
| **18. 创建执行记录** | 生成标准执行记录 | 💭 执行过程折叠框 → 3. 执行过程 | 调用 _create_step_execution_record() | `enhanced_plan_agent.py:70-88,210-215` | 无 | 生成执行记录 | StepExecutionRecord |
| **19. 发送执行记录 JSON** | 发送标准 JSON | 💭 执行过程折叠框 → 3. 执行过程 | push_message() 发送 JSON | `enhanced_plan_agent.py:231-234` | 无 | 发送执行记录 | StepExecutionRecord JSON |
| **20. 发送步骤完成消息** | 通知步骤完成 | 💭 执行过程折叠框 | push_message() 发送完成通知 | `enhanced_plan_agent.py:225-228` | 无 | 通知完成 | 步骤完成消息 |
| **21. 更新 PlanState** | 更新状态 | 💭 执行过程折叠框（后台） | 调用 PlanState.add_execution_record() | `enhanced_plan_agent.py:512` | `states.py:256-261` | 添加执行记录 | 更新的 state |
| **22. 保存代码文件** | 保存生成的代码 | 💭 执行过程折叠框（后台） | 调用 PlanState.add_generated_code() | `enhanced_plan_agent.py:529` | `states.py:263-268` | 保存代码文件 | 更新的 state |
| **23. 检查更多步骤** | 决定是否继续 | 💭 执行过程折叠框（后台） | 比较 executed_steps 和 plan.steps | `enhanced_plan_agent.py:541` | 无 | 控制流程 | 布尔判断 |
| **24. 继续下一循环** | 还有步骤，继续 | 💭 执行过程折叠框（后台） | 返回 Command(goto="plan_agent") | `enhanced_plan_agent.py:542-564` | 无 | 继续循环 | Command 对象 |
| **25. 决定报告或结束** | 所有步骤完成 | 💭 执行过程折叠框（后台） | 调用 _decide_report_or_end() | `enhanced_plan_agent.py:565-583,658-728` | 无 | 决定后续 | update_dict |
| **26. 标记工作流完成** | 设置最终状态 | 💭 执行过程折叠框（后台） | 调用 PlanState.mark_workflow_complete() | `enhanced_plan_agent.py:708,715,724` | `states.py:277-281` | 标记完成 | overall_status, end_time |
| **27. 直接结束** | 不生成报告 | 📊 结果返回 | 调用 _present_results_directly() | `enhanced_plan_agent.py:713-720,730-761` | 无 | 展示结果 | 最终结果消息 |
| **28. 后端提取结构化数据** | 提取要发送的数据 | 📊 结果返回（后台） | 调用 _extract_structured_data_from_state() | `server.py:263-397` | 无 | 提取数据 | 结构化数据列表 |
| **29. 发送消息到前端** | 通过 SSE 发送 | 💭 执行过程折叠框 + 📊 结果返回 | yield SSE 事件 | `server.py:480-552,571-572` | 无 | 流式传输 | SSE 事件流 |
| **30. 前端处理消息** | 接收并分类消息 | 💭 执行过程折叠框 + 📊 结果返回 | 调用 process_and_display_assistant_message() | `streamlit_appv1.py:895-990` | 无 | 处理消息 | 分类后的内容 |
| **31. 前端展示执行过程** | 展示思考过程 | 💭 执行过程（点击展开） | 展示意图、计划、执行记录 | `streamlit_appv1.py:992-1048` | 无 | 展示执行过程 | 折叠框内容 |
| **32. 前端展示结果返回** | 展示最终结果 | 📊 结果返回 | 展示表格、代码、文本 | `streamlit_appv1.py:1050-1100` | 无 | 展示结果 | 结果展示 |
| **33. 相似问题推荐** | 生成相似问题 | 页面底部 | 调用 /api/similar-questions | `streamlit_appv1.py:1353-1373` | 无 | 推荐问题 | 相似问题列表 |

---

## 关键状态字段说明

### PlanState 字段
| 字段名 | 类型 | 用途 | 代码位置 |
|-------|------|------|---------|
| `locale` | str | 用户语言设置 | `states.py:198` |
| `user_question` | str | 当前用户问题 | `states.py:203` |
| `origin_user_question` | str | 原始用户问题 | `states.py:204` |
| `current_plan` | Plan | 当前执行计划 | `states.py:200` |
| `executed_steps` | List[Step] | 已执行的步骤 | `states.py:206` |
| `execution_records` | List[StepExecutionRecord] | 标准执行记录 | `states.py:217` |
| `generated_code_files` | List[GeneratedCodeFile] | 生成的代码文件 | `states.py:220` |
| `intent_type` | str | 识别的意图类型 | `states.py:214` |
| `intent_confidence` | float | 意图置信度 | `states.py:213` |
| `search_result` | SearchResult | 搜索Agent结果 | `states.py:223` |
| `analysis_result` | AnalysisResult | 分析Agent结果 | `states.py:224` |
| `visualization_result` | VisualizationResult | 可视化Agent结果 | `states.py:225` |
| `overall_status` | ExecutionStatus | 工作流整体状态 | `states.py:251` |
| `start_time` | str | 工作流开始时间 | `states.py:252` |
| `end_time` | str | 工作流结束时间 | `states.py:253` |

---

## 前端内容分类说明

### 1. 💭 执行过程（折叠框）
| 子部分 | 识别条件 | 展示内容 | 代码位置 |
|-------|---------|---------|---------|
| **1. 意图识别** | JSON 包含 `intent_type` 和 `confidence` | 意图识别 JSON + 路由日志 | `streamlit_appv1.py:996-1004` |
| **2. 执行步骤** | JSON 包含 `locale`、`thought`、`steps` | 完整执行计划 JSON | `streamlit_appv1.py:1007-1019` |
| **3. 执行过程** | JSON 包含 `step_name` 和 `execution_status` | 每个步骤的标准执行 JSON | `streamlit_appv1.py:1022-1048` |

### 2. 📊 结果返回
| 子部分 | 识别条件 | 展示内容 | 代码位置 |
|-------|---------|---------|---------|
| **（1）表格化数据** | JSON 包含 `result`/`results`/`data`/`records` 且为列表 | DataFrame 表格 | `streamlit_appv1.py:1055-1101` |
| **（2）Python 代码脚本** | 代码块标记为 `python` | 可折叠的代码块 | `streamlit_appv1.py:1053-1058` |
| **（3）文本内容** | 过滤后的剩余文本 | 文本框展示 | `streamlit_appv1.py:1060-1064` |

---

## 后端消息发送位置汇总

### enhanced_plan_agent.py 中的 push_message 调用
| 消息内容 | 用途 | 代码位置 | 前端展示位置 |
|---------|------|---------|-----------|
| `🚀 开始执行计划...` | 通知计划开始 | `enhanced_plan_agent.py:382-385` | 💭 执行过程（被过滤） |
| `🔍 正在分析问题...` | 通知正在分析 | `enhanced_plan_agent.py:414-417` | 💭 执行过程（被过滤） |
| `📚 已检索到相关知识信息` | 通知知识已检索 | `enhanced_plan_agent.py:425-428` | 💭 执行过程（被过滤） |
| `📋 正在生成执行计划...` | 通知正在生成计划 | `enhanced_plan_agent.py:433-436` | 💭 执行过程（被过滤） |
| `📋 **计划**: ...` | 展示计划标题 | `enhanced_plan_agent.py:444-447` | 💭 执行过程（被过滤） |
| `💡 **思路**: ...` | 展示计划思路 | `enhanced_plan_agent.py:450-453` | 💭 执行过程（被过滤） |
| `📝 **执行步骤**: ...` | 展示步骤列表 | `enhanced_plan_agent.py:460-463` | 💭 执行过程（被过滤） |
| ````json\n{plan_json}\n```` | 完整计划 JSON | `enhanced_plan_agent.py:468-471` | 💭 执行过程 → 2. 执行步骤 |
| `⚙️ **执行步骤 X**: ...` | 步骤开始通知 | `enhanced_plan_agent.py:150-153` | 💭 执行过程（被过滤） |
| `✅ **步骤 X 完成**: ...` | 步骤完成通知 | `enhanced_plan_agent.py:225-228` | 💭 执行过程（被过滤） |
| `{step_execution_json}` | 标准执行记录 JSON | `enhanced_plan_agent.py:231-234` | 💭 执行过程 → 3. 执行过程 |
| `❌ **步骤 X 失败**: ...` | 步骤失败通知 | `enhanced_plan_agent.py:243-246` | 💭 执行过程（被过滤） |

### enhanced_intent_recognition_agent.py 中的状态更新
| 字段 | 用途 | 代码位置 | 前端展示位置 |
|-----|------|---------|-----------|
| `intent` | 完整意图识别结果 | `enhanced_intent_recognition_agent.py:274` | 💭 执行过程 → 1. 意图识别 |
| `intent_type` | 意图类型 | `enhanced_intent_recognition_agent.py:275` | 💭 执行过程 → 1. 意图识别 |
| `intent_confidence` | 置信度 | `enhanced_intent_recognition_agent.py:276` | 💭 执行过程 → 1. 意图识别 |

---

## 关键代码文件索引

| 文件名 | 主要功能 | 关键行号 |
|-------|---------|---------|
| `streamlit_appv1.py` | 前端界面和消息处理 | 895-1100 |
| `server.py` | 后端服务器和 SSE 流式处理 | 263-572 |
| `enhanced_builder.py` | LangGraph 工作流构建 | 1-298 |
| `enhanced_plan_agent.py` | 增强版计划执行 Agent | 70-761 |
| `enhanced_intent_recognition_agent.py` | 增强版意图识别 | 210-282 |
| `states.py` | 状态定义和管理方法 | 194-281 |
| `agent_utils.py` | Agent 工具和初始化 | 13-63 |
| `template.py` | 提示模板加载 | 40-95 |
| `planner_model.py` | Plan/Step 数据模型 | 1-38 |
| `storage_manager.py` | 会话存储管理 | - |
| `session_manager.py` | 会话管理 | - |
| `similar_questions.py` | 相似问题生成 | - |

---

## 完整流程图（文字版）

```
用户输入
    ↓
前端发送 API 请求 (/api/chat/stream)
    ↓
后端初始化工作流 (server.py:400-463)
    ↓
START → enhanced_intent_recognition_agent
    ↓
    ├─→ SMALLTALK → small_talk_agent → __end__
    │
    ├─→ REPORT → report_workflow_router
    │               ↓
    │           (报告工作流)
    │
    └─→ 其他 → enhanced_plan_agent
                  ↓
            生成初始计划
                  ↓
            发送计划消息
                  ↓
            步骤执行循环
                  ↓
            ├─ 执行当前步骤
            │       ↓
            │   transfer_to_{agent}
            │       ↓
            │   创建执行记录
            │       ↓
            │   发送执行记录 JSON
            │
            ├─ 还有步骤 → enhanced_plan_agent (继续)
            │
            └─ 无更多步骤 → 决策：生成报告或直接结束
                                ↓
                        └─ 直接结束 → __end__
```

---

## 状态管理方法使用汇总

### PlanState 静态方法（states.py:255-281）
| 方法名 | 用途 | 调用位置 |
|-------|------|---------|
| `add_execution_record(state, record)` | 添加执行记录到状态 | `enhanced_plan_agent.py:512` |
| `add_generated_code(state, code_file)` | 添加生成的代码文件 | `enhanced_plan_agent.py:529` |
| `get_all_execution_records_json(state)` | 获取所有执行记录 JSON | `server.py:309` |
| `mark_workflow_complete(state, status)` | 标记工作流完成 | `enhanced_plan_agent.py:708,715,724` |

---

## 实际存在的模板文件清单

| 模板文件名 | 存在位置 |
|-----------|---------|
| `intent_recognition_agent.md` | `src/prompts/intent_recognition_agent.md` |
| `plan_agent.md` | `src/prompts/plan_agent.md` |
| `small_talk_agent.md` | `src/prompts/small_talk_agent.md` |
| `rewrite_question.md` | `src/prompts/rewrite_question.md` |
| `react_agent.md` | `src/prompts/react_agent.md` |
| `replan_agent.md` | `src/prompts/replan_agent.md` |
| `report_adaptive.md` | `src/prompts/report_adaptive.md` |
| `autostat_report.md` | `src/prompts/autostat_report.md` |
| `extract_keywords.md` | `src/prompts/extract_keywords.md` |
| `data_only_standard.md` | `src/prompts/data_only_standard.md` |
| `autostat_visualization.md` | `src/prompts/autostat_visualization.md` |
| `autostat_modeling.md` | `src/prompts/autostat_modeling.md` |
| `autostat_preprocessing.md` | `src/prompts/autostat_preprocessing.md` |

---

*文档创建时间：2026-03-28*
*最后更新：2026-03-28*
