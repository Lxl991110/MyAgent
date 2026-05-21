<template>
  <div class="regulation-page">
    <h1>📜 法规检索</h1>
    <p class="subtitle">Qdrant 语义检索 + 分类路由 + 精确法条定位，覆盖反垄断法、反不正当竞争法、招投标法等 6 部法律</p>

    <div class="search-bar">
      <input
        v-model="query"
        placeholder="输入关键词或法律问题，如'独家协议 限定交易'、'串通投标 处罚'..."
        @keydown.enter="search"
      />
      <button class="btn-search" @click="search" :disabled="loading">
        {{ loading ? "检索中..." : "检索" }}
      </button>
    </div>

    <!-- 分类过滤 -->
    <div class="category-row" v-if="categories.length">
      <span class="cat-label">分类过滤:</span>
      <button
        class="cat-chip"
        :class="{ active: selectedCategory === '' }"
        @click="selectedCategory = ''; search()"
      >全部</button>
      <button
        v-for="cat in categories"
        :key="cat"
        class="cat-chip"
        :class="{ active: selectedCategory === cat }"
        @click="selectedCategory = cat; search()"
      >
        {{ cat }}
        <span class="cat-count" v-if="categoryCounts[cat]">{{ categoryCounts[cat] }}</span>
      </button>
    </div>

    <div class="search-options">
      <label class="opt">
        结果数量:
        <select v-model="topK" @change="search">
          <option :value="3">3</option>
          <option :value="5">5</option>
          <option :value="10">10</option>
          <option :value="20">20</option>
        </select>
      </label>
      <span v-if="totalIndexed" class="opt indexed-info">
        已索引 {{ totalIndexed }} 条法条
      </span>
    </div>

    <!-- 路由分析结果 -->
    <div v-if="routeResult && routeResult.categories?.length" class="route-bar">
      <span class="route-label">🔎 查询分析:</span>
      <span v-if="routeResult.detected_law_name" class="route-detected">
        明确提及 {{ routeResult.detected_law_name }}
      </span>
      <span class="route-cats">
        匹配分类:
        <span v-for="cat in routeResult.categories.slice(0, 3)" :key="cat" class="route-cat">{{ cat }}</span>
      </span>
      <span v-if="routeResult.preferred_laws?.length" class="route-laws">
        优先检索:
        <span v-for="law in routeResult.preferred_laws.slice(0, 3)" :key="law" class="route-law">{{ law }}</span>
      </span>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 检索结果 -->
    <section v-if="hits.length" class="results-section">
      <h2>📋 检索结果 ({{ totalHits }} 条)</h2>
      <div class="law-card" v-for="law in hits" :key="law.law_id">
        <div class="law-header">
          <span class="law-name">{{ law.law_name }}</span>
          <span class="law-article">{{ law.article_number }}</span>
          <span class="law-category">{{ law.category }}</span>
          <span class="law-score" :class="scoreClass(law.score)">
            {{ (law.score * 100).toFixed(0) }}%
          </span>
        </div>
        <p class="law-content">{{ law.content }}</p>
        <div class="law-keywords" v-if="law.keywords?.length">
          <span v-for="kw in law.keywords" :key="kw" class="kw-tag">{{ kw }}</span>
        </div>
        <div class="law-meta">
          <span v-if="law.chapter">章节: {{ law.chapter }}</span>
          <span v-if="law.enforcement_level">效力级别: {{ law.enforcement_level }}</span>
          <span v-if="law.issuing_authority">发布机关: {{ law.issuing_authority }}</span>
        </div>
      </div>
    </section>

    <div v-if="searched && !hits.length && !loading" class="empty">
      未找到匹配的法条，尝试更换关键词或取消分类过滤
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from "vue";
import { searchLawsSemantic, listCategories, type LawSearchHit, type LawRouteResult } from "../services/api";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const query = ref("");
const loading = ref(false);
const error = ref("");
const searched = ref(false);
const topK = ref(10);

const hits = ref<LawSearchHit[]>([]);
const totalHits = ref(0);
const routeResult = ref<LawRouteResult | null>(null);

// 分类
const categories = ref<string[]>([]);
const categoryCounts = ref<Record<string, number>>({});
const selectedCategory = ref("");
const totalIndexed = ref(0);

onMounted(async () => {
  try {
    const data = await listCategories();
    categories.value = data.categories;
    categoryCounts.value = data.counts;
    totalIndexed.value = data.total_indexed;
  } catch {
    // 分类数据不可用时静默
  }
});

function scoreClass(score: number) {
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "mid";
  return "low";
}

