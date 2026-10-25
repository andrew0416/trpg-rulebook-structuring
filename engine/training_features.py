"""PTK training regimes and their source-owned Priority (Limited) Orders.

ch03:620,693,696-718 uses thirty minutes in the selected Korean rules.
Orders use actual communication and expire at the issuer's next turn start.
Training never silently awards experience, tutor points, or a new movement mode.
"""
from copy import deepcopy
import common_checks as C
import skill_modifiers as SKILL
import state_grants as GRANTS
import turn as TURN

TYPE = 'training_regime'
AGILITY = 'feat/민첩성-훈련'
BRUTAL = 'feat/잔혹성-훈련'
FOCUSED = 'feat/집중성-훈련'
INSPIRED = 'feat/영감성-훈련'
ELITE = 'feat/엘리트-트레이너'
ACE = 'class/에이스-트레이너'
TRAINED_STAT = 'ace_trained_stat'
ACE_SOURCES = {
    'C03-123': {'file': 'input/ch03-skills-edges-feats.md',
                'sha256': 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23',
                'lines': [568, 570], 'requires_training_feat': True},
    'C04-009': {'file': 'input/ch04-trainer-classes.md',
                'sha256': 'a1a4a213074bc6166507db3e0d4c04ded02c04168c4798c636a4d53911494ac4',
                'lines': [312, 314], 'requires_training_feat': False},
    'C2CSV/input/db/feats.csv:R55:main': {'file':'input/db/feats.csv',
                'sha256':'4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd',
                'record_span':[55,55], 'requires_training_feat':False},
}
RULES = {
    AGILITY: {'aliases': ('민첩성 훈련', 'Agility Training'), 'skills': {'육상': 3, '명령': 2}, 'bonuses': {'movement': 1, 'initiative': 4}},
    BRUTAL: {'aliases': ('잔혹성 훈련', 'Brutal Training'), 'skills': {'협박': 3, '명령': 2}, 'bonuses': {'critical': 1, 'effect': 1}},
    FOCUSED: {'aliases': ('집중성 훈련', 'Focused Training'), 'skills': {'명령': 3}, 'bonuses': {'accuracy': 1, 'skill': 2}},
    INSPIRED: {'aliases': ('영감성 훈련', 'Inspired Training'), 'skills': {'매력': 3, '명령': 2}, 'bonuses': {'evasion': 1, 'save': 2}},
}
CSV_CLAUSES = {
    AGILITY: 'C2CSV/input/db/feats.csv:R14:main',
    BRUTAL: 'C2CSV/input/db/feats.csv:R15:main',
    FOCUSED: 'C2CSV/input/db/feats.csv:R16:main',
    INSPIRED: 'C2CSV/input/db/feats.csv:R17:main',
}
BOOK_LINES = {AGILITY: [696, 700], BRUTAL: [702, 706], FOCUSED: [708, 712], INSPIRED: [714, 718]}
BOOK_SOURCE = {'file': 'input/ch03-skills-edges-feats.md', 'sha256': 'b94e43349794836391501f9aac10009d20746bf946ea0c4b5ff3adf85e982d23'}
CSV_SOURCE = {'file': 'input/db/feats.csv', 'sha256': '4435ff1c462a211564c85d2c1c9a2ac6e7c790c7545e1ad7056d32888b2367bd'}


def order_definitions(uid):
    """Whole reviewed book/CSV definitions; neither supplies fields to the other."""
    return [{'rule_id': CSV_CLAUSES[uid] if csv else uid,
             'source': deepcopy(CSV_SOURCE if csv else BOOK_SOURCE),
             'locator': {'record': 14 + list(RULES).index(uid)} if csv else {'lines': BOOK_LINES[uid][:]},
             'values': {'training_feature': uid, 'source_clause_id': CSV_CLAUSES[uid] if csv else
                        'input/ch03-skills-edges-feats.md:' + '-'.join(map(str, BOOK_LINES[uid])),
                        'self_target': csv, 'target': 'one_owned_pokemon_or_self' if csv else 'one_owned_pokemon',
                        'communication': 'required_except_self' if csv else 'required',
                        'action': 'standard', 'priority': 'limited', 'frequency': 'at_will',
                        'lifetime': 'start_of_issuer_next_actual_turn', 'stacks_with_training': True,
                        'skills': deepcopy(RULES[uid]['skills']), 'bonuses': deepcopy(RULES[uid]['bonuses'])}}
            for csv in (False, True)]


def selected_order(rules, name):
    uid = identity(name)
    if uid is None: raise ValueError('known training feature required')
    requested = name if name in CSV_CLAUSES.values() else uid
    return rules.bind_source_policy(requested, order_definitions(uid))


def order_values(uid, binding, clause):
    import source_selection as SELECTION
    if uid not in RULES: raise ValueError('known Training Order feature required')
    if binding is None:
        # Old producers retained their actual CSV clause, but never a selection binding.
        if clause != CSV_CLAUSES.get(uid): raise ValueError('legacy Training Order requires its actual CSV source clause')
        return deepcopy(order_definitions(uid)[1]['values'])
    values = SELECTION.policy_values(binding, order_definitions(uid))
    if values['training_feature'] != uid or values['source_clause_id'] != clause:
        raise ValueError('Training Order source policy and clause changed')
    return values


