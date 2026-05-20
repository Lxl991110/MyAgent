<template>
  <div class="research-page">
    <h1>🔍 法律研究</h1>
    <p class="subtitle">输入研究主题，AI 自动拆解任务、检索信息并生成结构化报告</p>

    <!-- 输入表单 -->
    <div v-if="!isResearching || !showResults" class="research-form-card">
      <div v-if="caseText" class="case-imported">
        <span>📋</span> 已从案例解析导入案例文本 ({{ caseText.length }} 字)
        <button @click="caseText = ''" class="btn-remove-case">移除</button>
      </div>
      <label class="field">
        <span>研究主题</span>
        <textarea
          v-model="form.topic"
          placeholder="例如：未成年人网络保护相关法律法规及典型案例研究"
          rows="4"
          @keydown.ctrl.enter="handleSubmit"
        ></textarea>
      </label>

      <div class="form-row">
        <label class="field field-sm">
          <span>搜索引擎</span>
          <select v-model="form.searchApi">
            <option value="">沿用后端配置</option>
            <option value="duckduckgo">DuckDuckGo</option>
            <option value="tavily">Tavily</option>
          </select>
        </label>

        <div class="form-actions">
          <button class="btn-submit" @click="handleSubmit" :disabled="loading">
            <span v-if="loading" class="spinner"></span>
            {{ loading ? "研究进行中..." : "开始研究" }}
          </button>
          <button v-if="loading" class="btn-cancel" @click="cancelResearch">取消</button>
        </div>
      </div>

      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>

    <!-- 结果区域 -->
    <div v-if="showResults" class="results-layout">
      <!-- 顶部状态栏 -->
      <div class="status-bar">
        <div class="status-left">
          <span class="status-chip" :class="{ active: loading }">
            <span class="dot"></span> {{ loading ? "研究进行中" : "研究完成" }}
          </span>
          <span class="status-meta">
            任务进度: {{ completedTasks }} / {{ todoTasks.length || 1 }}
            · 日志 {{ progressLogs.length }} 条
          </span>
        </div>
        <div class="status-right">
          <button v-if="!loading" class="btn-new" @click="startNew">新建研究</button>
          <button class="btn-toggle" @click="showLogs = !showLogs">
            {{ showLogs ? "收起日志" : "展开日志" }}
          </button>
        </div>
      </div>

      <!-- 进度日志 -->
      <div v-if="showLogs && progressLogs.length" class="log-panel">
        <div class="log-item" v-for="(log, i) in progressLogs" :key="i">
          <span class="log-dot"></span> {{ log }}
        </div>
      </div>

      <!-- 主内容区：任务列表 + 任务详情 -->
      <div class="main-grid">
        <!-- 左侧任务列表 -->
        <aside class="task-sidebar">
          <h3>任务清单</h3>
          <div
            v-for="task in todoTasks"
            :key="task.id"
            class="task-card"
            :class="{ active: task.id === activeTaskId, completed: task.status === 'completed' }"
            @click="activeTaskId = task.id"
          >
            <div class="task-card-header">
              <strong>{{ task.title }}</strong>
              <span class="task-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
            </div>
            <p class="task-card-intent">{{ task.intent }}</p>
          </div>
        </aside>

        <!-- 右侧任务详情 -->
        <div class="task-detail" v-if="currentTask">
          <div class="detail-header">
            <h3>{{ currentTask.title }}</h3>
            <div class="detail-meta">
              <span>查询: {{ currentTask.query }}</span>
              <span>目标: {{ currentTask.intent }}</span>
            </div>
          </div>

          <!-- 系统提示 -->
          <div v-if="currentTask.notices.length" class="detail-section notices">
            <h4>系统提示</h4>
            <ul>
              <li v-for="(n, i) in currentTask.notices" :key="i">{{ n }}</li>
            </ul>
          </div>

          <!-- 信息来源 -->
          <div class="detail-section" :class="{ highlight: sourcesFlash }">
            <h4>信息来源</h4>
            <div v-if="currentTask.sourceItems.length" class="source-list">
              <a
                v-for="(s, i) in currentTask.sourceItems"
                :key="i"
                :href="s.url || '#'"
                target="_blank"
                rel="noopener"
                class="source-link"
              >{{ s.title || s.url }}</a>
            </div>
            <p v-else class="muted">暂无来源</p>
          </div>

          <!-- 任务总结 -->
          <div class="detail-section" :class="{ highlight: summaryFlash }">
            <h4>任务总结</h4>
            <pre class="content-pre">{{ currentTask.summary || "等待总结..." }}</pre>
          </div>
        </div>

        <!-- 无任务占位 -->
        <div v-else class="task-detail empty-detail">
          <p class="muted">选择左侧任务查看详情</p>
        </div>
      </div>

      <!-- 最终报告 -->
      <div v-if="reportMarkdown" class="report-section" :class="{ highlight: reportFlash }">
        <h2>最终研究报告</h2>
        <pre class="content-pre report-pre">{{ reportMarkdown }}</pre>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from "vue";
