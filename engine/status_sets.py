"""Shared affliction sets and selected-source dependencies for both actor kinds.

Combatant.conditions remains authoritative. No second mutable flag registry.
Classification, prerequisite, cure dependency and save-event rules come from
selected condition definitions; resource balances never become afflictions.
"""
import common_checks as C
AFFLICTION_CLASSES=('persistent','volatile')
SAVE_EVENTS={'잠듦':'on_sleep_save'}
ALIASES={'중독':'독','맹독':'독','완전 실명':'완전-실명'}
def normalize(condition):return ALIASES.get(condition,condition)


def afflictions(actor,classification=None):
    if classification is not None and classification not in AFFLICTION_CLASSES:
        raise ValueError('ordinary affliction class required')
    return tuple(sorted(name for name in actor.conditions
        if (actor.r.condition_class(name) or __import__('custom_condition_effects').classification(actor,name)) in ((classification,) if classification else AFFLICTION_CLASSES)))


def cure_group(engine,actor,classification=None):
    for name in afflictions(actor,classification):engine.cure_status(actor,name)


def can_apply(engine,actor,condition):
    import equipment_variant_contracts as EQUIPMENT_VARIANTS
    if getattr(actor,EQUIPMENT_VARIANTS.COVERT_BLOCK,None) is not None:return False
    effects=engine.r.condition_effects(condition)
    if engine.r.condition_class(condition)=='resource':
        raise ValueError('resource balance is not an affliction; use its native producer')
    for effect in effects:
        if effect.get('type')=='requires' and 'condition' in effect:
            required=effect['condition']
            if not isinstance(required,str):raise ValueError('one named prerequisite condition required')
            if required not in actor.conditions:
                engine.log('    '+actor.name+': '+condition+' requires '+required,'condition/'+condition)
                return False
    return True


def on_cure(engine,actor,condition):
    """Cascade only explicit cure dependencies; unrelated states remain."""
    for name in tuple(sorted(actor.conditions)):
        if actor.r.condition_class(name) is None:continue
        if any(e.get('type')=='cured_by' and 'cure:'+condition in e.get('any_of',[])
               for e in engine.r.condition_effects(name)):
            engine.cure_status(actor,name)


def on_save(engine,actor,condition,roll):
    """One actual save event, regardless of success; previews call no hook."""
    C.integer(roll,'actual condition save face',1,20)
    event=SAVE_EVENTS.get(condition)
    if event is None:return
    for name in tuple(sorted(actor.conditions)):
        if name not in actor.conditions or actor.r.condition_class(name) is None:continue
        for effect in engine.r.condition_effects(name):
            if effect.get('type')=='tick_damage' and effect.get('when')==event:
                ticks=C.integer(effect.get('ticks'),'save-triggered tick loss',1)
                amount=engine.tick_loss(actor,ticks)
                engine.log('    '+actor.name+' '+name+': actual '+condition+' save; '+str(amount)+' HP loss','condition/'+name)
                engine.lose_hp(actor,amount,source='condition/'+name)


def forces_damaging_move(actor):
    return any(e.get('type')=='forced_action' and e.get('must')=='damaging_move_or_struggle'
               for name in actor.conditions if actor.r.condition_class(name) is not None for e in actor.r.condition_effects(name))


def validate(actor):
    for name in actor.conditions:
        classification=actor.r.condition_class(name)
        if classification=='resource' or name in ('임시 체력','임시-체력'):
            raise ValueError('resource balance cannot be stored as an affliction flag')
        if classification is None:continue  # preserve opaque GM observations
        for effect in actor.r.condition_effects(name):
            if effect.get('type')=='requires' and 'condition' in effect:
                required=effect['condition']
                if not isinstance(required,str) or required not in actor.conditions:
                    raise ValueError(name+' requires its actual prerequisite condition')
