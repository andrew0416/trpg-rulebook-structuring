"""Source-bound incoming damage responses. Mettle: PTU 1.05 p171.
Damage calculation is completed once; a response changes its resistance step, not its dice.
Interception eligibility/movement is the caller's separately resolved maneuver.
"""
import arithmetic as A
import frequency as FREQ
import effects as FX
import effects_ext as EXT
import turn as TURN
METTLE = "feat/깡다구"

def resistance_multiplier(engine, multiplier):
    steps={1.0:0,1.5:1,2.0:2,3.0:3,0.5:-1,0.25:-2,0.125:-3}
    if multiplier==0:return 0
    if multiplier not in steps:return None
    return engine.r.mech("combat/type-effectiveness")["multiplier_by_net_steps"][str(max(-3,steps[multiplier]-1))]

def select_mettle(engine, event):
    """Return selected damage; only an explicit positive decision authorizes use."""
    damage=event["damage"]
    c=event["target"]
    if c.fainted:return damage
    header=None
    for name in c.spec.get("feats",[]):
        _,candidate=engine.r.feat_effects(name)
        if candidate.get("id")==METTLE:
            header=candidate
            break
    if header is None:return damage
    frequency=header.get("frequency")
    if not FREQ.activation_allowed(c,METTLE,frequency,engine=engine):return damage
    potential=min(damage,max(0,c.hp-1)) if event.get("damage_floor") else damage
    # Match injury processing: the actual maximum is unchanged by injury healing caps.
    massive=max(0,EXT.cap_damage(engine,c,potential)-c.temp_hp)>=A.multiply(engine.formula("massive_damage"),c.base_max_hp)
    if not (massive or event.get("intercepted") is True):return damage
    if event.get("resisted_damage") is None or event.get("attack_stat") not in event["attacker"].stages:
        engine.log("    [보류] 깡다구: 피해 배수 또는 공격 스탯 문맥 미해석",METTLE)
        return damage
    answer=engine.rulings.decide(dict(type="mettle",unit=METTLE,text="이 공격에 깡다구를 사용합니까?",actor=c.name,attacker=event["attacker"].name,move=event["move"]["id"],damage=damage,resisted_damage=event["resisted_damage"],massive=massive,intercepted=event.get("intercepted",False)))
    if answer is not True:
        engine.log("    깡다구: 사용 미선택 → 원래 피해 적용",METTLE)
        return damage
    __import__("action_lifecycle").triggered_free_action(engine,c,METTLE)
    event["mettle_frequency"]=frequency
    event["mettle_selected"]=True
    engine.log(f"    깡다구: 해당 공격 저항 1단계 → 피해 {damage} → {event['resisted_damage']}",METTLE)
    return event["resisted_damage"]

def finish_mettle(engine,event):
    """The triggering foe's stat changes after this damage has been applied, once."""
    if not event.get("damage_applied") or not event.get("mettle_selected") or event.get("mettle_finished"):return
    event["mettle_finished"]=True
    c=event["target"];foe=event["attacker"]
    FREQ.consume_activation(c,METTLE,event["mettle_frequency"],engine=engine)
    FX.h_stage_change(engine,c,foe,dict(type="stage_change",stat=event["attack_stat"],delta=-2,target="target"),dict(engine=engine,source_id=METTLE,attacker=c,target=foe,hit=True))
