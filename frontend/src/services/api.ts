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
