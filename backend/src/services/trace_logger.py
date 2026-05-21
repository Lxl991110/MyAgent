"""Agent Trace 日志系统 — 记录合规审查完整执行链路。

每条审查生成一个 JSON trace 文件，存储于 backend/logs/compliance/，
支持问题定位、Prompt 调试、失败案例回放与审查效果分析。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _logs_dir() -> Path:
    """获取日志输出目录（相对于本文件的 backend/logs/compliance）。"""
    return Path(__file__).resolve().parent.parent.parent / "logs" / "compliance"


class ComplianceTrace:
    """单次合规审查的完整执行追踪。"""

    def __init__(self, trace_id: str, query: str, context: str = "") -> None:
        self.trace_id = trace_id
        self.query = query
        self.context = context
        self.steps: List[Dict[str, Any]] = []
        self.final_report: Optional[Dict[str, Any]] = None
        self.memory_saved: bool = False
        self.started_at = datetime.now(timezone.utc).isoformat()

    def log_step(self, node: str, **kwargs: Any) -> None:
        """记录一个执行步骤。"""
        self.steps.append({
            "node": node,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        })

    def set_final_report(self, report: Dict[str, Any]) -> None:
        self.final_report = report

    def mark_memory_saved(self) -> None:
        self.memory_saved = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "context": self.context,
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "steps": self.steps,
            "final_report": self.final_report,
            "memory_saved": self.memory_saved,
        }


class TraceLogger:
    """Trace 日志管理器 — 创建、保存、检索 trace。"""

    def __init__(self) -> None:
        self._dir = _logs_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── 创建与保存 ──────────────────────────────────────────────────────

    def start_trace(self, query: str, *, context: str = "") -> ComplianceTrace:
        """创建一条新的审查 trace。"""
        trace_id = f"trace-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        return ComplianceTrace(trace_id, query, context)

    def save_trace(self, trace: ComplianceTrace) -> Optional[str]:
        """将 trace 序列化为 JSON 写入磁盘。返回文件路径或 None。"""
        try:
            data = trace.to_dict()
            filename = f"{trace.trace_id}.json"
            filepath = self._dir / filename
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            return str(filepath)
        except Exception:
            # 日志记录不应影响主流程
            return None

    # ── 检索 ────────────────────────────────────────────────────────────

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """按 trace_id 读取单条 trace。"""
        filepath = self._dir / f"{trace_id}.json"
        if not filepath.exists():
            return None
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            return None

    def list_traces(self, limit: int = 50) -> List[Dict[str, Any]]:
        """列出最近的 trace 摘要（按文件修改时间倒序）。"""
        files = sorted(
            self._dir.glob("trace-*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]

        traces: List[Dict[str, Any]] = []
        for fp in files:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                traces.append({
                    "trace_id": data.get("trace_id", fp.stem),
                    "query": (data.get("query", "") or "")[:120],
                    "started_at": data.get("started_at", ""),
                    "finished_at": data.get("finished_at", ""),
                    "risk_level": (
                        data.get("final_report", {}).get("risk_level", "")
                        if data.get("final_report")
                        else ""
                    ),
                    "step_count": len(data.get("steps", [])),
                    "memory_saved": data.get("memory_saved", False),
                })
            except Exception:
                traces.append({
                    "trace_id": fp.stem,
                    "query": "",
                    "started_at": "",
                    "finished_at": "",
                    "risk_level": "",
                    "step_count": 0,
                    "memory_saved": False,
                })
        return traces


# 全局单例
_trace_logger: Optional[TraceLogger] = None


def get_trace_logger() -> TraceLogger:
    global _trace_logger
    if _trace_logger is None:
        _trace_logger = TraceLogger()
    return _trace_logger
