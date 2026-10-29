"""Researcher Fields of Study: Climatology (static/teaching), Paleontology and Pokemon Caretaking Pokemon-side Features (ch04:2111-2128).

Borrows fixture helpers from the crafting module without inheriting its tests.
"""
from copy import deepcopy
import ast
import hashlib
import json
import unittest
from unittest.mock import patch

import test_book_researcher_fields_crafting as fixture
from engine import Rules
import researcher_fields as RFS
import researcher_features as RF
import move_state as MOVES
import growth_stats as GROWTH
import world_entities as WORLD


class ResearcherFieldsPokemonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    setUp = fixture.ResearcherFieldsCraftingTests.setUp
    setup = fixture.ResearcherFieldsCraftingTests.setup
    trainer = fixture.ResearcherFieldsCraftingTests.trainer
    pokemon = fixture.ResearcherFieldsCraftingTests.pokemon
    rejected = fixture.ResearcherFieldsCraftingTests.rejected
    valid = fixture.ResearcherFieldsCraftingTests.valid
    restore = fixture.ResearcherFieldsCraftingTests.restore
    new_day = fixture.ResearcherFieldsCraftingTests.new_day

    def fossil(self, species, name, *, feature=False, hidden=None):
        """Search, restore (natively or with Fossil Restoration) and return the unhatched egg."""
        import skill_modifiers as SKILLS
        self.t.spec['items']['복원기'] = 1
        if 'pokemon_party_policy' not in self.t.spec:
            self.e.pokemon_activity(self.t, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'fossil', phase='search', site={'name': 'GM deposit', 'fossils_present': True}, dc=15, minutes=120,
                                discovery={'id': name, 'species': 'pokemon/' + species}, fixed=[6] * SKILLS.rank(self.rules, self.t, '포켓몬학')[2])
        if feature:
            egg = RFS.fossil_restoration(self.e, self.t, fossil_id=name, seconds=600, reason='actual Fossil Restoration')['egg']
        else:
            egg = self.e.pokemon_activity(self.t, 'fossil', phase='restore', fossil_id=name)['egg']
        return next(row for row in self.t.spec['eggs'] if row['entity_id'] == egg['entity_id'])

    def hatch(self, egg, name, *, abilities=None, nature='노력'):
        if abilities is None:
            abilities = () if RFS.FOSSIL_MARK in egg else self.rules.learnsets[egg['species'].removeprefix('pokemon/')]['abilities']['기본 특성'][:1]
        details = dict(gender='female', nature=nature, abilities=list(abilities), moves=[], inheritance_moves=[], special_appearance=False)
        child = self.e.pokemon_activity(self.t, 'hatch_fossil', egg_id=egg['id'], name=name, ready=True, reason='GM confirmed readiness', details=details)['pokemon']
        self.e.gm.observe_loyalty(child, 6, reason='actual willing Pokemon')
        return child

    def restored(self, species, name, **extra):
        return self.hatch(self.fossil(species, name), name, **extra)

    def reject_invalid_fossil_evidence(self, egg, record, change):
        """Inject only the disputed evidence; compare the entire valid world/RNG after removing that injection."""
        before = self.e.export_state()
        original_egg, original_record = deepcopy(egg), deepcopy(record)
        try:
            change(egg, record)
            invalid_egg, invalid_record = deepcopy(egg), deepcopy(record)
            self.assertFalse(self.e.validate_state()['valid'])
            with self.assertRaisesRegex(ValueError, 'Fossil Restoration'):
                self.hatch(egg, 'forged child', abilities=[])
            self.assertEqual((egg, record), (invalid_egg, invalid_record))
        finally:
            egg.clear(); egg.update(original_egg)
            if record is not None:
                record.clear(); record.update(original_record)
        self.assertEqual(self.e.export_state(), before)

    def saved_egg_node(self, payload, egg):
        return next(node for node in payload['nodes'].values()
                    if node['kind'] == 'dict' and ['entity_id', egg['entity_id']] in node['items'])

    def legacy_fossil_fixture(self, name, *, hatched=False):
        """Project genuine native facts to the exact save fields written by the frozen old producers."""
        source = json.loads((fixture.ROOT / 'data/verification/audit-egg-fossil-legacy-producer-source.json').read_text(encoding='utf-8'))
        trees = {}
        for function, row in source['functions'].items():
            self.assertEqual(hashlib.sha256(row['source'].encode('utf-8')).hexdigest(), row['sha256_utf8'])
            trees[function] = ast.parse(row['source'])
            self.assertNotIn(RFS.FOSSIL_AUTHORITY, row['source'])
        producer = trees['fossil_restoration']
        pending = next(node for node in ast.walk(producer) if isinstance(node, ast.Dict) and
                       any(isinstance(key, ast.Constant) and key.value == 'fossil_id' for key in node.keys))
        completed = next(node for node in ast.walk(producer) if isinstance(node, ast.Call) and
                         isinstance(node.func, ast.Attribute) and node.func.attr == 'update' and
                         {keyword.arg for keyword in node.keywords} == {'status', 'egg_entity_id'})
        self.assertEqual({key.value for key in pending.keys} | {keyword.arg for keyword in completed.keywords} | {'tutor_points'}, set(source['legacy_event_fields']))
        declaration = trees['fossil_restoration_declaration']
        self.assertTrue(any(isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'pending' and
                            isinstance(node.slice, ast.Constant) and node.slice.value == 'tutor_points' and isinstance(node.ctx, ast.Store)
                            for node in ast.walk(declaration)))
        mark = next(node for node in ast.walk(trees['fossil_restoration_mark']) if isinstance(node, ast.Dict))
        self.assertEqual({key.value for key in mark.keys}, set(source['legacy_marker_fields']))
        choice_targets = [target for node in ast.walk(trees['choose_hidden_ability']) if isinstance(node, ast.Assign)
                          for target in node.targets if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value == 'gm_hidden_ability']
        self.assertEqual(len(choice_targets), 1)
        self.assertEqual(ast.dump(choice_targets[0].value), ast.dump(ast.parse('egg[FOSSIL_MARK]', mode='eval').body))
        import creation_fossil as FOSSIL
        native = FOSSIL.native
        # Execute the actual producer with its preserved pre-Q43 birth policy.
        # Its real request/egg/feature receipts are produced with1→0/deficit1;
        # no historical balance, award or past interpretation is synthesized.
        with patch.object(FOSSIL, 'native', lambda **options: native(legacy=True)), patch.object(FOSSIL, 'INITIAL_LEVEL_BASIS', None):
            egg = self.fossil('릴링', name, feature=True)
        RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='저수', reason='original GM chose Water Absorb')
        if hatched:
            self.hatch(egg, 'historical lawful child')
        record = self.t.spec[RFS.KEY]['fossils'][-1]
        original_egg, original_event = deepcopy(egg), deepcopy(record)
        self.assertEqual((record.pop(RFS.FOSSIL_AUTHORITY), record.pop('gm_hidden_ability')), (1, egg[RFS.FOSSIL_MARK]['gm_hidden_ability']))
        self.assertEqual(set(record), set(source['legacy_event_fields']))
        self.assertEqual(record, {key: original_event[key] for key in source['legacy_event_fields']})
        self.assertEqual(egg, original_egg)
        self.valid()
        return egg, record

    # ------------------------------------------------------------ Climatology
    def test_climatology_grants_overcoat_while_qualified_and_the_grant_is_revoked_with_the_feature(self):
        self.t.spec['skills']['생존'] = 2
        self.rejected(lambda: RFS.activate_climatology(self.e, self.t), 'Climatology requires its printed skill rank')
        self.t.spec['skills']['생존'] = 3
        sid = RFS.activate_climatology(self.e, self.t)
        self.assertEqual((sid, self.t.abilities), (RFS.CLIMATOLOGY_PREFIX + self.t.entity_id, ['방진']))
        self.assertEqual(RFS.activate_climatology(self.e, self.t), sid)
        self.restore('t')
        self.assertEqual(self.t.abilities, ['방진'])
        self.t.spec['feats'].remove(RFS.CLIMATOLOGY)
        self.assertFalse(self.e.validate_state()['valid'])
        RFS.release_climatology(self.e, self.t)
        self.assertEqual(self.t.abilities, [])
        self.valid()

    def test_weather_systems_teaches_one_printed_weather_move_by_a_real_route_free_from_the_level_up_list(self):
        w = self.pokemon('투구', 20, 'learner', moves=['move/단단해지기', 'move/할퀴기'], tutor_points=8)
        s = self.pokemon('캐스퐁', 20, 'sunny', pos=(2, 0), moves=['move/몸통박치기'], tutor_points=8)   # Sunny Day is on its Level-Up list at 20
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/몸통박치기', seconds=3600, reason='x'), 'Hail, Rain Dance, Sandstorm or Sunny Day')
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/쾌청', seconds=3600, reason='x'), 'cannot learn that Move by level_up, tm, tutor')
        self.t.spec['skills']['생존'] = 4
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='x'), 'Weather Systems requires its printed skill rank')
        self.t.spec['skills']['생존'] = 6
        w.spec['tutor_points'] = 1
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='x'), 'two actual Tutor Points')
        w.spec['tutor_points'] = 8
        elapsed = self.e.elapsed_seconds
        out = RFS.weather_systems(self.e, self.t, w, 'move/싸라기눈', seconds=3600, reason='actual teaching')
        self.assertEqual((out['point_cost'], out['routes'], out['classification'], w.spec['tutor_points'], self.e.elapsed_seconds - elapsed), (2, ['tm'], 'taught', 6, 3600))
        self.assertIn('move/싸라기눈', w.moves)
        routes = RFS.learning_routes(self.e, s, 'move/쾌청')
        self.assertIn('level_up', routes)
        out = RFS.weather_systems(self.e, self.t, s, 'move/쾌청', seconds=3600, reason='level-up list route')
        self.assertEqual((out['point_cost'], s.spec['tutor_points'], s.spec['move_learning']['move/쾌청']['paid_tp']), (0, 8, 0))
        other = self.trainer('stranger', (5, 5))
        wild = self.pokemon('투구', 20, 'other owned', pos=(6, 5), owner=other, moves=['move/단단해지기'], tutor_points=8)
        self.rejected(lambda: RFS.weather_systems(self.e, self.t, wild, 'move/싸라기눈', seconds=3600, reason='x'), 'actual owned Pokemon')
        self.valid()
        self.restore('t')

    # ------------------------------------------------------------ Paleontology
    def test_fossil_restoration_lowers_birth_tutor_points_by_two_and_hatches_with_both_basic_abilities(self):
        self.t.spec['items']['복원기'] = 1
        self.e.pokemon_activity(self.t, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'fossil', phase='search', site={'name': 'GM deposit', 'fossils_present': True}, dc=15, minutes=120,
                                discovery={'id': 'F', 'species': 'pokemon/프테라'}, fixed=[3] * 6)
        self.t.spec['skills']['포켓몬학'] = 2
        self.rejected(lambda: RFS.fossil_restoration(self.e, self.t, fossil_id='F', seconds=600, reason='x'), 'Fossil Restoration requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        self.rejected(lambda: RFS.fossil_restoration(self.e, self.t, fossil_id='missing', seconds=600, reason='x'), 'unconsumed owned fossil')
        elapsed = self.e.elapsed_seconds
        out = RFS.fossil_restoration(self.e, self.t, fossil_id='F', seconds=600, reason='actual restoration')
        egg = self.t.spec['eggs'][0]
        self.assertEqual((out['phase'], self.e.elapsed_seconds - elapsed, egg['fossil_birth_policy']['tutor_points'], egg[RFS.FOSSIL_MARK]['tutor_points']),
                         ('restore', 600, 1, {'native': 3, 'printed_delta': -2, 'birth': 1, 'deficit': 0}))
        self.assertEqual(self.t.spec[RFS.KEY]['fossils'][-1]['status'], 'restored')
        self.restore('t')
        egg = self.t.spec['eggs'][0]
        self.rejected(lambda: self.hatch(egg, 'wrong', abilities=['겁주기']), 'must be exactly')
        child = self.hatch(egg, 'child')
        self.assertEqual((sorted(child.abilities), child.spec['tutor_points']), (['겁주기', '긴장감'], 1))
        self.valid()

    def test_plain_native_fossil_rejects_empty_foreign_hidden_and_multiple_birth_abilities(self):
        egg = self.fossil('암나이트', 'ordinary', feature=False)
        self.assertNotIn(RFS.FOSSIL_MARK, egg)
        for abilities in ([], ['정전기'], ['쓱쓱'], ['조가비갑옷', '깨어진갑옷']):
            reason = 'missing_source_identity' if abilities == ['쓱쓱'] else 'one species Basic|outside.*species Basic'
            self.rejected(lambda: self.hatch(egg, 'invalid', abilities=abilities), reason)
        child = self.hatch(egg, 'ordinary child', abilities=['깨어진갑옷'])
        self.assertEqual((child.level, child.abilities, child.spec['tutor_points']), (10, ['깨어진갑옷'], 3))
        self.valid()
        self.restore('t')
        self.assertEqual(WORLD.actor_index(self.e)[child.entity_id].abilities, ['깨어진갑옷'])

    def test_single_basic_ability_species_needs_the_gm_hidden_ability_choice_before_hatching(self):
        egg = self.fossil('릴링', 'single', feature=True)
        self.rejected(lambda: self.hatch(egg, 'child'), 'GM-chosen hidden Ability')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='흡반', reason='x'), 'hidden Abilities')
        out = RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='저수', reason='GM chose Water Absorb')
        self.assertEqual(out['gm_hidden_ability']['ability'], '저수')
        self.assertEqual(RFS.fossil_birth_details(self.e, self.t, egg, {'abilities': []})['abilities'], ['흡반', '저수'])
        two = self.fossil('프테라', 'two', feature=True)
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, two['entity_id'], ability='잔인', reason='x'), 'already has two basic Abilities')
        self.valid()
        self.restore('t')
        egg = next(row for row in self.t.spec['eggs'] if row['entity_id'] == egg['entity_id'])
        child = self.hatch(egg, 'single-basic feature child')
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['흡반', '저수'], 1))
        self.valid()
        self.restore('t')
        self.assertEqual(WORLD.actor_index(self.e)[child.entity_id].abilities, ['흡반', '저수'])

    def test_fossil_restoration_rejects_bare_copied_and_unearned_markers_in_live_and_json_worlds(self):
        genuine = self.fossil('암나이트', 'actual feature event', feature=True)
        ordinary = self.fossil('암나이트', 'ordinary despite owning the feat', feature=False)
        self.assertNotIn(RFS.FOSSIL_MARK, ordinary)
        self.assertEqual(len(self.t.spec[RFS.KEY]['fossils']), 1)
        for facts in ({}, None, deepcopy(genuine[RFS.FOSSIL_MARK])):
            with self.subTest(marker=facts):
                self.reject_invalid_fossil_evidence(ordinary, None,
                    lambda egg, record: egg.__setitem__(RFS.FOSSIL_MARK, deepcopy(facts)))
        for kind in ('empty', 'null', 'copied'):
            with self.subTest(json_marker=kind):
                payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
                if kind == 'empty':
                    uid = 'n' + str(len(payload['nodes']))
                    self.assertNotIn(uid, payload['nodes'])
                    payload['nodes'][uid] = {'kind': 'dict', 'items': []}
                    marker = {'$ref': uid}
                elif kind == 'null':
                    marker = None
                else:
                    marker = deepcopy(dict(self.saved_egg_node(payload, genuine)['items'])[RFS.FOSSIL_MARK])
                self.saved_egg_node(payload, ordinary)['items'].append([RFS.FOSSIL_MARK, marker])
                self.rejected(lambda: type(self.e).import_state(self.rules, payload), 'Fossil Restoration')
        child = self.hatch(ordinary, 'ordinary remains ordinary', abilities=['깨어진갑옷'])
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['깨어진갑옷'], 3))
        self.valid()

    def test_fossil_restoration_rejects_changed_event_marker_and_missing_authority_without_side_effects(self):
        egg = self.fossil('암나이트', 'bound event', feature=True)
        record = self.t.spec[RFS.KEY]['fossils'][-1]
        for field, value in (('trainer_id', 'trainer/forged'), ('feature', RFS.ANCIENT), ('clause_id', 'forged'),
                             ('tutor_points', {'native': 1, 'printed_delta': 0, 'birth': 1, 'deficit': 0}),
                             ('tutor_points', {'native': 1, 'printed_delta': -2, 'birth': False, 'deficit': 1}),
                             ('second_basic_ability', 1), ('gm_hidden_ability', {'ability': '쓱쓱', 'reason': 'forged', 'at': self.e.elapsed_seconds})):
            with self.subTest(marker_field=field):
                self.reject_invalid_fossil_evidence(egg, record,
                    lambda egg, record: egg[RFS.FOSSIL_MARK].__setitem__(field, deepcopy(value)))
        for field, value in (('fossil_id', 'other fossil'), ('egg_entity_id', 'egg/other'), ('status', 'pending'),
                             ('tutor_points', {'native': 1, 'printed_delta': -2, 'birth': 1, 'deficit': 1}), ('at', egg['produced_at'])):
            with self.subTest(event_field=field):
                self.reject_invalid_fossil_evidence(egg, record,
                    lambda egg, record: record.__setitem__(field, deepcopy(value)))
        self.reject_invalid_fossil_evidence(egg, record, lambda egg, record: egg.pop(RFS.FOSSIL_MARK))
        self.reject_invalid_fossil_evidence(egg, record, lambda egg, record: egg.__setitem__(RFS.FOSSIL_MARK, {}))
        payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        marker = dict(self.saved_egg_node(payload, egg)['items'])[RFS.FOSSIL_MARK]
        facts = payload['nodes'][marker['$ref']]
        next(pair for pair in facts['items'] if pair[0] == 'trainer_id')[1] = 'trainer/forged'
        self.rejected(lambda: type(self.e).import_state(self.rules, payload), 'Fossil Restoration')
        child = self.hatch(egg, 'actual event child')
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['조가비갑옷', '깨어진갑옷'], 1))
        self.valid()

    def test_fossil_restoration_transferred_egg_keeps_original_event_through_gm_and_json_restore(self):
        for species, expected in (('암나이트', ['조가비갑옷', '깨어진갑옷']), ('릴링', ['흡반', '저수'])):
            with self.subTest(species=species):
                self.setUp()
                egg = self.fossil(species, 'gift', feature=True)
                original_id = self.t.entity_id
                self.recipient = self.trainer('recipient without the feature', (1, 0), feats=[])
                self.e.pokemon_activity(self.recipient, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
                self.e.gm.transfer_egg(self.t, self.recipient, egg['entity_id'], reason='actual marked egg gift', request_id='marked-gift')
                if species == '릴링':
                    RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='저수', reason='GM chose Water Absorb after the gift')
                record = deepcopy(self.t.spec[RFS.KEY]['fossils'][-1])
                details = dict(gender='female', nature='노력', abilities=[], moves=[], inheritance_moves=[], special_appearance=False)
                snapshot = self.e.gm.snapshot()
                first = self.e.hatch_restored_fossil(self.recipient, egg['entity_id'], name='gift child', ready=True, reason='GM readiness', details=details)['pokemon']
                self.assertEqual((first.abilities, first.spec['trainer_id'], first.spec['tutor_points']), (expected, self.recipient.entity_id, 1))
                self.e.gm.restore(snapshot)
                self.assertNotIn(first.entity_id, WORLD.actor_index(self.e))
                self.restore('t', 'recipient')
                egg = next(row for row in self.recipient.spec['eggs'] if row['entity_id'] == egg['entity_id'])
                self.assertEqual((egg[RFS.FOSSIL_MARK]['trainer_id'], egg['restored_by'], self.t.spec[RFS.KEY]['fossils'][-1]), (original_id, original_id, record))
                self.assertNotIn(RFS.FOSSIL_RESTORATION, self.recipient.spec['feats'])
                child = self.e.hatch_restored_fossil(self.recipient, egg['entity_id'], name='gift child', ready=True, reason='GM readiness', details=details)['pokemon']
                self.assertEqual((child.abilities, child.spec['trainer_id'], child.spec['tutor_points']), (expected, self.recipient.entity_id, 1))
                self.restore('t', 'recipient')
                self.assertEqual(WORLD.actor_index(self.e)[child.entity_id].abilities, expected)
                self.assertEqual(self.t.spec[RFS.KEY]['fossils'][-1], record)

    def test_fossil_restoration_gm_choice_is_bound_to_the_original_event(self):
        egg = self.fossil('릴링', 'GM event', feature=True)
        RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='저수', reason='GM chose Water Absorb')
        record = self.t.spec[RFS.KEY]['fossils'][-1]
        self.assertEqual(record['gm_hidden_ability'], egg[RFS.FOSSIL_MARK]['gm_hidden_ability'])
        self.reject_invalid_fossil_evidence(egg, record,
            lambda egg, record: egg[RFS.FOSSIL_MARK]['gm_hidden_ability'].__setitem__('ability', '마중물'))
        self.reject_invalid_fossil_evidence(egg, record,
            lambda egg, record: record['gm_hidden_ability'].__setitem__('ability', '마중물'))
        payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
        marker = dict(self.saved_egg_node(payload, egg)['items'])[RFS.FOSSIL_MARK]
        chosen = dict(payload['nodes'][marker['$ref']]['items'])['gm_hidden_ability']
        next(pair for pair in payload['nodes'][chosen['$ref']]['items'] if pair[0] == 'ability')[1] = '마중물'
        self.rejected(lambda: type(self.e).import_state(self.rules, payload), 'Fossil Restoration')
        child = self.hatch(egg, 'GM chosen child')
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['흡반', '저수'], 1))
        self.valid()

    def test_legacy_fossil_choice_waits_for_exact_confirmation_after_transfer_and_survives_gm_json_hatch(self):
        egg, record = self.legacy_fossil_fixture('legacy selected egg')
        original_event, original_egg = deepcopy(record), deepcopy(egg)
        self.recipient = self.trainer('legacy recipient without feature', (1, 0), feats=[])
        self.e.pokemon_activity(self.recipient, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.gm.transfer_egg(self.t, self.recipient, egg['entity_id'], reason='actual legacy egg gift', request_id='legacy-gift')
        self.restore('t', 'recipient')
        egg = next(row for row in self.recipient.spec['eggs'] if row['entity_id'] == egg['entity_id'])
        record = self.t.spec[RFS.KEY]['fossils'][-1]
        self.assertEqual((record, egg[RFS.FOSSIL_MARK]), (original_event, original_egg[RFS.FOSSIL_MARK]))
        details = dict(gender='female', nature='노력', abilities=[], moves=[], inheritance_moves=[], special_appearance=False)
        hatch = lambda: self.e.hatch_restored_fossil(self.recipient, egg['entity_id'], name='legacy child', ready=True, reason='GM readiness', details=details)['pokemon']
        self.rejected(hatch, 'legacy Fossil Restoration choice requires explicit GM confirmation')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='마중물', reason='not confirmation'), 'requires explicit GM confirmation')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='마중물', reason='wrong confirmation', confirm_legacy=True), 'retain exactly the existing GM Ability')
        balance = (self.e.elapsed_seconds, fixture.AP.available(self.t), fixture.AP.available(self.recipient), deepcopy(egg['fossil_birth_policy']))
        before_egg = deepcopy(egg)
        confirmed = RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='저수', reason='GM confirms the retained historical selection', confirm_legacy=True)
        self.assertEqual((confirmed, egg), (original_egg[RFS.FOSSIL_MARK], before_egg))
        self.assertEqual({key: record[key] for key in original_event}, original_event)
        self.assertEqual((record['gm_hidden_ability'], record['legacy_hidden_ability_confirmation']['trainer_id']), (original_egg[RFS.FOSSIL_MARK]['gm_hidden_ability'], self.recipient.entity_id))
        self.assertEqual((self.e.elapsed_seconds, fixture.AP.available(self.t), fixture.AP.available(self.recipient), egg['fossil_birth_policy']), balance)
        self.assertNotIn(RFS.FOSSIL_RESTORATION, self.recipient.spec['feats'])
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='저수', reason='duplicate confirmation', confirm_legacy=True), 'only an unconfirmed actual legacy')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.recipient, egg['entity_id'], ability='마중물', reason='reset'), 'cannot be reset')
        snapshot = self.e.gm.snapshot()
        first = hatch()
        self.assertEqual((first.abilities, first.spec['tutor_points'], first.spec['trainer_id']), (['흡반', '저수'], 0, self.recipient.entity_id))
        self.e.gm.restore(snapshot)
        self.restore('t', 'recipient')
        child = hatch()
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['흡반', '저수'], 0))
        self.restore('t', 'recipient')
        self.assertEqual(WORLD.actor_index(self.e)[child.entity_id].abilities, ['흡반', '저수'])
        record = self.t.spec[RFS.KEY]['fossils'][-1]
        self.assertEqual({key: record[key] for key in original_event}, original_event)

    def test_legacy_fossil_confirmation_distinguishes_absent_explicit_none_other_choice_and_new_schema(self):
        current = self.fossil('릴링', 'new schema egg', feature=True)
        current_record = self.t.spec[RFS.KEY]['fossils'][-1]
        self.assertEqual((current_record[RFS.FOSSIL_AUTHORITY], current_record['gm_hidden_ability']), (1, None))
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, current['entity_id'], ability='저수', reason='not legacy', confirm_legacy=True), 'only an unconfirmed actual legacy')
        RFS.choose_hidden_ability(self.e, self.t, current['entity_id'], ability='저수', reason='actual current GM choice')
        self.reject_invalid_fossil_evidence(current, current_record, lambda egg, record: record.pop('gm_hidden_ability'))
        egg, record = self.legacy_fossil_fixture('legacy mismatches')
        chosen = egg[RFS.FOSSIL_MARK]['gm_hidden_ability']
        for value in (None, dict(chosen, ability='마중물')):
            with self.subTest(explicit_event_choice=value):
                self.reject_invalid_fossil_evidence(egg, record, lambda egg, record: record.__setitem__('gm_hidden_ability', deepcopy(value)))
                payload = json.loads(json.dumps(self.e.export_state(), ensure_ascii=False))
                event = next(node for node in payload['nodes'].values() if node['kind'] == 'dict' and ['egg_entity_id', egg['entity_id']] in node['items'] and ['status', 'restored'] in node['items'])
                if value is None:
                    saved_choice = None
                else:
                    marker = dict(self.saved_egg_node(payload, egg)['items'])[RFS.FOSSIL_MARK]
                    old_choice = dict(payload['nodes'][marker['$ref']]['items'])['gm_hidden_ability']
                    uid = 'n' + str(len(payload['nodes']))
                    self.assertNotIn(uid, payload['nodes'])
                    payload['nodes'][uid] = deepcopy(payload['nodes'][old_choice['$ref']])
                    next(pair for pair in payload['nodes'][uid]['items'] if pair[0] == 'ability')[1] = '마중물'
                    saved_choice = {'$ref': uid}
                event['items'].append(['gm_hidden_ability', saved_choice])
                self.rejected(lambda: type(self.e).import_state(self.rules, payload), 'Fossil Restoration authority facts disagree')
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, egg['entity_id'], ability='저수', reason='not a boolean', confirm_legacy=1), 'explicit boolean legacy')
        self.valid()

    def test_legacy_fossil_confirmation_rejects_bare_copied_markers_and_missing_original_event(self):
        genuine, event = self.legacy_fossil_fixture('actual legacy event')
        ordinary = self.fossil('릴링', 'ordinary has no event', feature=False)
        for facts in ({}, None, deepcopy(genuine[RFS.FOSSIL_MARK])):
            with self.subTest(marker=facts):
                before = self.e.export_state()
                ordinary[RFS.FOSSIL_MARK] = deepcopy(facts)
                bad = deepcopy(ordinary)
                try:
                    with self.assertRaisesRegex(ValueError, 'Fossil Restoration'):
                        RFS.choose_hidden_ability(self.e, self.t, ordinary['entity_id'], ability='저수', reason='cannot manufacture legacy authority', confirm_legacy=True)
                    self.assertEqual(ordinary, bad)
                finally:
                    ordinary.pop(RFS.FOSSIL_MARK)
                self.assertEqual(self.e.export_state(), before)
        before = self.e.export_state()
        records = self.t.spec[RFS.KEY]['fossils']
        index = records.index(event)
        records.pop(index)
        try:
            with self.assertRaisesRegex(ValueError, 'Fossil Restoration'):
                RFS.choose_hidden_ability(self.e, self.t, genuine['entity_id'], ability='저수', reason='missing original event', confirm_legacy=True)
            self.assertNotIn(event, records)
        finally:
            records.insert(index, event)
        self.assertEqual(self.e.export_state(), before)
        self.valid()

    def test_legacy_fossil_confirmation_preserves_already_hatched_child_after_ownership_transfer(self):
        egg, record = self.legacy_fossil_fixture('already hatched legacy', hatched=True)
        child_id, egg_id = egg['pokemon_id'], egg['entity_id']
        child = WORLD.actor_index(self.e)[child_id]
        self.assertEqual((child.abilities, child.spec['tutor_points']), (['흡반', '저수'], 0))
        original_event, original_egg = deepcopy(record), deepcopy(egg)
        self.recipient = self.trainer('historical child recipient', (1, 0), feats=[])
        self.e.pokemon_activity(self.recipient, 'party_policy', mode='unlimited', reason='GM carrying policy', roster=[])
        self.e.pokemon_activity(self.t, 'party_transfer', target=child, new_owner=self.recipient, reason='actual historical child gift', request_id='legacy-child-gift')
        self.restore('t', 'recipient')
        child = WORLD.actor_index(self.e)[child_id]
        before_child = deepcopy((child.spec, child.stats, child.abilities, child.modifiers))
        self.assertEqual(child.spec['trainer_id'], self.recipient.entity_id)
        self.assertEqual(self.t.spec[RFS.KEY]['fossils'][-1], original_event)
        self.rejected(lambda: RFS.choose_hidden_ability(self.e, self.t, egg_id, ability='저수', reason='former owner', confirm_legacy=True), 'actual owned legacy')
        pending_snapshot = self.e.gm.snapshot()
        for phase in ('first confirmation', 'after pending GM rollback and JSON'):
            with self.subTest(phase=phase):
                before = (self.e.elapsed_seconds, fixture.AP.available(self.t), fixture.AP.available(self.recipient))
                RFS.choose_hidden_ability(self.e, self.recipient, egg_id, ability='저수', reason='GM confirms original hatched selection', confirm_legacy=True)
                child = WORLD.actor_index(self.e)[child_id]
                self.assertEqual((child.spec, child.stats, child.abilities, child.modifiers), before_child)
                self.assertEqual((self.e.elapsed_seconds, fixture.AP.available(self.t), fixture.AP.available(self.recipient)), before)
                self.assertEqual(next(row for row in self.t.spec['eggs'] if row['entity_id'] == egg_id), original_egg)
                self.assertEqual({key: self.t.spec[RFS.KEY]['fossils'][-1][key] for key in original_event}, original_event)
                if phase == 'first confirmation':
                    self.e.gm.restore(pending_snapshot)
                    self.restore('t', 'recipient')
                    self.assertNotIn('gm_hidden_ability', self.t.spec[RFS.KEY]['fossils'][-1])
        self.restore('t', 'recipient')
        self.assertEqual(WORLD.actor_index(self.e)[child_id].abilities, ['흡반', '저수'])

    def test_ancient_heritage_teaches_ancient_power_free_from_the_level_up_list_else_for_two_points_only_to_your_fossil_pokemon(self):
        k = self.restored('프테라', 'fossil')
        n = self.pokemon('투구', 20, 'ordinary', pos=(3, 0), moves=['move/단단해지기'], tutor_points=8)
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, n, seconds=3600, reason='x'), 'restored from a fossil')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=1, reason='GM confirms below Ancient Heritage minimum')
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='x'), 'two actual Tutor Points')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=6, reason='GM establishes the actual balance')
        out = RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='actual teaching')
        self.assertEqual((out['point_cost'], sorted(out['routes']), k.spec['tutor_points']), (0, ['level_up', 'tutor'], 6))
        self.assertTrue(RFS.ancient_heritage_active(self.e, k))
        self.rejected(lambda: RFS.ancient_heritage(self.e, self.t, k, seconds=3600, reason='x'), 'already learned')
        self.rejected(lambda: RFS.choose_ancient_power_class(self.e, k, '변화'), '물리 or 특수')
        self.assertEqual(RFS.choose_ancient_power_class(self.e, k, '물리'), '물리')
        self.restore('t')
        k = WORLD.actor_index(self.e)[k.entity_id]
        self.assertEqual(k.spec['researcher_ancient_power_choice'], '물리')
        t2 = self.restored('꼬마돌', 'paid')   # GM-approved nonstandard fossil species: Ancient Power only on its Tutor list
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=t2, balance=6, reason='GM establishes the actual balance')
        out = RFS.ancient_heritage(self.e, self.t, t2, seconds=3600, reason='tutor list route')
        self.assertEqual((out['point_cost'], out['routes'], t2.spec['tutor_points']), (2, ['tutor'], 4))
        self.valid()

    def test_genetic_memory_teaches_egg_and_tutor_moves_once_per_route_daily_twice_and_keeps_the_egg_route_outside_the_pool_limit(self):
        k = self.restored('프테라', 'fossil')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=k, balance=12, reason='GM establishes the actual balance')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='tm', seconds=3600, reason='x'), 'route is egg or tutor')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/아쿠아테일', route='egg', seconds=3600, reason='x'), 'cannot learn that Move by the egg route')
        self.t.spec['skills']['포켓몬학'] = 4
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='egg', seconds=3600, reason='x'), 'Genetic Memory requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        egg = RFS.genetic_memory(self.e, self.t, k, 'move/저주', route='egg', seconds=3600, reason='egg route')
        self.assertEqual((egg['point_cost'], egg['classification'], k.spec['tutor_points']), (2, 'natural', 10))
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, k, 'move/승부굳히기', route='egg', seconds=3600, reason='x'), 'already used the egg route')
        tutor = RFS.genetic_memory(self.e, self.t, k, 'move/아쿠아테일', route='tutor', seconds=3600, reason='tutor route')
        self.assertEqual((tutor['point_cost'], tutor['classification'], k.spec['tutor_points']), (2, 'taught', 8))
        self.assertTrue(RFS.pool_exempt(k.spec, 'move/저주'))
        self.assertFalse(RFS.pool_exempt(k.spec, 'move/아쿠아테일'))
        self.assertEqual(MOVES.describe(self.rules, k.spec, require_routes=True)['taught_count'], 1)
        other = self.restored('아마루스', 'second')
        self.e.pokemon_activity(self.t, 'observe_tutor_points', target=other, balance=6, reason='GM establishes the actual balance')
        self.rejected(lambda: RFS.genetic_memory(self.e, self.t, other, 'move/배리어', route='egg', seconds=3600, reason='x'), 'daily frequency')
        self.new_day()
        out = RFS.genetic_memory(self.e, self.t, other, 'move/배리어', route='egg', seconds=3600, reason='next day')
        self.assertEqual(out['route'], 'egg')
        self.valid()
        self.restore('t')

    def test_prehistoric_bond_makes_each_printed_relic_from_the_individuals_highest_nature_adjusted_base_stat(self):
        import items as ITEMS
        for species, relic, expected in (('아마루스', 'hp', 'save_mod'), ('두개도스', 'atk', 'crit_range'), ('방패톱스', 'def', None),
                                         ('릴링', 'spd', 'damage_reduction'), ('프테라', 'spe', None)):
            with self.subTest(relic=relic):
                self.setUp()
                k = self.restored(species, species)
                wrong = next(stat for stat in ('hp', 'atk', 'def', 'spa', 'spd', 'spe') if stat != relic)
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic=wrong, minutes=10), 'among the highest nature-adjusted base stats')
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='spa' if relic != 'spa' else 'hp', minutes=10), 'among the highest')
                record = RFS.craft_relic(self.e, self.t, k, relic=relic, minutes=10)
                self.assertEqual((record['selected_stat'], record['feature'], self.t.spec['items'][record['id']]), (relic, RF.PREHISTORIC_BOND, 1))
                self.assertTrue(record['id'].startswith(RFS.DEFINITIONS[RFS.BOND]['relics'][relic]['prefix']))
                self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic=relic, minutes=10), 'already produced a relic')
                RF.equip_relic(self.e, self.t, k, record['id'])
                self.assertEqual((k.item, self.t.spec['items'][record['id']]), (record['id'], 0))
                kinds = [m.get('type') for m in k.modifiers if m.get('_item') == record['id']]
                if relic == 'hp':
                    self.assertEqual(k.save_mod, 2)
                elif expected is not None:
                    self.assertIn(expected, kinds)
                if relic == 'spe':
                    self.assertEqual(RFS.evasion_bonus(self.e, k, self.rules.move('move/꼬리흔들기')), 2)
                    self.assertEqual(RFS.evasion_bonus(self.e, k, self.rules.move('move/전광석화')), 0)
                self.restore('t')
                k = WORLD.actor_index(self.e)[k.entity_id]
                self.assertEqual(ITEMS.register_item(self.e, k, record['id']), 0)
                self.valid()

    def dual_relic(self, species, stat, name):
        import items as ITEMS
        holder = self.restored(species, name)
        record = RFS.craft_relic(self.e, self.t, holder, relic=stat, minutes=10)
        self.e.gm.set_ability(holder, '배달부', reason='actual two-held capability')
        RF.equip_relic(self.e, self.t, holder, record['id'])
        WORLD.register_object(self.e, 'relic-companion', location={'kind': 'unknown'},
                              reason='actual second held item', kind='item_instance',
                              item_rule_id='item/선제공격손톱', owner_id=holder.entity_id)
        ITEMS.equip_held(self.e, holder, '선제공격손톱', source_instance_id='relic-companion')
        return holder, record['id']

    def test_dual_held_sash_requires_live_registration_and_preserves_suppression_after_restore(self):
        import held_equipment as HELD, items as ITEMS, field_effects as FIELD
        holder, identity = self.dual_relic('프테라', 'spe', 'actual sash holder')
        status = self.rules.move('move/꼬리흔들기');held = deepcopy(HELD.entries(holder))
        self.assertEqual(len(held), 2);self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 2)
        self.assertEqual(RFS.evasion_bonus(self.e, holder, self.rules.move('move/몸통박치기')), 0)
        # A bare sheet name cannot substitute for an actual equipped registration.
        with patch.dict(holder.spec, {'held_equipment': [{'slot_id': 'held:1', 'name': identity,
                        'instance_id': None, 'registration_key': None, 'identity_evidence': 'legacy_slot'}], 'item': identity}):
            self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 0)
        FIELD.install(self.e, self.t, self.rules.move_mech('move/매직룸')[0]['effects_exec'][0], 'move/매직룸')
        self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 0)
        uid = holder.entity_id;self.restore('t');holder = WORLD.actor_index(self.e)[uid]
        self.assertEqual(HELD.entries(holder), held);self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 0)
        FIELD.clear(self.e);self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 2)
        ITEMS.unregister_item(self.e, holder, registration_key=identity)
        self.assertEqual(RFS.evasion_bonus(self.e, holder, status), 0)
        self.assertEqual([row['instance_id'] for row in HELD.entries(holder)], ['relic-companion']);self.valid()

    def test_dual_held_razors_react_once_to_native_melee_hit_and_stop_while_suppressed(self):
        from grid import Grid
        from native_scenario_fixture import prepare_body
        from engine import Engine
        import held_equipment as HELD, field_effects as FIELD
        holder, identity = self.dual_relic('방패톱스', 'def', 'actual razors holder')
        self.e.grid = Grid(8, 8)
        self.e.gm.add_combatant(holder, pos=(1, 0), side='foes', reason='actual opposing held-item recipient')
        if not holder.on_field:self.e.gm.send_out(holder, pos=(1, 0), reason='actual native field entry')
        for actor in (self.t, holder):prepare_body(self.e, actor, size=actor.spec.get('size', '중형'), offsets=[(0, 0)], reason='actual attack bodies')
        self.e.gm.set_move(self.t, 'move/몸통박치기', reason='actual learned melee attack')
        RFS.set_razors_reaction(self.e, holder, True);held = deepcopy(HELD.entries(holder))
        for suppressed in (False, True, False):
            with self.subTest(suppressed=suppressed):
                if self.e.encounter_active:self.e.end_of_turn(self.t);self.e.end_round()
                if holder.fainted:self.e.gm.revive(holder, hp=holder.base_max_hp, reason='actual recipient restored for next attack')
                else:self.e.gm.set_hp(holder, value=holder.base_max_hp, reason='actual recipient healed for next attack')
                if suppressed:FIELD.install(self.e, self.t, self.rules.move_mech('move/매직룸')[0]['effects_exec'][0], 'move/매직룸')
                else:FIELD.clear(self.e)
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t, initiative_count=20)
                before = self.t.hp;count = len(holder.spec.get('researcher_relic_reactions', []));tick = self.e.tick_loss(self.t)
                with patch.object(Engine, 'd20', return_value=15):dealt = self.e.use_move(self.t, holder, 'move/몸통박치기', set_damage=True)
                self.assertGreater(dealt, 0);self.assertEqual(self.t.hp, before - (0 if suppressed else tick))
                rows = holder.spec.get('researcher_relic_reactions', [])
                self.assertEqual(len(rows), count + int(not suppressed));self.assertEqual(HELD.entries(holder), held)
                if not suppressed:self.assertEqual(rows[-1]['relic'], identity)
        uid = holder.entity_id;self.restore('t');holder = WORLD.actor_index(self.e)[uid]
        self.assertEqual(len(holder.spec['researcher_relic_reactions']), 2);self.assertEqual(HELD.entries(holder), held)

    def test_native_razors_require_observed_opposing_sides_without_cancelling_the_attack(self):
        from grid import Grid
        from native_scenario_fixture import prepare_body
        from engine import Engine
        import held_equipment as HELD
        holder, identity = self.dual_relic('방패톱스', 'def', 'razors side boundary')
        self.e.grid = Grid(8, 8)
        self.e.gm.add_combatant(holder, pos=(1, 0), side='foes', reason='actual opposing held-item recipient')
        if not holder.on_field:self.e.gm.send_out(holder, pos=(1, 0), reason='actual native field entry')
        for actor in (self.t, holder):prepare_body(self.e, actor, size=actor.spec.get('size', '중형'), offsets=[(0, 0)], reason='actual attack bodies')
        self.e.gm.set_move(self.t, 'move/몸통박치기', reason='actual learned melee attack')
        RFS.set_razors_reaction(self.e, holder, True)
        absent = object()
        cases = (('same', 'party', 'party', False), ('absent-both', absent, absent, False),
                 ('absent-attacker', absent, 'foes', False), ('absent-holder', 'party', absent, False),
                 ('none-both', None, None, False), ('none-attacker', None, 'foes', False),
                 ('none-holder', 'party', None, False), ('opposed', 'party', 'foes', True))
        for label, attacker_side, holder_side, reacts in cases:
            with self.subTest(sides=label):
                for actor, side in ((self.t, 'party'), (holder, 'foes')):
                    actor.side = side;actor.spec['side'] = side
                if self.e.encounter_active:self.e.end_of_turn(self.t);self.e.end_round()
                if holder.fainted:self.e.gm.revive(holder, hp=holder.base_max_hp, reason='actual recipient restored for next attack')
                else:self.e.gm.set_hp(holder, value=holder.base_max_hp, reason='actual recipient healed for next attack')
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t, initiative_count=20)
                for actor, side in ((self.t, attacker_side), (holder, holder_side)):
                    if side is absent:del actor.side;actor.spec.pop('side', None)
                    else:actor.side = side;actor.spec['side'] = side
                before_hp = self.t.hp;count = len(holder.spec.get('researcher_relic_reactions', []))
                before_equipment = deepcopy((HELD.entries(holder), holder._item_reg, holder.spec['researcher_razors_reaction']))
                uses = self.t.move_uses.get('move/몸통박치기', 0);tick = self.e.tick_loss(self.t)
                with patch.object(Engine, 'd20', return_value=15):dealt = self.e.use_move(self.t, holder, 'move/몸통박치기', set_damage=True)
                self.assertGreater(dealt, 0);self.assertEqual(self.t.hp, before_hp - (tick if reacts else 0))
                self.assertEqual(self.t.move_uses['move/몸통박치기'], uses + 1);self.assertEqual(self.t.budget['standard'], 0)
                rows = holder.spec.get('researcher_relic_reactions', [])
                self.assertEqual(len(rows), count + int(reacts))
                self.assertEqual((HELD.entries(holder), holder._item_reg, holder.spec['researcher_razors_reaction']), before_equipment)
                for actor, side in ((self.t, attacker_side), (holder, holder_side)):
                    self.assertEqual(hasattr(actor, 'side'), side is not absent)
                    if side is not absent:self.assertEqual(actor.side, side)
                if reacts:self.assertEqual(rows[-1]['relic'], identity)
        self.valid()

    def test_two_distinct_active_sashes_do_not_choose_an_arbitrary_effect_source(self):
        import items as ITEMS, held_equipment as HELD
        holder, first = self.dual_relic('프테라', 'spe', 'first sash source')
        ITEMS.drop_item(self.e, holder, selection='relic-companion')
        donor = self.restored('프테라', 'second sash source')
        second = RFS.craft_relic(self.e, self.t, donor, relic='spe', minutes=10)['id']
        RF.equip_relic(self.e, self.t, donor, second)
        ITEMS.transfer_equipment(self.e, donor, holder, 'legacy:' + second)
        before = deepcopy((HELD.entries(holder), holder._item_reg, self.e.rng.getstate()))
        self.assertEqual({row['name'] for row in HELD.entries(holder)}, {first, second})
        with self.assertRaisesRegex(ValueError, 'multiple active relic effect sources'):
            RFS.evasion_bonus(self.e, holder, self.rules.move('move/꼬리흔들기'))
        self.assertEqual((HELD.entries(holder), holder._item_reg, self.e.rng.getstate()), before)
        self.valid()

    def test_relics_require_the_restorer_the_expert_rank_and_the_field_and_stay_bound_to_the_individual(self):
        k = self.restored('아마루스', 'crown')
        self.t.spec['skills']['포켓몬학'] = 4
        self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='hp', minutes=10), 'Prehistoric Bond requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        self.rejected(lambda: RFS.craft_relic(self.e, self.t, k, relic='xyz', minutes=10), 'relic stat required')
        record = RFS.craft_relic(self.e, self.t, k, relic='hp', minutes=10)
        other = self.pokemon('아마루스', 10, 'other', pos=(4, 0))
        self.rejected(lambda: RF.equip_relic(self.e, self.t, other, record['id']), 'actual Pokemon revived from a fossil')
        self.assertEqual(RFS.relic_definition(record['id'])[0], 'hp')
        self.assertIsNone(RFS.relic_definition('item/기합의띠'))

    # ------------------------------------------------------------ Pokemon Caretaking
    def test_pusher_funds_the_listed_poke_edges_so_the_pokemon_pays_no_tutor_points(self):
        q = self.pokemon('파이리', 20, 'free', moves=[], abilities=[], tutor_points=0)
        self.t.spec['skills']['포켓몬학'] = 2
        self.rejected(lambda: self.e.pokemon_activity(self.t, 'teach_edge', target=q, edge='기본 원거리 공격', capability='불쏘시개', safe=True), 'Pusher requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 3
        elapsed = self.e.elapsed_seconds
        out = self.e.pokemon_activity(self.t, 'teach_edge', target=q, edge='기본 원거리 공격', capability='불쏘시개', safe=True)
        receipt = q.spec['learned_poke_edges'][-1]
        self.assertEqual((out['pusher_net_point_cost'], q.spec['tutor_points'], receipt['point_cost'], receipt['pusher']['net_point_cost'], receipt['pusher']['feature'], self.e.elapsed_seconds - elapsed),
                         (0, 0, 1, 0, RFS.PUSHER, 0))
        other = self.pokemon('꼬부기', 20, 'paying', pos=(2, 0), moves=[], abilities=[], tutor_points=3)
        self.e.pokemon_activity(self.t, 'teach_edge', target=other, edge='재능 훈련', capability='power', safe=True)
        self.assertEqual(other.spec['tutor_points'], 2)   # an unlisted Poke Edge still costs its point
        stranger = self.trainer('stranger', (5, 5))
        self.rejected(lambda: self.e.pokemon_activity(stranger, 'teach_edge', target=other, edge='기본 원거리 공격', capability='물줄기', safe=True), 'belongs to a different trainer')
        self.valid()
        self.restore('t')

    def test_this_ones_special_marks_one_hatching_egg_once_per_pokemon_education_rank_above_untrained_and_the_child_carries_it(self):
        egg = self.fossil('프테라', 'first')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, 'egg/missing', quality='x', reason='r'), 'actual unhatched egg')
        self.t.spec['skills']['포켓몬학'] = 3
        self.assertEqual(RFS.special_uses(self.e, self.t), 1)
        out = RFS.special_quality(self.e, self.t, egg['entity_id'], quality='GM: it hums in its sleep', reason='GM decision')
        self.assertEqual(out['quality'], 'GM: it hums in its sleep')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, egg['entity_id'], quality='again', reason='r'), 'once per Pokemon Education rank')
        second = self.fossil('아마루스', 'second')
        self.rejected(lambda: RFS.special_quality(self.e, self.t, second['entity_id'], quality='x', reason='r'), 'once per Pokemon Education rank')
        self.t.spec['skills']['포켓몬학'] = 4
        RFS.special_quality(self.e, self.t, second['entity_id'], quality='GM: unusual colouring pattern', reason='GM decision')
        self.restore('t')
        child = self.hatch(next(row for row in self.t.spec['eggs'] if row['id'] == 'fossil/first'), 'child')
        self.assertEqual(child.spec['special_quality']['quality'], 'GM: it hums in its sleep')
        self.assertEqual(len(self.t.spec[RFS.KEY]['special_quality']), 2)
        self.valid()

    def test_rebalancing_adds_the_chosen_base_bonus_then_redistributes_points_for_two_tutor_points_once_per_pokemon(self):
        q = self.pokemon('근육몬', 20, 'target', moves=[], abilities=[], tutor_points=6)
        investment = GROWTH.project_actor(self.e, q)['permanent']['investment']
        legal = {'hp': 5, 'atk': 8, 'def': 7, 'spa': 4, 'spd': 4, 'spe': 2}
        self.assertEqual(sum(legal.values()), sum(investment.values()))
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk'], investment=legal, seconds=3600, reason='x', request_id='r1'), 'exactly 2 distinct base stats')
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=investment, seconds=3600, reason='x', request_id='r1'), 'violates base relations')
        self.t.spec['skills']['포켓몬학'] = 5
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=legal, seconds=3600, reason='x', request_id='r1'), 'Re-Balancing requires its printed skill rank')
        self.t.spec['skills']['포켓몬학'] = 6
        before = dict(q.spec['stats'])
        out = RFS.rebalance(self.e, self.t, q, option='two_plus_two', stats=['atk', 'def'], investment=legal, seconds=3600, reason='actual rebalancing', request_id='r1')
        self.assertEqual((out['deltas'], q.spec['tutor_points']), ({'atk': 2, 'def': 2}, 4))
        self.assertEqual(q.spec['stats'], {'hp': 13, 'atk': 20, 'def': 16, 'spa': 9, 'spd': 10, 'spe': 7})
        self.assertNotEqual(q.spec['stats'], before)
        self.assertEqual(GROWTH.project_actor(self.e, q)['permanent']['stats'], q.spec['stats'])
        self.rejected(lambda: RFS.rebalance(self.e, self.t, q, option='all_plus_one', stats=None, investment=legal, seconds=3600, reason='x', request_id='r2'), 'only once')
        other = self.pokemon('근육몬', 20, 'one', pos=(3, 0), moves=[], abilities=[], tutor_points=6)
        self.restore('t')
        q, other = (WORLD.actor_index(self.e)[x.entity_id] for x in (q, other))
        self.assertEqual(GROWTH.project_actor(self.e, q)['permanent']['stats'], {'hp': 13, 'atk': 20, 'def': 16, 'spa': 9, 'spd': 10, 'spe': 7})
        out = RFS.rebalance(self.e, self.t, other, option='one_plus_three', stats=['atk'], investment={'hp': 6, 'atk': 10, 'def': 5, 'spa': 3, 'spd': 4, 'spe': 2}, seconds=3600, reason='one stat', request_id='r3')
        self.assertEqual((out['deltas'], other.spec['stats']['atk']), ({'atk': 3}, 10 + 3 + 10))
        self.valid()


if __name__ == '__main__':
    unittest.main()
