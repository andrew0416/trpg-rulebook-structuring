"""Researcher Fields of Study: encounter-side Features on a grid scene (Fistful of Force, Rainbow Light, Chemical Warfare,
Caustic Chemistry, Temperature Control, Extreme Weather, Prehistoric Razors/Relic Sash, Ancient Heritage's damage class)."""
from copy import deepcopy
from unittest.mock import patch
import json
import unittest

import test_book_researcher_fields_crafting as fixture
from engine import Rules, Engine, Combatant
from grid import Grid
from builder import build_pokemon
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import action_points as AP
import class_passive_combat as CLASS_PASSIVE
import combat_precision_features as CPF
import combat_timing as TIMING
import items as ITEMS
import pester_balls as PESTER
import researcher_fields as RFS
import researcher_features as RF
import state_codec as CODEC
import weather_state as WEATHER
import world_entities as WORLD

COMMON = dict(level=30, size='중형', stats={'hp': 100, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20}, abilities=[], types=['노말'],
              movement={'land': 6, 'swim': 0, 'sky': 0, 'power': 4}, weight_kg=30, skills=dict(fixture.SKILLS))


class ResearcherFieldsCombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    rejected = fixture.ResearcherFieldsCraftingTests.rejected
    valid = fixture.ResearcherFieldsCraftingTests.valid
    restore = fixture.ResearcherFieldsCraftingTests.restore
    new_day = fixture.ResearcherFieldsCraftingTests.new_day

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.e = Engine(self.rules, seed=20862128)
        self.e.grid = Grid(14, 12)
        self.t = self.add('actual Researcher', 'trainer', (1, 1), classes=['class/연구원'], feats=list(fixture.ALL_FEATURES), edges=list(fixture.EDGES),
                          feature_choices={'class/연구원': deepcopy(fixture.FIELDS)}, feat_ranks={RFS.SEED_BAG: 2}, items={}, money=10000, moves=[], shards={'빨강': 3}, speed=30)

    def add(self, name, kind, pos, speed=None, side='party', **extra):
        spec = dict(deepcopy(COMMON), name=name, kind=kind)
        if speed is not None:
            spec['stats'] = dict(spec['stats'], spe=speed)   # distinct Speeds keep initiative schedules tie-free
        spec.update(extra)
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, pos=pos, side=side, reason='actual Researcher scene participant')
        prepare_body(self.e, actor, size='중형', offsets=[(0, 0)], reason='observed complete body')
        if kind == 'pokemon' and extra.get('trainer_id'):
            self.e.gm.observe_loyalty(actor, 6, reason='actual willing Pokemon')
        return actor

    def combat(self, actor, *, count=30):
        self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor, initiative_count=count)

    def next_turn(self, actor, *, count=30):
        if self.e._active_turn_actor is None:   # a codec-restored engine resumes at a fresh round
            return self.combat(actor, count=count)
        self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round()
        self.combat(actor, count=count)

    def use(self, actor, target, move, *, face=10, **options):
        if move not in actor.moves:
            self.e.gm.set_move(actor, move, reason='actual complete known Move list')
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.use_move_on(actor, target, move, self.e.everyone, **options)

    def restored(self, species, name, pos=(2, 2)):
        """A natively restored, hatched and sent-out fossil Pokemon of the Researcher."""
        import skill_modifiers as SKILLS
        self.t.spec['items']['복원기'] = 1
        if 'pokemon_party_policy' not in self.t.spec:
            self.e.pokemon_activity(self.t, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'fossil', phase='search', site={'name': 'GM deposit', 'fossils_present': True}, dc=15, minutes=120,
                                discovery={'id': name, 'species': 'pokemon/' + species}, fixed=[6] * SKILLS.rank(self.rules, self.t, '포켓몬학')[2])
        egg = self.e.pokemon_activity(self.t, 'fossil', phase='restore', fossil_id=name)['egg']
        import growth_milestones as MILESTONES
        basics = MILESTONES.ability_options(self.rules, {'species': egg['species'], 'abilities': []}, 'creation')
        self.assertTrue(basics, 'restored species must provide its actual Basic birth candidates')
        details = dict(gender='female', nature='노력', abilities=[basics[0]], moves=[], inheritance_moves=[], special_appearance=False)
        k = self.e.pokemon_activity(self.t, 'hatch_fossil', egg_id=egg['id'], name=name, ready=True, reason='GM confirmed readiness', details=details)['pokemon']
        prepare_body(self.e, k, size=k.spec.get('size') or '소형', offsets=[(0, 0)], reason='observed complete body')
        self.e.gm.observe_loyalty(k, 6, reason='actual willing Pokemon')
        self.e.gm.send_out(k, pos, reason='actual deployment')
        return k

    # ------------------------------------------------------------ Artificer
    def test_fistful_of_force_destroys_the_held_shard_uses_judgement_of_a_shard_type_with_occult_rank_x3_once_per_scene(self):
        f = self.add('foe', 'pokemon', (4, 1), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
        self.rejected(lambda: RFS.hold_shard(self.e, self.t, '파랑', '주요손'), 'owned shard of that colour')
        self.rejected(lambda: RFS.hold_shard(self.e, self.t, '빨강', '머리'), 'main hand')
        self.rejected(lambda: RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='불꽃'), 'requires a shard in the main or off hand')
        self.combat(self.t)
        held = RFS.hold_shard(self.e, self.t, '빨강', '주요손')
        self.assertEqual((held['color'], self.t.spec['shards']['빨강'], self.t.budget['swift']), ('빨강', 2, 0))
        self.rejected(lambda: RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='물'), 'held shard colour types')
        self.t.spec['skills']['오컬트학'] = 5
        self.rejected(lambda: RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='불꽃'), 'Fistful of Force requires its printed skill rank')
        self.t.spec['skills']['오컬트학'] = 6
        before = f.hp
        with patch.object(Engine, 'd20', return_value=15):
            out = RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='불꽃')
        self.assertEqual((out['type'], out['attack_bonus'], out['shard']['color']), ('불꽃', 18, '빨강'))
        self.assertLess(f.hp, before)
        self.assertIsNone(self.t.spec[RFS.KEY]['held_shard'])
        self.assertIsNone(self.t.spec[RFS.KEY]['fistful'])
        self.assertEqual(self.t.moves, [])
        self.assertTrue(any('심판의뭉치(불꽃)' in line for line in self.e.log_lines))
        dealt = before - f.hp
        self.next_turn(self.t)
        RFS.hold_shard(self.e, self.t, '빨강', '반대손')
        self.rejected(lambda: RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='페어리'), 'already used this scene')
        self.e.end_scene()
        self.combat(self.t)
        # Judgement itself is a Daily Move: the new scene allows Fistful again, but the Move frequency refuses before the shard is spent.
        self.rejected(lambda: RFS.fistful_of_force(self.e, self.t, f, self.e.everyone, move_type='페어리'), 'Judgement frequency refuses')
        self.assertEqual((self.t.spec[RFS.KEY]['held_shard']['hand'], self.t.spec['shards']['빨강']), ('반대손', 1))
        self.assertGreater(dealt, 0)
        self.valid()
        self.restore('t')

    def test_rainbow_light_needs_the_worn_rainbow_gem_costs_two_ap_and_gives_allies_three_effect_range_for_one_round(self):
        self.p = p = self.add('ally', 'pokemon', (2, 2), trainer_id=self.t.entity_id, species='피카츄', types=['전기'], moves=['move/전광석화'], speed=25)
        self.f = f = self.add('foe', 'pokemon', (4, 1), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
        self.rejected(lambda: RFS.rainbow_light(self.e, self.t), 'Standard action in an active encounter')
        self.combat(self.t)
        self.rejected(lambda: RFS.rainbow_light(self.e, self.t), 'wearing the actual Rainbow Gem')
        ITEMS.register_item(self.e, self.t, '무지개주얼')
        self.t.spec['skills']['오컬트학'] = 4
        self.rejected(lambda: RFS.rainbow_light(self.e, self.t), 'Rainbow Light requires its printed skill rank')
        self.t.spec['skills']['오컬트학'] = 6
        ap = AP.available(self.t)
        move = self.rules.move('move/전광석화')
        base = CPF.effect_natural(self.e, p, move, 10)
        out = RFS.rainbow_light(self.e, self.t)
        self.assertEqual((out['effect_range'], AP.available(self.t), self.t.budget['standard']), (3, ap - 2, 0))
        self.assertEqual((RFS.effect_range_bonus(self.e, p, move), RFS.effect_range_bonus(self.e, self.t, move), RFS.effect_range_bonus(self.e, f, move)), (3, 3, 0))
        self.assertEqual(CPF.effect_natural(self.e, p, move, 10), base + 3)
        self.rejected(lambda: RFS.rainbow_light(self.e, self.t), 'already active')
        self.restore('t', 'p', 'f')
        self.assertEqual(RFS.effect_range_bonus(self.e, self.p, move), 3)
        self.next_turn(self.p)
        self.assertEqual([r.get('source') for r in TIMING.records(self.t)], [RFS.RAINBOW])
        self.next_turn(self.t)   # one full round: the rainbow ends as the Researcher's next turn begins
        self.assertEqual(TIMING.records(self.t), [])
        self.assertEqual(RFS.effect_range_bonus(self.e, self.p, move), 0)
        self.valid()

    # ------------------------------------------------------------ Chemistry
    def test_chemical_warfare_bursts_the_pester_ball_and_caustic_chemistry_drains_every_exposed_target_once_per_scene(self):
        self.t.spec['items'].update({uid: 3 for uid in PESTER.VARIANTS})
        self.t.spec['skills'].update({'육상': 2, '곡예': 4})
        f1 = self.add('f1', 'pokemon', (3, 1), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
        f2 = self.add('f2', 'pokemon', (4, 2), side='foe', species='이상해씨', types=['풀'], moves=['move/몸통박치기'], speed=12)
        f3 = self.add('f3', 'pokemon', (9, 9), side='foe', species='이상해씨', types=['풀'], moves=['move/몸통박치기'], speed=11)
        self.combat(self.t)
        self.rejected(lambda: RFS.caustic_chemistry(self.e, self.t, fixed=[3] * 6), 'needs your actual Pester Ball hit or Repel spray')
        self.t.spec['skills']['기술학'] = 3
        self.rejected(lambda: RFS.chemical_warfare(self.e, self.t), 'Chemical Warfare requires its printed skill rank')
        self.t.spec['skills']['기술학'] = 6
        RFS.chemical_warfare(self.e, self.t)
        self.rejected(lambda: RFS.chemical_warfare(self.e, self.t), 'already declared')
        out = self.e.use_item(self.t, 'item/오물탄-잠듦', f1, fixed_accuracy=20)
        self.assertTrue(out['hit'] and out['status_applied'])
        self.assertEqual([row['target_id'] for row in out['chemical_warfare']], [f2.entity_id])
        self.assertEqual(('잠듦' in f1.conditions, '잠듦' in f2.conditions, '잠듦' in f3.conditions), (True, True, False))
        exposure = self.t.spec[RFS.KEY]['chemistry']['exposures'][-1]
        self.assertEqual((exposure['kind'], exposure['targets']), ('pester', [f1.entity_id, f2.entity_id]))
        ap = AP.available(self.t)
        self.t.spec['skills']['기술학'] = 4
        self.rejected(lambda: RFS.caustic_chemistry(self.e, self.t, fixed=[3] * 4), 'Caustic Chemistry requires its printed skill rank')
        self.t.spec['skills']['기술학'] = 6
        hp = (f1.hp, f2.hp, f3.hp)
        out = RFS.caustic_chemistry(self.e, self.t, fixed=[3] * 6)
        self.assertEqual((out['roll'], [row['hp_loss'] for row in out['targets']], AP.available(self.t), self.t.budget['swift']), (18, [18, 18], ap - 1, 0))
        self.assertEqual((f1.hp, f2.hp, f3.hp), (hp[0] - 18, hp[1] - 18, hp[2]))
        self.rejected(lambda: RFS.caustic_chemistry(self.e, self.t, fixed=[3] * 6), 'needs your actual Pester Ball hit')
        self.next_turn(self.t)
        self.e.use_item(self.t, 'item/오물탄-화상', f1, fixed_accuracy=20)
        out = RFS.caustic_chemistry(self.e, self.t, fixed=[3] * 6)
        self.assertEqual(out['targets'][0].get('skipped'), 'already affected this scene')
        self.next_turn(self.t)
        RFS.chemical_warfare(self.e, self.t)
        self.e.use_item(self.t, 'item/오물탄-독', f2, fixed_accuracy=20)
        self.next_turn(self.t)
        self.rejected(lambda: RFS.chemical_warfare(self.e, self.t), 'already used twice this scene')
        self.valid()
        self.restore('t')

    def test_a_direct_repel_spray_is_also_a_caustic_chemistry_trigger(self):
        self.t.spec['items'].update({'item/벌레회피스프레이': 2})
        self.t.spec['skills'].update({'육상': 2, '곡예': 4})
        f = self.add('foe', 'pokemon', (3, 1), side='foe', species='이상해씨', types=['풀'], moves=['move/몸통박치기'], speed=15, level=10)
        self.combat(self.t)
        self.e.use_item(self.t, 'item/벌레회피스프레이', f, fixed_accuracy=20, aim={'reason': 'GM: direct spray at the target', 'reachable': True})
        exposure = self.t.spec[RFS.KEY]['chemistry']['exposures'][-1]
        self.assertEqual((exposure['kind'], exposure['targets']), ('spray', [f.entity_id]))
        hp = f.hp
        out = RFS.caustic_chemistry(self.e, self.t, fixed=[2] * 6)
        self.assertEqual((out['roll'], f.hp), (12, hp - 12))
        self.restore('t')

    # ------------------------------------------------------------ Climatology
    def test_temperature_control_lets_the_next_move_weather_coexist_and_the_survivor_continues_until_a_new_weather_replaces_both(self):
        self.p = p = self.add('ally', 'pokemon', (2, 2), trainer_id=self.t.entity_id, species='이상해씨', types=['풀'], moves=['move/비바라기', 'move/쾌청', 'move/싸라기눈'], speed=25)
        self.f = f = self.add('foe', 'pokemon', (5, 2), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
        self.combat(p)
        self.rejected(lambda: RFS.temperature_control(self.e, self.t), 'non-standard weather already in effect')
        self.use(p, p, 'move/비바라기')
        self.assertEqual(WEATHER.effective_weathers(self.e), ('rain',))
        self.next_turn(self.t)
        ap = AP.available(self.t)
        out = RFS.temperature_control(self.e, self.t)
        self.assertEqual((out['turn_serial'], AP.available(self.t)), (1, ap - 1))
        self.rejected(lambda: RFS.temperature_control(self.e, self.t), 'already declared')
        self.next_turn(p, count=25)
        self.use(p, p, 'move/쾌청')
        state = WEATHER.state(self.e)
        self.assertEqual((self.e.weather, WEATHER.effective_weathers(self.e), [x['weather'] for x in state['layers']]), ('rain', ('rain', 'sunny'), ['sunny']))
        self.assertEqual(state['layers'][0]['temperature_control']['trainer_id'], self.t.entity_id)
        self.assertIsNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.restore('t', 'p', 'f')
        p, f = self.p, self.f
        rain_end = WEATHER.state(self.e)['active']['deadline_round']
        while self.e.round_no < rain_end + 1:
            self.next_turn(f, count=15)
            self.next_turn(p, count=25)
        self.assertEqual((self.e.weather, WEATHER.effective_weathers(self.e), WEATHER.state(self.e)['layers']), ('sunny', ('sunny',), []))
        self.use(p, p, 'move/싸라기눈')   # a new weather with no declaration replaces the survivor
        self.assertEqual((self.e.weather, WEATHER.effective_weathers(self.e)), ('hail', ('hail',)))
        self.valid()

    def test_temperature_control_lapses_at_the_researchers_next_turn_and_only_a_move_or_ability_weather_layers(self):
        p = self.add('ally', 'pokemon', (2, 2), trainer_id=self.t.entity_id, species='이상해씨', types=['풀'], moves=['move/비바라기', 'move/쾌청'], speed=25)
        self.combat(p)
        self.use(p, p, 'move/비바라기')
        self.next_turn(self.t)
        RFS.temperature_control(self.e, self.t)
        self.next_turn(p, count=25)
        self.next_turn(self.t)   # the Researcher's next turn begins without a weather trigger
        self.next_turn(p, count=25)
        self.use(p, p, 'move/쾌청')
        self.assertEqual((self.e.weather, WEATHER.state(self.e).get('layers', [])), ('sunny', []))
        self.next_turn(self.t)
        RFS.temperature_control(self.e, self.t)
        self.e.gm.set_weather('hail', rounds=5, reason='GM weather is not a Move or Ability trigger')
        self.assertEqual((self.e.weather, WEATHER.state(self.e).get('layers', [])), ('hail', []))
        self.assertIsNotNone(self.t.spec[RFS.KEY]['climatology']['temperature_control'])
        self.valid()

    def test_extreme_weather_hail_and_sandstorm_penalise_damaged_actors_rain_slows_and_sun_suppresses_until_the_weather_ends(self):
        cases = (('move/싸라기눈', 'hail', {'damage_roll': -5}, None), ('move/모래바람', 'sandstorm', {'accuracy': -2}, None),
                 ('move/비바라기', 'rain', None, '둔화'), ('move/쾌청', 'sunny', None, '억압'))
        for move, weather, penalty, status in cases:
            with self.subTest(weather=weather):
                self.setUp()
                self.p = p = self.add('ally', 'pokemon', (2, 2), trainer_id=self.t.entity_id, species='이상해씨', types=['풀'], moves=[move, 'move/몸통박치기'], speed=25)
                self.f = f = self.add('foe', 'pokemon', (3, 2), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
                self.g = g = self.add('water foe', 'pokemon', (6, 6), side='foe', species='꼬부기', types=['물'], moves=['move/몸통박치기'], speed=14)
                self.combat(p)
                self.rejected(lambda: RFS.extreme_weather(self.e, self.t), 'weather you or your Pokemon created this round')
                self.use(p, p, move)
                self.t.spec['skills']['생존'] = 5
                self.rejected(lambda: RFS.extreme_weather(self.e, self.t), 'Extreme Weather requires its printed skill rank')
                self.t.spec['skills']['생존'] = 6
                out = RFS.extreme_weather(self.e, self.t)
                self.assertEqual(out['feature'], RFS.EXTREME)
                if status is not None:
                    # Electric foe: always; Water foe: only Sun (Rain exempts Water); Grass ally: exempt from both
                    self.assertEqual((status in f.conditions, status in g.conditions, status in p.conditions), (True, weather == 'sunny', False))
                    self.assertIn(f.entity_id, out['statuses'])
                self.next_turn(f, count=15)
                if penalty is not None:
                    self.assertEqual(f.custom_conditions['researcher_extreme_weather'].get('damage_roll', 0), penalty.get('damage_roll', 0))
                    self.assertEqual(CLASS_PASSIVE.damage_roll_modifier(self.e, f, p, self.rules.move('move/전광석화'), 1), penalty.get('damage_roll', 0))
                    self.assertEqual(CLASS_PASSIVE.accuracy_bonus(self.e, f, p, self.rules.move('move/전광석화'), self.rules.move_mech('move/전광석화')[0]), penalty.get('accuracy', 0))
                    self.assertNotIn('researcher_extreme_weather', p.custom_conditions)   # Grass is immune to both tick weathers
                else:
                    self.assertIn(status, f.conditions)
                self.restore('t', 'p', 'f', 'g')
                p, f = self.p, self.f
                deadline = WEATHER.state(self.e)['active']['deadline_round']
                while self.e.round_no <= deadline:
                    self.next_turn(f, count=15)
                    self.next_turn(p, count=25)
                self.assertIsNone(self.e.weather)
                self.assertNotIn('researcher_extreme_weather', f.custom_conditions)
                if status is not None:
                    self.assertNotIn(status, f.conditions)
                self.valid()
        self.setUp()
        p = self.add('ally', 'pokemon', (2, 2), trainer_id=self.t.entity_id, species='이상해씨', types=['풀'], moves=['move/싸라기눈', 'move/모래바람', 'move/비바라기', 'move/쾌청'], speed=25)
        self.combat(p)
        for move in ('move/싸라기눈', 'move/모래바람', 'move/비바라기'):   # each weather Move is Daily x2: three different Moves
            self.use(p, p, move)
            RFS.extreme_weather(self.e, self.t)
            self.e.end_scene()
            self.next_turn(p, count=25)
        self.use(p, p, 'move/쾌청')
        self.rejected(lambda: RFS.extreme_weather(self.e, self.t), 'daily uses exhausted')

    # ------------------------------------------------------------ Paleontology relics in combat
    def test_prehistoric_razors_make_a_damaging_melee_attacker_lose_a_tick_and_the_relic_sash_adds_two_evasion_against_status_moves(self):
        k = self.restored('방패톱스', 'razors')
        RF.equip_relic(self.e, self.t, k, RFS.craft_relic(self.e, self.t, k, relic='def', minutes=10)['id'])
        f = self.add('foe', 'pokemon', (3, 2), side='foe', species='피카츄', types=['전기'], moves=['move/몸통박치기', 'move/전기쇼크'], speed=15)
        self.combat(f)
        hp = f.hp
        self.use(f, k, 'move/몸통박치기', face=15)
        self.assertEqual((f.hp, k.spec.get('researcher_relic_reactions')), (hp, None))   # no standing reaction declared
        self.rejected(lambda: RFS.set_razors_reaction(self.e, k, 'yes'), 'explicit reaction policy')
        RFS.set_razors_reaction(self.e, k, True)
        self.next_turn(f, count=15)
        hp = f.hp
        self.use(f, k, 'move/몸통박치기', face=15)
        self.assertEqual((hp - f.hp, k.spec['researcher_relic_reactions'][-1]['hp_loss']), (self.e.tick_loss(f), self.e.tick_loss(f)))
        self.next_turn(f, count=15)
        hp = f.hp
        self.use(f, k, 'move/전기쇼크', face=15)   # ranged damaging hit: no reaction
        self.assertEqual((hp, len(k.spec['researcher_relic_reactions'])), (f.hp, 1))
        self.restore('t')
        self.setUp()
        k = self.restored('프테라', 'sash')
        RF.equip_relic(self.e, self.t, k, RFS.craft_relic(self.e, self.t, k, relic='spe', minutes=10)['id'])
        f = self.add('foe', 'pokemon', (3, 2), side='foe', species='피카츄', types=['전기'], moves=['move/꼬리흔들기', 'move/전광석화'], speed=15)
        self.combat(f)
        need = self.rules.move('move/꼬리흔들기')['ac'] + k.evasion('변화') + 2
        self.use(f, k, 'move/꼬리흔들기', face=need - 1)
        self.assertEqual(k.stages['def'], 0)
        self.next_turn(f, count=15)
        self.use(f, k, 'move/꼬리흔들기', face=need)
        self.assertEqual(k.stages['def'], -1)
        self.valid()

    def test_ancient_heritage_turns_an_eighteen_plus_ancient_power_into_the_declared_damage_class_once(self):
        k = self.restored('프테라', 'ancient')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=6, reason='GM establishes the actual balance')
        RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='actual teaching')
        f = self.add('foe', 'pokemon', (3, 2), side='foe', species='피카츄', types=['전기'], moves=['move/전광석화'], speed=15)
        self.combat(k)
        RFS.choose_ancient_power_class(self.e, k, '물리')
        hp = f.hp
        self.use(k, f, 'move/원시의힘', face=18, set_damage=True)
        physical = hp - f.hp
        self.assertTrue(any('고대 유산: 18+ 원시의힘 → 물리' in line for line in self.e.log_lines))
        self.assertIsNone(k.spec.get('researcher_ancient_power_choice'))
        self.next_turn(f, count=15)
        self.next_turn(k)
        self.next_turn(f, count=15)
        self.next_turn(k)
        hp = f.hp
        self.use(k, f, 'move/원시의힘', face=18, set_damage=True)   # no declaration: the printed Special class
        special = hp - f.hp
        self.assertNotEqual(physical, special)
        self.next_turn(f, count=15)
        self.next_turn(k)
        self.next_turn(f, count=15)
        self.next_turn(k)
        RFS.choose_ancient_power_class(self.e, k, '물리')
        hp = f.hp
        self.use(k, f, 'move/원시의힘', face=17, set_damage=True)   # below 18: the declaration lapses with the use
        self.assertEqual((hp - f.hp, k.spec.get('researcher_ancient_power_choice')), (special, None))
        self.valid()


if __name__ == '__main__':
    unittest.main()
