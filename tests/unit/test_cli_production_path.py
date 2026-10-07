import pytest

from facet.cli import bootstrap
from facet.sync import SyncCycleReceipt


@pytest.mark.parametrize(
    "expected_warnings", [(), ("expired_action_events_not_reconstructable",)]
)
def test_production_run_dispatches_reviewed_factory_without_exposing_provider_data(
    monkeypatch,
    expected_warnings,
):
    factory = object()
    seen = {}

    class Factory:
        def __new__(cls):
            return factory

    def run(owner, config, received_factory, **kwargs):
        seen.update(
            owner=owner,
            config=config,
            factory=received_factory,
            kwargs=kwargs,
        )
        return SyncCycleReceipt(
            discovered=2,
            history_pages=1,
            resolved_events=3,
            attention=2,
            warnings=expected_warnings,
        )

    monkeypatch.setattr(
        "facet.gmail.service_factory.GoogleGmailServiceFactory", Factory
    )

    monkeypatch.setattr("facet.runtime.foreground_runtime.run_foreground_once", run)

    owner = object()
    config = object()
    data, warnings = bootstrap._run_once_production(owner, config)

    assert data == {
        "discovered": 2,
        "history_pages": 1,
        "resolved_events": 3,
        "projected": 0,
        "attention": 2,
    }
    assert warnings == expected_warnings
    assert seen == {
        "owner": owner,
        "config": config,
        "factory": factory,
        "kwargs": {},
    }