import { runResearchStream, type ResearchStreamEvent } from "../services/api";

interface SourceItem {
  title: string;
  url: string;
  snippet: string;
  raw: string;
}

interface TodoTaskView {
  id: number;
  title: string;
  intent: string;
  query: string;
  status: string;
  summary: string;
  sourcesSummary: string;
  sourceItems: SourceItem[];
  notices: string[];
}

const form = reactive({ topic: "", searchApi: "" });
const caseText = ref("");
const loading = ref(false);
const error = ref("");
const isResearching = ref(false);
const showResults = ref(false);
const showLogs = ref(true);

onMounted(() => {
  // 从案例解析页面传入的案例文本
  const stored = sessionStorage.getItem("case_text");
  if (stored) {
    caseText.value = stored;
    sessionStorage.removeItem("case_text");
  }
});

const todoTasks = ref<TodoTaskView[]>([]);
const activeTaskId = ref<number | null>(null);
const reportMarkdown = ref("");
const progressLogs = ref<string[]>([]);

const sourcesFlash = ref(false);
const summaryFlash = ref(false);
const reportFlash = ref(false);

let controller: AbortController | null = null;

const statusLabels: Record<string, string> = {
  pending: "待执行",
  in_progress: "进行中",
  completed: "已完成",
  skipped: "已跳过",
};
const statusLabel = (s: string) => statusLabels[s] ?? s;

const completedTasks = computed(() =>
  todoTasks.value.filter((t) => t.status === "completed").length
);

const currentTask = computed(() => {
  if (activeTaskId.value !== null) {
    return todoTasks.value.find((t) => t.id === activeTaskId.value) ?? null;
  }
  return todoTasks.value[0] ?? null;
});

const pulse = (flag: typeof sourcesFlash) => {
  flag.value = true;
  setTimeout(() => (flag.value = false), 1200);
};

function findTask(id: unknown): TodoTaskView | undefined {
  const n = typeof id === "number" ? id : Number(id);
  if (Number.isNaN(n)) return undefined;
  return todoTasks.value.find((t) => t.id === n);
}

function parseSources(raw: string): SourceItem[] {
  if (!raw) return [];
  const items: SourceItem[] = [];
  const lines = raw.split("\n");
  let cur: SourceItem | null = null;

  const flush = () => {
    if (!cur) return;
    if (cur.title || cur.url || cur.snippet || cur.raw) {
      if (!cur.title && cur.url) cur.title = cur.url;
      items.push(cur);
    }
    cur = null;
  };

  for (const line of lines) {
    const t = line.trim();
    if (!t) continue;

    if (/^\*/.test(t) && t.includes(" : ")) {
      flush();
      const [title, url] = t.replace(/^\*\s*/, "").split(" : ");
      cur = { title: title?.trim() || "", url: url?.trim() || "", snippet: "", raw: "" };
      continue;
    }
    if (/^(信息来源|Source)\s*:/.test(t)) {
      flush();
      const [, title] = t.split(/:\s*(.+)/);
      cur = { title: (title || "").trim(), url: "", snippet: "", raw: "" };
      continue;
    }
    if (/^URL\s*:/.test(t)) {
      if (!cur) cur = { title: "", url: "", snippet: "", raw: "" };
      const [, url] = t.split(/:\s*(.+)/);
      cur.url = (url || "").trim();
      continue;
    }
    if (/^(信息内容|Most relevant content)\s*:/.test(t)) {
      if (!cur) cur = { title: "", url: "", snippet: "", raw: "" };
      const [, c] = t.split(/:\s*(.+)/);
      cur.snippet = (c || "").trim();
      continue;
    }
    if (/https?:\/\//.test(t)) {
      if (!cur) cur = { title: "", url: "", snippet: "", raw: "" };
      if (!cur.url) { cur.url = t; continue; }
    }
    if (!cur) cur = { title: "", url: "", snippet: "", raw: "" };
    cur.raw = cur.raw ? `${cur.raw}\n${t}` : t;
  }
  flush();
  return items;
}

