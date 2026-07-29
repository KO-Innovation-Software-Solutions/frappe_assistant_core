"""
Generic Aggregation Tool for Core Plugin.

Groups and aggregates any DocType server-side, returning clean structured
JSON — {"groups": [{"label": ..., "value": ...}, ...]} — instead of a
printed text report. This is what lets a dashboard's Query() bindings work
for KPIs and chart breakdowns (category counts, status splits, monthly
trends, etc.) for ANY doctype, without needing a bespoke tool per domain
(get_asset_status_breakdown, get_fuel_by_vehicle, ...) and without the
model falling back to run_python_code + Counter/value_counts() printouts
that can never be bound back to a DSL literal on refresh.
"""

from typing import Any, Dict, List

import frappe
from frappe import _
from frappe.utils import getdate

from frappe_assistant_core.core.base_tool import BaseTool


class AggregateDocuments(BaseTool):
    """
    Tool for grouping and aggregating Frappe documents server-side.

    Provides capabilities for:
    - Category/status/type breakdowns (count per group)
    - Sums and averages per group (e.g. total cost per category)
    - Optional filtering, same filter shape as list_documents
    - Optional date-bucketing (day/week/month) for trend-over-time charts
    """

    def __init__(self):
        super().__init__()
        self.name = "aggregate_documents"
        self.description = (
            "Group and aggregate Frappe documents server-side — e.g. count of Assets per "
            "category, sum of Fuel Entry cost per vehicle, average purchase cost per condition, "
            "or a monthly count trend. Use this instead of run_python_code whenever a dashboard "
            "needs a breakdown, KPI total, or chart series — it returns clean structured JSON "
            "({'groups': [{'label': ..., 'value': ...}]}) that can be bound with Query() and will "
            "still be correct after Refresh, unlike a printed report from run_python_code."
        )
        self.requires_permission = None  # Permission checked dynamically per DocType

        self.inputSchema = {
            "type": "object",
            "properties": {
                "doctype": {
                    "type": "string",
                    "description": "The Frappe DocType to aggregate (e.g., 'Asset', 'Fuel Entry', 'Asset Movement').",
                },
                "group_by": {
                    "type": "string",
                    "description": (
                        "Field to group by, producing one row per distinct value (e.g. "
                        "'asset_category', 'status', 'vehicle'). For a trend-over-time chart, "
                        "pass a Date/Datetime field here and set date_bucket."
                    ),
                },
                "aggregate": {
                    "type": "string",
                    "enum": ["count", "sum", "avg"],
                    "default": "count",
                    "description": "Aggregate function to apply within each group.",
                },
                "value_field": {
                    "type": "string",
                    "description": "Numeric field to sum/average. Required when aggregate is 'sum' or 'avg'; ignored for 'count'.",
                },
                "date_bucket": {
                    "type": "string",
                    "enum": ["day", "week", "month"],
                    "description": "If group_by is a Date/Datetime field, bucket it to this granularity instead of grouping by the exact timestamp.",
                },
                "filters": {
                    "type": "object",
                    "default": {},
                    "description": "Same filter shape as list_documents — e.g. {'status': 'Active'}, {'creation': ['>', '2026-01-01']}.",
                },
                "order_by": {
                    "type": "string",
                    "enum": ["value desc", "value asc", "label asc", "label desc"],
                    "default": "value desc",
                    "description": "Sort order of the returned groups.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "maximum": 200,
                    "description": "Maximum number of groups to return.",
                },
            },
            "required": ["doctype", "group_by"],
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Group and aggregate documents, returning clean structured JSON."""
        doctype = arguments.get("doctype")
        group_by = arguments.get("group_by")
        if not doctype:
            return {"success": False, "error": "doctype is required"}
        if not group_by:
            return {"success": False, "error": "group_by is required", "doctype": doctype}
        aggregate = (arguments.get("aggregate") or "count").lower()
        value_field = arguments.get("value_field")
        date_bucket = arguments.get("date_bucket")
        filters = arguments.get("filters", {}) or {}
        order_by = arguments.get("order_by", "value desc")
        limit = arguments.get("limit", 50)

        from frappe_assistant_core.core.security_config import validate_document_access

        validation_result = validate_document_access(
            user=frappe.session.user,
            doctype=doctype,
            name=None,
            perm_type="read",
        )
        if not validation_result["success"]:
            return validation_result

        if aggregate not in ("count", "sum", "avg"):
            return {
                "success": False,
                "error": f"Invalid aggregate '{aggregate}'. Must be one of: count, sum, avg.",
                "doctype": doctype,
            }

        if aggregate in ("sum", "avg") and not value_field:
            return {
                "success": False,
                "error": f"aggregate '{aggregate}' requires value_field to be set.",
                "doctype": doctype,
            }
        error = self.validate_fields(doctype, [f for f in (group_by, value_field) if f])
        if error:
            return error

        fetch_fields = [group_by]
        if value_field and value_field not in fetch_fields:
            fetch_fields.append(value_field)

        try:
            rows = frappe.get_all(
                doctype,
                filters=filters,
                fields=fetch_fields,
                limit_page_length=0,
                ignore_permissions=False,
            )
        except Exception as e:
            frappe.log_error(title=_("Aggregate Documents Error"), message=f"Error fetching {doctype}: {str(e)}")
            return {"success": False, "error": str(e), "doctype": doctype}

        buckets: Dict[Any, Dict[str, float]] = {}
        for row in rows:
            raw_label = row.get(group_by)
            if raw_label is None:
                continue
            label = self._bucket_label(raw_label, date_bucket) if date_bucket else raw_label

            bucket = buckets.setdefault(label, {"count": 0, "sum": 0.0})
            bucket["count"] += 1
            if value_field:
                try:
                    bucket["sum"] += float(row.get(value_field) or 0)
                except (TypeError, ValueError):
                    pass

        groups: List[Dict[str, Any]] = []
        for label, b in buckets.items():
            if aggregate == "count":
                value = b["count"]
            elif aggregate == "sum":
                value = b["sum"]
            else:  # avg
                value = (b["sum"] / b["count"]) if b["count"] else 0
            groups.append({"label": label, "value": self._clean_number(value)})

        sort_desc = "desc" in order_by
        sort_by_value = order_by.startswith("value")
        groups.sort(key=(lambda g: g["value"]) if sort_by_value else (lambda g: str(g["label"])), reverse=sort_desc)
        groups = groups[:limit]

        return {
            "success": True,
            "doctype": doctype,
            "group_by": group_by,
            "aggregate": aggregate,
            "value_field": value_field,
            "groups": groups,
            "count": len(groups),
            "total_groups": len(groups),
            "label":  [g["label"] for g in groups],
            "labels": [g["label"] for g in groups],
            "value":  [g["value"] for g in groups],
            "values": [g["value"] for g in groups],
            "count_sum": sum(
                (g["value"] if isinstance(g["value"], (int, float)) else 0) for g in groups
            ),
            "total_count": sum(
                (g["value"] if isinstance(g["value"], (int, float)) else 0) for g in groups
            ),
            "message": f"Grouped {doctype} by {group_by} ({aggregate}) into {len(groups)} groups",
        }

    def _bucket_label(self, raw_value: Any, date_bucket: str) -> str:
        """Bucket a date/datetime value to day/week/month granularity."""
        try:
            d = getdate(raw_value)
        except Exception:
            return str(raw_value)
        if date_bucket == "day":
            return d.strftime("%Y-%m-%d")
        if date_bucket == "week":
            return d.strftime("%G-W%V")
        if date_bucket == "month":
            return d.strftime("%Y-%m")
        return str(raw_value)

    def _clean_number(self, value: Any) -> Any:
        """Round floats to a sane display precision; leave ints/None alone."""
        if isinstance(value, float):
            return round(value, 2)
        return value
aggregate_documents = AggregateDocuments