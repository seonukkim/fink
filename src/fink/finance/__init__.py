"""Financial feature bindings and impact modules for FInk."""

_FEATURE_BINDING_EXPORTS = {
    "FeatureBinding",
    "FeatureBindingError",
    "FeatureBindingReport",
    "FimInputBinding",
    "feature_binding_complete",
    "load_feature_bindings",
}

_IMPACT_EXPORTS = {
    "BlankWithoutInputsTestReport",
    "DecimalRange",
    "ExposureSeparationTestReport",
    "Fim1Result",
    "Fim2Result",
    "Fim3Result",
    "Fim4Result",
    "Fim5Result",
    "Fim6Result",
    "Fim7Result",
    "FimCoreTestReport",
    "FimScenarioTestReport",
    "FinanceImpactError",
    "RecoupmentTimeline",
    "blank_without_inputs_test",
    "exposure_separation_test",
    "exposure_type_subtotals",
    "fim1_revenue_base_deduction_leakage",
    "fim2_payment_delay_present_value_loss",
    "fim3_mg_advance_recoupment",
    "fim4_unpaid_additional_work_cost",
    "fim5_exclusivity_renewal_opportunity_cost",
    "fim6_ip_secondary_rights_scenario_value",
    "fim7_penalty_liability_exposure",
    "fim_core_unit_tests",
    "fim_scenario_unit_tests",
    "partition_exposures_by_type",
}

__all__ = sorted(_FEATURE_BINDING_EXPORTS | _IMPACT_EXPORTS)


def __getattr__(name: str) -> object:
    if name in _FEATURE_BINDING_EXPORTS:
        from fink.finance import feature_bindings

        return getattr(feature_bindings, name)
    if name in _IMPACT_EXPORTS:
        from fink.finance import impact

        return getattr(impact, name)
    raise AttributeError(name)
