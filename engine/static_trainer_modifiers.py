"""Exact source-owned Static modifiers for trainer classes and branch feats.

This adapter consumes existing acquisition identities.  It neither grants a
class/feature nor certifies its prerequisites.  Each contribution retains its
owner, target lifetime, exact source clause and formula so withdrawal, growth,
transactions and JSON restoration use the existing state-grant machinery.
"""
import arithmetic_policy as NUMERIC
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import acquired_features as ACQUIRED
import state_grants as GRANTS

ENDURING='class/불굴의-투지'
STAT_ACE='class/스탯-에이스'
STAT_MASTERY='feat/스탯-마스터리'
POLICY_PATH='data/static-trainer-modifier-policy.json'
STAT_FIELDS=('atk','def','spa','spd','spe')


def _policy(rules):
    cached=getattr(rules,'_static_trainer_modifier_policy',None)
    if cached is not None:return cached
    path=Path(rules.root)/POLICY_PATH
    # Overlay verification deliberately keeps the large rule corpus at the
    # canonical root while importing candidate code and new policy files from
    # the integration stage.  Until the candidate is published, its policy is
    # therefore adjacent to this module rather than present below rules.root.
    # Normal canonical execution still takes the rules-root path first.
    if not path.is_file():
        staged=Path(__file__).resolve().parent.parent/POLICY_PATH
        if staged.is_file():path=staged
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version')!=1:raise ValueError('unsupported Static trainer modifier policy')
    for relative,digest in data.get('source_files',{}).items():
        actual=hashlib.sha256((Path(rules.root)/relative).read_bytes()).hexdigest()
        if actual!=digest:raise ValueError('Static trainer modifier source changed: '+relative)
    clauses=data.get('clauses')
    if not isinstance(clauses,dict) or any(not isinstance(row,dict) for row in clauses.values()):
        raise ValueError('Static trainer modifier clauses must be exact records')
    rules._static_trainer_modifier_policy=data
    return data


def _clause(rules,clause_id):
    if clause_id in ('C04-047','input/ch04-trainer-classes.md:1131-1140'):
        import trainer_feature_acquisition as T
        T._static_source(rules,STAT_ACE if clause_id=='C04-047' else STAT_MASTERY)
        return {'id':clause_id}
    try:row=_policy(rules)['clauses'][clause_id]
    except KeyError:raise ValueError('unreviewed Static trainer modifier clause: '+str(clause_id))
    if row.get('id')!=clause_id:
        raise ValueError('Static trainer modifier source changed: '+clause_id)
    return row


def _targets(engine,trainer,candidates=None):
    import world_entities as WORLD
    actual=WORLD.actor_index(engine)
    values=list(actual.values()) if candidates is None else list(candidates)
    result=[]
    for target in values:
        if actual.get(getattr(target,'entity_id',None)) is not target:
            raise ValueError('Static trainer modifier requires actual registered targets')
        if target.kind=='pokemon' and target.spec.get('trainer_id')==trainer.entity_id:
            result.append(target)
    return tuple({target.entity_id:target for target in result}.values())


def _stat_key(trainer,rule_id,branch):
    return 'static-modifier:'+trainer.entity_id+':'+rule_id+':'+branch


def _install_stat(engine,trainer,target,*,rule_id,branch,field,clause_id):
    if engine.r._selected_rule(rule_id)!=rule_id:raise ValueError('selected Static class source changed')
    clause=_clause(engine.r,clause_id)
    key=_stat_key(trainer,rule_id,branch)
    declaration={'contract':'level_scaled_base_stat','clause_id':clause_id,'field':field,
                 'formula':'1 + floor(level / 10)','branch':branch}
    row=GRANTS._source(target,key,'static_trainer_modifier',owner_id=trainer.entity_id,
        lifetime='your_pokemon',rule_id=rule_id,tutor_points=0,clause_id=clause_id,
        declaration=declaration)
    existing=row['grants'].get('static_modifiers')
    if existing is not None and existing!=[declaration]:raise ValueError('Static modifier declaration collision')
    row['grants']['static_modifiers']=[deepcopy(declaration)]
    GRANTS.reconcile_stat(target,field,1+NUMERIC.ratio(target.level,10),key,operation_id='level_formula')
    return key


def _install_special_range(engine,trainer,target,clause_id):
    if engine.r._selected_rule(STAT_MASTERY)!=STAT_MASTERY:raise ValueError('selected Stat Mastery source changed')
    clause=_clause(engine.r,clause_id)
    key='static-modifier:'+trainer.entity_id+':'+STAT_MASTERY+':spa'
    declaration={'contract':'move_range','clause_id':clause_id,'move_class':'특수',
                 'non_melee':True,'origin_delta':2,'area_size_delta':0}
    row=GRANTS._source(target,key,'static_trainer_modifier',owner_id=trainer.entity_id,
        lifetime='your_pokemon',rule_id=STAT_MASTERY,tutor_points=0,clause_id=clause_id,
        declaration=declaration)
    existing=row['grants'].get('static_modifiers')
    if existing is not None and existing!=[declaration]:raise ValueError('Static modifier declaration collision')
    row['grants']['static_modifiers']=[deepcopy(declaration)]
    part=key+':move-range'
    parts=row.setdefault('effect_sources',[])
    effect={'type':'move_range_mod','value':2,'move_class':'특수','non_melee':True,
            'area_size_delta':0,'_clause_id':clause_id}
    if part not in parts:
        GRANTS.apply_owned(engine,target,part,lambda:target.modifiers.append(effect),effects=(effect,))
        parts.append(part)
    return key


