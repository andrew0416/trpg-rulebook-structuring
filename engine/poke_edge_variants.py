"""Reviewed CSV specializations of existing investment consumers.

Only identity and fixed choices live here. Costs, eligibility, duplicate checks,
state changes and refunds remain in the shared native policy. Source identity
survives on the same investment receipt, not in a parallel state registry.
"""
import json,hashlib
from pathlib import Path
from copy import deepcopy
from source_context import verified_source
import skill_modifiers as S


def catalog(rules):
    root=Path(rules.root).resolve()
    raw=root.joinpath('data/poke-edge-variants.json').read_bytes()
    identity=(str(root),hashlib.sha256(raw).hexdigest())
    cached=getattr(rules,'_poke_edge_variants',None)
    if cached is not None and getattr(rules,'_poke_edge_variants_identity',None)!=identity:
        raise ValueError('Poke Edge definition or root changed; review required')
    data=json.loads(raw.decode('utf-8'))
    if data.get('schema')!='poke-edge-variants-v1':raise ValueError('unknown edge variant schema')
    verified_source(rules,{'file':data['source_file'],'sha256':data['source_sha256']},label='Poke Edge')
    if cached is None:
        cached=data['entries'];rules._poke_edge_variants=deepcopy(cached)
        rules._poke_edge_variants_identity=identity
    return deepcopy(cached)


def selected(rules,row):
    uid=row['rule_id']
    if rules._selected_rule(uid)!=uid:raise ValueError('selected CSV edge requires its own policy')
    source=rules.selection.units[uid]['source']
    if source.get('file')!='db/poke-edges.csv' or source.get('record_span')!=[row['record'],row['record']]:
        raise ValueError('CSV edge definition identity collision')


def resolve(rules,edge):
    rows=[x for x in catalog(rules) if edge in (x['clause_id'],x['rule_id'],x['name'])]
    if len(rows)>1:raise ValueError('ambiguous Poke Edge identity')
    if not rows:return None
    selected(rules,rows[0]);return rows[0]


def choice_value(rules,row,value):
    if row['field']=='ability':
        import ability_mastery as ABILITY_MASTERY
        return ABILITY_MASTERY.choice(rules,value)
    if row['field']=='lesson':
        import underdog_lessons as LESSONS
        return LESSONS.choice(rules,value)
    if row['field']=='growth':
        import underdog_edges as U
        return U.growth_choice(value)
    if row['field']=='none':
        if value is not None:raise ValueError('this CSV Edge has no acquisition choice')
        return None
    if row['policy']=='poke_edge/기본-원거리-공격':
        import ranged_struggle as RANGED
        return RANGED.choice(value)
    if row['field']=='skill':return S.skill_id(rules.skill_policy,value,required=True)
    if row['field']=='stat':
        import pokemon_stat_edges as STAT
        if not isinstance(value,str) or value not in STAT.CHOICES:raise ValueError('choose Attack or Special Attack explicitly')
        return STAT.CHOICES[value]
    if row['field']=='move_id':
        result=rules.move_id(value) if isinstance(value,str) else None
        if result is None:raise ValueError('choose an actual Move')
        return result
    import pokemon_capability_edges as CAP
    result=CAP.CHOICES.get(value,value) if isinstance(value,str) else None
    if result not in CAP.RULES[row['policy']]['choices']:raise ValueError('eligible capability choice required')
    return result


TRAINING_SOURCES=('input/ch05-pokemon.md:274','input/ch05-pokemon.md:229','edge/미용사')


def validate_history(receipt,*,minimum_level=None,rules=None):
    """Acquisition history written by every native Poke Edge teaching producer.

    input/ch05-pokemon.md:274: a Pokemon spends Tutor Points on an Edge only after an
    hour of training (or a completed training-session/Groomer hour). Mentor's printed
    prerequisite waiver and the Connection keyword's immediate acquisition retain their
    exact native producer validators instead of pretending to be ordinary hours. Active and refunded
    receipts therefore keep the actual teacher, completion time and training source; the
    current Tutor Point balance never proves a past payment. Producers that record the
    acquisition level pass their level prerequisite as minimum_level.
    """
    import state_fields as F
    training_source=receipt.get('training_source')
    lesson=training_source=='feat/수업'
    connection=training_source=='keyword/연결'
    # Immediate Connection is an Ability-gain opportunity, not a training hour.
    if not connection or receipt.get('trainer_id') is not None:
        if type(receipt.get('trainer_id')) is not str or not receipt['trainer_id'].strip():raise ValueError('actual historical Poke Edge trainer required')
    F.integer(receipt.get('completed_at'),'completed Poke Edge training time',0)
    if lesson:
        if rules is None:raise ValueError('actual Mentor source rules required')
        if receipt.get('source') not in ('poke_edge/스킬-향상','poke_edge/고급-이동','poke_edge/재능-훈련'):
            raise ValueError('Mentor lesson permits only its three printed Poke Edges')
        import mentor as MENTOR
        MENTOR.validate_edge_origin(rules,receipt)
    elif connection:
        if rules is None:raise ValueError('actual Connection source rules required')
        import advanced_connection as CONNECTION
        CONNECTION.validate_immediate_receipt(rules,receipt)
    elif training_source not in TRAINING_SOURCES:
        import researcher_fields as RFS
        if training_source!=RFS.PUSHER or receipt.get('pusher',{}).get('acquisition')!='automatic':raise ValueError('actual completed Poke Edge training source required')
        RFS.pusher_receipt(rules=None,receipt=receipt)
    if minimum_level is not None:F.integer(receipt.get('acquired_level'),'historical Poke Edge acquisition level',1 if lesson else minimum_level,100)


