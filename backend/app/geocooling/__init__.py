"""Contrôleur GeoCooling du Smart Building Controller."""

# Install hardware policy gates as soon as the geocooling package is imported.
# They are idempotent and preserve safety-stop / simulation behaviour.
from app.geocooling.commissioning_test_gate_patch import (
    install_commissioning_test_policy_gate,
)
from app.geocooling.direct_relay_gate_patch import (
    install_direct_relay_policy_gate,
)

install_commissioning_test_policy_gate()
install_direct_relay_policy_gate()
