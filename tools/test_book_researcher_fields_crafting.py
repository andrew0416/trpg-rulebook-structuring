"""Researcher Fields of Study: Apothecary, Artificer, Botany and Chemistry crafting/Extended Features (ch04:2076-2103)."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import researcher_fields as RFS
import researcher_features as RF
import action_points as AP
import frequency as FREQ
import state_codec as CODEC
import world_entities as WORLD

FIELDS = [['apothecary', 'artificer'], ['botany', 'chemistry'], ['climatology', 'paleontology'], ['pokemon_caretaking', 'general']]
ALL_FEATURES = [uid for uid in RFS.DEFINITIONS] + [RF.PUSHER, RF.SKILL_TRAINER]
EDGES = ['edge/원예가', 'edge/보석-지식', 'edge/스프레이-제작자', 'edge/고생물학자', 'edge/고난이도-스킬']
def fixture_edges():
    return list(EDGES)


SKILLS = {'의학': 6, '오컬트학': 6, '일반 지식': 6, '생존': 6, '기술학': 6, '포켓몬학': 6, '명령': 4, '육상': 4, '곡예': 4, '통찰': 4, '집중': 4}


class ResearcherFieldsCraftingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def setUp(self):
        previous = self.rules.rulings
        self.rules.rulings = deepcopy(previous)
        self.addCleanup(setattr, self.rules, 'rulings', previous)
        self.setup()

    def setup(self, **extra):
        self.e = Engine(self.rules, seed=20762128)
        self.t = self.trainer('actual Researcher', (0, 0), **extra)

    def trainer(self, name, pos, *, skills=None, feats=None, fields=None, **extra):
        spec = {'id': 'trainer/' + name.replace(' ', '-'), 'name': name, 'kind': 'trainer', 'level': 30, 'pos': pos,
                'stats': {'hp': 30, 'atk': 10, 'def': 10, 'spa': 10, 'spd': 10, 'spe': 10},
                'skills': dict(SKILLS, **(skills or {})), 'classes': ['class/연구원'],
                'feats': list(dict.fromkeys(ALL_FEATURES if feats is None else feats)), 'edges': list(EDGES),
                'feature_choices': {'class/연구원': deepcopy(FIELDS if fields is None else fields)},
                'feat_ranks': {RFS.SEED_BAG: 2}, 'items': {}, 'money': 10000}
        spec.update(extra)
        actor = Combatant(self.rules, spec)
        self.e.gm.add_combatant(actor, pos=pos, side='party', reason='actual Researcher scene participant')
        return actor

    def pokemon(self, species, level, name, pos=(1, 0), *, owner=None, loyalty=6, **extra):
        owner = self.t if owner is None else owner
        actor = Combatant(self.rules, build_pokemon(self.rules, species, level, name=name,
            extra={'trainer_id': owner.entity_id, **extra}))
        self.e.gm.add_combatant(actor, pos=pos, side='party', reason='actual owned Pokemon')
        if loyalty is not None:
            self.e.gm.observe_loyalty(actor, loyalty, reason='GM observed loyalty')
        return actor

    def rejected(self, operation, pattern):
        return assert_rejected_unchanged(self.e, operation, reason_pattern=pattern)

    def valid(self):
        result = self.e.validate_state()
        self.assertTrue(result['valid'], result['issues'])

    def restore(self, *names):
        identities = {name: getattr(self, name).entity_id for name in names}
        self.e = CODEC.load_engine(self.rules, json.loads(json.dumps(self.e.export_state(), ensure_ascii=False)))
        actors = WORLD.actor_index(self.e)
        for name, identity in identities.items():
            setattr(self, name, actors[identity])
        self.valid()

    def new_day(self):
        for actor in self.e.everyone:
            FREQ.new_day(actor)

    # ------------------------------------------------------------ Apothecary
    def test_patch_cure_extracts_three_extended_only_patches_and_medical_techniques_adds_tick_plus_medicine_rank(self):
        self.t.spec['items'].update({'상처약': 2, '플러스파워': 1})
        self.p = p = self.pokemon('이상해씨', 10, 'patient', tutor_points=4)
        self.rejected(lambda: RFS.patch_cure(self.e, self.t, '플러스파워', seconds=600, reason='x'), 'restorative item, not an X item')
        self.rejected(lambda: RFS.patch_cure(self.e, self.t, '상처약', seconds=0, reason='x'), 'seconds')
        elapsed = self.e.elapsed_seconds
        out = RFS.patch_cure(self.e, self.t, '상처약', seconds=600, reason='actual extraction')
        self.assertEqual((out['patch'], out['count'], self.t.spec['items']['상처약'], self.e.elapsed_seconds - elapsed),
                         ('patch:item/상처약', 3, 1, 600))
        p.hp = 5
        self.e.encounter_active = True
        self.rejected(lambda: RFS.apply_patch(self.e, self.t, 'patch:item/상처약', p, seconds=600, reason='x'), 'outside an active encounter')
        self.e.encounter_active = False
        self.t.spec['skills']['의학'] = 4
        self.rejected(lambda: RFS.apply_patch(self.e, self.t, 'patch:item/상처약', p, seconds=600, reason='x', medical_techniques=True), 'Medical Techniques requires its printed skill rank')
        self.t.spec['skills']['의학'] = 6
        out = RFS.apply_patch(self.e, self.t, 'patch:item/상처약', p, seconds=600, reason='actual application', medical_techniques=True)
        tick = self.e.tick(p)
        self.assertEqual(out['medical_techniques'], {'heal': tick + 6, 'tick': tick, 'medicine_rank': 6})
        self.assertEqual((p.hp, self.t.spec['items']['patch:item/상처약'], AP.available(self.t)), (min(p.base_max_hp, 5 + 20 + tick + 6), 2, 10))   # level 30: 11 AP, one spent on Medical Techniques
        self.restore('t', 'p')
        p = self.p
        self.assertEqual(self.t.spec[RFS.KEY]['patches']['patch:item/상처약']['item_id'], 'item/상처약')
        out = RFS.apply_patch(self.e, self.t, 'patch:item/상처약', p, seconds=600, reason='second application')
        self.assertEqual((out['medical_techniques'], self.t.spec['items']['patch:item/상처약']), (None, 1))

    def test_medicinal_blend_rejects_same_effect_pair_and_keeps_extended_only_use_from_a_patch_component(self):
        self.t.spec['items'].update({'상처약': 2, '좋은상처약': 1, '해독제': 1, '플러스파워': 2})
        p = self.pokemon('이상해씨', 10, 'patient', tutor_points=4)
        self.rejected(lambda: RFS.medicinal_blend(self.e, self.t, '상처약', '좋은상처약', seconds=600, reason='x'), 'must not share the same effect')
        self.rejected(lambda: RFS.medicinal_blend(self.e, self.t, '플러스파워', '플러스파워', seconds=600, reason='x'), 'two restorative items or one restorative item and one X item')
        self.t.spec['skills']['의학'] = 5
        self.rejected(lambda: RFS.medicinal_blend(self.e, self.t, '상처약', '해독제', seconds=600, reason='x'), 'Medicinal Blend requires its printed skill rank')
        self.t.spec['skills']['의학'] = 6
        cure = RFS.medicinal_blend(self.e, self.t, '상처약', '해독제', seconds=600, reason='two restoratives')
        self.assertEqual((cure['extended_only'], cure['components']), (False, ['item/상처약', 'item/해독제']))
        RFS.patch_cure(self.e, self.t, '상처약', seconds=600, reason='extract')
        mixed = RFS.medicinal_blend(self.e, self.t, 'patch:item/상처약', '플러스파워', seconds=600, reason='patch and X item')
        self.assertTrue(mixed['extended_only'])
        self.assertEqual(self.t.spec['items']['patch:item/상처약'], 2)
        p.hp = 5
        self.e.apply_status(p, '독', source='test')
        self.e.encounter_active = True
        self.rejected(lambda: RFS.apply_blend(self.e, self.t, mixed['blend'], p, reason='x'), 'outside an active encounter')
        self.e.encounter_active = False
        out = RFS.apply_blend(self.e, self.t, cure['blend'], p, reason='ordinary blend outside combat')
        self.assertEqual((out['applied'], p.hp, '독' in p.conditions, self.t.spec['items'][cure['blend']]), (2, 25, False, 0))
        p.hp = 5
        out = RFS.apply_blend(self.e, self.t, mixed['blend'], p, seconds=600, reason='extended-only blend')
        self.assertEqual((out['applied'], p.hp, p.stages['atk']), (2, 25, 2))
        self.valid()
        self.restore('t')

    def test_apothecary_recipes_remain_the_existing_restorative_crafting_consumer_with_the_field_requirement(self):
        self.t.spec['items']['화학 세트'] = 1
        out = self.e.pokemon_activity(self.t, 'craft_item', item='상처약', minutes=30, reason='GM recipe duration')
        self.assertEqual((out['item'], self.t.spec['items']['상처약'], self.t.spec['money']), ('상처약', 1, 9900))
        other = self.trainer('non apothecary', (3, 3), fields=[['botany', 'chemistry']])
        other.spec['items']['화학 세트'] = 1
        self.rejected(lambda: self.e.pokemon_activity(other, 'craft_item', item='상처약', minutes=30, reason='x'), 'acquired Researcher field')

    # ------------------------------------------------------------ Artificer
    def test_crystal_artificer_makes_type_items_from_four_same_colour_shards_with_a_colour_type_and_needs_gem_lore(self):
        self.t.spec['shards'] = {'빨강': 8, '파랑': 3}
        self.rejected(lambda: RFS.craft_artificer(self.e, self.t, '타입부스터', color='빨강', move_type='물', minutes=30, reason='x'), 'shard colour types')
        self.rejected(lambda: RFS.craft_artificer(self.e, self.t, '타입부스터', color='파랑', move_type='물', minutes=30, reason='x'), 'insufficient aggregate recipe ingredients')
        self.rejected(lambda: RFS.craft_artificer(self.e, self.t, '진화의돌', color='빨강', move_type='불꽃', minutes=30, reason='x'), 'recipe required')
        self.t.spec['edges'].remove('edge/보석-지식')
        self.rejected(lambda: RFS.craft_artificer(self.e, self.t, '타입부스터', color='빨강', move_type='불꽃', minutes=30, reason='x'), 'acquired feature required')
        self.t.spec['edges'].append('edge/보석-지식')
        booster = RFS.craft_artificer(self.e, self.t, '타입부스터', color='빨강', move_type='불꽃', minutes=30, reason='actual crafting')
        brace = RFS.craft_artificer(self.e, self.t, '타입깁스', color='빨강', move_type='에스퍼', minutes=30, reason='actual crafting')
        self.assertEqual((booster['item_id'], brace['item_id'], self.t.spec['shards']['빨강'], self.t.spec['items']['타입부스터'], self.t.spec['items']['타입깁스']),
                         ('item/타입부스터', 'item/타입깁스', 0, 1, 1))
        self.assertEqual([row['type'] for row in self.t.spec[RFS.KEY]['artificer']], ['불꽃', '에스퍼'])
        self.restore('t')

    def test_crystal_resonance_adds_three_dowsing_dice_only_with_the_approved_dowsing_stunt(self):
        self.t.spec['items']['다우징 로드'] = 1
        self.t.spec['skills']['오컬트학'] = 5
        self.e.approve_skill_stunt(self.t, choice_id='repair', skill='기술학', use='고장 난 선박 엔진 배선 진단', reason='GM approved another narrow use', approved=True)
        self.assertEqual(RFS.dowsing_bonus(self.e, self.t), 0)
        plain = self.e.pokemon_activity(self.t, 'dowse', outdoors=True, fixed={str(i): 1 for i in range(5)})
        self.assertEqual(plain['pool'], 5)
        self.t.spec['edge_choices'][next(iter(self.t.spec['edge_choices']))].clear()
        self.e.approve_skill_stunt(self.t, choice_id='dowse', skill='오컬트학', use='다우징', reason='GM approved the narrow Dowsing use', approved=True)
        self.assertEqual(RFS.dowsing_bonus(self.e, self.t), 3)
        self.rejected(lambda: self.e.pokemon_activity(self.t, 'dowse', outdoors=True, fixed={str(i): 1 for i in range(12)}), 'unused fixed pool faces')
        boosted = self.e.pokemon_activity(self.t, 'dowse', outdoors=True, fixed={str(i): 1 for i in range(9)})
        self.assertEqual(boosted['pool'], 5 + 1 + 3)
        other = self.trainer('botanist', (3, 3), fields=[['botany', 'chemistry']], edges=[edge for edge in fixture_edges() if edge != 'edge/고난이도-스킬'])
        self.assertEqual(RFS.dowsing_bonus(self.e, other), 0)

    # ------------------------------------------------------------ Botany
    def test_seed_bag_harvests_rank_moves_from_a_willing_grass_pokemon_two_uses_per_rank_without_duplicates_until_the_day_ends(self):
        g = self.pokemon('이상해씨', 12, 'donor', moves=['move/수면가루', 'move/독가루', 'move/씨뿌리기'])
        n = self.pokemon('피카츄', 12, 'normal', pos=(2, 0), moves=['move/전광석화'])
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, n, 'move/수면가루', seconds=600, reason='x'), 'Grass-type')
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/몸통박치기', seconds=600, reason='x'), 'printed powder/spore/seed Moves')
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/저리가루', seconds=600, reason='x'), 'actually know that Move')
        self.e.gm.observe_loyalty(g, 1, reason='GM: unwilling')
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/수면가루', seconds=600, reason='x'), 'willing Pokemon')
        self.e.gm.observe_loyalty(g, 4, reason='GM: willing again')
        self.t.spec['feat_ranks'][RFS.SEED_BAG] = 1
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/씨뿌리기', seconds=600, reason='x'), 'printed powder/spore/seed Moves')
        self.t.spec['skills'].update({'일반 지식': 3, '생존': 3})
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/수면가루', seconds=600, reason='x'), 'Seed Bag rank 1 requires')
        self.t.spec['skills'].update({'일반 지식': 4})
        out = RFS.seed_bag(self.e, self.t, g, 'move/수면가루', seconds=600, reason='actual harvest')
        self.assertEqual((out['move'], out['rank'], self.t.moves), ('move/수면가루', 1, ['move/수면가루']))
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/수면가루', seconds=600, reason='x'), 'already on your Move list')
        RFS.seed_bag(self.e, self.t, g, 'move/독가루', seconds=600, reason='second harvest')
        self.t.spec['items']['x'] = 0
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/저리가루', seconds=600, reason='x'), 'actually know that Move')
        self.e.gm.set_move(g, 'move/저리가루', reason='actual complete known Move list')
        self.rejected(lambda: RFS.seed_bag(self.e, self.t, g, 'move/저리가루', seconds=600, reason='x'), 'daily uses')
        self.t.spec['feat_ranks'][RFS.SEED_BAG] = 2
        self.t.spec['skills'].update({'생존': 6})
        self.restore('t')
        g = WORLD.actor_index(self.e)[g.entity_id]
        self.assertEqual(sorted(self.t.moves), ['move/독가루', 'move/수면가루'])
        self.new_day()
        self.assertEqual(self.t.moves, [])
        self.valid()
        out = RFS.seed_bag(self.e, self.t, g, 'move/씨뿌리기', seconds=600, reason='rank two harvest')
        self.assertEqual((out['rank'], self.t.moves), (2, ['move/씨뿌리기']))

    def test_herb_lore_follows_the_printed_ingredient_yields_and_needs_seed_bag_rank_one(self):
        self.t.spec['items'].update({'자뭉열매': 1, '작은버섯': 1, '힘의뿌리': 1, '리샘열매': 1, '큰버섯': 1, '부활초': 1})
        self.rejected(lambda: RFS.herb_lore(self.e, self.t, '파스', option=0, minutes=30, reason='x'), 'insufficient aggregate recipe ingredients')
        self.rejected(lambda: RFS.herb_lore(self.e, self.t, '상처약', option=0, minutes=30, reason='x'), 'Herb Lore makes')
        for product, option, count in (('힘의가루', 0, 2), ('힘의가루', 1, 2), ('힘의가루', 2, 3), ('만능가루', 0, 2), ('만능가루', 1, 2), ('만능가루', 2, 3)):
            self.assertEqual(RFS.herb_lore(self.e, self.t, product, option=option, minutes=30, reason='actual crafting')['count'], count)
        self.assertEqual((self.t.spec['items']['힘의가루'], self.t.spec['items']['만능가루']), (7, 7))
        out = RFS.herb_lore(self.e, self.t, '파스', option=0, minutes=30, reason='poultice')
        self.assertEqual((out['count'], self.t.spec['items']['파스'], self.t.spec['items']['힘의가루'], self.t.spec['items']['만능가루']), (3, 3, 6, 6))
        self.t.spec['feats'].remove(RFS.SEED_BAG)
        self.rejected(lambda: RFS.herb_lore(self.e, self.t, '파스', option=0, minutes=30, reason='x'), 'actual acquired Researcher feature required')
        self.restore('t')

    def test_top_tier_berries_keep_their_existing_harvest_owner_master_soil_plus_one_and_the_field_prerequisite(self):
        self.t.spec['items'].update({'나무열매플랜터': 1, '과사열매': 1})
        self.t.spec['skills'].update({'일반 지식': 5, '생존': 5})
        self.e.pokemon_activity(self.t, 'plant_berry', berry='과사열매', plant_id='tier3', soft_soil=True)
        self.e.advance_time(172800, [self.t])
        self.t.spec['skills']['생존'] = 6
        self.assertEqual(RFS.qualify(self.e, self.t, RFS.TOP_TIER)['english'], 'Top Tier Berries')
        result = self.e.pokemon_activity(self.t, 'harvest_berry', plant_id='tier3', fixed=4)
        self.assertEqual((result['soil_bonus'], result['amount']), (2, 3))   # existing owner: Master rank soil +1 on top of the soft-soil site
        self.t.spec['edges'].remove('edge/원예가')
        self.rejected(lambda: RFS.qualify(self.e, self.t, RFS.TOP_TIER), 'acquired feature required')

    # ------------------------------------------------------------ Chemistry
    def test_chemist_recipes_need_the_chemistry_set_the_field_edge_and_the_printed_provider_feature_per_pester_ball(self):
        self.rejected(lambda: RFS.craft_chemistry(self.e, self.t, '플러스파워', minutes=30, reason='x'), 'required equipment is not accessible')
        self.t.spec['items']['화학 세트'] = 1
        self.rejected(lambda: RFS.craft_chemistry(self.e, self.t, '상처약', minutes=30, reason='x'), 'Chemistry recipe required')
        self.t.spec['skills']['기술학'] = 4
        self.rejected(lambda: RFS.craft_chemistry(self.e, self.t, '오물탄: 마비', minutes=30, reason='x'), 'Caustic Chemistry requires its printed skill rank')
        self.t.spec['skills']['기술학'] = 6
        self.t.spec['edges'].remove('edge/스프레이-제작자')
        self.rejected(lambda: RFS.craft_chemistry(self.e, self.t, '플러스파워', minutes=30, reason='x'), 'acquired feature required')
        self.t.spec['edges'].append('edge/스프레이-제작자')
        before = self.t.spec['money']
        for item, cost in (('플러스파워', 100), ('크리티컬 커터', 100), ('오물탄: 격노', 50), ('오물탄: 화상', 50), ('오물탄: 마비', 50)):
            out = RFS.craft_chemistry(self.e, self.t, item, minutes=30, reason='actual crafting')
            self.assertEqual((out['money_spent'], self.t.spec['items'][out['item']]), (cost, 1), item)
        self.assertEqual(self.t.spec['money'], before - 350)
        self.restore('t')

    def test_playing_god_builds_an_artificial_egg_for_3500_with_technology_rank_upgrades_and_hatches_after_one_day_at_level_five(self):
        from builder import STATS
        self.t.spec['items']['화학 세트'] = 1
        upgrades = [{'kind': 'shiny_contest', 'contest_stat': '근사함'}, {'kind': 'inheritance_move', 'move': 'move/저주'},
                    {'kind': 'base_stat', 'stat': 'spa'}, {'kind': 'base_stat', 'stat': 'spa'}, {'kind': 'base_stat', 'stat': 'hp'}, {'kind': 'base_stat', 'stat': 'def'}]
        call = lambda **kw: RFS.playing_god(self.e, self.t, **dict(dict(species='코일', nature='겁쟁이', ability='옹골참', gender='무성', upgrades=upgrades, seconds=3600, reason='actual synthesis', request_id='pg-1'), **kw))
        self.rejected(lambda: call(species='피카츄'), 'eight printed species')
        self.rejected(lambda: call(ability='애널라이즈'), 'species basic Abilities')
        self.rejected(lambda: call(upgrades=upgrades[:5]), 'one upgrade per Technology rank')
        self.rejected(lambda: call(upgrades=upgrades[:2] + [{'kind': 'inheritance_move', 'move': 'move/기어체인지'}] + upgrades[3:]), 'species Egg or Tutor list')
        self.rejected(lambda: call(upgrades=[{'kind': 'shiny_contest', 'contest_stat': '근사함'}] * 2 + upgrades[2:]), 'upgrade limit exceeded')
        self.t.spec['money'] = 3499
        self.rejected(lambda: call(), 'insufficient matching scrap or money')
        self.t.spec['money'] = 10000
        first = call()
        self.assertEqual((self.t.spec['money'], len(self.t.spec['eggs']), first['egg_entity_id']), (6500, 1, self.t.spec['eggs'][0]['entity_id']))
        self.assertEqual(call(), first)   # replay of the same request creates nothing new
        self.assertEqual((self.t.spec['money'], len(self.t.spec['eggs'])), (6500, 1))
        egg = self.t.spec['eggs'][0]
        self.rejected(lambda: RFS.hatch_artificial(self.e, self.t, egg['entity_id'], name='Coil', reason='x'), 'hatches after one day')
        self.e.advance_time(86400, [self.t])
        self.restore('t')
        child = RFS.hatch_artificial(self.e, self.t, egg['entity_id'], name='Coil', reason='actual hatching')['pokemon']
        self.assertEqual((child.level, child.spec['nature'], child.abilities, child.spec['special_appearance']), (5, '겁쟁이', ['옹골참'], True))
        self.assertIn('move/저주', child.moves)
        self.assertEqual(child.spec['vitamin_bonus'], {'spa': 2, 'hp': 1, 'def': 1})
        self.assertEqual(RFS.vitamin_equivalents(child.spec), 4)
        import move_state as MOVES
        self.assertEqual(MOVES.vitamin_state(self.rules, child.spec)['occupied'], 4)
        self.assertEqual(child.spec['researcher_contest_introduction'], {'stat': '근사함', 'dice': 2, 'feature': RFS.PLAYING_GOD, 'clause_id': 'C04-085'})
        self.assertEqual(RFS.introduction_bonus_dice(self.e, child, '근사함'), 2)
        self.assertEqual(RFS.introduction_bonus_dice(self.e, child, '아름다움'), 0)
        self.assertTrue(self.t.spec['eggs'][0]['hatched'])
        self.valid()
        self.restore('t')


if __name__ == '__main__':
    unittest.main()
