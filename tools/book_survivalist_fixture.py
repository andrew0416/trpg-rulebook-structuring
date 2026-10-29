"""Survivalist whole-class scenario helpers (no tests): real static acquisition, actual
terrain mastery through the existing GM activities, Terrain Talent choices, encounter
setup, GM rulings and both restore paths.

Every helper uses public engine entry points; nothing patches classes, feats, talents,
tools, hazards or timed records into state.
"""
from copy import deepcopy
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
import survivalist_class as SC
import survivalist_features as V
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import world_entities as W
from chained_case_lifecycle import bind_case_lifecycle, defer_case_commit

STATS = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 12)
SKILLS = {'생존': 6, '육상': 4, '곡예': 4, '은신': 3, '통찰': 3, '집중': 3, '전투': 4, '교활': 4, '협박': 4, '매력': 4}
CORE_FEATURES = (SC.CLASS, SC.NATURAL, SC.TRAPPER, SC.GUIDE)
FOE_MOVES = ['move/몸통박치기', 'move/모래뿌리기', 'move/냉동빔', 'move/모래지옥', 'move/독가루', 'move/화염방사', 'move/압정뿌리기', 'move/스텔스록']
TERRAIN_CELLS = ((5, 1), (5, 2), (5, 3), (5, 4), (6, 1), (6, 2), (6, 3), (6, 4))


def trainer_spec(rules, name, *, survival=6, skills=None, feats=(), classes=(), movement=None, edges=()):
    extra = {'classes': list(classes), 'feats': list(feats), 'edges': list(edges),
             'skills': dict(SKILLS, **{'생존': survival}, **(skills or {}))}
    if movement is not None:
        extra['movement'] = dict(movement)
    return build_trainer(rules, name, 20, STATS, extra=extra)


def pokemon_spec(rules, trainer, name, *, species='이브이', moves=None, abilities=()):
    extra = {} if trainer is None else {'trainer_id': trainer.entity_id, 'trainer': trainer.name}
    return build_pokemon(rules, species, 20, name=name, moves=list(moves or ['move/몸통박치기']), abilities=list(abilities), extra=extra)


def acquire(engine, trainer, uid, *, request=None, rank=None):
    suffix = '' if rank is None else ':' + str(rank)
    return ACQUIRE.acquire_static(engine, trainer, uid, acquisition_request_id=request or ('survivalist/' + trainer.entity_id + '/' + uid + suffix), rank=rank)


def scene(rules, *, seed=11, feats=CORE_FEATURES, grid=(12, 8), ally=False, foe_moves=None, partner_species='이브이', survival=6):
    """Survivalist trainer at (2,2), its Pokemon at (3,2), an optional allied trainer at (2,3) and a wild foe at (8,2)."""
    engine = Engine(rules, seed=seed)
    if grid is not None:
        engine.grid = Grid(*grid)
    trainer = Combatant(rules, trainer_spec(rules, 'survivalist', survival=survival))
    engine.gm.add_combatant(trainer, pos=(2, 2), side='party', reason='actual Survivalist trainer')
    partner = Combatant(rules, pokemon_spec(rules, trainer, 'partner', species=partner_species))
    engine.gm.add_combatant(partner, pos=(3, 2), side='party', reason='own Pokemon')
    world = {'engine': engine, 'trainer': trainer, 'partner': partner}
    if ally:
        friend = Combatant(rules, trainer_spec(rules, 'ally'))
        engine.gm.add_combatant(friend, pos=(2, 3), side='party', reason='allied trainer')
        world['ally'] = friend
    foe = Combatant(rules, pokemon_spec(rules, None, 'foe', moves=foe_moves or ['move/몸통박치기']))
    engine.gm.add_combatant(foe, pos=(8, 2), side='wild', reason='opposing wild Pokemon')
    world['foe'] = foe
    for uid in feats:
        acquire(engine, trainer, uid)
    return world


def env(engine, actor, *terrains, light='normal'):
    return engine.survivalist_activity(actor, 'observe_environment', terrains=list(terrains), light=light, reason='GM actual terrain and light')


def night(engine, actor, terrain, identity):
    env(engine, actor, terrain)
    engine.survivalist_activity(actor, 'begin_night', night_id=identity, terrain_name=terrain, reason='GM overnight beginning')
    engine.advance_time(60, [actor])
    return engine.survivalist_activity(actor, 'finish_night', night_id=identity, reason='GM overnight completed')


def master(engine, actor, terrain, *, minutes=7):
    for n in range(3):
        night(engine, actor, terrain, terrain + ':' + str(n))
    return engine.survivalist_activity(actor, 'select_terrain', terrain_name=terrain, minutes=minutes, reason='GM Extended selection duration')


def talents(engine, actor, *terrains, rank=1):
    """Acquire the printed rank and choose the given talents from already mastered terrains."""
    acquire(engine, actor, SC.TALENT, rank=rank)
    return engine.survivalist_activity(actor, 'choose_talents', terrains=list(terrains))


