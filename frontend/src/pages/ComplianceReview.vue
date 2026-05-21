<template>
  <div class="compliance-page">
    <h1>⚖️ 合规审查</h1>
    <p class="subtitle">基于违规检测模型与法条知识库 + Qdrant 长期记忆，自动审查并辅助 RAG 增强</p>

    <!-- 近期案例卡片 -->
    <div v-if="recentCases.length" class="recent-cases">
      <h3>📌 近期审查案例</h3>
      <div class="recent-grid">
        <div class="recent-card" v-for="c in recentCases" :key="c.case_id">
          <div class="rc-top">
            <span class="rc-type">{{ caseType(c) }}</span>
            <span class="rc-risk" :class="riskBadgeClass(c.risk_level)">{{ c.risk_level }}</span>
          </div>
          <p class="rc-query">{{ c.query?.slice(0, 60) || "无描述" }}{{ c.query?.length > 60 ? "..." : "" }}</p>
          <div class="rc-laws">
            <span v-if="hasViolation(c)" class="law-chip" v-for="(l, i) in violatedLawList(c).slice(0, 2)" :key="i">{{ l }}</span>
            <span v-if="hasViolation(c) && !violatedLawList(c).length" class="law-chip">详见审查报告</span>
            <span v-if="!hasViolation(c)" class="no-law">未发现违规</span>
          </div>
        </div>
      </div>
    </div>

    <div class="input-area">
      <textarea
        v-model="text"
        placeholder="输入待审查的合同条款或商业行为描述...&#10;&#10;例如：某电商平台要求入驻商家签订独家协议，不得在其他平台上架相同商品，违者每件罚款500元。"
        rows="8"
      ></textarea>
      <div class="input-actions">
        <label class="rag-toggle">
          <input type="checkbox" v-model="useRag" /> 启用 RAG 知识库增强
        </label>
        <button class="btn-review" @click="review" :disabled="loading">
          {{ loading ? "审查中..." : "开始合规审查" }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <div v-if="result" class="result-panel">
      <!-- 风险等级 -->
      <div class="risk-banner" :class="riskColor">
        <span class="risk-icon">{{ riskIcon }}</span>
        <div>
          <strong>风险等级: {{ result.risk_level }}</strong>
          <p v-if="result.review_summary">{{ result.review_summary }}</p>
        </div>
      </div>

      <!-- 违规点 -->
      <section v-if="result.violations?.length" class="result-section">
        <h2>🚨 检测到的违规风险 ({{ result.violations.length }})</h2>
        <div class="violation-card" v-for="(v, i) in result.violations" :key="i">
          <div class="violation-header">
            <span class="violation-type">{{ v.type }}</span>
            <span class="severity" :class="'sev-' + (v.severity || '★☆☆').charAt(v.severity?.length - 2) || '1'">
              {{ v.severity || '★☆☆' }}
            </span>
          </div>
          <div class="violation-keywords">
            <span v-for="kw in v.matched_keywords" :key="kw" class="kw-tag">{{ kw }}</span>
          </div>
          <div class="violation-laws" v-if="v.relevant_laws?.length">
            <strong>适用法条:</strong>
            <span v-for="law in v.relevant_laws" :key="law" class="law-ref">{{ law }}</span>
          </div>
        </div>
      </section>

      <!-- 相关法条 -->
      <section v-if="result.relevant_laws?.length" class="result-section">
        <div class="section-header">
          <h2>📜 相关法律法规 ({{ editMode ? editingLaws.length : result.relevant_laws.length }})</h2>
          <button class="btn-edit-laws" @click="toggleEditLaws">
            {{ editMode ? "取消编辑" : "✏️ 修正法条" }}
          </button>
        </div>

        <!-- 编辑模式 -->
        <template v-if="editMode">
          <div class="law-edit-card" v-for="(law, i) in editingLaws" :key="i">
            <div class="law-edit-row">
              <input v-model="law.law_name" placeholder="法律名称（如《反垄断法》）" class="law-input law-name-input" />
              <input v-model="law.article" placeholder="条文号（如第二十二条）" class="law-input law-article-input" />
            </div>
            <textarea v-model="law.content" placeholder="条文内容摘要" class="law-textarea" rows="3"></textarea>
            <button class="btn-remove-law" @click="removeLaw(i)">✕ 删除此条</button>
          </div>
          <button class="btn-add-law" @click="addLaw">+ 添加法条</button>

          <div class="re-review-bar">
            <p class="re-review-hint">修改完成后，点击下方按钮重新提交给大模型生成修正后的审查结果。</p>
            <button class="btn-re-review" @click="reReview" :disabled="reReviewing">
              {{ reReviewing ? "重新审查中..." : "🔄 重新提交大模型审查" }}
            </button>
          </div>
        </template>

        <!-- 展示模式 -->
        <template v-else>
          <div class="law-card" v-for="law in result.relevant_laws" :key="law.law_name + law.article">
            <div class="law-card-header">
              <strong>{{ law.law_name }}</strong>
              <span class="article">{{ law.article }}</span>
              <span v-if="law.score" class="score">{{ (law.score * 100).toFixed(0) }}%</span>
            </div>
            <p class="law-text">{{ law.content }}</p>
          </div>
        </template>
      </section>

      <!-- 整改建议 -->
      <section v-if="result.suggestions?.length" class="result-section">
        <h2>💡 合规建议</h2>
        <ul class="suggestion-list">
          <li v-for="(s, i) in result.suggestions" :key="i">{{ s }}</li>
        </ul>
      </section>

      <!-- 存入记忆 -->
      <div v-if="caseId" class="memory-action">
        <button
          class="btn-memory"
          :class="{ saved: savedToMemory }"
          :disabled="saving || savedToMemory"
          @click="saveToMemory"
        >
          {{ savedToMemory ? "✅ 已存入记忆" : saving ? "保存中..." : "💾 存入长期记忆" }}
        </button>
        <span v-if="savedToMemory" class="memory-hint">该审查结果已存入 Qdrant 长期记忆，后续审查将自动检索相似案例</span>
        <span v-if="memoryError" class="memory-error">{{ memoryError }}</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";
import { storeMemory, listMemoryCases, type MemoryEntry } from "../services/api";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const text = ref("");
const loading = ref(false);
const useRag = ref(true);
const error = ref("");
const result = ref<any>(null);

const caseId = ref("");
const savedToMemory = ref(false);
const saving = ref(false);
const memoryError = ref("");

// 法条编辑
const editMode = ref(false);
const editingLaws = ref<any[]>([]);
const reReviewing = ref(false);

const recentCases = ref<MemoryEntry[]>([]);

onMounted(async () => {
  try {
    recentCases.value = await listMemoryCases(3);
  } catch {
    // 记忆服务不可用时静默
  }
});

const riskColor = computed(() => {
  if (!result.value) return "";
  const level = result.value.risk_level;
  if (level === "高") return "risk-high";
  if (level === "中") return "risk-mid";
  return "risk-low";
});

const riskIcon = computed(() => {
  if (!result.value) return "";
  const level = result.value.risk_level;
  if (level === "高") return "🔴";
  if (level === "中") return "🟡";
  return "🟢";
});

async function review() {
  if (!text.value.trim()) return;
  loading.value = true;
  error.value = "";
  result.value = null;
  caseId.value = "";
  savedToMemory.value = false;
  editMode.value = false;
  memoryError.value = "";

  try {
    const res = await fetch(`${baseURL}/compliance/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.value,
        use_rag: useRag.value,
      }),
    });
    if (!res.ok) {
      const err = await res.text().catch(() => "");
      throw new Error(err || "审查请求失败");
    }
    result.value = await res.json();
    caseId.value = result.value?.case_id || "";
  } catch (e: any) {
    error.value = "合规审查失败: " + (e.message || "未知错误");
  } finally {
    loading.value = false;
  }
}

// ── 法条编辑 ──
function toggleEditLaws() {
  if (!editMode.value) {
    // 进入编辑模式：深拷贝当前法条
    editingLaws.value = (result.value.relevant_laws || []).map((l: any) => ({
      law_name: l.law_name || "",
      article: l.article || "",
      content: l.content || "",
      score: l.score ?? 0,
    }));
  }
  editMode.value = !editMode.value;
}

function addLaw() {
  editingLaws.value.push({ law_name: "", article: "", content: "", score: 0 });
}

function removeLaw(index: number) {
  editingLaws.value.splice(index, 1);
}

async function reReview() {
  if (!text.value.trim()) return;
  reReviewing.value = true;
  error.value = "";

  try {
    const res = await fetch(`${baseURL}/compliance/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.value,
        use_rag: false,
        override_laws: editingLaws.value.filter((l: any) => l.law_name.trim() || l.article.trim()),
      }),
    });
    if (!res.ok) {
      const err = await res.text().catch(() => "");
      throw new Error(err || "重新审查请求失败");
    }
    result.value = await res.json();
    caseId.value = result.value?.case_id || "";
    savedToMemory.value = false;
    editMode.value = false;
  } catch (e: any) {
    error.value = "重新审查失败: " + (e.message || "未知错误");
  } finally {
    reReviewing.value = false;
  }
}