def validate_order_history(owner):
    import trainer_feature_acquisition as ACQUISITION
    uses = owner.spec.get('training_order_uses', [])
    if type(uses) is not list: raise ValueError('actual Training Order use history required')
    for use in uses:
        if (type(use) is not dict or set(use) != {'result', 'integrity'} or type(use['result']) is not dict
                or use['integrity'] != ACQUISITION._digest('training-order/use/v1', use['result'])):
            raise ValueError('Training Order use receipt changed')
        result = use['result']; uid = result.get('rule_id')
        if uid not in RULES or result.get('trainer_id') != owner.entity_id:
            raise ValueError('Training Order use owner or feature changed')
        if result.get('order_source',{}).get('edition')=='core':
            paid=core_payment(owner,result.get('core_standard_payment',{}).get('id'))
            if (result['order_source']!=paid['source'] or result.get('source_clause_id')!=paid['source']['clause_id']
                    or result.get('target_id')!=paid['target_id'] and not __import__('commander').training_authority_id(owner,result.get('target_id'),uid,paid['id'])):
                raise ValueError('Core Training Order use source or recipient changed')
            values={'self_target':False}
        else:values = order_values(uid, result.get('source_policy_binding'), result.get('source_clause_id'))
        if result.get('target_id') == owner.entity_id and not values['self_target']:
            raise ValueError('book Training Order cannot target its issuer')
    return uses

def identity(name):
    if not isinstance(name, str): return None
    if name in CSV_CLAUSES.values(): return next(uid for uid, clause in CSV_CLAUSES.items() if clause == name)
    return next((uid for uid, policy in RULES.items() if SKILL.key(name) in {SKILL.key(x) for x in (uid, *policy['aliases'])}), None)

def _count(actor, names):
    aliases = {SKILL.key(x) for x in names}
    values = actor.spec.get('feats', [])
    if not isinstance(values, (list, tuple)): raise ValueError('actual acquired features must be a list')
    return sum(SKILL.key(x) in aliases for x in values)

def elite(actor):
    count = _count(actor, (ELITE, '엘리트 트레이너', 'Elite Trainer'))
    if not count: return False
    if count != 1 or actor.kind != 'trainer': raise ValueError('one actual Elite Trainer acquisition required')
    if actor.r._selected_rule(ELITE) != ELITE: raise ValueError('selected Elite Trainer variant needs its own policy')
    if __import__('ace_trainer').acquired(actor,ELITE):
        __import__('trainer_feature_acquisition').validate_actor(actor)
        return True
    if sum(SKILL.key(x) in {SKILL.key(n) for n in ('class/에이스-트레이너', '에이스 트레이너', 'Ace Trainer')} for x in [*actor.spec.get('classes', []), *actor.spec.get('feats', [])]) != 1 or SKILL.rank(actor.r, actor, '명령')[2] < 3:
        raise ValueError('Elite Trainer requires acquired Ace Trainer with Novice Command')
    return True

def owns(actor, uid, *, order_binding=None):
    count = _count(actor, (uid, *RULES[uid]['aliases']))
    if not count: return False
    if count != 1 or actor.kind != 'trainer': raise ValueError('one actual trainer feature acquisition required')
    if order_binding is None and actor.r._selected_rule(uid) != uid: raise ValueError('selected training variant needs its own policy')
    if uid in RULES:
        import trainer_feature_acquisition as TFA
        if any(active and row['static_acquisition']['feature_id'] == uid for _,row,active in TFA._static_records(actor)):
            TFA.validate_actor(actor)
            return True
    # Imported acquisition is not new character creation. The precise Elite gift
    # must be identified to apply its printed prerequisite waiver.
    gift = actor.spec.get('elite_training_choice')
    waived = gift is not None and identity(gift) == uid and elite(actor)
    if not waived and any(SKILL.rank(actor.r, actor, skill)[2] < minimum for skill, minimum in RULES[uid]['skills'].items()):
        raise ValueError('training feature prerequisite is not established: ' + uid)
    return True

def register_owned(engine, actor, name):
    uid = identity(name)
    if uid is None: return False
    owns(actor, uid)
    # Registration alone does not execute either mode or award any bonus.
    return True

def records(actor):
    return [row for row in getattr(actor, 'registry', ()) if isinstance(row, dict) and row.get('type') == TYPE]

