from app.geocooling.rc1_architecture import CANONICAL_PIPELINE, LEGACY_OR_ADVISORY_COMPONENTS, architecture_status

def test_roles_unique():
    roles=[c.role for c in CANONICAL_PIPELINE]
    assert len(roles)==len(set(roles))

def test_required_roles():
    assert {c.role for c in CANONICAL_PIPELINE}=={"sensors","historian","weather","learning","thermal_engine","prediction","brain","safety","controller","hardware"}

def test_single_authority():
    status=architecture_status()
    assert status["authority"]["brain"]=="app.geocooling.brain.GeoCoolingBrain"
    assert status["authority"]["controller"]=="app.geocooling.controller"
    assert status["authority"]["hardware"]=="app.geocooling.waveshare_modbus_driver"

def test_legacy_not_canonical():
    assert {c.module for c in CANONICAL_PIPELINE}.isdisjoint({c.module for c in LEGACY_OR_ADVISORY_COMPONENTS})

def test_side_effect_free():
    assert architecture_status()["safety"]=={"side_effect_free":True,"hardware_write":False,"mqtt_publish":False,"database_write":False}