async function saveToMemory() {
  if (!result.value || !text.value.trim()) return;
  saving.value = true;
  memoryError.value = "";

  try {
    await storeMemory({
      case_text: text.value,
      risk_level: result.value.risk_level || "",
      review_summary: result.value.review_summary || "",
      violations: result.value.violations || [],
      relevant_laws: result.value.relevant_laws || [],
      suggestions: result.value.suggestions || [],
    });
    savedToMemory.value = true;
  } catch (e: any) {
    memoryError.value = "保存失败: " + (e.message || "未知错误");
  } finally {
    saving.value = false;
  }
}

// ── 近期案例卡片辅助 ──
function hasViolation(c: MemoryEntry): boolean {
  return c.risk_level === "高" || c.risk_level === "中" || (c.violations?.length || 0) > 0;
}

function caseType(c: MemoryEntry): string {
  const types = (c.violations || []).map((v: any) => v.type).filter(Boolean);
  return types.length ? types[0] : "其他";
}

function riskBadgeClass(level: string) {
  if (level === "高") return "r-high";
  if (level === "中") return "r-mid";
  return "r-low";
}

function violatedLawList(c: MemoryEntry): string[] {
  const laws = new Set<string>();
  (c.violations || []).forEach((v: any) => {
    // LLM 返回的 relevant_laws 是字符串数组
    const refs = v.relevant_laws || [];
    refs.forEach((l: any) => {
      if (typeof l === "string") laws.add(l);
      else if (l.law_name) laws.add(`${l.law_name} ${l.article || ""}`.trim());
    });
  });
  // 顶层 relevant_laws 是对象数组
  (c.relevant_laws || []).forEach((l: any) => {
    if (l.law_name) {
      laws.add(`${l.law_name} ${l.article || ""}`.trim());
    }
  });
  return Array.from(laws).slice(0, 3);
}
</script>

