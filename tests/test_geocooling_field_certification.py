from app.geocooling.field_certification import GeoCoolingFieldCertification

class Ready:
    def status(self):
        return {"status": "PASS", "hardware_touched": False}

class Journal:
    def __init__(self): self.events=[]
    def record(self, *args, **kwargs): self.events.append((args, kwargs))

def complete_checks():
    return {name: True for name in GeoCoolingFieldCertification.REQUIRED_CHECKS}

def test_pass_certificate_is_signed_and_non_activating(tmp_path):
    service=GeoCoolingFieldCertification(Ready(), Journal(), str(tmp_path/'cert.json'))
    result=service.evaluate({"operator":"Nicolas", "site":"Chevannes", "checks":complete_checks()})
    assert result["status"] == "PASS"
    assert result["certificate_id"].startswith("H024-")
    assert len(result["sha256"]) == 64
    assert result["activation_allowed"] is False
    assert result["hardware_touched"] is False

def test_missing_check_fails(tmp_path):
    checks=complete_checks(); checks["protective_earth_verified"] = False
    result=GeoCoolingFieldCertification(Ready(), Journal(), str(tmp_path/'cert.json')).evaluate({"operator":"Nicolas", "checks":checks})
    assert result["status"] == "FAIL"

def test_operator_required(tmp_path):
    service=GeoCoolingFieldCertification(Ready(), Journal(), str(tmp_path/'cert.json'))
    try:
        service.evaluate({"checks":complete_checks()})
    except ValueError as exc:
        assert "operator" in str(exc)
    else:
        raise AssertionError("ValueError expected")

def test_persistence_and_history(tmp_path):
    path=tmp_path/'cert.json'
    service=GeoCoolingFieldCertification(Ready(), Journal(), str(path))
    service.evaluate({"operator":"Nicolas", "checks":complete_checks()})
    loaded=GeoCoolingFieldCertification(Ready(), Journal(), str(path))
    assert loaded.status()["certified"] is True
    assert len(loaded.certificates()) == 1
