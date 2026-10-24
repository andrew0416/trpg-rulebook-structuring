"""New native admission, independent of the valid declared-owned sheet path."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import acquired_features as A
import blessing_skill_features as B
import native_acquisition_adapters as N
import native_scenario_fixture as FIXTURE
import state_codec as CODEC
import state_grants as G
import trainer_feature_acquisition as T
import static_feature_state_grants as STATIC
from ruleset import RuleFilter


class NativeAcquisitionAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def fixture(self, uid, *, role='contractor', rules=None):
        rules = self.rules if rules is None else rules
        d = N.DEFINITIONS[uid]
        extra = dict(classes=[], feats=[], edges=[], gifts=[], techniques=[],
                     static_feature_choices={}, edge_choices={}, feat_ranks={})
        skills = {skill: minimum for skill, minimum in d.get('skills', {}).items()}
        for parent in d.get('parents', []):
            field = 'classes' if parent.startswith('class/') else 'edges' if parent.startswith('edge/') else 'gifts' if parent.startswith('gift/') else 'feats'
            extra[field].append(parent)
            if parent.endswith('R643:main'):
                extra['static_feature_choices'][parent] = '꽃의 맹약'
        if d.get('element'):
            extra['edges'].append('edge/원소-교감')
            extra['edge_choices']['edge/원소-교감'] = [d['element']]
        if d['kind'] == 'technique':
            extra['feat_ranks'][N.JOURNEY] = 1
        if d['kind'] == 'blessing':
            route = N.ROUTES[role]
            extra['feats'].extend([route, B.SIGNER])
            extra['feat_ranks'][route] = 3
            extra['gift_patrons'] = {}
        engine = Engine(rules, seed=162001)
        actor = Combatant(rules, build_trainer(rules, 'native-acquirer', 30,
            dict.fromkeys(('hp', 'atk', 'def', 'spa', 'spd', 'spe'), 10), moves=[], abilities=[],
            skills=skills, extra=extra))
        engine.gm.add_combatant(actor, reason='actual trainer before new native acquisition')
        selection = {'waivers': []}
        if d.get('choices') is not None:
            choice = ['power', 'land'] if uid == 'edge/여행자' else d['choices'][0]
            selection['choice'] = choice
        if d['kind'] == 'blessing':
            selection = dict(role=role, grant_rank=3, slot=1,
                permission={'reason': 'GM permits this exact new native blessing'}, waivers=[])
            if uid == N.INSIGHT:
                actor.spec['gift_patrons']['gift/고대의-지혜'] = '뮤'
                B.confirm(engine, actor, 'gift/고대의-지혜', reason='independent permission for already-owned prerequisite', configuration={'role': 'contractor'})
                selection['configuration'] = {'role': '계약자' if role == 'contractor' else '메시아'}
            else:
                patron = Combatant(rules, build_pokemon(rules, '스이쿤', 30, moves=[], abilities=[]))
                engine.gm.add_combatant(patron, reason='actual Resilience patron')
                actor.spec['gift_patrons'][uid] = patron.entity_id
                choice = dict(role=role, patron_id=patron.entity_id,
                              eligible_types=['강철', '물', '불꽃', '얼음'])
                if role == 'messiah':
                    choice['selected_types'] = ['불꽃', '물']
                selection['configuration'] = choice
        if d['kind'] == 'exalted':
            patron = Combatant(rules, build_pokemon(rules, '뮤츠', 30, moves=[], abilities=[]))
            engine.gm.add_combatant(patron, reason='actual Mewtwo granting Exalted Gift')
            selection = {'permission': {'reason': 'GM permits exactly Psystrike from Mewtwo',
                                        'patron_id': patron.entity_id}, 'waivers': []}
        return engine, actor, selection

    def acquire(self, engine, actor, uid, selection=None, request='native/request/1'):
        source_id = N.DEFINITIONS[uid]['clause_id'] if uid == 'feat/파캐스트' else None
        return T.acquire_static(engine, actor, uid, acquisition_request_id=request,
            selection=selection, source_id=source_id)

    def reject(self, engine, operation, pattern):
        return FIXTURE.assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def restore(self, engine, actor):
        restored = CODEC.load_engine(engine.r, json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
        return restored, next(value for value in restored.everyone if value.entity_id == actor.entity_id)

    def withdraw(self, engine, actor, uid):
        d = N.DEFINITIONS[uid]
        def apply(staged, owner):
            G.revoke(owner, N._sid(owner, uid), engine=staged)
            owner.spec[d['field']].remove(d['owned_value'])
            if d.get('choice_field'):
                owner.spec[d['choice_field']].pop(uid)
            STATIC.register_all(staged, owner)
            __import__('class_passive_combat').register_all(staged, owner)
        G.transition(engine, actor, apply)

    def test_exact_fifteen_sources_have_native_success_and_existing_receipt_reader(self):
        self.assertEqual(len(N.DEFINITIONS), 15)
        for uid, definition in N.DEFINITIONS.items():
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                row = self.acquire(e, a, uid, selection)
                self.assertEqual(row['source']['clause_id'], definition['clause_id'])
                self.assertEqual(row['qualification']['status'], 'qualified')
                self.assertIn(definition['owned_value'], a.spec[definition['field']])
                self.assertEqual(row['snapshot']['trainer'], True)
                self.assertEqual([r['request_id'] for r in e.acquisition_receipts(a) if r['basis'] == N.LABEL], ['native/request/1'])

    def test_each_printed_skill_rejects_below_boundary_and_accepts_exact_boundary(self):
        for uid, d in N.DEFINITIONS.items():
            for skill, minimum in d.get('skills', {}).items():
                with self.subTest(source=uid, skill=skill):
                    e, a, selection = self.fixture(uid)
                    a.spec['skills'][skill] = minimum - 1
                    if d.get('any_skill'):
                        for other in d['skills']:
                            a.spec['skills'][other] = minimum - 1
                    self.reject(e, lambda: self.acquire(e, a, uid, selection), 'printed rank|Expert Focus')
                    e.gm.set_skill(a, skill, minimum, reason='actual acquisition boundary observation')
                    self.assertEqual(self.acquire(e, a, uid, selection)['qualification']['status'], 'qualified')

    def test_psychic_assault_accepts_either_focus_or_intuition_without_requiring_both(self):
        uid = 'C2CSV/input/db/feats.csv:R507:main'
        for skill in ('집중', '직감'):
            e, a, selection = self.fixture(uid)
            a.spec['skills'] = {'집중': 2, '직감': 2, skill: 5}
            self.acquire(e, a, uid, selection)
            self.assertTrue({'move/신통력', 'move/어시스트파워'} <= set(a.moves))

    def test_each_missing_owned_prerequisite_rejects_without_using_gm_reason_as_waiver(self):
        for uid, d in N.DEFINITIONS.items():
            for parent in d.get('parents', []):
                with self.subTest(source=uid, parent=parent):
                    e, a, selection = self.fixture(uid)
                    for field in ('classes', 'feats', 'edges', 'gifts'):
                        if parent in a.spec[field]:
                            a.spec[field].remove(parent)
                    if parent.endswith('R643:main'):
                        a.spec['static_feature_choices'].pop(parent)
                    STATIC.register_all(e, a)
                    self.reject(e, lambda: self.acquire(e, a, uid, selection), 'prerequisite|Hero Journey')

    def test_elemental_classes_require_exact_owned_type_and_each_printed_skill(self):
        for number, element in ((587, '벌레'), (643, '풀')):
            uid = f'C2CSV/input/db/feats.csv:R{number}:main'
            for mutation in ('missing_edge', 'wrong_type'):
                e, a, selection = self.fixture(uid)
                if mutation == 'missing_edge':
                    a.spec['edges'].clear()
                    a.spec['edge_choices'].clear()
                else:
                    a.spec['edge_choices']['edge/원소-교감'] = ['불꽃']
                self.reject(e, lambda: self.acquire(e, a, uid, selection), 'Elemental Connection')

    def test_all_class_branches_and_fire_stat_choices_commit_exact_selection(self):
        for uid, d in N.DEFINITIONS.items():
            if not d.get('choices') or uid == 'edge/여행자':
                continue
            for choice in d['choices']:
                with self.subTest(source=uid, choice=choice):
                    e, a, selection = self.fixture(uid)
                    selection['choice'] = choice
                    self.acquire(e, a, uid, selection)
                    row = STATIC.rules(e.r)[d['static_row']]
                    stat = row['branches'][choice]['stat'] if d['kind'] == 'class' else choice
                    self.assertEqual(a.stats[stat], 11)
                    self.assertEqual(a.spec[d['choice_field']][uid], choice)

    def test_synthetic_classes_use_actual_four_class_slots_and_atomic_fifth_rejection(self):
        uid = 'C2CSV/input/db/feats.csv:R643:main'
        e, a, selection = self.fixture(uid)
        a.spec['classes'] = ['class/에이스-트레이너', 'class/텔레파시능력자', 'class/공간도약자']
        self.acquire(e, a, uid, selection)
        self.assertEqual(len(A.class_instances(a)), 4)
        other = 'C2CSV/input/db/feats.csv:R587:main'
        e.gm.set_skill(a, '명령', 3, reason='Novice Command')
        a.spec['edges'].append('edge/원소-교감')
        a.spec['edge_choices']['edge/원소-교감'].append('벌레')
        self.reject(e, lambda: self.acquire(e, a, other, {'choice': '거미의 포용', 'waivers': []}, 'native/request/2'), 'four slots')

    def test_existing_synthetic_class_aliases_in_classes_or_feats_keep_one_real_slot(self):
        for uid, d in N.DEFINITIONS.items():
            if not d.get('class_slot'):
                continue
            for field in ('classes', 'feats'):
                for alias in d['owned_aliases']:
                    with self.subTest(source=uid, field=field, alias=alias):
                        e, a, selection = self.fixture('edge/파워-부스트')
                        a.spec[field].append(alias)
                        a.spec['static_feature_choices'][alias] = d['choices'][0]
                        self.assertEqual(len(A.class_instances(a)), 1)
                        self.assertEqual(A.class_instances(a)[0]['source_id'], uid)
                        self.assertEqual(N.receipts(a), [])
                        self.acquire(e, a, 'edge/파워-부스트', selection)

    def test_nontrainer_native_admission_rejects_before_any_write(self):
        for uid in N.DEFINITIONS:
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                pokemon = Combatant(e.r, build_pokemon(e.r, '이브이', 30, moves=[], abilities=[]))
                e.gm.add_combatant(pokemon, reason='actual registered nontrainer')
                self.reject(e, lambda: self.acquire(e, pokemon, uid, selection), 'trainer')

    def test_backpacker_talents_use_two_per_actual_journey_rank_and_preserve_skill_gate(self):
        e, a, selection = self.fixture('technique/해트트릭')
        a.spec['techniques'] = ['모험 모집', '통찰']
        self.reject(e, lambda: self.acquire(e, a, 'technique/해트트릭', selection), 'talent slots')
        a.spec['techniques'].pop()
        self.acquire(e, a, 'technique/해트트릭', selection)
        e.gm.set_skill(a, '생존', 5, reason='Expert Survival before native reinforced clothing')
        self.reject(e, lambda: self.acquire(e, a, 'technique/강화옷', selection, 'native/request/2'), 'talent slots')
        a.spec['feat_ranks'][N.JOURNEY] = 2
        self.acquire(e, a, 'technique/강화옷', selection, 'native/request/2')
        self.assertEqual(len(a.spec['techniques']), 3)

    def test_all_requests_replay_without_state_change_and_changed_intent_is_atomic(self):
        for uid in N.DEFINITIONS:
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                first = self.acquire(e, a, uid, selection)
                before = e.export_state()
                self.assertEqual(self.acquire(e, a, uid, selection), first)
                self.assertEqual(e.export_state(), before)
                changed = deepcopy(selection)
                changed['waivers'] = [{'source_id': uid, 'provider': 'native', 'stage': 'acquire',
                    'checks': ['trainer'], 'reason': 'explicit changed request intent'}]
                self.reject(e, lambda: self.acquire(e, a, uid, changed), 'changed intent')

    def test_changed_feature_for_same_request_rejects_and_no_retroactive_owned_certification(self):
        e, a, selection = self.fixture('edge/파워-부스트')
        self.acquire(e, a, 'edge/파워-부스트', selection)
        self.reject(e, lambda: self.acquire(e, a, 'edge/여행자', {'choice': [], 'waivers': []}), 'changed intent')
        for uid, d in N.DEFINITIONS.items():
            e, a, selection = self.fixture(uid)
            a.spec[d['field']].append(d['owned_value'])
            if d.get('choice_field'):
                a.spec[d['choice_field']][uid] = selection['choice']
            # Invalid unconfirmed legacy Blessings cannot be exported as native state.
            if d['kind'] == 'blessing':
                B.confirm(e, a, uid, reason='explicit old-sheet migration only', configuration=selection['configuration'])
            if d['kind'] in ('static', 'class'):
                STATIC.register_all(e, a)
            self.reject(e, lambda: self.acquire(e, a, uid, selection), 'already-owned')

    def test_historical_skill_ownership_and_route_loss_survive_json_and_gm_restore(self):
        for uid, d in N.DEFINITIONS.items():
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                receipt = self.acquire(e, a, uid, selection)
                e.gm.snapshot('native-admission')
                for skill in d.get('skills', {}):
                    e.gm.set_skill(a, skill, 1, reason='later actual skill loss does not rewrite old qualification')
                for parent in d.get('parents', []):
                    # Preserve the parent static projection when a dependent was acquired.
                    if parent.startswith('class/'):
                        a.spec['classes'].remove(parent)
                if d['kind'] == 'blessing':
                    a.spec['feat_ranks'][N.ROUTES[selection['role']]] = 1
                self.assertEqual(N.receipts(a)[0]['snapshot'], receipt['snapshot'])
                N.validate_actor(a)
                restored, actor = self.restore(e, a)
                self.assertEqual(N.receipts(actor)[0]['snapshot'], receipt['snapshot'])
                if d['kind'] == 'blessing':
                    self.assertTrue(B.approval(actor, uid))
                e.gm.restore('native-admission')
                self.assertEqual(N.receipts(a)[0]['snapshot'], receipt['snapshot'])

    def test_all_sources_withdraw_keep_archived_qualification_and_old_replay_does_not_reacquire(self):
        for uid, d in N.DEFINITIONS.items():
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                receipt = self.acquire(e, a, uid, selection)
                self.withdraw(e, a, uid)
                self.assertNotIn(d['owned_value'], a.spec[d['field']])
                archived = N.receipts(a)[0]
                self.assertEqual((archived['state'], archived['snapshot']), ('ended', receipt['snapshot']))
                before = e.export_state()
                self.assertEqual(self.acquire(e, a, uid, selection)['status'], 'withdrawn')
                self.assertEqual(e.export_state(), before)
                self.assertFalse(any(row['source_id'] == uid for row in A.class_instances(a)))
                restored, actor = self.restore(e, a)
                self.assertEqual(N.receipts(actor)[0]['state'], 'ended')

    def test_transaction_failure_after_source_write_keeps_world_rng_and_ownership_unchanged(self):
        transition = G.transition
        for uid in N.DEFINITIONS:
            with self.subTest(source=uid):
                e, a, selection = self.fixture(uid)
                def fail_after_apply(engine, actor, operation):
                    def late_failure(staged, trainer):
                        operation(staged, trainer)
                        staged.rng.random()
                        raise ValueError('injected native commit failure')
                    return transition(engine, actor, late_failure)
                with patch.object(G, 'transition', side_effect=fail_after_apply):
                    self.reject(e, lambda: self.acquire(e, a, uid, selection), 'injected native commit')

    def test_scoped_prerequisite_waiver_has_exact_source_provider_stage_and_check(self):
        uid = 'edge/파워-부스트'
        for field, wrong in (('source_id', 'edge/여행자'), ('provider', 'other-provider'), ('stage', 'owned')):
            e, a, selection = self.fixture(uid)
            a.spec['skills']['육상'] = 4
            waiver = {'source_id': uid, 'provider': 'native', 'stage': 'acquire',
                      'checks': ['skill:육상'], 'reason': 'explicit campaign prerequisite exception'}
            waiver[field] = wrong
            selection['waivers'] = [waiver]
            self.reject(e, lambda: self.acquire(e, a, uid, selection), 'printed rank')
        e, a, selection = self.fixture(uid)
        a.spec['skills']['육상'] = 4
        selection['waivers'] = [{'source_id': uid, 'provider': 'native', 'stage': 'acquire',
            'checks': ['skill:육상'], 'reason': 'explicit campaign prerequisite exception'}]
        row = self.acquire(e, a, uid, selection)
        self.assertEqual(next(check['state'] for check in row['qualification']['checks'] if check['id'] == 'skill:육상'), 'waived')

    def test_explicit_seven_plus_declared_skills_are_not_capped_at_six(self):
        rules = Rules(ROOT, ruleset='all')
        e, a, selection = self.fixture('edge/파워-부스트', rules=rules)
        rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.초월',
            {'rank': 7, 'dice': '7d6', 'eng': 'Epic'}, reason='explicit campaign rank', rules=rules)
        e.gm.set_skill(a, '육상', 7, reason='actual declared rank seven')
        row = self.acquire(e, a, 'edge/파워-부스트', selection)
        self.assertEqual(row['snapshot']['skill:육상'], 7)
        restored, actor = self.restore(e, a)
        self.assertEqual(N.receipts(actor)[0]['snapshot']['skill:육상'], 7)

    def test_farcast_legacy_csv_receipt_replay_preserves_source_before_and_after_withdrawal(self):
        uid = 'feat/파캐스트'
        e, a, selection = self.fixture(uid)
        first = N.acquire(e, a, uid, acquisition_request_id='legacy/csv/farcast', selection=selection)
        before = e.export_state()
        self.assertEqual(T.acquire_static(e, a, uid, acquisition_request_id='legacy/csv/farcast'), first)
        self.assertEqual(e.export_state(), before)
        self.withdraw(e, a, uid)
        e, a = self.restore(e, a)
        before = e.export_state()
        self.assertEqual(T.acquire_static(e, a, uid, acquisition_request_id='legacy/csv/farcast')['status'], 'withdrawn')
        self.assertEqual(e.export_state(), before)
        self.reject(e, lambda: T.acquire_static(e, a, uid,
            acquisition_request_id='legacy/csv/farcast', source_id='C04-119'), 'changed intent or source')

    def test_farcast_exact_csv_source_exclusion_is_enforced_even_with_book_identity_enabled(self):
        uid = 'feat/파캐스트'
        profile = deepcopy(self.rules.ruleset.profile)
        profile['exclude_units'] = list(set(profile.get('exclude_units', [])) | {N.DEFINITIONS[uid]['clause_id']})
        with patch.object(RuleFilter, 'load', return_value=RuleFilter(profile, name='farcast-csv-source-exclusion')):
            rules = Rules(ROOT, ruleset='all')
        e, a, selection = self.fixture(uid, rules=rules)
        self.reject(e, lambda: self.acquire(e, a, uid, selection), 'excluded|Excluded')

    def test_exact_source_exclusion_and_invalid_choices_fail_before_any_commit(self):
        uid = 'feat/파캐스트'
        e, a, selection = self.fixture(uid, rules=Rules(ROOT, ruleset='core'))
        self.reject(e, lambda: self.acquire(e, a, uid, selection), 'excluded|Excluded')
        for uid in N.DEFINITIONS:
            profile = deepcopy(self.rules.ruleset.profile)
            profile['exclude_units'] = list(set(profile.get('exclude_units', [])) | {uid})
            with patch.object(RuleFilter, 'load', return_value=RuleFilter(profile, name='native-test-exclusion')):
                rules = Rules(ROOT, ruleset='all')
            e, a, selection = self.fixture(uid, rules=rules)
            self.reject(e, lambda: self.acquire(e, a, uid, selection), 'excluded|Excluded')
        for uid in ('edge/여행자', 'C2CSV/input/db/feats.csv:R587:main', 'feat/불의-영혼'):
            e, a, selection = self.fixture(uid)
            selection['choice'] = ['jump', 'jump'] if uid == 'edge/여행자' else 'not-a-source-choice'
            self.reject(e, lambda: self.acquire(e, a, uid, selection), 'substitutions|printed source domain')

    def test_new_emergency_care_reaches_native_kit_recovery_and_daily_target_consumer(self):
        import tools.test_category2_class_actor_state_actions as CASES
        case = CASES.ClassActorStateActionTests('runTest')
        case.rules = self.rules
        e, a, pokemon, other = case.fixture()
        a.spec['edges'].append('edge/메딕-훈련')
        e.gm.set_skill(a, '의학', 5, reason='actual Expert Medicine before acquisition')
        self.acquire(e, a, 'feat/응급-처치-전문지식')
        pokemon.hp = 1
        pokemon.injuries = 2
        e.apply_status(pokemon, '독')
        self.reject(e, lambda: e.emergency_care_expertise(a, pokemon), 'inventory')
        a.spec['items']['응급치료키트'] = 1
        result = e.emergency_care_expertise(a, pokemon)
        self.assertEqual(result['injuries_removed'], 1)
        self.assertEqual(pokemon.hp, pokemon.max_hp)
        self.assertNotIn('독', pokemon.conditions)
        self.assertEqual(a.spec['items']['응급치료키트'], 1)
        self.reject(e, lambda: e.emergency_care_expertise(a, pokemon), 'target daily')

    def test_new_top_percentage_reaches_native_growth_four_use_and_stat_consumer(self):
        import tools.test_category2_class_actor_state_actions as CASES
        import class_actor_state_actions as ACTIONS
        import downtime
        case = CASES.ClassActorStateActionTests('runTest')
        case.rules = self.rules
        e, a, pokemon, other = case.fixture(level=4, species='메타몽', moves=('변신',))
        a.spec.setdefault('classes', []).append('class/에이스-트레이너')
        e.gm.set_skill(a, '명령', 5, reason='actual Expert Command before acquisition')
        self.acquire(e, a, 'feat/탑-퍼센티지')
        before = pokemon.spec['tutor_points']
        for level in (5, 10, 15, 20):
            while pokemon.level < level:
                downtime.gain_exp_combatant(e, pokemon, 'to next level')
            event = case.one(e, a, ACTIONS.TOP_PERCENTAGE)
            result = e.resolve_class_actor_state_action(a, event['id'], use=True)
            self.assertEqual(result['target_uses'], level // 5)
        self.assertEqual(pokemon.spec['tutor_points'], before + 8)
        for stat in pokemon.stats:
            self.assertEqual(pokemon.stats[stat], pokemon.spec['stats'][stat] + 1)

    def test_new_talents_reach_native_head_body_critical_and_nonstack_consumers(self):
        import tools.test_category2_class_passive_combat_bulk as CASES
        import class_passive_combat as PASSIVE
        import items
        case = CASES.ClassPassiveCombatBulkTests('runTest')
        case.rules = self.rules
        e, a, pokemon, enemy = case.fixture(feats=[N.JOURNEY])
        a.spec['feat_ranks'] = {N.JOURNEY: 1}
        e.gm.set_skill(a, '생존', 5, reason='Expert Survival before talent acquisition')
        self.acquire(e, a, 'technique/해트트릭', request='native/hat')
        self.acquire(e, a, 'technique/강화옷', request='native/clothing')
        physical = self.rules.move('move/몸통박치기')
        special = self.rules.move('move/화염방사')
        self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, physical, 1.0, True), 0)
        items.register_item(e, a, 'item/선글라스')
        self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, physical, 1.0, True), 15)
        self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, physical, 1.0, False), 0)
        # Vary only the source-read price seam; the equipped native item remains real.
        original = self.rules.item_effects
        for price, expected in ((999, 0), (1000, 15)):
            def observed_price(name):
                effects, header = original(name)
                return effects, dict(header, price=price)
            with patch.object(self.rules, 'item_effects', side_effect=observed_price):
                self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, physical, 1.0, True), expected)
        items.register_item(e, a, 'item/경갑')
        self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, physical, 1.0, False), 0)
        self.assertEqual(PASSIVE.damage_reduction(e, enemy, a, special, 1.0, False), 5)


if __name__ == '__main__':
    unittest.main()
