"""Focused Command's round permission; native turns and Orders keep ownership."""
from copy import deepcopy

FEATURE = 'feat/집중-명령'
VOICE = 'feat/지휘관의-목소리'
FEATURES = {VOICE: (719, 724), FEATURE: (726, 731)}
KEY = 'focused_command_activations'
AP_KEY = 'focused_command_round_payments'
PENDING = 'focused_command_next_round_ap'
FACTS = 'focused_command_round_facts'
SKILLS = ('집중', '교활', '협박', '포켓몬학')


def source(rules, feature=FEATURE, edition='core'):
    import commander as C, commander_orders as O, source_context as S
    from pathlib import Path
    from hashlib import sha256
    if feature not in FEATURES or edition not in ('core', 'local_csv'):
        raise ValueError('reviewed Focused Command or Voice source required')
    if rules._selected_rule(feature) != feature:
        raise ValueError('selected Focused Command variant needs its own source contract')
    S.verified_source(rules, {'file': 'input/ch03-skills-edges-feats.md', 'sha256': C.GENERAL_SHA})
    if edition == 'local_csv':
        S.verified_source(rules, {'file': 'input/db/feats.csv', 'sha256': O.CSV_SHA})
        return {'edition': edition, 'file': 'input/db/feats.csv', 'sha256': O.CSV_SHA,
                'record': 19 if feature == FEATURE else 18}
    file = 'output/source-audit/2026-10-10/ptu-core-1.05.pdf'
    if sha256((Path(rules.root) / file).read_bytes()).hexdigest() != C.CORE_SHA:
        raise ValueError('actual Core Focused Command source changed')
    return {'edition': edition, 'file': 'input/ch03-skills-edges-feats.md',
            'sha256': C.GENERAL_SHA, 'span': list(FEATURES[feature]),
            'interpretation': {'file': file, 'sha256': C.CORE_SHA, 'pages': [60, 60]}}


def known_orders(actor):
    import acquired_features as A
    owned={row['source_id'] for row in A.feature_instances(actor)}
    return sorted(uid for uid in owned
                  if any('지시' in tag or tag == 'Orders'
                         for tag in actor.r.selection.units[uid].get('tags', [])))


def acquisition_snapshot(engine, actor, feature):
    import skill_modifiers as S
    return {'command': S.rank(engine.r, actor, '명령')[2],
            'skills': {skill: S.rank(engine.r, actor, skill)[2] for skill in SKILLS},
            'orders': known_orders(actor) if feature == VOICE else []}