def battle(engine, actor, *, count=20):
    engine.start_round(engine.everyone)
    engine.start_of_turn(actor, initiative_count=count)


def next_turn(engine, previous, actor, *, count=20):
    if previous is not None:
        engine.end_of_turn(previous)
    engine.start_of_turn(actor, initiative_count=count)


def ruling(engine, key, answer, *, reason='explicit GM adjudication for this test'):
    engine.rulings.answers = [row for row in engine.rulings.answers if row['key'] != key]
    engine.rulings.add_answer(key, answer, reason=reason, scope='permanent')


def restore(rules, engine):
    payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
    loaded = CODEC.load_engine(rules, payload)
    return loaded, W.actor_index(loaded)


def guide_rows(actor):
    return SC._guide_rows(actor)


class TerrainTalentChain:
    LIFECYCLE_METHODS = (
        'test_cave_dweller_is_immune_to_stealth_rock_hazards',
        'test_forest_ranger_grants_the_stealth_capability_everywhere_only_to_the_actual_choice',
        'test_arctic_pilgrim_ignores_hail_and_frozen_and_reduces_ice_damage_by_five',
        'test_talent_effects_survive_both_restores_and_need_the_actual_choice')

    @classmethod
    def prepare_chained_cases(cls, cases):
        if any(type(case) is not cls for case in cases):
            raise ValueError('Terrain Talent chain requires this exact class')
        stages = [case for case in cases if case._testMethodName in cls.LIFECYCLE_METHODS]
        if {case._testMethodName for case in stages} != set(cls.LIFECYCLE_METHODS):
            return None
        if len(stages) != len(cls.LIFECYCLE_METHODS):
            raise ValueError('each Terrain Talent stage must be selected once')
        if any(hasattr(case, '_terrain_context') for case in stages):
            raise ValueError('Terrain Talent cases already have a context')
        indexed = {case._testMethodName: case for case in stages}
        stages = [indexed[name] for name in cls.LIFECYCLE_METHODS]
        context = {'case_ids': tuple(case.id() for case in stages), 'next_stage': 0}
        for case in stages:
            case._terrain_context = context
            bind_case_lifecycle(case, lambda reason: context.setdefault('blocked', reason))
        ordered, inserted = [], False
        for case in cases:
            if case._testMethodName in cls.LIFECYCLE_METHODS:
                if not inserted:
                    ordered.extend(stages)
                    inserted = True
            else:
                ordered.append(case)
        return ordered

    def begin_talent_stage(self):
        context = getattr(self, '_terrain_context', None)
        if context is None:
            return False
        stage = self.LIFECYCLE_METHODS.index(self._testMethodName)
        self.assertEqual(context['case_ids'][stage], self.id())
        if context.get('blocked') or context['next_stage'] != stage:
            raise __import__('unittest').SkipTest('blocked Terrain Talent predecessor: ' + str(context.get('blocked', context['next_stage'])))
        if not stage:
            return False
        previous = self.rules.rulings
        self.rules.rulings = context['rulings']
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self._terrain_world, self._terrain_records = context['world'], context['records']
        return True

    def talent_stage_input(self, stage):
        if getattr(self, '_terrain_context', None) is not None and stage:
            return self._terrain_world
        world = scene(self.rules, foe_moves=['move/스텔스록', 'move/냉동빔', 'move/화염방사'])
        for terrain in ('cave', 'mountain'):
            master(world['engine'], world['trainer'], terrain, minutes=7)
        env(world['engine'], world['trainer'], 'urban')
        self._terrain_world, self._terrain_records = world, {}
        # Standalone O_A is built through the same native actions, not earlier
        # test methods/assertions; a connected stage never calls this prefix.
        for index, transition in enumerate((cave_transition, forest_transition, arctic_transition)):
            if index >= stage:
                break
            self._terrain_records[index] = list(transition(world))
        return world

    def complete_talent_stage(self, stage):
        context = getattr(self, '_terrain_context', None)
        if context is not None:
            self.assertEqual(context['next_stage'], stage)
            completed = {'world': self._terrain_world, 'records': self._terrain_records,
                         'rulings': self._terrain_world['engine'].r.rulings, 'next_stage': stage + 1}
            defer_case_commit(self, lambda: context.update(completed))


def hazard_count(engine):
    return sum(len(envelope['instances']) for envelope in engine.hazards.values())