def active(actor):
    result = []
    sources = actor.spec.get(GRANTS.KEY, {}).get('sources', {})
    for row in records(actor):
        source = row.get(GRANTS.TAG)
        receipt = sources.get(source)
        if receipt is None: raise ValueError('training projection requires its live source receipt')
        uid = row.get('rule_id')
        definition=row.get('training_reward_definition')
        if definition is not None:
            import training_rewards as REWARDS
            REWARDS.bonus_definition(definition)
            if definition['source']!=uid:raise ValueError('declared training bonus source changed')
        elif uid not in RULES:raise ValueError('known training regime required')
        if row.get('mode') != 'orders' and actor.r._selected_rule(uid) != uid: raise ValueError('training source selection changed')
        owner = row.get('owner')
        if owner is None or owner.entity_id != receipt.get('owner_id'): raise ValueError('training owner receipt mismatch')
        if (actor is not owner and (actor.spec.get('trainer_id', owner.entity_id) != owner.entity_id or actor.spec.get('trainer', owner.name) != owner.name)
                and not (row.get('mode')=='orders' and (__import__('commander').training_authority(owner,actor,uid,row.get('order_id'))))):
            raise ValueError('training ownership changed without source cleanup')
        mode=row.get('mode')
        if mode not in ('training','orders'): raise ValueError('unsupported Training/Orders source mode')
        if mode=='orders':
            core=row.get('order_source',{}).get('edition')=='core'
            origin=__import__('native_order_transfer').origin_id(row,actor)
            if core:
                paid=core_payment(owner,row.get('order_id'))
                if (row['order_source']!=paid['source'] or row.get('source_clause_id')!=paid['source']['clause_id']
                        or receipt.get('core_order_payment')!=paid['id'] or paid['feature']!=uid
                        or paid['target_id']!=origin and not __import__('commander').training_authority(owner,actor,uid,paid['id'])):
                    raise ValueError('Core Training Order requires its exact native Standard payment')
            else:
                binding=row.get('source_policy_binding')
                values=order_values(uid,binding,row.get('source_clause_id'))
                if origin==owner.entity_id and not values['self_target']:
                    raise ValueError('book Training Order cannot target its issuer')
                if binding is not None and (receipt.get('source_policy_binding')!=binding
                        or receipt.get('source_clause_id')!=row['source_clause_id']):
                    raise ValueError('Training Order grant source policy changed')
                if binding is None and ('source_policy_binding' in receipt or 'source_clause_id' in receipt):
                    raise ValueError('Training Order lost its producing source policy')
                uses=validate_order_history(owner)
                producing=[use['result'] for use in uses if use['result'].get('source')==source]
                if binding is not None and (len(producing)!=1
                        or producing[0].get('source_policy_binding')!=binding
                        or producing[0].get('source_clause_id')!=row['source_clause_id']
                        or producing[0].get('target_id')!=origin):
                    raise ValueError('Training Order lost its actual producing source receipt')
            import combat_timing as TIMING
            import priority_limited as PRIORITY
            PRIORITY.validate(owner)
            if core:pass
            elif row.get('free_order_payment') is not None:
                if receipt.get('free_order_payment')!=row['free_order_payment']:
                    raise ValueError('Training Order Free payment source changed')
            elif row.get('ordinary_order_payment') is not None:
                paid=row['ordinary_order_payment']
                if (receipt.get('ordinary_order_payment')!=paid or set(paid)!={'kind','action','turn','history_index'}
                        or paid['kind']!='ordinary' or paid['action']!='standard'
                        or type(paid['turn']) is not int or not 1<=paid['turn']<=owner.custom_conditions.get('combat_turn_serial',0)
                        or type(paid['history_index']) is not int or paid['history_index']<0):
                    raise ValueError('Training Order ordinary Standard payment changed')
                if paid['turn']==owner.custom_conditions.get('combat_turn_serial',0):
                    history=owner._action_history
                    if paid['history_index']>=len(history) or history[paid['history_index']]!='standard':
                        raise ValueError('Training Order lost its actual Standard action')
            else:
                payments=[payment for payment in PRIORITY.records(owner)
                          if payment['id']==row.get('order_id') and payment['source']==uid
                          and payment['subject_id']==origin]
                if len(payments)!=1 and not __import__('commander').training_authority(owner,actor,uid,row.get('order_id')):
                    raise ValueError('Training Order requires its exact Priority Limited payment')
            lifetime=[effect for effect in TIMING.records(actor) if effect.get('grant_source')==source]
            if len(lifetime)!=1 or lifetime[0].get('turn_owner') is not owner:
                raise ValueError('Training Order requires its live next-owner-turn lifetime')
        result.append(row)
    trained=[row for row in result if row['mode']=='training']
    ordered=[row for row in result if row['mode']=='orders']
    if len(trained) > 1 and (len(trained) > 2 or len({r['rule_id'] for r in trained}) != len(trained) or any(not r.get('elite_authority') for r in trained)):
        raise ValueError('invalid simultaneous training regimes')
    if len(ordered)>1:
        raise ValueError('multiple simultaneous Training Orders need an explicit stacking rule')
    return result


def preflight_transfer(engine,actor,replacement,*,identifiers=None):
    """Only the four live Training Orders, not an extended Training regime."""
    import combat_timing as TIMING
    import native_order_transfer as TRANSFER
    rows=[row for row in active(actor) if row['mode']=='orders'
          and (identifiers is None or TRANSFER.instance_id(row,actor) in identifiers)]
    if rows and any(row['mode']=='orders' for row in active(replacement)):
        raise ValueError('replacement already has a live Training Order')
    for row in rows:
        source=row[GRANTS.TAG];state=actor.spec[GRANTS.KEY]
        if state['effects'][source]!={'rows':['registry'],'listeners':[]}:
            raise ValueError('Training Order transfer requires its exact source-owned projection')
        if source in replacement.spec.get(GRANTS.KEY,{}).get('sources',{}):
            raise ValueError('Training Order source identity collision')
        lifetime=[effect for effect in TIMING.records(actor) if effect.get('grant_source')==source]
        if len(lifetime)!=1 or lifetime[0]['turn_owner'] is not row['owner']:
            raise ValueError('Training Order issuer deadline must remain authoritative')
    return rows