async function search() {
  if (!query.value.trim()) return;
  loading.value = true;
  error.value = "";
  searched.value = true;

  try {
    const result = await searchLawsSemantic(query.value, {
      category: selectedCategory.value || undefined,
      top_k: topK.value,
    });
    hits.value = result.hits;
    totalHits.value = result.total;
    routeResult.value = result.route;
  } catch (e: any) {
    error.value = "检索失败: " + (e.message || "未知错误");
    hits.value = [];
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.regulation-page { max-width: 960px; }
.regulation-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 20px; color: #64748b; font-size: 14px; }

.search-bar { display: flex; gap: 10px; margin-bottom: 14px; }
.search-bar input {
  flex: 1; padding: 12px 16px; border: 1px solid #e2e8f0; border-radius: 10px;
  font-size: 14px; outline: none;
}
.search-bar input:focus { border-color: #c9a84c; }
.btn-search {
  padding: 12px 28px; background: #1e3a5f; color: #fff; border: none;
  border-radius: 10px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.btn-search:disabled { opacity: 0.5; cursor: not-allowed; }

/* 分类过滤 */
.category-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.cat-label { font-size: 13px; color: #64748b; font-weight: 500; }
.cat-chip {
  padding: 4px 12px; font-size: 12px; border-radius: 14px;
  background: #fff; color: #475569; border: 1px solid #e2e8f0;
  cursor: pointer; transition: all 0.15s;
}
.cat-chip:hover { border-color: #c9a84c; }
.cat-chip.active {
  background: rgba(201,168,76,0.12);
  color: #8b7318;
  border-color: #c9a84c;
  font-weight: 600;
}
.cat-count { font-size: 10px; margin-left: 2px; opacity: 0.7; }

.search-options { display: flex; gap: 20px; align-items: center; margin-bottom: 16px; font-size: 13px; color: #64748b; }
.opt { display: flex; align-items: center; gap: 6px; }
.opt select { padding: 4px 8px; border-radius: 6px; border: 1px solid #e2e8f0; }
.indexed-info { color: #94a3b8; font-size: 12px; }

/* 路由分析 */
.route-bar {
  padding: 10px 14px; margin-bottom: 16px;
  background: rgba(30,58,95,0.03); border: 1px solid rgba(30,58,95,0.08);
  border-radius: 10px; display: flex; align-items: center; gap: 14px;
  flex-wrap: wrap; font-size: 13px;
}
.route-label { font-weight: 600; color: #1e3a5f; }
.route-detected { color: #c9a84c; font-weight: 600; }
.route-cats { color: #64748b; }
.route-cat {
  display: inline-block; margin: 1px 3px; padding: 1px 8px;
  background: rgba(30,58,95,0.06); border-radius: 6px; font-size: 12px;
}
.route-laws { color: #64748b; }
.route-law {
  display: inline-block; margin: 1px 3px; padding: 1px 8px;
  background: rgba(201,168,76,0.08); border-radius: 6px; font-size: 12px;
}

.error-msg { padding: 12px; background: #fef2f2; color: #dc2626; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }
.empty { text-align: center; padding: 40px; color: #94a3b8; }

.results-section { margin-bottom: 32px; }
.results-section h2 { font-size: 16px; color: #1e3a5f; margin: 0 0 14px; }

.law-card {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 12px;
  padding: 16px; margin-bottom: 10px;
}
.law-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.law-name { font-weight: 700; color: #1e3a5f; font-size: 15px; }
.law-article { font-size: 13px; color: #c9a84c; font-weight: 600; }
.law-category {
  font-size: 11px; padding: 1px 8px; border-radius: 8px;
  background: rgba(30,58,95,0.06); color: #1e3a5f; font-weight: 500;
}
.law-score { font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.law-score.high { background: rgba(34,197,94,0.12); color: #15803d; }
.law-score.mid { background: rgba(201,168,76,0.12); color: #8b7318; }
.law-score.low { background: rgba(148,163,184,0.1); color: #64748b; }

.law-content { margin: 0 0 8px; font-size: 13px; color: #475569; line-height: 1.6; }

.law-keywords { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.kw-tag {
  font-size: 11px; padding: 2px 8px; background: rgba(201,168,76,0.06);
  color: #8b7318; border-radius: 8px; font-weight: 500;
}

.law-meta { display: flex; gap: 14px; font-size: 11px; color: #94a3b8; flex-wrap: wrap; }

@media (max-width: 640px) {
  .route-bar { flex-direction: column; align-items: flex-start; gap: 6px; }
}
</style>
