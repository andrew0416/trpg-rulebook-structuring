"""Source-bound accuracy admission shared by status Moves and their consumers.

An explicit absent check is distinct from numeric zero or a source-dependent
AC. Damaging Moves keep the existing natural roll for critical/effect ranges.
"""
from pathlib import Path
import hashlib,json
import common_checks as C
import combat_precision_features as CPF
import effect_contracts as CONTRACTS


def policy(rules):
    row=getattr(rules,'_move_accuracy_policy',None)
    if row is None:
        row=json.loads((Path(rules.root)/'data/move-accuracy-policy.json').read_text(encoding='utf-8'))
        for file,digest in row['source_files'].items():
            if hashlib.sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=digest:raise ValueError('accuracy source changed: '+file)
        rules._move_accuracy_policy=row
    return row


def no_status_check(engine,attacker,target,move,mechanics):
    if move.get('class')!='변화' or move.get('ac') is not None:return False
    source=move.get('id');rules=policy(engine.r);entry=rules['sources'].get(source)
    if source in rules['unresolved']:return False
    if entry is None:
        # A registered structured definition can explicitly declare null AC.
        # Unclassified raw-source imports cannot silently acquire that meaning.
        canonical=engine.r.moves.get(source,{})
        if __import__('dancer').dance_instance(engine.r,source) is not None:canonical=engine.r.move(source)   # printed Dance Move template declares AC None
        if canonical.get('_source') or 'ac' not in canonical or canonical['ac'] is not None or canonical.get('class')!='변화':return False
    elif engine.r._selected_rule(source)!=source:raise ValueError('selected no-AC Move source changed')
    if CPF.blur_applies(engine,target,move,mechanics):return False
    # An explicit applicable replacement supplies a check even when the printed
    # Move has none. Unknown conditions must not be treated as false.
    ctx={'attacker':attacker,'target':target,'move':move,'engine':engine,'hit':True,'nat':None}
    for effect in mechanics.get('effects_exec',[])+attacker.registry:
        if effect.get('type')!='accuracy_override':continue
        condition=CONTRACTS.condition(engine,effect,ctx,source=effect.get('_rule_id',source))
        if condition.truth is CONTRACTS.ROOT.Truth.UNKNOWN:raise ValueError('conditional AC replacement needs an actual source observation')
        if condition.truth is CONTRACTS.ROOT.Truth.TRUE and effect.get('ac') is not None:
            C.integer(effect['ac'],'replacement AC',0);return False
    if 'on_natural_roll' in mechanics or any(any(key in effect for key in ('on_natural_roll','on_natural_roll_min')) or effect.get('type')=='multi_roll' for effect in mechanics.get('effects_exec',[])):
        raise ValueError('no-AC status Move cannot invent a natural-roll source predicate')
    return True


def preflight(engine,attacker,target,move,mechanics,*,roll_id=None,reliable_trainer=None):
    import class_passive_combat as CLASS_PASSIVE
    CLASS_PASSIVE.preflight_glacial(engine,attacker,target,move,mechanics)
    automatic=no_status_check(engine,attacker,target,move,mechanics)
    if automatic and (roll_id is not None or reliable_trainer is not None):
        raise ValueError('this Move has no accuracy roll to boost or reroll')
    return automatic
