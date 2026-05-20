<template>
  <div class="case-parse-page">
    <header class="page-header">
      <div>
        <h1>📋 案例结构化解析</h1>
        <p>输入法律案例文本，自动抽取实体、结构化信息并匹配相关法条</p>
      </div>
      <div class="header-actions">
        <span class="badge" :class="backendOk ? 'badge-online' : 'badge-offline'">
          {{ backendOk ? "后端在线" : "后端离线" }}
        </span>
      </div>
    </header>

    <!-- 输入区域 -->
    <div class="input-section">
      <div class="input-card">
        <div class="input-header">
          <h3>案例文本</h3>
          <div class="input-actions">
            <label class="btn-upload" title="文件上传开发中">
              📎 上传文件
              <span class="tag-wip">开发中</span>
            </label>
            <button class="btn-clear" @click="clearInput" :disabled="!rawText">清空</button>
            <label class="toggle-bert">
              <input type="checkbox" v-model="useBert" :disabled="true" />
              BERT 增强 <span class="tag-wip">需额外安装</span>
            </label>
          </div>
        </div>
        <textarea
          v-model="rawText"
          placeholder="在此粘贴法律案例文本...
例如：A科技有限公司在2023年1月至2024年6月期间，滥用市场支配地位，限定交易相对人只能与其指定的B平台进行交易，违反了《反垄断法》第二十二条。北京市市场监督管理局对其处以罚款500万元，并责令停止违法行为。"
          rows="8"
          @keydown.ctrl.enter="handleParse"
        ></textarea>
        <div class="input-footer">
          <span class="char-count">{{ rawText.length }} 字</span>
          <button class="btn-parse" @click="handleParse" :disabled="parsing || !rawText.trim()">
            <span v-if="parsing" class="spinner"></span>
            {{ parsing ? "解析中..." : "🔍 解析案例" }}
          </button>
        </div>
        <p class="hint">Ctrl + Enter 快速提交</p>
      </div>

      <!-- 预处理统计 -->
      <div v-if="preprocessInfo.sentence_count" class="preprocess-badge">
        <span>预处理:</span>
        <span>{{ preprocessInfo.sentence_count }} 句</span>
        <span>·</span>
        <span>{{ preprocessInfo.paragraph_count }} 段</span>
        <span>·</span>
        <span>{{ preprocessInfo.char_count }} 字符</span>
      </div>

      <p v-if="parseError" class="error-msg">{{ parseError }}</p>
    </div>

    <!-- 解析结果 -->
    <div v-if="parseResult" class="results-area">
      <!-- 实体列表 -->
      <section class="result-panel panel-entities">
        <h3>
          🏷️ 抽取实体
          <span class="count">{{ entitiesByType.length }} 类 · {{ allEntities.length }} 个</span>
        </h3>
        <div v-if="allEntities.length" class="entity-groups">
          <div
            v-for="group in entitiesByType"
            :key="group.type"
            class="entity-group"
          >
            <span class="entity-type-label" :style="{ background: typeColor(group.type) }">
              {{ group.type }}
            </span>
            <div class="entity-tags">
              <span
                v-for="(e, i) in group.entities"
                :key="i"
                class="entity-tag"
                :class="{ dim: e.confidence < 0.8 }"
              >
                {{ e.value }}
                <small v-if="e.confidence < 0.9">{{ (e.confidence * 100).toFixed(0) }}%</small>
              </span>
            </div>
          </div>
        </div>
        <p v-else class="muted">未抽取到实体</p>
      </section>

      <!-- 结构化结果 -->
      <section class="result-panel panel-structured">
        <h3>📊 结构化案例</h3>
        <div v-if="parseResult.case_type" class="struct-grid">
          <div class="struct-item primary">
            <span class="struct-key">案例类型</span>
            <span class="struct-val">{{ parseResult.case_type }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">案例 ID</span>
            <span class="struct-val mono">{{ parseResult.case_id }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">涉事主体</span>
            <span class="struct-val">{{ parseResult.subjects.join("、") || "—" }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">核心行为</span>
            <span class="struct-val">{{ parseResult.behaviors.join("、") || "—" }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">涉案金额</span>
            <span class="struct-val">{{ parseResult.amount || "—" }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">地域 / 时间</span>
            <span class="struct-val">{{ parseResult.region || "—" }} / {{ parseResult.time_period || "—" }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">相关法条</span>
            <span class="struct-val laws">{{ parseResult.related_laws.join("、") || "—" }}</span>
          </div>
          <div class="struct-item">
            <span class="struct-key">风险标签</span>
            <span class="struct-val">
              <span v-for="tag in parseResult.risk_tags" :key="tag" class="risk-tag">{{ tag }}</span>
              <span v-if="!parseResult.risk_tags.length">—</span>
            </span>
          </div>
        </div>
        <p v-else class="muted">待解析</p>

        <button
          v-if="parseResult.case_type"
          class="btn-research"
          @click="startResearch"
        >
          🔍 基于此案例开始法律研究
        </button>
      </section>

      <!-- 匹配法条 -->
      <section class="result-panel panel-laws">
        <h3>
          📜 匹配法条
          <span class="count">{{ matchedLaws.length }} 条</span>
        </h3>
        <div v-if="matchedLaws.length" class="law-list">
          <div v-for="law in matchedLaws" :key="law.law_id" class="law-card">
            <div class="law-header">
              <strong>{{ law.law_name }} {{ law.article_number }}</strong>
              <span v-if="law.score" class="law-score">匹配度 {{ (law.score * 100).toFixed(0) }}%</span>
            </div>
            <p class="law-content">{{ law.content.slice(0, 200) }}{{ law.content.length > 200 ? "..." : "" }}</p>
            <div class="law-meta">
              <span v-if="law.chapter">{{ law.chapter }}</span>
              <span v-if="law.enforcement_level">{{ law.enforcement_level }}</span>
            </div>
          </div>
        </div>
        <div v-else class="law-search">
          <p class="muted">自动根据案例类型检索相关法条</p>
          <button class="btn-search-laws" @click="searchRelatedLaws" :disabled="searchingLaws">
            {{ searchingLaws ? "检索中..." : "检索相关法条" }}
          </button>
        </div>
      </section>
    </div>

    <!-- 知识库：已入库案例 -->
    <section class="kb-section" v-if="storedCases.length">
      <h2>📁 历史解析案例</h2>
      <div class="kb-grid">
        <div v-for="c in storedCases" :key="c.case_id" class="kb-card">
          <h4>{{ c.case_type || "未分类" }}</h4>
          <p>{{ c.description.slice(0, 120) }}{{ c.description.length > 120 ? "..." : "" }}</p>
          <div class="kb-tags">
            <span v-for="s in c.subjects.slice(0, 3)" :key="s">{{ s }}</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import {
  parseCase as apiParseCase,
  searchLaws as apiSearchLaws,
  listCases as apiListCases,
  type CaseParseResponse,
  type LawEntry,
  type CaseEntry,
} from "../services/api";

const router = useRouter();
const rawText = ref("");
const useBert = ref(false);
const parsing = ref(false);
const parseError = ref("");
const searchingLaws = ref(false);
const backendOk = ref(false);

const parseResult = ref<CaseParseResponse | null>(null);
const matchedLaws = ref<LawEntry[]>([]);
const storedCases = ref<CaseEntry[]>([]);
const preprocessInfo = ref<Record<string, unknown>>({});

const allEntities = computed(() => parseResult.value?.entities ?? []);

const entitiesByType = computed(() => {
  const map: Record<string, typeof allEntities.value> = {};
  for (const e of allEntities.value) {
    (map[e.type] ??= []).push(e);
  }
  const order = ["主体", "行为", "条文", "金额", "时间", "地域", "风险关键词"];
  return order
    .filter((t) => map[t]?.length)
    .map((type) => ({ type, entities: map[type] }));
});

const TYPE_COLORS: Record<string, string> = {
  "主体": "#1e3a5f",
  "行为": "#b45309",
  "条文": "#0f766e",
  "金额": "#b91c1c",
  "时间": "#6366f1",
  "地域": "#0891b2",
  "风险关键词": "#be123c",
};
const typeColor = (t: string) => TYPE_COLORS[t] || "#64748b";

const ENTITY_TYPES_CN: Record<string, string> = {
  "subject": "主体",
  "behavior": "行为",
  "law": "条文",
  "amount": "金额",
  "time": "时间",
  "region": "地域",
  "risk": "风险关键词",
};

onMounted(async () => {
  try {
    const res = await fetch((import.meta.env.VITE_API_BASE_URL || "http://localhost:8000") + "/healthz");
    backendOk.value = res.ok;
  } catch {
    backendOk.value = false;
  }

  try {
    storedCases.value = await apiListCases();
  } catch {
    // 后端未启动时忽略
  }
});

const handleParse = async () => {
  if (!rawText.value.trim() || parsing.value) return;
  parsing.value = true;
  parseError.value = "";
  parseResult.value = null;
  matchedLaws.value = [];

  try {
    const result = await apiParseCase({ text: rawText.value, use_bert: useBert.value });
    parseResult.value = result;
    preprocessInfo.value = (result.preprocess_info as Record<string, unknown>) || {};

    if (result.case_type) {
      // 自动检索相关法条
      searchingLaws.value = true;
      try {
        matchedLaws.value = await apiSearchLaws(result.case_type);
      } catch { /* ignore */ }
      searchingLaws.value = false;
    }
  } catch (err: any) {
    parseError.value = err.message || "解析请求失败，请检查后端是否在线";
  } finally {
    parsing.value = false;
  }
};

const searchRelatedLaws = async () => {
  const query = parseResult.value?.case_type || rawText.value.slice(0, 50);
  if (!query) return;
  searchingLaws.value = true;
  try {
    matchedLaws.value = await apiSearchLaws(query);
  } catch (err: any) {
    parseError.value = "法条检索失败: " + (err.message || "");
  } finally {
    searchingLaws.value = false;
  }
};

const clearInput = () => {
  rawText.value = "";
  parseResult.value = null;
  matchedLaws.value = [];
  preprocessInfo.value = {};
  parseError.value = "";
};

const startResearch = () => {
  // 将案例文本存入 sessionStorage，跳转研究页面
  sessionStorage.setItem("case_text", rawText.value);
  router.push("/research");
};
</script>

<style scoped>
.case-parse-page { max-width: 1100px; }

.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  flex-wrap: wrap; gap: 12px; margin-bottom: 24px;
}
.page-header h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.page-header p { margin: 0; color: #64748b; font-size: 13px; }

.badge { font-size: 12px; padding: 5px 12px; border-radius: 8px; font-weight: 500; }
.badge-online { background: rgba(34,197,94,0.1); color: #15803d; }
.badge-offline { background: rgba(248,113,113,0.1); color: #b91c1c; }

/* ── 输入区域 ── */
.input-section { margin-bottom: 24px; }
.input-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.15);
  border-radius: 16px; padding: 22px;
}
.input-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.input-header h3 { margin: 0; font-size: 15px; color: #1e3a5f; }
.input-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.btn-upload {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 12px; border: 1px solid rgba(148,163,184,0.25);
  border-radius: 8px; font-size: 12px; color: #64748b;
  cursor: not-allowed; opacity: 0.7;
}
.btn-clear {
  padding: 6px 12px; border: 1px solid rgba(148,163,184,0.2);
  border-radius: 8px; font-size: 12px; color: #64748b;
  background: #fff; cursor: pointer;
}
.btn-clear:hover:not(:disabled) { border-color: #c9a84c; color: #1e3a5f; }
.toggle-bert { font-size: 12px; color: #64748b; display: flex; align-items: center; gap: 4px; cursor: not-allowed; opacity: 0.7; }
.tag-wip { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(201,168,76,0.15); color: #8b7318; margin-left: 4px; }

textarea {
  width: 100%; padding: 14px; border-radius: 12px;
  border: 1px solid rgba(148,163,184,0.3); font-size: 14px;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  line-height: 1.7; resize: vertical; color: #1f2937;
  background: #fafaf9;
}
textarea:focus { outline: none; border-color: #c9a84c; box-shadow: 0 0 0 3px rgba(201,168,76,0.1); }

.input-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
.char-count { font-size: 12px; color: #94a3b8; }

.btn-parse {
  padding: 10px 22px; border: none; border-radius: 12px;
  background: linear-gradient(135deg, #1e3a5f, #c9a84c);
  color: #fff; font-weight: 600; font-size: 14px; cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.btn-parse:not(:disabled):hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(30,58,95,0.2); }
.btn-parse:disabled { opacity: 0.5; cursor: not-allowed; }
.hint { margin: 8px 0 0; font-size: 12px; color: #94a3b8; }
.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.preprocess-badge {
  display: flex; align-items: center; gap: 6px;
  margin-top: 10px; padding: 8px 14px;
  background: rgba(30,58,95,0.03); border: 1px solid rgba(30,58,95,0.08);
  border-radius: 10px; font-size: 12px; color: #64748b;
}
.error-msg {
  margin-top: 10px; padding: 10px 14px;
  background: rgba(248,113,113,0.08); border: 1px solid rgba(248,113,113,0.2);
  border-radius: 10px; color: #b91c1c; font-size: 13px;
}

/* ── 结果区域 ── */
.results-area { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 32px; }
.result-panel {
  background: #fff; border: 1px solid rgba(148,163,184,0.12);
  border-radius: 16px; padding: 20px;
}
.result-panel h3 { margin: 0 0 14px; font-size: 15px; color: #1e3a5f; display: flex; justify-content: space-between; align-items: center; }
.count { font-size: 12px; color: #94a3b8; font-weight: 400; }

/* 实体 */
.entity-groups { display: flex; flex-direction: column; gap: 14px; }
.entity-type-label {
  display: inline-block; padding: 2px 10px; border-radius: 6px;
  font-size: 11px; font-weight: 600; color: #fff; margin-bottom: 6px;
}
.entity-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.entity-tag {
  padding: 3px 10px; background: rgba(30,58,95,0.05);
  border: 1px solid rgba(30,58,95,0.1); border-radius: 8px;
  font-size: 12px; color: #1f2937;
}
.entity-tag small { color: #94a3b8; margin-left: 2px; }
.entity-tag.dim { opacity: 0.55; }

/* 结构化 */
.struct-grid { display: flex; flex-direction: column; gap: 10px; }
.struct-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 12px; border-radius: 8px;
  background: rgba(30,58,95,0.02); border: 1px solid rgba(30,58,95,0.04);
}
.struct-item.primary { border-color: rgba(201,168,76,0.25); background: rgba(201,168,76,0.04); }
.struct-key { font-size: 11px; color: #94a3b8; font-weight: 600; text-transform: uppercase; }
.struct-val { font-size: 13px; color: #1e3a5f; font-weight: 500; }
.struct-val.mono { font-family: monospace; font-size: 12px; }
.struct-val.laws { color: #0f766e; }
.risk-tag {
  display: inline-block; padding: 1px 8px; margin: 1px 2px;
  background: rgba(190,18,60,0.08); border-radius: 6px;
  font-size: 11px; color: #be123c; font-weight: 500;
}

.btn-research {
  width: 100%; margin-top: 14px; padding: 10px;
  border: 1px solid #c9a84c; border-radius: 10px;
  background: rgba(201,168,76,0.06); color: #1e3a5f;
  font-size: 13px; font-weight: 600; cursor: pointer;
  transition: background 0.2s;
}
.btn-research:hover { background: rgba(201,168,76,0.14); }

/* 法条 */
.law-list { display: flex; flex-direction: column; gap: 10px; }
.law-card {
  padding: 12px; border: 1px solid rgba(148,163,184,0.12);
  border-radius: 10px; background: #fafaf9;
}
.law-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.law-header strong { font-size: 13px; color: #1e3a5f; }
.law-score { font-size: 11px; color: #c9a84c; font-weight: 600; }
.law-content { margin: 0 0 6px; font-size: 12px; color: #475569; line-height: 1.6; }
.law-meta { display: flex; gap: 10px; font-size: 11px; color: #94a3b8; }

.btn-search-laws {
  padding: 8px 16px; margin-top: 8px;
  border: 1px solid rgba(30,58,95,0.15); border-radius: 8px;
  background: #fff; color: #1e3a5f; cursor: pointer; font-size: 13px;
}
.btn-search-laws:hover:not(:disabled) { background: rgba(30,58,95,0.04); }

/* 知识库 */
.kb-section { margin-top: 32px; }
.kb-section h2 { margin: 0 0 14px; font-size: 18px; color: #1e3a5f; }
.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.kb-card {
  padding: 16px; background: #fff;
  border: 1px solid rgba(148,163,184,0.1); border-radius: 12px;
}
.kb-card h4 { margin: 0 0 6px; font-size: 14px; color: #1e3a5f; }
.kb-card p { margin: 0 0 8px; font-size: 12px; color: #64748b; line-height: 1.5; }
.kb-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.kb-tags span {
  padding: 2px 8px; font-size: 11px;
  background: rgba(30,58,95,0.05); border-radius: 4px; color: #475569;
}

.muted { color: #94a3b8; font-size: 13px; }

@media (max-width: 900px) {
  .results-area { grid-template-columns: 1fr; }
}
</style>
