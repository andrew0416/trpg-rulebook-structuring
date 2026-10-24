"""Exact source-owned consumers for four reviewed static equipment rows."""
from copy import deepcopy
import hashlib
import json
import os

POLICY_FILE = "static-equipment-contract-policy.json"
KINDS = {"clear_amulet", "ability_shield", "heavy_duty_boots", "terrain_extender"}
ITEM_KINDS={"item/클리어참":"clear_amulet","item/특성가드":"ability_shield","item/통굽부츠":"heavy_duty_boots","item/그라운드코트":"terrain_extender"}

def _path(rules):
    canonical = os.path.join(rules.root, "data", POLICY_FILE)
    staged = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", POLICY_FILE))
    return canonical if os.path.exists(canonical) else staged

def policy(rules):
    with open(_path(rules), encoding="utf-8") as handle:value = json.load(handle)
    rows = value.get("rows")
    if value.get("schema_version") != 1 or value.get("contract") != "source-owned static equipment projection":
        raise ValueError("static equipment policy schema changed")
    if not isinstance(rows, dict) or len(rows) != 4:
        raise ValueError("static equipment policy must contain the exact four reviewed equipment rows")
    source = os.path.join(rules.root, "input", "db", "inventory.csv")
    with open(source, "rb") as handle:source_sha = hashlib.sha256(handle.read()).hexdigest()
    if source_sha != value.get("source_file_sha256"):raise ValueError("static equipment inventory source changed")
    with open(os.path.join(rules.root,"data","verification","category2-item-table-status.json"),encoding="utf-8") as handle:
        status=json.load(handle)
    source_rows={row["clause_id"]:row for row in status.get("new_clauses",())};seen=set()
    for item_id,row in rows.items():
        if item_id!=row.get("item_id") or row.get("kind") not in KINDS:raise ValueError("static equipment identity or kind changed")
        clause=row.get("clause_id")
        if not isinstance(clause,str) or clause in seen:raise ValueError("static equipment clause identity changed")
        seen.add(clause);registered=source_rows.get(clause)
        if registered is None or len(registered.get("source",()))!=1:raise ValueError("static equipment source row is missing")
        src=registered["source"][0]
        expected=(row.get("source_file"),row.get("source_row"),row.get("source_columns"),row.get("source_row_sha256"))
        actual=(src.get("file"),src.get("row"),src.get("columns"),src.get("raw_cells_sha256"))
        if expected!=actual:raise ValueError("static equipment source provenance changed: "+clause)
        header=rules.item_effects(item_id)[1]
        if header.get("id")!=item_id or rules._selected_rule(item_id)!=item_id:raise ValueError("static equipment selected item changed: "+item_id)
    return value

def definition(rules,item_id):return deepcopy(policy(rules)["rows"].get(item_id))

def prepare_register(engine,actor,item_id,source_instance_id=None):
    if item_id not in ITEM_KINDS:return None
    row=definition(engine.r,item_id)
    if row is not None and row.get("wearer_kind") and actor.kind!=row["wearer_kind"]:
        raise ValueError(row["name"]+" requires a "+row["wearer_kind"]+" wearer")
    return row

def consumes_effect(plan,effect):
    return bool(plan and plan["kind"]=="clear_amulet" and isinstance(effect,dict) and effect.get("type")=="immune_stage_loss")

def install(engine,actor,source_id,plan):return [],0

def _active(engine,actor,kind):
    registrations=getattr(actor,"_item_reg",{})
    if not any(ITEM_KINDS.get(record.get("item_id"))==kind for record in registrations.values()):return []
    rows=policy(engine.r)["rows"];sources=actor.spec.get("state_grants",{}).get("sources",{});found=[]
    for record in registrations.values():
        row=rows.get(record.get("item_id"))
        if row is None or row["kind"]!=kind or record.get("state_source") not in sources:continue
        uid=record.get("instance_id")
        if uid is not None:
            obj=getattr(engine,"_physical_objects",{}).get(uid)
            if not isinstance(obj,dict) or obj.get("item_rule_id")!=row["item_id"] or obj.get("equipped_by")!=actor.entity_id:
                raise ValueError("static equipment registration and physical instance disagree")
        found.append((row,record))
    return found

def blocks_stage_loss(engine,target,source_actor,context,*,origin_source_id=None,source_side=None):
    rows=_active(engine,target,"clear_amulet")
    if not rows:return False
    if source_side is None:
        if source_actor is target:return False
        source_side=getattr(source_actor,"side",None)
    if source_side is None or getattr(target,"side",None) is None or source_side==target.side:return False
    source=origin_source_id if origin_source_id is not None else str((context or {}).get("source_id") or "")
    return any(source.startswith(prefix) for prefix in rows[0][0]["blocked_source_prefixes"])

def blocks_ability_change(engine,target,source_actor):
    return source_actor is not target and bool(_active(engine,target,"ability_shield"))

def ignores_entry_hazard(engine,actor):return bool(_active(engine,actor,"heavy_duty_boots"))

def terrain_duration_source(engine,actor,base_rounds):
    rows=_active(engine,actor,"terrain_extender")
    if not rows:return base_rounds,None
    row,registration=rows[0]
    return base_rounds+row["round_bonus"],{"clause_id":row["clause_id"],"item_id":row["item_id"],"instance_id":registration.get("instance_id"),"base_rounds":base_rounds,"bonus_rounds":row["round_bonus"]}

def validate_terrain_duration(engine,receipt,base_rounds):
    required={"clause_id","item_id","instance_id","base_rounds","bonus_rounds"}
    if not isinstance(receipt,dict) or set(receipt)!=required:raise ValueError("terrain extender duration receipt changed")
    row=policy(engine.r)["rows"].get(receipt["item_id"])
    if row is None or row["kind"]!="terrain_extender" or receipt["clause_id"]!=row["clause_id"]:raise ValueError("terrain extender source changed")
    if receipt["base_rounds"]!=base_rounds or receipt["bonus_rounds"]!=row["round_bonus"]:raise ValueError("terrain extender duration arithmetic changed")
    uid=receipt["instance_id"]
    if uid is not None:
        obj=getattr(engine,"_physical_objects",{}).get(uid)
        if not isinstance(obj,dict) or obj.get("item_rule_id")!=row["item_id"]:raise ValueError("terrain extender physical provenance changed")
    return base_rounds+row["round_bonus"]
