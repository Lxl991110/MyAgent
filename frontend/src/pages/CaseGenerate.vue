<template>
  <div class="case-gen-page">
    <div class="chat-container">
      <!-- 消息列表 -->
      <div class="chat-messages" ref="messagesEl">
        <!-- 欢迎消息 -->
        <div class="chat-msg system">
          <div class="msg-avatar">🤖</div>
          <div class="msg-body">
            <p>我是案例生成助手，可以根据你指定的条件生成真实合理的法律案例。</p>
            <p>请在下方面板中填写生成条件，或直接描述你想要的案例类型。</p>
            <div class="msg-hint">
              <span>可指定: 违法行为 · 违反法条 · 案件类型 · 风险等级 · 生成风格</span>
            </div>
          </div>
        </div>

        <!-- 流式消息 -->
        <template v-for="(msg, idx) in messages" :key="idx">
          <div class="chat-msg" :class="msg.role">
            <div class="msg-avatar">{{ msg.role === "user" ? "👤" : "🤖" }}</div>
            <div class="msg-body">
              <!-- 进度事件 -->
              <div v-if="msg.progress" class="progress-msg">
                <span class="progress-icon">{{ msg.icon }}</span>
                <span>{{ msg.progress }}</span>
                <span v-if="msg.progress === 'config_resolved'" class="progress-tags">
                  <span v-for="t in msg.tags" :key="t" class="p-tag">{{ t }}</span>
                </span>
              </div>

              <!-- 检索结果摘要 -->
              <div v-if="msg.type === 'laws_retrieved' && msg.laws?.length" class="retrieval-summary">
                <div class="rs-title">📜 检索到 {{ msg.count }} 条相关法条</div>
                <div class="rs-chips">
                  <span v-for="l in msg.laws" :key="l.article_number" class="rs-chip">
                    {{ l.law_name }} {{ l.article_number }}
                  </span>
                </div>
              </div>
              <div v-if="msg.type === 'cases_retrieved' && msg.cases?.length" class="retrieval-summary">
                <div class="rs-title">📁 检索到 {{ msg.count }} 个相似历史案例</div>
              </div>

              <!-- 生成案例卡片 -->
              <div v-if="msg.type === 'case_generated' && msg.case" class="gen-case-card">
                <div class="gcc-header">
                  <h3>{{ msg.case.title }}</h3>
                  <span class="gcc-badge" :class="riskClass(msg.case.risk_level)">{{ msg.case.risk_level }}风险</span>
                </div>
                <div class="gcc-meta">
                  <span>📂 {{ msg.case.case_type }}</span>
                  <span>⚠️ {{ msg.case.violation_behavior }}</span>
                  <span>📜 {{ msg.case.violated_law }}</span>
                </div>
                <div class="gcc-section">
                  <h4>📋 案件背景</h4>
                  <p>{{ msg.case.background }}</p>
                </div>
                <div class="gcc-section">
                  <h4>🚨 违法行为描述</h4>
                  <p>{{ msg.case.behavior_description }}</p>
                </div>
                <div v-if="msg.case.subjects?.length" class="gcc-section">
                  <h4>👥 涉及主体</h4>
                  <div class="gcc-subjects">
                    <span v-for="s in msg.case.subjects" :key="s" class="subject-tag">{{ s }}</span>
                  </div>
                </div>
                <div class="gcc-section">
                  <h4>⚖️ 法律分析</h4>
                  <p>{{ msg.case.legal_analysis }}</p>
                </div>
                <div class="gcc-section">
                  <h4>✅ 审查结论</h4>
                  <p>{{ msg.case.review_conclusion }}</p>
                </div>
                <div v-if="msg.case.penalty_reference" class="gcc-section">
                  <h4>💊 处罚参考</h4>
                  <p>{{ msg.case.penalty_reference }}</p>
                </div>
                <div v-if="msg.case.keywords?.length" class="gcc-keywords">
                  <span v-for="kw in msg.case.keywords" :key="kw" class="kw-tag">{{ kw }}</span>
                </div>
              </div>

              <!-- 校验结果 -->
              <div v-if="msg.type === 'verification_result'" class="verify-bar" :class="{ passed: msg.passed, failed: !msg.passed }">
                <span>{{ msg.passed ? "✅" : "⚠️" }}</span>
                <span>校验{{ msg.passed ? "通过" : "未通过" }} ({{ (msg.overall_score || 0).toFixed(0) }}分)</span>
                <span v-if="msg.warnings?.length" class="verify-warnings">
                  {{ msg.warnings.join("; ") }}
                </span>
              </div>

              <!-- 保存按钮 -->
              <div v-if="msg.type === 'done' && msg.case" class="save-bar">
                <button class="btn-save" :class="{ saved: savedCaseId }" :disabled="saving || savedCaseId" @click="saveCase(msg.case)">
                  {{ savedCaseId ? "✅ 已存入记忆库" : saving ? "保存中..." : "💾 存入案例记忆库" }}
                </button>
              </div>

              <!-- 普通文本 -->
              <p v-if="msg.text && !msg.progress && !msg.case" class="msg-text">{{ msg.text }}</p>
            </div>
          </div>
        </template>

        <!-- 生成中动画 -->
        <div v-if="generating && !messages.length" class="chat-msg system">
          <div class="msg-avatar">🤖</div>
          <div class="msg-body">
            <span class="typing-dots"><span>.</span><span>.</span><span>.</span></span>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="chat-input-area">
        <!-- 条件配置面板 -->
        <div class="config-panel">
          <div class="config-row">
            <div class="config-field">
              <label>违法行为</label>
              <input v-model="form.violation_behavior" placeholder="如: 地域限制、限定交易..." list="behaviors-list" @keydown.enter="generate" />
              <datalist id="behaviors-list">
                <option v-for="b in quickBehaviors" :key="b" :value="b" />
              </datalist>
            </div>
            <div class="config-field">
              <label>违反法条</label>
              <div class="cascade-law-select">
                <select v-model="selectedLaw" @change="onLawChange" class="law-select">
                  <option value="">选择法律...</option>
                  <option v-for="l in availableLaws" :key="l.law_name" :value="l.law_name">{{ l.law_name }}</option>
                </select>
                <select v-model="selectedArticle" @change="onArticleChange" class="article-select" :disabled="!selectedLaw || loadingArticles">
                  <option value="">{{ loadingArticles ? "加载中..." : selectedLaw ? "选择条文..." : "请先选择法律" }}</option>
                  <option v-for="a in availableArticles" :key="a.article_number" :value="a.article_number">
                    {{ a.article_number }} — {{ a.content.slice(0, 50) }}{{ a.content.length > 50 ? "..." : "" }}
                  </option>
                </select>
              </div>
            </div>
            <div class="config-field">
              <label>案件类型</label>
              <input v-model="form.case_type" placeholder="如: 政府采购、招投标..." list="types-list" @keydown.enter="generate" />
              <datalist id="types-list">
                <option v-for="t in quickTypes" :key="t" :value="t" />
              </datalist>
            </div>
          </div>
          <div class="config-row config-row-2">
            <div class="config-field">
              <label>风险等级</label>
              <select v-model="form.risk_level">
                <option value="">自动判断</option>
                <option value="高">高风险</option>
                <option value="中">中风险</option>
                <option value="低">低风险</option>
              </select>
            </div>
            <div class="config-field">
              <label>生成风格</label>
              <select v-model="form.style">
                <option value="真实案例风格">真实案例风格</option>
                <option value="行政处罚风格">行政处罚风格</option>
                <option value="法院判决风格">法院判决风格</option>
              </select>
            </div>
            <div class="config-field config-field-grow">
              <label>补充描述</label>
              <input v-model="form.user_message" placeholder="自由描述案例需求..." @keydown.enter="generate" />
            </div>
          </div>
        </div>

        <!-- 快捷标签 -->
        <div class="quick-chips">
          <span class="chips-label">快捷填入:</span>
          <button v-for="b in quickBehaviors.slice(0, 6)" :key="b" class="q-chip" @click="form.violation_behavior = b">{{ b }}</button>
        </div>

        <!-- 发送按钮 -->
        <button class="btn-generate" @click="generate" :disabled="generating">
          {{ generating ? "生成中..." : "🔄 生成案例" }}
        </button>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, nextTick, watch } from "vue";
