"""Persistent event memory for freshness and repeated-news detection."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from typing import Any
STATE=Path("data/event_memory.json")
def _key(text:str)->str:return hashlib.sha1(text.strip().lower().encode()).hexdigest()
def load()->dict[str,Any]:
    if not STATE.exists():return {}
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:return {}
def remember(events:list[dict[str,Any]])->list[dict[str,Any]]:
    memory=load(); now=datetime.now(timezone.utc).isoformat(); enriched=[]
    for event in events:
        key=_key(event.get("headline","")); previous=memory.get(key)
        item=dict(event); item["event_status"]="repeat" if previous else "new"
        item["first_seen_utc"]=previous.get("first_seen_utc") if previous else now
        item["last_seen_utc"]=now
        memory[key]={"headline":item.get("headline"),"first_seen_utc":item["first_seen_utc"],"last_seen_utc":now}
        enriched.append(item)
    STATE.parent.mkdir(parents=True,exist_ok=True); STATE.write_text(json.dumps(memory,ensure_ascii=False,indent=2),encoding="utf-8")
    return enriched
