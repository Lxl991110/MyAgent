<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 2L3 7v10l9 5 9-5V7L12 2zm0 2.8L18.5 7 12 10.2 5.5 7 12 4.8zM5 8.5l6 3v8.2l-6-3.3V8.5zm8 0l6 3v7.9l-6 3.3V11.5z" fill="currentColor"/>
            <circle cx="12" cy="12" r="1.2" fill="currentColor" opacity="0.9"/>
          </svg>
        </div>
        <span class="brand-text">法律研究 Agent</span>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-section">
          <span class="nav-label">核心功能</span>
          <router-link to="/" class="nav-item" active-class="active" exact>
            <span class="nav-icon">🏠</span> 工作台
          </router-link>
          <router-link to="/research" class="nav-item" active-class="active">
            <span class="nav-icon">🔍</span> 法律研究
          </router-link>
          <router-link to="/workflow" class="nav-item" active-class="active">
            <span class="nav-icon">🔀</span> 工作流可视化
          </router-link>
        </div>

        <div class="nav-section">
          <span class="nav-label">智能体模块</span>
          <router-link to="/case-parse" class="nav-item" active-class="active">
            <span class="nav-icon">📋</span> 案例解析
          </router-link>
          <router-link to="/regulation-search" class="nav-item" active-class="active">
            <span class="nav-icon">📜</span> 法规检索
          </router-link>
          <router-link to="/compliance-review" class="nav-item" active-class="active">
            <span class="nav-icon">⚖️</span> 合规审查
          </router-link>
          <router-link to="/case-generate" class="nav-item" active-class="active">
            <span class="nav-icon">📝</span> 案例生成
          </router-link>
        </div>

        <div class="nav-section">
          <span class="nav-label">其他</span>
          <router-link to="/history" class="nav-item" active-class="active">
            <span class="nav-icon">📁</span> 历史案例库
          </router-link>
          <router-link to="/settings" class="nav-item" active-class="active">
            <span class="nav-icon">⚙️</span> 系统设置
          </router-link>
        </div>
      </nav>

      <div class="sidebar-footer">
        <span class="status-dot"></span>
        <span>后端: {{ backendStatus }}</span>
      </div>
    </aside>

    <main class="main-content">
      <slot />
    </main>
  </div>
</template>

<script lang="ts" setup>
import { ref, onMounted } from "vue";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const backendStatus = ref("检测中...");

onMounted(async () => {
  try {
    const res = await fetch(`${baseURL}/healthz`);
    if (res.ok) {
      backendStatus.value = "在线";
    } else {
      backendStatus.value = "异常";
    }
  } catch {
    backendStatus.value = "离线";
  }
});
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
  background: #fafaf9;
}

.sidebar {
  width: 260px;
  min-width: 260px;
  height: 100vh;
  position: sticky;
  top: 0;
  background: linear-gradient(180deg, #1e3a5f 0%, #152d4a 100%);
  color: #e2e8f0;
  display: flex;
  flex-direction: column;
  padding: 24px 0;
  overflow-y: auto;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  margin-bottom: 16px;
}

.brand-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: linear-gradient(135deg, #c9a84c, #e0c878);
}

.brand-icon svg {
  width: 22px;
  height: 22px;
  color: #1e3a5f;
}

.brand-text {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: #f1f5f9;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0 12px;
}

.nav-section {
  margin-bottom: 16px;
}

.nav-label {
  display: block;
  padding: 8px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(255,255,255,0.35);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  color: rgba(255,255,255,0.7);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s ease;
  margin-bottom: 2px;
}

.nav-item:hover {
  background: rgba(255,255,255,0.06);
  color: #f1f5f9;
}

.nav-item.active {
  background: rgba(201,168,76,0.15);
  color: #c9a84c;
  font-weight: 600;
}

.nav-icon {
  font-size: 16px;
  width: 24px;
  text-align: center;
}

.badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 6px;
  font-weight: 600;
  letter-spacing: 0.03em;
}

.badge-wip {
  background: rgba(201,168,76,0.2);
  color: #c9a84c;
  margin-left: auto;
}

.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px 0;
  border-top: 1px solid rgba(255,255,255,0.06);
  font-size: 12px;
  color: rgba(255,255,255,0.4);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 32px;
}

@media (max-width: 768px) {
  .sidebar {
    width: 200px;
    min-width: 200px;
  }
  .main-content {
    padding: 20px;
  }
}
</style>
