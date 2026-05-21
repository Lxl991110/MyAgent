"""MCP 数据校验工具 —— 校验案例结构化字段的完整性和合法性。"""

from __future__ import annotations

from typing import Any

from tools.base import MCPTool, ToolResult

# 合法案例类型
_VALID_CASE_TYPES = {"滥用市场支配地位", "垄断协议", "经营者集中", "行政垄断", "不正当竞争", "其他"}

# 合法金额单位模式
_AMOUNT_PATTERNS = ["万元", "亿元", "元", "美元", "欧元"]


class DataValidationTool(MCPTool):
    name = "data_validation"
    description = "校验案例结构化数据字段完整性、类型合法性和金额格式"
    input_schema = {
        "type": "object",
        "properties": {
            "case_data": {
                "type": "object",
                "description": "结构化案例数据，包含 case_type, subjects, behaviors, amount, region, related_laws 等字段",
                "properties": {
                    "case_type": {"type": "string"},
                    "subjects": {"type": "array", "items": {"type": "string"}},
                    "behaviors": {"type": "array", "items": {"type": "string"}},
                    "amount": {"type": "string"},
                    "region": {"type": "string"},
                    "related_laws": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "required": ["case_data"],
    }

    def call(self, **kwargs: Any) -> ToolResult:
        case_data = kwargs.get("case_data", {})
        if not isinstance(case_data, dict):
            return ToolResult(success=False, error="case_data 必须为字典")

        errors: list[str] = []
        warnings: list[str] = []
        validations: list[dict[str, Any]] = []

        # 案由校验
        case_type = case_data.get("case_type", "")
        if not case_type:
            errors.append("缺失案由（case_type）")
        elif case_type not in _VALID_CASE_TYPES:
            warnings.append(f"非标准案由: '{case_type}'，合法值: {', '.join(sorted(_VALID_CASE_TYPES))}")
        validations.append({"field": "case_type", "value": case_type, "valid": case_type in _VALID_CASE_TYPES})

        # 主体校验
        subjects = case_data.get("subjects", [])
        if not subjects:
            errors.append("缺失当事人主体（subjects）")
        validations.append({"field": "subjects", "count": len(subjects), "valid": len(subjects) > 0})

        # 行为校验
        behaviors = case_data.get("behaviors", [])
        if not behaviors:
            warnings.append("未识别到行为描述（behaviors）")
        validations.append({"field": "behaviors", "count": len(behaviors), "valid": len(behaviors) > 0})

        # 金额格式校验
        amount = case_data.get("amount", "")
        if amount:
            has_unit = any(p in amount for p in _AMOUNT_PATTERNS)
            if not has_unit:
                warnings.append(f"金额缺少单位: '{amount}'，建议使用: {', '.join(_AMOUNT_PATTERNS)}")
            validations.append({"field": "amount", "value": amount, "valid": has_unit})
        else:
            validations.append({"field": "amount", "value": "", "valid": True})

        # 法条校验
        related_laws = case_data.get("related_laws", [])
        if not related_laws:
            warnings.append("未关联任何法条（related_laws）")
        validations.append({"field": "related_laws", "count": len(related_laws), "valid": len(related_laws) > 0})

        # 地域校验
        region = case_data.get("region", "")
        if not region:
            warnings.append("未识别到地域信息（region）")
        validations.append({"field": "region", "value": region, "valid": bool(region)})

        return ToolResult(
            success=len(errors) == 0,
            data={
                "errors": errors,
                "warnings": warnings,
                "validations": validations,
            },
            metadata={
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        )
