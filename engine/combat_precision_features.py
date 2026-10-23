"""Source-owned Demoralize, Blur and Pinpoint Strike native combat consumers.

PTK ch03:430-432, 623, 805-829; PTU 1.05 pp54,61-63.
Accuracy bonuses, secondary effect ranges, and natural critical faces are distinct.
Pinpoint's one live Stratagem owns a matching trainer AP binding, per Pokemon.
"""
import arithmetic_policy as M
import action_points as AP
import skill_modifiers as SKILL
import turn as TURN
import combat_modifiers as COMBAT_MODS

BAD_MOOD = "edge/나쁜-분위기"
DEMORALIZE = "edge/사기저하"
BLUR = "feat/흐릿함"
PRECISION = "feat/정밀-지시"
PINPOINT = "feat/핀포인트-스트라이크"
CSV_FEATURES = {
    'C2CSV/input/db/feats.csv:R33:main': PINPOINT,
    'C2CSV/input/db/feats.csv:R36:main': BLUR,
}
KEY = "_pinpoint_strike"
ALIASES = {
    BAD_MOOD: ("나쁜 분위기", "Bad Mood"),
    DEMORALIZE: ("사기저하", "Demoralize"),
    BLUR: ("흐릿함", "Blur"),
    PRECISION: ("정밀 지시", "Precision Orders"),
    PINPOINT: ("핀포인트 스트라이크", "Pinpoint Strike"),
}

def identity(name):
    if not isinstance(name, str):
        return None
    if name in CSV_FEATURES:
        return CSV_FEATURES[name]
    return next((uid for uid, aliases in ALIASES.items()
                 if SKILL.key(name) in {SKILL.key(x) for x in (uid, *aliases)}), None)

def _acquired_source(actor, uid):
    field = 'edges' if uid in (DEMORALIZE,BAD_MOOD) else 'feats'
    names = actor.spec.get(field, [])
    if not isinstance(names, (list, tuple)):
        raise ValueError('feature ownership must be a list')
    acquired = [name for name in names if identity(name) == uid]
    if not acquired:
        return None
    if len(acquired) != 1 or actor.kind != 'trainer':
        raise ValueError('feature requires exactly one trainer acquisition')
    return acquired[0] if acquired[0] in CSV_FEATURES else uid

def owns(engine, actor, uid, *, validate_stat=True):
    source = _acquired_source(actor, uid)
    if source is None:
        return False
    if engine.r._selected_rule(source) != source:
        raise ValueError('selected feature variant requires its sourced policy')
    if uid == BAD_MOOD and SKILL.rank(engine.r, actor, '협박')[2] < 5:
        raise ValueError('Bad Mood requires Expert Intimidate')
    if uid == DEMORALIZE and SKILL.rank(engine.r, actor, '협박')[2] < 4 and not __import__('provocateur').waive_demoralize(actor):
        raise ValueError('Demoralize requires Adept Intimidate')
    if uid == BLUR and any(SKILL.rank(engine.r, actor, x)[2] < 5 for x in ('곡예', '은신')):
        raise ValueError('Blur requires Expert Acrobatics and Expert Stealth')
    if uid == PRECISION and not any(SKILL.rank(engine.r, actor, x)[2] >= 5 for x in ('명령', '통찰')):
        raise ValueError('Precision Orders requires Expert Command or Perception')
    if uid == PINPOINT and not owns(engine, actor, PRECISION):
        raise ValueError('Pinpoint Strike requires acquired Precision Orders')
    if uid == BLUR and validate_stat:
        _stat_receipt(actor, source)
    return True

def register_owned(engine, actor, name):
    uid = identity(name)
    if uid is None:
        return False
    owns(engine, actor, uid, validate_stat=False)
    source = _acquired_source(actor, uid)
    if uid == BLUR:
        _register_stat(actor, source)
    engine.log(f"    {actor.name}: {uid} native accuracy/damage consumer", source)
    return True

def _stat_declaration(actor, source):
    declarations=actor.spec.get('feature_stat_imports',{})
    if not isinstance(declarations,dict):
        raise ValueError('explicit feature stat import declarations required')
    choice=declarations.get(source)
    if not isinstance(choice,dict) or set(choice)!={'mode','base_stat'} or choice.get('mode') not in ('apply','included'):
        raise ValueError('Blur +Speed requires explicit apply or included stat import')
    base=choice['base_stat']
    if type(base) is not int or base < 1:
        raise ValueError('Blur stat import requires the original positive Speed stat')
    return choice

def _stat_receipt(actor, source):
    choice=_stat_declaration(actor, source)
    receipts=actor.custom_conditions.get('_feature_stat_receipts',{})
    if any(identity(key)==BLUR and key!=source for key in receipts):
        raise ValueError('Blur acquisition source changed without reconciliation')
    row=receipts.get(source)
    expected={'source':source,'stat':'spe','delta':1,'before':choice['base_stat'],
              'after':choice['base_stat']+1,'mode':choice['mode']}
    if row!=expected:
        raise ValueError('Blur +Speed requires registered acquisition receipt')
    # Combat stages and other live modifiers are separate runtime values; this
    # receipt accounts for the acquired base-sheet contribution, not their totals.
    if actor.spec['stats'].get('spe')!=row['after']:
        raise ValueError('Blur base-sheet stat changed without acquisition reconciliation')
    return row

