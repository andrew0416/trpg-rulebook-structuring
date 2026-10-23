"""Sourced permanent stat-allocation exceptions from acquired Poke Edges."""
import state_fields as F

ATTACK_CONFLICT='poke_edge/공격-충돌'
ALIASES=(ATTACK_CONFLICT,'공격 충돌','Attack Conflict')
CHOICES={'atk':'atk','공격':'atk','Attack':'atk','spa':'spa','특공':'spa','특수공격':'spa','Special Attack':'spa'}


def base_sources(rules,spec):
    import underdog_edges as U
    import baby_templates as BABY
    import special_entities as SPECIAL
    import marsupial_state as MARSUPIAL
    others=U.base_sources(rules,spec)+BABY.base_sources(rules,spec)+SPECIAL.prime_base_sources(rules,spec)+__import__('researcher_fields').base_sources(rules,spec)
    return others+MARSUPIAL.base_sources(rules,spec,others)


def point_sources(rules,spec,*,form='base'):
    import underdog_edges as U
    import mixed_sweeper as M
    return U.point_sources(rules,spec,form=form)+M.point_sources(rules,spec,form=form)


def validate(rules,spec):
    investments=spec.get('learned_poke_edges',[])
    if not isinstance(investments,list) or any(not isinstance(r,dict) for r in investments):raise ValueError('Poke Edge investments must be records')
    rows=[r for r in investments if r.get('source')==ATTACK_CONFLICT]
    if rows and spec.get('kind')!='pokemon':raise ValueError('Poke Edge investment requires an actual Pokemon')
    if len(rows)>1:raise ValueError('Attack Conflict is not a ranked or repeatable Poke Edge')
    for row in rows:
        import poke_edge_variants as VARIANTS
        VARIANTS.validate_receipt(rules,row)
        if rules._selected_rule(ATTACK_CONFLICT)!=ATTACK_CONFLICT:raise ValueError('selected Attack Conflict needs its own allocation policy')
        if row.get('stat') not in ('atk','spa') or row.get('status')!='active':raise ValueError('Attack Conflict needs one active Attack or Special Attack choice')
        F.integer(row.get('point_cost'),'Attack Conflict investment',1,1)
    legacy=spec.get('stat_relation_exempt',[])
    if not isinstance(legacy,(list,tuple)) or any(not isinstance(st,str) or st not in F.STATS for st in legacy) or len(set(legacy))!=len(legacy):raise ValueError('explicit distinct legacy base-relation exceptions required')
    return rows


def exemptions(rules,spec):
    rows=validate(rules,spec)
    return set(spec.get('stat_relation_exempt',[]))|{row['stat'] for row in rows}


def teach(e,owner,*,target,stat,from_grooming=False,from_training=False,safe=None):
    import state_grants as G
    return G.transition(e,target,lambda se,st,so:_teach(se,so,st,stat,from_grooming,from_training,safe),participants=(owner,))


def _teach(e,owner,target,stat,from_grooming,from_training,safe=None):
    import pokemon_teaching as T
    T._pokemon(e,owner,target);T.source(e.r,ATTACK_CONFLICT,T.POINTS)
    choices=CHOICES
    if not isinstance(stat,str) or stat not in choices:raise ValueError('choose Attack or Special Attack explicitly')
    chosen=choices[stat]
    if validate(e.r,target.spec):raise ValueError('Attack Conflict is already acquired')
    if T._balance(target.spec)<1:raise ValueError('Attack Conflict costs one Tutor Point')
    if T.credit_mode(from_grooming,from_training):T.training_credit(e,owner,target,ATTACK_CONFLICT,from_training=from_training)
    else:T.edge_training_hour(e,owner,target,ATTACK_CONFLICT,ATTACK_CONFLICT,safe=safe)
    T._debit_points(target.spec,1)
    target.spec.setdefault('learned_poke_edges',[]).append({'source':ATTACK_CONFLICT,
        'status':'active','stat':chosen,'point_cost':1,'trainer_id':owner.entity_id,
        'training_source':'edge/미용사' if from_grooming else 'input/ch05-pokemon.md:229' if from_training else 'input/ch05-pokemon.md:274',
        'completed_at':e.elapsed_seconds})
    if T.credit_mode(from_grooming,from_training):T.consume_credit(target,ATTACK_CONFLICT,from_training=from_training)
    validate(e.r,target.spec)
    return {'activity':'teach_edge','edge':ATTACK_CONFLICT,'stat':chosen,'point_cost':1,'seconds':0 if (from_grooming or from_training) else 3600}


def levelup_provider(rules,spec,growth_context):
    """Resolve a live owner for this level-up only; never persist a blanket exemption."""
    if growth_context is None:return None
    engine,target=growth_context
    import world_entities as W
    index=W.require_actors(engine,target)
    if engine.r is not rules or target.kind!='pokemon' or spec.get('id')!=target.entity_id:
        raise ValueError('level-up context must name the actual Pokemon')
    owner_id=spec.get('trainer_id')
    if owner_id is None:return None
    owner=index.get(owner_id)
    if owner is None or owner.kind!='trainer':raise ValueError('actual trainer owner required for level-up context')
    import acquired_features as A
    import stat_ace as STAT
    ace=[branch for branch in STAT.STATS if STAT.acquired(owner,STAT.CLASS,branch)]
    ace_context={'source':STAT.CLASS,'trainer_id':owner.entity_id,'target_id':target.entity_id,
                 'selection':rules.select_source_definition(STAT.CLASS),'stat_ace_branches':ace} if ace else None
    uid='class/불굴의-투지'
    # An unrelated unavailable class must not invalidate ordinary growth.
    from enduring_awareness import acquired
    if not acquired(owner,uid,('Enduring Soul',)):return ace_context
    if not A.owned_rule_count(owner,uid):return ace_context
    selected=rules.select_source_definition(uid)
    result={'source':uid,'trainer_id':owner.entity_id,'target_id':target.entity_id,'selection':selected}
    if ace:result['stat_ace_branches']=ace
    return result
