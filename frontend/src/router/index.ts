import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "dashboard",
      component: () => import("../pages/Dashboard.vue"),
    },
    {
      path: "/research",
      name: "research",
      component: () => import("../pages/Research.vue"),
    },
    {
      path: "/research/:id/report",
      name: "report",
      component: () => import("../pages/Report.vue"),
    },
    {
      path: "/case-parse",
      name: "case-parse",
      component: () => import("../pages/CaseParse.vue"),
    },
    {
      path: "/regulation-search",
      name: "regulation-search",
      component: () => import("../pages/RegulationSearch.vue"),
    },
    {
      path: "/compliance-review",
      name: "compliance-review",
      component: () => import("../pages/ComplianceReview.vue"),
    },
    {
      path: "/workflow",
      name: "workflow",
      component: () => import("../pages/Workflow.vue"),
    },
    {
      path: "/history",
      name: "history",
      component: () => import("../pages/History.vue"),
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../pages/Settings.vue"),
    },
  ],
});

export default router;