def qualification(actor, feature, snapshot, prerequisite_source):
    import acquisition_qualification as Q, common_checks as C
    if (prerequisite_source is not None or type(snapshot) is not dict
            or set(snapshot) != {'command', 'skills', 'orders'}
            or type(snapshot['skills']) is not dict or set(snapshot['skills']) != set(SKILLS)
            or type(snapshot['orders']) is not list):
        raise ValueError('exact historical Focused Command prerequisites required')
    for value in (snapshot['command'], *snapshot['skills'].values()):
        C.integer(value, 'Focused Command acquisition skill rank', 0)
    if feature == FEATURE:
        if snapshot['orders']:raise ValueError('Focused Command has no Orders-count prerequisite')
        checks = [Q.check('command', 'prerequisite', snapshot['command'] >= 6, 'Master Command required'),
                  Q.check('expert', 'prerequisite', max(snapshot['skills'].values()) >= 5,
                          'one of Focus, Guile, Intimidate or Pokemon Education at Expert required')]
    else:
        orders = snapshot['orders']
        valid = len(set(orders)) == len(orders) and len(orders) >= 2
        for uid in orders:
            unit = actor.r.selection.units.get(uid, {})
            valid = valid and uid.startswith('feat/') and any(
                '지시' in tag or tag == 'Orders' for tag in unit.get('tags', []))
        checks = [Q.check('orders', 'prerequisite', valid, 'two actually acquired [Orders] Features required')]
    return Q.require(feature, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'), *checks])


def acquired(actor, feature=FEATURE):
    import commander as C
    return C.acquired(actor, feature)


def _seal(row):
    import trainer_feature_acquisition as T
    return T._digest('focused-command/v1', {key: value for key, value in row.items() if key != 'integrity'})


def _scope(engine):
    import party_actions as P
    return list(P.scope(engine))


def plan_ap(engine, actor, lift, *, edition='core'):
    """Choose before start_round; only the actual boundary charges the AP."""
    import world_entities as W, state_grants as G
    W.require_actors(engine, actor)
    if acquired(actor) is None:raise ValueError('actual acquired Focused Command required')
    selected = source(engine.r, edition=edition)
    if lift not in ('frequency', 'damage', 'both'):
        raise ValueError('lift exactly the frequency restriction, damage penalty, or both')
    if engine.round_start_seconds is not None or engine._active_turn_actor is not None:
        raise ValueError('Focused Command AP must be chosen before the actual beginning of the round')
    if PENDING in actor.spec:raise ValueError('one actual next-round Focused Command AP choice required')
    scope = [engine._party_encounter_epoch + (not engine.encounter_active), engine.round_no + 1]
    def apply(e, owner):
        row = {'issuer_id': owner.entity_id, 'scope': scope, 'lift': lift, 'source': selected,
               'acquisition': acquired(owner)['request_id']}
        row['integrity'] = _seal(row);owner.spec[PENDING] = row
        return deepcopy(row)
    return G.transition(engine, actor, apply)


def round_started(engine, participants):
    import world_entities as W
    actual = {c.entity_id for c in participants}
    for owner in W.actor_index(engine).values():
        row = owner.spec.get(PENDING)
        if row is None:continue
        if row.get('integrity') != _seal(row) or row['scope'] != _scope(engine):
            raise ValueError('Focused Command AP choice lost its actual next-round boundary')
        if owner.entity_id not in actual or acquired(owner) is None:
            raise ValueError('Focused Command AP payer must actually participate in the new round')
        if row['source'] != source(engine.r, edition=row['source']['edition']):
            raise ValueError('Focused Command AP selected source changed')
        amount = 2 if row['lift'] == 'both' else 1
        owner.ap_account.charge(amount, mode='spend')
        payment = dict(row, amount=amount, at=engine.elapsed_seconds)
        payment['integrity'] = _seal(payment)
        owner.spec.setdefault(AP_KEY, []).append(payment)
        del owner.spec[PENDING]


def _payments(actor):
    rows=actor.spec.get(AP_KEY, [])
    if type(rows)is not list or any(type(row)is not dict or row.get('integrity')!=_seal(row) for row in rows):
        raise ValueError('Focused Command round-start AP evidence changed')
    return rows


def _live(engine, actor=None):
    if not engine.encounter_active or engine.round_start_seconds is None:return []
    import world_entities as W
    owners = [actor] if actor is not None else W.actor_index(engine).values()
    result=[]
    for owner in owners:
        rows=owner.spec.get(KEY, [])
        if type(rows)is not list:raise ValueError('Focused Command history must be a list')
        for row in rows:
            if type(row)is not dict or row.get('integrity')!=_seal(row):
                raise ValueError('Focused Command actual activation evidence changed')
            if row['scope']==_scope(engine):result.append(row)
    return result


def pokemon_pair(engine, actor, pokemon):
    import world_entities as W, pokemon_activities as P
    if not isinstance(pokemon, (list, tuple)) or len(pokemon) != 2 or pokemon[0] is pokemon[1]:
        raise ValueError('two distinct actual commanded Pokemon required')
    W.require_actors(engine, actor, *pokemon)
    for partner in pokemon:
        P._pokemon(partner);P._owner(actor, partner)
        if not partner.on_field or partner.fainted or partner.captured:
            raise ValueError('commanded Pokemon must be conscious and on the field')
    used = {r['pokemon_id'] for r in actor.spec.get('party_command_turns', []) if r['scope'] == _scope(engine)}
    import party_actions as COMMANDS
    ordinary=COMMANDS.ordinary_command_limit(engine,actor) if COMMANDS.POLICY in actor.spec else 1
    if ordinary<2 and not used.issubset({p.entity_id for p in pokemon}):
        raise ValueError('both actual Pokemon commanded this round must be included')
    return tuple(pokemon)


def round_facts(actor):
    rows=actor.spec.get(FACTS,[])
    if type(rows)is not list or any(type(row)is not dict or row.get('integrity')!=_seal(row) for row in rows):
        raise ValueError('Focused Command actual round action evidence changed')
    return rows


def record_fact(engine, actor, source_id, kind, *, penalty=None):
    """Observe native frequency/Damage Roll owners, not a caller's declaration."""
    import party_actions as P
    if not engine.encounter_active or engine.round_start_seconds is None or actor.kind!='pokemon':return
    owner=P.owner(engine,actor)
    rows=round_facts(actor)
    row={'sequence':len(rows)+1,'issuer_id':None if owner is None else owner.entity_id,'pokemon_id':actor.entity_id,
         'scope':_scope(engine),'source_id':source_id,'kind':kind,'penalty':penalty,'at':engine.elapsed_seconds}
    row['integrity']=_seal(row);actor.spec.setdefault(FACTS,[]).append(row)


def prior_round_consistent(engine, actor, pokemon):
    payments=[r for r in _payments(actor) if r['scope']==_scope(engine)]
    lift=payments[0]['lift'] if payments else None
    for partner in pokemon:
        for fact in round_facts(partner):
            if fact['scope']!=_scope(engine):continue
            if fact['kind']=='damage_roll':
                if lift not in ('damage','both') and fact['penalty']!=-5:
                    raise ValueError('Focused Command cannot waive its penalty on prior Damage Rolls this round')
            elif lift not in ('frequency','both') and fact['kind'] not in ('at_will','static'):
                raise ValueError('Focused Command cannot allow a prior non-At-Will action this round')


def use(engine, actor, pokemon, *, target=None, edition='core'):
    import state_grants as G, turn as TURN, commander as C, world_entities as W
    receipt = acquired(actor)
    if receipt is None:raise ValueError('actual acquired Focused Command required')
    selected = source(engine.r, edition=edition)
    pair = pokemon_pair(engine, actor, pokemon)
    if edition == 'core' and target is not None:raise ValueError('Core Focused Command has no targets')
    if edition == 'local_csv':
        if target is None:raise ValueError('retained CSV Focused Command requires an explicit actual target')
        W.require_actors(engine, target)
    if not engine.encounter_active or engine.round_start_seconds is None:
        raise ValueError('Focused Command requires an actual open combat round')
    prior_round_consistent(engine,actor,pair)
    def apply(e, owner, *subjects):
        actual_pair = subjects[:2]
        if C.scope(e, owner, FEATURE) is None:
            from action_metadata import ActionCost
            paid = TURN.spend_compound(e, owner, ActionCost(('standard', 'swift')), FEATURE)
        else:
            paid = TURN.spend(e, owner, 'standard', FEATURE)
        if not paid:raise ValueError('Focused Command requires its actual Standard and Swift actions')
        payments = [r for r in _payments(owner) if r['scope'] == _scope(e)]
        row = {'id': 'focused-command:' + owner.entity_id + ':' + str(len(owner.spec.get(KEY, [])) + 1),
               'issuer_id': owner.entity_id, 'scope': _scope(e), 'source': selected,
               'acquisition': receipt['request_id'], 'pokemon_ids': [p.entity_id for p in actual_pair],
               'target_id': None if target is None else subjects[2].entity_id,
               'lift': payments[0]['lift'] if payments else None, 'at': e.elapsed_seconds,
               'turn': owner.custom_conditions.get('combat_turn_serial', 0)}
        row['integrity'] = _seal(row);owner.spec.setdefault(KEY, []).append(row)
        return deepcopy(row)
    return G.transition(engine, actor, apply, participants=(*pair, *((target,) if target is not None else ())))


def command_limit(engine, actor, ordinary_limit):
    return max(ordinary_limit, 2) if _live(engine, actor) else ordinary_limit


def require_turn(engine, trainer, pokemon, ordinary_limit):
    rows = _live(engine, trainer)
    if ordinary_limit < 2 and rows and not any(pokemon.entity_id in row['pokemon_ids'] for row in rows):
        raise ValueError('Focused Command extra turn belongs to the actual commanded Pokemon')


def restricted(engine, actor):
    return any(actor.entity_id in row['pokemon_ids'] and row['lift'] not in ('frequency', 'both')
               for row in _live(engine))


def frequency_allowed(engine, actor, kind):
    return not restricted(engine, actor) or kind in ('at_will', 'static')


def damage_modifier(engine, actor):
    return -5 if any(actor.entity_id in row['pokemon_ids'] and row['lift'] not in ('damage', 'both')
                     for row in _live(engine)) else 0


def validate_world(engine, index):
    import commander as C, common_checks as CHECK
    for owner in index.values():
        for number,fact in enumerate(round_facts(owner),1):
            fields={'sequence','issuer_id','pokemon_id','scope','source_id','kind','penalty','at','integrity'}
            if (set(fact)!=fields or fact['sequence']!=number or fact['pokemon_id']!=owner.entity_id
                    or owner.kind!='pokemon' or fact['issuer_id'] is not None and (fact['issuer_id'] not in index or index[fact['issuer_id']].kind!='trainer')
                    or type(fact['scope'])is not list or len(fact['scope'])!=2
                    or any(type(v)is not int or v<1 for v in fact['scope'])
                    or fact['scope'][0]>engine._party_encounter_epoch or fact['scope'][1]>engine.round_no
                    or fact['kind'] not in ('damage_roll','at_will','static','scene','daily','encounter','turn','every_other_turn','one_time','unknown')
                    or (fact['kind']=='damage_roll' and fact['penalty'] not in (0,-5))
                    or (fact['kind']!='damage_roll' and fact['penalty'] is not None)
                    or type(fact['source_id'])is not str or not fact['source_id']):
                raise ValueError('Focused Command actual round action evidence changed')
            CHECK.integer(fact['at'],'Focused Command round action time',0,engine.elapsed_seconds)
        for field in (KEY, AP_KEY):
            rows = owner.spec.get(field, [])
            if type(rows) is not list:raise ValueError('Focused Command history must be a list')
            for n, row in enumerate(rows, 1):
                common = {'issuer_id', 'scope', 'source', 'acquisition', 'lift', 'integrity', 'at'}
                fields = common | ({'id', 'pokemon_ids', 'target_id', 'turn'} if field == KEY else {'amount'})
                if (type(row) is not dict or set(row) != fields or row['integrity'] != _seal(row)
                        or row['issuer_id'] != owner.entity_id or owner.kind != 'trainer'
                        or row['source'] != source(engine.r, edition=row['source']['edition'])
                        or not any(r['request_id'] == row['acquisition'] for r in C.receipts(owner, FEATURE))):
                    raise ValueError('Focused Command actual source or acquisition evidence changed')
                if (type(row['scope']) is not list or len(row['scope']) != 2
                        or any(type(x) is not int or x < 1 for x in row['scope'])
                        or row['scope'][0] > engine._party_encounter_epoch or row['scope'][1] > engine.round_no
                        or row['lift'] not in (None, 'frequency', 'damage', 'both')):
                    raise ValueError('Focused Command actual round or AP choice changed')
                CHECK.integer(row['at'], 'Focused Command actual time', 0, engine.elapsed_seconds)
                if field == KEY:
                    ids = row['pokemon_ids']
                    if (row['id'] != 'focused-command:' + owner.entity_id + ':' + str(n)
                            or type(ids) is not list or len(set(ids)) != 2
                            or any(uid not in index or index[uid].kind != 'pokemon' for uid in ids)
                            or row['source']['edition'] == 'core' and row['target_id'] is not None
                            or row['source']['edition'] == 'local_csv' and row['target_id'] not in index):
                        raise ValueError('Focused Command targets and affected Pokemon are distinct source facts')
                    payments = [p for p in _payments(owner) if p['scope'] == row['scope']]
                    if row['lift'] != (payments[0]['lift'] if payments else None):
                        raise ValueError('Focused Command restriction lift requires its actual round-start AP')
                    CHECK.integer(row['turn'], 'Focused Command actual Trainer turn', 1,
                                  owner.custom_conditions.get('combat_turn_serial', 0))
                elif row['amount'] != (2 if row['lift'] == 'both' else 1):
                    raise ValueError('Focused Command AP amount changed')
        pending = owner.spec.get(PENDING)
        if pending is not None:
            fields = {'issuer_id', 'scope', 'lift', 'source', 'acquisition', 'integrity'}
            expected = [engine._party_encounter_epoch + (not engine.encounter_active), engine.round_no + 1]
            if (type(pending) is not dict or set(pending) != fields or pending['integrity'] != _seal(pending)
                    or pending['issuer_id'] != owner.entity_id or pending['scope'] != expected
                    or pending['lift'] not in ('frequency', 'damage', 'both')
                    or pending['source'] != source(engine.r, edition=pending['source']['edition'])
                    or not any(r['request_id'] == pending['acquisition'] for r in C.receipts(owner, FEATURE))):
                raise ValueError('Focused Command pending AP requires the actual next round')
    return True
