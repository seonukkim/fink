from __future__ import annotations

import html
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fink.finance import (
    DecimalRange,
    fim1_revenue_base_deduction_leakage,
    fim2_payment_delay_present_value_loss,
    fim3_mg_advance_recoupment,
    fim4_unpaid_additional_work_cost,
    fim5_exclusivity_renewal_opportunity_cost,
    fim6_ip_secondary_rights_scenario_value,
    fim7_penalty_liability_exposure,
)
from fink.schemas import (
    ExposureType,
    FimModule,
    FinancialScenarioInputs,
    MonetaryExposureEstimate,
)


@dataclass(frozen=True)
class AssumptionFieldSpec:
    name: str
    label: str
    fim_modules: tuple[FimModule, ...]
    unit: str
    required_for_output: bool = True


@dataclass(frozen=True)
class EditableAssumptions:
    annual_discount_rate: Decimal | None = None
    sales_low: Decimal | None = None
    sales_base: Decimal | None = None
    sales_high: Decimal | None = None
    creator_hourly_value: Decimal | None = None
    hours_per_unit: Decimal | None = None
    unpaid_revision_units: int | None = None
    alternative_monthly_revenue: Decimal | None = None
    scenario_probability_low: Decimal | None = None
    scenario_probability_base: Decimal | None = None
    scenario_probability_high: Decimal | None = None
    secondary_rights: tuple[Mapping[str, object], ...] | None = None
    penalty_probability: Decimal | None = None
    gross_sales: Decimal | None = None
    refunds: Decimal | None = None
    explicitly_allowed_deductions: Decimal | None = None
    revenue_share_rate: Decimal | None = None
    fixed_fee: Decimal | None = None
    advance_recoupment: Decimal | None = None
    open_ended_deductions_low: Decimal | None = None
    open_ended_deductions_base: Decimal | None = None
    open_ended_deductions_high: Decimal | None = None
    delayed_amount: Decimal | None = None
    delay_days_low: Decimal | None = None
    delay_days_base: Decimal | None = None
    delay_days_high: Decimal | None = None
    recoupable_advance: Decimal | None = None
    cumulative_recouped: Decimal | None = None
    exclusivity_duration_months: int | None = None
    renewal_duration_months: int | None = None
    include_renewal: bool = False
    explicit_penalty_cap: Decimal | None = None
    penalty_scenario_amount: Decimal | None = None
    is_uncapped: bool = False
    is_ambiguous: bool = False

    @classmethod
    def from_financial_scenario_inputs(
        cls,
        scenario_inputs: FinancialScenarioInputs,
        **known_terms: object,
    ) -> EditableAssumptions:
        probabilities = scenario_inputs.scenario_probabilities or {}
        base_probability = probabilities.get("base")
        return cls(
            annual_discount_rate=Decimal(str(scenario_inputs.annual_discount_rate)),
            sales_low=scenario_inputs.sales_low,
            sales_base=scenario_inputs.sales_base,
            sales_high=scenario_inputs.sales_high,
            creator_hourly_value=scenario_inputs.creator_hourly_value,
            hours_per_unit=_optional_decimal(scenario_inputs.hours_per_unit),
            unpaid_revision_units=scenario_inputs.unpaid_revision_units,
            alternative_monthly_revenue=scenario_inputs.alternative_monthly_revenue,
            scenario_probability_low=_optional_decimal(probabilities.get("low", base_probability)),
            scenario_probability_base=_optional_decimal(base_probability),
            scenario_probability_high=_optional_decimal(
                probabilities.get("high", base_probability)
            ),
            secondary_rights=scenario_inputs.secondary_rights,
            penalty_probability=_optional_decimal(scenario_inputs.penalty_probability),
            **known_terms,
        )


@dataclass(frozen=True)
class AssumptionModuleRow:
    module: FimModule
    exposure_type: ExposureType
    exposure: MonetaryExposureEstimate
    missing_inputs: tuple[str, ...]
    synthetic_labels: tuple[str, ...]
    details: tuple[tuple[str, str], ...] = ()

    @property
    def is_blank(self) -> bool:
        return self.exposure.is_user_input_required


@dataclass(frozen=True)
class AssumptionRecomputeResult:
    rows: tuple[AssumptionModuleRow, ...]

    @property
    def exposures(self) -> tuple[MonetaryExposureEstimate, ...]:
        return tuple(row.exposure for row in self.rows)

    @property
    def live_recompute_ready(self) -> bool:
        return True


