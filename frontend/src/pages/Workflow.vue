<template>
  <div class="workflow-page">
    <h1>🔀 智能体工作流可视化</h1>
    <p class="subtitle">LangGraph 7 节点多智能体协同工作流 — RAG + MCP + 生成 + 验证</p>

    <!-- 主工作流 -->
    <section class="wf-section">
      <h2>法律研究 7 节点工作流</h2>
      <div class="wf-diagram">
        <div class="wf-node" v-for="(node, i) in fullFlow" :key="node.id">
          <div class="wf-node-card" :class="node.status">
            <span class="wf-node-icon">{{ node.icon }}</span>
            <strong>{{ node.label }}</strong>
            <p>{{ node.desc }}</p>
            <div class="wf-node-badge" :class="node.status">
              {{ node.status === "active" ? "已实现" : "计划中" }}
            </div>
          </div>
          <div class="wf-edge" v-if="i < fullFlow.length - 1">
            <span class="edge-arrow">↓</span>
            <span class="edge-label">{{ node.nextLabel }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 节点详情 -->
    <section class="wf-section">
      <h2>节点详情</h2>
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
            {{ node.status === "active" ? "已实现" : "计划中" }}
          </span>
        </div>
      </div>
    </section>

    <!-- 技术栈 -->
    <section class="wf-section">
      <h2>RAG + MCP 技术栈</h2>
      <div class="tech-grid">
        <div class="tech-card" v-for="tech in techStack" :key="tech.name">
          <span class="tech-icon">{{ tech.icon }}</span>
          <strong>{{ tech.name }}</strong>
          <p>{{ tech.desc }}</p>
        </div>
      </div>
    </section>
  </div>
</template>

<script lang="ts" setup>
const fullFlow = [
  { id: "case_parse", label: "案例解析", icon: "📋", desc: "NER 实体抽取 + 结构化", status: "active", nextLabel: "结构化案例" },
  { id: "plan", label: "研究规划", icon: "📝", desc: "拆解主题为待办任务", status: "active", nextLabel: "任务清单" },
  { id: "search", label: "信息检索", icon: "🔍", desc: "Tavily 多源网络搜索", status: "active", nextLabel: "检索结果" },
  { id: "summarize", label: "任务总结", icon: "📊", desc: "LLM 总结每个任务", status: "active", nextLabel: "任务总结" },
  { id: "retrieve", label: "RAG 检索", icon: "🧠", desc: "向量 + 关键词检索法条案例", status: "active", nextLabel: "知识库上下文" },
  { id: "generate", label: "生成代理", icon: "✍️", desc: "案由场景模版 + 分段生成", status: "active", nextLabel: "报告草稿" },
  { id: "verify", label: "验证代理", icon: "✅", desc: "事实核查 + 法条校验 + 违规检测", status: "active", nextLabel: "验证结果" },
  { id: "report", label: "报告整合", icon: "📄", desc: "整合生成结果与参考文献", status: "active", nextLabel: "" },
];

const nodeDetails = [
  {
    id: "case_parse", icon: "📋", name: "案例解析 (case_parse)", status: "active",
    description: "接收法律案例文本，通过正则 + 关键词 + 可选 BERT NER 进行实体抽取，输出结构化案例信息并与知识库法条关联。",
    input: "case_text (string)",
    output: "parse_result: case_type, subjects, behaviors, related_laws, risk_tags",
  },
  {
    id: "plan", icon: "📝", name: "研究规划 (plan)", status: "active",
    description: "接收研究主题，调用 LLM 将主题拆解为 3-5 个互补研究任务，每个任务包含标题、意图和检索查询。",
    input: "research_topic",
    output: "todo_items (3-5 个)",
  },
  {
    id: "search", icon: "🔍", name: "信息检索 (search_tasks)", status: "active",
    description: "遍历任务列表，调用 Tavily/DuckDuckGo 搜索引擎采集信息，去重并格式化来源。",
    input: "todo_items",
    output: "web_research_results, sources_gathered",
  },
  {
    id: "summarize", icon: "📊", name: "任务总结 (summarize_tasks)", status: "active",
    description: "对每个任务的检索结果，调用 LLM 进行流式总结，提取关键信息并整合。",
    input: "web_research_results, todo_items",
    output: "task.summary, task.sources_summary",
  },
  {
    id: "retrieve", icon: "🧠", name: "RAG 检索 (retrieve)", status: "active",
    description: "从 Sentence-BERT + FAISS 向量库中检索相关法条和案例，支持向量+关键词混合检索。回退到知识库关键词匹配。",
    input: "research_topic, parse_result, sources_gathered",
    output: "retrieved_laws, retrieved_cases, rag_context",
  },
  {
    id: "generate", icon: "✍️", name: "生成代理 (generate)", status: "active",
    description: "基于 RAG 上下文 + 网络检索结果，按案由场景模版分段生成：案件概述、法律分析、类案参考、风险评估、合规建议。",
    input: "rag_context, web_research_results, parse_result",
    output: "generation_result: report + validation",
  },
  {
    id: "verify", icon: "✅", name: "验证代理 (verify)", status: "active",
    description: "三项检查 — 法条有效性（引用真实性）、事实一致性（报告 vs 原文）、违法行为检测（关键词匹配）。输出评分和修正建议。",
    input: "generated_report, original_case_text, retrieved_laws",
    output: "verification_result: score, warnings, corrections",
  },
  {
    id: "report", icon: "📄", name: "报告整合 (generate_report)", status: "active",
    description: "整合各节点输出，构建参考文献章节，生成最终结构化 Markdown 法律研究报告。",
    input: "generation_result, verification_result",
    output: "structured_report (markdown)",
  },
];

const techStack = [
  { icon: "🧠", name: "Sentence-BERT", desc: "paraphrase-multilingual-MiniLM-L12-v2 中文语义向量 (384维)" },
  { icon: "🔍", name: "FAISS", desc: "Facebook AI Similarity Search — 高效向量索引与最近邻检索" },
  { icon: "🔧", name: "MCP 协议", desc: "Model Context Protocol — 工具标准化注册与调用" },
  { icon: "📚", name: "RAG", desc: "Retrieval-Augmented Generation — 检索增强生成，提升法律引用准确性" },
  { icon: "✅", name: "验证代理", desc: "法条真实性 + 事实一致性 + 违法行为检测三重校验" },
  { icon: "🔗", name: "LangGraph", desc: "有向图状态机编排 7 节点多智能体协同工作流" },
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
  width: 340px; padding: 18px 20px; background: #fff;
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

/* 技术栈 */
.tech-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; }
.tech-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 14px;
  padding: 18px; text-align: center;
}
.tech-icon { font-size: 32px; display: block; margin-bottom: 10px; }
.tech-card strong { display: block; font-size: 14px; color: #1e3a5f; margin-bottom: 4px; }
.tech-card p { margin: 0; font-size: 12px; color: #94a3b8; line-height: 1.4; }

@media (max-width: 640px) {
  .node-detail-grid, .tech-grid { grid-template-columns: 1fr; }
}
</style>