def _register_stat(actor, source):
    choice=_stat_declaration(actor, source)
    receipts=actor.custom_conditions.get('_feature_stat_receipts',{})
    if any(identity(key)==BLUR for key in receipts):
        return _stat_receipt(actor, source)
    base=choice['base_stat'];before=base if choice['mode']=='apply' else base+1
    if actor.stats.get('spe')!=before or actor.spec['stats'].get('spe')!=before:
        raise ValueError('Blur stat import does not match actual base-sheet Speed')
    if choice['mode']=='apply':
        actor.stats['spe']=base+1;actor.spec['stats']['spe']=base+1
    row={'source':source,'stat':'spe','delta':1,'before':base,'after':base+1,'mode':choice['mode']}
    actor.custom_conditions.setdefault('_feature_stat_receipts',{})[source]=row
    return row

def _live(engine, actor):
    return any(x is actor for x in engine.everyone)

def _owner(engine, trainer, pokemon):
    if pokemon is None or pokemon is trainer or pokemon.kind != 'pokemon':
        raise ValueError('Pinpoint requires your own Pokemon')
    owner_id = pokemon.spec.get('trainer_id')
    owner_name = pokemon.spec.get('trainer')
    if owner_id is not None:
        if not isinstance(owner_id,str) or not owner_id or owner_id != trainer.spec.get('id'):
            raise ValueError('Pokemon belongs to a different trainer identity')
        if sum(c.kind=='trainer' and c.spec.get('id')==owner_id for c in engine.everyone) != 1:
            raise ValueError('ambiguous actual trainer identity')
        if owner_name is not None and owner_name != trainer.name:
            raise ValueError('conflicting Pokemon owner fields')
    else:
        if owner_name != trainer.name or sum(c.kind=='trainer' and c.name==trainer.name for c in engine.everyone) != 1:
            raise ValueError('Pokemon requires an unambiguous trainer owner')
    return True

def _ledger(actor):
    return AP.ActionPointAccount(actor).identified_bindings(allow_missing=True)

def _pinpoint_source(engine, trainer, requested=None):
    source = _acquired_source(trainer, PINPOINT) or PINPOINT
    if requested in CSV_FEATURES and requested != source:
        raise ValueError('actual acquired Pinpoint source required')
    if engine.r._selected_rule(source) != source:
        raise ValueError('Pinpoint source ownership or selected rule changed')
    return source

def binding(engine, pokemon):
    row = pokemon.custom_conditions.get(KEY)
    if row is None:
        return None
    trainer = row.get('owner')
    if not engine.encounter_active or not _live(engine, pokemon) or not _live(engine, trainer):
        raise ValueError('Pinpoint binding must belong to the actual active encounter')
    if row.get('target') is not pokemon:
        raise ValueError('Pinpoint actual Pokemon ownership changed')
    _owner(engine,trainer,pokemon)
    if not owns(engine, trainer, PRECISION) or row.get('source') != _pinpoint_source(engine, trainer):
        raise ValueError('Pinpoint source ownership or selected rule changed')
    if _ledger(trainer).get(row.get('instance')) != 2:
        raise ValueError('Pinpoint requires its matching two AP binding')
    return row

def _owned_target(engine, trainer, pokemon, source=None):
    if not owns(engine, trainer, PRECISION):
        raise ValueError('Pinpoint Strike requires acquired Precision Orders')
    source = _pinpoint_source(engine, trainer, source)
    if not _live(engine, trainer) or not _live(engine, pokemon):
        raise ValueError('actual registered trainer and Pokemon required')
    _owner(engine,trainer,pokemon)
    if not engine.encounter_active:
        raise ValueError('Stratagem may only be bound during combat')
    if not pokemon.on_field or pokemon.fainted or pokemon.captured:
        raise ValueError('Pinpoint target must be an available Pokemon')
    return source

import cheerleader as CHEER

@CHEER.order_activation('feat/핀포인트-스트라이크')
def activate(engine, trainer, pokemon, *, source=None):
    source = _owned_target(engine, trainer, pokemon, source)
    bound = _ledger(trainer)
    import class_passive_combat as CLASS_PASSIVE
    CLASS_PASSIVE._require_stratagem_slot(pokemon)
    if AP.available(trainer) < 2:
        raise ValueError('Pinpoint Strike requires two available AP')
    import temporary_ap as TEMP_AP
    TEMP_AP.preflight_binding(trainer,2,'combat_precision_features')
    if not TURN.spend(engine, trainer, 'standard', source):
        return (0, 1)
    # No RNG, callback, or fallible effect follows the committed Standard action.
    serial = trainer.custom_conditions.get('_pinpoint_serial', 0) + 1
    trainer.custom_conditions['_pinpoint_serial'] = serial
    instance = source + ':' + str(serial)
    while instance in bound:
        serial += 1
        trainer.custom_conditions['_pinpoint_serial'] = serial
        instance = source + ':' + str(serial)
    trainer.ap_account.charge(2, mode='bind', instance_id=instance, temporary_binding_owner='combat_precision_features')
    pokemon.custom_conditions[KEY] = {'owner':trainer, 'target':pokemon, 'instance':instance, 'source':source}
    engine.time_actors([trainer, pokemon])
    engine.log(f"    {trainer.name}: {pokemon.name} Pinpoint Strike, bind 2 AP", source)
    return (1, 0)

