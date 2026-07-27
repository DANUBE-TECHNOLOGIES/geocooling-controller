from __future__ import annotations
import math, os, statistics, threading
from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

class SensorValidationEngine:
    PATCH_VERSION = "C016.1R2"
    def __init__(self, *, sensor_discovery: Any, event_bus: Any=None, controller: Any=None, history_capacity_per_sensor: int=240, evaluation_history_capacity: int=500):
        self.sensor_discovery=sensor_discovery; self.event_bus=event_bus; self.controller=controller
        self.expected=max(1,int(os.getenv("GEOCOOLING_EXPECTED_DS18B20_COUNT","4")))
        self.min_c=float(os.getenv("GEOCOOLING_SENSOR_MIN_C","-10")); self.max_c=float(os.getenv("GEOCOOLING_SENSOR_MAX_C","60"))
        self.stale=max(10,int(os.getenv("GEOCOOLING_SENSOR_STALE_SECONDS","120")))
        self.min_samples=max(3,int(os.getenv("GEOCOOLING_SENSOR_VALIDATION_MIN_SAMPLES","5")))
        self.freeze_samples=max(4,int(os.getenv("GEOCOOLING_SENSOR_FREEZE_MIN_SAMPLES","8")))
        self.freeze_eps=max(0.0,float(os.getenv("GEOCOOLING_SENSOR_FREEZE_EPSILON_C","0.03")))
        self.max_jump=max(0.1,float(os.getenv("GEOCOOLING_SENSOR_MAX_JUMP_C","5.0")))
        self.max_spread=max(0.5,float(os.getenv("GEOCOOLING_SENSOR_MAX_SPREAD_C","20.0")))
        self.max_interval=max(10.0,float(os.getenv("GEOCOOLING_SENSOR_MAX_UPDATE_INTERVAL_SECONDS","120")))
        self._lock=threading.RLock(); self._samples=defaultdict(lambda: deque(maxlen=max(30,history_capacity_per_sensor)))
        self._signatures={}; self._history=deque(maxlen=max(50,evaluation_history_capacity)); self._latest=None; self._started=self._now()
        self._metrics={"evaluation_count":0,"sample_ingest_count":0,"duplicate_observation_count":0,"last_evaluated_at":None,"last_level":None,"last_score":None,"last_error":None}
    @staticmethod
    def _now(): return datetime.now(timezone.utc).isoformat()
    @staticmethod
    def _num(v):
        if v is None or isinstance(v,bool): return None
        try: x=float(v)
        except (TypeError,ValueError): return None
        return None if math.isnan(x) or math.isinf(x) else x
    @staticmethod
    def _bool(v): return v is True or str(v).lower() in {"true","1","yes","on","fresh"}
    def _publish(self, typ, payload, level):
        if self.event_bus is None: return
        try: self.event_bus.publish(event_type=typ,source="sensor-validation",payload=deepcopy(payload),level=level)
        except Exception as exc: self._metrics["last_error"]=repr(exc)
    def _read(self):
        try: data=self.sensor_discovery.sensors()
        except Exception as exc: self._metrics["last_error"]=repr(exc); return []
        return [x for x in data.get("sensors",[]) if isinstance(x,dict)] if isinstance(data,dict) else []
    def _ingest(self,sensors):
        for s in sensors:
            sid=str(s.get("sensor_id") or s.get("topic") or "unknown"); temp=self._num(s.get("temperature_c")); sig=(s.get("last_seen_at"),temp,s.get("message_count"))
            with self._lock:
                if self._signatures.get(sid)==sig: self._metrics["duplicate_observation_count"]+=1; continue
                self._signatures[sid]=sig
                self._samples[sid].append({"sensor_id":sid,"temperature_c":temp,"observed_at":s.get("last_seen_at") or self._now(),"age_seconds":self._num(s.get("age_seconds")),"fresh":self._bool(s.get("fresh")),"topic":s.get("topic"),"field":s.get("field"),"technology":s.get("technology")})
                self._metrics["sample_ingest_count"]+=1
    @staticmethod
    def _intervals(samples):
        out=[]; parsed=[]
        for s in samples:
            raw=s.get("observed_at")
            if not isinstance(raw,str): continue
            try: parsed.append(datetime.fromisoformat(raw.replace("Z","+00:00")))
            except Exception: pass
        for a,b in zip(parsed,parsed[1:]): out.append(max(0.0,(b-a).total_seconds()))
        return out
    def _validate(self,s,peers):
        sid=str(s.get("sensor_id") or "unknown"); cur=self._num(s.get("temperature_c")); fresh=self._bool(s.get("fresh")); age=self._num(s.get("age_seconds"))
        with self._lock: samples=list(self._samples.get(sid,()))
        vals=[v for x in samples if (v:=self._num(x.get("temperature_c"))) is not None]
        last=vals[-self.freeze_samples:]; frozen=len(last)>=self.freeze_samples and max(last)-min(last)<=self.freeze_eps
        jumps=[abs(b-a) for a,b in zip(vals,vals[1:])]; maxjump=max(jumps) if jumps else 0.0
        intervals=self._intervals(samples); medint=statistics.median(intervals) if intervals else None
        p=[v for k,v in peers.items() if k!=sid]; pmed=statistics.median(p) if p else None; pdelta=abs(cur-pmed) if cur is not None and pmed is not None else None
        checks=[
          ("value.available",cur is not None,20,"Mesure absente"),
          ("value.physical_range",cur is not None and self.min_c<=cur<=self.max_c,20,"Valeur hors plage"),
          ("freshness",fresh and (age is None or age<=self.stale),20,"Mesure périmée"),
          ("sample_count",len(vals)>=self.min_samples,10,"Échantillons insuffisants"),
          ("not_frozen",not frozen,10,"Sonde potentiellement figée"),
          ("jump_rate",maxjump<=self.max_jump,10,"Saut thermique anormal"),
          ("update_frequency",medint is None or medint<=self.max_interval,5,"Publication trop lente"),
          ("peer_consistency",pdelta is None or pdelta<=self.max_spread,5,"Écart excessif avec les autres sondes"),
        ]
        score=round(sum(w for _,ok,w,_ in checks if ok)/sum(w for _,_,w,_ in checks)*100)
        blockers=[{"id":i,"reason":r} for i,ok,_,r in checks if not ok and i in {"value.available","value.physical_range","freshness"}]
        warnings=[{"id":i,"reason":r} for i,ok,_,r in checks if not ok and i not in {"value.available","value.physical_range","freshness"}]
        quality="FAILED" if blockers or score<50 else "DEGRADED" if score<70 else "ACCEPTABLE" if score<85 else "GOOD"
        return {"sensor_id":sid,"technology":s.get("technology"),"topic":s.get("topic"),"field":s.get("field"),"temperature_c":cur,"fresh":fresh,"age_seconds":age,"sample_count":len(vals),"score":score,"quality":quality,"certified":quality in {"GOOD","ACCEPTABLE"} and not blockers,"statistics":{"minimum_c":min(vals) if vals else None,"maximum_c":max(vals) if vals else None,"mean_c":round(statistics.mean(vals),4) if vals else None,"maximum_jump_c":round(maxjump,4),"update_interval_median_seconds":round(medint,4) if medint is not None else None,"peer_delta_c":pdelta},"checks":[{"id":i,"passed":ok,"weight":w,"reason":r} for i,ok,w,r in checks],"blockers":blockers,"warnings":warnings}
    def evaluate(self, *, trigger="manual"):
        sensors=self._read(); self._ingest(sensors)
        peers={str(s.get("sensor_id") or "unknown"):v for s in sensors if (v:=self._num(s.get("temperature_c"))) is not None}
        results=[self._validate(s,peers) for s in sensors]; certified=[x for x in results if x["certified"]]; failed=[x for x in results if x["quality"]=="FAILED"]
        explicit=[x for x in results if str(x.get("technology")).upper()=="DS18B20"]
        score=round(statistics.mean(x["score"] for x in results)) if results else 0
        checks=[
          {"id":"sensor_count","passed":len(results)>=self.expected,"observed":len(results),"expected":self.expected,"blocking":True},
          {"id":"explicit_ds18b20_count","passed":len(explicit)>=self.expected,"observed":len(explicit),"expected":self.expected,"blocking":False},
          {"id":"certified_sensor_count","passed":len(certified)>=self.expected,"observed":len(certified),"expected":self.expected,"blocking":True},
          {"id":"average_quality_score","passed":score>=75,"observed":score,"expected":75,"blocking":True},
          {"id":"no_failed_sensor","passed":not failed,"observed":len(failed),"expected":0,"blocking":True},
        ]
        blockers=[x for x in checks if x["blocking"] and not x["passed"]]; warnings=[x for x in checks if not x["blocking"] and not x["passed"]]
        ready=not blockers
        result={"component":"sensor_validation","patch_version":self.PATCH_VERSION,"generated_at":self._now(),"trigger":trigger,"level":"SENSORS_CERTIFIED" if ready else "SENSOR_VALIDATION_INCOMPLETE","ready":ready,"ready_for_mqtt_driver":ready,"passive_only":True,"mqtt_publish_allowed":False,"physical_commands_allowed":False,"driver_change_allowed":False,"automatic_bridge_arm_allowed":False,"expected_sensor_count":self.expected,"sensor_count":len(results),"explicit_ds18b20_count":len(explicit),"certified_sensor_count":len(certified),"failed_sensor_count":len(failed),"score":score,"global_checks":checks,"blockers":blockers,"warnings":warnings,"sensors":sorted(results,key=lambda x:x["sensor_id"])}
        with self._lock:
            self._latest=deepcopy(result); self._history.append(deepcopy(result)); self._metrics.update({"evaluation_count":self._metrics["evaluation_count"]+1,"last_evaluated_at":result["generated_at"],"last_level":result["level"],"last_score":score})
        self._publish("sensor.validation" if ready else "sensor.validation.warning",result,"INFO" if ready else "WARN")
        return deepcopy(result)
    def status(self):
        with self._lock: latest=deepcopy(self._latest); metrics=deepcopy(self._metrics); counts={k:len(v) for k,v in self._samples.items()}
        return {"component":"sensor_validation","patch_version":self.PATCH_VERSION,"running":True,"started_at":self._started,"passive_only":True,"mqtt_publish_allowed":False,"physical_commands_allowed":False,"driver_change_allowed":False,"automatic_bridge_arm_allowed":False,"latest_level":latest.get("level") if latest else None,"latest_score":latest.get("score") if latest else None,"sample_counts":counts,"history_count":len(self._history),"metrics":metrics}
    def latest(self):
        with self._lock: latest=deepcopy(self._latest)
        return {"component":"sensor_validation","available":latest is not None,"evaluation":latest}
    def sensors(self):
        with self._lock: latest=deepcopy(self._latest)
        items=latest.get("sensors",[]) if latest else []
        return {"component":"sensor_validation","count":len(items),"sensors":items}
    def sensor_history(self,sensor_id,*,limit=100):
        limit=max(1,min(int(limit),240))
        with self._lock: items=list(self._samples.get(sensor_id,()))[-limit:]
        return {"component":"sensor_validation","sensor_id":sensor_id,"count":len(items),"samples":deepcopy(items)}
    def history(self,*,limit=100):
        limit=max(1,min(int(limit),500))
        with self._lock: items=list(self._history)[-limit:]
        return {"component":"sensor_validation","count":len(items),"evaluations":deepcopy(items)}
