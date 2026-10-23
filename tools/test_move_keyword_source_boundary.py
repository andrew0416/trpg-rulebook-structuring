"""Voice Lessons uses printed Sonic keywords and explicit conditional grants.

Source anchors: input/ch04-trainer-classes.md:2516-2520;
input/ch10-index-reference.md:334,371,373; PTU 1.05 Core:4822-4823.
Checks owned-Pokemon combat and Contest paths, native costs, keyword consumers,
and generated headers.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

import test_book_musician_full as MF  # module object only; its TestCase is not re-exported
from engine import Rules, Engine
from grid import Grid
from contest import ContestRules, ContestEngine
import musician as M

_H = MF.MusicianTests.__dict__


class VoiceLessonsProbe(unittest.TestCase):
    add = _H['add']
    acquire = _H['acquire']
    musician = _H['musician']
    pokemon = _H['pokemon']
    foe = _H['foe']
    combat = _H['combat']
    use = _H['use']
    restore = _H['restore']
    valid = _H['valid']
    rejected = _H['rejected']

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')
        cls.contest_rules = ContestRules(ROOT, ruleset='core')

    def setUp(self):
        old = self.rules.rulings
        self.rules.rulings = deepcopy(old)
        self.addCleanup(setattr, self.rules, 'rulings', old)
        self.e = Engine(self.rules, seed=2345)
        self.e.grid = Grid(18, 12)
        self.t = self.add('Musician', 'trainer', (3, 3), speed=30, classes=[], feats=[], edges=[], moves=[], items={}, exp_bank=50)

    def _line_up(self, owner):
        # singer (4,6) -> ally (5,6) -> foe (6,6): the same close-blast line as the canonical Trainer test.
        self.P = self.pokemon('Singer', pos=(4, 6), owner=owner)
        self.A = self.pokemon('Ally', pos=(5, 6), owner=owner)
        self.F = self.foe(pos=(6, 6))

    # --- positive: owned Pokemon path, after JSON restore -----------------------
    def test_owned_pokemon_sonic_move_spares_ally_after_restore(self):
        self.musician(M.VOICE)
        self._line_up(self.t)
        self.restore('t', 'P', 'A', 'F')
        hp = self.A.hp
        self.combat(self.P)
        self.use(self.P, self.F, 'move/하이퍼보이스', aim=(6, 6))
        self.assertEqual(self.A.hp, hp, 'Friendly from Voice Lessons must keep the allied Pokemon out of the hit')
        self.assertLess(self.F.hp, self.F.max_hp, 'foe must still be hit')

    # --- control: same geometry, Trainer without Voice Lessons ------------------
    def test_control_without_voice_lessons_hits_the_same_ally(self):
        self.musician(M.NOISE)  # Noise Complaint owned, Voice Lessons not owned
        self._line_up(self.t)
        hp = self.A.hp
        self.combat(self.P)
        self.use(self.P, self.F, 'move/하이퍼보이스', aim=(6, 6))
        self.assertLess(self.A.hp, hp, 'without Voice Lessons the close blast hits the ally (geometry is real)')

    # --- prerequisite: Voice Lessons requires Noise Complaint ------------------
    def test_voice_requires_noise_complaint(self):
        self.acquire(M.CLASS)
        for f in (M.BLUES, M.CACOPHONY):
            self.acquire(f)
        self.rejected(lambda: self.acquire(M.VOICE), 'acquired|prerequisite')

    # --- negative: effect-text [소리] mention is not a Sonic keyword -----------
    def test_effect_text_mention_is_not_a_sonic_move(self):
        self.musician(M.VOICE)
        p = self.add('Coat', 'pokemon', (4, 3), trainer_id=self.t.entity_id, abilities=[],
                     moves=['move/대타출동', 'move/지옥찌르기', 'move/하이퍼보이스'])
        failures = []
        for mid in ('move/대타출동', 'move/지옥찌르기', 'move/꼬리자르기'):
            move = self.rules.move(mid)
            if '친화' in M.project_move(self.e, p, move)['keywords']:
                failures.append(f'{mid}: gained 친화 (Range line has no 소리)')
            if M.contest_bonus(self.e, p, self.t, move):
                failures.append(f'{mid}: contest_bonus=1')
        # positive control in the same fixture
        self.assertIn('친화', M.project_move(self.e, p, self.rules.move('move/하이퍼보이스'))['keywords'])
        self.assertEqual(failures, [], failures)

    def test_substitute_contest_pool_has_no_voice_die(self):
        self.musician(M.VOICE)
        p = self.add('Coat', 'pokemon', (4, 3), trainer_id=self.t.entity_id, abilities=[],
                     moves=['move/대타출동', 'move/하이퍼보이스'])
        ce = ContestEngine(self.contest_rules, seed=99)
        c = ce.contestant_from_combatants(self.e, p, self.t, '매력', stat_dice={'슬기로움': 0, '근사함': 0})
        frames = []
        finish = ContestEngine._finish_performance

        def observe(native, actor, adjacent, frame, reroll_kind=None):
            frames.append(deepcopy(frame))
            return finish(native, actor, adjacent, frame, reroll_kind)
        with patch.object(ContestEngine, '_finish_performance', new=observe):
            ce.perform(c, '대타출동', '슬기로움', [], False)
        self.assertNotIn('voice_lessons', frames[-1]['pool_components'],
                         'Substitute (자신, 환영, 코트) is not a Sonic move; no Voice Lessons die')


    # --- combat consequence of the false Sonic tag on a Self move -------------
    def _substitute(self, top):
        self.musician(top)
        p = self.add('Coat', 'pokemon', (4, 3), trainer_id=self.t.entity_id, abilities=[],
                     moves=['move/대타출동'])
        self.foe(pos=(9, 9))
        hp = p.hp
        self.combat(p)
        result = self.use(p, p, 'move/대타출동')
        return hp, p.hp, result

    def test_control_substitute_without_voice_lessons_is_used(self):
        before, after, _ = self._substitute(M.NOISE)
        self.assertLess(after, before, 'Substitute costs 1/4 of max HP when used')

    def test_substitute_with_voice_lessons_is_still_used(self):
        before, after, result = self._substitute(M.VOICE)
        self.assertLess(after, before, f'Voice Lessons must not turn Substitute into a no-op (result={result!r}, log tail={self.e.log_lines[-3:]!r})')


    def test_all_printed_sonic_moves_keep_voice_except_perish_song(self):
        self.musician(M.VOICE)
        singer = self.pokemon()
        printed = [move for mid, move in self.rules.moves.items()
                   if '소리' in move.get('range', '') and mid in self.rules.moves_mech]
        self.assertGreaterEqual(len(printed), 20)
        for move in printed:
            with self.subTest(move=move['id']):
                self.assertTrue(M.sonic(singer, move))
                eligible = move['id'] != 'move/멸망의노래'
                self.assertEqual(M.contest_bonus(self.e, singer, self.t, move), int(eligible))
                if eligible:
                    self.assertIn('친화', M.project_move(self.e, singer, move)['keywords'])

    def test_soundproof_blocks_real_sound_but_not_throat_chop(self):
        import effects_ext as EXT
        self.musician(ability='방음')
        attacker = self.foe(pos=(4, 3), moves=['move/지옥찌르기', 'move/하이퍼보이스'])
        sound = self.rules.move('move/하이퍼보이스')
        chop = self.rules.move('move/지옥찌르기')
        self.assertIsNotNone(EXT.keyword_block_reason(self.e, attacker, self.t, sound))
        self.assertIsNone(EXT.keyword_block_reason(self.e, attacker, self.t, chop))
        before = self.t.hp
        self.combat(attacker)
        self.use(attacker, self.t, chop['id'])
        self.assertLess(self.t.hp, before)

    def test_substitute_is_not_social_but_explicit_keyword_grants_still_work(self):
        import combat_social_edges as SOCIAL
        import effects_ext as EXT
        move = self.rules.move('move/대타출동')
        self.assertFalse(SOCIAL.social(self.t, move))
        self.assertTrue(SOCIAL.social(self.t, self.rules.move('move/애교부리기')))
        self.t.registry.append({'type': 'gain_keyword', 'keyword': '소리', 'moves': 'all'})
        self.assertIn('소리', EXT.keywords_for(self.t, move))

    def test_normal_dark_void_can_hit_an_ally(self):
        caster = self.add('Caster', 'pokemon', (4, 3), trainer_id=self.t.entity_id,
                          abilities=[], moves=['move/다크홀'])
        ally = self.pokemon('Ally', pos=(5, 3))
        self.foe(pos=(10, 10))
        self.combat(caster)
        self.use(caster, ally, 'move/다크홀', face=20)
        self.assertIn('잠듦', ally.conditions)


    def test_optional_modes_supply_only_their_current_keywords_to_consumers(self):
        import optional_move_modes as MODES
        import effects_ext as EXT
        names = ('꽃가루경단', '다크홀', '섬뜩한주문', '암석액스', '백귀야행')
        caster = self.add('Caster', 'pokemon', (4, 3), trainer_id=self.t.entity_id,
                          abilities=[], moves=['move/'+name for name in names])
        ally = self.pokemon('Ally', pos=(5, 3))
        foe = self.foe(pos=(5, 4))
        self.e.apply_status(foe, '독')
        self.combat(caster)
        for name in names:
            mid = 'move/'+name
            target = ally if name == '꽃가루경단' else foe
            base = self.rules.move(mid)
            mechanics = self.rules.move_mech(mid)[0]
            normal, _ = MODES.project(self.e, caster, target, base, mechanics)
            expected = {'베기'} if name == '암석액스' else set()
            self.assertEqual(EXT.keywords_for(caster, normal), expected, mid)
            self.e.gm.choose_optional_move_effect(caster, mid, reason='actual optional mode selection')
            selected, _ = MODES.project(self.e, caster, target, base, mechanics)
            selected_expected = {'치유'} if name == '꽃가루경단' else {'친화'} if name == '다크홀' else expected
            self.assertEqual(EXT.keywords_for(caster, selected), selected_expected, mid)


class MoveKeywordProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        import ptk_structure as P
        cls.rows, _ = P.parse_moves(ROOT/'input/db/moves.csv')
        P.dedupe_ids(cls.rows)
        cls.parsed = {m['id']:m for m in cls.rows}
        cls.saved = {m['id']:m for m in json.loads((ROOT/'output/entities/moves.json').read_text(encoding='utf8'))}
        cls.mech = json.loads((ROOT/'data/moves-mech.json').read_text(encoding='utf8'))

    def test_effect_mentions_and_conditional_grants_are_not_base_keywords(self):
        expected = {
            '대타출동': {'코트', '환영'}, '꼬리자르기': {'코트', '환영', '방해', '방패', '발동조건'},
            '지옥찌르기': set(), '다크홀': set(), '성묘': set(), '트윈빔': set(),
            '꽃가루경단': set(), '불꽃의맹세': {'맹세'}, '패스트가드': {'방해', '방패', '발동조건'},
            '솔라빔': {'준비'}, '노래하기': {'소리', '친화'},
        }
        for name, keywords in expected.items():
            with self.subTest(move=name):
                self.assertEqual(set(self.parsed['move/'+name].get('keywords', [])), keywords)

    def test_generated_catalog_and_mechanics_match_fresh_source_extraction(self):
        self.assertEqual(set(self.saved), set(self.parsed))
        for mid, move in self.parsed.items():
            with self.subTest(move=mid):
                self.assertEqual(self.saved[mid].get('keywords', []), move.get('keywords', []))
                if mid in self.mech:
                    self.assertEqual(self.mech[mid]['header']['keywords'], move.get('keywords', []))

    def test_both_ruleunit_exports_match_the_active_mechanics_header(self):
        import json
        for relative in ('output/ruleunits.jsonl', 'output/ruleunits.core.jsonl'):
            for line in (ROOT/relative).read_text(encoding='utf8').splitlines():
                unit = json.loads(line)
                if unit.get('kind') == 'entity:move' and unit['id'] in self.mech:
                    header = unit.get('mech', {}).get('data', {}).get('header')
                    if header is not None:
                        self.assertEqual(header.get('keywords', []), self.mech[unit['id']]['header']['keywords'], unit['id'])


def load_tests(loader, tests, pattern):
    return unittest.TestSuite([loader.loadTestsFromTestCase(MoveKeywordProducerTests),
                               loader.loadTestsFromTestCase(VoiceLessonsProbe)])


if __name__ == '__main__':
    unittest.main()