import { searchLawsSemantic, type LawSearchHit, getTxtLaws, getTxtLawArticles, type TxtLawInfo, type TxtLawArticle } from "../services/api";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface ChatMessage {
  role: "system" | "user";
  text?: string;
  type?: string;
  icon?: string;
  progress?: string;
  tags?: string[];
  case?: any;
  laws?: any[];
  cases?: any[];
  count?: number;
  passed?: boolean;
  overall_score?: number;
  warnings?: string[];
  [key: string]: any;
}

const messages = ref<ChatMessage[]>([]);
const generating = ref(false);
const saving = ref(false);
const savedCaseId = ref("");
const messagesEl = ref<HTMLElement>();

const form = ref({
  violation_behavior: "",
  violated_law: "",
  case_type: "",
  risk_level: "",
  style: "真实案例风格",
  user_message: "",
});

// 法条级联选择：先选法律 → 再选条文
const availableLaws = ref<TxtLawInfo[]>([]);
const selectedLaw = ref("");
const availableArticles = ref<TxtLawArticle[]>([]);
const selectedArticle = ref("");
const loadingArticles = ref(false);

async function loadLaws() {
  try {
    availableLaws.value = await getTxtLaws();
  } catch { /* ignore */ }
}
loadLaws();

async function onLawChange() {
  selectedArticle.value = "";
  availableArticles.value = [];
  form.value.violated_law = "";
  if (!selectedLaw.value) return;

  loadingArticles.value = true;
  try {
    availableArticles.value = await getTxtLawArticles(selectedLaw.value);
  } catch {
    availableArticles.value = [];
  } finally {
    loadingArticles.value = false;
  }
}

