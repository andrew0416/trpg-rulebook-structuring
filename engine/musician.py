"""Book Musician declarations and source-owned consumers of shared native APIs."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import acquired_features as ACQUIRED
import contest_features as CF
import skill_modifiers as SKILLS
import state_grants as G

_data = json.loads((Path(__file__).resolve().parents[1] / 'data/musician-definitions.json').read_text(encoding='utf8'))
DEFINITIONS = _data['features']
FEATURES = tuple(DEFINITIONS)
CLASS, ABILITY, BLUES, CACOPHONY, NOISE, VOICE, CHORD = FEATURES
SOURCE_SHA256 = _data['source_sha256']
DROWN = 'ability/소리묻히기'
DROWN_PLAYTEST = 'ability/소리묻히기-playtest'
KEY = 'musician'


def _records(actor, feature, active=True):
    import trainer_feature_acquisition as TFA
    return [record for _, record in TFA.static_acquisitions(actor, feature, active=active)]


def owns(actor, feature):
    return actor.kind == 'trainer' and bool(ACQUIRED.owned_rule_count(actor, feature))


def acquisition_snapshot(e, actor, feature, branch=None):
    d = DEFINITIONS[feature]
    if feature == ABILITY:
        if branch not in ('방음', '소리묻히기', '소리묻히기 [Playtest]'):
            raise ValueError('Musical Ability requires Soundproof or an explicitly selected Drown Out version')
        if owns(actor, feature):
            raise ValueError('Musical Ability already acquired; its choice cannot be repeated')
        e.r._selected_rule(e.r.selection.resolve_name(branch, ('ability/',)))
    elif branch is not None:
        raise ValueError('this Musician Feature has no branch')
    parents = {}
    for parent in d['parents']:
        qualify(e, actor, parent)
        parents[parent] = _records(actor, parent)[-1]['request_id']
    return {'parents': parents, 'ranks': {s: SKILLS.rank(e.r, actor, s)[2] for s in ('매력', '집중')}, 'branch': branch}


def qualification(actor, feature, snapshot, prerequisite_source):
    import acquisition_qualification as Q
    if prerequisite_source is not None or type(snapshot) is not dict or set(snapshot) != {'parents', 'ranks', 'branch'}:
        raise ValueError('exact Musician acquisition observations required')
    d = DEFINITIONS[feature]
    if set(snapshot['parents']) != set(d['parents']) or set(snapshot['ranks']) != {'매력', '집중'}:
        raise ValueError('printed Musician prerequisite observations required')
    for parent, request in snapshot['parents'].items():
        if not any(r['request_id'] == request for r in _records(actor, parent, False)):
            raise ValueError('actual historical Musician prerequisite receipt required')
    if any(type(v) is not int or not 1 <= v <= 6 for v in snapshot['ranks'].values()):
        raise ValueError('actual Musician skill ranks required')
    branch = snapshot['branch']
    if (feature == ABILITY and branch not in ('방음', '소리묻히기', '소리묻히기 [Playtest]')) or (feature != ABILITY and branch is not None):
        raise ValueError('printed Musical Ability selection required')
    sufficient = min(snapshot['ranks'].values()) >= 3 if feature == CLASS else max(snapshot['ranks'].values()) >= d['any_skill_rank']
    return Q.require(feature, 'native', 'acquire', [
        Q.check('trainer', 'prerequisite', actor.kind == 'trainer', 'actual Trainer required'),
        Q.check('skill', 'prerequisite', sufficient, 'printed Musician skill rank required')])


def qualify(e, actor, feature):
    import trainer_feature_acquisition as TFA
    if not owns(actor, feature) or len(_records(actor, feature)) != 1:
        raise ValueError('actual acquired Musician source required: ' + feature)
    TFA.validate_actor(actor)
    TFA._static_source(e.r, feature)
    for parent in DEFINITIONS[feature]['parents']:
        qualify(e, actor, parent)
    ranks = [SKILLS.rank(e.r, actor, skill)[2] for skill in ('매력', '집중')]
    if (feature == CLASS and min(ranks) < 3) or max(ranks) < DEFINITIONS[feature]['any_skill_rank']:
        raise ValueError('printed Musician skill rank required')
    return DEFINITIONS[feature]


def after_acquire(e, actor, feature, source_id, branch):
    if feature in (BLUES, CACOPHONY, NOISE):
        import items
        items.register_feats(e, actor)  # existing fixed move and [+Special Attack] projections
    else:
        G.stat(actor, 'spa', 1, source_id, operation_id='acquisition_stat_tag')
    if feature == ABILITY:
        G.grant(actor, 'abilities', branch, source_id, 'feature', owner_id=actor.entity_id,
                lifetime='while_owned', rule_id=feature, tutor_points=0)
        e.register_abilities_one(actor, branch)


def voice_owner(e, actor):
    import world_entities as W
    owner = actor if actor.kind == 'trainer' else W.actor_index(e).get(actor.spec.get('trainer_id')) if actor.kind == 'pokemon' else None
    if owner is None or not owns(owner, VOICE):
        return None
    qualify(e, owner, VOICE)
    return owner


def sonic(actor, move):
    import effects_ext as EXT
    return '소리' in EXT.keywords_for(actor, move)


def project_move(e, actor, move):
    import effects_ext as EXT
    keywords=sorted(EXT.keywords_for(actor,move))
    move=dict(move)
    if keywords or 'keywords' in move:move['keywords']=keywords
    if move['id'] != 'move/멸망의노래' and sonic(actor, move) and voice_owner(e, actor) is not None:
        return dict(move, keywords=sorted(set(move.get('keywords', [])) | {'친화'}))
    return move


def friendly_targets(actor, move, targets):
    import effects_ext as EXT
    if '친화' not in EXT.keywords_for(actor, move):
        return targets
    return [target for target in targets if target.side != actor.side]


def contest_bonus(e, pokemon, trainer, move):
    # The exclusion applies to the whole Feature, not just its combat keyword.
    return int(pokemon.kind == 'pokemon' and pokemon.spec.get('trainer_id') == trainer.entity_id
               and move['id'] != 'move/멸망의노래' and sonic(pokemon, move)
               and voice_owner(e, pokemon) is trainer)


def _stamp(e, actor):
    return {'round': e.round_no, 'turn': actor.custom_conditions.get('combat_turn_serial', 0),
            'at': e.elapsed_seconds, 'encounter': bool(e.encounter_active)}


def _current(e, actor, record):
    return record is not None and record['stamp'] == _stamp(e, actor)


def after_move_use(e, actor, target, move, mm, completion_id):
    import dancer as D
    import area_targets as AREA
    import weapon_actions as W
    import body_state as BODY
    if not owns(actor, CLASS) or not (sonic(actor, move) or D.is_dance_move(e.r, move['id'])):
        return
    completion=getattr(e,'_move_completions',{}).get(completion_id)
    if (completion is None or completion['actor'] is not actor or completion['move_id']!=move['id']
            or completion['phase']!='targets' or target.entity_id not in completion['started']
            or target.entity_id in completion['results'] or not getattr(e,'_native_move_resolution_depth',0)):
        raise ValueError('actual native Musician Move activation required')
    geometry = W.range_spec(e, move, actor)
    if geometry.get('shape') and e.grid is not None:
        bound = move if '_area_aim' in move else AREA.bind(e, actor, move, actor.pos if geometry['shape'] == 'burst' else target.pos)
        cells = sorted(AREA.cells(e, actor, bound))
    else:
        cells = sorted(BODY.cells(target, require_complete=True))
    completion['musician_song']={'sonic': sonic(actor,move), 'dance':D.is_dance_move(e.r,move['id']),
        'cells':[list(c) for c in cells], 'used':False}
    actor.spec.setdefault(KEY,{})['move_trigger']=completion_id


def play(e, actor, songs, *, mode='standard', power_chord=None):
    """Play one Song or two with Full Action; optional Power Chord resolves at each actual Song trigger."""
    import world_entities as W
    import turn as TURN
    import action_points as AP
    import effects as FX
    import body_state as BODY
    W.require_actors(e, actor)
    qualify(e, actor, CLASS)
    if not e.encounter_active or e.grid is None:
        raise ValueError('Songs require an actual mapped encounter and turn lifetime')
    if type(songs) not in (list, tuple) or len(songs) != (2 if mode == 'full' else 1) or any(s not in _data['songs'] for s in songs):
        raise ValueError('one printed Song, or exactly two for a Full Action, required')
    if mode not in ('standard', 'full', 'sound', 'dance'):
        raise ValueError('printed Song activation mode required')
    chords = ([power_chord] + [None] * (len(songs) - 1) if power_chord is None or isinstance(power_chord, str) else list(power_chord))
    if len(chords) != len(songs) or any(c not in (None, '매력', '집중') for c in chords):
        raise ValueError('each Song takes an independent optional Charm or Focus Power Chord choice')
    if any(c is not None for c in chords):
        qualify(e, actor, CHORD)
    def apply(native, user):
        trigger = None
        if mode in ('sound', 'dance'):
            trigger=_song_origin(native,user,for_use=True)
            if trigger is None or trigger['used'] or not trigger['sonic' if mode == 'sound' else 'dance']:
                raise ValueError('an actual unused same-turn Sonic or Dance Move trigger required')
        if AP.available(user) < len(songs):
            raise ValueError('one AP required for each Song')
        if native._active_turn_actor is not user or not TURN.spend(native, user, {'sound': 'swift', 'dance': 'shift'}.get(mode, mode), CLASS):
            raise ValueError('Song action unavailable on the actual user turn')
        AP.spend(user, len(songs))
        cells = {tuple(c) for c in trigger['cells']} if mode == 'sound' else set(native.grid.burst(user.pos, 2 if mode == 'dance' else 4))
        if mode in ('sound', 'dance'):
            trigger['used'] = True
        allies = [c for c in W.actor_index(native).values() if c is user or
                  (c.side == user.side and c.on_field and not c.fainted and not c.captured
                   and BODY.cells(c, require_complete=True).intersection(cells))]
        result = []
        for song, chord in zip(songs, chords):
            effects = [dict(effect, target='target', until="end of user's next turn") for effect in _data['songs'][song]]
            for ally in allies:
                applied = FX.run_effects(native, user, ally, effects, {"hit": True}, CLASS)
                if applied[1]:
                    raise ValueError('Song effect contract was not fully executable: '+str(applied.outcomes))
            record = {'song': song, 'mode': mode, 'cells': [list(c) for c in sorted(cells)],
                      'targets': [a.entity_id for a in allies], 'stamp': _stamp(native, user)}
            if chord is not None:
                record['power_chord'] = _power_chord(native, user, cells, chord)
            result.append(record)
        user.spec.setdefault(KEY, {})['last_songs'] = result
        return deepcopy(result)
    return G.transition(e, actor, apply, include_rulings=True, include_grid=True)


def _power_chord(e, actor, cells, skill):
    import world_entities as W
    import body_state as BODY
    import frequency as F
    import combat_damage as DAMAGE
    import effects_ext as EXT
    qualify(e, actor, CHORD)
    if not F.activation_allowed(actor, CHORD, '장면x2', engine=e):
        raise ValueError('Power Chord scene uses exhausted')
    CF.trigger_free_action(e, actor, CHORD)
    F.consume_activation(actor, CHORD, '장면x2', engine=e)
    check = e.skill_roll(actor, skill)
    total = check.total + actor.staged('spa')
    move = {'id': CHORD, 'name': '파워 코드', 'type': '노말', 'class': '특수', 'keywords': [], 'range': 'Song area'}
    receipts = {}
    for target in W.actor_index(e).values():
        if target.side == actor.side or not target.on_field or target.fainted or target.captured or not BODY.cells(target, require_complete=True).intersection(cells):
            continue
        defense, reduction = EXT.defense_hook(e, actor, target, move, {'effects_exec': []}, 'spd')
        defended = DAMAGE.defend(dice=check.total, attack=actor.staged('spa'), modifiers=0, defense=defense, reduction=reduction)
        mult, _ = e.type_multiplier('노말', target)
        amount = DAMAGE.scale(after_defense=defended['after_defense'], type_multiplier=mult)
        before = DAMAGE.observe(target)
        e.take_damage(target, amount)
        receipts[target.entity_id] = DAMAGE.application(requested=amount, before=before, after=DAMAGE.observe(target), source=CHORD, damage_class='특수')
    return {'skill': skill, 'check': check.total, 'special_attack': actor.staged('spa'), 'total': total, 'damage': receipts}


def validate_world(e, index):
    for actor in index.values():
        st = actor.spec.get(KEY)
        if st is None:
            continue
        if type(st) is not dict or set(st) - {'move_trigger', 'last_songs'}:
            raise ValueError('typed Musician trigger state required')
        if 'move_trigger' in st:_song_origin(e,actor)


def validate_core_ability(rules, row):
    expected = {'type': 'sonic_move_cancellation', 'action': 'free', 'frequency': '장면', 'skill': '집중', 'dc': 'actual_accuracy_roll'}
    if row.get('id') != DROWN or row.get('name') != '소리묻히기' or row.get('native_contract') != expected:
        raise ValueError('reviewed core Drown Out contract required')
    source = row['source']
    if source['file'] != 'ch04-trainer-classes.md' or source['lines'] != [2496, 2496]:
        raise ValueError('Musical Ability core Drown Out reference changed')
    if sha256((Path(rules.root) / 'input' / source['file']).read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Musical Ability source changed')
    official = row['official_source']
    if official['extract']!='source-audit/core-drown-out.txt' or source['additional_snapshots']!={official['extract']:official['sha256']}:
        raise ValueError('core Drown Out exact auxiliary source locator required')
    from source_context import verified_source
    verified_source(rules,{'file':official['extract'],'sha256':official['sha256']},label='core Drown Out',source_root='source-audit')


def drown_out(e, attacker, target, move, total, shared_roll=None):
    """Native accuracy producer only: one optional reaction per activation, before any target effects."""
    import ability_transitions as AB
    import ability_interrupt_choices as INTERRUPTS
    import frequency as F
    import move_activation as ACTIVATION
    import world_entities as W
    if not sonic(attacker, move):
        return False
    scope = ACTIVATION.current_scope(e, attacker, target, move['id'])
    if scope is None:
        # Direct native use_move still has an authenticated target completion.
        import move_completion as COMPLETE
        row = next((r for r in reversed(list(getattr(e, '_move_completions', {}).values()))
                    if r.get('actor') is attacker and r.get('move_id') == move['id'] and target.entity_id in r.get('started', []) and target.entity_id not in r.get('results', {})), None)
        if row is None:
            return False
        scope = row
    if scope.get('completion_id'):
        scope=getattr(e,'_move_completions',{})[scope['completion_id']]
    if 'drown_out' in scope:
        return scope['drown_out']['cancelled']
    result = {'cancelled': False, 'attempts': []}
    scope['drown_out'] = result
    for owner in W.actor_index(e).values():
        if owner.side == attacker.side or owner.fainted or not owner.on_field or owner.captured:
            continue
        source = DROWN if _drown_active(owner,DROWN) else DROWN_PLAYTEST if _drown_active(owner,DROWN_PLAYTEST) else None
        if source is None:
            continue
        frequency = '장면' if source == DROWN else '장면x2'
        if not F.activation_allowed(owner, source, frequency, engine=e):
            continue
        ruling = _no_accuracy_ruling(e,owner,move) if source==DROWN and total is None else None
        if source==DROWN and total is None and (ruling is None or ruling.get('not_applicable')):
            continue
        dc=ruling['dc'] if ruling is not None and 'dc' in ruling else total
        answer = True if owner.spec.get('drown_out_request',{}).get('source')==source else e.decide({'type': 'drown_out', 'owner': owner, 'attacker': attacker, 'source': source, 'move_id': move['id'], 'accuracy_total': total})
        if answer is not True:
            continue
        INTERRUPTS.pay_free(e, owner, source, frequency, trigger={'owner': attacker})
        check = e.skill_check(owner, '집중', dc)[1] if source == DROWN else None
        cancelled = source == DROWN_PLAYTEST or check >= dc
        result['attempts'].append({'owner_id': owner.entity_id, 'source': source, 'check': check, 'dc': dc, 'ruling': deepcopy(ruling), 'cancelled': cancelled})
        if cancelled:
            result['cancelled'] = True
            e.log('  Drown Out: Sonic Move fails', source)
            return True
    return False


def validate(e):
    import world_entities as W
    validate_world(e,W.actor_index(e))


def request_drown_out(e, owner, *, source=DROWN, reason):
    import ability_transitions as AB
    import world_entities as W
    W.require_actors(e,owner)
    if source not in (DROWN,DROWN_PLAYTEST) or not _drown_active(owner,source) or not isinstance(reason,str) or not reason.strip():
        raise ValueError('actual owned Drown Out and explicit reaction intent required')
    owner.spec['drown_out_request']={'source':source,'reason':reason}


def no_accuracy_pending(e, attacker, move_id):
    import common_checks as C
    import ability_transitions as AB
    import world_entities as W
    if move_id is None:return None
    move=e.r.move(move_id)
    if move.get('ac') is not None or not sonic(attacker,move):return None
    for owner in W.actor_index(e).values():
        if (owner.side!=attacker.side and owner.spec.get('drown_out_request',{}).get('source')==DROWN
                and _drown_active(owner,DROWN) and not owner.fainted and owner.on_field and not owner.captured):
            if _no_accuracy_ruling(e,owner,move) is not None:continue
            return C.PendingDecision('Core Drown Out triggers on this Sonic Move, but it has no Accuracy Roll to supply the printed Focus DC. A source ruling is required before activation.',
                basis={'source':DROWN,'move_id':move['id'],'owner_id':owner.entity_id,'source_reference':'PTU Core316 / source-audit/core-drown-out.txt',
                       'unanswered':'DC or explicit inapplicability for no-Accuracy Sonic Moves; Playtest is a separate source',
                       'resume':'record an authoritative source ruling; no action, AP, frequency, accuracy or effect was consumed'})
    return None


def drown_interested(e):
    import ability_transitions as AB
    import world_entities as W
    return any(_drown_active(a,DROWN) or _drown_active(a,DROWN_PLAYTEST) for a in W.actor_index(e).values())


def _no_accuracy_ruling(e, owner, move):
    """Existing explicit GM answer channel; no edition choice or DC is inferred."""
    answer=e.rulings.decide({'type':'drown_out_no_accuracy','source':DROWN,
        'owner_id':owner.entity_id,'move_id':move['id'],
        'text':'Core Drown Out has no printed DC for this Move without an Accuracy Roll.'})
    if answer is None:return None
    if not isinstance(answer,dict) or set(answer) not in ({'source','move_id','dc','reason'},{'source','move_id','not_applicable','reason'}):
        raise ValueError('exact source-specific no-Accuracy Drown Out GM ruling required')
    if answer['source']!=DROWN or answer['move_id']!=move['id']:
        return None
    if not isinstance(answer['reason'],str) or not answer['reason'].strip():
        raise ValueError('explicit GM ruling reason required')
    if 'dc' in answer:
        if type(answer['dc']) is not int or answer['dc']<0:raise ValueError('explicit nonnegative Focus DC required')
    elif answer['not_applicable'] is not True:
        raise ValueError('explicit no-Accuracy inapplicability ruling required')
    return deepcopy(answer)


def _drown_active(actor, source):
    import ability_transitions as AB
    label='소리묻히기' if source==DROWN else '소리묻히기 [Playtest]'
    return bool((label in actor.abilities or source in actor.abilities) and AB.active(actor,label))


def _song_origin(e, actor, *, for_use=False):
    """The class stores only the ID of the existing authoritative Move completion."""
    import dancer as D
    import move_completion as COMPLETE
    uid=actor.spec.get(KEY,{}).get('move_trigger')
    if uid is None:return None
    if not isinstance(uid,str):raise ValueError('actual Musician completion identity required')
    row=getattr(e,'_move_completions',{}).get(uid)
    if row is None or row.get('actor') is not actor or row.get('id')!=uid:
        raise ValueError('actual Musician completion owner required')
    move=row.get('move',{})
    if row.get('move_id')!=move.get('id') or (not row.get('started') and row.get('activation')!='empty_area_field'):
        raise ValueError('actual Musician prepared Move required')
    data=row.get('musician_song')
    if not isinstance(data,dict) or set(data)!={'sonic','dance','cells','used'}:
        raise ValueError('actual native Musician activation evidence required')
    expected_sonic='소리' in move.get('keywords',())
    expected_dance=D.is_dance_move(e.r,row['move_id'])
    if (not (expected_sonic or expected_dance) or data['sonic'] is not expected_sonic
            or data['dance'] is not expected_dance or type(data['used']) is not bool):
        raise ValueError('Musician trigger differs from its actual Sonic or Dance Move')
    if not isinstance(data['cells'],list) or any(not isinstance(c,list) or len(c)!=2 or any(type(n) is not int for n in c) for c in data['cells']):
        raise ValueError('native Musician area cells required')
    if row.get('drown_out',{}).get('cancelled') or (row['results'] and all(r['cancelled'] for r in row['results'].values())):
        raise ValueError('cancelled Move cannot authorize a Musician Song')
    if for_use:
        latest=next((value['id'] for value in reversed(list(getattr(e,'_move_completions',{}).values())) if value['actor'] is actor),None)
        if latest!=uid:raise ValueError('stale Musician Move activation cannot trigger a Song')
        if row.get('phase')!='complete':raise ValueError('completed native Musician Move required')
        if (row['round']!=e.round_no or row['turn_serial']!=actor.custom_conditions.get('combat_turn_serial',0)
                or row['seconds']!=e.elapsed_seconds):
            raise ValueError('an actual unused same-turn Sonic or Dance Move trigger required')
    return data


def after_completion(e, row):
    if 'musician_song' not in row:return
    actor=row['actor']
    cancelled=row.get('drown_out',{}).get('cancelled') or (bool(row['results']) and all(r['cancelled'] for r in row['results'].values()))
    if cancelled and actor.spec.get(KEY,{}).get('move_trigger')==row['id']:
        actor.spec[KEY].pop('move_trigger',None)


def after_empty_use(e,actor,row):
    if not owns(actor,CLASS) or not sonic(actor,row['move']):return
    if (row.get('activation')!='empty_area_field' or row.get('phase')!='complete'
            or getattr(e,'_move_completions',{}).get(row['id']) is not row
            or not getattr(e,'_native_move_resolution_depth',0)):
        raise ValueError('actual completed target-free Sonic activation required')
    row['musician_song']={'sonic':True,'dance':False,'cells':[list(c) for c in row['field_cells']],'used':False}
    actor.spec.setdefault(KEY,{})['move_trigger']=row['id']
