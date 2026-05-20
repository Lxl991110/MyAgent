<template>
  <Placeholder
    icon="⚖️"
    title="合规审查"
    description="基于违规检测模型与事实校验引擎，自动判断案例合规性，输出风险等级、违规依据与整改建议。"
    :features="['违规点自动检测', '风险仪表盘', '事实校验', '审查依据溯源', '去幻觉校验']"
  />
</template>

<script lang="ts" setup>
import Placeholder from "../components/Placeholder.vue";
</script>
