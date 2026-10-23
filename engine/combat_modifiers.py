"""Ordinary bounded combat modifiers, distinct from scoped roll effects.

Shared by passive registration and source ownership. A qualifier cannot silently
become an unconditional self bonus merely because it shares an effect name.
"""
import common_checks as C
FIELDS={'accuracy_mod':'accuracy_stage','evasion_mod':'evasion_mod'}


def passive_field(effect):
    if not isinstance(effect,dict) or effect.get('type') not in FIELDS:
        return None
    if type(effect.get('value')) is not int or effect.get('target','self')!='self':
        return None
    if any(k not in ('type','value','target') and not k.startswith('_') for k in effect):
        return None
    return FIELDS[effect['type']]


def effect_range_supported(effect):
    """Only exact numeric, optionally typed, self contributions are executable."""
    if not isinstance(effect, dict) or effect.get('type') != 'effect_range_mod':
        return False
    if type(effect.get('value')) is not int or effect.get('target', 'self') != 'self':
        return False
    if any(key not in ('type', 'value', 'target', 'of_type') and not key.startswith('_') for key in effect):
        return False
    if 'of_type' in effect and (not isinstance(effect['of_type'], str) or not effect['of_type'].strip()):
        return False
    return True


def effect_range_bonus(actor, move):
    """Unsupported scopes remain inert, including contributions from old saves."""
    if not move:
        return 0
    return sum(effect['value'] for effect in actor.modifiers
               if effect_range_supported(effect)
               and ('of_type' not in effect or effect['of_type'] == move.get('type')))


def extra_evasion(*contributions):
    """C07-065 bounds the aggregate extra modifier, before stat evasion."""
    for value in contributions:C.integer(value,'extra evasion contribution')
    return max(-6,min(6,sum(contributions)))


def accuracy_stage(actor):
    """Ordinary and timed stage contributions share C07-062's bounded total."""
    import effect_lifetimes as LIFETIMES
    C.integer(actor.accuracy_stage,'accuracy stage',-6,6)
    timed=LIFETIMES.numeric(actor,'accuracy_modifier')
    C.integer(timed,'timed accuracy stage')
    return max(-6,min(6,actor.accuracy_stage+timed))


def incoming_derivation(target,field,*,status=None):
    import combat_timing as T,composition_derive as COMPOSITION
    rows=[r for r in T.records(target) if field in r and (status is None or r[field]['status']==status)]
    contributions=[];steps=[];seen=set()
    for row in rows:
        identity=row['effect_occurrence'];source=row['source'];plan=row.get('roughneck_stacking')
        if source in seen and plan is None:raise COMPOSITION.CompositionPending('overlapping identical source needs its explicit GM ruling')
        value=row[field] if status is None else row[field]['bonus']
        contributions.append({'id':identity,'source':source,'value':value})
        steps.append({'law':plan['operator'] if plan else 'add','contributors':[identity]});seen.add(source)
    return COMPOSITION.derive(0,contributions,steps,rounding='exact')


def incoming_critical_bonus(target):
    return incoming_derivation(target,'incoming_critical_bonus')['value']


def incoming_status_threshold(target,status,threshold):
    return threshold-incoming_derivation(target,'incoming_status_range',status=status)['value'] if status else threshold


def incoming_status_hit(e,attacker,target,move,mm,natural):
    """Supply one status range when the actual attack has no intrinsic range."""
    import combat_timing as T,combat_precision_features as CPF
    if natural is None:return
    statuses={r['incoming_status_range']['status']:r['source'] for r in T.records(target) if 'incoming_status_range' in r}
    for status,source in statuses.items():
        if mm.get('apply_status')==status or mm.get('on_natural_roll',{}).get('apply_status')==status:continue
        if any(effect.get('type')=='apply_status' and effect.get('status')==status for effect in mm.get('effects_exec',[])):continue
        value=incoming_derivation(target,'incoming_status_range',status=status)['value']
        if CPF.effect_natural(e,attacker,move,natural)>=21-value:
            e.apply_status(target,status,source=source,applied_by=attacker)
