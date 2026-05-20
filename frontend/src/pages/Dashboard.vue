<template>
  <div class="dashboard">
    <header class="dash-hero">
      <div>
        <h1>法律研究智能体工作台</h1>
        <p>基于 LangGraph 多智能体协同，覆盖 规划 → 检索 → 总结 → 报告 全流程</p>
      </div>
      <router-link to="/research" class="btn-primary">
        <span>+</span> 新建研究任务
      </router-link>
    </header>

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
        <span class="stat-num">3</span>
        <span class="stat-label">已实现智能体</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">5</span>
        <span class="stat-label">待开发模块</span>
      </div>
    </div>

    <section class="quick-section">
      <h2>快捷入口</h2>
      <div class="quick-grid">
        <router-link to="/research" class="quick-card">
          <span class="qc-icon">🔍</span>
          <div>
            <h3>法律研究</h3>
            <p>输入研究主题，AI 自动拆解任务、检索信息并生成报告</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/workflow" class="quick-card">
          <span class="qc-icon">🔀</span>
          <div>
            <h3>工作流可视化</h3>
            <p>实时查看 LangGraph 工作流执行状态与节点输出</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/case-parse" class="quick-card disabled">
          <span class="qc-icon">📋</span>
          <div>
            <h3>案例解析 <small>(开发中)</small></h3>
            <p>上传案例文本，自动抽取法律实体与结构化信息</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
        <router-link to="/compliance-review" class="quick-card disabled">
          <span class="qc-icon">⚖️</span>
          <div>
            <h3>合规审查 <small>(开发中)</small></h3>
            <p>自动检测违规点、评估风险等级、输出审查报告</p>
          </div>
          <span class="qc-arrow">→</span>
        </router-link>
      </div>
    </section>

    <section class="recent-section" v-if="recentTasks.length">
      <h2>最近研究</h2>
      <div class="recent-list">
        <div
          v-for="task in recentTasks"
          :key="task.id"
          class="recent-item"
        >
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

    <section class="arch-section">
      <h2>智能体工作流架构</h2>
      <div class="arch-flow">
        <div class="arch-node" v-for="(node, i) in flowNodes" :key="node.name">
          <div class="arch-node-box" :class="{ active: node.active }">
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

interface RecentTask {
  id: string;
  topic: string;
  date: string;
  taskCount: number;
  status: string;
}

const recentTasks = ref<RecentTask[]>([]);
const completedCount = computed(() =>
  recentTasks.value.filter((t) => t.status === "done").length
);

const flowNodes = [
  { name: "研究规划", icon: "📝", desc: "拆解主题为任务清单", active: true },
  { name: "信息检索", icon: "🔍", desc: "多源搜索采集信息", active: true },
  { name: "任务总结", icon: "📊", desc: "LLM 整合关键发现", active: true },
  { name: "报告生成", icon: "📄", desc: "结构化研究报告", active: true },
  { name: "合规审查", icon: "⚖️", desc: "违规检测与风险评估", active: false },
  { name: "案例归档", icon: "📁", desc: "存入历史知识库", active: false },
];

onMounted(() => {
  try {
    const stored = localStorage.getItem("law_research_tasks");
    if (stored) {
      recentTasks.value = JSON.parse(stored);
    }
  } catch {
    // ignore
  }
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
  grid-template-columns: 1fr 1fr;
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

.quick-card:hover:not(.disabled) {
  border-color: #c9a84c;
  box-shadow: 0 4px 16px rgba(201,168,76,0.08);
}

.quick-card.disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.qc-icon { font-size: 28px; flex-shrink: 0; }

.quick-card h3 {
  margin: 0 0 2px;
  font-size: 15px;
  color: #1e3a5f;
}

.quick-card h3 small {
  font-size: 11px;
  color: #c9a84c;
  font-weight: 400;
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

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 32px;
}

.recent-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  background: #fff;
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 12px;
}

.recent-topic {
  font-weight: 600;
  color: #1e3a5f;
  font-size: 14px;
}

.recent-meta {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

.recent-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 500;
}

.recent-status.done {
  background: rgba(34,197,94,0.1);
  color: #15803d;
}

.recent-status.running {
  background: rgba(59,130,246,0.1);
  color: #2563eb;
}

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
  width: 140px;
  padding: 16px 14px;
  background: #fff;
  border: 1px solid rgba(148,163,184,0.15);
  border-radius: 14px;
  text-align: center;
  opacity: 0.5;
}

.arch-node-box.active {
  opacity: 1;
  border-color: rgba(201,168,76,0.3);
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
  .quick-grid { grid-template-columns: 1fr; }
  .arch-flow { flex-direction: column; }
  .arch-arrow { display: none; }
}
</style>
