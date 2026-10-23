"""Source-specific adapters; the transport itself does not infer semantics from Static."""
from pathlib import Path
import hashlib,json
RULE = "ability/자기과신"
NAME = "자기과신"
def source_profile(e):
    root=Path(e.r.root)
    p=json.loads((root/"data/verification/passive-event-runtime-profile.json").read_text(encoding="utf8"))
    a=p["source_anchor"];source=root/a["file"]
    if hashlib.sha256(source.read_bytes()).hexdigest()!=a["file_sha256"]:
        raise ValueError("passive source changed")
    ex="\n".join(source.read_text(encoding="utf-8-sig").splitlines()[a["start"]-1:a["end"]])
    if ex!=a["excerpt"] or hashlib.sha256(ex.encode()).hexdigest()!=a["excerpt_sha256"]:
        raise ValueError("passive source excerpt mismatch")
    return p


def register_profile(e,selected_id):
    if selected_id!=RULE:return None
    source_profile(e)
    return {"rule_id":RULE,"kind":"static_consequence","profile":"direct_single_attack_ko"}

def eligibility(e,ev,rule_id):
    a,t=ev["actor"],ev["target"]
    if rule_id!=RULE:return "pending","source_adapter_not_implemented"
    if NAME not in a.abilities:return "pending","source_listener_no_longer_owned"
    if ev["owner_before"] != ev["owner_after"]:
        return "pending","owner_state_changed_during_move_order_unresolved"
    if type(ev["hit"]) is not bool:return "pending","hit_evidence_unknown"
    if a.fainted or a.dead or a.abilities_suppressed:
        return "inapplicable","owner_cannot_use_new_ability"
    if not ev["hit"] or not ev["target_after"]["fainted"]:
        return "inapplicable","no_observed_move_knockout"
    if ev["target_before"]["fainted"]:return "inapplicable","target_already_fainted"
    if ev["effect_held_count"]:return "pending","move_effect_prefix_unresolved"
    if not ev["mechanics_scope_supported"]:
        return "pending","move_mechanics_outside_direct_native_profile"
    packet=ev["attack_observation"]
    if not ev["ordinary_single"]:return "pending","multi_target_or_nonordinary_activation_scope_unproved"
    if not packet or packet["before"]["fainted"] or not packet["after"]["fainted"]:
        return "pending","direct_attack_knockout_causality_unproved"
    if packet["after"]!=ev["target_after"]:
        return "pending","later_move_effects_changed_knockout_state"
    if a is t:return "pending","self_not_enemy"
    sa,st=getattr(a,"side",None),getattr(t,"side",None)
    if not sa or not st:return "pending","enemy_relation_unknown"
    if sa==st:return "inapplicable","target_is_ally"
    if a.registry or a.modifiers or a.ability_triggers or t.ability_triggers:
        return "pending","interacting_effect_order_unproved"
    source_profile(e)
    return "eligible","source_direct_attack_ko"

def apply(e,ev,rule_id):
    if rule_id!=RULE:raise ValueError("unsupported consequence adapter")
    a=ev["actor"];before=a.stages["atk"]
    e.change_stage(a,"atk",1)
    return dict(type="stage_change",stat="atk",delta=1,before=before,after=a.stages["atk"])