def transfer(engine,actor,replacement,*,source,recall_id,identifiers=None):
    import combat_timing as TIMING
    rows=preflight_transfer(engine,actor,replacement,identifiers=identifiers)
    for row in rows:
        key=row[GRANTS.TAG];old=actor.spec[GRANTS.KEY];new=GRANTS.state(replacement)
        __import__('native_order_transfer').observe(engine,actor,replacement,row,source,recall_id)
        new['sources'][key]=old['sources'].pop(key)
        new['effects'][key]=old['effects'].pop(key)
        actor.registry.remove(row);replacement.registry.append(row)
        timed=next(effect for effect in TIMING.records(actor) if effect.get('grant_source')==key)
        TIMING.records(actor).remove(timed)
        replacement.custom_conditions.setdefault(TIMING.KEY,[]).append(timed)
        engine.time_actors([replacement,row['owner']])
    active(actor);active(replacement)
    return [row[GRANTS.TAG] for row in rows]

def bonuses(row):
    """Read one validated native or declared training source contribution."""
    if row.get('mode')=='orders':
        if row.get('order_source',{}).get('edition')=='core':return RULES[row['rule_id']]['bonuses']
        return order_values(row['rule_id'],row.get('source_policy_binding'),row.get('source_clause_id'))['bonuses']
    return (row['training_reward_definition'] if 'training_reward_definition' in row else RULES[row['rule_id']])['bonuses']


def bonus(actor, field):
    import control_mount as MOUNT
    import ace_trainer as ACE_CLASS
    return sum(bonuses(row).get(field,0)*(MOUNT.agility_multiplier(actor) if row['rule_id']==AGILITY else 1)*ACE_CLASS.training_multiplier(actor,row)
               for row in active(actor))

def movement(actor, values):
    amount = bonus(actor, 'movement')
    return {key: value + amount if key in ('land', 'sky', 'levitate', 'swim', 'burrow', 'teleport') and value > 0 else value for key, value in values.items()}

def _declared_targets(engine, trainer, choices, *, allow_empty=False):
    import world_entities as WORLD
    if not isinstance(choices,(list,tuple)) or not 1<=len(choices)<=6:
        raise ValueError('one to six trained Pokemon required')
    plan=[]
    for pair in choices:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2:
            raise ValueError('each target needs its selected training features')
        pokemon,names=pair
        if not isinstance(names,(list,tuple)) or (not names and not allow_empty):
            raise ValueError('selected training features required')
        uids=[identity(name) for name in names]
        if None in uids or len(set(uids))!=len(uids):
            raise ValueError('distinct known training features required')
        plan.append((pokemon,uids))
    if len({id(p) for p,_ in plan})!=len(plan):
        raise ValueError('distinct actual training targets required')
    WORLD.require_actors(engine,trainer,*[p for p,_ in plan])
    return plan


def _targets(engine, trainer, choices, *, allow_empty=False):
    import training_eligibility as E
    plan=_declared_targets(engine,trainer,choices,allow_empty=allow_empty)
    E.participants(engine,trainer,[p for p,_ in plan])
    limit=2 if elite(trainer) else 1
    for pokemon,uids in plan:
        if len(uids)>limit:raise ValueError('selected training count exceeds the actual regime limit')
        for uid in uids:
            if not owns(trainer,uid):raise ValueError('trainer does not own selected training feature')
        if uids:
            for old in active(pokemon):
                if old['mode']=='training':GRANTS.preflight_revoke(pokemon,old[GRANTS.TAG])
    return plan


def _ace_source(rules, clause_id):
    from source_context import verified_source
    if type(clause_id) is not str or clause_id not in ACE_SOURCES:raise ValueError('exact reviewed Ace Trainer book source required')
    if rules._selected_rule(ACE)!=ACE or any(uid in rules.ruleset.unit_versions for uid in (ACE,clause_id)):
        raise ValueError('selected Ace Trainer variant requires its own reviewed policy')
    source=ACE_SOURCES[clause_id]
    reference={'file':source['file'].removeprefix('input/')}
    reference.update({key:source[key] for key in ('lines','record_span') if key in source})
    rules.ruleset.require({'id':clause_id,'source':reference})
    verified_source(rules,source,label='Ace Trainer')
    return source


def stat_records(actor):
    return [row for row in getattr(actor,'registry',()) if isinstance(row,dict) and row.get('type')==TRAINED_STAT]


