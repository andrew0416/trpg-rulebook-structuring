"""C02-163 consumes actual owned sources and the existing withdrawal evidence."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import acquisition_withdrawal as WITHDRAWAL
import acquired_features as ACQUIRED
import state_grants as GRANTS


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise ValueError(label + ' required')
    return value


def _owned(actor):
    if actor.kind != 'trainer':
        raise ValueError('actual trainer acquisition required')
    result = {}
    for prefix, fields in (('edge/', ('edges',)), ('feat/', ('feats',)),
                           ('class/', ('classes', 'feats'))):
        names = ACQUIRED._names(actor, prefix)
        for field in fields:
            for value in actor.spec.get(field, []):
                if value not in names:
                    continue
                uid = ACQUIRED._resolve(actor, value, prefix, names)
                if uid in result:
                    raise ValueError('retraining requires one distinct acquired source')
                result[uid] = (field, value)
    return result


def owned_source(engine, actor, rule_id):
    """Observe current ownership; never fabricate an acquisition-time receipt."""
    import world_entities as WORLD
    WORLD.require_actors(engine, actor)
    if rule_id not in _owned(actor):
        raise ValueError('actual acquired trainer source required')
    import type_expertise as TYPE_EXPERTISE
    if rule_id == TYPE_EXPERTISE.FEATURE:
        return TYPE_EXPERTISE.source_for_rank(actor)
    import stat_ace as STAT
    branches=STAT.records(actor,rule_id,active=True) if rule_id in STAT.FEATURES else []
    if len(branches)==1:return 'feature:'+actor.entity_id+':'+rule_id+':'+branches[0]['snapshot']['branch']
    import style_expert as STYLE
    acquisition=STYLE.acquired(actor,rule_id) if rule_id in STYLE.FEATURES else None
    if acquisition is not None:
        import trainer_feature_acquisition as FEATURES
        definition=FEATURES.STATIC_FEATURES[rule_id]
        return 'feature:'+actor.entity_id+':'+rule_id+(':'+acquisition['snapshot']['branch'] if definition.get('branch') else '')+(':rank:'+str(acquisition['snapshot']['rank_number']) if definition.get('ranked') else '')
    import hunter as HUNTER
    acquisition=HUNTER.acquired(actor,rule_id) if rule_id in HUNTER.FEATURES else None
    if acquisition is not None and HUNTER.DEFINITIONS[rule_id].get('branch'):
        return 'feature:'+actor.entity_id+':'+rule_id+':'+acquisition['snapshot']['branch']
    import dancer as DANCER
    acquisitions=DANCER._records(actor,rule_id) if rule_id==DANCER.CLASS else []
    if len(acquisitions)==1:
        return DANCER.acquisition_source_id(actor,rule_id,acquisitions[0]['snapshot']['branch'])
    source = 'feature:' + actor.entity_id + ':' + rule_id
    row = GRANTS.state(actor)['sources'].get(source)
    if row is not None:
        if (row.get('rule_id') != rule_id or row.get('owner_id') != actor.entity_id or
                row.get('lifetime') != 'while_owned'):
            raise ValueError('owned trainer source provenance changed')
    else:
        GRANTS._source(actor, source, 'feature', rule_id=rule_id,
                       owner_id=actor.entity_id, lifetime='while_owned', tutor_points=0)
    return source


def irreversible(engine, actor, rule_id, *, event_id, reason):
    """Called inside the real permanent-effect producer's staged commit."""
    _text(event_id, 'actual permanent effect event')
    _text(reason, 'actual permanent effect reason')
    source = owned_source(engine, actor, rule_id)
    result = WITHDRAWAL.irreversible(engine, actor, source, event_id=event_id, reason=reason)
    GRANTS.state(actor)['sources'][source]['irreversible_trainer_feature'] = True
    return result


