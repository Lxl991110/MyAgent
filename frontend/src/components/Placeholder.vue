<template>
  <div class="placeholder-page">
    <div class="placeholder-card">
      <div class="placeholder-icon">{{ icon }}</div>
      <h2>{{ title }}</h2>
      <p class="placeholder-desc">{{ description }}</p>
      <div class="feature-list" v-if="features.length">
        <span v-for="f in features" :key="f" class="feature-tag">{{ f }}</span>
      </div>
      <div class="wip-banner">
        <span class="wip-icon">🚧</span>
        功能暂未实现 — 后端智能体开发中
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
defineProps<{
  icon: string;
  title: string;
  description: string;
  features: string[];
}>();
</script>

<style scoped>
.placeholder-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 64px);
}

.placeholder-card {
  text-align: center;
  max-width: 520px;
  padding: 48px 40px;
  background: #fff;
  border-radius: 20px;
  border: 1px solid rgba(148,163,184,0.2);
  box-shadow: 0 8px 32px rgba(15,23,42,0.06);
}

.placeholder-icon {
  font-size: 56px;
  margin-bottom: 16px;
}

.placeholder-card h2 {
  margin: 0 0 8px;
  font-size: 22px;
  color: #1e3a5f;
}

.placeholder-desc {
  margin: 0 0 20px;
  color: #64748b;
  font-size: 14px;
  line-height: 1.6;
}

.feature-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-bottom: 24px;
}

.feature-tag {
  padding: 4px 12px;
  background: rgba(30,58,95,0.05);
  border: 1px solid rgba(30,58,95,0.12);
  border-radius: 8px;
  font-size: 12px;
  color: #1e3a5f;
}

.wip-banner {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  background: rgba(201,168,76,0.1);
  border: 1px solid rgba(201,168,76,0.25);
  border-radius: 12px;
  font-size: 13px;
  color: #8b7318;
  font-weight: 500;
}
</style>
