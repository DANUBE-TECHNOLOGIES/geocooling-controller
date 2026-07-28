from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

def now(): return datetime.now(timezone.utc).isoformat()
def safe(fn: Callable[[],Any], default=None):
    try: return fn()
    except Exception as exc: return {"available":False,"error":str(exc)} if default is None else default

class GeoCoolingOperationsSuite:
    def __init__(self, *, controller, health_manager, commissioning_manager, commissioning_test_manager, hardware_manual_control, operations_dashboard, integration_audit, runtime_profiler, efficiency_index, drift_detector, assisted_calibration, digital_twin_calibration, hardware_certification, alarm_engine):
        self.controller=controller; self.health_manager=health_manager; self.commissioning_manager=commissioning_manager; self.commissioning_test_manager=commissioning_test_manager; self.hardware_manual_control=hardware_manual_control; self.operations_dashboard=operations_dashboard; self.integration_audit=integration_audit; self.runtime_profiler=runtime_profiler; self.efficiency_index=efficiency_index; self.drift_detector=drift_detector; self.assisted_calibration=assisted_calibration; self.digital_twin_calibration=digital_twin_calibration; self.hardware_certification=hardware_certification; self.alarm_engine=alarm_engine
    def _findings(self,data):
        out=[]
        audit=data.get("integration_audit",{})
        for i,item in enumerate(audit.get("blockers",[]) or []): out.append({"source":"integration_audit","code":str(item.get("code",f"BLOCKER_{i}")) if isinstance(item,dict) else f"BLOCKER_{i}","severity":"ERROR","message":item.get("message",str(item)) if isinstance(item,dict) else str(item),"recommendation":"Corriger le blocage avant l’automatisme."})
        health=data.get("health",{})
        for i,msg in enumerate(health.get("errors",[]) or []): out.append({"source":"health","code":f"HEALTH_ERROR_{i}","severity":"ERROR","message":str(msg)})
        for i,msg in enumerate(health.get("warnings",[]) or []): out.append({"source":"health","code":f"HEALTH_WARNING_{i}","severity":"WARNING","message":str(msg)})
        runtime=data.get("runtime",{})
        if runtime.get("slow_calls",0): out.append({"source":"runtime","code":"SLOW_CALLS","severity":"WARNING","message":f'{runtime.get("slow_calls")} appel(s) lent(s) détecté(s).',"recommendation":"Consulter le profil runtime."})
        return out
    def snapshot(self):
        data={"generated_at":now(),"version":"C025-1.0","read_only":True,"controller":safe(self.controller.status),"dashboard":safe(self.operations_dashboard.snapshot),"health":safe(self.health_manager.status),"integration_audit":safe(self.integration_audit.status),"runtime":safe(self.runtime_profiler.snapshot),"gei":safe(self.efficiency_index.status),"drift":safe(self.drift_detector.status),"calibration":safe(self.assisted_calibration.status),"digital_twin":safe(self.digital_twin_calibration.status),"hardware":safe(self.hardware_manual_control.status),"hardware_certification":safe(self.hardware_certification.status),"commissioning":safe(self.commissioning_manager.status),"commissioning_tests":safe(self.commissioning_test_manager.status)}
        data["alarms"]=self.alarm_engine.synchronize(self._findings(data)); data["readiness"]=self.readiness(data); return data
    def readiness(self,data=None):
        d=data or self.snapshot(); audit=d.get("integration_audit",{}); hw=d.get("hardware",{}); health=d.get("health",{})
        software=not bool(audit.get("blockers")) and health.get("overall") not in {"ERROR"}
        manual=software and bool(hw.get("driver_name"))
        hardware_ready=bool(hw.get("connected")) and bool(hw.get("ready"))
        automatic=software and hardware_ready and bool(hw.get("armed"))
        stage="READY_FOR_AUTOMATIC" if automatic else "READY_FOR_MANUAL_TESTS" if manual and hardware_ready else "SOFTWARE_READY_HARDWARE_PENDING" if software else "NOT_READY"
        return {"generated_at":now(),"stage":stage,"software_ready":software,"manual_tests_ready":manual and hardware_ready,"automatic_ready":automatic,"hardware_connected":bool(hw.get("connected")),"hardware_armed":bool(hw.get("armed")),"read_only":True}
    def checklist(self):
        r=self.readiness({"integration_audit":safe(self.integration_audit.status),"hardware":safe(self.hardware_manual_control.status),"health":safe(self.health_manager.status)})
        items=[("Logiciel sans blocage",r["software_ready"]),("Waveshare connecté",r["hardware_connected"]),("Essais manuels autorisés",r["manual_tests_ready"]),("Matériel armé",r["hardware_armed"]),("Automatisme autorisable",r["automatic_ready"])]
        return {"generated_at":now(),"stage":r["stage"],"items":[{"label":a,"complete":b} for a,b in items],"remaining":[a for a,b in items if not b]}
    def report(self):
        snap=self.snapshot(); return {"report_type":"GEОCOOLING_COMMISSIONING_REPORT","generated_at":now(),"software_version":"C025-1.0","readiness":snap["readiness"],"health":snap["health"],"alarms":snap["alarms"],"hardware_certification":snap["hardware_certification"],"commissioning":snap["commissioning"],"checklist":self.checklist()}
