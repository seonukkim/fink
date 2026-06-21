from __future__ import annotations

import importlib
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any


def _load_module(name: str) -> Any:
    src_root = Path(__file__).resolve().parents[2] / "src"
    src_text = src_root.as_posix()
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
    return importlib.import_module(name)


SCHEMAS = _load_module("fink.schemas")
WEB = _load_module("fink.web")


def _known_terms() -> dict[str, object]:
    return {
        "gross_sales": Decimal("10000000"),
        "refunds": Decimal("500000"),
        "explicitly_allowed_deductions": Decimal("1000000"),
        "revenue_share_rate": Decimal("0.7"),
        "fixed_fee": Decimal("0"),
        "advance_recoupment": Decimal("0"),
        "open_ended_deductions_low": Decimal("0"),
        "open_ended_deductions_base": Decimal("1000000"),
        "open_ended_deductions_high": Decimal("2000000"),
        "delayed_amount": Decimal("10000000"),
        "delay_days_low": Decimal("90"),
        "delay_days_base": Decimal("180"),
        "delay_days_high": Decimal("270"),
        "recoupable_advance": Decimal("12000000"),
        "cumulative_recouped": Decimal("0"),
        "exclusivity_duration_months": 12,
        "explicit_penalty_cap": Decimal("5000000"),
        "penalty_scenario_amount": Decimal("5000000"),
    }


def _scenario_inputs(**overrides: object) -> Any:
    values: dict[str, object] = {
        "annual_discount_rate": 0.05,
        "inputs_are_synthetic": True,
        "sales_low": Decimal("1000000"),
        "sales_base": Decimal("2000000"),
        "sales_high": Decimal("4000000"),
        "creator_hourly_value": Decimal("30000"),
        "hours_per_unit": 8,
        "unpaid_revision_units": 5,
        "alternative_monthly_revenue": Decimal("1000000"),
        "scenario_probabilities": {"low": 0.25, "base": 0.5, "high": 0.75},
        "secondary_rights": (
            {"type": "overseas", "value": Decimal("5000000"), "prob": 0.4},
            {"type": "merchandise", "value": Decimal("3000000"), "prob": 0.2},
        ),
        "penalty_probability": 0.1,
    }
    values.update(overrides)
    return SCHEMAS.FinancialScenarioInputs(**values)


def _editable(**overrides: object) -> Any:
    scenario_inputs = _scenario_inputs(
        **{
            key: overrides.pop(key)
            for key in tuple(overrides)
            if key
            in {
                "annual_discount_rate",
                "sales_low",
                "sales_base",
                "sales_high",
                "creator_hourly_value",
                "hours_per_unit",
                "unpaid_revision_units",
                "alternative_monthly_revenue",
                "scenario_probabilities",
                "secondary_rights",
                "penalty_probability",
            }
        }
    )
    terms = _known_terms()
    terms.update(overrides)
    return WEB.EditableAssumptions.from_financial_scenario_inputs(scenario_inputs, **terms)


def _rows_by_module(result: Any) -> dict[str, Any]:
    return {row.module.value: row for row in result.rows}


def _details(row: Any) -> dict[str, str]:
    return dict(row.details)