def validate_trained(actor, actors=None):
    import combat_stage_sources as CS
    validate_order_history(actor)
    active(actor)
    rows=stat_records(actor)
    if len(rows)>2:raise ValueError('at most two actual Champ trained non-HP stats per Pokemon')
    if len(rows)==2 and (len({r.get('stat') for r in rows})!=2 or len({r.get('session') for r in rows})!=1
            or len({r.get('champ_acquisition') for r in rows})!=1 or not rows[0].get('champ_acquisition')):
        raise ValueError('one trained stat unless two distinct stats share one actual Champ training session')
    sources=actor.spec.get(GRANTS.KEY,{}).get('sources',{})
    tags=[row.get(GRANTS.TAG) for row in rows]
    if (any(type(tag) is not str or not tag for tag in tags)
            or {key for key,receipt in sources.items() if receipt.get('kind')==TRAINED_STAT}!=set(tags)):
        raise ValueError('trained stat source and recipient row must correspond exactly')
    for row in rows:
        source=row.get(GRANTS.TAG);owner=row.get('owner');stat=row.get('stat')
        if type(source) is not str or not source:raise ValueError('trained stat requires its actual source identity')
        receipt=sources.get(source,{})
        _ace_source(actor.r,row.get('source_clause_id'))
        if (actor.kind!='pokemon' or stat not in CS.STATS or getattr(owner,'kind',None)!='trainer'
                or (actors is not None and actors.get(owner.entity_id) is not owner)
                or any(receipt.get(key)!=value for key,value in {'kind':TRAINED_STAT,'owner_id':owner.entity_id,
                    'rule_id':ACE,'source_clause_id':row['source_clause_id'],'stat':stat,'lifetime':'recipient_extended_rest'}.items())):
            raise ValueError('trained stat lost its actual source, recipient or training owner')
        session_id=row.get('session')
        session=owner.custom_conditions.get('_training_sessions',{}).get(session_id,{}) if type(session_id) is str else {}
        expected={'pokemon_id':actor.entity_id,'stat':stat,'source':source,'source_clause_id':row['source_clause_id']}
        if (session.get('request_id')!=session_id or session.get('trainer')!=owner.entity_id
                or session.get('trained_stat_sources',[]).count(expected)!=1):
            raise ValueError('trained stat requires its actual completed training session source')
        champion=row.get('champ_acquisition')
        if champion:
            import ace_trainer as ACE_CLASS
            if (session.get('champ_acquisition')!=champion or session.get('ap_removed')!=2
                    or not any(r['request_id']==champion for r in ACE_CLASS.records(owner,ACE_CLASS.CHAMP))):
                raise ValueError('two-stat training needs the actual historical Champ acquisition and extra session drain')
        state=CS.validate(actor)
        if (state is None or state['base'].get(source)!={'source':ACE,'ends':source,'deltas':{stat:1}}
                or actor.spec[GRANTS.KEY]['effects'].get(source)!={'rows':['registry'],'listeners':[],'stages':True}):
            raise ValueError('trained stat requires its exact source-owned base stage')
    return rows


def _stat_choices(trainer, plan, clause_id, champion=None):
    import acquired_features as ACQUIRED
    import action_points as AP
    source=_ace_source(trainer.r,clause_id)
    native=__import__('ace_trainer').acquired(trainer,ACE)
    if (trainer.kind!='trainer' or not any(row['source_id']==ACE for row in ACQUIRED.class_instances(trainer))
            or (native is None and SKILL.rank(trainer.r,trainer,'명령')[2]<3)):
        raise ValueError('Ace Trainer requires actual class acquisition and Novice Command')
    if source['requires_training_feat'] and not any('훈련' in trainer.r.selection.units[row['source_id']].get('tags',[])
            for row in ACQUIRED.feature_instances(trainer)):
        raise ValueError('C03-123 requires an actual acquired Training feature')
    if AP.available(trainer)<1+bool(champion):raise ValueError('Ace Trainer and selected Champ require available session AP to drain')
    for target,_ in plan:
        for old in validate_trained(target):GRANTS.preflight_revoke(target,old[GRANTS.TAG])


def _grant_stats(engine, trainer, targets, trained_stats, clause_id, request_id, champion=None):
    import combat_stage_sources as CS
    applied=[]
    for target in targets:
        for old in list(stat_records(target)):GRANTS.revoke(target,old[GRANTS.TAG],engine=engine)
        chosen=trained_stats[target.entity_id]
        for stat in ([chosen] if type(chosen)is str else chosen):
            source='trained-stat:'+trainer.entity_id+':'+request_id+':'+target.entity_id+(':'+stat if champion else '')
            GRANTS._source(target,source,TRAINED_STAT,owner_id=trainer.entity_id,rule_id=ACE,
                source_clause_id=clause_id,stat=stat,lifetime='recipient_extended_rest',tutor_points=0)
            row={'type':TRAINED_STAT,'owner':trainer,'stat':stat,'source_clause_id':clause_id,'session':request_id}
            if champion:row['champ_acquisition']=champion
            GRANTS.apply_owned(engine,target,source,lambda target=target,row=row:target.registry.append(row))
            CS.add_base(target,source,stat,1,source=ACE,ends=source)
            target.spec[GRANTS.KEY]['effects'][source]['stages']=True
            applied.append({'pokemon_id':target.entity_id,'stat':stat,'source':source,'source_clause_id':clause_id})
    return applied