def _unbind(engine, pokemon, row):
    row['owner'].ap_account.release_binding(row['instance'], expected_amount=2)
    pokemon.custom_conditions.pop(KEY)
    engine.log(f"    {pokemon.name}: Pinpoint Strike ends; release 2 AP", row['source'])

def release(engine, trainer, pokemon):
    row = binding(engine, pokemon)
    if row is None or row['owner'] is not trainer:
        raise ValueError('actual owner of the active Pinpoint binding required')
    if not TURN.spend(engine, trainer, 'free', row['source'] + ' release'):
        return (0, 1)
    _unbind(engine, pokemon, row)
    return (1, 0)

def end_encounter(engine, actors):
    # Ending an encounter is global even when the caller supplies only a subset.
    all_actors = list({id(c):c for c in [*actors,*engine.time_actors(),*engine.everyone]}.values())
    rows = [(c, binding(engine,c)) for c in all_actors if KEY in c.custom_conditions]
    for pokemon, row in rows:
        _unbind(engine, pokemon, row)

def damaging(move):
    return bool(move and move.get('class') in ('물리','특수'))

def preflight(engine, attacker, target, move, mm, *, applying=False):
    for actor in (attacker, target):
        owns(engine, actor, BLUR)
        owns(engine, actor, DEMORALIZE)
        owns(engine, actor, BAD_MOOD)
        binding(engine, actor)
    if applying and owns(engine, attacker, DEMORALIZE) and target is not attacker:
        if attacker.side is None or target.side is None:
            raise ValueError('Demoralize requires the actual friend/foe relation before attack cost')

def blur_applies(engine, target, move, mm, automatic=False):
    return owns(engine, target, BLUR) and (move.get('ac') is None or bool(mm.get('never_miss')) or automatic)

def accuracy_policy(engine, attacker, target, move, mm, ac, evasion, automatic):
    if blur_applies(engine, target, move, mm, automatic):
        return 2, M.ratio(evasion,2), False
    return ac, evasion, automatic

def accuracy_bonus(engine, attacker, move):
    return 2 if damaging(move) and binding(engine, attacker) else 0

def effect_range_bonus(attacker, move):
    """Compatibility entry for the shared, scope-checked modifier consumer."""
    return COMBAT_MODS.effect_range_bonus(attacker, move)


def effect_natural(engine, attacker, move, natural, *, actual_damage_type=None):
    # Only threshold comparisons change. Natural-one misses, critical ranges and
    # even/odd effects continue to consume the actual rolled face.
    if natural is None:
        return None
    if __import__("provocateur").blocked(attacker,"no_effect_range"):return -1000
    import training_features as TRAINING
    import class_passive_combat as CLASS_PASSIVE
    import optional_weapon_framework as FRAMEWORK
    import pledge_state as PLEDGE
    import taskmaster as TASK
    import stat_ace as STAT
    mechanics,_ = engine.r.move_mech(move['id'])
    return (natural + accuracy_bonus(engine, attacker, move)
            + (TRAINING.bonus(attacker, "effect") if move else 0)
            + effect_range_bonus(attacker, move)
            + CLASS_PASSIVE.effect_range_bonus(engine,attacker,move,mechanics,actual_damage_type=actual_damage_type)
            + __import__('type_ace').effect_range(engine,attacker,move)
            + __import__('martial_artist').effect_range(engine,attacker,move)
            + FRAMEWORK.effect_range_bonus(engine,attacker,move)
            + PLEDGE.effect_range_bonus(engine,attacker,move)
            + __import__('chef_cooking').effect_range_bonus(engine,attacker,move)
            + TASK.bonus(attacker,'effect')
            + STAT.stratagem_bonus(engine,attacker,'effect',move))

def damage_modifier(engine, attacker, move):
    return -5 if damaging(move) and binding(engine, attacker) else 0

def status_can_critical(engine, attacker, target, move):
    mm,_ = engine.r.move_mech(move['id'])
    return owns(engine,attacker,DEMORALIZE) and (move.get('ac') is not None or blur_applies(engine,target,move,mm))


def bad_mood_critical_bonus(engine,actor):
    """Each actual status category contributes once, not once per condition."""
    if not owns(engine,actor,BAD_MOOD):return 0
    categories={engine.r.condition_class(name) for name in actor.conditions}
    return int('persistent' in categories)+int('volatile' in categories)

