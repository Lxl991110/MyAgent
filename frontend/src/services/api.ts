const baseURL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// ── 案例解析 ────────────────────────────────────────────────────────────────

export interface CaseParseRequest {
  text: string;
  use_bert?: boolean;
}

export interface CaseParseResponse {
  success: boolean;
  case_id: string;
  case_type: string;
  subjects: string[];
  behaviors: string[];
  amount: string;
  region: string;
  time_period: string;
  related_laws: string[];
  risk_tags: string[];
  description: string;
  entities: { type: string; value: string; confidence: number }[];
  preprocess_info: Record<string, unknown>;
  errors: string[];
}

export interface LawEntry {
  law_id: string;
  law_name: string;
  article_number: string;
  content: string;
  chapter?: string;
  enforcement_level?: string;
  score?: number;
}

export interface CaseEntry {
  case_id: string;
  case_type: string;
  subjects: string[];
  behaviors: string[];
  related_laws: string[];
  risk_tags: string[];
  description: string;
}

export async function parseCase(payload: CaseParseRequest): Promise<CaseParseResponse> {
  const res = await fetch(`${baseURL}/case/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    throw new Error(err || "案例解析请求失败");
  }
  return res.json();
}

export async function searchLaws(query: string): Promise<LawEntry[]> {
  const params = new URLSearchParams({ search: query });
  const res = await fetch(`${baseURL}/case/knowledge-base/laws?${params}`);
  if (!res.ok) throw new Error("法条检索失败");
  return res.json();
}

export async function listLaws(): Promise<LawEntry[]> {
  const res = await fetch(`${baseURL}/case/knowledge-base/laws`);
  if (!res.ok) throw new Error("获取法条列表失败");
  return res.json();
}

// ── 法规检索（Qdrant 语义 + 分类）────────────────────────────────────────

export interface LawSearchHit {
  law_id: string;
  law_name: string;
  article_number: string;
  content: string;
  chapter: string;
  category: string;
  keywords: string[];
  enforcement_level: string;
  issuing_authority: string;
  score: number;
}

export interface LawRouteResult {
  categories: string[];
  preferred_laws: string[];
  detected_law_name: string | null;
  suggested_filter: Record<string, unknown>;
}

export interface LawSearchResponse {
  hits: LawSearchHit[];
  total: number;
  route: LawRouteResult;
}

export async function searchLawsSemantic(
  q: string,
  options?: { category?: string; law_name?: string; top_k?: number; auto_route?: boolean }
): Promise<LawSearchResponse> {
  const params = new URLSearchParams({ q, top_k: String(options?.top_k || 10) });
  if (options?.category) params.set("category", options.category);
  if (options?.law_name) params.set("law_name", options.law_name);
  if (options?.auto_route !== undefined) params.set("auto_route", String(options.auto_route));
  const res = await fetch(`${baseURL}/laws/search?${params}`);
  if (!res.ok) throw new Error("法规检索失败");
  return res.json();
}

export async function listCategories(): Promise<{
  categories: string[];
  counts: Record<string, number>;
  total_indexed: number;
}> {
  const res = await fetch(`${baseURL}/laws/categories`);
  if (!res.ok) throw new Error("获取分类列表失败");
  return res.json();
}

export async function getArticle(
  law_name: string,
  article_number: string
): Promise<LawSearchHit> {
  const params = new URLSearchParams({ law_name, article_number });
  const res = await fetch(`${baseURL}/laws/article?${params}`);
  if (!res.ok) throw new Error("法条查找失败");
  return res.json();
}

export async function analyzeQuery(q: string): Promise<LawRouteResult> {
  const params = new URLSearchParams({ q });
  const res = await fetch(`${baseURL}/laws/route?${params}`);
  if (!res.ok) throw new Error("查询分析失败");
  return res.json();
}

export async function listCases(): Promise<CaseEntry[]> {
  const res = await fetch(`${baseURL}/case/knowledge-base/cases`);
  if (!res.ok) throw new Error("获取案例列表失败");
  return res.json();
}

// ── 法律研究（已有）──────────────────────────────────────────────────────────

export interface ResearchRequest {
  topic: string;
  case_text?: string;
  search_api?: string;
}

export interface ResearchStreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface StreamOptions {
  signal?: AbortSignal;
}

export async function runResearchStream(
  payload: ResearchRequest,
  onEvent: (event: ResearchStreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  const response = await fetch(`${baseURL}/research/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream"
    },
    body: JSON.stringify(payload),
    signal: options.signal
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(
      errorText || `研究请求失败，状态码：${response.status}`
    );
  }

  const body = response.body;
  if (!body) {
    throw new Error("浏览器不支持流式响应，无法获取研究进度");
  }

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);

      if (rawEvent.startsWith("data:")) {
        const dataPayload = rawEvent.slice(5).trim();
        if (dataPayload) {
          try {
            const event = JSON.parse(dataPayload) as ResearchStreamEvent;
            onEvent(event);

            if (event.type === "error" || event.type === "done") {
              return;
            }
          } catch (error) {
            console.error("解析流式事件失败：", error, dataPayload);
          }
        }
      }

      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      // 处理可能的尾巴事件
      if (buffer.trim()) {
        const rawEvent = buffer.trim();
        if (rawEvent.startsWith("data:")) {
          const dataPayload = rawEvent.slice(5).trim();
          if (dataPayload) {
            try {
              const event = JSON.parse(dataPayload) as ResearchStreamEvent;
              onEvent(event);
            } catch (error) {
              console.error("解析流式事件失败：", error, dataPayload);
            }
          }
        }
      }
      break;
    }
  }
}