def train(engine, trainer, choices, *, minutes, reason, request_id, from_grooming=False, from_training=False, safe=None,
          trained_stats=None, source_clause_id=None):
    """Perform a real Extended training session with exact per-Pokemon choices.

    The caller supplies the GM's observation of the actual training activity,
    while the engine advances its elapsed clock and records its participants.
    """
    from resolution_transaction import request_fingerprint, replay_result
    import movement_actions as MOVEMENT
    import downtime as DT
    if not isinstance(reason, str) or not reason.strip(): raise ValueError('actual training observation reason required')
    if not isinstance(request_id, str) or not request_id.strip(): raise ValueError('training request identity required')
    C.integer(minutes, 'training minutes', 30)
    import pokemon_teaching as TEACHING
    TEACHING.credit_mode(from_grooming,from_training)
    has_stats=trained_stats is not None
    plan = _declared_targets(engine, trainer, choices,allow_empty=has_stats)
    if has_stats:
        import ace_trainer as ACE_CLASS
        # Shape is checked before replay; historical completed sessions remain
        # replayable after a Feature is withdrawn, as ordinary training does.
        if type(trained_stats)is not dict:raise ValueError('actual trained stat choices required')
    elif source_clause_id is not None:raise ValueError('Ace Trainer source requires selected trained stats')
    payload = {'trainer': trainer.entity_id, 'targets': [(p.entity_id, uids) for p, uids in plan], 'minutes': minutes, 'reason': reason}
    if has_stats:payload.update(trained_stats=dict(trained_stats),source_clause_id=source_clause_id)
    if from_grooming:payload['from_grooming']=True
    if from_training:payload['from_training']=True
    if safe is not None:payload['safe']=safe
    signature = request_fingerprint(payload)
    prior = replay_result(trainer.custom_conditions.get('_training_sessions', {}),request_id,payload,fingerprint_field='payload_sha256')
    if prior is not None:return prior
    if engine.encounter_active: raise ValueError('Extended training must occur outside combat')
    MOVEMENT.boundary(engine, 'training_feature')
    plan = _targets(engine, trainer, choices,allow_empty=has_stats)
    champion=None
    if has_stats:
        champion=ACE_CLASS.trained_stat_choices(trainer,trained_stats,[p for p,_ in plan])
        _stat_choices(trainer,plan,source_clause_id,champion)
    import training_eligibility as E
    eligibility=E.prepare(engine,trainer,[p for p,_ in plan],E.native('training_regime',seconds=minutes*60),
                          safe=safe,from_grooming=from_grooming,from_training=from_training)
    credits=eligibility['completed_training_credits']
    if not (from_grooming or from_training):
        engine.preflight_advance_time(minutes * 60, [trainer, *[p for p, _ in plan]])
    def apply(e, owner, *targets):
        if not TURN.spend(e, owner, 'extended', 'training features'): raise ValueError('Extended training action is unavailable')
        if has_stats:
            import action_points as AP
            AP.charge(owner,1,mode='drain')
            if champion:
                import action_lifecycle as ACTION
                ACTION.triggered_free_action(e,owner,ACE_CLASS.CHAMP)
                AP.charge(owner,1,mode='drain')
        started = e.elapsed_seconds
        for actor in (owner, *targets): DT.interrupt_rest(actor)
        if not (from_grooming or from_training):
            import activity_jobs as JOBS
            JOBS.run_fixed(e,owner,targets,seconds=minutes*60,source='training/features',
                context={'safe':True,'reason':reason},job_id='training-regime:'+owner.entity_id+':'+request_id)
        import training_rewards as REWARDS
        applied=REWARDS.grant_regimes(e,owner,targets,plan,request_id=request_id,started_at=started)
        receipt = {**payload, 'request_id': request_id, 'payload_sha256': signature, 'started_at': started,
                   'completed_at': e.elapsed_seconds, 'target_ids': [p.entity_id for p in targets], 'sources': applied,'eligibility':deepcopy(eligibility)}
        if has_stats:
            receipt['trained_stat_sources']=_grant_stats(e,owner,targets,trained_stats,source_clause_id,request_id,champion)
            receipt['ap_removed']=1+bool(champion)
            if champion:receipt['champ_acquisition']=champion
        if from_grooming or from_training:
            for target in targets:TEACHING.consume_credit(target,'training_regime',**({'from_training':True} if from_training else {}))
            receipt.update(time_cost_seconds=0,completed_training_credits=deepcopy(credits))
        owner.custom_conditions.setdefault('_training_sessions', {})[request_id] = receipt
        e.gm._rec('Training session', None, deepcopy(receipt), reason, owner)
        return deepcopy(receipt)
    return GRANTS.transition(engine, trainer, apply, participants=[p for p, _ in plan])

def extended_rest(engine, trainer):
    # Ace training belongs to the recipient's rest, independently of trainer AP recovery.
    for row in list(stat_records(trainer)):
        GRANTS.revoke(trainer,row[GRANTS.TAG],engine=engine)
    # Target rest alone does not end a trainer-owned training session.
    for target in engine.time_actors():
        for row in list(records(target)):
            if row.get('owner') is trainer and row.get('mode')=='training':
                GRANTS.revoke(target, row[GRANTS.TAG], engine=engine)


CORE_PAYMENTS='_training_core_order_payments'


def order_source(rules,uid,edition):
    """Select the printed cost without changing the acquired Training Feature."""
    import source_context as S,commander as COMMANDER
    from pathlib import Path
    from hashlib import sha256
    if edition=='local_csv':
        S.verified_source(rules,{'file':'input/db/feats.csv','sha256':__import__('commander_orders').CSV_SHA})
        return {'edition':edition,'file':'input/db/feats.csv','sha256':__import__('commander_orders').CSV_SHA,
                'clause_id':CSV_CLAUSES[uid],'action':'priority_limited_standard'}
    if edition!='core':raise ValueError('explicit Core or local CSV Training Order source required')
    file='output/source-audit/2026-10-10/ptu-core-1.05.pdf'
    if sha256((Path(rules.root)/file).read_bytes()).hexdigest()!=COMMANDER.CORE_SHA:
        raise ValueError('actual Core Training Orders source changed')
    return {'edition':'core','file':file,'sha256':COMMANDER.CORE_SHA,'pages':[60,60],
            'clause_id':file+':p60','action':'standard'}


def core_payments(owner):
    return owner.custom_conditions.get(CORE_PAYMENTS,[])


