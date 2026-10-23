"""Explicit read-only bindings to actual native actor state, without path eval.

owner_id reads the native trainer_id relation, not possession or control.
controller_kind and controller_id preserve actor/player/GM namespaces; authors
must test the kind when comparing a controller ID with an actor ID. Missing
relations and unresolved controller identities stay unknown. Queries establish
facts, not ownership changes or additional native action permissions.
"""

WORLD_FIELDS={'elapsed_seconds':'integer','round_no':'integer',
              'encounter_active':'boolean','session_id':'string','weather_is':'boolean'}

FIELDS={'grant_active':'boolean','level':'integer','kind':'string','entity_id':'string','species_id':'string',
        'skill_rank':'integer','effective_skill_rank':'integer','skill_reward_max_rank':'integer','owned_rule_count':'integer',
        'owner_id':'string','controller_kind':'string','controller_id':'string',
        'consumed':'boolean','destroyed':'boolean','disabled':'boolean','suppressed':'boolean',**WORLD_FIELDS}


def validate(spec):
    binding=spec.get('binding')
    if type(binding) is not dict or not {'subject','field'}<=set(binding):
        raise ValueError('state input requires subject and field binding')
    field=binding['field']
    if type(field) is not str or field not in FIELDS or binding['subject'] not in ('actor','target','entity','world'):
        raise ValueError('unsupported native state binding')
    if (binding['subject']=='world') != (field in WORLD_FIELDS):
        raise ValueError('world clock fields require world subject')
    required={'subject','field','rule_id'} if field=='owned_rule_count' else {'subject','field','milestone'} if field=='skill_reward_max_rank' else {'subject','field','skill'} if field in ('skill_rank','effective_skill_rank') else {'subject','field'}
    if field=='grant_active':
        required={'subject','field','source_id'}
        if type(binding.get('source_id')) is not str or not binding['source_id']:raise ValueError('explicit grant source identity required')
    if field=='weather_is':
        required={'subject','field','weather'}
        if type(binding.get('weather')) is not str or not binding['weather']:raise ValueError('explicit weather identity required')
    if binding['subject']=='entity':
        if field not in ('grant_active','entity_id','kind','owner_id','controller_kind','controller_id','consumed','destroyed','disabled','suppressed'):
            raise ValueError('entity binding supports identity fields only')
        required=required | {'entity_id'}
        if type(binding.get('entity_id')) is not str or not binding['entity_id'].strip():
            raise ValueError('explicit entity identity required')
    if field in ('consumed','destroyed','disabled','suppressed') and binding['subject']!='entity':
        raise ValueError('physical lifecycle requires an explicit entity binding')
    if set(binding)!=required or spec['type']!=FIELDS[field]:
        raise ValueError('native state binding fields/type mismatch')
    if 'rule_id' in binding and (type(binding['rule_id']) is not str or not binding['rule_id'].startswith(('edge/','feat/','class/'))):
        raise ValueError('exact trainer acquisition rule identity required')
    if 'milestone' in binding and (type(binding['milestone']) is not int or binding['milestone'] not in (2,6,12)):
        raise ValueError('known skill reward milestone required')
    if 'skill' in binding and (type(binding['skill']) is not str or not binding['skill'].strip()):
        raise ValueError('explicit skill identity required')


def read(engine,actor,target,specs):
    required={key:spec for key,spec in specs.items() if spec['authority']=='state'}
    import world_entities as W
    index=W.require_actors(engine,actor,target)
    result={}
    for key,spec in required.items():
        validate(spec);binding=spec['binding']
        if binding['subject']=='world':
            result[key]=(engine.weather==binding['weather']) if binding['field']=='weather_is' else getattr(engine,binding['field'])
            continue
        if binding['field']=='grant_active':
            subject=index.get(binding['entity_id']) if binding['subject']=='entity' else actor if binding['subject']=='actor' else target
            if subject is None:raise ValueError('actual grant provider actor required')
            result[key]=binding['source_id'] in subject.spec.get('state_grants',{}).get('sources',{})
            continue
        if binding['subject']=='entity':
            result[key]=W.entity_identity(engine,binding['entity_id']).get(binding['field'])
            continue
        subject=actor if binding['subject']=='actor' else target
        field=binding['field']
        if field in ('skill_rank','effective_skill_rank'):
            import skill_modifiers as S
            S.skill_id(engine.r.skill_policy,binding['skill'],required=True)
            result[key]=S.rank(engine.r,subject,binding['skill'])[2] if field=='skill_rank' else S.effective_rank(engine.r,subject,binding['skill'])
        elif field=='species_id':
            result[key]=subject.spec.get('species')
        elif field=='owned_rule_count':
            import acquired_features as ACQUIRED
            result[key]=ACQUIRED.owned_rule_count(subject,binding['rule_id'])
        elif field=='skill_reward_max_rank':
            import trainer_entitlements as E
            rewards=E.skill_rewards(engine,subject) if subject.kind=='trainer' else []
            result[key]=next((row['max_rank'] for row in rewards if row['level']==binding['milestone']),None)
        elif field in ('entity_id','kind','owner_id','controller_kind','controller_id'):
            result[key]=W.identity_field(engine,subject,field,index=index)
        else:result[key]=getattr(subject,field,None)
    return result
