from app.geocooling.alarm_engine import GeoCoolingAlarmEngine
from app.geocooling.operations_suite import GeoCoolingOperationsSuite

class Stub:
    def __init__(self, value): self.value=value
    def status(self): return self.value
    def snapshot(self): return self.value

class Audit(Stub):
    pass

def make_suite(tmp_path, blockers=None, connected=False, armed=False):
    controller=Stub({"state":"IDLE"})
    health=Stub({"overall":"GOOD","errors":[],"warnings":[]})
    audit=Audit({"blockers": blockers or [], "verdict":"READY_FOR_COMMISSIONING" if not blockers else "NOT_READY"})
    hw=Stub({"driver_name":"waveshare_modbus","connected":connected,"ready":connected,"armed":armed})
    generic=Stub({})
    alarms=GeoCoolingAlarmEngine(str(tmp_path))
    return GeoCoolingOperationsSuite(controller=controller, health_manager=health, commissioning_manager=generic, commissioning_test_manager=generic, hardware_manual_control=hw, operations_dashboard=generic, integration_audit=audit, runtime_profiler=generic, efficiency_index=generic, drift_detector=generic, assisted_calibration=generic, digital_twin_calibration=generic, hardware_certification=generic, alarm_engine=alarms)

def test_software_ready_hardware_pending(tmp_path):
    suite=make_suite(tmp_path)
    assert suite.readiness()["stage"] == "SOFTWARE_READY_HARDWARE_PENDING"

def test_ready_for_automatic(tmp_path):
    suite=make_suite(tmp_path, connected=True, armed=True)
    assert suite.readiness()["stage"] == "READY_FOR_AUTOMATIC"

def test_blocker_creates_alarm(tmp_path):
    suite=make_suite(tmp_path, blockers=[{"code":"PERSISTENCE","message":"Répertoire absent"}])
    snap=suite.snapshot()
    assert snap["alarms"]["active_count"] == 1
    assert snap["readiness"]["stage"] == "NOT_READY"

def test_alarm_acknowledgement_persists(tmp_path):
    engine=GeoCoolingAlarmEngine(str(tmp_path))
    engine.synchronize([{"source":"test","code":"X","severity":"WARNING","message":"x"}])
    engine.acknowledge("test:X", "nicolas", "vu")
    reloaded=GeoCoolingAlarmEngine(str(tmp_path))
    assert reloaded.snapshot()["active"][0]["acknowledged"] is True

def test_report_is_read_only(tmp_path):
    report=make_suite(tmp_path).report()
    assert report["readiness"]["read_only"] is True
    assert report["report_type"] == "GEОCOOLING_COMMISSIONING_REPORT"