def core_payment(owner,payment_id):
    import trainer_feature_acquisition as TFA
    rows=[r for r in core_payments(owner) if r['id']==payment_id]
    if len(rows)!=1:raise ValueError('actual Core Training Order Standard payment required')
    row=rows[0]
    fields={'id','issuer_id','feature','target_id','source','at','round','turn','encounter',
            'action','commander_activation','free_order_payment','communication','integrity'}
    if (set(row)!=fields or row['integrity']!=TFA._digest('training-core-order/v1',{k:v for k,v in row.items() if k!='integrity'})
            or row['issuer_id']!=owner.entity_id or row['feature'] not in RULES
            or row['source']!=order_source(owner.r,row['feature'],'core')
            or row['action'] not in ('standard','free')
            or row['action']=='free' and row['free_order_payment'] is None and row['commander_activation'] is None):
        raise ValueError('Core Training Order payment or actual source changed')
    return row


def pay_core_order(engine,owner,target,uid,communication):
    import commander as COMMANDER,order_actions as ORDERS,trainer_feature_acquisition as TFA
    scope=COMMANDER.scope(engine,owner,uid,target)
    history=len(getattr(owner,'_action_history',[]))
    if not TURN.spend(engine,owner,'standard',uid):raise ValueError('Core Training Order Standard action unavailable')
    actions=getattr(owner,'_action_history',[])[history:]
    if len(actions)!=1 or actions[0] not in ('standard','free'):raise ValueError('actual Training Order action recording required')
    row={'id':'training-core-order:'+owner.entity_id+':'+str(len(core_payments(owner))+1),
         'issuer_id':owner.entity_id,'feature':uid,'target_id':target.entity_id,
         'source':order_source(engine.r,uid,'core'),'at':engine.elapsed_seconds,'round':engine.round_no,
         'turn':owner.custom_conditions.get('combat_turn_serial',0),'encounter':engine._party_encounter_epoch,
         'action':actions[0],'commander_activation':None if scope is None else scope['activation']['id'],
         'free_order_payment':ORDERS.payment(engine,owner,uid),'communication':deepcopy(communication)}
    row['integrity']=TFA._digest('training-core-order/v1',row)
    owner.custom_conditions.setdefault(CORE_PAYMENTS,[]).append(row)
    return deepcopy(row)


def validate_core_payments(engine,index):
    for owner in index.values():
        for serial,payment in enumerate(core_payments(owner),1):
            row=core_payment(owner,payment.get('id'))
            if row['id']!='training-core-order:'+owner.entity_id+':'+str(serial) or row['target_id'] not in index:
                raise ValueError('Core Training Order actual issuer sequence or target changed')
            C.integer(row['at'],'Core Training Order time',0,engine.elapsed_seconds)
            C.integer(row['round'],'Core Training Order round',0,engine.round_no)
            C.integer(row['turn'],'Core Training Order actual turn',0,owner.custom_conditions.get('combat_turn_serial',0))
            C.integer(row['encounter'],'Core Training Order encounter',1,engine._party_encounter_epoch)
            if row['commander_activation'] is not None:
                import commander as COMMANDER
                activations=[a for a in owner.spec.get(COMMANDER.ACTIVATIONS,[]) if a['id']==row['commander_activation']]
                if (len(activations)!=1 or activations[0]['integrity']!=COMMANDER._seal(activations[0])
                        or {'target_id':row['target_id'],'feature':row['feature']} not in activations[0]['orders']):
                    raise ValueError('Core Training Order lost its actual Commander activation')
            if row['free_order_payment'] is not None:
                __import__('order_actions').validate(engine,owner,index[row['target_id']],row['feature'],row['free_order_payment'])