function onArticleChange() {
  if (selectedLaw.value && selectedArticle.value) {
    // 将全称映射为简称
    const shortMap: Record<string, string> = {
      "中华人民共和国反垄断法": "《反垄断法》",
      "中华人民共和国反不正当竞争法": "《反不正当竞争法》",
      "中华人民共和国招标投标法": "《招标投标法》",
      "中华人民共和国政府采购法": "《政府采购法》",
      "中华人民共和国价格法": "《价格法》",
      "中华人民共和国电子商务法": "《电子商务法》",
    };
    const short = shortMap[selectedLaw.value] || selectedLaw.value;
    form.value.violated_law = `${short} ${selectedArticle.value}`;
  }
}

const quickBehaviors = [
  "地域限制", "限定交易", "拒绝交易", "差别待遇", "搭售",
  "串通投标", "虚假宣传", "商业贿赂", "低价倾销", "价格歧视",
  "联合抵制", "固定价格", "划分市场",
];

const quickLaws = [
  "《反垄断法》第二十二条", "《反垄断法》第十七条", "《反垄断法》第四十二条",
  "《反垄断法》第十八条", "《反不正当竞争法》第八条", "《反不正当竞争法》第十二条",
  "《招标投标法》第三十二条", "《招标投标法》第五十三条", "《政府采购法》第七十七条",
  "《电子商务法》第三十五条",
];

const quickTypes = [
  "政府采购", "招标投标", "市场竞争", "电商平台", "企业经营", "行政垄断",
];

const progressIcons: Record<string, string> = {
  config_resolved: "📋",
  laws_retrieved: "📜",
  cases_retrieved: "📁",
  rag_built: "🧠",
  prompt_built: "📝",
  case_generated: "✨",
  verification_result: "🔍",
  done: "✅",
  generation_error: "❌",
};

const progressLabels: Record<string, string> = {
  config_resolved: "正在解析生成条件...",
  laws_retrieved: "正在检索相关法律法规...",
  cases_retrieved: "正在检索相似历史案例...",
  rag_built: "正在构建 RAG 上下文...",
  prompt_built: "正在构建生成提示词...",
  case_generated: "案例已生成！",
  verification_result: "校验结果",
  done: "生成完成",
  generation_error: "生成出错",
};

function riskClass(level: string) {
  if (level === "高") return "risk-high";
  if (level === "中") return "risk-mid";
  return "risk-low";
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
    }
  });
}

