"""Selected-source held-item protection; consent belongs to the actual holder."""
class ProtectedEquipment(ValueError):pass
class EquipmentConsentRequired(ValueError):pass

def active(e,actor,source):
    name=source.split("/",1)[1]
    if actor.abilities_suppressed or name not in actor.abilities:return False
    if e.r._selected_rule(source)!=source:raise ValueError("selected equipment-protection variant needs its own policy")
    return True

def rule_id(actor,row):
    if row.get("weapon_key"):
        weapon=actor.custom_conditions.get("equipped_weapons",{}).get(row["weapon_key"],{}).get("weapon",{})
        return weapon.get("item_rule_id")
    record=getattr(actor,"_item_reg",{}).get(row.get("registration_key",row["name"]),{})
    return record.get("item_id") or actor.r.item_effects(row["name"])[1].get("id")

def status(e,actor,row,operation):
    if operation not in ("transfer","exchange","give","drop","disarm","destroy"):raise ValueError("unreviewed equipment removal operation")
    if row.get('natural_weapon'):
        import wielder_capability as WIELDER
        if WIELDER.natural_identity(actor,row) and WIELDER.active(e,actor):
            return {'status':'blocked','source':WIELDER.SOURCE,'holder_id':actor.entity_id,'equipment':row['key']}
        raise ValueError('attached anatomy is not removable item equipment')
    import mega_forms as MEGA
    if MEGA.locked(e,actor,instance_id=row.get("instance_id"),registration_key=row.get("registration_key",row.get("key"))):
        return {"status":"blocked","source":MEGA.SOURCE,"holder_id":actor.entity_id,"equipment":row["key"]}
    if row.get("held") and operation!="give" and active(e,actor,"ability/점착"):
        return {"status":"blocked","source":"ability/점착","holder_id":actor.entity_id,"equipment":row["key"]}
    if rule_id(actor,row)=="item/대파" and active(e,actor,"ability/대파의달인"):
        return {"status":"blocked" if operation=="disarm" else "needs_consent","source":"ability/대파의달인","holder_id":actor.entity_id,"equipment":row["key"]}
    import fashionista as FASHIONISTA
    style=FASHIONISTA.protection(e,actor,row,operation)
    if style is not None:return style
    return {"status":"allowed","holder_id":actor.entity_id,"equipment":row["key"]}

def require(e,actor,row,operation,consent_by=()):
    if not isinstance(consent_by,(list,tuple)) or any(type(c) is not type(actor) for c in consent_by):raise ValueError("consent must identify actual holder actors, never an exemption boolean")
    result=status(e,actor,row,operation)
    if result["status"]=="blocked":raise ProtectedEquipment(result["source"]+" prevents actual item removal")
    if result["status"]=="needs_consent" and not any(c is actor for c in consent_by):raise EquipmentConsentRequired("actual Leek holder must choose whether to allow removal")
    return result

def itemless_for_move(e,actor,move):
    import held_equipment as HELD
    held=HELD.entries(actor)
    if not held:return True
    if not isinstance(move,dict) or move.get("id")!="move/애크러뱃":return False
    if __import__('tumbler').acrobatics_itemless(actor,move):return True
    if not active(e,actor,"ability/대파의달인"):return False
    if e.r._selected_rule("move/애크러뱃")!="move/애크러뱃":raise ValueError("selected Acrobatics variant needs its own Leek policy")
    has_leek=any((x.get('item_id') or actor.r.item_effects(x['name'])[1].get('id'))=='item/대파' for x in held)
    if has_leek and len(held)>1:raise ValueError('Leek Mastery with a second held object needs an explicit source interpretation')
    return has_leek


def deferred_registration(rules,effect):
    """Only this exact reviewed rule is consumed by the live protection query."""
    if effect.get("_ability")!="점착":return False
    semantic={k:v for k,v in effect.items() if not k.startswith("_")}
    if semantic!={"type":"rule","held_item_cannot_be_removed":True}:return False
    if rules._selected_rule("ability/점착")!="ability/점착":raise ValueError("selected Sticky Hold variant needs its own contract")
    return True
