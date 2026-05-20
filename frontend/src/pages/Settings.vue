<template>
  <div class="settings-page">
    <h1>⚙️ 系统设置</h1>
    <p class="subtitle">当前后端配置与模型信息</p>

    <div class="config-grid">
      <div class="config-card">
        <h3>LLM 配置</h3>
        <div class="config-row">
          <span class="config-key">提供商</span>
          <span class="config-value">{{ config.llmProvider || "未配置" }}</span>
        </div>
        <div class="config-row">
          <span class="config-key">模型</span>
          <span class="config-value">{{ config.modelId || "未配置" }}</span>
        </div>
        <div class="config-row">
          <span class="config-key">API 端点</span>
          <span class="config-value">DashScope (百炼原生)</span>
        </div>
      </div>

      <div class="config-card">
        <h3>搜索引擎</h3>
        <div class="config-row">
          <span class="config-key">后端</span>
          <span class="config-value">{{ config.searchApi || "默认" }}</span>
        </div>
        <div class="config-row">
          <span class="config-key">最大检索轮次</span>
          <span class="config-value">{{ config.maxLoops || 3 }}</span>
        </div>
      </div>

      <div class="config-card">
        <h3>后端服务</h3>
        <div class="config-row">
          <span class="config-key">地址</span>
          <span class="config-value">{{ baseURL }}</span>
        </div>
        <div class="config-row">
          <span class="config-key">状态</span>
          <span class="config-value" :class="{ online: backendOnline, offline: !backendOnline }">
            {{ backendOnline ? "在线" : "离线" }}
          </span>
        </div>
      </div>

      <div class="config-card wip-card">
        <h3>功能状态</h3>
        <div class="feature-status">
          <span>法律研究（规划 → 检索 → 总结 → 报告）</span>
          <span class="tag tag-done">已实现</span>
        </div>
        <div class="feature-status">
          <span>案例解析（BERT + NER）</span>
          <span class="tag tag-wip">开发中</span>
        </div>
        <div class="feature-status">
          <span>法规检索（向量库 + RAG）</span>
          <span class="tag tag-wip">开发中</span>
        </div>
        <div class="feature-status">
          <span>合规审查（违规检测 + 事实校验）</span>
          <span class="tag tag-wip">开发中</span>
        </div>
        <div class="feature-status">
          <span>报告导出（PDF / Word / MD）</span>
          <span class="tag tag-wip">开发中</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from "vue";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const backendOnline = ref(false);
const config = ref<Record<string, string>>({});

onMounted(async () => {
  try {
    const res = await fetch(`${baseURL}/healthz`);
    backendOnline.value = res.ok;
  } catch {
    backendOnline.value = false;
  }

  // Read config from localStorage or defaults
  config.value = {
    llmProvider: "custom (百炼)",
    modelId: "qwen-max",
    searchApi: "tavily",
    maxLoops: "3",
  };
});
</script>

<style scoped>
.settings-page {
  max-width: 900px;
}

.settings-page h1 {
  margin: 0 0 4px;
  font-size: 24px;
  color: #1e3a5f;
}

.subtitle {
  margin: 0 0 28px;
  color: #64748b;
  font-size: 14px;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.config-card {
  background: #fff;
  border: 1px solid rgba(148,163,184,0.18);
  border-radius: 16px;
  padding: 22px;
}

.config-card h3 {
  margin: 0 0 14px;
  font-size: 15px;
  color: #1e3a5f;
  font-weight: 600;
}

.config-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgba(148,163,184,0.08);
}

.config-row:last-child {
  border-bottom: none;
}

.config-key {
  font-size: 13px;
  color: #64748b;
}

.config-value {
  font-size: 13px;
  font-weight: 500;
  color: #1e3a5f;
}

.config-value.online { color: #15803d; }
.config-value.offline { color: #b91c1c; }

.wip-card {
  grid-column: 1 / -1;
}

.feature-status {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid rgba(148,163,184,0.06);
  font-size: 13px;
}

.feature-status:last-child { border-bottom: none; }

.tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 8px;
  font-weight: 600;
}

.tag-done {
  background: rgba(34,197,94,0.1);
  color: #15803d;
}

.tag-wip {
  background: rgba(201,168,76,0.15);
  color: #8b7318;
}

@media (max-width: 640px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
