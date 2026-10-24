"""Calculate financial metrics: contracts only, no business logic."""

from typing import Literal
from decimal import Decimal

from pydantic import BaseModel

from core.models import Source, ToolMetadata, ToolResult

METADATA = ToolMetadata(name="calc_financials", description_zh="计算财务指标", description_en="Calculate financial metrics")


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


def calc_financials(request: CalcFinancialsInput) -> CalcFinancialsOutput:
    raise NotImplementedError("Step 1: calc_financials contract only")
