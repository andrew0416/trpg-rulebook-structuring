"""Chef class scenario helpers (no tests): real static acquisition, cooking, serving and the GM lifetime ruling.

Every helper uses public engine entry points; nothing patches feats, classes, buffs or batches into state.
"""
from copy import deepcopy
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import chef_cooking as CHEF
import items as I
import nature_state as NATURE
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import world_entities as W

ALL_FEATURES = (CHEF.CLASS, CHEF.HITS, CHEF.ACCENTUATED, CHEF.AFTERTASTE, CHEF.DIETICIAN, CHEF.APPRECIATION, CHEF.DUMPLINGS)
STATS = dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 12)
INVENTORY = {'요리 세트': 1, '먹다남은음식': 2, '작은버섯': 4, '큰버섯': 1, '향기버섯': 1, '파워풀허브': 2, '하양허브': 2, '멘탈허브': 2,
             '오랭열매': 2, '오카열매': 1, '카리열매': 1, '버치열매': 1}
MOVES = ['move/몸통박치기', 'move/파괴광선']


def nature_for(rules, flavor, disposition):
    clean = lambda value: None if value is None else value.replace(' ', '')
    for name in rules.mech('pokemon/natures')['by_name']:
        row = NATURE.describe(rules, name)
        if clean(row['likes' if disposition == 'liked' else 'dislikes']) == clean(flavor):
            return name
    raise AssertionError('missing exact Nature for ' + flavor)


def trainer_spec(rules, name, *, intuition=6, edges=('edge/기본-요리',), items=None, money=2000, feats=(), classes=()):
    return build_trainer(rules, name, 20, STATS, extra={'classes': list(classes), 'feats': list(feats), 'edges': list(edges),
                         'skills': {'직감': intuition}, 'items': dict(INVENTORY if items is None else items), 'money': money})


def pokemon_spec(rules, trainer, name, *, nature=None, abilities=(), tutor_points=5):
    return build_pokemon(rules, '이브이', 20, name=name, nature=nature, moves=list(MOVES), abilities=list(abilities),
                         extra={'trainer_id': trainer.entity_id, 'trainer': trainer.name, 'tutor_points': tutor_points})


def acquire(engine, trainer, uid, *, request=None):
    return ACQUIRE.acquire_static(engine, trainer, uid, acquisition_request_id=request or ('chef/' + trainer.entity_id + '/' + uid))


def scene(rules, *, seed=77, feats=ALL_FEATURES, pokemon_nature=None, abilities=(), ally=False, intuition=6, register=True):
    """Chef trainer, its Pokemon and a foe; optionally an allied trainer with its own Pokemon."""
    engine = Engine(rules, seed=seed)
    chef = Combatant(rules, trainer_spec(rules, 'chef', intuition=intuition))
    engine.gm.add_combatant(chef, pos=(0, 0), side='party', reason='actual chef trainer')
    partner = Combatant(rules, pokemon_spec(rules, chef, 'partner', nature=pokemon_nature, abilities=abilities))
    engine.gm.add_combatant(partner, pos=(1, 0), side='party', reason='own Pokemon')
    world = {'engine': engine, 'chef': chef, 'partner': partner}
    if ally:
        friend = Combatant(rules, trainer_spec(rules, 'ally', items={'요리 세트': 1}, money=500))
        engine.gm.add_combatant(friend, pos=(1, 1), side='party', reason='allied trainer')
        companion = Combatant(rules, pokemon_spec(rules, friend, 'companion'))
        engine.gm.add_combatant(companion, pos=(1, 2), side='party', reason='allied Pokemon')
        world.update(ally=friend, companion=companion)
    foe = Combatant(rules, build_pokemon(rules, '이브이', 20, name='foe', moves=list(MOVES), abilities=[], extra={}))
    engine.gm.add_combatant(foe, pos=(2, 0), side='enemy', reason='opposing wild Pokemon')
    world['foe'] = foe
    for uid in feats:
        acquire(engine, chef, uid)
    if register and feats:
        I.register_feats(engine, chef)
    return world


def cook(engine, trainer, **options):
    options.setdefault('minutes', 5)
    options.setdefault('reason', 'GM-observed actual cooking time')
    return engine.pokemon_activity(trainer, 'cook_chef_food', **options)


def serve(engine, trainer, batch_id, target=None, **options):
    options.setdefault('minutes', 1)
    options.setdefault('reason', 'actual Extended intake')
    return engine.pokemon_activity(trainer, 'serve_chef_food', batch_id=batch_id, target=target, **options)


def ruling(engine, boundary, *, reason='explicit GM adjudication of the unprinted Accentuated Taste bonus duration'):
    engine.rulings.answers = [row for row in engine.rulings.answers if row['key'] != CHEF.RULING]
    engine.rulings.add_answer(CHEF.RULING, boundary, reason=reason, scope='permanent')


def pending(engine, trainer, source=None):
    rows = engine.pending_class_actor_state_actions(trainer)
    return [row for row in rows if source is None or row['source'] == source]


def decline_all(engine, *trainers):
    for trainer in trainers:
        for row in engine.pending_class_actor_state_actions(trainer):
            engine.resolve_class_actor_state_action(trainer, row['id'], use=False)


def battle(engine, actor, *, count=20):
    engine.start_round(engine.everyone)
    engine.start_of_turn(actor, initiative_count=count)


def restore(rules, engine):
    payload = json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False))
    loaded = CODEC.load_engine(rules, payload)
    return loaded, W.actor_index(loaded)


def receipt(actor):
    return actor.spec['food_consumption_receipts'][-1]