ASSUMPTION_FIELD_SPECS: tuple[AssumptionFieldSpec, ...] = (
    AssumptionFieldSpec(
        "gross_sales",
        "Gross sales / total settlement basis",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec("refunds", "Refunds", (FimModule.FIM_1,), "KRW"),
    AssumptionFieldSpec(
        "explicitly_allowed_deductions",
        "Explicitly allowed deductions",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "open_ended_deductions_low",
        "Open-ended deductions low",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "open_ended_deductions_base",
        "Open-ended deductions base",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "open_ended_deductions_high",
        "Open-ended deductions high",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "revenue_share_rate",
        "Creator revenue share rate",
        (FimModule.FIM_1, FimModule.FIM_3),
        "fraction",
    ),
    AssumptionFieldSpec("fixed_fee", "Fixed fee", (FimModule.FIM_1,), "KRW"),
    AssumptionFieldSpec(
        "advance_recoupment",
        "Advance recoupment deducted in payout",
        (FimModule.FIM_1,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "delayed_amount",
        "Delayed or unpaid nominal amount",
        (FimModule.FIM_2,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "annual_discount_rate",
        "Annual discount rate",
        (FimModule.FIM_2, FimModule.FIM_5),
        "fraction",
    ),
    AssumptionFieldSpec("delay_days_low", "Delay days low", (FimModule.FIM_2,), "days"),
    AssumptionFieldSpec("delay_days_base", "Delay days base", (FimModule.FIM_2,), "days"),
    AssumptionFieldSpec("delay_days_high", "Delay days high", (FimModule.FIM_2,), "days"),
    AssumptionFieldSpec(
        "recoupable_advance",
        "Recoupable advance / MG balance basis",
        (FimModule.FIM_3,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "cumulative_recouped",
        "Cumulative recouped amount",
        (FimModule.FIM_3,),
        "KRW",
    ),
    AssumptionFieldSpec(
        "sales_low",
        "Monthly net sales low",
        (FimModule.FIM_3,),
        "KRW/month",
    ),
    AssumptionFieldSpec(
        "sales_base",
        "Monthly net sales base",
        (FimModule.FIM_3,),
        "KRW/month",
    ),
    AssumptionFieldSpec(
        "sales_high",
        "Monthly net sales high",
        (FimModule.FIM_3,),
        "KRW/month",
    ),
    AssumptionFieldSpec(
        "unpaid_revision_units",
        "Unpaid additional-work units",
        (FimModule.FIM_4,),
        "count",
    ),
    AssumptionFieldSpec("hours_per_unit", "Hours per unit", (FimModule.FIM_4,), "hours"),
    AssumptionFieldSpec(
        "creator_hourly_value",
        "Creator hourly value",
        (FimModule.FIM_4,),
        "KRW/hour",
    ),
    AssumptionFieldSpec(
        "exclusivity_duration_months",
        "Exclusivity duration",
        (FimModule.FIM_5,),
        "months",
    ),
    AssumptionFieldSpec(
        "renewal_duration_months",
        "Renewal duration",
        (FimModule.FIM_5,),
        "months",
        required_for_output=False,
    ),
    AssumptionFieldSpec(
        "alternative_monthly_revenue",
        "Alternative monthly revenue",
        (FimModule.FIM_5,),
        "KRW/month",
    ),
    AssumptionFieldSpec(
        "scenario_probability_low",
        "Scenario probability low",
        (FimModule.FIM_5,),
        "fraction",
    ),
    AssumptionFieldSpec(
        "scenario_probability_base",
        "Scenario probability base",
        (FimModule.FIM_5,),
        "fraction",
    ),
    AssumptionFieldSpec(
        "scenario_probability_high",
        "Scenario probability high",
        (FimModule.FIM_5,),
        "fraction",
    ),
    AssumptionFieldSpec(
        "secondary_rights",
        "Secondary-rights scenario rows",
        (FimModule.FIM_6,),
        "type/value/probability",
    ),
    AssumptionFieldSpec(
        "explicit_penalty_cap",
        "Explicit penalty or liability cap",
        (FimModule.FIM_7,),
        "KRW",
        required_for_output=False,
    ),
    AssumptionFieldSpec(
        "penalty_probability",
        "Penalty probability",
        (FimModule.FIM_7,),
        "fraction",
        required_for_output=False,
    ),
    AssumptionFieldSpec(
        "penalty_scenario_amount",
        "Penalty scenario amount",
        (FimModule.FIM_7,),
        "KRW",
        required_for_output=False,
    ),
)

FIM_MODULE_ORDER = (
    FimModule.FIM_1,
    FimModule.FIM_2,
    FimModule.FIM_3,
    FimModule.FIM_4,
    FimModule.FIM_5,
    FimModule.FIM_6,
    FimModule.FIM_7,
)


def assumption_field_specs() -> tuple[AssumptionFieldSpec, ...]:
    return ASSUMPTION_FIELD_SPECS


def recompute_assumptions(
    assumptions: EditableAssumptions | None = None,
) -> AssumptionRecomputeResult:
    values = assumptions or EditableAssumptions()
    return AssumptionRecomputeResult(
        rows=(
            _fim1_row(values),
            _fim2_row(values),
            _fim3_row(values),
            _fim4_row(values),
            _fim5_row(values),
            _fim6_row(values),
            _fim7_row(values),
        )
    )


def render_assumptions_panel_html(
    assumptions: EditableAssumptions | None = None,
) -> str:
    result = recompute_assumptions(assumptions)
    fields = "\n".join(_render_field(spec, assumptions) for spec in ASSUMPTION_FIELD_SPECS)
    outputs = "\n".join(_render_row(row) for row in result.rows)
    return f"""<section class="assumptions-panel" aria-labelledby="assumptions-heading"
      data-assumptions-panel="true" data-live-recompute="true"
      data-fim-modules="{_escape(' '.join(module.value for module in FIM_MODULE_ORDER))}">
      <div class="section-heading">
        <p class="eyebrow">Editable assumptions</p>
        <h3 id="assumptions-heading">FIM assumptions</h3>
      </div>
      <p class="hint">Outputs stay blank until required inputs are supplied.</p>
      <div class="assumption-fields">{fields}</div>
      <ul class="assumption-results" data-assumption-results="true">{outputs}</ul>
    </section>"""


def _fim1_row(values: EditableAssumptions) -> AssumptionModuleRow:
    missing = _missing(
        values,
        (
            "gross_sales",
            "refunds",
            "explicitly_allowed_deductions",
            "revenue_share_rate",
            "fixed_fee",
            "advance_recoupment",
            "open_ended_deductions_low",
            "open_ended_deductions_base",
            "open_ended_deductions_high",
        ),
    )
    if missing:
        return _blank_row(FimModule.FIM_1, ExposureType.NOMINAL_LEAKAGE, missing)
    result = fim1_revenue_base_deduction_leakage(
        gross_sales=values.gross_sales,
        refunds=values.refunds,
        explicitly_allowed_deductions=values.explicitly_allowed_deductions,
        revenue_share_rate=values.revenue_share_rate,
        fixed_fee=values.fixed_fee,
        advance_recoupment=values.advance_recoupment,
        open_ended_deductions=DecimalRange(
            low=_expect_decimal(values.open_ended_deductions_low),
            base=_expect_decimal(values.open_ended_deductions_base),
            high=_expect_decimal(values.open_ended_deductions_high),
        ),
    )
    return _computed_row(result.nominal_leakage)


def _fim2_row(values: EditableAssumptions) -> AssumptionModuleRow:
    missing = _missing(
        values,
        (
            "delayed_amount",
            "annual_discount_rate",
            "delay_days_low",
            "delay_days_base",
            "delay_days_high",
        ),
    )
    if missing:
        return _blank_row(FimModule.FIM_2, ExposureType.PRESENT_VALUE_LOSS, missing)
    result = fim2_payment_delay_present_value_loss(
        delayed_amount=values.delayed_amount,
        annual_discount_rate=values.annual_discount_rate,
        delay_days=DecimalRange(
            low=_expect_decimal(values.delay_days_low),
            base=_expect_decimal(values.delay_days_base),
            high=_expect_decimal(values.delay_days_high),
        ),
    )
    return _computed_row(result.present_value_loss)


def _fim3_row(values: EditableAssumptions) -> AssumptionModuleRow:
    missing = _missing(
        values,
        (
            "recoupable_advance",
            "cumulative_recouped",
            "revenue_share_rate",
            "sales_low",
            "sales_base",
            "sales_high",
        ),
    )
    if missing:
        return _blank_row(FimModule.FIM_3, ExposureType.DEFERRAL, missing)
    result = fim3_mg_advance_recoupment(
        recoupable_advance=values.recoupable_advance,
        cumulative_recouped=values.cumulative_recouped,
        revenue_share_rate=values.revenue_share_rate,
        monthly_net_sales=DecimalRange(
            low=_expect_decimal(values.sales_low),
            base=_expect_decimal(values.sales_base),
            high=_expect_decimal(values.sales_high),
        ),
    )
    return AssumptionModuleRow(
        module=FimModule.FIM_3,
        exposure_type=result.deferral.exposure_type,
        exposure=result.deferral,
        missing_inputs=(),
        synthetic_labels=_synthetic_labels(result.deferral),
        details=(
            ("months_to_recoup_low_sales", _format_detail(result.months_to_recoup[0])),
            ("months_to_recoup_base_sales", _format_detail(result.months_to_recoup[1])),
            ("months_to_recoup_high_sales", _format_detail(result.months_to_recoup[2])),
            ("sales_label_note", result.sales_label_note),
        ),
    )


def _fim4_row(values: EditableAssumptions) -> AssumptionModuleRow:
    result = fim4_unpaid_additional_work_cost(
        unpaid_revision_units=values.unpaid_revision_units,
        hours_per_unit=values.hours_per_unit,
        creator_hourly_value=values.creator_hourly_value,
    )
    return AssumptionModuleRow(
        module=FimModule.FIM_4,
        exposure_type=result.unpaid_work_cost.exposure_type,
        exposure=result.unpaid_work_cost,
        missing_inputs=result.missing_inputs,
        synthetic_labels=_synthetic_labels(result.unpaid_work_cost),
    )


def _fim5_row(values: EditableAssumptions) -> AssumptionModuleRow:
    probability = _range_or_none(
        values.scenario_probability_low,
        values.scenario_probability_base,
        values.scenario_probability_high,
    )
    missing = _missing(
        values,
        ("exclusivity_duration_months", "alternative_monthly_revenue", "annual_discount_rate"),
    )
    if probability is None:
        missing = (*missing, "scenario_probability_low/base/high")
    if values.include_renewal and values.renewal_duration_months is None:
        missing = (*missing, "renewal_duration_months")
    if missing:
        return _blank_row(FimModule.FIM_5, ExposureType.OPPORTUNITY_COST, missing)
    result = fim5_exclusivity_renewal_opportunity_cost(
        exclusivity_duration_months=values.exclusivity_duration_months,
        alternative_monthly_revenue=values.alternative_monthly_revenue,
        scenario_probability=probability,
        annual_discount_rate=values.annual_discount_rate,
        renewal_duration_months=values.renewal_duration_months,
        include_renewal=values.include_renewal,
    )
    return AssumptionModuleRow(
        module=FimModule.FIM_5,
        exposure_type=result.opportunity_cost.exposure_type,
        exposure=result.opportunity_cost,
        missing_inputs=result.missing_inputs,
        synthetic_labels=_synthetic_labels(result.opportunity_cost),
        details=(
            (("scenario_months", "/".join(str(month) for month in result.scenario_months)),)
            if result.scenario_months is not None
            else ()
        ),
    )


def _fim6_row(values: EditableAssumptions) -> AssumptionModuleRow:
    result = fim6_ip_secondary_rights_scenario_value(secondary_rights=values.secondary_rights)
    return AssumptionModuleRow(
        module=FimModule.FIM_6,
        exposure_type=result.scenario_value.exposure_type,
        exposure=result.scenario_value,
        missing_inputs=result.missing_inputs,
        synthetic_labels=_synthetic_labels(result.scenario_value),
        details=(
            (("right_types", ", ".join(result.right_types)),) if result.right_types else ()
        ),
    )


def _fim7_row(values: EditableAssumptions) -> AssumptionModuleRow:
    missing: tuple[str, ...] = ()
    scenario_amount = values.penalty_scenario_amount
    if values.penalty_probability is not None and scenario_amount is None:
        missing = ("penalty_scenario_amount",)
        result = None
    else:
        result = fim7_penalty_liability_exposure(
            explicit_penalty_cap=values.explicit_penalty_cap,
            is_uncapped=values.is_uncapped,
            is_ambiguous=values.is_ambiguous,
            penalty_probability=values.penalty_probability,
            scenario_amount=scenario_amount,
        )
        if (
            result.liability_exposure.is_user_input_required
            and values.explicit_penalty_cap is None
            and values.penalty_probability is None
        ):
            missing = ("explicit_penalty_cap", "penalty_probability")
    if result is None:
        return _blank_row(FimModule.FIM_7, ExposureType.LIABILITY_EXPOSURE, missing)
    return AssumptionModuleRow(
        module=FimModule.FIM_7,
        exposure_type=result.liability_exposure.exposure_type,
        exposure=result.liability_exposure,
        missing_inputs=missing,
        synthetic_labels=_synthetic_labels(result.liability_exposure),
        details=(
            ("max_nominal_exposure", _format_detail(result.max_nominal_exposure)),
            ("expected_penalty", _format_detail(result.expected_penalty)),
        ),
    )


def _computed_row(exposure: MonetaryExposureEstimate) -> AssumptionModuleRow:
    return AssumptionModuleRow(
        module=exposure.module,
        exposure_type=exposure.exposure_type,
        exposure=exposure,
        missing_inputs=(),
        synthetic_labels=_synthetic_labels(exposure),
    )


def _blank_row(
    module: FimModule,
    exposure_type: ExposureType,
    missing_inputs: tuple[str, ...],
) -> AssumptionModuleRow:
    exposure = MonetaryExposureEstimate(
        module=module,
        exposure_type=exposure_type,
        is_user_input_required=True,
        assumptions=(),
        low=None,
        base=None,
        high=None,
        uncertainty_flags=tuple(f"missing_user_input:{item}" for item in missing_inputs),
    )
    return AssumptionModuleRow(
        module=module,
        exposure_type=exposure_type,
        exposure=exposure,
        missing_inputs=missing_inputs,
        synthetic_labels=(),
    )


def _render_field(spec: AssumptionFieldSpec, assumptions: EditableAssumptions | None) -> str:
    value = getattr(assumptions, spec.name, None) if assumptions is not None else None
    value_attr = "" if value is None or isinstance(value, tuple) else f' value="{_escape(value)}"'
    modules = " ".join(module.value for module in spec.fim_modules)
    return f"""<label class="assumption-field" data-assumption-field="{_escape(spec.name)}"
      data-fim-modules="{_escape(modules)}" data-synthetic-assumption="true">
      <span>{_escape(spec.label)}</span>
      <small>{_escape(spec.unit)} · synthetic assumption when supplied</small>
      <input type="number" inputmode="decimal" name="{_escape(spec.name)}"
        autocomplete="off" placeholder="blank until supplied"{value_attr}>
    </label>"""


def _render_row(row: AssumptionModuleRow) -> str:
    if row.is_blank:
        status = "blank"
        range_text = "blank until inputs supplied"
    else:
        status = "computed"
        range_text = (
            f"low {_money(row.exposure.low)} / base {_money(row.exposure.base)} / "
            f"high {_money(row.exposure.high)}"
        )
    missing = ", ".join(row.missing_inputs)
    missing_html = (
        f'<p class="hint" data-missing-inputs="{_escape(missing)}">Missing: {_escape(missing)}</p>'
        if missing
        else ""
    )
    labels = "".join(
        f'<span class="badge synthetic-assumption">{_escape(label)}</span>'
        for label in row.synthetic_labels
    )
    nominal = (
        f'<p class="hint">Nominal amount kept separate: {_money(row.exposure.nominal_amount)}</p>'
        if row.exposure.nominal_amount is not None
        else ""
    )
    details = "".join(
        f'<span data-assumption-detail="{_escape(name)}">{_escape(value)}</span>'
        for name, value in row.details
    )
    return f"""<li data-fim-module="{_escape(row.module.value)}"
      data-exposure-type="{_escape(row.exposure_type.value)}" data-output-state="{status}">
      <strong>{_escape(row.module.value)} {_escape(row.exposure_type.value)}</strong>
      <output>{range_text}</output>
      {missing_html}
      {labels}
      {nominal}
      {details}
    </li>"""


def _synthetic_labels(exposure: MonetaryExposureEstimate) -> tuple[str, ...]:
    labels = tuple(item for item in exposure.assumptions if "synthetic assumption" in item)
    if labels or exposure.is_user_input_required:
        return labels
    return ("synthetic assumption: user-supplied panel values are editable",)


def _range_or_none(
    low: Decimal | None,
    base: Decimal | None,
    high: Decimal | None,
) -> DecimalRange | None:
    if low is None or base is None or high is None:
        return None
    return DecimalRange(low=low, base=base, high=high)


def _missing(values: EditableAssumptions, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if getattr(values, name) is None)


def _optional_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _expect_decimal(value: Decimal | None) -> Decimal:
    if value is None:
        raise AssertionError("caller must check missing inputs first")
    return value


def _money(value: Decimal | None) -> str:
    if value is None:
        return "blank"
    return f"KRW {Decimal(str(value)):,.0f}"


def _format_detail(value: object) -> str:
    if value is None:
        return "blank"
    return str(value)


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