def validate_receipt(rules,receipt,*,history=False,minimum_level=None):
    if 'pusher' in receipt:
        import researcher_fields as RFS
        RFS.pusher_receipt(rules,receipt)
    if history:validate_history(receipt,minimum_level=minimum_level,rules=rules)
    origin=receipt.get('definition_origin')
    if origin is None:return  # Earlier native receipts keep their native identity; history is checked above.
    if not isinstance(origin,dict):raise ValueError('typed definition origin required')
    rows=[r for r in catalog(rules) if r['clause_id']==origin.get('clause_id')]
    if len(rows)!=1:raise ValueError('unknown acquired CSV definition')
    row=rows[0];selected(rules,row)
    expected={'clause_id':row['clause_id'],'rule_id':row['rule_id'],'record':row['record']}
    if origin!=expected or receipt.get('source')!=row['policy']:raise ValueError('CSV source receipt mismatch')
    value=receipt.get('choice' if row['field']=='capability' else row['field'])
    actual=choice_value(rules,row,value)
    if row['choice'] is not None and actual!=choice_value(rules,row,row['choice']):
        raise ValueError('CSV fixed choice changed in receipt')


def teach(engine,owner,target,row,*,skill=None,capability=None,stat=None,move_id=None,growth=None,lesson=None,ability=None,negative_decision=None,from_grooming=False,from_training=False,safe=None):
    import state_grants as G
    options={'skill':skill,'capability':capability,'stat':stat,'move_id':move_id,'growth':growth,'lesson':lesson,'ability':ability,'none':None}
    if row['field'] not in options:raise ValueError('unsupported variant choice field')
    if negative_decision is not None and row.get('underdog_kind')!='points':raise ValueError('negative-bonus interpretation belongs to actual Realized Potential')
    if any(value is not None for key,value in options.items() if key!=row['field']):raise ValueError('unexpected choice field for CSV variant')
    supplied=options[row['field']]
    fixed=row['choice']
    value=choice_value(engine.r,row,fixed if supplied is None else supplied)
    if fixed is not None and value!=choice_value(engine.r,row,fixed):raise ValueError('choice conflicts with fixed CSV variant')
    def apply(e,t,o):
        selected(e.r,row)
        if row.get('native_kind')=='capability_parameters':
            import capability_parameter_edges as PARAMETERS
            result=PARAMETERS.teach(e,o,t,row,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['policy']=='poke_edge/고급-연결':
            import advanced_connection as CONNECTION
            result=CONNECTION.teach(e,o,t,row,value,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['policy']=='poke_edge/특성-숙달':
            import ability_mastery as ABILITY_MASTERY
            result=ABILITY_MASTERY.teach(e,o,t,row,value,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['policy']=='poke_edge/약골의-수업':
            import underdog_lessons as LESSONS
            result=LESSONS.teach(e,o,t,row,value,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row.get('underdog_kind') in ('base','points'):
            import underdog_edges as UNDERDOG
            result=UNDERDOG.teach(e,o,t,row,growth=value,negative_decision=negative_decision,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['policy']=='poke_edge/tk-마스터리':
            import tk_mastery as MASTERY
            result=MASTERY.teach(e,o,target=t,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['policy']=='poke_edge/기본-원거리-공격':
            import ranged_struggle as RANGED
            result=RANGED._teach(e,o,t,value,from_grooming,from_training,safe)
        elif row['field']=='skill':
            import pokemon_teaching as T
            result=T._teach_edge(e,o,target=t,edge=row['policy'],skill=value,from_grooming=from_grooming,from_training=from_training,safe=safe)
        elif row['field']=='stat':
            import pokemon_stat_edges as STAT
            result=STAT._teach(e,o,t,value,from_grooming,from_training,safe)
        elif row['field']=='move_id':
            import pokemon_move_edges as MOVE
            result=MOVE._teach(e,o,t,value,from_grooming,from_training,safe)
        else:
            import pokemon_capability_edges as CAP
            result=CAP._teach(e,o,t,row['policy'],value,from_grooming,from_training,safe)
        receipt=t.spec['learned_poke_edges'][-1]
        receipt['definition_origin']={'clause_id':row['clause_id'],'rule_id':row['rule_id'],'record':row['record']}
        validate_receipt(e.r,receipt)
        result['definition_origin']=dict(receipt['definition_origin'])
        return result
    return G.transition(engine,target,apply,participants=(owner,))
