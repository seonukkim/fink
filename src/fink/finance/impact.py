from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any

from fink.schemas import ExposureType, FimModule, MonetaryExposureEstimate


DecimalLike = Decimal | int | float | str
RangeLike = Any
MONTHS_INF = math.inf


class FinanceImpactError(ValueError):
    """Raised when financial-impact inputs violate the FIM contract."""


@dataclass(frozen=True)
class DecimalRange:
    low: Decimal
    base: Decimal
    high: Decimal

    def as_tuple(self) -> tuple[Decimal, Decimal, Decimal]:
        return self.low, self.base, self.high


@dataclass(frozen=True)
class RecoupmentTimeline:
    low_sales: int | float
    base_sales: int | float
    high_sales: int | float

    def as_tuple(self) -> tuple[int | float, int | float, int | float]:
        return self.low_sales, self.base_sales, self.high_sales


@dataclass(frozen=True)
class Fim1Result:
    net_sales: DecimalRange
    creator_payout: DecimalRange
    nominal_leakage: MonetaryExposureEstimate
    leakage: Decimal

    @property
    def maximum_nominal_leakage(self) -> Decimal:
        return self.leakage


@dataclass(frozen=True)
class Fim2Result:
    nominal_amount: Decimal
    delay_pv_loss: Decimal
    present_value_loss: MonetaryExposureEstimate


@dataclass(frozen=True)
class Fim3Result:
    recoupment_balance: Decimal
    monthly_recoupment: DecimalRange
    months_to_recoup_by_sales: RecoupmentTimeline
    deferral: MonetaryExposureEstimate
    sales_label_note: str

    @property
    def months_to_recoup(self) -> tuple[int | float, int | float, int | float]:
        return self.months_to_recoup_by_sales.as_tuple()


@dataclass(frozen=True)
class Fim4Result:
    unpaid_work_cost: MonetaryExposureEstimate
    missing_inputs: tuple[str, ...] = ()

    @property
    def is_blank(self) -> bool:
        return self.unpaid_work_cost.is_user_input_required


@dataclass(frozen=True)
class Fim5Result:
    opportunity_cost: MonetaryExposureEstimate
    scenario_months: tuple[int, int, int] | None
    includes_renewal: bool
    missing_inputs: tuple[str, ...] = ()

    @property
    def is_blank(self) -> bool:
        return self.opportunity_cost.is_user_input_required


@dataclass(frozen=True)
class Fim6Result:
    scenario_value: MonetaryExposureEstimate
    right_types: tuple[str, ...]
    auto_valued_from_contract_text: bool = False
    missing_inputs: tuple[str, ...] = ()

    @property
    def is_blank(self) -> bool:
        return self.scenario_value.is_user_input_required


@dataclass(frozen=True)
class Fim7Result:
    max_nominal_exposure: Decimal | None
    expected_penalty: Decimal | None
    liability_exposure: MonetaryExposureEstimate
    uncapped_signal: bool
    ambiguous_signal: bool

    @property
    def uncapped(self) -> bool:
        return self.uncapped_signal


@dataclass(frozen=True)
class Fim8Result:
    adjusted_exposure: MonetaryExposureEstimate
    band_widen_factor: Decimal
    opacity_flags: tuple[str, ...]