async function generate() {
  const f = form.value;
  if (!f.violation_behavior && !f.violated_law && !f.case_type && !f.user_message) return;

  generating.value = true;
  savedCaseId.value = "";
  messages.value = [];

  // 添加用户消息
  const userParts = [];
  if (f.violation_behavior) userParts.push(`违法行为: ${f.violation_behavior}`);
  if (f.violated_law) userParts.push(`违反法条: ${f.violated_law}`);
  if (f.case_type) userParts.push(`案件类型: ${f.case_type}`);
  if (f.risk_level) userParts.push(`风险等级: ${f.risk_level}`);
  if (f.user_message) userParts.push(f.user_message);

  if (userParts.length) {
    messages.value.push({
      role: "user",
      text: userParts.join("\n") || "生成一个法律案例",
    });
  }
  scrollToBottom();

  try {
    const res = await fetch(`${baseURL}/case/generate/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(f),
    });

    if (!res.ok) {
      const err = await res.text().catch(() => "");
      throw new Error(err || "请求失败");
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary).trim();
        buffer = buffer.slice(boundary + 2);

        if (raw.startsWith("data:")) {
          const payload = raw.slice(5).trim();
          if (payload) {
            try {
              const event = JSON.parse(payload);
              handleEvent(event);
            } catch { /* parse error */ }
          }
        }
        boundary = buffer.indexOf("\n\n");
      }

      if (done) break;
    }
  } catch (e: any) {
    messages.value.push({
      role: "system",
      text: "生成失败: " + (e.message || "未知错误"),
      type: "generation_error",
    });
  } finally {
    generating.value = false;
    scrollToBottom();
  }
}

function handleEvent(event: any) {
  const type = event.type;

  if (type === "config_resolved") {
    const config = event.config || {};
    const tags = [config.violation_behavior, config.violated_law, config.case_type, config.style].filter(Boolean);
    messages.value.push({
      role: "system",
      progress: type,
      icon: progressIcons[type] || "📌",
      type: type,
      tags,
      text: `生成条件已确认: ${tags.join(" · ")}`,
    });
  } else if (type === "laws_retrieved" || type === "cases_retrieved") {
    messages.value.push({
      role: "system",
      progress: type,
      icon: progressIcons[type] || "📌",
      type: type,
      count: event.count,
      laws: event.laws,
      cases: event.cases,
      text: progressLabels[type] || type,
    });
  } else if (type === "rag_built" || type === "prompt_built" || type === "case_generated") {
    const msg: ChatMessage = {
      role: "system",
      progress: type,
      icon: progressIcons[type] || "📌",
      type: type,
      text: progressLabels[type] || type,
    };
    if (type === "case_generated") {
      msg.case = event.case;
    }
    messages.value.push(msg);
  } else if (type === "verification_result") {
    messages.value.push({
      role: "system",
      progress: type,
      icon: progressIcons[type] || "📌",
      type: type,
      passed: event.passed,
      overall_score: event.overall_score,
      warnings: event.warnings,
      text: progressLabels[type] || type,
    });
  } else if (type === "done") {
    messages.value.push({
      role: "system",
      type: type,
      case: event.case,
      text: progressLabels[type] || type,
    });
  } else if (type === "generation_error" || type === "error") {
    messages.value.push({
      role: "system",
      text: event.detail || "生成失败",
      type: "generation_error",
    });
  }
  scrollToBottom();
}

async function saveCase(caseData: any) {
  saving.value = true;
  try {
    const res = await fetch(`${baseURL}/case/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case: caseData }),
    });
    if (!res.ok) throw new Error("保存失败");
    savedCaseId.value = (await res.json()).case_id;
  } catch (e: any) {
    messages.value.push({
      role: "system",
      text: "保存失败: " + (e.message || ""),
      type: "generation_error",
    });
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.case-gen-page {
  display: flex;
  justify-content: center;
  height: calc(100vh - 64px);
}

.chat-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 900px;
  height: 100%;
}

/* 消息区域 */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chat-msg {
  display: flex;
  gap: 12px;
  max-width: 95%;
}

.chat-msg.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.chat-msg.system {
  align-self: flex-start;
}

.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 18px;
  flex-shrink: 0;
  background: #f1f5f9;
}

.chat-msg.user .msg-avatar {
  background: rgba(201,168,76,0.15);
}

.msg-body {
  background: #fff;
  border: 1px solid rgba(148,163,184,0.15);
  border-radius: 16px;
  padding: 14px 18px;
  font-size: 14px;
  color: #1e3a5f;
  line-height: 1.6;
  min-width: 0;
}

.chat-msg.user .msg-body {
  background: rgba(30,58,95,0.04);
  border-color: rgba(30,58,95,0.1);
}

.msg-body > p { margin: 0 0 6px; }
.msg-body > p:last-child { margin-bottom: 0; }

.msg-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
}

/* 进度消息 */
.progress-msg {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #64748b;
  flex-wrap: wrap;
}

.progress-icon { font-size: 16px; }

.progress-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-left: 4px;
}

.p-tag {
  font-size: 11px;
  padding: 1px 8px;
  background: rgba(201,168,76,0.1);
  color: #8b7318;
  border-radius: 6px;
}

/* 检索摘要 */
.retrieval-summary {
  margin-top: 6px;
}

.rs-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e3a5f;
  margin-bottom: 6px;
}

