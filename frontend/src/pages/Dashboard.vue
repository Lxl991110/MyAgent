<template>
  <div class="dashboard">
    <header class="dash-hero">
      <div>
        <h1>法律研究智能体工作台</h1>
        <p>LangGraph 多智能体协同 — 案例解析 · 法规检索 · 合规审查 · 记忆存储 · RAG 增强</p>
      </div>
      <router-link to="/research" class="btn-primary">
        <span>+</span> 新建研究任务
      </router-link>
    </header>

    <!-- 统计卡片 -->
    <div class="stat-row">
      <div class="stat-card">
        <span class="stat-num">{{ recentTasks.length }}</span>
        <span class="stat-label">历史研究任务</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ completedCount }}</span>
        <span class="stat-label">已完成报告</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ memoryCount }}</span>
        <span class="stat-label">历史案例库</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ toolCount }}</span>
        <span class="stat-label">MCP 工具</span>
      </div>
    </div>

    <!-- 快捷入口 -->
    <section class="quick-section">
      <h2>快捷入口</h2>
      <div class="quick-grid">
        <router-link to="/research" class="quick-card">
          <span class="qc-icon">🔍</span>
          <div>
            <h3>法律研究</h3>
            <p>多智能体协同，拆解任务、检索信息、生成结构化报告</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/workflow" class="quick-card">
          <span class="qc-icon">🔀</span>
          <div>
            <h3>工作流可视化</h3>
            <p>查看 7 节点 LangGraph 工作流执行状态与节点输出</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/case-parse" class="quick-card">
          <span class="qc-icon">📋</span>
          <div>
            <h3>案例解析</h3>
            <p>上传案例文本，自动抽取法律实体、行为与结构化信息</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/regulation-search" class="quick-card">
          <span class="qc-icon">📜</span>
          <div>
            <h3>法规检索</h3>
            <p>向量 + 关键词混合检索法规库，支持语义相似法条匹配</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/compliance-review" class="quick-card">
          <span class="qc-icon">⚖️</span>
          <div>
            <h3>合规审查</h3>
            <p>规则扫描 + LLM 深度分析 · 记忆增强 RAG · 人工修正</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/history" class="quick-card">
          <span class="qc-icon">📁</span>
          <div>
            <h3>历史案例库</h3>
            <p>Qdrant 长期记忆存储，语义检索相似审查案例辅助 RAG</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
      </div>
    </section>

    <!-- 最近活动 -->
    <div class="recent-sections">
      <section class="recent-section" v-if="recentTasks.length">
        <h2>最近研究</h2>
        <div class="recent-list">
          <div v-for="task in recentTasks" :key="task.id" class="recent-item">
            <div class="recent-info">
              <span class="recent-topic">{{ task.topic }}</span>
              <span class="recent-meta">{{ task.date }} · {{ task.taskCount || 0 }} 个任务</span>
            </div>
            <span class="recent-status" :class="task.status">
              {{ task.status === "done" ? "已完成" : "进行中" }}
            </span>
          </div>
        </div>
      </section>

      <section class="recent-section" v-if="recentTraces.length">
        <h2>最近审查</h2>
        <div class="recent-list">
          <div v-for="t in recentTraces" :key="t.trace_id" class="recent-item">
            <div class="recent-info">
              <span class="recent-topic">{{ t.query?.slice(0, 60) || "无描述" }}{{ t.query?.length > 60 ? "..." : "" }}</span>
              <span class="recent-meta">
                {{ t.step_count || 0 }} 步骤 · {{ formatTime(t.finished_at) }}
                <span v-if="t.memory_saved" class="tag-memory">已入记忆库</span>
              </span>
            </div>
            <span class="recent-risk" v-if="t.risk_level" :class="riskClass(t.risk_level)">{{ t.risk_level }}风险</span>
          </div>
        </div>
      </section>
    </div>

    <!-- 架构流程图 -->
    <section class="arch-section">
      <h2>智能体工作流架构（7 节点 LangGraph Pipeline）</h2>
      <div class="arch-flow">
        <div class="arch-node" v-for="(node, i) in flowNodes" :key="node.name">
          <div class="arch-node-box active">
            <span class="arch-node-icon">{{ node.icon }}</span>
            <strong>{{ node.name }}</strong>
            <p>{{ node.desc }}</p>
          </div>
          <span class="arch-arrow" v-if="i < flowNodes.length - 1">→</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface RecentTask {
  id: string;
  topic: string;
  date: string;
  taskCount: number;
  status: string;
}

interface TraceSummary {
  trace_id: string;
  query: string;
  finished_at: string;
  risk_level: string;
  step_count: number;
  memory_saved: boolean;
}

const recentTasks = ref<RecentTask[]>([]);
const recentTraces = ref<TraceSummary[]>([]);
const memoryCount = ref(0);
const toolCount = ref(0);

const completedCount = computed(() =>
  recentTasks.value.filter((t) => t.status === "done").length
);

const flowNodes = [
  { name: "案例解析", icon: "📋", desc: "实体抽取 & 结构化" },
  { name: "任务规划", icon: "📝", desc: "拆解为子任务清单" },
  { name: "信息检索", icon: "🔍", desc: "多源搜索采集" },
  { name: "RAG 增强", icon: "🧠", desc: "向量检索 + 记忆" },
  { name: "报告生成", icon: "📄", desc: "章节式结构化输出" },
  { name: "合规审查", icon: "⚖️", desc: "规则 + LLM 分析" },
  { name: "校验反馈", icon: "✅", desc: "法条 & 事实验证" },
];

