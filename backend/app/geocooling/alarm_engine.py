from __future__ import annotations
import json, os, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now(): return datetime.now(timezone.utc).isoformat()

class GeoCoolingAlarmEngine:
    """Read-mostly operational alarms with persistent acknowledgement history."""
    def __init__(self, data_dir: str | None = None):
        base=Path(data_dir or os.getenv("GEOCOOLING_DATA_DIR","/app/data/geocooling"))
        self.path=base/"alarms.jsonl"; self._lock=threading.RLock(); self._alarms={}
        self.path.parent.mkdir(parents=True, exist_ok=True); self._load()
    def _load(self):
        if not self.path.exists(): return
        for line in self.path.read_text(errors="ignore").splitlines():
            try:
                row=json.loads(line); self._alarms[row["alarm_id"]]=row
            except Exception: continue
    def _persist(self,row):
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False)+"\n")
    def synchronize(self, findings: list[dict[str,Any]]) -> dict[str,Any]:
        now=_now(); seen=set()
        with self._lock:
            for item in findings:
                key=f'{item.get("source","system")}:{item.get("code",item.get("message","unknown"))}'
                seen.add(key); alarm=self._alarms.get(key)
                if alarm is None:
                    alarm={"alarm_id":key,"event_id":str(uuid.uuid4()),"source":item.get("source","system"),"code":item.get("code","GENERIC"),"severity":item.get("severity","WARNING"),"message":item.get("message","Anomalie détectée"),"recommendation":item.get("recommendation"),"active":True,"acknowledged":False,"first_seen_at":now,"last_seen_at":now,"occurrences":1}
                else:
                    alarm.update({"active":True,"last_seen_at":now,"severity":item.get("severity",alarm["severity"]),"message":item.get("message",alarm["message"]),"recommendation":item.get("recommendation",alarm.get("recommendation")),"occurrences":int(alarm.get("occurrences",0))+1})
                self._alarms[key]=alarm; self._persist(alarm)
            for key,alarm in list(self._alarms.items()):
                if alarm.get("active") and key not in seen:
                    alarm={**alarm,"active":False,"resolved_at":now}; self._alarms[key]=alarm; self._persist(alarm)
        return self.snapshot()
    def acknowledge(self, alarm_id: str, operator: str="operator", note: str=""):
        with self._lock:
            if alarm_id not in self._alarms: raise KeyError("Alarme inconnue")
            row={**self._alarms[alarm_id],"acknowledged":True,"acknowledged_at":_now(),"acknowledged_by":operator,"acknowledgement_note":note}
            self._alarms[alarm_id]=row; self._persist(row); return row
    def snapshot(self):
        items=sorted(self._alarms.values(),key=lambda x:x.get("last_seen_at",""),reverse=True)
        active=[x for x in items if x.get("active")]
        return {"generated_at":_now(),"read_only_detection":True,"active_count":len(active),"unacknowledged_count":sum(not x.get("acknowledged") for x in active),"by_severity":{s:sum(x.get("severity")==s for x in active) for s in ("INFO","WARNING","ERROR","CRITICAL")},"active":active}
    def history(self,limit=200):
        return sorted(self._alarms.values(),key=lambda x:x.get("last_seen_at",""),reverse=True)[:limit]
