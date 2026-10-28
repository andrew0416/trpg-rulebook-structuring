"""Exact sacrifice-Move and selected Sturdy HP-loss boundaries, not a new ruleset."""
from contextvars import ContextVar
from functools import wraps
from inspect import signature
_PREPARED=ContextVar('hp_setting_prepared_move_choices',default=None)
FINAL='move/목숨걸기'
EXPLOSIONS={'move/대폭발','move/자폭'}
AFTER_ALL=EXPLOSIONS|{'move/미스트버스트'}
CAPS={'ability/옹골참-홈브류':303,'ability/옹골참-playtest':491}
MOVE_REF={'file':'input/db/moves.csv','sha256':'ab83f872e5eca67a41db7d126b842f0165437e0fa70bb77ddad832a0b7396c93'}
ABILITY_REF={'file':'input/db/abilities.csv','sha256':'87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'}

def _root_context(engine,activation=None):
    # Reuse only aliases issued by the existing validated atomic deepcopy graph.
    import state_grants as GRANTS
    for original,staged,aliases in reversed(GRANTS._TRANSITION_MOVE_ALIASES.get()):
        if engine is not staged:continue
        if activation is not None:
            keys=[key for key,value in aliases.items() if value is activation]
            if keys:
                values=[scope['activation'] for scope in getattr(original,'_move_activation_scopes',())
                        if id(scope['activation']) in keys]
                if len(values)!=1:raise ValueError('prepared loyalty native activation alias changed')
                activation=values[0]
        engine=original
    return engine,activation

def _root_actor(engine,actor):
    import world_entities as WORLD
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError('prepared loyalty requires the actual world actor')
    root,_=_root_context(engine)
    return WORLD.actor_index(root).get(actor.entity_id)

def preparation_scope(fn):
    """One public activation owns one GM decision across its repeated preflights."""
    sig=signature(fn)
    @wraps(fn)
    def run(*args,**kwargs):
        bound=sig.bind(*args,**kwargs)
        args,kwargs=bound.args,bound.kwargs
        supplied=bound.arguments
        engine=supplied.get('self',supplied.get('engine'))
        parent=_PREPARED.get();activation=supplied.get('_activation')
        world,original_activation=_root_context(engine,activation)
        live=[scope for scope in getattr(engine,'_move_activation_scopes',())
              if activation is not None and scope['activation'] is activation
              and scope['accuracy'] is supplied.get('_shared_accuracy')
              and scope['actor'] is supplied.get('attacker')
              and scope['move_id']==supplied.get('move_id')
              and 0<=scope['index']<len(scope['targets'])
              and supplied.get('target') is scope['targets'][scope['index']]]
        if (parent is not None and parent['world'] is world and len(live)==1
                and parent['source'] in (None,live[0]['move_id'])
                and _root_actor(engine,supplied['attacker']) is _root_actor(parent['engine'],parent['actor'])):
            current=tuple(_root_context(engine,s['activation'])[1] for s in engine._move_activation_scopes)
            if parent['activation'] is original_activation:
                return fn(*args,**kwargs)
            if (parent['activation'] is None and len(current)==len(parent['baseline'])+1
                    and all(a is b for a,b in zip(current,parent['baseline']))
                    and current[-1] is original_activation):
                parent['activation']=original_activation
                return fn(*args,**kwargs)
        token=_PREPARED.set({'world':world,'engine':engine,'actor':supplied.get('attacker'),
            'source':None,'choices':{},'activation':original_activation if len(live)==1 else None,
            'baseline':tuple(_root_context(engine,s['activation'])[1] for s in getattr(engine,'_move_activation_scopes',()))})
        try:return fn(*args,**kwargs)
        finally:_PREPARED.reset(token)
    return run

def source(rules,uid,reference):
    from source_context import verified_source
    verified_source(rules,reference,label='HP-setting selected source')
    if rules._selected_rule(uid)!=uid:raise ValueError('exact HP-setting source must remain selected')

def registration(rules,value):
    """Keep exact selected cap identities separate from the conflicting R492 name."""
    home='ability/옹골참-홈브류';play='ability/옹골참-playtest'
    if value in CAPS:uid=value
    elif value in ('옹골참','ability/옹골참'):
        uid=rules._selected_rule('ability/옹골참')
        if uid not in CAPS:return None
    elif value=='옹골참 [Playtest]':uid=play
    elif value=='옹골참 [홈브류]':
        if rules._selected_rule('ability/옹골참')!=home:
            from ruleset import UnresolvedRuleSelection
            raise UnresolvedRuleSelection(value,[home,'ability/옹골참-홈브류-2'])
        uid=home
    else:return None
    source(rules,uid,ABILITY_REF)
    unit=rules.selection.units[uid];origin=unit['source']
    if origin.get('file')!='db/abilities.csv' or origin.get('record_span')!=[CAPS[uid],CAPS[uid]]:
        raise ValueError('selected Sturdy registration source changed')
    return {'name':unit['title'],'source_id':uid,'equivalent_source_ids':[uid]}