function reset() {
  todoTasks.value = [];
  activeTaskId.value = null;
  reportMarkdown.value = "";
  progressLogs.value = [];
  sourcesFlash.value = summaryFlash.value = reportFlash.value = false;
}

const handleSubmit = async () => {
  if (!form.topic.trim()) { error.value = "请输入研究主题"; return; }
  if (controller) controller.abort();

  loading.value = true;
  error.value = "";
  isResearching.value = true;
  showResults.value = true;
  reset();

  controller = new AbortController();

  try {
    await runResearchStream(
      { topic: form.topic.trim(), case_text: caseText.value, search_api: form.searchApi || undefined },
      (event: ResearchStreamEvent) => {
        if (event.type === "status") {
          const msg = typeof event.message === "string" ? event.message : "";
          if (msg) progressLogs.value.push(msg);
          const task = findTask((event as Record<string, unknown>).task_id);
          if (task && msg) task.notices.push(msg);
          return;
        }

        if (event.type === "todo_list") {
          const tasks = Array.isArray(event.tasks) ? event.tasks as Record<string, unknown>[] : [];
          todoTasks.value = tasks.map((item, i) => ({
            id: typeof item.id === "number" ? item.id : i + 1,
            title: String(item.title || `任务${i + 1}`),
            intent: String(item.intent || ""),
            query: String(item.query || form.topic),
            status: String(item.status || "pending"),
            summary: "",
            sourcesSummary: "",
            sourceItems: [],
            notices: [],
          }));
          if (todoTasks.value.length) {
            activeTaskId.value = todoTasks.value[0].id;
            progressLogs.value.push(`已生成 ${todoTasks.value.length} 个研究任务`);
          }
          return;
        }

        if (event.type === "task_status") {
          const task = findTask(event.task_id);
          if (!task) return;
          const status = String(event.status || task.status);
          task.status = status;
          if (status === "in_progress") {
            progressLogs.value.push(`开始: ${task.title}`);
            activeTaskId.value = task.id;
          } else if (status === "completed") {
            if (typeof event.summary === "string") task.summary = event.summary;
            if (typeof event.sources_summary === "string") {
              task.sourcesSummary = event.sources_summary;
              task.sourceItems = parseSources(task.sourcesSummary);
            }
            progressLogs.value.push(`完成: ${task.title}`);
            if (activeTaskId.value === task.id) { pulse(summaryFlash); pulse(sourcesFlash); }
          } else if (status === "skipped") {
            progressLogs.value.push(`跳过: ${task.title}`);
          }
          return;
        }

        if (event.type === "sources") {
          const task = findTask(event.task_id);
          if (!task) return;
          const payload = event as Record<string, unknown>;
          const text = [payload.latest_sources, payload.sources_summary, payload.raw_context]
            .find((v) => typeof v === "string" && v.trim()) as string | undefined;
          if (text) {
            task.sourcesSummary = text;
            task.sourceItems = parseSources(text);
            if (activeTaskId.value === task.id) pulse(sourcesFlash);
          }
          return;
        }

        if (event.type === "task_summary_chunk") {
          const task = findTask(event.task_id);
          if (!task) return;
          task.summary += typeof event.content === "string" ? event.content : "";
          if (activeTaskId.value === task.id) pulse(summaryFlash);
          return;
        }

        if (event.type === "final_report") {
          reportMarkdown.value = typeof event.report === "string" ? event.report : "";
          pulse(reportFlash);
          progressLogs.value.push("最终报告已生成");
          saveToHistory();
          return;
        }

        if (event.type === "error") {
          error.value = typeof event.detail === "string" ? event.detail : "研究失败";
          progressLogs.value.push("错误: " + error.value);
        }
      },
      { signal: controller.signal },
    );
  } catch (err: any) {
    if (err.name === "AbortError") {
      progressLogs.value.push("已取消当前研究");
    } else {
      error.value = err.message || "请求失败";
    }
  } finally {
    loading.value = false;
    controller = null;
  }
};