.rs-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.rs-chip {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(30,58,95,0.06);
  color: #1e3a5f;
  border-radius: 6px;
}

/* 打字动画 */
.typing-dots span {
  display: inline-block;
  animation: blink 1.4s infinite both;
  font-size: 24px;
  line-height: 1;
  color: #94a3b8;
}

.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes blink {
  0%, 80%, 100% { opacity: 0; }
  40% { opacity: 1; }
}

/* 生成案例卡片 */
.gen-case-card {
  margin-top: 8px;
}

.gcc-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.gcc-header h3 {
  margin: 0;
  font-size: 16px;
  color: #1e3a5f;
}

.gcc-badge {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.gcc-badge.risk-high { background: rgba(220,38,38,0.1); color: #dc2626; }
.gcc-badge.risk-mid { background: rgba(201,168,76,0.12); color: #8b7318; }
.gcc-badge.risk-low { background: rgba(34,197,94,0.1); color: #15803d; }

.gcc-meta {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(148,163,184,0.12);
}

.gcc-section {
  margin-bottom: 12px;
}

.gcc-section h4 {
  margin: 0 0 4px;
  font-size: 13px;
  color: #1e3a5f;
}

.gcc-section p {
  margin: 0;
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
}

.gcc-subjects {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.subject-tag {
  font-size: 12px;
  padding: 2px 10px;
  background: rgba(30,58,95,0.06);
  color: #1e3a5f;
  border-radius: 8px;
}

.gcc-keywords {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(148,163,184,0.12);
}

.kw-tag {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(201,168,76,0.06);
  color: #8b7318;
  border-radius: 6px;
}

/* 校验结果 */
.verify-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  flex-wrap: wrap;
}

.verify-bar.passed {
  background: rgba(34,197,94,0.06);
  border: 1px solid rgba(34,197,94,0.15);
}

.verify-bar.failed {
  background: rgba(220,38,38,0.05);
  border: 1px solid rgba(220,38,38,0.12);
}

.verify-warnings {
  font-size: 12px;
  color: #b91c1c;
  margin-left: 4px;
}

/* 保存 */
.save-bar {
  margin-top: 12px;
}

.btn-save {
  padding: 8px 20px;
  font-size: 13px;
  font-weight: 600;
  background: #1e3a5f;
  color: #fff;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-save:hover:not(:disabled) { background: #152d4a; }
.btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-save.saved { background: #15803d; }

/* 输入区域 */
.chat-input-area {
  border-top: 1px solid rgba(148,163,184,0.15);
  padding: 16px 0 8px;
}

.config-panel {
  margin-bottom: 10px;
}

.config-row {
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}

.config-field {
  flex: 1;
  min-width: 0;
}

.config-field label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 4px;
}

.config-field input,
.config-field select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  box-sizing: border-box;
}

.config-field input:focus,
.config-field select:focus {
  border-color: #c9a84c;
}

.config-field select {
  background: #fff;
  cursor: pointer;
}

.config-field-grow {
  flex: 2;
}

/* 法条级联选择 */
.cascade-law-select {
  display: flex;
  gap: 6px;
}

.law-select,
.article-select {
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  background: #fff;
  cursor: pointer;
  box-sizing: border-box;
}

.law-select {
  flex: 0 0 40%;
  min-width: 0;
}

.article-select {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.law-select:focus,
.article-select:focus {
  border-color: #c9a84c;
}

.article-select:disabled {
  background: #f8fafc;
  color: #94a3b8;
  cursor: not-allowed;
}

/* 快捷标签 */
.quick-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.chips-label {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
}

.q-chip {
  padding: 3px 10px;
  font-size: 11px;
  background: #fff;
  color: #475569;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.q-chip:hover {
  border-color: #c9a84c;
  color: #8b7318;
}

.q-chip.law {
  background: rgba(201,168,76,0.04);
  border-color: rgba(201,168,76,0.2);
}

.chips-sep {
  font-size: 12px;
  color: #e2e8f0;
}

/* 生成按钮 */
.btn-generate {
  width: 100%;
  padding: 12px;
  font-size: 15px;
  font-weight: 700;
  background: linear-gradient(135deg, #1e3a5f, #c9a84c);
  color: #fff;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-generate:hover:not(:disabled) {
  box-shadow: 0 4px 16px rgba(201,168,76,0.25);
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .config-row {
    flex-direction: column;
    gap: 6px;
  }
  .case-gen-page {
    height: auto;
    min-height: 100vh;
  }
}
</style>
