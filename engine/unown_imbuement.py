"""Explicit Unown sample, sharing native Move, action, scene and hit owners.

Clusters are a source-attached reservoir, not actors, learned Moves or another
clock. The actual native activation burns them; previews never consume them.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json

import common_checks as CHECKS
import resolution_transaction as TX
import source_selection as SELECT

KEY = 'unown_imbuement'
SOURCE = 'ch11-running-the-game/보스-인카운터/특별한-보스-파워'
SOURCE_FILE = {'file': 'input/ch11-running-the-game.md',
               'sha256': '5311a50a2c70748465fe6fd73b52a8abbf337a11791509d88a15e19295232dad'}
HP = 'move/잠재파워'
DETECT = 'move/판별'
AMOUNTS = {'hidden_power': 1, 'accuracy': 2, 'detect': 3}
SHIELD = {'type': 'reaction_shield', 'trigger': 'user hit by a move', 'effect': 'negate hit'}
POLICY = 'data/core-unown-imbuement-policy.json'


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')
    return value.strip()


def policy(rules):
    from source_context import verified_source
    local = Path(__file__).resolve().parents[1] / POLICY
    path = local if local.exists() else Path(rules.root) / POLICY
    data = json.loads(path.read_text(encoding='utf-8'))
    expected = {'schema_version': 1, 'source': SOURCE, 'source_file': SOURCE_FILE,
                'lines': [2394, 2398], 'clauses': ['C11-143', 'C11-144'],
                'clusters': [1, 5], 'passive': {'accuracy': 1, 'evasion': 1},
                'burns': AMOUNTS, 'frequency': 'native_move_unchanged',
                'exhaustion': 'actual_scene', 'accuracy_selection': 'one_explicit_native_activation',
                'hidden_power': {'move_id': HP, 'action': 'swift', 'classes': ['물리', '특수'], 'type': 'per_use'},
                'detect': {'move_id': DETECT, 'action': 'free', 'trigger': 'actual_native_move_hit', 'effect': SHIELD}}
    if data != expected:
        raise ValueError('reviewed Unown Imbuement policy changed')
    SELECT.select(rules, SOURCE, source=SOURCE_FILE)
    verified_source(rules, SOURCE_FILE, label='Unown Imbuement')
    rulings = getattr(rules, 'rulings', None)
    if rulings and (rulings.effects.get(SOURCE) or rulings.mech.get(SOURCE)):
        raise ValueError('overridden Unown sample requires its own adapter')
    return data


def _scene(actor):
    import frequency as FREQ
    return FREQ.state(actor)['scene']


def state(actor):
    row = actor.spec.get(KEY)
    if row is None:
        return None
    policy(actor.r)
    if (actor.kind not in ('pokemon', 'trainer') or type(row) is not dict
            or set(row) != {'version', 'adoption', 'burns'} or row['version'] != 1
            or type(row['burns']) is not list):
        raise ValueError('actual actor-owned Unown reservoir required')
    adoption = row['adoption']
    if (type(adoption) is not dict or set(adoption) != {'actor_id', 'source', 'source_file', 'clusters',
            'gm_id', 'reason', 'at', 'scene', 'active'} or adoption['actor_id'] != actor.entity_id
            or adoption['source'] != SOURCE or adoption['source_file'] != SOURCE_FILE
            or type(adoption['active']) is not bool):
        raise ValueError('Unown adoption source or actual identity changed')
    CHECKS.integer(adoption['clusters'], 'implanted Unown Clusters', 1, 5)
    CHECKS.integer(adoption['at'], 'Unown adoption time', 0)
    CHECKS.integer(adoption['scene'], 'Unown adoption scene', 0, _scene(actor))
    _text(adoption['gm_id'], 'actual GM'); _text(adoption['reason'], 'Unown adoption reason')
    ids = set(); spent = {}
    for burn in row['burns']:
        if (type(burn) is not dict or set(burn) != {'id', 'intent', 'fingerprint', 'phase', 'at',
                'completion_ids', 'result'} or burn['phase'] not in ('prepared', 'used', 'complete')):
            raise ValueError('typed actual Unown use receipt required')
        identity = _text(burn['id'], 'Unown request identity')
        if identity in ids:
            raise ValueError('duplicate Unown use receipt')
        ids.add(identity)
        intent = burn['intent']
        if (type(intent) is not dict or set(intent) != {'actor_id', 'scene', 'mode', 'amount', 'move_id',
                'primary_id', 'target_ids', 'options', 'reason', 'source_file', 'trigger'}
                or intent['actor_id'] != actor.entity_id or intent['source_file'] != SOURCE_FILE
                or intent['mode'] not in AMOUNTS or intent['amount'] != AMOUNTS[intent['mode']]
                or type(intent['amount']) is not int
                or burn['fingerprint'] != TX.request_fingerprint(intent)):
            raise ValueError('Unown use source, mode or request changed')
        CHECKS.integer(intent['scene'], 'Unown use scene', adoption['scene'], _scene(actor))
        CHECKS.integer(burn['at'], 'Unown use time', adoption['at'])
        _text(intent['reason'], 'Unown use reason')
        _text(intent['move_id'], 'actual native Move')
        if (type(intent['target_ids']) is not list or not intent['target_ids']
                or len(set(intent['target_ids'])) != len(intent['target_ids'])
                or intent['primary_id'] not in intent['target_ids']):
            raise ValueError('actual Unown native candidate identities required')
        for uid in intent['target_ids']:
            _text(uid, 'actual native candidate')
        if type(burn['completion_ids']) is not list or len(set(burn['completion_ids'])) != len(burn['completion_ids']):
            raise ValueError('unique native completion identities required')
        if intent['mode'] == 'hidden_power':
            if intent['move_id'] != HP or set(intent['options']) != {'chosen_type', 'damage_class'}:
                raise ValueError('exact source-granted Hidden Power choice required')
            if intent['options']['damage_class'] not in ('물리', '특수'):
                raise ValueError('Hidden Power chooses Physical or Special')
            import type_state as TYPES
            TYPES.validate_types(actor.r, [intent['options']['chosen_type']])
        elif intent['mode'] == 'accuracy':
            if intent['options'] or intent['move_id'] not in actor.r.moves:
                raise ValueError('one selected actual attack required')
        elif (intent['move_id'] != DETECT or intent['options'] or type(intent['trigger']) is not str):
            raise ValueError('Detect requires its actual native hit trigger')
        if intent['mode'] != 'detect' and intent['trigger'] is not None:
            raise ValueError('ordinary Unown use cannot invent a hit trigger')
        if burn['phase'] != 'prepared':
            if not burn['completion_ids']:
                raise ValueError('burned groups lack actual Move activation')
            spent[intent['scene']] = spent.get(intent['scene'], 0) + intent['amount']
        elif burn['completion_ids'] or burn['result'] is not None:
            raise ValueError('unactivated Unown choice cannot contain a result')
        if burn['phase'] == 'complete' and type(burn['result']) is not int:
            raise ValueError('completed native Unown use needs its actual return')
    if any(amount > adoption['clusters'] for amount in spent.values()):
        raise ValueError('Unown Cluster reservoir overdrawn')
    return row


def active_count(actor):
    row = state(actor)
    if row is None or not row['adoption']['active']:
        return 0
    return row['adoption']['clusters'] - sum(b['intent']['amount'] for b in row['burns']
        if b['phase'] != 'prepared' and b['intent']['scene'] == _scene(actor))


def adopt(engine, actor, clusters, *, gm_id, reason):
    import world_entities as WORLD, state_grants as GRANTS
    WORLD.require_actors(engine, actor); policy(engine.r)
    CHECKS.integer(clusters, 'implanted Unown Clusters', 1, 5)
    _text(gm_id, 'actual GM'); _text(reason, 'Unown adoption reason')
    if actor.kind not in ('pokemon', 'trainer') or state(actor) is not None:
        raise ValueError('new explicit actual Pokemon or Trainer Unown adoption required')
    def apply(e, a):
        a.spec[KEY] = {'version': 1, 'adoption': {'actor_id': a.entity_id, 'source': SOURCE,
            'source_file': deepcopy(SOURCE_FILE), 'clusters': clusters, 'gm_id': gm_id,
            'reason': reason, 'at': e.elapsed_seconds, 'scene': _scene(a), 'active': True}, 'burns': []}
        return deepcopy(state(a)['adoption'])
    return GRANTS.transition(engine, actor, apply)


def set_active(engine, actor, active, *, reason):
    import world_entities as WORLD, state_grants as GRANTS
    WORLD.require_actors(engine, actor); _text(reason, 'Unown sample activation reason')
    if type(active) is not bool or state(actor) is None:
        raise ValueError('existing actual Unown adoption and Boolean required')
    def apply(e, a):
        a.spec[KEY]['adoption']['active'] = active
        return active_count(a)
    return GRANTS.transition(engine, actor, apply)


def _native(rules, mid):
    if mid not in rules.moves or rules._selected_rule(mid) != mid:
        raise ValueError('exact selected native Unown Move required')
    move = rules.move(mid); mm = rules.move_mech(mid)[0]
    effects = [{k: v for k, v in x.items() if not k.startswith('_')} for x in mm.get('effects_exec', [])]
    if mid == HP:
        if (move['damage_base'] != 6 or move['ac'] != 2 or move['range'] != '파열 1'
                or len(effects) != 1 or effects[0].get('type') != 'random_type_on_learn'):
            raise ValueError('native Hidden Power definition changed')
    elif mid == DETECT and effects != [SHIELD]:
        raise ValueError('native Detect effect changed')
    return move, mm


def _scope(engine, actor, mid=None):
    scope = getattr(engine, '_unown_imbuement_scope', None)
    if scope is None:
        # A saved native target group may resume after the original public
        # producer returned a wait. Its verified completion remains the same
        # use; copied request data alone can never authorize a new attack.
        if not getattr(engine,'_resuming_move_activation',False):
            return None
        import move_activation as ACTIVATION
        for group in reversed(getattr(engine,'_move_activation_scopes',())):
            if group['actor'] is not actor or not 0 < group['index'] <= len(group['targets']):
                continue
            target=group['targets'][group['index']-1]
            if ACTIVATION.current_scope(engine,actor,target,group['move_id']) is not group:
                continue
            completion=getattr(engine,'_move_completions',{}).get(group.get('completion_id'))
            row=state(actor)
            identity=None if completion is None else completion['move'].get('_unown_use')
            use=next((b for b in (row or {}).get('burns',[]) if b['id']==identity),None)
            if (use and use['phase']=='used' and use['completion_ids']==[group['completion_id']]
                    and completion['actor'] is actor and group['move_id']==use['intent']['move_id']):
                scope={'actor':actor,'id':use['id'],'fingerprint':use['fingerprint']}
                break
        if scope is None:
            return None
    if scope['actor'] is not actor:
        return None
    row = state(actor)
    use = next((b for b in row['burns'] if b['id'] == scope['id']), None)
    if (use is None or use['fingerprint'] != scope['fingerprint']
            or use['intent']['scene'] != _scene(actor) or not row['adoption']['active']):
        raise ValueError('actual Unown use authority changed')
    if mid is not None and use['intent']['move_id'] != mid:
        return None
    return use


@contextmanager
def _using(engine, actor, use):
    if getattr(engine, '_unown_imbuement_scope', None) is not None:
        raise ValueError('one actual source-selected attack at a time')
    engine._unown_imbuement_scope = {'actor': actor, 'id': use['id'], 'fingerprint': use['fingerprint']}
    try:
        yield
    finally:
        del engine._unown_imbuement_scope


def prepare(engine, actor, move):
    use = _scope(engine, actor, move['id'])
    if use is None:
        return move
    if use['intent']['mode'] != 'hidden_power':
        return dict(move,_unown_use=use['id'])
    _native(engine.r, HP)
    options = use['intent']['options']
    return dict(move, type=options['chosen_type'], **{'class': options['damage_class']},
                range='파열 1, 신속 행동', _unown_use=use['id'])


def mechanics(engine, actor, move, mm):
    use = _scope(engine, actor, move['id'])
    if use is None or use['intent']['mode'] != 'hidden_power':
        return mm
    _native(engine.r, HP)
    # The selected sample explicitly replaces permanent random-on-learn Type
    # with this use's chosen Type; do not dispatch the explanatory learn prompt.
    return dict(mm, effects_exec=[x for x in mm.get('effects_exec', [])
                                  if x.get('type') != 'random_type_on_learn'])


def begin_move_use(engine, actor, target, move, completion_id):
    use = _scope(engine, actor, move['id'])
    if use is None:
        return
    import move_completion as COMPLETE
    completion = getattr(engine, COMPLETE.KEY, {}).get(completion_id)
    if (completion is None or completion['actor'] is not actor or completion['move_id'] != move['id']
            or target.entity_id not in completion['started'] or target not in completion['targets']):
        raise ValueError('Unown burn requires its actual native Move activation')
    if use['phase'] == 'prepared':
        if active_count(actor) < use['intent']['amount']:
            raise ValueError('insufficient active Unown Clusters')
        use['phase'] = 'used'
    if completion_id not in use['completion_ids']:
        if use['completion_ids']:
            raise ValueError('one Unown burn cannot authorize two native attacks')
        use['completion_ids'].append(completion_id)


def accuracy_bonus(engine, actor, target, move):
    use = _scope(engine, actor, move['id'])
    if use is None or use['intent']['mode'] != 'accuracy':
        return 0
    if use['phase'] not in ('used', 'complete') or not use['completion_ids']:
        raise ValueError('Unown accuracy purchase lacks native activation')
    import move_activation as ACTIVATION
    scope = ACTIVATION.current_scope(engine, actor, target, move['id'])
    if scope is not None and scope.get('completion_id') != use['completion_ids'][0]:
        raise ValueError('Unown accuracy belongs to another actual activation')
    row = getattr(engine,'_move_completions',{}).get(use['completion_ids'][0])
    if row is None or target not in row['targets'] or target.entity_id not in row['started']:
        raise ValueError('Unown accuracy belongs to another actual target')
    return 5


def _intent(actor, mode, mid, primary, everyone, options, reason, trigger=None):
    return {'actor_id': actor.entity_id, 'scene': _scene(actor), 'mode': mode, 'amount': AMOUNTS[mode],
            'move_id': mid, 'primary_id': primary.entity_id, 'target_ids': [a.entity_id for a in everyone],
            'options': deepcopy(options), 'reason': _text(reason, 'Unown use reason'),
            'source_file': deepcopy(SOURCE_FILE), 'trigger': trigger}


def _receipt(engine, actor, request_id, intent):
    row = state(actor)
    if row is None or not row['adoption']['active']:
        raise ValueError('actual active adopted Unown sample required')
    _text(request_id, 'Unown use request ID')
    old = next((b for b in row['burns'] if b['id'] == request_id), None)
    if old is not None:
        # Scene is an observed use fact, not a caller option. A delivered
        # request retains its original Scene when redelivered later.
        intent['scene'] = old['intent']['scene']
        TX.replay_result({old['id']:old},request_id,intent,fingerprint_field='fingerprint')
        _complete_returned(engine,actor,old)
        if old['phase'] != 'complete':
            raise ValueError('Unown use has not completed its native attack')
        return old
    if active_count(actor) < intent['amount']:
        raise ValueError('insufficient active Unown Clusters')
    return None


def _new(actor, request_id, intent, at):
    use = {'id': request_id, 'intent': deepcopy(intent),
           'phase': 'prepared', 'at': at, 'completion_ids': [], 'result': None}
    TX.bind_request_intent(use,intent,field='fingerprint')
    actor.spec[KEY]['burns'].append(use)
    return use


def _complete_returned(engine, actor, use):
    if use['phase'] != 'used':
        return
    rows = [getattr(engine,'_move_completions',{}).get(key) for key in use['completion_ids']]
    if rows and all(row and row['actor'] is actor and row['phase'] == 'complete' for row in rows):
        use['result'] = sum(result['dealt'] for row in rows for result in row['results'].values())
        use['phase'] = 'complete'


def _attack(engine, actor, primary, everyone, mode, mid, options, request_id, reason):
    import world_entities as WORLD, state_grants as GRANTS, turn as TURN
    WORLD.require_actors(engine, actor, primary, *everyone)
    if (type(everyone) not in (list, tuple) or not everyone or primary not in everyone
            or len({a.entity_id for a in everyone}) != len(everyone)):
        raise ValueError('distinct actual native candidate group including primary required')
    mid = engine.r.move_id(mid)
    if mid is None:
        raise ValueError('selected actual native attack required')
    if mode == 'hidden_power':
        _native(engine.r, HP)
        import type_state as TYPES
        TYPES.validate_types(engine.r, [options['chosen_type']])
        if options['damage_class'] not in ('물리', '특수'):
            raise ValueError('Hidden Power chooses Physical or Special')
    elif engine.r.move(mid)['class'] not in ('물리', '특수'):
        raise ValueError('two-Cluster Accuracy applies to an actual attack')
    intent = _intent(actor, mode, mid, primary, everyone, options, reason)
    old = _receipt(engine,actor,request_id,intent)
    if old is not None:
        return old['result']
    ids = tuple(a.entity_id for a in everyone); primary_id = primary.entity_id
    pending = []
    def apply(e, a):
        index = WORLD.actor_index(e); target = index[primary_id]
        use = _new(a, request_id, intent, e.elapsed_seconds)
        if mode == 'accuracy' and not TURN.spend(e, a, 'swift', 'Unown Accuracy'):
            raise ValueError('Unown Accuracy requires its actual Swift action')
        with _using(e, a, use):
            try:
                result = e.use_move_on(a,target,mid,[index[uid] for uid in ids])
            except Exception as error:
                import passive_events as PASSIVE, heavy_injury_adapter as HEAVY
                if (type(error) is PASSIVE.PassiveEventPending and e._passive_pending == error.event_id
                        and error.event_id in e._passive_events):
                    pending.append((PASSIVE.PassiveEventPending,error.event_id)); result = None
                elif (type(error) is HEAVY.HeavyPending and e._heavy_pending == error.event_id
                        and error.event_id in e._heavy_events):
                    pending.append((HEAVY.HeavyPending,error.event_id)); result = None
                else:
                    raise
        if use['phase'] != 'used':
            raise ValueError('native Unown attack was unavailable before activation')
        if not pending:
            use['phase'] = 'complete'; use['result'] = result
        state(a)
        return result
    result = GRANTS.transition(engine,actor,apply,include_grid=engine.grid is not None,include_rulings=True)
    if pending:
        exception,event_id = pending[0]
        raise exception(event_id)
    return result


def use_hidden_power(engine, actor, primary, everyone, *, chosen_type, damage_class, request_id, reason):
    return _attack(engine, actor, primary, everyone, 'hidden_power', HP,
                   {'chosen_type': chosen_type, 'damage_class': damage_class}, request_id, reason)


def boost_attack(engine, actor, primary, move_id, everyone, *, request_id, reason):
    return _attack(engine, actor, primary, everyone, 'accuracy', move_id,
                   {},request_id,reason)


def watch_detect(engine, actor, *, reason):
    """Choose the existing native defense route; a watch is no asserted hit."""
    import move_defense_reactions as DEFENSE
    preflight_detect(engine, actor)
    return DEFENSE.watch(engine, actor, [{'actor_id': actor.entity_id, 'source': SOURCE}], reason=reason)


def preflight_detect(engine, actor):
    import world_entities as WORLD, frequency as FREQ
    WORLD.require_actors(engine, actor); _native(engine.r, DETECT)
    if active_count(actor) < 3:
        raise ValueError('Detect requires three active Unown Clusters')
    if not FREQ.move_allowed(engine, actor, DETECT, outside_combat=not engine.encounter_active)[0]:
        raise ValueError('native Detect frequency unavailable')
    import reactive_ability_events as REACTIVE
    if actor.abilities_suppressed or not REACTIVE._reaction_allowed(engine,actor):
        raise ValueError('native Detect reaction or Shield consumption unavailable')
    return True


def detect_actual(engine, event, actor, *, reason):
    """Existing DEFENSE continuation supplies the actual successful hit."""
    import move_defense_reactions as DEFENSE, passive_events as PASSIVE
    import move_completion as COMPLETE, action_lifecycle as ACTION
    import frequency as FREQ, effects as FX, event_effects as EVENTS
    import move_activation as ACTIVATION
    state_row = DEFENSE._defense(engine,event)
    if (state_row is None or engine._passive_events.get(event['id']) is not event
            or event['target'] is not actor or event.get('hit') is not True
            or event['phase'] != 'accuracy_boundary' or engine._passive_pending is not None
            or state_row['phase'] != 'choices'):
        raise ValueError('actual waiting successful Move hit required for Detect')
    if state_row['decisions'].get(str(state_row['cursor'])) != {'use': True, 'options': {}, 'reason': reason}:
        raise ValueError('actual selected native Detect decision required')
    request = state_row['facts']['watch']['requests'][state_row['cursor']]
    if request != {'source':SOURCE,'actor_id':actor.entity_id}:
        raise ValueError('actual selected Unown defense owner required')
    accuracy = next((o['facts'] for o in PASSIVE.observations(engine,event['id']) if o['stage']=='accuracy'),None)
    if accuracy is None or accuracy['hit'] is not True or state_row['facts']['hit'] is not True:
        raise ValueError('Detect requires the actual native accuracy observation')
    incoming = state_row['facts']['move']
    if DEFENSE._prohibited(engine,incoming,'shield'):
        raise ValueError('this actual Move bypasses native Detect Shield')
    preflight_detect(engine,actor)
    move,mm = _native(engine.r,DETECT)
    # Keep the actual selected Move, its Interrupt/Shield and effects. Only
    # the sample's Free action replaces its ordinary action cost.
    move = dict(move,range=move['range']+', 자유 행동')
    import partial_entities as PARTIAL, actor_templates as TEMPLATES
    import supplemental_state as SUPPLEMENTAL, move_permissions as PERMISSIONS
    PARTIAL.require_complete(actor,'Unown Detect')
    TEMPLATES.require_ordinary(actor,'Unown Detect')
    SUPPLEMENTAL.require_actor_access(engine,actor,'Unown Detect')
    PERMISSIONS.require_native_move(engine,actor,DETECT)
    import field_effects as FIELD, effects_ext as EXT, condition_instances as CONDITIONS
    if FIELD.move_block_reason(engine,actor,actor,move,mm) or not EXT.pre_use(engine,actor,actor,move,mm):
        raise ValueError('native Detect Move entry unavailable')
    CONDITIONS.preflight_move(engine,actor,actor,mm)
    FX.preflight_effects(engine,actor,actor,mm.get('effects_exec',[]),DETECT)
    identity = event['id']+':unown-detect:'+actor.entity_id
    intent = _intent(actor,'detect',DETECT,actor,[actor],{},reason,trigger=event['id'])
    if _receipt(engine,actor,identity,intent) is not None:
        raise ValueError('Detect already delivered for this actual hit')
    use = _new(actor,identity,intent,engine.elapsed_seconds)
    move = dict(move,_unown_use=identity)
    @ACTION.resolved_native('actor',DETECT,'move')
    @ACTIVATION.effect_contributions
    def activate(engine,actor,target,move_id):
        ACTION.triggered_free_action(engine,actor,DETECT)
        token = COMPLETE.start_target(engine,actor,target,move,mm,None)
        with _using(engine,actor,use):
            begin_move_use(engine,actor,target,move,token)
        EVENTS.begin_move_use(engine,actor,target,move,mm)
        FX.fire_event(engine,actor,{'event':'on_move_use','move':move},target)
        actor.last_move = DETECT; actor.last_target = target
        FREQ.consume_move(engine,actor,DETECT)
        result = FX.run_effects(engine,actor,target,mm['effects_exec'],
            {'move':move,'move_completion':token,'hit':True,'nat':None},DETECT)
        receipts = [outcome.receipt for outcome in result.outcomes if outcome.receipt is not None]
        if result.pending or result[0] != 1 or result[1] or len(receipts) != 1:
            raise ValueError('native Detect shield effect did not complete')
        COMPLETE.finish_target(engine,token,actor,target,hit=True,dealt=0,effects=receipts)
        return token,receipts
    token,receipts = activate(engine,actor,actor,DETECT)
    shield = deepcopy(actor.shield)
    if not DEFENSE.consume_shield(engine,event['actor'],actor,incoming,actual_hit=True):
        raise ValueError('native Detect did not consume its actual Shield')
    use['phase']='complete';use['result']=0
    return {'request_id':identity,'completion_id':token,'effect_receipt':receipts[0],'shield':shield}


def validate_detect_attempt(engine, event, actor, attempt):
    import effect_contracts as CONTRACTS
    proof = attempt.get('unown')
    if (type(proof) is not dict or set(proof) != {'request_id','completion_id','effect_receipt','shield'}
            or event['target'] is not actor or attempt.get('outcome') != 'avoided'
            or attempt.get('paid') is not True):
        raise ValueError('actual completed Unown Detect proof required')
    row = state(actor)
    use = next((b for b in row['burns'] if b['id']==proof['request_id']),None) if row else None
    completion = getattr(engine,'_move_completions',{}).get(proof['completion_id'])
    if (use is None or use['phase']!='complete' or use['intent']['mode']!='detect'
            or use['intent']['trigger']!=event['id'] or use['completion_ids']!=[proof['completion_id']]
            or completion is None or completion['actor'] is not actor or completion['move_id']!=DETECT
            or completion['phase']!='complete' or completion['targets']!=[actor]
            or completion['results']!={actor.entity_id:{'hit':True,'dealt':0,'cancelled':False}}
            or completion['effects']!=[proof['effect_receipt']]
            or proof['shield'].get('_native_shield')!={'completion_id':proof['completion_id'],
                'source_id':DETECT,'actor_id':actor.entity_id}):
        raise ValueError('Detect group burn lost its actual native completion or target')
    effect = engine._effect_dispatch_receipts.get(proof['effect_receipt'])
    if effect is None or effect['status']!='completed' or effect['effect'].get('type')!='reaction_shield':
        raise ValueError('Detect lacks its completed native effect dispatcher receipt')
    CONTRACTS.validate_receipt(engine,proof['effect_receipt'],DETECT,effect['occurrence'],actor,actor,effect['effect'])
    return True


def validate_world(engine, index):
    for actor in index.values():
        row = state(actor)
        if row is None:
            continue
        if row['adoption']['at'] > engine.elapsed_seconds:
            raise ValueError('Unown adoption belongs to future time')
        for burn in row['burns']:
            if burn['phase'] == 'prepared' and _scope(engine, actor) is not burn:
                raise ValueError('prepared Unown use lacks live native scope')
            if burn['at'] > engine.elapsed_seconds or any(uid not in index for uid in burn['intent']['target_ids']):
                raise ValueError('Unown use references future time or missing actual target')
            for token in burn['completion_ids']:
                completion = getattr(engine, '_move_completions', {}).get(token)
                if (completion is None or completion['actor'] is not actor
                        or completion['move_id'] != burn['intent']['move_id']
                        or completion['move'].get('_unown_use') != burn['id']
                        or any(t.entity_id not in burn['intent']['target_ids'] for t in completion['targets'])):
                    raise ValueError('Unown use lost its actual native completion')
                if burn['phase'] == 'complete' and completion['phase'] != 'complete':
                    raise ValueError('Unown use cannot complete before its native Move')
                if (burn['phase']=='complete' and burn['result'] !=
                        sum(result['dealt'] for result in completion['results'].values())):
                    raise ValueError('Unown replay result differs from actual native return')
            if burn['intent']['mode']=='detect' and burn['phase']=='complete':
                event=getattr(engine,'_passive_events',{}).get(burn['intent']['trigger'])
                incoming=getattr(engine,'_move_completions',{}).get(event.get('completion_id')) if event else None
                defense=incoming.get('defense',{}).get(actor.entity_id) if incoming else None
                attempts=[] if defense is None else [a for a in defense['attempts']
                    if a.get('unown',{}).get('request_id')==burn['id']]
                if len(attempts)!=1:
                    raise ValueError('Unown Detect burn lost its actual successful-hit defense')
                validate_detect_attempt(engine,event,actor,attempts[0])
    return True
