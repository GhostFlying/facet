"""Explicit function-scoped shared foundations; no implicit live-service setup."""

import pytest
from fakes.clock import Clock
from fakes.faults import Faults
from fakes.gmail import Controller
from fakes.network import deny_network


@pytest.fixture
def deny_external_network():
    with deny_network():
        yield


@pytest.fixture
def fake_clock():
    return Clock()


@pytest.fixture
def fake_faults():
    faults = Faults()
    try:
        yield faults
    finally:
        faults.close()
        faults.assert_consumed()


@pytest.fixture
def gmail_controller(fake_clock, fake_faults, deny_external_network):
    controller = Controller(fake_clock, fake_faults)
    try:
        yield controller
    finally:
        controller.assert_consumed()
