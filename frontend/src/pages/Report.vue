<template>
  <div class="report-page">
    <button class="back-link" @click="$router.push('/history')">← 返回历史案例库</button>
    <h1>📄 研究报告</h1>
    <p class="subtitle">研究 ID: {{ $route.params.id }}</p>

    <div class="report-body">
      <pre class="report-content" v-if="reportText">{{ reportText }}</pre>
      <div v-else class="empty-state">
        <span>📭</span>
        <p>报告内容暂未存储。请从研究页面完成一次研究后查看。</p>
      </div>
    </div>

    <div class="export-bar" v-if="reportText">
      <span class="hint">导出功能开发中，当前支持复制文本</span>
      <button class="btn-copy" @click="copyReport">复制报告内容</button>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from "vue";

const reportText = ref("");

onMounted(() => {
  // 尝试从 localStorage 加载报告
  const stored = localStorage.getItem("law_research_report");
  if (stored) reportText.value = stored;
});

async function copyReport() {
  try {
    await navigator.clipboard.writeText(reportText.value);
    alert("报告已复制到剪贴板");
  } catch {
    const ta = document.createElement("textarea");
    ta.value = reportText.value;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}
</script>

<style scoped>
.report-page { max-width: 900px; }
.back-link { background: none; border: none; color: #64748b; cursor: pointer; font-size: 13px; padding: 0; margin-bottom: 12px; display: block; }
.back-link:hover { color: #1e3a5f; }
.report-page h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
.subtitle { margin: 0 0 20px; color: #64748b; font-size: 13px; }

.report-body {
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 16px;
  padding: 28px; min-height: 400px;
}

.report-content {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-break: break-word;
  color: #1f2937;
}

.empty-state { text-align: center; padding: 60px 0; color: #94a3b8; }
.empty-state span { font-size: 48px; display: block; margin-bottom: 12px; }

.export-bar {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 16px; padding: 14px 18px;
  background: #fff; border: 1px solid rgba(148,163,184,0.12); border-radius: 12px;
}
.hint { font-size: 13px; color: #94a3b8; }
.btn-copy {
  padding: 8px 18px; border: 1px solid rgba(30,58,95,0.2); border-radius: 10px;
  background: #fff; color: #1e3a5f; cursor: pointer; font-size: 13px;
}
.btn-copy:hover { background: rgba(30,58,95,0.04); }
</style>