def register_all(engine,trainer,pokemon=None):
    """Materialize exact owned contributions on the trainer's current Pokemon."""
    if trainer.kind!='trainer':return 0
    ACQUIRED.validate_class_slots(trainer)
    instances=ACQUIRED.class_instances(trainer)
    targets=_targets(engine,trainer,pokemon)
    count=0
    if any(row['source_id']==ENDURING for row in instances) and __import__('breather').class_edition(trainer)=='local_csv':
        for target in targets:
            _install_stat(engine,trainer,target,rule_id=ENDURING,branch='hp',field='hp',
                          clause_id='C2CSV/input/db/feats.csv:R125:main');count+=1
    branches={row['branch'] for row in instances if row['source_id']==STAT_ACE}
    import stat_ace as STAT
    mapping=_policy(engine.r)['stat_ace_branches']
    for branch in sorted(branches):
        if branch not in STAT_FIELDS or branch not in mapping:raise ValueError('unreviewed Stat Ace branch')
        clause_id=mapping[branch]
        if STAT.acquired(trainer,STAT_ACE,branch):clause_id='C04-047'
        for target in targets:
            _install_stat(engine,trainer,target,rule_id=STAT_ACE,branch=branch,field=branch,
                          clause_id=clause_id);count+=1
    mastery=[row for row in ACQUIRED.feature_instances(trainer) if row['source_id']==STAT_MASTERY]
    if any(row['branch']=='spa' for row in mastery):
        for target in targets:
            clause='input/ch04-trainer-classes.md:1131-1140' if STAT.acquired(trainer,STAT_MASTERY,'spa') else 'C2CSV/input/db/feats.csv:R194:main'
            _install_special_range(engine,trainer,target,clause);count+=1
    return count


def refresh_level(actor):
    """Reconcile only formulas already owned by this target after level changes."""
    rows=actor.spec.get(GRANTS.KEY,{}).get('sources',{})
    for key,row in list(rows.items()):
        declaration=row.get('declaration')
        if row.get('kind')!='static_trainer_modifier' or not isinstance(declaration,dict):continue
        if declaration.get('contract')!='level_scaled_base_stat':continue
        field=declaration.get('field')
        _clause(actor.r,declaration.get('clause_id'))
        GRANTS.reconcile_stat(actor,field,1+NUMERIC.ratio(actor.level,10),key,operation_id='level_formula')


def range_spec(actor,move,spec):
    """Project owned move-range contributions without changing area dimensions."""
    result=deepcopy(spec)
    state=actor.spec.get(GRANTS.KEY,{})
    for effect in actor.modifiers:
        if not isinstance(effect,dict) or effect.get('type')!='move_range_mod':continue
        source=effect.get(GRANTS.TAG)
        expected={'type':'move_range_mod','value':2,'move_class':'특수','non_melee':True,
                  'area_size_delta':0,'_clause_id':effect.get('_clause_id'),
                  GRANTS.TAG:source}
        if effect!=expected or source not in state.get('effects',{}):continue
        if effect.get('_clause_id') not in ('C2CSV/input/db/feats.csv:R194:main','input/ch04-trainer-classes.md:1131-1140'):continue
        parent=source.removesuffix(':move-range') if isinstance(source,str) else None
        owner=state.get('sources',{}).get(parent,{})
        if source not in owner.get('effect_sources',[]) or owner.get('declaration',{}).get('contract')!='move_range':continue
        if effect.get('move_class') is not None and move.get('class')!=effect['move_class']:continue
        if effect.get('non_melee') and result.get('origin')=='melee':continue
        value=effect.get('value')
        if type(value) is not int or type(result.get('origin')) is not int:
            continue
        result['origin']+=value
        result['static_origin_bonus']=result.get('static_origin_bonus',0)+value
        # Deliberately retain result['size']; R194 extends placement/origin only.
    return result


def validate(actor):
    """Reject forged declarations, stale formulas and untracked visibility."""
    state=actor.spec.get(GRANTS.KEY,{})
    sources=state.get('sources',{})
    for key,row in sources.items():
        if row.get('kind')!='static_trainer_modifier':continue
        declaration=row.get('declaration')
        if not isinstance(declaration,dict) or row.get('grants',{}).get('static_modifiers')!=[declaration]:
            raise ValueError('Static trainer modifier declaration provenance changed')
        clause=_clause(actor.r,declaration.get('clause_id'))
        if row.get('clause_id')!=clause['id'] or row.get('lifetime')!='your_pokemon' or not row.get('owner_id'):
            raise ValueError('Static trainer modifier owner/lifetime changed')
        if actor.kind!='pokemon' or actor.spec.get('trainer_id')!=row['owner_id']:
            raise ValueError('Static trainer modifier target ownership changed without withdrawal')
        if declaration.get('contract')=='level_scaled_base_stat':
            field=declaration.get('field');operations=state.get('stat_sources',{}).get(field,{}).get('sources',{}).get(key,{})
            expected={'delta':1+NUMERIC.ratio(actor.level,10),'minimum':None}
            if operations.get('level_formula')!=expected:raise ValueError('Static level formula is stale or forged')
        elif declaration.get('contract')=='move_range':
            if declaration!={'contract':'move_range','clause_id':clause['id'],'move_class':'특수','non_melee':True,'origin_delta':2,'area_size_delta':0}:
                raise ValueError('Static move range declaration changed')
            part=key+':move-range'
            expected={'type':'move_range_mod','value':2,'move_class':'특수','non_melee':True,
                      'area_size_delta':0,'_clause_id':clause['id'],GRANTS.TAG:part}
            if row.get('effect_sources')!=[part] or state.get('effects',{}).get(part)!={'rows':['modifiers'],'listeners':[]}:
                raise ValueError('Static move range source receipt changed')
            if sum(effect==expected for effect in actor.modifiers)!=1:
                raise ValueError('Static move range visibility changed')
        else:raise ValueError('unknown Static trainer modifier contract')
    return True