// ── 合规审查 ───────────────────────────────────────────────────────────────

export interface ComplianceReviewRequest {
  text: string;
  context?: string;
  use_rag?: boolean;
  override_laws?: {
    law_name: string;
    article: string;
    content: string;
    score?: number;
  }[];
}

export interface ComplianceReviewResponse {
  risk_level: string;
  violations: {
    type: string;
    matched_keywords: string[];
    count: number;
    relevant_laws: string[];
    severity: string;
  }[];
  relevant_laws: {
    law_name: string;
    article: string;
    content: string;
    score: number;
  }[];
  suggestions: string[];
  review_summary: string;
}

export async function reviewCompliance(
  payload: ComplianceReviewRequest
): Promise<ComplianceReviewResponse> {
  const res = await fetch(`${baseURL}/compliance/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    throw new Error(err || "合规审查请求失败");
  }
  return res.json();
}

// ── MCP 工具 ────────────────────────────────────────────────────────────────

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export async function listTools(): Promise<ToolDefinition[]> {
  const res = await fetch(`${baseURL}/tools/list`);
  if (!res.ok) throw new Error("获取工具列表失败");
  return res.json();
}

export async function callTool(
  name: string,
  params: Record<string, unknown>
): Promise<{ success: boolean; data: unknown; error: string; metadata: Record<string, unknown> }> {
  const res = await fetch(`${baseURL}/tools/call?name=${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error("工具调用失败");
  return res.json();
}

// ── ResearchResponse 扩展字段 ──────────────────────────────────────────────

export interface VerificationPayload {
  passed: boolean;
  score: number;
  law_validity: Record<string, unknown>;
  fact_consistency: Record<string, unknown>;
  violation_detection: Record<string, unknown>;
  warnings: string[];
  corrections: string[];
}

// ── 长期记忆 ──────────────────────────────────────────────────────────────

export interface MemoryStoreRequest {
  case_text: string;
  risk_level: string;
  review_summary: string;
  violations: Record<string, unknown>[];
  relevant_laws: Record<string, unknown>[];
  suggestions: string[];
}

export interface MemoryEntry {
  case_id: string;
  query: string;
  risk_level: string;
  review_summary: string;
  violations: Record<string, unknown>[];
  relevant_laws: Record<string, unknown>[];
  suggestions: string[];
  timestamp: string;
  score?: number;
}

export async function storeMemory(
  payload: MemoryStoreRequest
): Promise<{ success: boolean; case_id: string; message: string }> {
  const res = await fetch(`${baseURL}/memory/store`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    throw new Error(err || "记忆存储失败");
  }
  return res.json();
}

export async function searchMemory(
  query: string,
  topK: number = 5
): Promise<MemoryEntry[]> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  const res = await fetch(`${baseURL}/memory/search?${params}`);
  if (!res.ok) throw new Error("记忆检索失败");
  return res.json();
}

export async function listMemoryCases(limit: number = 50): Promise<MemoryEntry[]> {
  const res = await fetch(`${baseURL}/memory/cases?limit=${limit}`);
  if (!res.ok) throw new Error("获取记忆列表失败");
  return res.json();
}

// ── TXT 原文库 ──────────────────────────────────────────────────────────────

export interface TxtLawInfo {
  law_name: string;
  article_count: number;
  file: string;
}

export interface TxtLawArticle {
  article_number: string;
  content: string;
  category: string;
  keywords: string[];
}

export async function getTxtLaws(): Promise<TxtLawInfo[]> {
  const res = await fetch(`${baseURL}/laws/txt`);
  if (!res.ok) throw new Error("获取法律列表失败");
  const data = await res.json();
  return data.laws || [];
}

export async function getTxtLawArticles(lawName: string): Promise<TxtLawArticle[]> {
  const params = new URLSearchParams({ law_name: lawName });
  const res = await fetch(`${baseURL}/laws/txt/articles?${params}`);
  if (!res.ok) throw new Error("获取法条列表失败");
  const data = await res.json();
  return data.articles || [];
}

// ── 案例生成 ───────────────────────────────────────────────────────────────

export interface CaseGenerateConfig {
  violation_behavior: string;
  violated_law: string;
  case_type: string;
  risk_level: string;
  style: string;
  extra_context?: string;
}

export interface CaseGenerationStreamEvent {
  type: string;
  [key: string]: unknown;
}

export async function runCaseGenerationStream(
  payload: { config: CaseGenerateConfig; user_message: string },
  onEvent: (event: CaseGenerationStreamEvent) => void,
  options: StreamOptions = {}
): Promise<void> {
  const response = await fetch(`${baseURL}/case/generate/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
    signal: options.signal,
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(errorText || `案例生成请求失败，状态码：${response.status}`);
  }

  const body = response.body;
  if (!body) throw new Error("浏览器不支持流式响应");

  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);

      if (rawEvent.startsWith("data:")) {
        const dataPayload = rawEvent.slice(5).trim();
        if (dataPayload) {
          try {
            const event = JSON.parse(dataPayload) as CaseGenerationStreamEvent;
            onEvent(event);
            if (event.type === "error" || event.type === "done") return;
          } catch (error) {
            console.error("解析流式事件失败：", error, dataPayload);
          }
        }
      }
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      if (buffer.trim()) {
        const rawEvent = buffer.trim();
        if (rawEvent.startsWith("data:")) {
          const dataPayload = rawEvent.slice(5).trim();
          if (dataPayload) {
            try {
              const event = JSON.parse(dataPayload) as CaseGenerationStreamEvent;
              onEvent(event);
            } catch (error) {
              console.error("解析流式事件失败：", error, dataPayload);
            }
          }
        }
      }
      break;
    }
  }
}

export async function saveGeneratedCase(
  caseData: Record<string, unknown>
): Promise<{ success: boolean; case_id: string; message: string }> {
  const res = await fetch(`${baseURL}/case/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(caseData),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    throw new Error(err || "案例保存失败");
  }
  return res.json();
}