def _source_matches(actor,source,row):
    expected='feature:'+actor.entity_id+':'+row.get('rule_id','')
    acquisition=row.get('static_acquisition')
    if acquisition is not None:
        import trainer_feature_acquisition as FEATURES
        definition=FEATURES.STATIC_FEATURES[acquisition['feature_id']]
        if definition.get('branch'):expected+=':'+acquisition['snapshot']['branch']
        if definition.get('ranked'):expected+=':rank:'+str(acquisition['snapshot']['rank_number'])
    return source==expected


def validate_actor(actor):
    for source, row in actor.spec.get(GRANTS.KEY, {}).get('sources', {}).items():
        if not row.get('irreversible_trainer_feature'):
            continue
        uid = row.get('rule_id')
        uses = row.get('irreversible_uses')
        if (uid not in _owned(actor) or not _source_matches(actor,source,row) or
                row.get('owner_id') != actor.entity_id or row.get('lifetime') != 'while_owned' or
                type(uses) is not dict or not uses or any(
                    type(key) is not str or not key.strip() or type(value) is not str or not value.strip()
                    for key, value in uses.items())):
            raise ValueError('irreversible trainer Feature requires its actual owned source and use')
    return True


def retired_receipts(actor):
    """Selection receipts remain immutable after their owning source ends."""
    result = set()
    for entry in actor.spec.get(GRANTS.KEY, {}).get('ended_sources', []):
        row = entry['record']
        withdrawal = row.get('retraining')
        if withdrawal is None:
            continue
        if (type(withdrawal) is not dict or withdrawal.get('cause') != 'retraining' or
                not _source_matches(actor,entry['source_id'],row) or
                row.get('owner_id') != actor.entity_id or row.get('lifetime') != 'while_owned'):
            raise ValueError('actual ended retraining source required')
        ids = withdrawal.get('acquisition_receipt_ids')
        if type(ids) is not list or any(type(value) is not str for value in ids):
            raise ValueError('original withdrawn acquisition receipt references required')
        if result.intersection(ids):
            raise ValueError('acquisition receipt withdrawn twice')
        receipts = {value['receipt_id']: value for value in
                    actor.spec.get('trainer_feature_acquisition_receipts', {}).values()}
        if any(identity not in receipts or receipts[identity]['feature_id'] != row['rule_id']
               for identity in ids):
            raise ValueError('withdrawn selection must name its own original acquisition receipt')
        result.update(ids)
    return result