def cave_transition(world):
    engine, trainer, foe = (world[key] for key in ('engine', 'trainer', 'foe'))
    rocks = ((6, 1), (6, 3), (8, 0), (8, 4))
    battle(engine, foe)
    engine.use_move_on(foe, foe, 'move/스텔스록', engine.everyone, aim=rocks)
    yield 'placed', {'hazards': hazard_count(engine)}
    next_turn(engine, foe, trainer, count=10)
    hp = trainer.hp
    engine.approach(trainer, foe)
    yield 'unprotected', {'hp_before': hp, 'hp_after': trainer.hp, 'position': trainer.pos,
                          'hazards': hazard_count(engine)}
    acquire(engine, trainer, SC.TALENT, rank=1)
    yield 'unchosen', {}
    engine.survivalist_activity(trainer, 'choose_talents', terrains=['cave', 'mountain'])
    engine.end_of_turn(trainer)
    engine.end_round()
    battle(engine, trainer, count=10)
    origin = trainer.pos
    from grid import cheb
    import movement_actions as MOVEMENT
    import body_state as BODY
    candidates = []
    adjacent = BODY.in_range(engine, trainer, foe, 1)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx, dy) == (0, 0):
                continue
            q = (origin[0] + dx, origin[1] + dy)
            if not engine.grid.inside(q) or engine.grid.blocked(origin, q) or q in engine.occupied(trainer):
                continue
            if adjacent and not BODY.in_range(engine, trainer, foe, 1, left_position=q):
                continue  # Keep the real foe adjacent; do not suppress its unrelated native opportunity attack.
            entered = BODY.at_position(trainer, q) - BODY.at_position(trainer, origin)
            triggers = [row['id'] for point, envelope in engine.hazards.items() for row in envelope['instances']
                        if row['kind'] == 'stealth_rock' and any(cheb(point, cell) <= row['trigger_range'] for cell in entered)]
            if triggers and BODY.can_place(engine, trainer, q, origin=origin):
                cost = MOVEMENT.step_cost(origin, q, getattr(trainer, '_diagonal_steps', 0))[0]
                candidates.append((cost, q, (dx, dy), triggers))
    if not candidates:
        raise ValueError('no legal next native step enters a surviving Stealth Rock trigger')
    distance, destination, vector, triggers = min(candidates)
    engine.observe_relative_directions(trainer, directions={'surviving rock': vector},
        quickly_trip_placement='enter_passable', reason='GM observes direction to the surviving physical hazard')
    yield 'ready-immune', {'origin': origin, 'destination': destination, 'triggers': triggers}
    hp, count, log_start = trainer.hp, hazard_count(engine), len(engine.log_lines)
    engine.move_relative(trainer, direction='surviving rock', distance=distance, pace='slowly',
                         movement_id='survivalist/cave-immune-entry')
    yield 'immune', {'hp_before': hp, 'hp_after': trainer.hp, 'position': trainer.pos,
                    'destination': destination, 'hazards_before': count, 'hazards_after': hazard_count(engine),
                    'new_logs': engine.log_lines[log_start:]}
    engine.end_of_turn(trainer)
    engine.end_encounter()


def forest_transition(world):
    engine, trainer, foe = (world[key] for key in ('engine', 'trainer', 'foe'))
    yield 'before-forest', {}
    acquire(engine, trainer, SC.ADAPTIVE)
    for terrain in ('forest', 'tundra'):
        master(engine, trainer, terrain, minutes=7)
    # Record the real pre-Tundra source baseline before expanding the same actor.
    world['plain_ice'] = engine.roll_damage(foe, trainer, engine.r.move('move/냉동빔'), set_damage=True)
    world['plain_fire'] = engine.roll_damage(foe, trainer, engine.r.move('move/화염방사'), set_damage=True)
    talents(engine, trainer, 'cave', 'mountain', 'forest', 'tundra', rank=2)
    env(engine, trainer, 'urban')
    yield 'forest-chosen', {}


def arctic_transition(world):
    engine, trainer, partner, foe = (world[key] for key in ('engine', 'trainer', 'partner', 'foe'))
    yield 'damage', {'ice': engine.roll_damage(foe, trainer, engine.r.move('move/냉동빔'), set_damage=True),
                     'fire': engine.roll_damage(foe, trainer, engine.r.move('move/화염방사'), set_damage=True)}
    yield 'frozen', {'trainer_applied': engine.apply_status(trainer, '얼음'),
                     'partner_applied': engine.apply_status(partner, '얼음')}
    battle(engine, foe)
    engine.gm.set_weather('hail', rounds=5, reason='GM observed the hail')
    next_turn(engine, foe, trainer, count=15)
    hp = trainer.hp
    engine.end_of_turn(trainer)
    engine.end_round()
    engine.start_round(engine.everyone)
    engine.start_of_turn(trainer, initiative_count=15)
    yield 'hail-immune', {'hp_before': hp, 'hp_after': trainer.hp}
    engine.end_of_turn(trainer)
    hp = foe.hp
    engine.start_of_turn(foe, initiative_count=10)
    yield 'hail-foe', {'hp_before': hp, 'hp_after': foe.hp, 'loss': engine.tick_loss(foe)}
    engine.end_of_turn(foe)
    engine.end_encounter()


