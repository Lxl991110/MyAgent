<template>
  <div class="history-page">
    <h1>📁 历史案例库</h1>
    <p class="subtitle">Qdrant 长期记忆存储的所有审查案例</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="!loading && !error" class="history-toolbar">
      <span class="case-count">共 {{ cases.length }} 个案例</span>
      <button class="btn-refresh" @click="fetchCases" :disabled="loading">刷新</button>
    </div>

    <div v-if="!loading && cases.length === 0" class="empty">
      暂无历史案例，完成合规审查后可存入长期记忆
    </div>

    <div v-if="cases.length" class="case-list">
      <div class="case-card" v-for="c in cases" :key="c.case_id">
        <div class="case-card-top">
          <span class="case-type">{{ caseType(c) }}</span>
          <span class="risk-badge" :class="riskClass(c.risk_level)">{{ c.risk_level }}风险</span>
        </div>

        <p class="case-query">{{ c.query?.slice(0, 120) || "无描述" }}{{ c.query?.length > 120 ? "..." : "" }}</p>

        <div class="case-status">
          <span v-if="hasViolation(c)" class="status-violation">⚠ 存在违规</span>
          <span v-else class="status-clean">✓ 未发现违规</span>
        </div>

        <div v-if="hasViolation(c)" class="violated-laws">
          <strong>违反法条:</strong>
          <span class="law-tag" v-for="(law, i) in violatedLaws(c)" :key="i">
            {{ law }}
          </span>
        </div>

        <div class="case-meta">
          <span class="case-id" :title="c.case_id">{{ c.case_id }}</span>
          <span class="case-time">{{ formatTime(c.timestamp) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from "vue";
import { listMemoryCases, type MemoryEntry } from "../services/api";

const cases = ref<MemoryEntry[]>([]);
const loading = ref(true);
const error = ref("");

onMounted(() => fetchCases());

async function fetchCases() {
  loading.value = true;
  error.value = "";
  try {
    cases.value = await listMemoryCases(100);
  } catch (e: any) {
    error.value = "加载失败: " + (e.message || "未知错误");
  } finally {
    loading.value = false;
  }
}

function caseType(c: MemoryEntry): string {
  const types = c.violations?.map((v: any) => v.type).filter(Boolean) || [];
  return types.length ? types.join(" / ") : "其他";
}

function hasViolation(c: MemoryEntry): boolean {
  return c.risk_level === "高" || c.risk_level === "中" || (c.violations?.length || 0) > 0;
}

function violatedLaws(c: MemoryEntry): string[] {
  const laws = new Set<string>();
  (c.violations || []).forEach((v: any) => {
    const refs = v.relevant_laws || [];
    refs.forEach((l: any) => {
      if (typeof l === "string") laws.add(l);
      else if (l.law_name) laws.add(`${l.law_name} ${l.article || ""}`.trim());
    });
  });
  (c.relevant_laws || []).forEach((l: any) => {
    if (l.law_name) laws.add(`${l.law_name} ${l.article || ""}`.trim());
  });
  return Array.from(laws).slice(0, 5);
}

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
</script>

<style scoped>
.history-page { max-width: 1000px; }
.history-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 24px; color: #64748b; font-size: 14px; }

.loading { text-align: center; padding: 40px; color: #94a3b8; }
.error-msg { padding: 12px; background: #fef2f2; color: #dc2626; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }
.empty { text-align: center; padding: 60px 20px; color: #94a3b8; font-size: 14px; }

.history-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.case-count { font-size: 13px; color: #64748b; }
.btn-refresh {
  padding: 6px 16px; background: #fff; border: 1px solid #e2e8f0;
  border-radius: 8px; font-size: 12px; color: #475569; cursor: pointer;
}
.btn-refresh:hover { border-color: #c9a84c; }

.case-list { display: flex; flex-direction: column; gap: 12px; }

.case-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 14px;
  padding: 18px 20px;
}
.case-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.case-type { font-size: 15px; font-weight: 700; color: #1e3a5f; }
.risk-badge { font-size: 12px; padding: 3px 10px; border-radius: 10px; font-weight: 600; }
.risk-badge.risk-high { background: rgba(220,38,38,0.08); color: #dc2626; }
.risk-badge.risk-mid { background: rgba(201,168,76,0.1); color: #8b7318; }
.risk-badge.risk-low { background: rgba(34,197,94,0.08); color: #15803d; }

.case-query { margin: 0 0 8px; font-size: 13px; color: #475569; line-height: 1.5; }

.case-status { margin-bottom: 6px; }
.status-violation { font-size: 12px; color: #dc2626; font-weight: 500; }
.status-clean { font-size: 12px; color: #15803d; font-weight: 500; }

.violated-laws { font-size: 13px; color: #475569; margin-bottom: 8px; }
.violated-laws strong { color: #1e3a5f; }
.law-tag {
  display: inline-block; margin: 2px 4px; padding: 2px 8px;
  background: rgba(201,168,76,0.08); color: #8b7318;
  border-radius: 6px; font-size: 12px;
}

.case-meta { display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8; }
.case-id { font-family: monospace; }
</style>