def orders(engine, trainer, name, target, *, edition='local_csv', communication=None):

    """Issue one native Training Order with its selected printed action cost."""
    import world_entities as WORLD
    import pokemon_activities as ACTIVITIES
    import priority_limited as PRIORITY
    import perception_communicate as COMM
    import combat_timing as TIMING
    import order_actions as ORDERS
    communication_request=communication
    uid=identity(name)
    if uid is None: raise ValueError('known training feature required')
    if edition=='core':
        selected_source=order_source(engine.r,uid,edition);binding=None
        values={'self_target':False,'source_clause_id':selected_source['clause_id']}
    elif edition=='local_csv':
        binding=selected_order(engine.r,name);values=binding['definition']['values']
        selected_source={'clause_id':values['source_clause_id'],'action':'standard'}
    else:raise ValueError('explicit Core or local CSV Training Order source required')
    WORLD.require_actors(engine,trainer,target)
    ACTIVITIES._trainer(trainer)
    if not owns(trainer,uid,order_binding=binding):raise ValueError('trainer does not own selected training feature')
    if target is trainer and not values['self_target']:
        raise ValueError('book Training Order cannot target its issuer')
    if target is not trainer:
        import commander as COMMANDER
        if not (COMMANDER.transformed_target(engine,trainer,target) or COMMANDER.leadership_target(engine,trainer,target)):
            ACTIVITIES._pokemon(target);ACTIVITIES._owner(trainer,target)
        if target.dead or target.fainted:raise ValueError('conscious order recipient required')
    commander_scope=__import__('commander').scope(engine,trainer,uid,target)
    if edition=='local_csv' and ORDERS.current(engine,trainer,uid) is None and not (commander_scope or {}).get('priority_receipt') and not (commander_scope or {}).get('voice'):
        if not engine.encounter_active:PRIORITY.preflight(engine,trainer,action='standard',source=uid)
        ORDERS.preflight(engine,trainer,uid,action=__import__('commander').priority_action(engine,trainer,uid))
    if any(row.get('mode')=='orders' for row in records(target)):
        raise ValueError('target already has a live Training Order')
    def apply(e,owner,recipient):
        if recipient is owner:
            if communication_request is not None:raise ValueError('self-target Order has no external communication request')
            communication={'status':'delivered','mode':'self_target_exception','source_clause_id':values['source_clause_id'],
                           'sender_id':owner.entity_id,'recipient_id':recipient.entity_id}
        elif communication_request is not None:
            communication=ORDERS.delivery(e,owner,recipient,uid,communication=communication_request)
        else:
            policy={'id':'training-order:'+uid,'source':uid,'capabilities':[],'requirements':[],
                    'mode':'auditory','range':None,'path':'auditory','medium':[],
                    'consent':{'kind':'none'},'blockers':[],'connection':None,
                    'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
            state=getattr(e,COMM.KEY,{'attempts':[]})
            request='training-order:'+owner.entity_id+':'+str(len(state.get('attempts',[]))+1)
            communication=COMM.send(e,owner,recipient,policy,'Training Order: '+uid,request_id=request)
            if communication['status']!='delivered':
                raise ValueError('Training Order communication was not delivered: '+str(communication.get('reason')))
        ordinary=None
        commander_payment=__import__('commander').training_payment(e,owner,recipient,uid,communication,edition=edition)
        if commander_payment is not None:
            free=None;receipt=commander_payment
        elif edition=='core':
            receipt=pay_core_order(e,owner,recipient,uid,communication);free=receipt['free_order_payment']
        elif ORDERS.current(e,owner,uid) is not None:
            import turn as TURN
            if not TURN.spend(e,owner,'standard',uid):raise ValueError('Free Training Order permission required')
            free=ORDERS.payment(e,owner,uid)
            receipt={'id':'free-order:'+free['parent'],'payment':free}
        else:
            free=None
            receipt=ORDERS.spend(e,owner,uid,subject=recipient.entity_id,communication=communication)
            if receipt.get('kind')=='ordinary':
                ordinary=receipt
                receipt={'id':'training-order:'+owner.entity_id+':'+str(owner.custom_conditions.get('_training_order_serial',0)+1),'payment':ordinary}
        serial=C.integer(owner.custom_conditions.get('_training_order_serial',0),'Training Order serial',0)+1
        owner.custom_conditions['_training_order_serial']=serial
        source='training-order:'+owner.entity_id+':'+str(serial)+':'+recipient.entity_id+':'+uid
        GRANTS._source(recipient,source,'training_order',owner_id=owner.entity_id,
                       lifetime='start_of_issuer_next_turn',rule_id=uid,tutor_points=0,
                       **({'source_clause_id':values['source_clause_id'],'source_policy_binding':binding} if binding is not None else {}))
        if free is not None:GRANTS.state(recipient)['sources'][source]['free_order_payment']=deepcopy(free)
        if edition=='core':GRANTS.state(recipient)['sources'][source]['core_order_payment']=receipt['id']
        row={'type':TYPE,'rule_id':uid,'source_clause_id':selected_source['clause_id'],'mode':'orders','owner':owner,
             'order_id':receipt['id'],'elite_authority':False,'started_at':e.elapsed_seconds,
             'started_round':e.round_no}
        if binding is not None:row['source_policy_binding']=deepcopy(binding)
        if edition=='core':row['order_source']=deepcopy(selected_source)
        if free is not None:row['free_order_payment']=free
        if ordinary is not None:
            row['ordinary_order_payment']=deepcopy(ordinary)
            GRANTS.state(recipient)['sources'][source]['ordinary_order_payment']=deepcopy(ordinary)
        GRANTS.apply_owned(e,recipient,source,lambda row=row,recipient=recipient:recipient.registry.append(row))
        deadline=C.integer(owner.custom_conditions.get('combat_turn_serial',0),'actual owner turn serial',0)+1
        TIMING.install(e,recipient,{'source':uid,'effect_contract':True,'grant_source':source,
                                    'turn_owner':owner,'turn_start_deadline':deadline})
        result={'status':'applied','rule_id':uid,'source_clause_id':selected_source['clause_id'],
                'source':source,'trainer_id':owner.entity_id,'target_id':recipient.entity_id,
                'expires_at_owner_turn':deadline,
                'communication':deepcopy(communication)}
        result['core_standard_payment' if edition=='core' else 'priority_receipt']=deepcopy(receipt)
        if edition=='core':result['order_source']=deepcopy(selected_source)
        if binding is not None:result['source_policy_binding']=deepcopy(binding)
        import trainer_feature_acquisition as ACQUISITION
        owner.spec.setdefault('training_order_uses',[]).append({
            'result':deepcopy(result),'integrity':ACQUISITION._digest('training-order/use/v1',result)})
        e.gm._rec('Training Order',None,result,'actual delivered Order',owner)
        import cheerleader as CHEER
        if __import__('commander').scope(e,owner) is None:CHEER.after_training(e,owner,recipient,result)
        import duelist as DUELIST
        if __import__('commander').scope(e,owner) is None:DUELIST.after_order(e,owner,[recipient],{'kind':'training','receipt_id':receipt['id']})
        return deepcopy(result)
    return GRANTS.transition(engine,trainer,apply,participants=(target,),include_rulings=True)
