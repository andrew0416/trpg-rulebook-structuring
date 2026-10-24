"""F-31 remaining numeric effects through their native public consumers.

Fixtures declare already-owned sheet Features and Virtuoso before actor creation.
No acquisition is manufactured by appending Features or Classes after creation.
"""
from copy import copy, deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools'), str(ROOT/'examples')]
from engine import Engine, Rules
from grid import Grid
from rulings import Rulings
from declared_skill_ranks import configure
from native_scenario_fixture import assert_rejected_unchanged
import action_points as AP
import researcher_fields as RESEARCH
import skill_modifiers as SKILLS
import taskmaster as TASK
import test_book_researcher_fields_crafting as CRAFT
import test_book_researcher_fields_combat as COMBAT
import test_book_researcher_fields_pokemon as POKEMON

VIRTUOSO = 'edge/거장'
CASES = ((6, True, 8), (7, False, 7), (10, False, 10), (10, True, 8))


class RemainingEffectRankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Rules(ROOT, ruleset='core')

    def rules(self):
        rules = copy(self.base)
        rules.rulings = Rulings()
        configure(rules)
        return rules

    def choices(self, skill, virtuoso):
        return dict(edges=[*CRAFT.fixture_edges(), *([VIRTUOSO] if virtuoso else [])],
                    edge_choices={VIRTUOSO: [skill]} if virtuoso else {})

    def crafting(self, skill, rank, virtuoso, *, pokemon_fixture=False):
        cls = POKEMON.ResearcherFieldsPokemonTests if pokemon_fixture else CRAFT.ResearcherFieldsCraftingTests
        f = cls('runTest')
        f.rules = self.rules()
        f.setup(skills={skill: rank}, **self.choices(skill, virtuoso))
        return f

    def combat(self, skill, rank, virtuoso, *, press=False):
        f = COMBAT.ResearcherFieldsCombatTests('runTest')
        f.rules = self.rules()
        f.e = Engine(f.rules, seed=20862128)
        f.e.grid = Grid(14, 12)
        f.t = f.add('effect rank owner', 'trainer', (1, 1), speed=30,
                    classes=[] if press else ['class/연구원'],
                    feats=[TASK.PRESS_ACTION] if press else list(CRAFT.ALL_FEATURES),
                    skills=dict(CRAFT.SKILLS, **{skill: rank}),
                    feature_choices={} if press else {'class/연구원': deepcopy(CRAFT.FIELDS)},
                    feat_ranks={RESEARCH.SEED_BAG: 2}, items={}, money=10000,
                    moves=[], shards={'빨강': 3}, **self.choices(skill, virtuoso))
        return f

    def ordinary_pool(self, f, skill, rank):
        dice = 6 if rank == 6 else 7
        self.assertEqual(SKILLS.rank(f.e.r, f.t, skill)[1:], (str(dice)+'d6', rank))
        result = f.e.skill_roll(f.t, skill, fixed=[2]*dice)
        self.assertEqual((result.rank, result.dice_count, result.total), (rank, dice, 2*dice))

    def test_press_native_obedience_roll_adds_half_effect_rank_to_ordinary_dice(self):
        for rank, virtuoso, effect in CASES:
            with self.subTest(rank=rank, virtuoso=virtuoso):
                f = self.combat('협박', rank, virtuoso, press=True)
                p = f.add('actual owned target', 'pokemon', (2, 1), speed=25,
                          trainer_id=f.t.entity_id, species='피카츄')
                q = f.add('other owned target', 'pokemon', (2, 2), speed=20,
                          trainer_id=f.t.entity_id, species='피카츄')
                f.combat(f.t)
                before = p.hp
                f.e.manual_feat(f.t, TASK.PRESS_ACTION, p,
                                adjustment={'stats': ['atk', 'spe'], 'obedience': True})
                self.assertEqual((p.stages['atk'], p.stages['spe'], f.t.budget['standard']), (1, 1, 0))
                self.assertEqual(before-p.hp, p.base_max_hp//6)
                dice = 6 if rank == 6 else 7
                result = f.e.skill_roll(f.t, '협박', fixed=[2]*dice,
                                       skill_context={'purpose': 'pokemon_obedience'}, skill_target=p)
                self.assertEqual((result.rank, result.dice_count, result.modifier, result.total),
                                 (rank, dice, effect//2, 2*dice+effect//2))
                other = f.e.skill_roll(f.t, '협박', fixed=[2]*dice,
                                      skill_context={'purpose': 'pokemon_obedience'}, skill_target=q)
                self.assertEqual(other.modifier, 0)

    def test_medical_techniques_native_patch_heals_tick_plus_effect_rank(self):
        for rank, virtuoso, effect in CASES:
            with self.subTest(rank=rank, virtuoso=virtuoso):
                f = self.crafting('의학', rank, virtuoso)
                f.t.spec['items']['상처약'] = 1
                p = f.pokemon('이상해씨', 30, 'actual patient')
                RESEARCH.patch_cure(f.e, f.t, '상처약', seconds=600, reason='native patch extraction')
                f.e.gm.set_hp(p, value=1, reason='actual injured patient')
                before_ap = AP.available(f.t)
                out = RESEARCH.apply_patch(f.e, f.t, 'patch:item/상처약', p,
                                           seconds=600, reason='native Medical Techniques', medical_techniques=True)
                tick = f.e.tick(p)
                self.assertEqual(out['medical_techniques'], {'heal': tick+effect, 'tick': tick, 'medicine_rank': effect})
                self.assertEqual(p.hp, min(p.base_max_hp, 1+20+tick+effect))
                self.assertEqual((AP.available(f.t), f.t.spec['items']['patch:item/상처약']), (before_ap-1, 2))
                self.ordinary_pool(f, '의학', rank)

    def test_fistful_native_damage_reads_the_paid_effect_rank_times_three(self):
        for rank, virtuoso, effect in CASES:
            with self.subTest(rank=rank, virtuoso=virtuoso):
                f = self.combat('오컬트학', rank, virtuoso)
                foe = f.add('actual foe', 'pokemon', (4, 1), side='foe', speed=15,
                            species='피카츄', types=['전기'], moves=['move/전광석화'])
                f.combat(f.t)
                RESEARCH.hold_shard(f.e, f.t, '빨강', '주요손')
                original = RESEARCH.attack_stat_value
                observed = []
                def observe(engine, attacker, move, value):
                    result = original(engine, attacker, move, value)
                    if attacker is f.t and '_researcher_fistful' in move:
                        observed.append(result)
                    return result
                before = foe.hp
                with patch.object(Engine, 'd20', return_value=15), patch.object(RESEARCH, 'attack_stat_value', observe):
                    out = RESEARCH.fistful_of_force(f.e, f.t, foe, f.e.everyone, move_type='불꽃')
                self.assertTrue(observed)
                self.assertEqual(set(observed), {effect*3})
                self.assertEqual(out['attack_bonus'], effect*3)
                self.assertLess(foe.hp, before)
                self.assertIsNone(f.t.spec[RESEARCH.KEY]['fistful'])
                self.assertIsNone(f.t.spec[RESEARCH.KEY]['held_shard'])
                self.assertEqual(f.t.moves, [])
                self.ordinary_pool(f, '오컬트학', rank)

    def upgrades(self):
        return ([{'kind': 'shiny_contest', 'contest_stat': '근사함'}]
                + [{'kind': 'inheritance_move', 'move': move} for move in ('move/저주', 'move/버티기', 'move/깃털댄스')]
                + [{'kind': 'base_stat', 'stat': stat} for stat in ('hp', 'atk', 'def', 'spa', 'spd')])

    def synthesize(self, f, upgrades):
        return RESEARCH.playing_god(f.e, f.t, species='코일', nature='겁쟁이', ability='옹골참',
                                   gender='무성', upgrades=upgrades, seconds=3600,
                                   reason='native Technology effect upgrades', request_id='effect-rank/egg')

    def test_playing_god_effect_upgrade_count_reaches_native_birth_without_learning_inheritance(self):
        for rank, virtuoso, effect in (CASES[0], CASES[1], CASES[3]):
            with self.subTest(rank=rank, virtuoso=virtuoso):
                f = self.crafting('기술학', rank, virtuoso)
                f.t.spec['items']['화학 세트'] = 1
                upgrades = self.upgrades()[:effect]
                assert_rejected_unchanged(f.e, lambda: self.synthesize(f, upgrades[:-1]),
                                          reason_pattern='one upgrade per Technology rank')
                row = self.synthesize(f, upgrades)
                egg = f.t.spec['eggs'][0]
                self.assertEqual((egg[RESEARCH.EGG_MARK]['technology_rank'], len(egg[RESEARCH.EGG_MARK]['upgrades'])), (effect, effect))
                self.assertEqual(f.t.spec['money'], 6500)
                f.e.advance_time(86400, [f.t])
                child = RESEARCH.hatch_artificial(f.e, f.t, row['egg_entity_id'], name='native rank child', reason='actual hatching')['pokemon']
                self.assertEqual((child.level, child.spec['gender'], child.spec['nature']), (5, '무성', '겁쟁이'))
                self.assertEqual(child.spec['inheritance_moves'], ['move/저주', 'move/버티기', 'move/깃털댄스'])
                self.assertTrue(set(child.spec['inheritance_moves']).isdisjoint(child.moves))
                self.assertEqual(RESEARCH.vitamin_equivalents(child.spec), effect-4)
                self.ordinary_pool(f, '기술학', rank)

    def test_playing_god_declared_ten_keeps_exact_count_and_printed_nine_upgrade_ceiling(self):
        f = self.crafting('기술학', 10, False)
        f.t.spec['items']['화학 세트'] = 1
        upgrades = self.upgrades()
        assert_rejected_unchanged(f.e, lambda: self.synthesize(f, upgrades),
                                  reason_pattern='one upgrade per Technology rank')
        assert_rejected_unchanged(f.e, lambda: self.synthesize(f, upgrades+[{'kind': 'base_stat', 'stat': 'spe'}]),
                                  reason_pattern='upgrade limit exceeded')
        self.ordinary_pool(f, '기술학', 10)

    def fossil(self, f, number, dice):
        f.t.spec['items']['복원기'] = 1
        f.e.pokemon_activity(f.t, 'fossil', phase='search', site={'name': 'observed deposit', 'fossils_present': True},
                             dc=15, minutes=120, discovery={'id': 'rank-fossil-'+str(number), 'species': 'pokemon/프테라'}, fixed=[6]*dice)
        egg = f.e.pokemon_activity(f.t, 'fossil', phase='restore', fossil_id='rank-fossil-'+str(number))['egg']
        return next(row for row in f.t.spec['eggs'] if row['entity_id'] == egg['entity_id'])

    def test_special_lifetime_capacity_counts_native_egg_uses_and_stops_at_effect_rank_minus_two(self):
        for rank, virtuoso, effect in (CASES[0], CASES[1], CASES[2]):
            with self.subTest(rank=rank, virtuoso=virtuoso):
                f = self.crafting('포켓몬학', rank, virtuoso, pokemon_fixture=True)
                f.e.pokemon_activity(f.t, 'party_policy', mode='unlimited', reason='actual carrying policy', roster=[])
                self.assertEqual(RESEARCH.special_uses(f.e, f.t), effect-2)
                dice = 6 if rank == 6 else 7
                first = None
                for number in range(effect-2):
                    egg = self.fossil(f, number, dice)
                    if first is None:
                        first = egg
                    result = RESEARCH.special_quality(f.e, f.t, egg['entity_id'], quality='GM quality '+str(number), reason='GM decision')
                    self.assertEqual(result['quality'], 'GM quality '+str(number))
                extra = self.fossil(f, effect-2, dice)
                assert_rejected_unchanged(f.e, lambda: RESEARCH.special_quality(f.e, f.t, extra['entity_id'], quality='overflow', reason='GM decision'),
                                          reason_pattern='once per Pokemon Education rank')
                self.assertEqual(len(f.t.spec[RESEARCH.KEY]['special_quality']), effect-2)
                child = f.hatch(first, 'actual special child')
                self.assertEqual(child.spec['special_quality']['quality'], 'GM quality 0')
                self.ordinary_pool(f, '포켓몬학', rank)


if __name__ == '__main__':
    unittest.main()
