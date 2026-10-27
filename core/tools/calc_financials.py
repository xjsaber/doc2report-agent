"""Pure-code financial metrics; never call a language model for arithmetic."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import logging
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from core.models import Source, ToolMetadata, ToolResult

METADATA = ToolMetadata(
    name="calc_financials",
    description_zh="计算财务指标",
    description_en="Calculate financial metrics",
)
logger = logging.getLogger(__name__)

MetricName = Literal["营业收入", "营业成本", "净利润", "经营活动现金流", "总资产", "总负债"]


class MetricValue(BaseModel):
    value: Decimal
    sources: list[Source]


class PeriodValues(BaseModel):
    current: MetricValue
    previous: MetricValue | None = None


class CalcFinancialsInput(BaseModel):
    values: dict[MetricName, PeriodValues]


class FinancialMetric(BaseModel):
    name: str
    value: Decimal | None
    formula: str
    inputs: dict[str, MetricValue]
    sources: list[Source]
    note: str | None = None


class CalcFinancialsData(BaseModel):
    metrics: list[FinancialMetric]


CalcFinancialsOutput = ToolResult[CalcFinancialsData]


def _yoy(current: Decimal, previous: Decimal) -> Decimal:
    if previous == 0:
        raise InvalidOperation("previous period is zero")
    return (current - previous) / abs(previous)


def _merge_sources(*values: MetricValue | None) -> list[Source]:
    out: list[Source] = []
    seen: set[tuple[str, int, str]] = set()
    for value in values:
        if value is None:
            continue
        for source in value.sources:
            key = (source.file, source.page, source.chunk_id)
            if key not in seen:
                seen.add(key)
                out.append(source)
    return out


def calc_financials(request: CalcFinancialsInput) -> CalcFinancialsOutput:
    started = perf_counter()
    try:
        if not request.values:
            raise ValueError("values must not be empty")
        metrics: list[FinancialMetric] = []
        values = request.values

        def add_yoy(metric_key: MetricName, label: str) -> None:
            period = values.get(metric_key)
            if period is None or period.previous is None:
                return
            try:
                value = _yoy(period.current.value, period.previous.value)
                note = None
            except InvalidOperation:
                value = None
                note = "previous period is zero; year-over-year undefined"
            metrics.append(
                FinancialMetric(
                    name=label,
                    value=value,
                    formula="(current - previous) / abs(previous)",
                    inputs={"current": period.current, "previous": period.previous},
                    sources=_merge_sources(period.current, period.previous),
                    note=note,
                )
            )

        add_yoy("营业收入", "营业收入同比增速")
        add_yoy("净利润", "净利润同比增速")

        revenue = values.get("营业收入")
        cost = values.get("营业成本")
        if revenue is not None and cost is not None:
            if revenue.current.value == 0:
                metrics.append(
                    FinancialMetric(
                        name="毛利率",
                        value=None,
                        formula="(营业收入 - 营业成本) / 营业收入",
                        inputs={"营业收入": revenue.current, "营业成本": cost.current},
                        sources=_merge_sources(revenue.current, cost.current),
                        note="营业收入为 0，毛利率未定义",
                    )
                )
            else:
                gross = (revenue.current.value - cost.current.value) / revenue.current.value
                metrics.append(
                    FinancialMetric(
                        name="毛利率",
                        value=gross,
                        formula="(营业收入 - 营业成本) / 营业收入",
                        inputs={"营业收入": revenue.current, "营业成本": cost.current},
                        sources=_merge_sources(revenue.current, cost.current),
                    )
                )

        profit = values.get("净利润")
        if revenue is not None and profit is not None:
            if revenue.current.value == 0:
                net_margin = None
                note = "营业收入为 0，净利率未定义"
            else:
                net_margin = profit.current.value / revenue.current.value
                note = None
            metrics.append(
                FinancialMetric(
                    name="净利率",
                    value=net_margin,
                    formula="净利润 / 营业收入",
                    inputs={"净利润": profit.current, "营业收入": revenue.current},
                    sources=_merge_sources(profit.current, revenue.current),
                    note=note,
                )
            )

        assets = values.get("总资产")
        liabilities = values.get("总负债")
        if assets is not None and liabilities is not None:
            if assets.current.value == 0:
                ratio = None
                note = "总资产为 0，资产负债率未定义"
            else:
                ratio = liabilities.current.value / assets.current.value
                note = None
            metrics.append(
                FinancialMetric(
                    name="资产负债率",
                    value=ratio,
                    formula="总负债 / 总资产",
                    inputs={"总负债": liabilities.current, "总资产": assets.current},
                    sources=_merge_sources(liabilities.current, assets.current),
                    note=note,
                )
            )

        cash = values.get("经营活动现金流")
        if cash is not None and profit is not None:
            if profit.current.value == 0:
                net_cash = None
                note = "净利润为 0，净现比未定义"
            else:
                net_cash = cash.current.value / profit.current.value
                note = None
            metrics.append(
                FinancialMetric(
                    name="净现比",
                    value=net_cash,
                    formula="经营活动现金流 / 净利润",
                    inputs={"经营活动现金流": cash.current, "净利润": profit.current},
                    sources=_merge_sources(cash.current, profit.current),
                    note=note,
                )
            )

        if not metrics:
            raise ValueError("insufficient inputs to compute any metric")
        result = CalcFinancialsOutput(ok=True, data=CalcFinancialsData(metrics=metrics))
    except Exception as exc:
        result = CalcFinancialsOutput(ok=False, error=f"{type(exc).__name__}: {exc}")
    logger.info(
        "tool=calc_financials input_keys=%d elapsed_seconds=%.6f ok=%s",
        len(request.values or {}),
        perf_counter() - started,
        result.ok,
    )
    return result
