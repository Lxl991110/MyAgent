<template>
  <Placeholder
    icon="📁"
    title="历史案例库"
    description="存储与检索历史审查案例，查看案例与法条的关联关系，支持筛选、排序与批量导入。"
    :features="['案例列表与检索', '法条关联图谱', '案例详情回看', '批量导入导出']"
  />
</template>

<script lang="ts" setup>
import Placeholder from "../components/Placeholder.vue";
</script>