@dataclass(frozen=True)
class FimCoreTestReport:
    fim_1_t1: bool
    fim_2_t1: bool
    fim_3_t1: bool
    fim_7_t1: bool
    fim_7_t2: bool

    @property
    def ok(self) -> bool:
        return (
            self.fim_1_t1
            and self.fim_2_t1
            and self.fim_3_t1
            and self.fim_7_t1
            and self.fim_7_t2
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "fim_1_t1": self.fim_1_t1,
            "fim_2_t1": self.fim_2_t1,
            "fim_3_t1": self.fim_3_t1,
            "fim_7_t1": self.fim_7_t1,
            "fim_7_t2": self.fim_7_t2,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class FimScenarioTestReport:
    fim_4_t1: bool
    fim_5_t1: bool
    fim_6_t1: bool

    @property
    def ok(self) -> bool:
        return self.fim_4_t1 and self.fim_5_t1 and self.fim_6_t1

    def as_dict(self) -> dict[str, bool]:
        return {
            "fim_4_t1": self.fim_4_t1,
            "fim_5_t1": self.fim_5_t1,
            "fim_6_t1": self.fim_6_t1,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class BlankWithoutInputsTestReport:
    fim_4_blank: bool
    fim_5_blank: bool
    fim_6_blank: bool
    fim_7_expected_path_blank: bool

    @property
    def ok(self) -> bool:
        return (
            self.fim_4_blank
            and self.fim_5_blank
            and self.fim_6_blank
            and self.fim_7_expected_path_blank
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "fim_4_blank": self.fim_4_blank,
            "fim_5_blank": self.fim_5_blank,
            "fim_6_blank": self.fim_6_blank,
            "fim_7_expected_path_blank": self.fim_7_expected_path_blank,
            "ok": self.ok,
        }


@dataclass(frozen=True)
class ExposureSeparationTestReport:
    sc_sep_t1_no_cross_type_summation: bool
    exposure_types: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.sc_sep_t1_no_cross_type_summation

    def as_dict(self) -> dict[str, object]:
        return {
            "sc_sep_t1_no_cross_type_summation": self.sc_sep_t1_no_cross_type_summation,
            "exposure_types": list(self.exposure_types),
            "ok": self.ok,
        }


def fim1_revenue_base_deduction_leakage(
    gross_sales: DecimalLike,
    refunds: DecimalLike,
    explicitly_allowed_deductions: DecimalLike,
    revenue_share_rate: DecimalLike,
    fixed_fee: DecimalLike = 0,
    advance_recoupment: DecimalLike = 0,
    open_ended_deductions: RangeLike = 0,
) -> Fim1Result:
    """FIM-1: revenue-base and deduction leakage as nominal leakage only."""

    gross = _money(gross_sales, "gross_sales")
    refund_amount = _money(refunds, "refunds")
    allowed = _money(explicitly_allowed_deductions, "explicitly_allowed_deductions")
    rate = _fraction(revenue_share_rate, "revenue_share_rate")
    fixed = _money(fixed_fee, "fixed_fee")
    advance = _money(advance_recoupment, "advance_recoupment")
    open_deductions = _range(open_ended_deductions, "open_ended_deductions")

    creator_favorable_net = gross - refund_amount - allowed
    base_net = creator_favorable_net - open_deductions.base
    company_favorable_net = creator_favorable_net - open_deductions.high

    payout_without_open = _payout(fixed, rate, creator_favorable_net, advance)
    payout_open_low = _payout(
        fixed,
        rate,
        creator_favorable_net - open_deductions.low,
        advance,
    )
    payout_base = _payout(fixed, rate, base_net, advance)
    payout_low = _payout(fixed, rate, company_favorable_net, advance)

    leakage_low = _nonnegative(payout_without_open - payout_open_low)
    leakage_base = _nonnegative(payout_without_open - payout_base)
    leakage_high = _nonnegative(payout_without_open - payout_low)
    leakage_range = _ordered_range(leakage_low, leakage_base, leakage_high, "nominal_leakage")

    return Fim1Result(
        net_sales=DecimalRange(
            low=company_favorable_net,
            base=base_net,
            high=creator_favorable_net,
        ),
        creator_payout=DecimalRange(low=payout_low, base=payout_base, high=payout_without_open),
        nominal_leakage=_exposure(
            module=FimModule.FIM_1,
            exposure_type=ExposureType.NOMINAL_LEAKAGE,
            values=leakage_range,
            assumptions=(
                "synthetic assumption: open-ended deductions are modeled low/base/high",
            ),
        ),
        leakage=leakage_high,
    )


def fim2_payment_delay_present_value_loss(
    delayed_amount: DecimalLike,
    annual_discount_rate: RangeLike,
    delay_days: RangeLike,
) -> Fim2Result:
    """FIM-2: present-value loss with nominal unpaid amount kept separate."""

    nominal = _money(delayed_amount, "delayed_amount")
    rate = _range(annual_discount_rate, "annual_discount_rate")
    days = _range(delay_days, "delay_days")
    low = _delay_pv_loss(nominal, rate.low, days.low)
    base = _delay_pv_loss(nominal, rate.base, days.base)
    high = _delay_pv_loss(nominal, rate.high, days.high)
    pv_range = _ordered_range(low, base, high, "present_value_loss")

    return Fim2Result(
        nominal_amount=nominal,
        delay_pv_loss=base,
        present_value_loss=_exposure(
            module=FimModule.FIM_2,
            exposure_type=ExposureType.PRESENT_VALUE_LOSS,
            values=pv_range,
            assumptions=("synthetic assumption: discount-rate and delay scenarios are editable",),
            nominal_amount=nominal,
        ),
    )


def fim3_mg_advance_recoupment(
    advance: DecimalLike | None = None,
    cumulative_recouped: DecimalLike = 0,
    revenue_share_rate: DecimalLike = 0,
    monthly_net_sales: RangeLike | None = None,
    *,
    minimum_guarantee: DecimalLike | None = None,
    recoupable_advance: DecimalLike | None = None,
) -> Fim3Result:
    """FIM-3: recoupment balance, monthly recoupment, and deferral exposure."""

    recoupable = _first_money(
        (
            ("recoupable_advance", recoupable_advance),
            ("advance", advance),
            ("minimum_guarantee", minimum_guarantee),
        )
    )
    recouped = _money(cumulative_recouped, "cumulative_recouped")
    rate = _fraction(revenue_share_rate, "revenue_share_rate")
    if monthly_net_sales is None:
        raise FinanceImpactError("monthly_net_sales is required for FIM-3")
    monthly_sales = _range(monthly_net_sales, "monthly_net_sales")

    balance = _nonnegative(recoupable - recouped)
    monthly_recoupment = DecimalRange(
        low=rate * monthly_sales.low,
        base=rate * monthly_sales.base,
        high=rate * monthly_sales.high,
    )
    months = RecoupmentTimeline(
        low_sales=_months_to_recoup(balance, monthly_recoupment.low),
        base_sales=_months_to_recoup(balance, monthly_recoupment.base),
        high_sales=_months_to_recoup(balance, monthly_recoupment.high),
    )

    return Fim3Result(
        recoupment_balance=balance,
        monthly_recoupment=monthly_recoupment,
        months_to_recoup_by_sales=months,
        deferral=_exposure(
            module=FimModule.FIM_3,
            exposure_type=ExposureType.DEFERRAL,
            values=DecimalRange(low=balance, base=balance, high=balance),
            assumptions=(
                "low/base/high columns label monthly sales assumptions, not exposure severity",
            ),
            nominal_amount=balance,
        ),
        sales_label_note=(
            "low/base/high labels track monthly sales; low sales produces the longest "
            "recoupment timeline"
        ),
    )


def fim4_unpaid_additional_work_cost(
    unpaid_revision_units: RangeLike | None = None,
    hours_per_unit: RangeLike | None = None,
    creator_hourly_value: RangeLike | None = None,
) -> Fim4Result:
    """FIM-4: unpaid additional-work cost from user-editable scenario inputs."""

    missing = _missing_inputs(
        (
            ("unpaid_revision_units", unpaid_revision_units),
            ("hours_per_unit", hours_per_unit),
            ("creator_hourly_value", creator_hourly_value),
        )
    )
    if missing:
        return Fim4Result(
            unpaid_work_cost=_blank_user_required_exposure(
                module=FimModule.FIM_4,
                exposure_type=ExposureType.OPPORTUNITY_COST,
                missing_inputs=missing,
            ),
            missing_inputs=missing,
        )

    units = _count_range(unpaid_revision_units, "unpaid_revision_units")
    hours = _range(hours_per_unit, "hours_per_unit")
    hourly = _range(creator_hourly_value, "creator_hourly_value")
    values = _ordered_range(
        units.low * hours.low * hourly.low,
        units.base * hours.base * hourly.base,
        units.high * hours.high * hourly.high,
        "unpaid_work_cost",
    )

    return Fim4Result(
        unpaid_work_cost=_exposure(
            module=FimModule.FIM_4,
            exposure_type=ExposureType.OPPORTUNITY_COST,
            values=values,
            assumptions=(
                "synthetic assumption: additional-work units, hours, and hourly value "
                "are user-supplied/editable",
            ),
        )
    )


def fim5_exclusivity_renewal_opportunity_cost(
    exclusivity_duration_months: RangeLike | None = None,
    alternative_monthly_revenue: RangeLike | None = None,
    scenario_probability: RangeLike | None = None,
    annual_discount_rate: RangeLike = Decimal("0.05"),
    *,
    renewal_duration_months: RangeLike | None = None,
    include_renewal: bool = False,
) -> Fim5Result:
    """FIM-5: discounted scenario opportunity cost for exclusivity/renewal."""

    if not isinstance(include_renewal, bool):
        raise FinanceImpactError("include_renewal must be bool")
    missing_pairs: list[tuple[str, object | None]] = [
        ("exclusivity_duration_months", exclusivity_duration_months),
        ("alternative_monthly_revenue", alternative_monthly_revenue),
        ("scenario_probability", scenario_probability),
    ]
    if include_renewal:
        missing_pairs.append(("renewal_duration_months", renewal_duration_months))
    missing = _missing_inputs(tuple(missing_pairs))
    if missing:
        return Fim5Result(
            opportunity_cost=_blank_user_required_exposure(
                module=FimModule.FIM_5,
                exposure_type=ExposureType.OPPORTUNITY_COST,
                missing_inputs=missing,
            ),
            scenario_months=None,
            includes_renewal=include_renewal,
            missing_inputs=missing,
        )

    exclusivity_months = _count_range(exclusivity_duration_months, "exclusivity_duration_months")
    renewal_months = (
        _count_range(renewal_duration_months, "renewal_duration_months")
        if include_renewal
        else DecimalRange(low=Decimal("0"), base=Decimal("0"), high=Decimal("0"))
    )
    months = (
        int(exclusivity_months.low + renewal_months.low),
        int(exclusivity_months.base + renewal_months.base),
        int(exclusivity_months.high + renewal_months.high),
    )
    alternative = _range(alternative_monthly_revenue, "alternative_monthly_revenue")
    probability = _range(scenario_probability, "scenario_probability", maximum=Decimal("1"))
    rate = _range(annual_discount_rate, "annual_discount_rate")
    values = _ordered_range(
        _discounted_monthly_scenario_sum(
            alternative.low,
            probability.low,
            rate.high,
            months[0],
        ),
        _discounted_monthly_scenario_sum(
            alternative.base,
            probability.base,
            rate.base,
            months[1],
        ),
        _discounted_monthly_scenario_sum(
            alternative.high,
            probability.high,
            rate.low,
            months[2],
        ),
        "opportunity_cost",
    )

    return Fim5Result(
        opportunity_cost=_exposure(
            module=FimModule.FIM_5,
            exposure_type=ExposureType.OPPORTUNITY_COST,
            values=values,
            assumptions=(
                "synthetic assumption: alternative revenue and scenario probability "
                "are user-supplied/editable",
                "synthetic assumption: annual discount rate is user-editable",
            ),
        ),
        scenario_months=months,
        includes_renewal=include_renewal,
    )


def fim6_ip_secondary_rights_scenario_value(
    secondary_rights: Sequence[Mapping[str, object]] | None = None,
    annual_discount_rate: RangeLike | None = Decimal("0.05"),
) -> Fim6Result:
    """FIM-6: user-supplied scenario value for IP and secondary rights."""

    missing = _secondary_rights_missing_inputs(secondary_rights)
    if missing:
        return Fim6Result(
            scenario_value=_blank_user_required_exposure(
                module=FimModule.FIM_6,
                exposure_type=ExposureType.OPPORTUNITY_COST,
                missing_inputs=missing,
            ),
            right_types=(),
            missing_inputs=missing,
        )

    assert secondary_rights is not None
    has_timing = any(
        isinstance(right, Mapping) and right.get("timing_months") is not None
        for right in secondary_rights
    )
    rate = (
        _range(annual_discount_rate, "annual_discount_rate")
        if has_timing and annual_discount_rate is not None
        else None
    )
    low = Decimal("0")
    base = Decimal("0")
    high = Decimal("0")
    right_types: list[str] = []
    for idx, right in enumerate(secondary_rights, start=1):
        if not isinstance(right, Mapping):
            raise FinanceImpactError(f"secondary_rights[{idx}] must be a mapping")
        right_type = str(right["type"]).strip()
        if not right_type:
            raise FinanceImpactError(f"secondary_rights[{idx}].type must be non-empty")
        right_types.append(right_type)
        value = _range(right["value"], f"secondary_rights[{idx}].value")
        probability = _range(
            right["prob"],
            f"secondary_rights[{idx}].prob",
            maximum=Decimal("1"),
        )
        timing = _optional_count(right.get("timing_months"), f"secondary_rights[{idx}].timing")
        if timing is None:
            low += probability.low * value.low
            base += probability.base * value.base
            high += probability.high * value.high
        else:
            low += _discounted_scenario_value(
                value.low,
                probability.low,
                rate,
                timing,
                high_case=False,
            )
            base += _discounted_scenario_value(
                value.base,
                probability.base,
                rate,
                timing,
                high_case=None,
            )
            high += _discounted_scenario_value(
                value.high,
                probability.high,
                rate,
                timing,
                high_case=True,
            )
    values = _ordered_range(low, base, high, "secondary_rights_scenario_value")
    assumptions = [
        "synthetic assumption: secondary-rights values and probabilities are "
        "user-supplied scenarios",
        "no automatic IP valuation is inferred from contract text",
    ]
    if rate is not None:
        assumptions.append("synthetic assumption: annual discount rate is user-editable")

    return Fim6Result(
        scenario_value=_exposure(
            module=FimModule.FIM_6,
            exposure_type=ExposureType.OPPORTUNITY_COST,
            values=values,
            assumptions=tuple(assumptions),
        ),
        right_types=tuple(right_types),
    )


def fim7_penalty_liability_exposure(
    explicit_penalty_cap: DecimalLike | None = None,
    *,
    cap: DecimalLike | None = None,
    penalty_basis: str | None = None,
    is_uncapped: bool = False,
    is_ambiguous: bool = False,
    penalty_probability: RangeLike | None = None,
    scenario_amount: RangeLike | None = None,
) -> Fim7Result:
    """FIM-7: capped liability and optional user-scenario expected penalty."""

    if explicit_penalty_cap is not None and cap is not None:
        raise FinanceImpactError("provide only one of explicit_penalty_cap or cap")
    raw_cap = explicit_penalty_cap if explicit_penalty_cap is not None else cap
    max_nominal = _money(raw_cap, "explicit_penalty_cap") if raw_cap is not None else None
    if penalty_basis is not None and not penalty_basis.strip():
        raise FinanceImpactError("penalty_basis must be non-empty when provided")

    expected_range: DecimalRange | None = None
    if penalty_probability is not None:
        if scenario_amount is None:
            raise FinanceImpactError("scenario_amount is required when penalty_probability is set")
        probability = _range(penalty_probability, "penalty_probability", maximum=Decimal("1"))
        scenario = _range(scenario_amount, "scenario_amount")
        expected_range = _ordered_range(
            probability.low * scenario.low,
            probability.base * scenario.base,
            probability.high * scenario.high,
            "expected_penalty",
        )

    if expected_range is not None:
        liability_values: DecimalRange | None = expected_range
        user_input_required = False
    elif max_nominal is not None:
        liability_values = DecimalRange(low=max_nominal, base=max_nominal, high=max_nominal)
        user_input_required = False
    else:
        liability_values = None
        user_input_required = True

    flags = []
    if is_uncapped:
        flags.append("uncapped")
    if is_ambiguous:
        flags.append("ambiguous")
    if expected_range is None and (is_uncapped or is_ambiguous):
        flags.append("scenario_required")

    return Fim7Result(
        max_nominal_exposure=max_nominal,
        expected_penalty=expected_range.base if expected_range is not None else None,
        liability_exposure=_exposure(
            module=FimModule.FIM_7,
            exposure_type=ExposureType.LIABILITY_EXPOSURE,
            values=liability_values,
            assumptions=("synthetic assumption: penalty probability is user-supplied",)
            if expected_range is not None
            else (),
            nominal_amount=max_nominal,
            is_user_input_required=user_input_required,
            uncertainty_flags=tuple(flags) or None,
        ),
        uncapped_signal=is_uncapped,
        ambiguous_signal=is_ambiguous,
    )


def fim8_evidence_opacity_uncertainty(
    exposure: MonetaryExposureEstimate,
    opacity_flags: Sequence[str],
    opacity_weights: Mapping[str, DecimalLike],
) -> Fim8Result:
    """FIM-8: widen uncertainty bands for opaque evidence without changing base."""

    _require_exposure(exposure, "exposure")
    flags = _unique_text_flags(opacity_flags, "opacity_flags")
    weights = _opacity_weight_map(opacity_weights)
    unknown_flags = tuple(flag for flag in flags if flag not in weights)
    if unknown_flags:
        raise FinanceImpactError(f"unknown FIM-8 opacity flag(s): {', '.join(unknown_flags)}")

    band_widen_factor = Decimal("1") + sum((weights[flag] for flag in flags), Decimal("0"))
    if band_widen_factor < Decimal("1"):
        raise FinanceImpactError("band_widen_factor must be >= 1")

    if exposure.low is None and exposure.base is None and exposure.high is None:
        values = None
    else:
        if exposure.low is None or exposure.base is None or exposure.high is None:
            raise FinanceImpactError("FIM-8 exposure range must be all set or all null")
        values = DecimalRange(
            low=exposure.low / band_widen_factor,
            base=exposure.base,
            high=exposure.high * band_widen_factor,
        )

    adjusted = _exposure(
        module=exposure.module,
        exposure_type=exposure.exposure_type,
        values=values,
        assumptions=(
            *exposure.assumptions,
            "heuristic: FIM-8 opacity flags widen low/high only; base is unchanged",
        ),
        nominal_amount=exposure.nominal_amount,
        is_user_input_required=exposure.is_user_input_required,
        uncertainty_flags=_merge_uncertainty_flags(
            exposure.uncertainty_flags,
            tuple(f"opacity:{flag}" for flag in flags),
            (f"band_widen_factor:{band_widen_factor}",),
        ),
    )
    return Fim8Result(
        adjusted_exposure=adjusted,
        band_widen_factor=band_widen_factor,
        opacity_flags=flags,
    )


def fim8_uncertainty_test(config_path: Path | str | None = None) -> object:
    """Run the cross-module FIM-8 machine gate from the finance namespace."""

    from fink.scoring import DEFAULT_SCORING_CONFIG_PATH
    from fink.scoring import fim8_uncertainty_test as scoring_fim8_uncertainty_test

    return scoring_fim8_uncertainty_test(
        DEFAULT_SCORING_CONFIG_PATH if config_path is None else config_path
    )


def partition_exposures_by_type(
    exposures: Sequence[MonetaryExposureEstimate],
) -> dict[ExposureType, tuple[MonetaryExposureEstimate, ...]]:
    partitions: dict[ExposureType, list[MonetaryExposureEstimate]] = {}
    for exposure in exposures:
        partitions.setdefault(exposure.exposure_type, []).append(exposure)
    return {exposure_type: tuple(rows) for exposure_type, rows in partitions.items()}


def exposure_type_subtotals(
    exposures: Sequence[MonetaryExposureEstimate],
) -> dict[ExposureType, DecimalRange]:
    """Return per-type subtotals only; no cross-type grand total is produced."""

    subtotals: dict[ExposureType, DecimalRange] = {}
    for exposure_type, rows in partition_exposures_by_type(exposures).items():
        low = sum((row.low for row in rows if row.low is not None), Decimal("0"))
        base = sum((row.base for row in rows if row.base is not None), Decimal("0"))
        high = sum((row.high for row in rows if row.high is not None), Decimal("0"))
        subtotals[exposure_type] = DecimalRange(low=low, base=base, high=high)
    return subtotals


def _blank_user_required_exposure(
    *,
    module: FimModule,
    exposure_type: ExposureType,
    missing_inputs: tuple[str, ...],
) -> MonetaryExposureEstimate:
    return _exposure(
        module=module,
        exposure_type=exposure_type,
        values=None,
        assumptions=(),
        is_user_input_required=True,
        uncertainty_flags=tuple(f"missing_user_input:{item}" for item in missing_inputs),
    )


def _require_exposure(value: object, field_name: str) -> None:
    if not isinstance(value, MonetaryExposureEstimate):
        raise FinanceImpactError(f"{field_name} must be MonetaryExposureEstimate")


def _unique_text_flags(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise FinanceImpactError(f"{field_name} must be a sequence, not a string")
    seen: set[str] = set()
    flags: list[str] = []
    for idx, raw_value in enumerate(values, start=1):
        value = str(raw_value).strip()
        if not value:
            raise FinanceImpactError(f"{field_name}[{idx}] must be non-empty")
        if value not in seen:
            seen.add(value)
            flags.append(value)
    return tuple(flags)


def _opacity_weight_map(values: Mapping[str, DecimalLike]) -> dict[str, Decimal]:
    if not isinstance(values, Mapping):
        raise FinanceImpactError("opacity_weights must be a mapping")
    weights: dict[str, Decimal] = {}
    for raw_key, raw_value in values.items():
        key = str(raw_key).strip()
        if not key:
            raise FinanceImpactError("opacity_weights keys must be non-empty")
        weight = _nonnegative(_decimal(raw_value, f"opacity_weights.{key}"))
        weights[key] = weight
    return weights


def _merge_uncertainty_flags(*groups: tuple[str, ...] | None) -> tuple[str, ...] | None:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        if group is None:
            continue
        for value in group:
            if value not in seen:
                seen.add(value)
                merged.append(value)
    return tuple(merged) or None


def fim_core_unit_tests() -> FimCoreTestReport:
    fim1 = fim1_revenue_base_deduction_leakage(
        gross_sales=Decimal("10000000"),
        refunds=Decimal("500000"),
        explicitly_allowed_deductions=Decimal("1000000"),
        revenue_share_rate=Decimal("0.7"),
        fixed_fee=Decimal("0"),
        advance_recoupment=Decimal("0"),
        open_ended_deductions=DecimalRange(
            low=Decimal("0"),
            base=Decimal("1000000"),
            high=Decimal("2000000"),
        ),
    )
    fim2 = fim2_payment_delay_present_value_loss(
        delayed_amount=Decimal("10000000"),
        annual_discount_rate=Decimal("0.05"),
        delay_days=Decimal("180"),
    )
    fim3 = fim3_mg_advance_recoupment(
        advance=Decimal("12000000"),
        cumulative_recouped=Decimal("0"),
        revenue_share_rate=Decimal("0.7"),
        monthly_net_sales=DecimalRange(
            low=Decimal("1000000"),
            base=Decimal("2000000"),
            high=Decimal("4000000"),
        ),
    )
    fim7_capped = fim7_penalty_liability_exposure(
        explicit_penalty_cap=Decimal("5000000"),
        penalty_probability=Decimal("0.1"),
        scenario_amount=Decimal("5000000"),
    )
    fim7_uncapped = fim7_penalty_liability_exposure(is_uncapped=True)

    return FimCoreTestReport(
        fim_1_t1=fim1.leakage == Decimal("1400000")
        and fim1.nominal_leakage.exposure_type is ExposureType.NOMINAL_LEAKAGE,
        fim_2_t1=_within_percent(fim2.delay_pv_loss, Decimal("237700"), Decimal("0.01"))
        and fim2.present_value_loss.nominal_amount == Decimal("10000000"),
        fim_3_t1=fim3.months_to_recoup == (18, 9, 5)
        and fim3.deferral.base == Decimal("12000000"),
        fim_7_t1=fim7_capped.max_nominal_exposure == Decimal("5000000")
        and fim7_capped.expected_penalty == Decimal("500000"),
        fim_7_t2=fim7_uncapped.expected_penalty is None
        and fim7_uncapped.uncapped_signal
        and fim7_uncapped.liability_exposure.low is None
        and fim7_uncapped.liability_exposure.base is None
        and fim7_uncapped.liability_exposure.high is None,
    )


def fim_scenario_unit_tests() -> FimScenarioTestReport:
    fim4 = fim4_unpaid_additional_work_cost(
        unpaid_revision_units=Decimal("5"),
        hours_per_unit=Decimal("8"),
        creator_hourly_value=DecimalRange(
            low=Decimal("20000"),
            base=Decimal("30000"),
            high=Decimal("40000"),
        ),
    )
    fim5 = fim5_exclusivity_renewal_opportunity_cost(
        exclusivity_duration_months=Decimal("12"),
        alternative_monthly_revenue=Decimal("1000000"),
        scenario_probability=DecimalRange(
            low=Decimal("0.25"),
            base=Decimal("0.5"),
            high=Decimal("0.75"),
        ),
        annual_discount_rate=Decimal("0.05"),
    )
    fim6 = fim6_ip_secondary_rights_scenario_value(
        secondary_rights=(
            {"type": "overseas", "value": Decimal("5000000"), "prob": Decimal("0.4")},
            {"type": "merchandise", "value": Decimal("3000000"), "prob": Decimal("0.2")},
        )
    )

    return FimScenarioTestReport(
        fim_4_t1=fim4.unpaid_work_cost.low == Decimal("800000")
        and fim4.unpaid_work_cost.base == Decimal("1200000")
        and fim4.unpaid_work_cost.high == Decimal("1600000")
        and fim4.unpaid_work_cost.module is FimModule.FIM_4
        and fim4.unpaid_work_cost.exposure_type is ExposureType.OPPORTUNITY_COST,
        fim_5_t1=_within_percent(
            fim5.opportunity_cost.base or Decimal("0"),
            Decimal("5845000"),
            Decimal("0.01"),
        )
        and fim5.opportunity_cost.module is FimModule.FIM_5
        and any("synthetic assumption" in item for item in fim5.opportunity_cost.assumptions),
        fim_6_t1=fim6.scenario_value.base == Decimal("2600000.0")
        and fim6.scenario_value.module is FimModule.FIM_6
        and fim6.auto_valued_from_contract_text is False,
    )


def blank_without_inputs_test() -> BlankWithoutInputsTestReport:
    fim4 = fim4_unpaid_additional_work_cost()
    fim5 = fim5_exclusivity_renewal_opportunity_cost(
        exclusivity_duration_months=Decimal("12"),
    )
    fim6 = fim6_ip_secondary_rights_scenario_value()
    fim7 = fim7_penalty_liability_exposure(is_uncapped=True)

    return BlankWithoutInputsTestReport(
        fim_4_blank=_is_blank_user_required(fim4.unpaid_work_cost),
        fim_5_blank=_is_blank_user_required(fim5.opportunity_cost),
        fim_6_blank=_is_blank_user_required(fim6.scenario_value),
        fim_7_expected_path_blank=_is_blank_user_required(fim7.liability_exposure),
    )


def exposure_separation_test() -> ExposureSeparationTestReport:
    fim1 = fim1_revenue_base_deduction_leakage(
        Decimal("10000000"),
        Decimal("500000"),
        Decimal("1000000"),
        Decimal("0.7"),
        open_ended_deductions=DecimalRange(
            low=Decimal("0"),
            base=Decimal("1000000"),
            high=Decimal("2000000"),
        ),
    )
    fim2 = fim2_payment_delay_present_value_loss(
        Decimal("10000000"),
        Decimal("0.05"),
        Decimal("180"),
    )
    fim3 = fim3_mg_advance_recoupment(
        Decimal("12000000"),
        Decimal("0"),
        Decimal("0.7"),
        DecimalRange(low=Decimal("1000000"), base=Decimal("2000000"), high=Decimal("4000000")),
    )
    fim5 = fim5_exclusivity_renewal_opportunity_cost(
        exclusivity_duration_months=Decimal("12"),
        alternative_monthly_revenue=Decimal("1000000"),
        scenario_probability=Decimal("0.5"),
        annual_discount_rate=Decimal("0.05"),
    )
    fim7 = fim7_penalty_liability_exposure(
        Decimal("5000000"),
        penalty_probability=Decimal("0.1"),
        scenario_amount=Decimal("5000000"),
    )
    exposures = (
        fim1.nominal_leakage,
        fim2.present_value_loss,
        fim3.deferral,
        fim5.opportunity_cost,
        fim7.liability_exposure,
    )
    partitions = partition_exposures_by_type(exposures)
    subtotals = exposure_type_subtotals(exposures)
    expected_types = {
        ExposureType.NOMINAL_LEAKAGE,
        ExposureType.OPPORTUNITY_COST,
        ExposureType.PRESENT_VALUE_LOSS,
        ExposureType.DEFERRAL,
        ExposureType.LIABILITY_EXPOSURE,
    }
    no_cross_type_sum = set(partitions) == expected_types and set(subtotals) == expected_types
    return ExposureSeparationTestReport(
        sc_sep_t1_no_cross_type_summation=no_cross_type_sum,
        exposure_types=tuple(sorted(exposure_type.value for exposure_type in partitions)),
    )


def _exposure(
    *,
    module: FimModule,
    exposure_type: ExposureType,
    values: DecimalRange | None,
    assumptions: tuple[str, ...],
    nominal_amount: Decimal | None = None,
    is_user_input_required: bool = False,
    uncertainty_flags: tuple[str, ...] | None = None,
) -> MonetaryExposureEstimate:
    if values is None:
        low = base = high = None
    else:
        low, base, high = values.as_tuple()
    return MonetaryExposureEstimate(
        module=module,
        exposure_type=exposure_type,
        is_user_input_required=is_user_input_required,
        assumptions=assumptions,
        low=low,
        base=base,
        high=high,
        uncertainty_flags=uncertainty_flags,
        nominal_amount=nominal_amount,
    )


def _payout(fixed_fee: Decimal, rate: Decimal, net_sales: Decimal, advance: Decimal) -> Decimal:
    return fixed_fee + rate * max(net_sales, Decimal("0")) - advance


def _delay_pv_loss(amount: Decimal, annual_discount_rate: Decimal, delay_days: Decimal) -> Decimal:
    factor = Decimal("1") / ((Decimal("1") + annual_discount_rate) ** (delay_days / Decimal(365)))
    return amount * (Decimal("1") - factor)


def _discounted_monthly_scenario_sum(
    alternative_monthly_revenue: Decimal,
    scenario_probability: Decimal,
    annual_discount_rate: Decimal,
    months: int,
) -> Decimal:
    total = Decimal("0")
    for month in range(1, months + 1):
        total += scenario_probability * alternative_monthly_revenue / _discount_factor(
            annual_discount_rate,
            month,
        )
    return total


def _discounted_scenario_value(
    value: Decimal,
    probability: Decimal,
    rate: DecimalRange | None,
    timing_months: int,
    *,
    high_case: bool | None,
) -> Decimal:
    if rate is None:
        return value * probability
    if high_case is True:
        selected_rate = rate.low
    elif high_case is False:
        selected_rate = rate.high
    else:
        selected_rate = rate.base
    return value * probability / _discount_factor(selected_rate, timing_months)


def _discount_factor(annual_discount_rate: Decimal, months: int) -> Decimal:
    return (Decimal("1") + annual_discount_rate) ** (Decimal(months) / Decimal("12"))


def _months_to_recoup(balance: Decimal, monthly_recoupment: Decimal) -> int | float:
    if balance == 0:
        return 0
    if monthly_recoupment <= 0:
        return MONTHS_INF
    return int((balance / monthly_recoupment).to_integral_value(rounding=ROUND_CEILING))


def _first_money(candidates: Sequence[tuple[str, DecimalLike | None]]) -> Decimal:
    for label, value in candidates:
        if value is not None:
            return _money(value, label)
    raise FinanceImpactError("one of recoupable_advance, advance, or minimum_guarantee is required")


def _missing_inputs(candidates: Sequence[tuple[str, object | None]]) -> tuple[str, ...]:
    return tuple(label for label, value in candidates if value is None)


def _secondary_rights_missing_inputs(
    secondary_rights: Sequence[Mapping[str, object]] | None,
) -> tuple[str, ...]:
    if not secondary_rights:
        return ("secondary_rights",)
    missing: list[str] = []
    for idx, right in enumerate(secondary_rights, start=1):
        if not isinstance(right, Mapping):
            continue
        for key in ("type", "value", "prob"):
            value = right.get(key)
            if value is None or (key == "type" and not str(value).strip()):
                missing.append(f"secondary_rights[{idx}].{key}")
    return tuple(missing)


def _is_blank_user_required(exposure: MonetaryExposureEstimate) -> bool:
    return (
        exposure.is_user_input_required
        and exposure.low is None
        and exposure.base is None
        and exposure.high is None
    )


def _range(
    value: RangeLike,
    label: str,
    *,
    maximum: Decimal | None = None,
) -> DecimalRange:
    if isinstance(value, DecimalRange):
        raw_low, raw_base, raw_high = value.as_tuple()
    elif isinstance(value, Mapping):
        try:
            raw_low = value["low"]
            raw_base = value["base"]
            raw_high = value["high"]
        except KeyError as exc:
            raise FinanceImpactError(f"{label} range requires low/base/high") from exc
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        if len(value) != 3:
            raise FinanceImpactError(f"{label} range sequence must have exactly three values")
        raw_low, raw_base, raw_high = value
    else:
        raw_low = raw_base = raw_high = value

    low = _decimal(raw_low, f"{label}.low", maximum=maximum)
    base = _decimal(raw_base, f"{label}.base", maximum=maximum)
    high = _decimal(raw_high, f"{label}.high", maximum=maximum)
    return _ordered_range(low, base, high, label)


def _count_range(value: RangeLike | None, label: str) -> DecimalRange:
    raw_range = _range(value, label)
    return DecimalRange(
        low=_whole_count(raw_range.low, f"{label}.low"),
        base=_whole_count(raw_range.base, f"{label}.base"),
        high=_whole_count(raw_range.high, f"{label}.high"),
    )


def _optional_count(value: object | None, label: str) -> int | None:
    if value is None:
        return None
    return int(_whole_count(_decimal(value, label), label))


def _whole_count(value: Decimal, label: str) -> Decimal:
    if value != value.to_integral_value():
        raise FinanceImpactError(f"{label} must be a whole number")
    return value


def _ordered_range(low: Decimal, base: Decimal, high: Decimal, label: str) -> DecimalRange:
    if not low <= base <= high:
        raise FinanceImpactError(f"{label} must satisfy low <= base <= high")
    return DecimalRange(low=low, base=base, high=high)


def _money(value: DecimalLike | None, label: str) -> Decimal:
    if value is None:
        raise FinanceImpactError(f"{label} is required")
    return _decimal(value, label)


def _fraction(value: DecimalLike, label: str) -> Decimal:
    return _decimal(value, label, maximum=Decimal("1"))


def _decimal(
    value: Any,
    label: str,
    *,
    maximum: Decimal | None = None,
) -> Decimal:
    if isinstance(value, bool):
        raise FinanceImpactError(f"{label} must be numeric, not bool")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FinanceImpactError(f"{label} must be numeric") from exc
    if not number.is_finite():
        raise FinanceImpactError(f"{label} must be finite")
    if number < 0:
        raise FinanceImpactError(f"{label} must be >= 0")
    if maximum is not None and number > maximum:
        raise FinanceImpactError(f"{label} must be <= {maximum}")
    return number


def _nonnegative(value: Decimal) -> Decimal:
    return max(value, Decimal("0"))


def _within_percent(actual: Decimal, expected: Decimal, tolerance: Decimal) -> bool:
    return abs(actual - expected) <= expected * tolerance
