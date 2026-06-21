"""Financial feature bindings for FInk."""

__all__ = [
    "FeatureBinding",
    "FeatureBindingError",
    "FeatureBindingReport",
    "FimInputBinding",
    "feature_binding_complete",
    "load_feature_bindings",
]


def __getattr__(name: str) -> object:
    if name in __all__:
        from fink.finance import feature_bindings

        return getattr(feature_bindings, name)
    raise AttributeError(name)