def cap_active(engine,actor,cap):
    uid=cap.get('_rule_id')
    if uid=='ability/옹골참-홈브류-2':
        engine.r._selected_rule(uid)
        raise ValueError('conflicting R492 Sturdy source is not an authorized cap')
    if uid not in CAPS:return True
    source(engine.r,uid,ABILITY_REF)
    row=engine.r.selection.units[uid]['source']
    if row.get('file')!='db/abilities.csv' or row.get('record_span')!=[CAPS[uid],CAPS[uid]]:
        raise ValueError('Sturdy cap source binding changed')
    if (cap.get('value')!='max_hp/2' or cap.get('applies_to')!='damage and hp loss'
            or cap.get('round')!=('up' if CAPS[uid]==303 else None)):
        raise ValueError('selected Sturdy cap declaration changed')
    import ability_transitions as ABILITIES
    return ABILITIES.active(actor,uid)

def final_gambit(move,mechanics):
    if move.get('id')!=FINAL:return False
    effects=mechanics.get('effects_exec',[])
    stripped=[{k:v for k,v in e.items() if not k.startswith('_')} for e in effects]
    return (len(stripped)==2 and type(stripped[0].get('self_hp')) is int and stripped[0].get('faint') is True
            and stripped==[{'type':'self_hp_set','self_hp':0,'faint':True},
                      {'type':'hp_loss','value':'hp lost by user','target':'target','as':'damage'}]
            )

def preflight(engine,actor,effects,uid):
    if uid not in AFTER_ALL|{FINAL}:return
    source(engine.r,uid,MOVE_REF)
    setting=[e for e in effects if e.get('type')=='self_hp_set']
    if len(setting)!=1:raise ValueError('one exact sacrifice HP-setting declaration required')
    e=setting[0]
    if uid==FINAL:
        if not final_gambit({'id':uid},{'effects_exec':effects}) or e.get('faint') is not True:
            raise ValueError('Final Gambit source declaration changed')
    elif e.get('self_hp')!='-50% max' or e.get('unpreventable') is not True or uid in EXPLOSIONS and e.get('loyalty')!=-1:
        raise ValueError('Explosion/Self-Destruct exact unavoidable self cost required')
    prepare_loyalty(engine,actor,e,uid)

def after_all(rules,move,effect):
    return move.get('id') in AFTER_ALL and effect.get('type')=='self_hp_set'

def prepare_loyalty(engine,actor,effect,uid,*,completion=None,allow_prompt=True):
    if 'loyalty' not in effect:return None
    if uid not in EXPLOSIONS or effect['loyalty']!=-1:
        raise ValueError('only reviewed Explosion/Self-Destruct loyalty decrease is supported')
    source(engine.r,uid,MOVE_REF)
    if completion is not None:return completion_choice(engine,actor,uid,completion)
    live=[scope for scope in getattr(engine,'_move_activation_scopes',())
          if scope['actor'] is actor and scope['move_id']==uid and scope.get('completion_id') is not None]
    if len(live)==1:return completion_choice(engine,actor,uid,live[0]['completion_id'])
    if actor.kind!='pokemon':return None
    import world_entities as WORLD,pokemon_entities as ENTITIES
    owner=WORLD.identity_field(engine,actor,'owner_id')
    if owner is None:
        if actor.spec.get('wild') is True:return None
        raise ValueError('actual trainer relationship or explicit wild observation required')
    before=ENTITIES.loyalty_value(actor,required=True)
    prepared=_PREPARED.get()
    if prepared is not None:
        world,_=_root_context(engine)
        if (prepared['world'] is not world or prepared['source'] not in (None,uid)
                or _root_actor(engine,actor) is not _root_actor(prepared['engine'],prepared['actor'])):
            prepared=None
        else:prepared['source']=uid
    key=(actor.entity_id,uid,owner,before)
    if prepared is not None and key in prepared['choices']:return dict(prepared['choices'][key])
    if (getattr(engine,'_resuming_move_activation',False) and
            any(scope['actor'] is actor and scope['move_id']==uid for scope in getattr(engine,'_move_activation_scopes',()))):
        raise ValueError('prepared sacrifice loyalty decision was not retained before native suspension; do not requery after cost')
    if not allow_prompt:raise ValueError('sacrifice decision must be prepared before its paid native completion')
    answer=engine.rulings.decide({'type':'sacrifice_loyalty','unit':uid,'actor_id':actor.entity_id,
        'text':'GM specifies the resulting loyalty decrease; the source supplies no numeric decrement.'})
    if (not isinstance(answer,dict) or set(answer)!={'after','reason'} or type(answer['after']) is not int
            or not 0<=answer['after']<=before or before>0 and answer['after']==before
            or not isinstance(answer['reason'],str) or not answer['reason'].strip()):
        raise ValueError('explicit GM loyalty decrease and reason required before sacrifice cost')
    decision=dict(answer,before=before,owner=owner)
    if prepared is not None:prepared['choices'][key]=dict(decision)
    return decision

