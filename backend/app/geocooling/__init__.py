"""Contrôleur GeoCooling du Smart Building Controller."""

# Install the commissioning-test hardware policy gate as soon as the
# geocooling package is imported. The patch is idempotent and affects only
# physical commissioning tests; simulation behaviour is unchanged.
from app.geocooling.commissioning_test_gate_patch import (
    install_commissioning_test_policy_gate,
)

install_commissioning_test_policy_gate()
