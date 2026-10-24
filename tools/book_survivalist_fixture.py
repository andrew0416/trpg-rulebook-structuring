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
    for sender in (trainer, *([world["ally"]] if ally else [])):
        for target in engine.everyone:
            if target is not sender and target.side==sender.side:
                engine.gm.observe_sensory_environment(sender,target,paths={"auditory":True},present=True,reason="actual audible Guide Order")
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