def apply_loyalty(engine,actor,choice,source_id,completion):
    if choice is None:return
    import world_entities as WORLD,pokemon_entities as ENTITIES
    if WORLD.identity_field(engine,actor,'owner_id')!=choice['owner'] or ENTITIES.loyalty_value(actor,required=True)!=choice['before']:
        raise ValueError('sacrifice loyalty observation changed during resolution')
    ENTITIES.observe_loyalty(engine,actor,choice['after'],reason=choice['reason'],
        request_id=('sacrifice:'+str(completion)) if completion is not None else None)

def _seal_prepared(record):
    from root_resolution import fingerprint
    return fingerprint({k:v for k,v in record.items() if k!='integrity'})

def begin_move(engine,row):
    """The existing completion is created before any recipient damage/suspension."""
    uid=row['move_id']
    if uid not in EXPLOSIONS:return
    effects=[e for e in row['post_effects'] if e.get('type')=='self_hp_set']
    if len(effects)!=1:raise ValueError('one source-owned sacrifice completion cost required')
    choice=prepare_loyalty(engine,row['actor'],effects[0],uid,allow_prompt=False)
    record={'completion_id':row['id'],'source_id':uid,'actor_id':row['actor'].entity_id,
            'profile':row['profile'],'source_sha256':MOVE_REF['sha256'],
            'choice':dict(choice) if choice is not None else None}
    record['integrity']=_seal_prepared(record)
    row['hp_setting_prepared']=record

def _validate_prepared(engine,row):
    record=row.get('hp_setting_prepared')
    if (not isinstance(record,dict) or set(record)!={'completion_id','source_id','actor_id','profile','source_sha256','choice','integrity'}
            or row['move_id'] not in EXPLOSIONS or record['completion_id']!=row['id']
            or record['source_id']!=row['move_id'] or record['actor_id']!=row['actor'].entity_id
            or record['profile']!=row['profile'] or record['source_sha256']!=MOVE_REF['sha256']
            or record['integrity']!=_seal_prepared(record)):
        raise ValueError('prepared sacrifice completion binding changed')
    choice=record['choice']
    if choice is not None and (not isinstance(choice,dict) or set(choice)!={'before','after','owner','reason'}
            or type(choice['before']) is not int or type(choice['after']) is not int
            or not 0<=choice['after']<=choice['before']<=6 or choice['before']>0 and choice['after']==choice['before']
            or not isinstance(choice['owner'],str) or not choice['owner']
            or not isinstance(choice['reason'],str) or not choice['reason'].strip()):
        raise ValueError('prepared sacrifice GM decision changed')
    return choice

def completion_choice(engine,actor,uid,completion):
    row=getattr(engine,'_move_completions',{}).get(completion)
    if (row is None or row['actor'] is not actor or row['move_id']!=uid
            or row['phase'] not in ('targets','applying','completion_effects')):
        raise ValueError('actual unfinished sacrifice completion required')
    import move_activation as ACTIVATION,world_entities as WORLD,pokemon_entities as ENTITIES
    if WORLD.actor_index(engine).get(actor.entity_id) is not actor:
        raise ValueError('actual sacrifice completion world actor required')
    if row['profile']!=ACTIVATION._profile(engine):raise ValueError('prepared sacrifice profile changed')
    source(engine.r,uid,MOVE_REF)
    choice=_validate_prepared(engine,row)
    if choice is None:
        if actor.kind=='pokemon' and (WORLD.identity_field(engine,actor,'owner_id') is not None or actor.spec.get('wild') is not True):
            raise ValueError('prepared sacrifice trainer relationship changed')
        return None
    if WORLD.identity_field(engine,actor,'owner_id')!=choice['owner'] or ENTITIES.loyalty_value(actor,required=True)!=choice['before']:
        raise ValueError('prepared sacrifice owner or prior loyalty changed')
    return dict(choice)

def validate_world(engine,index):
    for row in getattr(engine,'_move_completions',{}).values():
        if 'hp_setting_prepared' in row:
            if index.get(row['actor'].entity_id) is not row['actor']:
                raise ValueError('prepared sacrifice actor is not in this world')
            _validate_prepared(engine,row)
        elif row['move_id'] in EXPLOSIONS and row['phase'] not in ('complete','interrupted'):
            raise ValueError('active sacrifice completion lacks its prepared choice record')
