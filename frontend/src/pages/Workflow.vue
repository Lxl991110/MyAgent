<template>
  <div class="workflow-page">
    <h1>🔀 智能体工作流可视化</h1>
    <p class="subtitle">LangGraph 多智能体协同工作流 — 当前已实现的核心流程</p>

    <!-- 已实现的工作流 -->
    <section class="wf-section">
      <h2>已实现：法律研究工作流</h2>
      <div class="wf-diagram">
        <div class="wf-node" v-for="(node, i) in implementedFlow" :key="node.id">
          <div class="wf-node-card" :class="node.status">
            <span class="wf-node-icon">{{ node.icon }}</span>
            <strong>{{ node.label }}</strong>
            <p>{{ node.desc }}</p>
            <div class="wf-node-badge" :class="node.status">
              {{ node.status === "active" ? "已实现" : "" }}
            </div>
          </div>
          <div class="wf-edge" v-if="i < implementedFlow.length - 1">
            <span class="edge-arrow">↓</span>
            <span class="edge-label">{{ node.nextLabel }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 计划中的工作流 -->
    <section class="wf-section">
      <h2>规划中：完整智能体工作流 (开发中)</h2>
      <div class="wf-diagram wf-future">
        <div class="wf-row">
          <div class="wf-node future">
            <div class="wf-node-card future-card">
              <span class="wf-node-icon">📋</span>
              <strong>案例解析</strong>
              <p>BERT + NER 实体抽取</p>
            </div>
          </div>
          <span class="row-arrow">→</span>
          <div class="wf-node future">
            <div class="wf-node-card future-card">
              <span class="wf-node-icon">📜</span>
              <strong>法规检索</strong>
              <p>向量库 + RAG</p>
            </div>
          </div>
          <span class="row-arrow">→</span>
          <div class="wf-node future">
            <div class="wf-node-card future-card">
              <span class="wf-node-icon">⚖️</span>
              <strong>合规审查</strong>
              <p>违规检测 + 事实校验</p>
            </div>
          </div>
          <span class="row-arrow">→</span>
          <div class="wf-node future">
            <div class="wf-node-card future-card">
              <span class="wf-node-icon">📄</span>
              <strong>报告生成</strong>
              <p>结构化法律文书</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 执行日志（模拟） -->
    <section class="wf-section">
      <h2>节点说明</h2>
      <div class="node-detail-grid">
        <div class="node-detail" v-for="node in nodeDetails" :key="node.id">
          <h3>{{ node.icon }} {{ node.name }}</h3>
          <p class="node-detail-desc">{{ node.description }}</p>
          <div class="node-io">
            <span class="io-label">输入:</span> {{ node.input }}
          </div>
          <div class="node-io">
            <span class="io-label">输出:</span> {{ node.output }}
          </div>
          <span class="tag" :class="node.status === 'active' ? 'tag-done' : 'tag-wip'">
            {{ node.status === "active" ? "已实现" : "开发中" }}
          </span>
        </div>
      </div>
    </section>
  </div>
</template>

<script lang="ts" setup>
const implementedFlow = [
  { id: "plan", label: "研究规划", icon: "📝", desc: "拆解主题为 3-5 个待办任务", status: "active", nextLabel: "任务清单" },
  { id: "search", label: "信息检索", icon: "🔍", desc: "Tavily / DuckDuckGo 多源搜索", status: "active", nextLabel: "检索结果" },
  { id: "summarize", label: "任务总结", icon: "📊", desc: "LLM 整合每个任务的关键发现", status: "active", nextLabel: "任务总结" },
  { id: "report", label: "报告生成", icon: "📄", desc: "结构化 Markdown 研究报告", status: "active", nextLabel: "" },
];

const nodeDetails = [
  {
    id: "plan", icon: "📝", name: "研究规划 (plan)", status: "active",
    description: "接收研究主题，调用 LLM 将主题拆解为 3-5 个互补的研究任务，每个任务包含标题、意图和检索查询。",
    input: "research_topic (string)",
    output: "todo_items (list), 每个含 title / intent / query",
  },
  {
    id: "search", icon: "🔍", name: "信息检索 (search_tasks)", status: "active",
    description: "遍历每个任务，调用配置的搜索引擎 (Tavily/DuckDuckGo) 采集相关信息，去重并格式化来源。",
    input: "todo_items (list)",
    output: "web_research_results (list), sources_gathered (list)",
  },
  {
    id: "summarize", icon: "📊", name: "任务总结 (summarize_tasks)", status: "active",
    description: "对每个任务的检索结果，调用 LLM 进行流式总结，提取关键信息并整合为结构化摘要。",
    input: "web_research_results, todo_items",
    output: "每个任务的 summary + sources_summary",
  },
  {
    id: "report", icon: "📄", name: "报告生成 (generate_report)", status: "active",
    description: "整合所有任务的总结与来源，调用 LLM 生成最终的结构化 Markdown 研究报告。",
    input: "todo_items (含 summary), research_topic",
    output: "structured_report (markdown)",
  },
  {
    id: "case_parse", icon: "📋", name: "案例解析 (case_parse)", status: "wip",
    description: "计划中：基于 BERT + NER 模型，对输入的法律案例文本进行实体抽取与结构化信息提取。",
    input: "案例文本 / 文件",
    output: "结构化案例信息 (涉事主体、金额、条文等)",
  },
  {
    id: "compliance", icon: "⚖️", name: "合规审查 (compliance_review)", status: "wip",
    description: "计划中：基于违规检测模型与事实校验引擎，判断案例合规性并输出风险等级与违规依据。",
    input: "结构化案例 + 相关法条",
    output: "审查结论、风险等级、违规点列表",
  },
];
</script>

<style scoped>
.workflow-page { max-width: 1000px; }
.workflow-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 28px; color: #64748b; font-size: 14px; }

.wf-section { margin-bottom: 36px; }
.wf-section h2 { margin: 0 0 16px; font-size: 17px; color: #1e3a5f; }

/* 垂直流程图 */
.wf-diagram { display: flex; flex-direction: column; align-items: center; gap: 0; }

.wf-node { display: flex; flex-direction: column; align-items: center; }
.wf-node-card {
  width: 320px; padding: 18px 20px; background: #fff;
  border: 1px solid rgba(148,163,184,0.12); border-radius: 14px;
  text-align: center; position: relative;
}
.wf-node-card.active { border-color: rgba(34,197,94,0.3); }
.wf-node-icon { font-size: 28px; display: block; margin-bottom: 8px; }
.wf-node-card strong { display: block; font-size: 15px; color: #1e3a5f; margin-bottom: 4px; }
.wf-node-card p { margin: 0; font-size: 12px; color: #94a3b8; }
.wf-node-badge { margin-top: 8px; font-size: 11px; }
.wf-node-badge.active { color: #15803d; }

.wf-edge { display: flex; flex-direction: column; align-items: center; padding: 4px 0; }
.edge-arrow { font-size: 20px; color: #c9a84c; }
.edge-label { font-size: 11px; color: #94a3b8; }

/* 横向流程图 */
.wf-future { }
.wf-row { display: flex; align-items: flex-start; gap: 8px; justify-content: center; flex-wrap: wrap; }
.row-arrow { font-size: 22px; color: #94a3b8; padding-top: 30px; }
.future-card { opacity: 0.55; }

/* 节点详情网格 */
.node-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.node-detail {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 14px;
  padding: 18px; position: relative;
}
.node-detail h3 { margin: 0 0 8px; font-size: 15px; color: #1e3a5f; }
.node-detail-desc { margin: 0 0 10px; font-size: 13px; color: #475569; line-height: 1.5; }
.node-io { font-size: 12px; color: #64748b; margin-bottom: 2px; }
.io-label { font-weight: 600; color: #1e3a5f; }
.tag { font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 600; position: absolute; top: 14px; right: 14px; }
.tag-done { background: rgba(34,197,94,0.1); color: #15803d; }
.tag-wip { background: rgba(201,168,76,0.12); color: #8b7318; }

@media (max-width: 640px) {
  .node-detail-grid { grid-template-columns: 1fr; }
}
</style>