<style scoped>
.compliance-page { max-width: 900px; }
.compliance-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 20px; color: #64748b; font-size: 14px; }

/* 近期案例卡片 */
.recent-cases { margin-bottom: 20px; }
.recent-cases h3 { margin: 0 0 10px; font-size: 14px; color: #1e3a5f; }
.recent-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.recent-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.1); border-radius: 10px;
  padding: 12px 14px; cursor: default;
}
.recent-card:hover { border-color: rgba(201,168,76,0.25); }
.rc-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.rc-type { font-size: 12px; font-weight: 600; color: #1e3a5f; }
.rc-risk { font-size: 10px; padding: 1px 8px; border-radius: 8px; font-weight: 600; }
.rc-risk.r-high { background: rgba(220,38,38,0.08); color: #dc2626; }
.rc-risk.r-mid { background: rgba(201,168,76,0.1); color: #8b7318; }
.rc-risk.r-low { background: rgba(34,197,94,0.08); color: #15803d; }
.rc-query { margin: 0 0 6px; font-size: 11px; color: #64748b; line-height: 1.4; }
.rc-laws { display: flex; gap: 4px; flex-wrap: wrap; }
.law-chip {
  font-size: 10px; padding: 1px 6px;
  background: rgba(201,168,76,0.06); color: #8b7318;
  border-radius: 4px; font-weight: 500;
}
.no-law { font-size: 10px; color: #94a3b8; }
@media (max-width: 640px) {
  .recent-grid { grid-template-columns: 1fr; }
}

.input-area { margin-bottom: 24px; }
.input-area textarea {
  width: 100%; padding: 14px; border: 1px solid #e2e8f0; border-radius: 10px;
  font-size: 14px; font-family: inherit; resize: vertical; outline: none;
  box-sizing: border-box;
}
.input-area textarea:focus { border-color: #c9a84c; }

.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
.rag-toggle { font-size: 13px; color: #64748b; display: flex; align-items: center; gap: 6px; }
.btn-review {
  padding: 10px 28px; background: #1e3a5f; color: #fff; border: none;
  border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.btn-review:disabled { opacity: 0.5; cursor: not-allowed; }

.error-msg { padding: 12px; background: #fef2f2; color: #dc2626; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }

.result-panel { display: flex; flex-direction: column; gap: 20px; }

.risk-banner {
  display: flex; align-items: flex-start; gap: 14px; padding: 20px;
  border-radius: 14px;
}
.risk-banner.risk-high { background: rgba(220,38,38,0.06); border: 1px solid rgba(220,38,38,0.2); }
.risk-banner.risk-mid { background: rgba(201,168,76,0.08); border: 1px solid rgba(201,168,76,0.2); }
.risk-banner.risk-low { background: rgba(34,197,94,0.06); border: 1px solid rgba(34,197,94,0.2); }
.risk-icon { font-size: 28px; }
.risk-banner strong { font-size: 16px; color: #1e3a5f; display: block; margin-bottom: 4px; }
.risk-banner p { margin: 0; font-size: 13px; color: #475569; }

.result-section { margin-bottom: 8px; }
.result-section h2 { font-size: 16px; color: #1e3a5f; margin: 0 0 12px; }

.violation-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 12px;
  padding: 14px; margin-bottom: 10px;
}
.violation-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.violation-type { font-weight: 600; color: #1e3a5f; font-size: 14px; }
.severity { font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.sev-3 { background: rgba(220,38,38,0.1); color: #dc2626; }
.sev-2 { background: rgba(201,168,76,0.12); color: #8b7318; }
.sev-1 { background: rgba(148,163,184,0.1); color: #64748b; }

.violation-keywords { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.kw-tag {
  font-size: 11px; padding: 2px 8px; background: rgba(220,38,38,0.06);
  color: #b91c1c; border-radius: 8px; font-weight: 500;
}
.violation-laws { font-size: 12px; color: #64748b; }
.law-ref { display: inline-block; margin: 2px 4px; padding: 1px 6px; background: rgba(201,168,76,0.08); border-radius: 4px; font-size: 11px; color: #8b7318; }

.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h2 { margin: 0; }
.btn-edit-laws {
  padding: 6px 14px; font-size: 12px; font-weight: 500;
  background: #fff; color: #1e3a5f; border: 1px solid #c9a84c;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
}
.btn-edit-laws:hover { background: rgba(201,168,76,0.08); }

/* 法条编辑卡片 */
.law-edit-card {
  background: #fff; border: 1px dashed #c9a84c; border-radius: 12px;
  padding: 14px; margin-bottom: 10px; position: relative;
}
.law-edit-row { display: flex; gap: 10px; margin-bottom: 8px; }
.law-input {
  padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
  font-size: 13px; font-family: inherit; outline: none;
  box-sizing: border-box;
}
.law-input:focus { border-color: #c9a84c; }
.law-name-input { flex: 2; }
.law-article-input { flex: 1; }
.law-textarea {
  width: 100%; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
  font-size: 13px; font-family: inherit; resize: vertical; outline: none;
  box-sizing: border-box; margin-bottom: 6px;
}
.law-textarea:focus { border-color: #c9a84c; }
.btn-remove-law {
  padding: 4px 12px; font-size: 11px; color: #dc2626;
  background: transparent; border: none; cursor: pointer; font-weight: 500;
}
.btn-remove-law:hover { text-decoration: underline; }
.btn-add-law {
  padding: 8px 20px; font-size: 13px; font-weight: 500;
  background: #fff; color: #1e3a5f; border: 1px dashed #94a3b8;
  border-radius: 8px; cursor: pointer; width: 100%; margin-bottom: 16px;
}
.btn-add-law:hover { border-color: #c9a84c; color: #c9a84c; }

/* 重新审查 */
.re-review-bar {
  padding: 16px; background: rgba(201,168,76,0.04); border: 1px solid rgba(201,168,76,0.15);
  border-radius: 12px; text-align: center;
}
.re-review-hint { margin: 0 0 12px; font-size: 13px; color: #64748b; }
.btn-re-review {
  padding: 10px 28px; font-size: 14px; font-weight: 600;
  background: #c9a84c; color: #fff; border: none;
  border-radius: 10px; cursor: pointer; transition: all 0.15s;
}
.btn-re-review:hover:not(:disabled) { background: #b8993f; }
.btn-re-review:disabled { opacity: 0.5; cursor: not-allowed; }

.law-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 12px;
  padding: 14px; margin-bottom: 8px;
}
.law-card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.law-card-header strong { font-size: 14px; color: #1e3a5f; }
.article { font-size: 12px; color: #c9a84c; font-weight: 600; }
.score { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: rgba(34,197,94,0.1); color: #15803d; }
.law-text { margin: 0; font-size: 13px; color: #475569; line-height: 1.5; }

.suggestion-list { padding-left: 20px; }
.suggestion-list li { margin-bottom: 8px; font-size: 14px; color: #475569; line-height: 1.5; }

/* 记忆操作 */
.memory-action {
  margin-top: 20px; padding: 16px;
  background: rgba(30,58,95,0.02); border: 1px solid rgba(30,58,95,0.06);
  border-radius: 12px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
}
.btn-memory {
  padding: 10px 20px; font-size: 13px; font-weight: 600;
  background: #1e3a5f; color: #fff; border: none;
  border-radius: 10px; cursor: pointer; white-space: nowrap;
  transition: all 0.2s;
}
.btn-memory:hover:not(:disabled) { background: #152d4a; }
.btn-memory:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-memory.saved { background: #15803d; }
.memory-hint { font-size: 12px; color: #64748b; }
.memory-error { font-size: 12px; color: #dc2626; }
</style>