def _native_dependencies(engine, actor, owned):
    """Use the parent identities declared by the existing teaching owners."""
    import fortress as FORTRESS
    fortress={u:list(parents) for u,parents in FORTRESS.PARENTS.items() if u in owned}
    if any(parent not in owned for parents in fortress.values() for parent in parents):raise ValueError('actual acquired Fortress prerequisite required')
    import breather as BREATHER
    enduring={child:[parent] for child,parent in ((BREATHER.STAYING,BREATHER.CLASS),(BREATHER.SHRUG,BREATHER.STAYING),
        (BREATHER.VIM,BREATHER.SHRUG),(BREATHER.NOT_YET,BREATHER.CLASS)) if child in owned}
    if any(parent not in owned for parents in enduring.values() for parent in parents):
        raise ValueError('actual retained Enduring Soul feature prerequisite required')
    import pokemon_teaching as TEACHING
    import feature_ability_lessons as LESSONS
    import trainer_feature_acquisition as FEATURES
    result = dict(enduring)
    for child,parents in __import__('ace_trainer').PARENTS.items():
        if child in owned and parents:
            if not set(parents)<=set(owned):raise ValueError('actual retained Ace Trainer prerequisite required')
            result[child]=list(parents)
    import ace_trainer as ACE
    for receipt in ACE.records(actor,ACE.ELITE,active=True):
        gift=receipt['snapshot']['gift']['feature']
        if gift in owned:result[gift]=list(dict.fromkeys([*result.get(gift,[]),ACE.ELITE]))
    for child,parents in __import__('warper').PARENTS.items():
        if child in owned and parents:
            if not set(parents)<=set(owned):raise ValueError('actual retained Warper prerequisite required')
            result[child]=list(parents)
    for child,parents in __import__('telepath').PARENTS.items():
        if child in owned and parents:
            if not set(parents)<=set(owned):raise ValueError('actual retained Telepath prerequisite required')
            result[child]=list(parents)
    for child,parents in __import__('telekinetic').PARENTS.items():
        if child in owned:parents=__import__('telekinetic').prerequisite_parents(actor,child)
        if child in owned and parents:
            if not set(parents)<=set(owned):raise ValueError('actual retained Telekinetic prerequisite required')
            result[child]=list(parents)
    import sage as SAGE
    for child,parents in SAGE.PARENTS.items():
        if child in owned and parents:
            retained=[p for p in parents if p in owned]
            if not retained or child!=SAGE.BENEDICTION and len(retained)!=len(parents):raise ValueError('actual retained Sage prerequisite required')
            result[child]=retained[:1] if child==SAGE.BENEDICTION else retained
    import ninja as NINJA
    import oracle as ORACLE
    for child,definition in ORACLE.DEFINITIONS.items():
        if child in owned:
            parent=definition['parent']
            if parent:
                if parent not in owned:raise ValueError('actual retained Oracle prerequisite required')
                result[child]=[parent]
    for child,definition in NINJA.DEFINITIONS.items():
        parent=definition['parent']
        if child in owned and parent:
            if parent not in owned:raise ValueError('actual retained Ninja prerequisite required')
            result[child]=[parent]
    import rogue as ROGUE
    for child,definition in ROGUE.DEFINITIONS.items():
        if child in owned:
            parents=definition['parents']
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Rogue prerequisite required')
            result[child]=list(parents)
    import tumbler as TUMBLER
    for child,definition in TUMBLER.DEFINITIONS.items():
        if child in owned:result[child]=[definition["parent"]]
    import taskmaster as TASK
    for child,definition in TASK.DEFINITIONS.items():
        if child in owned:
            parents=definition['parents']
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Taskmaster prerequisite required')
            result[child]=list(parents)
    import conquerors_march as MARCH
    for child,parent in MARCH.PARENTS.items():
        if child in owned:
            if parent not in owned:raise ValueError('actual acquired Rider Feature prerequisite required')
            result[child]=[parent]
    import control_mount as MOUNT,training_features as TRAINING
    for child,parents in ((MOUNT.RIDER,('edge/탑승-기량',TRAINING.AGILITY)),(MOUNT.RIDE_AS_ONE,(MOUNT.RIDER,))):
        if child in owned:
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Rider prerequisite required')
            result[child]=list(parents)
    if 'feat/복원력' in owned:
        if 'feat/자각' not in owned:raise ValueError('actual Book Awareness prerequisite required')
        result['feat/복원력']=['feat/자각']
    import duelist as DUELIST
    for child,parents in DUELIST.PARENTS.items():
        if child in owned:
            if any(parent not in owned for parent in parents):raise ValueError('actual Duelist prerequisite required')
            result[child]=list(parents)
    for child,parent in (("class/치어리더","feat/영감성-훈련"),("feat/행동의-순간","class/치어리더"),("feat/응원-단체","class/치어리더"),("feat/영감을-주는-지원","feat/응원-단체"),("feat/신나게-방해","feat/응원-단체"),("feat/응원-문구","feat/행동의-순간")):
        if child in owned:
            if parent not in owned:raise ValueError('actual acquired Cheerleader prerequisite required')
            result[child]=[parent]
    import stat_ace as STAT
    for child,definition in STAT.DEFINITIONS.items():
        if child in owned:
            if any(parent not in owned for parent in definition['parents']):raise ValueError('actual Stat Ace prerequisite source required')
            result[child]=list(definition['parents'])
    import capture_techniques as CAPTURE
    import style_expert as STYLE
    for child,definition in STYLE.DEFINITIONS.items():
        if child in owned and child!=STYLE.CLASS:
            parent=definition.get('parent',STYLE.CLASS)
            if parent not in owned:raise ValueError('actual retained Style prerequisite required')
            result[child]=[parent]
    if "feat/포획-추진력" in owned:
        result["feat/포획-추진력"] = [CAPTURE.ADVANCED]
    if CAPTURE.ADVANCED in owned:
        if CAPTURE.CLASS not in owned:
            raise ValueError('Advanced Capture Techniques requires its actual acquired parent')
        result[CAPTURE.ADVANCED] = [CAPTURE.CLASS]
    if FEATURES.MARTIAL_ARTIST in owned:
        FEATURES._martial_qualification(actor, actor, ())
        result[FEATURES.MARTIAL_ARTIST] = [FEATURES.MARTIAL_PREREQUISITE]
    for child, parent in ((TEACHING.MOVE_TUTOR, TEACHING.MENTOR),
                          (TEACHING.EGG_TUTOR, TEACHING.MOVE_TUTOR)):
        if child in owned:
            if parent not in owned:
                raise ValueError('actual acquired teaching prerequisite required')
            result[child] = [parent]
    for child in LESSONS.SOURCES:
        if child in owned:
            parent = LESSONS._policy(engine.r)[child]['parent']
            if parent not in owned:
                raise ValueError('actual acquired Ability lesson parent required')
            result[child] = [parent]
    import roughneck as ROUGHNECK
    for child,definition in ROUGHNECK.DEFINITIONS.items():
        if child in owned:
            parents=list(definition["parents"])
            if child==ROUGHNECK.CLASS:parents.append(ROUGHNECK.PRESENCE)
            if any(parent not in owned for parent in parents):raise ValueError("actual acquired Roughneck prerequisite required")
            result[child]=parents
    import musician as MUSICIAN
    for child,definition in MUSICIAN.DEFINITIONS.items():
        if child in owned:
            parents=definition['parents']
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Musician prerequisite required')
            result[child]=list(parents)
    import hunter as HUNTER
    for child,definition in HUNTER.DEFINITIONS.items():
        if child in owned and child!=HUNTER.CLASS:
            parents=[definition['parent'],*definition.get('prerequisites',[])]
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Hunter prerequisite required')
            result[child]=list(dict.fromkeys(result.get(child,[])+parents))
    import martial_artist as MARTIAL
    for child,definition in MARTIAL.DEFINITIONS.items():
        if child in owned:
            parents=[MARTIAL.CLASS,*definition.get('prerequisites',[])]
            if any(parent not in owned for parent in parents):raise ValueError('actual acquired Martial Artist prerequisite required')
            result[child]=list(dict.fromkeys(result.get(child,[])+parents))
    import channeler as CHANNEL
    for child,definition in CHANNEL.DEFINITIONS.items():
        if child in owned:
            parent=definition['parent'] or 'edge/신비한-감각'
            if parent not in owned:raise ValueError('actual acquired Channeler prerequisite required')
            result[child]=[parent]
    import aura_guardian as AURA
    for child,definition in AURA.DEFINITIONS.items():
        if child in owned:
            parent=definition['parent'] or 'edge/원소-교감'
            if parent not in owned:raise ValueError('actual acquired Aura prerequisite required')
            result[child]=[parent]
    import provocateur as PROVOCATEUR
    for child,definition in PROVOCATEUR.DEFINITIONS.items():
        if child in owned and definition['parent']:
            parent=definition['parent']
            if parent not in owned:raise ValueError('actual acquired Provocateur prerequisite required')
            result[child]=list(dict.fromkeys(result.get(child,[])+[parent]))
    result.update(fortress)
    return result