class AssumptionsPanelTests(unittest.TestCase):
    def test_assumptions_recompute_test_blank_until_inputs_are_supplied(self) -> None:
        result = WEB.recompute_assumptions()
        rows = _rows_by_module(result)

        self.assertTrue(result.live_recompute_ready)
        self.assertEqual(set(rows), {f"FIM-{idx}" for idx in range(1, 8)})
        for row in rows.values():
            self.assertTrue(row.exposure.is_user_input_required)
            self.assertIsNone(row.exposure.low)
            self.assertIsNone(row.exposure.base)
            self.assertIsNone(row.exposure.high)
            self.assertTrue(row.missing_inputs)

        markup = WEB.render_assumptions_panel_html()
        self.assertIn('data-assumptions-panel="true"', markup)
        self.assertIn('data-live-recompute="true"', markup)
        self.assertIn('data-fim-modules="FIM-1 FIM-2 FIM-3 FIM-4 FIM-5 FIM-6 FIM-7"', markup)
        self.assertIn("blank until inputs supplied", markup)
        self.assertIn('data-output-state="blank"', markup)
        self.assertNotIn('data-output-state="computed"', markup)
        self.assertNotIn("KRW 0", markup)
        self.assertNotIn('value="0"', markup)
        for spec in WEB.assumption_field_specs():
            self.assertIn(f'data-assumption-field="{spec.name}"', markup)
            self.assertIn('data-synthetic-assumption="true"', markup)

    def test_assumptions_recompute_test_computes_fim_1_through_7_from_inputs(self) -> None:
        result = WEB.recompute_assumptions(_editable())
        rows = _rows_by_module(result)

        self.assertEqual(tuple(rows), tuple(f"FIM-{idx}" for idx in range(1, 8)))
        self.assertTrue(all(not row.exposure.is_user_input_required for row in rows.values()))
        self.assertEqual(rows["FIM-1"].exposure.base, Decimal("700000.0"))
        self.assertEqual(rows["FIM-1"].exposure.high, Decimal("1400000.0"))
        self.assertEqual(rows["FIM-2"].exposure.nominal_amount, Decimal("10000000"))
        self.assertNotEqual(rows["FIM-2"].exposure.base, rows["FIM-2"].exposure.nominal_amount)
        self.assertEqual(rows["FIM-3"].exposure.base, Decimal("12000000"))
        self.assertEqual(_details(rows["FIM-3"])["months_to_recoup_base_sales"], "9")
        self.assertEqual(rows["FIM-4"].exposure.base, Decimal("1200000"))
        self.assertGreater(rows["FIM-5"].exposure.base or Decimal("0"), Decimal("5800000"))
        self.assertEqual(rows["FIM-6"].exposure.base, Decimal("2600000.0"))
        self.assertEqual(rows["FIM-7"].exposure.base, Decimal("500000.0"))

        for row in rows.values():
            self.assertTrue(
                any("synthetic assumption" in label for label in row.synthetic_labels),
                row,
            )

        markup = WEB.render_assumptions_panel_html(_editable())
        self.assertIn('data-output-state="computed"', markup)
        self.assertIn('<span class="badge synthetic-assumption">', markup)
        self.assertIn('data-assumption-detail="months_to_recoup_base_sales">9</span>', markup)
        self.assertIn("Nominal amount kept separate: KRW 10,000,000", markup)

    def test_assumptions_recompute_test_financial_scenario_edits_refresh_outputs(self) -> None:
        baseline = _rows_by_module(WEB.recompute_assumptions(_editable()))
        changed_cases = {
            "annual_discount_rate": _editable(annual_discount_rate=0.1),
            "sales_base": _editable(sales_base=Decimal("3000000")),
            "creator_hourly_value": _editable(creator_hourly_value=Decimal("40000")),
            "hours_per_unit": _editable(hours_per_unit=10),
            "unpaid_revision_units": _editable(unpaid_revision_units=6),
            "alternative_monthly_revenue": _editable(
                alternative_monthly_revenue=Decimal("1200000")
            ),
            "scenario_probabilities": _editable(
                scenario_probabilities={"low": 0.3, "base": 0.6, "high": 0.8}
            ),
            "secondary_rights": _editable(
                secondary_rights=(
                    {"type": "overseas", "value": Decimal("6000000"), "prob": 0.5},
                )
            ),
            "penalty_probability": _editable(penalty_probability=0.2),
        }

        self.assertNotEqual(
            _rows_by_module(WEB.recompute_assumptions(changed_cases["annual_discount_rate"]))[
                "FIM-2"
            ].exposure.base,
            baseline["FIM-2"].exposure.base,
        )
        self.assertNotEqual(
            _details(_rows_by_module(WEB.recompute_assumptions(changed_cases["sales_base"]))[
                "FIM-3"
            ])["months_to_recoup_base_sales"],
            _details(baseline["FIM-3"])["months_to_recoup_base_sales"],
        )
        for name in ("creator_hourly_value", "hours_per_unit", "unpaid_revision_units"):
            with self.subTest(name=name):
                self.assertNotEqual(
                    _rows_by_module(WEB.recompute_assumptions(changed_cases[name]))[
                        "FIM-4"
                    ].exposure.base,
                    baseline["FIM-4"].exposure.base,
                )
        for name in ("alternative_monthly_revenue", "scenario_probabilities"):
            with self.subTest(name=name):
                self.assertNotEqual(
                    _rows_by_module(WEB.recompute_assumptions(changed_cases[name]))[
                        "FIM-5"
                    ].exposure.base,
                    baseline["FIM-5"].exposure.base,
                )
        self.assertNotEqual(
            _rows_by_module(WEB.recompute_assumptions(changed_cases["secondary_rights"]))[
                "FIM-6"
            ].exposure.base,
            baseline["FIM-6"].exposure.base,
        )
        self.assertNotEqual(
            _rows_by_module(WEB.recompute_assumptions(changed_cases["penalty_probability"]))[
                "FIM-7"
            ].exposure.base,
            baseline["FIM-7"].exposure.base,
        )


if __name__ == "__main__":
    unittest.main()
