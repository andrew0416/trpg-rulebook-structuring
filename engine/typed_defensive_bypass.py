"""Exact CSV Turboblaze/Teravolt sources, without merging duplicate row identities."""
from pathlib import Path
from copy import deepcopy
import json
from hashlib import sha256

_POLICY=json.loads((Path(__file__).resolve().parents[1]/'data/typed-defensive-bypass-policy.json').read_text(encoding='utf-8'))


def handles(source):return isinstance(source,str) and source in _POLICY['sources']


def definition(rules,source):
    row=_POLICY['sources'].get(source)
    if row is None:return None
    from source_context import verified_source
    verified_source(rules,_POLICY['source'],label='typed defensive bypass exact CSV source')
    if sha256((Path(rules.root)/'output/entities/abilities.json').read_bytes()).hexdigest()!=_POLICY['catalog_sha256']:
        raise ValueError('typed defensive bypass ability catalog changed')
    if rules._selected_rule(source)!=source:raise ValueError('exact selected typed defensive bypass source required')
    unit=rules.selection.units[source]
    if (unit['title']!=row['definition']['name'] or unit['source'].get('file')!='db/abilities.csv'
            or unit['source'].get('record_span')!=[row['record'],row['record']]
            or rules.ability_effects.get(unit['title'])!=row['effects']):
        raise ValueError('typed defensive bypass source or effect declaration changed')
    return row


def registration(rules,name):
    if not handles(name):return None
    row=definition(rules,name)
    # The public stored identity stays this exact CSV row. Its duplicate display
    # label remains ambiguous; no unreviewed alias or equivalence is introduced.
    return {'name':name,'source_id':name,'display_name':row['definition']['name']}


def effects(rules,source):
    row=definition(rules,source)
    if row is None:raise ValueError('known exact typed defensive bypass source required')
    return deepcopy(row['effects'])


def active_sources(engine,actor,target,move,*,actual_type=None):
    if actor is None or target is None or move is None or actor.abilities_suppressed:return ()
    actor_side,target_side=getattr(actor,'side',None),getattr(target,'side',None)
    if not actor_side or not target_side or actor_side==target_side:return ()
    import ability_transitions as ABILITIES
    selected=[]
    for effect in actor.registry:
        source=effect.get('_rule_id')
        if not handles(source):continue
        row=definition(engine.r,source)
        if {k:v for k,v in effect.items() if not k.startswith('_')} not in row['effects']:
            raise ValueError('typed defensive bypass live effect changed')
        if not ABILITIES.active(actor,source):continue
        if actual_type is None:
            import effects_ext as EXT
            actual_type=EXT.effective_type(engine,actor,target,move,engine.r.move_mech(move['id'])[0],consume=False)
        if actual_type==row['move_type']:selected.append(source)
    return tuple(selected)


def effectiveness(engine,actor,target,move,value,*,actual_type):
    if 0<value<1 and active_sources(engine,actor,target,move,actual_type=actual_type):return 1.0
    return value
