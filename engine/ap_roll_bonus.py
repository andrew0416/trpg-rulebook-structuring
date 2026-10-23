"""PTK pre-roll AP spending, ch06:85. Native rolls consume designated bonuses.

A trainer uses a permitted Free action before a named ordinary skill/accuracy
roll. The named beneficiary is that trainer or a GM-designated Pokemon. Each
roll ID is unique within the Engine; preparation is never a post-result edit.
Multi-target shared accuracy and other composite rolls require a separate policy.
"""
import action_points as AP
import turn as TURN
import skill_modifiers as SKILLS

def _identity(roll_id, kind):
    if not isinstance(roll_id,str) or not roll_id.strip():
        raise ValueError('explicit upcoming roll ID required')
    if kind not in ('skill','accuracy'):
        raise ValueError('AP bonus applies only to skill or accuracy')

def prepare(engine, payer, beneficiary, *, roll_id, kind):
    _identity(roll_id,kind)
    engine.r.mech('gameplay/action-points')
    records=engine._ap_rolls
    if roll_id in records:
        raise ValueError('roll ID is already prepared or resolved')
    if payer.kind!='trainer' or (beneficiary is not payer and beneficiary.kind!='pokemon'):
        raise ValueError('trainer AP may boost self or a designated Pokemon')
    if payer.r is not engine.r or beneficiary.r is not engine.r:
        raise ValueError('AP actors must belong to this Engine rule context')
    if payer.fainted or payer.hp<=0 or payer.dead or not payer.on_field or payer.captured:
        raise ValueError('AP payer cannot perform a Free action')
    if beneficiary.fainted or beneficiary.dead:
        raise ValueError('unconscious beneficiary needs a sourced action exception')
    payer.ap_account.validate(source_required=False)
    record=SKILLS.procedural_edge(engine.r,payer,'edge/타고난-적성') if beneficiary is payer else None
    amount=record['self_ap_bonus'] if record else 1
    if AP.available(payer)<1:
        raise ValueError('insufficient available AP')
    if not TURN.spend(engine,payer,'free','굴림 전 AP 보정'):
        raise ValueError('Free action permission was not established')
    AP.spend(payer,1)
    records[roll_id]={'state':'prepared','kind':kind,'beneficiary':beneficiary,'payer':payer,'bonus':amount}
    engine.log(f'  {payer.name}: 1 AP, {beneficiary.name}의 예정 {kind} 굴림 {roll_id}에 +{amount}','gameplay/action-points')
    return amount

def bonus(engine, actor, roll_id, kind):
    if roll_id is None:return 0
    _identity(roll_id,kind)
    record=engine._ap_rolls.get(roll_id)
    if record is None:return 0
    if record['state']!='prepared':raise ValueError('roll already resolved or expired')
    if record['kind']!=kind or record['beneficiary'] is not actor:
        raise ValueError('AP bonus belongs to another actor or roll kind')
    return record['bonus']

def complete(engine, actor, roll_id, kind):
    if roll_id is None:return
    bonus(engine,actor,roll_id,kind)
    engine._ap_rolls[roll_id]={'state':'resolved','kind':kind}

def end_scene(engine):
    for record in engine._ap_rolls.values():
        if record['state']=='prepared':
            record.clear()
            record['state']='expired'