def retrain(engine, actor, rule_id, *, request_id, reason, gm_decision,
            retained_dependencies, granted_skill_edge_policy=None, rank=None):
    """Retire one actual Edge/Feature selection after GM and source checks.

    GM-owned dynamic prerequisites (including skill-rank providers) name actual
    source IDs for every retained selection. Native teaching parents cannot be
    omitted. Replacement acquisition is a separate existing source adapter.
    """
    import world_entities as WORLD
    import trainer_xp_payments as XP
    import trainer_feature_acquisition as FEATURES
    import resolution_transaction as TRANSACTIONS
    WORLD.require_actors(engine, actor)
    source_file = Path(engine.r.root) / 'input/ch02-character-creation.md'
    if sha256(source_file.read_bytes()).hexdigest() != '44f0412c27e93730445a544096951925273bc98d3c729b65f4030f155d8dc000':
        raise ValueError('C02-163 retraining source changed; review required')
    engine.r.ruleset.require({'id': 'C02-163', 'source': {
        'file': 'ch02-character-creation.md', 'lines': [355, 358]}})
    for value, label in ((rule_id, 'actual rule identity'), (request_id, 'retraining request'),
                         (reason, 'retraining reason')):
        _text(value, label)
    if (type(gm_decision) is not dict or set(gm_decision) != {'allowed', 'reason'} or
            gm_decision['allowed'] is not True):
        raise ValueError('explicit allowed GM retraining consultation required')
    _text(gm_decision['reason'], 'GM narrative retraining decision')
    if type(retained_dependencies) is not dict:
        raise ValueError('complete retained source dependency declaration required')
    intent = {'rule_id': rule_id, 'request_id': request_id, 'reason': reason,
              'gm_decision': deepcopy(gm_decision), 'retained_dependencies': deepcopy(retained_dependencies)}
    if granted_skill_edge_policy is not None:
        intent['granted_skill_edge_policy'] = deepcopy(granted_skill_edge_policy)
    if rank is not None:
        intent['rank'] = rank
    fingerprint = TRANSACTIONS.request_fingerprint(intent)
    for entry in actor.spec.get(GRANTS.KEY, {}).get('ended_sources', []):
        prior = entry['record'].get('retraining', {})
        if prior.get('request_id') == request_id:
            if prior.get('intent') != fingerprint:
                raise ValueError('retraining request changed')
            return deepcopy(prior['result'])
    owned = _owned(actor)
    if rule_id not in owned:
        raise ValueError('actual acquired trainer source required')
    import type_expertise as TYPE_EXPERTISE
    selected_rank = TYPE_EXPERTISE.retraining_rank(actor, rule_id, rank)
    if selected_rank is None and ACQUIRED.owned_rule_count(actor, rule_id) != 1:
        raise ValueError('select one actual trainer acquisition for retraining')
    if request_id in actor.spec.get(XP.KEY, {}):
        raise ValueError('retraining request already belongs to an XP payment')

    def apply(e, trainer):
        import capture_techniques as CAPTURE
        import class_passive_combat as PASSIVE
        sources = {uid: owned_source(e, trainer, uid) for uid in owned}
        import keep_fighting as KEEP
        if KEEP.FEATURE in owned and rule_id!=KEEP.FEATURE:
            parents=[sources[uid] for uid in KEEP.FAMILY if uid in owned and uid!=rule_id]
            declared=retained_dependencies.get(sources[KEEP.FEATURE],[])
            if len(set(parents).intersection(declared))<5:
                raise ValueError('retained Keep Fighting requires five actual Cheerleader Feature sources')
        retained = set(sources.values()) - GRANTS._revocation_sources(trainer,[sources[rule_id]])
        retained_ranks = {sid for sid, row in TYPE_EXPERTISE.records(trainer)
                          if selected_rank is None or row['snapshot']['rank_number'] < selected_rank}
        retained.update(retained_ranks)
        import ace_trainer as ACE
        if ACE.CHAMP in owned and sources[ACE.CHAMP] in retained:
            parents=[sources[uid] for uid in ACE.FEATURES if uid in sources and uid!=ACE.CHAMP and sources[uid] in retained]
            declared=retained_dependencies.get(sources[ACE.CHAMP],[])
            if len(set(parents).intersection(declared))<4:
                raise ValueError('retained Champ in the Making requires four actual Ace Trainer Features')
        import oracle as ORACLE
        if ORACLE.PREVIEW in owned and sources[ORACLE.PREVIEW] in retained:
            parents=[sources[uid] for uid in ORACLE.FEATURES if uid in sources and uid!=ORACLE.PREVIEW and sources[uid] in retained]
            declared=retained_dependencies.get(sources[ORACLE.PREVIEW],[])
            if len(set(parents).intersection(declared))<3:
                raise ValueError('retained Two-Second Preview requires three actual Oracle Features')
        import taskmaster as TASK
        if TASK.GAMBIT in owned and rule_id!=TASK.GAMBIT:
            parents=[sources[uid] for uid in TASK.FEATURES if uid in owned and uid not in (rule_id,TASK.GAMBIT)]
            declared=retained_dependencies.get(sources[TASK.GAMBIT],[])
            if len(set(parents).intersection(declared))<TASK.DEFINITIONS[TASK.GAMBIT]['parameters']['class_features']:
                raise ValueError('retained Deadly Gambit requires five actual Taskmaster Features')
        import roughneck as ROUGHNECK
        if ROUGHNECK.NAILS in owned and rule_id!=ROUGHNECK.NAILS:
            parents=[sources[uid] for uid in ROUGHNECK.FEATURES if uid in owned and uid not in (rule_id,ROUGHNECK.NAILS)]
            declared=retained_dependencies.get(sources[ROUGHNECK.NAILS],[])
            if len(set(parents).intersection(declared))<3:
                raise ValueError('retained Tough as Nails requires three actual Roughneck Features')
        if set(retained_dependencies) != retained:
            raise ValueError('dependencies must cover every actual retained trainer source')
        required = _native_dependencies(e, trainer, owned)
        for source, parents in retained_dependencies.items():
            uid = TYPE_EXPERTISE.FEATURE if source in retained_ranks else next(uid for uid, value in sources.items() if value == source)
            WITHDRAWAL.dependencies(e, trainer, source, parents)
            if any(sources[parent] not in parents for parent in required.get(uid, [])):
                raise ValueError('native retained acquisition prerequisite cannot be omitted')
        CAPTURE.prepare_retraining(e, trainer, rule_id, granted_skill_edge_policy)
        source = sources[rule_id]
        affected = []
        modifier_prefix = 'static-modifier:' + trainer.entity_id + ':' + rule_id + ':'
        for target in WORLD.actors(e):
            keys = [key for key, row in target.spec.get(GRANTS.KEY, {}).get('sources', {}).items()
                    if row.get('owner_id') == trainer.entity_id and row.get('rule_id') == rule_id and
                    row.get('lifetime') in ('while_owned', 'your_pokemon') and
                    (selected_rank is None or key == source) and
                    (key == source or row.get('static_acquisition',{}).get('feature_id')==rule_id or (row.get('kind') == 'static_trainer_modifier' and key.startswith(modifier_prefix)) or
                     (row.get('kind') == 'class_passive_combat' and
                      (row.get('source_variant') == 'C03-126' or
                       rule_id in PASSIVE.POKEMON_STATIC and not row.get('sustain') and row.get('acquisition_source') == rule_id) and
                      key.startswith('class-passive:' + trainer.entity_id + ':')))]
            if keys:
                GRANTS.preflight_revoke(target, keys)
                affected.append((target, keys))
        # Type Expertise stores each rank in its own static source record. The
        # archived selected source already retains that exact request/receipt.
        acquisition_ids = [] if selected_rank is not None else [
            row['receipt_id'] for row in trainer.spec.get(FEATURES.LEDGER_KEY, {}).values()
            if row['feature_id'] == rule_id and row['receipt_id'] not in retired_receipts(trainer)]
        payment = XP.retraining(e, trainer, 'edge' if rule_id.startswith('edge/') else 'feature',
                                request_id=request_id, reason=reason, refund_policy='before_use')
        result = {'rule_id': rule_id, 'source_id': source, 'request_id': request_id,
                  'xp_paid': payment['amount'], 'cause': 'retraining'}
        if selected_rank is not None:
            result['rank'] = selected_rank
        GRANTS.state(trainer)['sources'][source]['retraining'] = {
            'cause': 'retraining', 'request_id': request_id, 'intent': fingerprint,
            'gm_decision': deepcopy(gm_decision), 'acquisition_receipt_ids': acquisition_ids,
            'result': deepcopy(result)}
        if granted_skill_edge_policy is not None:
            GRANTS.state(trainer)['sources'][source]['retraining']['granted_skill_edge_policy'] = deepcopy(granted_skill_edge_policy)
        import conquerors_march as MARCH
        MARCH.withdraw(e,trainer,rule_id)
        __import__('ace_trainer').withdraw(e,trainer,rule_id)
        __import__('channeler').withdraw(e,trainer,rule_id)
        __import__('oracle').withdraw(e,trainer,rule_id)
        __import__('sage').withdraw(e,trainer,rule_id)
        import stat_ace as STAT
        STAT.withdraw(e,trainer,rule_id)
        import chronicler as CHRONICLER
        CHRONICLER.withdraw(e,trainer,rule_id)
        import fashionista as FASHIONISTA
        FASHIONISTA.withdraw(e,trainer,rule_id)
        import hunter as HUNTER
        HUNTER.withdraw(e,trainer,rule_id)
        __import__('martial_artist').withdraw(e,trainer,rule_id)
        import athlete as ATHLETE
        ATHLETE.withdraw(e,trainer,rule_id)
        for target, keys in affected:
            GRANTS._revoke_sources(target, keys, e)
        field, raw = owned[rule_id]
        if selected_rank is not None and selected_rank > 1:
            trainer.spec['feat_ranks'][rule_id] = selected_rank - 1
        else:
            trainer.spec[field].remove(raw)
            for key in ('feat_ranks', 'feature_choices'):
                trainer.spec.get(key, {}).pop(rule_id, None)
        if rule_id.startswith('edge/'):
            import skill_modifiers as SKILLS
            import weapon_actions as WEAPONS
            names = ACQUIRED._names(trainer, 'edge/')
            aliases = {SKILLS.key(name) for name in names if names[name] == [rule_id]}
            for group in ('edges', 'rank_effects'):
                policy = trainer.r.skill_policy.get(group, {}).get(rule_id, {})
                aliases.update(SKILLS.key(name) for name in policy.get('aliases', ()))
            if rule_id == WEAPONS.CHOICE_EDGE:
                aliases.update(WEAPONS.CHOICE_ALIASES)
            choices = trainer.spec.get('edge_choices', {})
            for name in list(choices):
                if SKILLS.key(name) in aliases:
                    del choices[name]
        if FEATURES.PROJECTION_KEY in trainer.spec:
            trainer.spec[FEATURES.PROJECTION_KEY] = FEATURES._projection_from_rows(FEATURES._active_rows(trainer))
        import items as ITEMS
        ITEMS.register_feats(e, trainer)
        XP.mark_used(e, trainer, request_id, event_id='retraining:' + request_id)
        import state_fields as FIELDS
        for target, _ in affected:
            FIELDS.validate_actor(target)
        e.log(trainer.name + ': retrained ' + rule_id + ': ' + reason, 'C02-163')
        return result

    return GRANTS.transition(engine, actor, apply)
