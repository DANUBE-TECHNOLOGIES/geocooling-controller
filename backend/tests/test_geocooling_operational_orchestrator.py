from app.geocooling.operational_orchestrator import GeoCoolingOperationalOrchestrator


class Journal:
    def __init__(self): self.items=[]
    def record(self, component, event, **kwargs): self.items.append((component,event,kwargs))


def base():
    return {
        "continuity": {"continuity_state":"READY","recovery_required":False,"automatic_mode_allowed":True},
        "availability": {"availability":"AVAILABLE","recovery_required":False,"automatic_mode_allowed":True},
        "confidence": {"confidence_level":"HIGH","automatic_mode_allowed":True},
        "safety": {"safe":True,"emergency_stop":False},
        "hardware": {"armed":False,"pump_running":False,"valve_open":False},
    }


def test_normal_state(tmp_path):
    manager=GeoCoolingOperationalOrchestrator(Journal(), str(tmp_path/'state.json'))
    report=manager.evaluate(**base())
    assert report['operational_state']=='NORMAL'
    assert report['automatic_mode_allowed'] is True
    assert report['physical_activation_allowed'] is False


def test_maintenance_interlock(tmp_path):
    manager=GeoCoolingOperationalOrchestrator(Journal(), str(tmp_path/'state.json'))
    manager.set_maintenance(True, operator='Nicolas', reason='inspection')
    report=manager.evaluate(**base())
    assert report['operational_state']=='MAINTENANCE'
    assert report['automatic_mode_allowed'] is False
    assert report['maintenance']['operator']=='Nicolas'


def test_recovery_and_blocked_states(tmp_path):
    manager=GeoCoolingOperationalOrchestrator(Journal(), str(tmp_path/'state.json'))
    values=base(); values['continuity']['recovery_required']=True
    assert manager.evaluate(**values)['operational_state']=='RECOVERY'
    values=base(); values['safety']['safe']=False
    assert manager.evaluate(**values)['operational_state']=='BLOCKED'


def test_maintenance_persists(tmp_path):
    path=str(tmp_path/'state.json')
    first=GeoCoolingOperationalOrchestrator(Journal(), path)
    first.set_maintenance(True, operator='Ops', reason='service')
    second=GeoCoolingOperationalOrchestrator(Journal(), path)
    assert second.maintenance_status()['active'] is True