function riskClass(level: string) {
  if (level === "高") return "risk-high";
  if (level === "中") return "risk-mid";
  return "risk-low";
}

function formatTime(ts: string) {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    return d.toLocaleDateString("zh-CN") + " " + d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts.slice(0, 10);
  }
}

onMounted(async () => {
  // 本地研究任务
  try {
    const stored = localStorage.getItem("law_research_tasks");
    if (stored) recentTasks.value = JSON.parse(stored);
  } catch { /* ignore */ }

  // 并行加载后端数据
  const results = await Promise.allSettled([
    fetch(`${baseURL}/logs/traces?limit=5`).then(r => r.ok ? r.json() : []),
    fetch(`${baseURL}/memory/cases?limit=100`).then(r => r.ok ? r.json() : []),
    fetch(`${baseURL}/tools/list`).then(r => r.ok ? r.json() : []),
  ]);

  const [traces, cases, tools] = results;
  if (traces.status === "fulfilled") recentTraces.value = traces.value.slice(0, 5);
  if (cases.status === "fulfilled") memoryCount.value = (cases.value as any[]).length;
  if (tools.status === "fulfilled") toolCount.value = (tools.value as any[]).length;
});
</script>

<style scoped>
.dashboard {
  max-width: 1000px;
}

.dash-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}

.dash-hero h1 {
  margin: 0 0 6px;
  font-size: 26px;
  color: #1e3a5f;
}

.dash-hero p {
  margin: 0;
  color: #64748b;
  font-size: 14px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 12px 24px;
  background: linear-gradient(135deg, #1e3a5f, #c9a84c);
  color: #fff;
  border-radius: 14px;
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  transition: transform 0.2s, box-shadow 0.2s;
  white-space: nowrap;
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(30,58,95,0.25);
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.stat-card {
  background: #fff;
  border: 1px solid rgba(148,163,184,0.15);
  border-radius: 16px;
  padding: 20px;
  text-align: center;
}

.stat-num {
  display: block;
  font-size: 32px;
  font-weight: 700;
  color: #1e3a5f;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 13px;
  color: #64748b;
}

.quick-section h2,
.recent-section h2,
.arch-section h2 {
  margin: 0 0 16px;
  font-size: 18px;
  color: #1e3a5f;
}

.quick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 14px;
  margin-bottom: 32px;
}

.quick-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid rgba(148,163,184,0.15);
  border-radius: 14px;
  text-decoration: none;
  color: inherit;
  transition: all 0.15s ease;
}

.quick-card:hover {
  border-color: #c9a84c;
  box-shadow: 0 4px 16px rgba(201,168,76,0.08);
}

.qc-icon { font-size: 28px; flex-shrink: 0; }

.quick-card h3 {
  margin: 0 0 2px;
  font-size: 15px;
  color: #1e3a5f;
}

.quick-card p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
}

.qc-arrow {
  margin-left: auto;
  color: #94a3b8;
  font-size: 18px;
}

/* 最近活动 */
.recent-sections {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 32px;
}

.recent-section { min-width: 0; }

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  background: #fff;
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
  gap: 12px;
}

.recent-info { min-width: 0; flex: 1; }

.recent-topic {
  font-weight: 600;
  color: #1e3a5f;
  font-size: 14px;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-meta {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

.tag-memory {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 10px;
  background: rgba(34,197,94,0.1);
  color: #15803d;
  border-radius: 4px;
  font-weight: 500;
}

.recent-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 500;
  flex-shrink: 0;
}

.recent-status.done {
  background: rgba(34,197,94,0.1);
  color: #15803d;
}

.recent-status.running {
  background: rgba(59,130,246,0.1);
  color: #2563eb;
}

.recent-risk {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 8px;
  font-weight: 600;
  flex-shrink: 0;
}

.recent-risk.risk-high { background: rgba(220,38,38,0.08); color: #dc2626; }
.recent-risk.risk-mid { background: rgba(201,168,76,0.1); color: #8b7318; }
.recent-risk.risk-low { background: rgba(34,197,94,0.08); color: #15803d; }

/* 架构流 */
.arch-flow {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex-wrap: wrap;
}

.arch-node {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.arch-node-box {
  width: 130px;
  padding: 16px 12px;
  background: #fff;
  border: 1px solid rgba(201,168,76,0.25);
  border-radius: 14px;
  text-align: center;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}

.arch-node-icon { font-size: 22px; display: block; margin-bottom: 6px; }
.arch-node-box strong { display: block; font-size: 13px; color: #1e3a5f; margin-bottom: 4px; }
.arch-node-box p { margin: 0; font-size: 11px; color: #94a3b8; }

.arch-arrow {
  font-size: 20px;
  color: #94a3b8;
  padding-top: 20px;
}

@media (max-width: 768px) {
  .stat-row { grid-template-columns: repeat(2, 1fr); }
  .quick-grid { grid-template-columns: 1fr 1fr; }
  .recent-sections { grid-template-columns: 1fr; }
  .arch-flow { flex-direction: column; }
  .arch-arrow { display: none; }
}
</style>