function saveToHistory() {
  try {
    const stored = JSON.parse(localStorage.getItem("law_research_tasks") || "[]");
    stored.unshift({
      id: Date.now().toString(),
      topic: form.topic,
      date: new Date().toLocaleDateString("zh-CN"),
      taskCount: todoTasks.value.length,
      status: "done",
    });
    localStorage.setItem("law_research_tasks", JSON.stringify(stored.slice(0, 20)));
  } catch { /* ignore */ }
}

const cancelResearch = () => {
  if (controller) { controller.abort(); controller = null; }
};

const startNew = () => {
  reset();
  isResearching.value = false;
  showResults.value = false;
  form.topic = "";
  form.searchApi = "";
};

onBeforeUnmount(() => {
  if (controller) controller.abort();
});
</script>

<style scoped>
.research-page { max-width: 1100px; }
.research-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 24px; color: #64748b; font-size: 14px; }

/* --- 输入表单 --- */
.research-form-card {
  background: #fff;
  border: 1px solid rgba(148,163,184,0.15);
  border-radius: 20px;
  padding: 28px;
  max-width: 640px;
}

.case-imported {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; margin-bottom: 16px;
  background: rgba(201,168,76,0.06); border: 1px solid rgba(201,168,76,0.2);
  border-radius: 10px; font-size: 13px; color: #1e3a5f;
}
.btn-remove-case {
  margin-left: auto; padding: 3px 10px; border: 1px solid rgba(148,163,184,0.2);
  border-radius: 6px; background: #fff; cursor: pointer; font-size: 11px; color: #64748b;
}
.btn-remove-case:hover { border-color: #b91c1c; color: #b91c1c; }

.field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.field span { font-weight: 600; color: #475569; font-size: 13px; }
.field-sm { flex: 1; min-width: 160px; }
textarea, select {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(148,163,184,0.3);
  font-size: 14px;
  font-family: inherit;
  color: #1f2937;
  background: #fafaf9;
}
textarea:focus, select:focus { outline: none; border-color: #c9a84c; box-shadow: 0 0 0 3px rgba(201,168,76,0.12); }

.form-row { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
.form-actions { display: flex; align-items: center; gap: 10px; }

.btn-submit {
  padding: 12px 24px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #1e3a5f, #c9a84c);
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: transform 0.2s, box-shadow 0.2s;
}
.btn-submit:not(:disabled):hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(30,58,95,0.2); }
.btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-cancel {
  padding: 10px 18px;
  border: 1px solid rgba(148,163,184,0.3);
  border-radius: 12px;
  background: #fff;
  color: #64748b;
  cursor: pointer;
  font-size: 13px;
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.error-msg { margin-top: 12px; padding: 10px 14px; background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.25); border-radius: 12px; color: #b91c1c; font-size: 13px; }

/* --- 结果区域 --- */
.results-layout { display: flex; flex-direction: column; gap: 16px; }

.status-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 20px;
  background: #fff;
  border: 1px solid rgba(148,163,184,0.12);
  border-radius: 14px;
  flex-wrap: wrap; gap: 12px;
}
.status-left { display: flex; align-items: center; gap: 12px; }
.status-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: 20px; font-size: 13px;
  background: rgba(30,58,95,0.04); border: 1px solid rgba(30,58,95,0.15);
}
.status-chip.active { background: rgba(201,168,76,0.1); border-color: rgba(201,168,76,0.25); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; animation: pulse-dot 1.8s infinite; }
@keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.4} }
.status-meta { font-size: 13px; color: #64748b; }
.btn-new, .btn-toggle {
  padding: 8px 14px; border-radius: 10px; font-size: 13px; cursor: pointer;
  border: 1px solid rgba(148,163,184,0.2); background: #fff; color: #475569;
}
.btn-new { background: #1e3a5f; color: #fff; border: none; }

/* 日志面板 */
.log-panel {
  background: #fff; border: 1px solid rgba(148,163,184,0.1);
  border-radius: 12px; padding: 12px 16px; max-height: 180px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 6px;
}
.log-item { font-size: 13px; color: #475569; display: flex; align-items: center; gap: 8px; }
.log-dot { width: 6px; height: 6px; border-radius: 50%; background: #c9a84c; flex-shrink: 0; }

/* 主内容网格 */
.main-grid { display: grid; grid-template-columns: 260px 1fr; gap: 16px; align-items: start; }

/* 任务侧边栏 */
.task-sidebar {
  background: #fff; border: 1px solid rgba(148,163,184,0.1); border-radius: 14px;
  padding: 16px; display: flex; flex-direction: column; gap: 8px;
}
.task-sidebar h3 { margin: 0 0 4px; font-size: 15px; color: #1e3a5f; }
.task-card {
  padding: 12px; border-radius: 10px; cursor: pointer;
  border: 1px solid transparent; transition: all 0.15s;
}
.task-card:hover { background: rgba(30,58,95,0.02); }
.task-card.active { border-color: #c9a84c; background: rgba(201,168,76,0.04); }
.task-card.completed { border-color: rgba(34,197,94,0.2); }
.task-card-header { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.task-card-header strong { font-size: 13px; color: #1e3a5f; }
.task-card-intent { margin: 4px 0 0; font-size: 12px; color: #94a3b8; }
.task-badge {
  font-size: 10px; padding: 2px 8px; border-radius: 8px; font-weight: 500; white-space: nowrap;
}
.task-badge.pending { background: rgba(148,163,184,0.12); color: #64748b; }
.task-badge.in_progress { background: rgba(59,130,246,0.12); color: #2563eb; }
.task-badge.completed { background: rgba(34,197,94,0.12); color: #15803d; }
.task-badge.skipped { background: rgba(248,113,113,0.1); color: #b91c1c; }

/* 任务详情 */
.task-detail {
  background: #fff; border: 1px solid rgba(148,163,184,0.1); border-radius: 14px;
  padding: 22px; display: flex; flex-direction: column; gap: 18px;
}
.empty-detail { align-items: center; justify-content: center; min-height: 200px; }
.detail-header h3 { margin: 0 0 6px; font-size: 17px; color: #1e3a5f; }
.detail-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: #94a3b8; }
.detail-section { }
.detail-section h4 { margin: 0 0 8px; font-size: 14px; color: #1e3a5f; }
.notices { padding: 12px 16px; background: rgba(30,58,95,0.02); border-radius: 10px; }
.notices ul { margin: 0; padding-left: 18px; font-size: 13px; color: #475569; display: flex; flex-direction: column; gap: 4px; }
.source-list { display: flex; flex-direction: column; gap: 4px; }
.source-link { font-size: 13px; color: #1e3a5f; text-decoration: none; font-weight: 500; }
.source-link:hover { color: #c9a84c; }
.muted { color: #94a3b8; font-size: 13px; }
.content-pre {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word;
  background: #fafaf9; padding: 14px; border-radius: 10px;
  border: 1px solid rgba(148,163,184,0.15); max-height: 400px; overflow-y: auto;
}
.report-pre { max-height: 600px; }

.report-section {
  background: #fff; border: 1px solid rgba(201,168,76,0.2); border-radius: 16px;
  padding: 24px;
}
.report-section h2 { margin: 0 0 14px; font-size: 20px; color: #1e3a5f; }

.highlight { animation: glow 1.2s ease; }
@keyframes glow {
  0% { box-shadow: 0 0 0 rgba(201,168,76,0.3); border-color: rgba(201,168,76,0.5); }
  100% { box-shadow: none; border-color: rgba(148,163,184,0.1); }
}

@media (max-width: 768px) {
  .main-grid { grid-template-columns: 1fr; }
}
</style>
