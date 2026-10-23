"""Actual Engine current-state graph codec and adversarial input regressions.

These tests certify persistence boundaries, not category-6 creation legality.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from engine import Rules, Engine, Combatant
from grid import Grid
from state_codec import dump_engine, load_engine, import_legacy_encounter, StateCodecError


class StateCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')
        e, a, b = cls.fixture()
        cls.base = dump_engine(e)

    @classmethod
    def fixture(cls):
        r = cls.rules
        e = Engine(r, seed=712)
        spec = copy.deepcopy(r.creatures['pokemon/archie'])
        a = Combatant(r, dict(spec, id='pokemon/codec-a'))
        b = Combatant(r, dict(copy.deepcopy(spec), id='pokemon/codec-b', name=spec['name']))
        e.everyone = e.gm.everyone = [a, b]
        return e, a, b

    def roundtrip(self, e):
        return load_engine(self.rules, json.loads(json.dumps(dump_engine(e), ensure_ascii=False)))

    def test_capability_policy_cache_preserves_cold_save_and_rejects_actual_override(self):
        import capability_actions as LOAD
        r = Rules(str(ROOT), ruleset='core')
        e = Engine(r, seed=712)
        a = Combatant(r, dict(copy.deepcopy(r.creatures['pokemon/archie']), id='pokemon/codec-cache'))
        e.everyone = e.gm.everyone = [a];e.grid = Grid(8, 8);a.pos = (2, 2)
        self.assertFalse(hasattr(r, 'capability_policy'))
        saved = dump_engine(e)
        LOAD.policy(a)
        self.assertEqual(saved, dump_engine(e))
        restored = load_engine(r, json.loads(json.dumps(saved, ensure_ascii=False)))
        self.assertEqual(saved['rules'], dump_engine(restored)['rules'])
        self.assertEqual((a.entity_id, a.pos), (restored.everyone[0].entity_id, restored.everyone[0].pos))
        r.capability_policy['weight_limits_kg']['1']['staggering'] += 1
        with self.assertRaisesRegex(StateCodecError, 'fingerprint mismatch'):
            load_engine(r, saved)

    def test_selected_rule_fingerprint_keeps_nested_order_independent_and_rejects_bad_keys(self):
        from state_codec import _plain
        from resolution_transaction import json_fingerprint
        first = {'z': {'last': 2, 'first': 1}, 'a': [{'y': 4, 'x': 3}]}
        reordered = {'a': [{'x': 3, 'y': 4}], 'z': {'first': 1, 'last': 2}}
        self.assertEqual(json_fingerprint(_plain(first), allow_nan=False),
                         json_fingerprint(_plain(reordered), allow_nan=False))
        self.assertNotEqual(json_fingerprint(_plain(first), allow_nan=False),
                            json_fingerprint(_plain({'z': {'last': 9, 'first': 1}, 'a': first['a']}), allow_nan=False))
        with self.assertRaisesRegex(StateCodecError, 'text keys'):
            _plain({'nested': {1: 'not a policy key'}})

    def test_selected_rule_normalization_preserves_input_and_rechecks_changed_nested_values(self):
        from state_codec import _plain
        from resolution_transaction import json_fingerprint
        shared = {'values': [None, True, 2, 3.5, 'text']}
        value = {'plain': shared, 'alias': shared, 'converted': [(shared, {3, 1}), frozenset({2, 4})]}
        before = copy.deepcopy(value)
        expected = {'plain': shared, 'alias': shared,
                    'converted': [[shared, {'set': [1, 3]}], {'set': [2, 4]}]}
        first = json_fingerprint(_plain(value), allow_nan=False)
        self.assertEqual(first, json_fingerprint(expected, allow_nan=False))
        self.assertEqual(value, before)
        self.assertIs(value['plain'], value['alias'])
        shared['values'].append('changed')
        self.assertNotEqual(json_fingerprint(_plain(value), allow_nan=False), first)
        for invalid, reason in (
            ({'bad': float('nan')}, 'nonfinite'),
            ([{'bad': float('inf')}], 'nonfinite'),
            ((float('-inf'),), 'nonfinite'),
            ({'bad': {False: 1}}, 'text keys'),
            ({'bad': {1: 'value'}}, 'text keys'),
            ({'bad': object()}, 'unsupported'),
        ):
            with self.subTest(reason=reason, invalid=invalid), self.assertRaisesRegex(StateCodecError, reason):
                _plain(invalid)
        class Text(str): pass
        class Number(int): pass
        class Mapping(dict): pass
        class Sequence(list): pass
        for invalid in (Text('text'), Number(2), Mapping(a=1), Sequence([1])):
            with self.subTest(kind=type(invalid).__name__), self.assertRaisesRegex(StateCodecError, 'unsupported'):
                _plain({'nested': [invalid]})

    def node(self, p, kind, index=0):
        return [v for v in p['nodes'].values() if v['kind'] == kind][index]

    def attrs(self, p, kind, index=0):
        return p['nodes'][self.node(p, kind, index)['attrs']['$ref']]['items']

    def replace(self, p, kind, field, value, index=0):
        items = self.attrs(p, kind, index)
        for pair in items:
            if pair[0] == field:
                pair[1] = value
                return
        items.append([field, value])

    def test_native_objects_new_rules_wrapper_and_roster_alias(self):
        before = self.rules.rulings
        n = load_engine(self.rules, copy.deepcopy(self.base))
        self.assertIsNot(n.r, self.rules)
        self.assertIs(self.rules.rulings, before)
        self.assertIs(n.r.rulings, n.rulings)
        self.assertIs(n.gm.e, n)
        self.assertIs(n.everyone, n.gm.everyone)
        self.assertIs(n.everyone[0].r, n.r)
        self.assertNotEqual(n.everyone[0].spec['id'], n.everyone[1].spec['id'])
        self.assertEqual(n.everyone[0].name, n.everyone[1].name)

    def test_hp_condition_raw_dynamic_and_typed_keys(self):
        e, a, b = self.fixture()
        a.hp = 7; a.temp_hp = 3; a.injuries = 2; a.conditions.add('독')
        a._custom_gameplay_data = {1: 'integer', '1': 'text', (2, 3): {'set'}, 'frozen': frozenset((1, 2))}
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertEqual((c.hp, c.temp_hp, c.injuries, c.conditions), (7, 3, 2, {'독'}))
        self.assertEqual(c._custom_gameplay_data, a._custom_gameplay_data)
        self.assertIs(type(c._custom_gameplay_data['frozen']), frozenset)

    def test_optional_observed_terrain_and_required_grid_fields(self):
        e, a, b = self.fixture(); e.grid = Grid(4, 3)
        e.grid.terrain_types = {'1,2': ['forest']}
        e.grid.terrain_observations = {'1,2': {'reason': 'actual GM observation', 'source': 'test'}}
        p = dump_engine(e); n = load_engine(self.rules, p)
        self.assertEqual(n.grid.terrain_types, {'1,2': ['forest']})
        self.assertEqual(n.grid.terrain_observations, e.grid.terrain_observations)
        self.assertNotIn('0,0', n.grid.terrain_types)
        bad = copy.deepcopy(p); self.replace(bad, 'grid', 'terrain_types', None)
        with self.assertRaises(StateCodecError): load_engine(self.rules, bad)
        bad = copy.deepcopy(p); fields = self.attrs(bad, 'grid')
        fields[:] = [row for row in fields if row[0] != 'walls']
        with self.assertRaises(StateCodecError): load_engine(self.rules, bad)

    def test_cross_actor_cycles_and_mutable_aliases(self):
        e, a, b = self.fixture()
        shared = {'counter': [2]}
        a.custom_conditions['other'] = b; b.custom_conditions['other'] = a
        a.custom_conditions['shared'] = shared; e.field = {'shared': shared}
        a.custom_conditions['backing'] = a.__dict__
        n = self.roundtrip(e); c, d = n.everyone
        self.assertIs(c.custom_conditions['other'], d)
        self.assertIs(d.custom_conditions['other'], c)
        self.assertIs(c.custom_conditions['shared'], n.field['shared'])
        self.assertIs(c.custom_conditions['backing'], vars(c))
        n.field['shared']['counter'].append(3)
        self.assertEqual(c.custom_conditions['shared']['counter'], [2, 3])
        self.assertEqual(shared['counter'], [2])

    def test_tuple_list_cycle_and_actor_dict_keys(self):
        e, a, b = self.fixture()
        items = []; pair = (items, a); items.append(pair)
        a.custom_conditions['cycle'] = pair
        e._passive_listeners = {a: {'selected': b}}
        n = self.roundtrip(e); c, d = n.everyone
        saved = c.custom_conditions['cycle']
        self.assertIs(saved[0][0], saved)
        self.assertIs(saved[1], c)
        self.assertIs(n._passive_listeners[c]['selected'], d)

    def test_off_roster_delayed_actor_identity_and_native_execution(self):
        e, a, b = self.fixture(); b.hp = 1
        e.everyone = e.gm.everyone = [a]
        e.delayed = [dict(kind='heal', who=b, attacker=a, turns=1, effect={'fraction_of_max': [1, 2]}, src='test', healing_source_kind='move')]
        n = self.roundtrip(e); restored = n.delayed[0]['who']
        self.assertIsNot(restored, b)
        self.assertIs(n.delayed[0]['attacker'], n.everyone[0])
        n.end_of_turn(restored)
        self.assertEqual(restored.hp, 1 + restored.max_hp // 2)
        self.assertEqual(n.delayed, [])

    def test_item_modifier_alias_preserved(self):
        e, a, b = self.fixture()
        import world_entities as WORLD
        import items as ITEMS
        WORLD.register_object(e, 'codec-alias-item', location={'kind': 'unknown'},
            reason='codec alias fixture', kind='item_instance',
            item_rule_id='item/달인의띠', owner_id=a.entity_id)
        ITEMS.register_item(e, a, '달인의띠', source_instance_id='codec-alias-item')
        mod = {'value': 3}; a.modifiers.append(mod)
        a._item_reg['달인의띠']['mods'] = [mod]
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertIs(c.modifiers[-1], c._item_reg['달인의띠']['mods'][0])

    def test_rng_exact_continuation_and_repeated_load_independence(self):
        e, a, b = self.fixture()
        e.rng.random(); e.rng.gauss(0, 1)
        p = dump_engine(e)
        expected = [e.d20() for _ in range(12)]
        first, second = load_engine(self.rules, p), load_engine(self.rules, p)
        self.assertEqual([first.d20() for _ in range(12)], expected)
        self.assertEqual([second.d20() for _ in range(12)], expected)
        first.everyone[0].hp = 2
        self.assertNotEqual(first.everyone[0].hp, second.everyone[0].hp)
        self.assertEqual(p, json.loads(json.dumps(p)))

    def test_grid_dimensions_sets_walls_and_unknown_location_raw(self):
        e, a, b = self.fixture()
        e.grid = Grid(23, 19, blocking={(7, 8)}, walls=[((1, 2), (2, 2))])
        a.__dict__['location'] = {'kind': 'unknown', 'reason': 'not observed'}
        n = self.roundtrip(e)
        self.assertEqual((n.grid.w, n.grid.h), (23, 19))
        self.assertEqual(n.grid.walls, {((1, 2), (2, 2))})
        self.assertEqual(n.grid.blocking, {(7, 8)})
        self.assertEqual(n.everyone[0].__dict__['location'], a.__dict__['location'])

    def test_world_records_and_receipt_aliases(self):
        e, a, b = self.fixture()
        e._world_facts = {'f1': {'kind': 'world', 'owner_id': a.spec['id']}}
        e._world_relation_receipts = {'req': {'fact': e._world_facts['f1'], 'applied': True}}
        n = self.roundtrip(e)
        self.assertIs(n._world_facts['f1'], n._world_relation_receipts['req']['fact'])

    def test_base_types_and_effective_types_remain_separate(self):
        e, a, b = self.fixture()
        a._types = ['물']; original = list(a.spec['types'])
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertEqual(c._types, ['물']); self.assertEqual(c.spec['types'], original)

    def test_ruling_state_recovered_without_mutating_supplied_rules(self):
        e, a, b = self.fixture()
        original = copy.deepcopy(vars(self.rules.rulings))
        try:
            e.rule_formula('tick', 'max_hp / 8', 'codec test')
            p = dump_engine(e)
        finally:
            vars(self.rules.rulings).clear(); vars(self.rules.rulings).update(original)
        n = load_engine(self.rules, p)
        self.assertEqual(n.rulings.formulas['tick']['expr'], 'max_hp / 8')
        self.assertEqual(vars(self.rules.rulings), original)
        self.assertIs(n.rulings, n.r.rulings)

    def test_authentication_epoch_advance_receipts_remain_and_history_scope_explicit(self):
        e, a, b = self.fixture()
        e._root_common_epoch = 9; e._root_common_receipts = [{'event': 'done', 'status': 'complete'}]
        e.gm.snapshot('before')
        p = dump_engine(e)
        self.assertEqual(p['save_scope']['omitted_checkpoint_count'], 1)
        self.assertFalse(p['save_scope']['gm_checkpoint_history'])
        n = load_engine(self.rules, p)
        self.assertEqual(n._root_common_epoch, 10)
        self.assertIn('reauthentication_required', n._state_codec_authentication)
        self.assertEqual(n._root_common_receipts, e._root_common_receipts)
        self.assertEqual(n.gm.snapshots, {})

    def test_roundtrip_is_a_new_session_even_for_identical_saved_state(self):
        n = load_engine(self.rules, self.base)
        n2 = load_engine(self.rules, dump_engine(n))
        self.assertEqual(n2._root_common_epoch, n._root_common_epoch + 1)
        self.assertIsNot(n2.everyone[0], n.everyone[0])

    def test_callbacks_and_live_authenticated_binding_rejected(self):
        e, a, b = self.fixture()
        a.custom_conditions['callback'] = lambda: None
        with self.assertRaisesRegex(StateCodecError, 'unsupported gameplay object'):
            dump_engine(e)
        del a.custom_conditions['callback']
        e._root_common_binding = object()
        with self.assertRaisesRegex(StateCodecError, 'fixed native common-check binding'):
            dump_engine(e)

    def test_unknown_engine_attribute_rejected(self):
        e, a, b = self.fixture(); e.unregistered_gameplay_state = {'must_not_disappear': True}
        with self.assertRaisesRegex(StateCodecError, 'unsupported fields'):
            dump_engine(e)

    def test_duplicate_entity_ids_rejected(self):
        e, a, b = self.fixture(); b.spec['id'] = a.spec['id']; b.__dict__['_entity_id'] = a.spec['id']
        with self.assertRaisesRegex(StateCodecError, 'duplicate actor identity'):
            dump_engine(e)

    def test_profile_and_in_memory_rule_policy_mismatch_rejected(self):
        p = copy.deepcopy(self.base); p['rules']['profile'] = 'all'
        with self.assertRaisesRegex(StateCodecError, 'fingerprint mismatch'):
            load_engine(self.rules, p)
        changed = copy.copy(self.rules); changed.skill_policy = dict(self.rules.skill_policy, codec_test_changed=True)
        with self.assertRaisesRegex(StateCodecError, 'fingerprint mismatch'):
            load_engine(changed, self.base)

    def test_source_corpus_mismatch_rejected(self):
        changed = copy.copy(self.rules)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ('input', 'data', 'output/entities'):
                (root / folder).mkdir(parents=True)
            (root / 'input' / 'changed.md').write_text('different source', encoding='utf-8')
            changed.root = str(root)
            with self.assertRaisesRegex(StateCodecError, 'fingerprint mismatch'):
                load_engine(changed, self.base)

    def test_rule_corpus_walk_keeps_order_exclusions_and_live_additions(self):
        from state_codec import _corpus_paths
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for folder in ('input/sub', 'input/verification', 'data/verification', 'output/entities'):
                (root / folder).mkdir(parents=True)
            for name in ('input/a.md', 'input/sub/b.csv', 'input/verification/ignored.md',
                         'data/a.json', 'data/ignored.txt', 'data/verification/ignored.json',
                         'output/entities/a.json'):
                (root / name).write_text(name, encoding='utf-8')
            names = lambda: [path.relative_to(root).as_posix() for path in _corpus_paths(root)]
            self.assertEqual(names(), ['input/a.md', 'input/sub/b.csv', 'data/a.json',
                                       'output/entities/a.json'])
            (root / 'input/z.md').write_text('new rule source', encoding='utf-8')
            self.assertEqual(names(), ['input/a.md', 'input/sub/b.csv', 'input/z.md',
                                       'data/a.json', 'output/entities/a.json'])

    def test_unsupported_version_and_arbitrary_class_tag_rejected(self):
        p = copy.deepcopy(self.base); p['version'] = True
        with self.assertRaises(StateCodecError): load_engine(self.rules, p)
        p = copy.deepcopy(self.base); self.node(p, 'actor')['kind'] = 'subprocess.Popen'
        with self.assertRaisesRegex(StateCodecError, 'unknown graph tag'):
            load_engine(self.rules, p)

    def test_dangling_reference_duplicate_key_and_orphan_node_rejected(self):
        p = copy.deepcopy(self.base); self.replace(p, 'engine', 'everyone', {'$ref': 'n999999'})
        with self.assertRaisesRegex(StateCodecError, 'dangling reference'):
            load_engine(self.rules, p)
        p = copy.deepcopy(self.base); self.attrs(p, 'engine').append(copy.deepcopy(self.attrs(p, 'engine')[0]))
        with self.assertRaisesRegex(StateCodecError, 'duplicate decoded dictionary key'):
            load_engine(self.rules, p)
        p = copy.deepcopy(self.base); p['nodes']['n999999'] = {'kind': 'list', 'items': []}
        with self.assertRaisesRegex(StateCodecError, 'unreachable graph'):
            load_engine(self.rules, p)

    def test_malformed_actor_identity_and_base_state_rejected_atomically(self):
        before = copy.deepcopy(vars(self.rules.rulings))
        p = copy.deepcopy(self.base); self.node(p, 'actor')['entity_id'] = 'other'
        with self.assertRaisesRegex(StateCodecError, 'identity'):
            load_engine(self.rules, p)
        self.assertEqual(vars(self.rules.rulings), before)
        p = copy.deepcopy(self.base)
        spec_ref = next(v for k, v in self.attrs(p, 'actor') if k == 'spec')
        spec = p['nodes'][spec_ref['$ref']]['items']
        next(pair for pair in spec if pair[0] == 'level')[1] = -3
        with self.assertRaisesRegex(StateCodecError, 'invalid actor base'):
            load_engine(self.rules, p)

    def test_nonfinite_and_immutable_reference_cycle_rejected(self):
        e, a, b = self.fixture(); a.custom_conditions['infinite'] = float('inf')
        with self.assertRaisesRegex(StateCodecError, 'nonfinite'):
            dump_engine(e)
        p = copy.deepcopy(self.base)
        p['nodes']['n999999'] = {'kind': 'tuple', 'items': [{'$ref': 'n999999'}]}
        self.replace(p, 'actor', '_cyclic', {'$ref': 'n999999'})
        with self.assertRaisesRegex(StateCodecError, 'immutable-only'):
            load_engine(self.rules, p)

    def test_invalid_rng_and_unauthorized_engine_field_rejected(self):
        p = copy.deepcopy(self.base); self.node(p, 'random')['state'] = 'bad'
        with self.assertRaisesRegex(StateCodecError, 'RNG state'):
            load_engine(self.rules, p)
        p = copy.deepcopy(self.base); self.attrs(p, 'engine').append(['run_code', 'import os'])
        with self.assertRaisesRegex(StateCodecError, 'unsupported fields'):
            load_engine(self.rules, p)

    def test_legacy_scenario_import_records_provenance_without_creation_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'scenario.json'
            path.write_text(json.dumps({'name': 'legacy', 'party': [], 'wild': [], 'grid': {'w': 8, 'h': 7}}), encoding='utf-8')
            e = import_legacy_encounter(str(ROOT), path, reason='GM import of original scenario', ruleset='core')
            self.assertFalse(e.state_import_provenance['creation_legality_certified'])
            self.assertFalse(e.state_import_provenance['previous_runtime_state_recovered'])
            self.assertEqual(e.state_import_provenance['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            n = self.roundtrip(e)
            self.assertEqual(n.state_import_provenance, e.state_import_provenance)


    def observed_fixture(self):
        from test_category3_contest_skill_features import Tests
        import contest_features as F
        fixture = Tests()
        fixture.r = Rules(str(ROOT))
        fixture.fixture('슬기로움', F.MISTAKES)
        fixture.e.boost_roll(fixture.t, fixture.p, roll_id='saved-observation', kind='skill')
        with self.assertRaises(ValueError):
            fixture.mistakes(dc=99, fixed=None, reroll_faces=None,
                decision=lambda check:'invalid', roll_id='saved-observation')
        return fixture

    def test_observed_first_roll_ap_and_decline_survive_fresh_engine(self):
        import action_points as AP
        import contest_features as F
        fixture = self.observed_fixture()
        e = fixture.e
        rng = e.rng.getstate()
        ap = AP.available(fixture.t)
        first = e._ap_rolls['saved-observation']['observed_resolution']['observation']['first']
        n = load_engine(fixture.r, json.loads(json.dumps(dump_engine(e))))
        trainer, pokemon, _ = n.everyone
        observed = n._ap_rolls['saved-observation']['observed_resolution']
        self.assertIs(observed['participants'][0], trainer)
        self.assertIs(observed['participants'][1], pokemon)
        out = n.contest_skill_feature(trainer, pokemon, F.MISTAKES, '육상', 99,
            fixed=None, reroll_faces=None, decision=lambda check:False, roll_id='saved-observation')
        self.assertEqual(out['first_roll'], first)
        self.assertEqual(n.rng.getstate(), rng)
        self.assertEqual(AP.available(trainer), ap)
        again = load_engine(n.r, dump_engine(n))
        with self.assertRaises(ValueError):
            again.contest_skill_feature(again.everyone[0], again.everyone[1], F.MISTAKES,
                '육상', 99, fixed=None, decision=lambda check:False, roll_id='saved-observation')

    def test_observed_accept_rolls_only_new_reroll_and_keeps_original(self):
        import contest_features as F
        fixture = self.observed_fixture()
        n = load_engine(fixture.r, dump_engine(fixture.e))
        trainer, pokemon, _ = n.everyone
        first = n._ap_rolls['saved-observation']['observed_resolution']['observation']['first']
        before = n.rng.getstate()
        out = n.contest_skill_feature(trainer, pokemon, F.MISTAKES, '육상', 99,
            fixed=None, reroll_faces=None, decision=lambda check:True, roll_id='saved-observation')
        self.assertEqual(out['first_roll'], first)
        self.assertNotEqual(n.rng.getstate(), before)
        self.assertEqual(trainer.spec['frequency_state']['activations'][F.MISTAKES]['used'], 1)



    def test_common_pending_choices_dice_response_reauthenticate_and_repeat(self):
        # Isolate canonical package imports from the legacy top-level engine.py.
        script = r"""
from pathlib import Path
import sys,copy,json
root=Path(sys.argv[1]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tools'))
import common_check_fixture as f
from engine.engine import Rules,Engine,Combatant
from state_codec import dump_engine,load_engine,reauthenticate_common_checks,StateCodecError
rules=Rules(str(root),ruleset='core')
def fixture():
    e=Engine(rules,seed=32)
    actors={k:Combatant(rules,dict(id='trainer/'+k,name=k,kind='trainer',level=1,
        stats=dict(hp=10,atk=5,**{'def':5},spa=5,spd=5,spe=5),skills={'athletics':rank}))
        for k,rank in [('a','미숙'),('b','초보'),('helper','초보')]}
    e.everyone=e.gm.everyone=list(actors.values())
    session,principals,config=f.setup()
    binding=e.open_common_checks(session.runtime.registry,session.registration,actors,config,tuple(principals.values()))
    ticket=binding.begin('event','check');assert binding.submit(ticket).tag=='AwaitingInput'
    return e,binding,ticket,principals,config
for stage in range(4):
    e,b,t,p,c=fixture()
    if stage>=1: assert b.answer(b.pending(t),p['gm'],c['requests']['check']['decisions'][0]).tag=='AwaitingInput'
    if stage>=2: assert b.answer(b.pending(t),p['a'],[4,4]).tag=='AwaitingInput'
    if stage>=3: assert b.answer(b.pending(t),p['gm'],c['requests']['check']['outcomes'][0]).tag=='Completed'
    previous=b.result('event');previous=None if previous is None else b.rm.thaw(previous)
    rng=e.rng.getstate();hp=[a.hp for a in e.everyone];receipts=copy.deepcopy(e._root_common_receipts)
    envelope=json.loads(json.dumps(dump_engine(e)))
    for repeat in range(2):
        restored=load_engine(rules,envelope)
        assert '_root_common_binding' not in vars(restored)
        assert restored._root_common_saved['ledger']['game']['domains']['common_checks']['results'].get('event')==previous
        session,newp,newc=f.setup()
        renewed=reauthenticate_common_checks(restored,session.runtime.registry,session.registration,tuple(newp.values()))
        fresh=renewed.begin('event','check')
        assert renewed.submit(t).tag.startswith('Rejected')
        if stage<1: assert renewed.answer(renewed.pending(fresh),newp['gm'],c['requests']['check']['decisions'][0]).tag=='AwaitingInput'
        if stage<2:
            pending=renewed.pending(fresh)
            assert renewed.answer(pending,p['a'],[4,4]).tag.startswith('Rejected')
            assert renewed.answer(pending,newp['a'],[4,4]).tag=='AwaitingInput'
        if stage<3: assert renewed.answer(renewed.pending(fresh),newp['gm'],c['requests']['check']['outcomes'][0]).tag=='Completed'
        assert renewed.result('event')['raw']['total']==8
        assert restored.rng.getstate()==rng and [a.hp for a in restored.everyone]==hp
        assert len(restored._root_common_receipts)==1
        completed=load_engine(rules,dump_engine(restored))
        session,other,_=f.setup()
        final=reauthenticate_common_checks(completed,session.runtime.registry,session.registration,tuple(other.values()))
        assert final.submit(final.begin('event','check')).tag=='Completed'
        assert len(completed._root_common_receipts)==1
# Corruption is rejected without installing a live binding or altering gameplay.
e,b,t,p,c=fixture();b.answer(b.pending(t),p['gm'],c['requests']['check']['decisions'][0]);b.answer(b.pending(t),p['a'],[4,4])
n=load_engine(rules,dump_engine(e));n._root_common_saved['inputs'][-1]['value']=[6,6]
session,newp,_=f.setup();before=n.rng.getstate()
try: reauthenticate_common_checks(n,session.runtime.registry,session.registration,tuple(newp.values()))
except StateCodecError: pass
else: raise AssertionError('changed public faces accepted')
assert '_root_common_binding' not in vars(n) and n.rng.getstate()==before and not n._root_common_receipts
# A completed occurrence followed by another observation retains both histories.
e,b,t,p,c=fixture()
b.answer(b.pending(t),p['gm'],c['requests']['check']['decisions'][0]);b.answer(b.pending(t),p['a'],[4,4]);b.answer(b.pending(t),p['gm'],c['requests']['check']['outcomes'][0])
t2=b.begin('second','check');assert b.submit(t2).tag=='AwaitingInput'
b.answer(b.pending(t2),p['gm'],c['requests']['check']['decisions'][0]);b.answer(b.pending(t2),p['a'],[2,2])
n=load_engine(rules,dump_engine(e));session,newp,_=f.setup()
b2=reauthenticate_common_checks(n,session.runtime.registry,session.registration,tuple(newp.values()))
assert b2.result('event')['raw']['total']==8 and b2.result('second')['raw']['total']==4
assert len(n._root_common_receipts)==1
assert b2.answer(b2.pending(b2.begin('second','check')),newp['gm'],c['requests']['check']['outcomes'][1]).tag=='Completed'
assert len(n._root_common_receipts)==2
print('common pending stages and fresh-authority rejection: pass')
"""
        out = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-W', 'ignore::ResourceWarning',
            '-c', script, str(ROOT)], capture_output=True, text=True, encoding='utf-8', timeout=120,
            env=dict(os.environ,PYTHONPATH=os.pathsep.join((str(ROOT),str(ROOT/'tools')))))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


    def test_gm_snapshot_discovers_off_roster_skill_event_and_backing_alias(self):
        from skill_feature_actions import SkillEvent
        from common_checks import SkillRoll
        e, a, b = self.fixture()
        e.everyone = e.gm.everyone = [a]
        e._ap_rolls['off-roster'] = {'skill_event':SkillEvent(b, 'athletics', (), (), SkillRoll(1, (2,)))}
        b.custom_conditions['backing'] = vars(b)
        b.hp = 3
        e.gm.snapshot('observation')
        b.hp = 9
        e.gm.restore('observation')
        self.assertEqual(b.hp, 3)
        self.assertIs(e._ap_rolls['off-roster']['skill_event'].actor, b)
        self.assertIs(b.custom_conditions['backing'], vars(b))
        n = self.roundtrip(e)
        saved = n._ap_rolls['off-roster']['skill_event'].actor
        self.assertIsNot(saved, b)
        self.assertEqual(saved.hp, 3)
        self.assertIs(saved.custom_conditions['backing'], vars(saved))

    def test_native_league_agenda_roundtrip_continues_existing_order(self):
        from test_category3_batch15_pokemon import Tests
        fixture = Tests(); fixture.r = self.rules; fixture.setUp()
        e = fixture.e
        e.start_league([('a',fixture.a,fixture.p),('b',fixture.b,fixture.q)], mode='league')
        e.league_declare('a:trainer', {'kind':'no_action'})
        n = self.roundtrip(e)
        self.assertEqual(n.league_status(), e.league_status())
        self.assertIs(n._league_runtime['actors']['a:trainer'], n.everyone[0])
        n.league_declare('b:trainer', {'kind':'no_action'})
        n.league_step(); n.league_step()
        n.league_step(pokemon_intent={'kind':'no_action'})
        n.league_step(pokemon_intent={'kind':'no_action'})
        n.league_complete_round()
        restored = self.roundtrip(n)
        self.assertEqual(restored.league_status()['status'], 'round_complete')

    def test_effect_maneuver_pending_receipt_and_suffix_resume_once(self):
        import effects as FX
        import maneuver_grants as MG
        rules = Rules(str(ROOT))
        e = Engine(rules, 5)
        def actor(name,side,pos):
            return Combatant(rules,dict(id='trainer/'+name,name=name,kind='trainer',
                side=side,pos=pos,level=50,stats=dict(hp=100,atk=20,**{'def':20},spa=20,spd=20,spe=1),
                skills={'전투':4,'육상':4,'곡예':4},movement={'land':6,'power':4},weight_kg=30,
                feats=[],moves=['move/괴력','move/돌진','move/물고버티기']))
        a,b=actor('A','party',(1,1)),actor('B','wild',(2,1))
        e.everyone=e.gm.everyone=[a,b];e.grid=Grid(8,8)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        effect = next(x for x in e.r.move_mech('move/괴력')[0]['effects_exec'] if x['type']=='free_maneuver')
        result = FX.run_effects(e,a,b,[effect,{'type':'stage_change','stat':'atk','delta':1}],
            dict(hit=True,attacker=a,target=b,engine=e),'move/괴력')
        self.assertTrue(result.pending)
        row = next(iter(a.custom_conditions['_maneuver_grants'].values()))
        n = load_engine(rules, dump_engine(e)); c,d=n.everyone
        pending = c.custom_conditions['_maneuver_grants'][row['id']]
        token = pending['receipt']
        self.assertIs(n._effect_dispatch_receipts[token]['receipt'], token)
        self.assertIsNot(token, row['receipt'])
        rng=n.rng.getstate();before=d.stages['atk']
        done=MG.resolve(n,c,row['id'],accept=False)
        self.assertFalse(done.accepted)
        self.assertEqual(d.stages['atk'],before+1)
        self.assertEqual(n.rng.getstate(),rng)
        final=load_engine(n.r,dump_engine(n));c,d=final.everyone
        self.assertFalse(MG.resolve(final,c,row['id']).accepted)
        self.assertEqual(d.stages['atk'],before+1)
        import effect_contracts as EFFECTS
        batches=[x['result'] for x in final._effect_dispatch_receipts.values() if isinstance(x.get('result'),EFFECTS.BatchResult)]
        self.assertTrue(batches)
        self.assertIs(batches[0].engine, final)



    def test_fixed_observation_enum_and_unregistered_opaque_rejections(self):
        from common_checks import SkillRoll
        from league_agenda import Phase
        e,a,b=self.fixture();a.custom_conditions['observed']=SkillRoll(2,(2,3))
        a.custom_conditions['phase']=Phase.DECLARE
        p=dump_engine(e)
        changed=copy.deepcopy(p);self.node(changed,'observation')['type']='subprocess.Popen'
        with self.assertRaisesRegex(StateCodecError,'unknown fixed observation'):
            load_engine(self.rules,changed)
        changed=copy.deepcopy(p);self.node(changed,'enum')['member']='EXECUTE'
        with self.assertRaisesRegex(StateCodecError,'unknown fixed enum'):
            load_engine(self.rules,changed)
        changed=copy.deepcopy(p);changed['nodes']['n999999']={'kind':'effect_receipt'}
        self.replace(changed,'actor','_forged_effect_receipt',{'$ref':'n999999'})
        with self.assertRaisesRegex(StateCodecError,'opaque native effect receipts'):
            load_engine(self.rules,changed)
        a.custom_conditions['opaque']=object()
        with self.assertRaisesRegex(StateCodecError,'unsupported gameplay object'):
            dump_engine(e)

    def test_saving_inside_observed_callback_is_rejected_without_losing_prefix(self):
        fixture=self.observed_fixture()
        observed=fixture.e._ap_rolls['saved-observation']['observed_resolution']
        observed['state']='deciding'
        with self.assertRaisesRegex(StateCodecError,'decision callback'):
            dump_engine(fixture.e)
        observed['state']='pending'
        restored=load_engine(fixture.r,dump_engine(fixture.e))
        self.assertEqual(restored._ap_rolls['saved-observation']['observed_resolution']['state'],'pending')





    def test_core_c01_004_abstract_unknown_and_grid_survive_native_observation(self):
        import world_entities as W
        e, a, b = self.fixture()
        W.observe_location(e, a, {'kind': 'abstract', 'place_id': 'forest/west'}, reason='abstract scene chosen')
        W.observe_location(e, b, {'kind': 'unknown'}, reason='position not observed')
        e.gm.snapshot('abstract')
        e.gm.set_position(a, (3, 4), reason='map position now known')
        self.assertEqual(W.grid_cell(a), (3, 4))
        e.gm.restore('abstract')
        n = self.roundtrip(e); c, d = n.everyone
        self.assertEqual(W.location_of(c), {'kind': 'abstract', 'place_id': 'forest/west'})
        self.assertEqual(W.location_of(d), {'kind': 'unknown'})
        self.assertIsNone(W.distance_known(c, d))
        with self.assertRaises(ValueError): W.grid_cell(c)
        with self.assertRaises(ValueError): _ = d.pos
        n.gm.set_hp(c, value=7, reason='nongeometric observed HP')
        self.assertEqual(c.hp, 7)

    def test_core_c02_023_six_stats_keep_permanent_and_effective_authority(self):
        import state_fields as S
        e, a, b = self.fixture()
        original = copy.deepcopy(a.spec['stats'])
        self.assertEqual(set(original), {'hp', 'atk', 'def', 'spa', 'spd', 'spe'})
        a.stats['atk'] += 5
        e.gm.set_stat(a, 'atk', value=original['atk'] + 2, reason='permanent allocation observed')
        before = copy.deepcopy(a.spec)
        with self.assertRaises(ValueError):
            S.base_patch(a, {'stats': {'hp': 10}}, reason='incomplete stat input')
        self.assertEqual(a.spec, before)
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertEqual(set(c.stats), set(original))
        self.assertEqual(c.spec['stats']['atk'], original['atk'] + 2)
        self.assertEqual(c.stats['atk'], original['atk'] + 7)
        self.assertEqual(c.staged('atk'), original['atk'] + 7)
        self.assertEqual(set(c.stages), set(original) - {'hp'})
        for key in set(original) - {'atk'}:
            self.assertEqual(c.spec['stats'][key], original[key])
        S.validate_actor(c)

    def test_core_c02_024_hp_stat_current_and_derived_capacity_are_distinct(self):
        e, a, b = self.fixture()
        base_hp_stat = a.spec['stats']['hp']; old_max = a.base_max_hp
        e.gm.set_hp(a, value=9, reason='current HP observed')
        self.assertEqual((a.spec['stats']['hp'], a.stats['hp']), (base_hp_stat, base_hp_stat))
        e.gm.set_stat(a, 'hp', value=base_hp_stat + 2, reason='permanent HP allocation observed')
        self.assertEqual(a.hp, 9)
        self.assertEqual(a.base_max_hp, old_max + 6)
        e.take_damage(a, 2)
        self.assertEqual(a.hp, 7)
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertEqual((c.spec['stats']['hp'], c.stats['hp']), (base_hp_stat + 2, base_hp_stat + 2))
        self.assertEqual((c.hp, c.base_max_hp), (7, old_max + 6))
        n.take_damage(c, 1)
        self.assertEqual(c.hp, 6)
        self.assertEqual(c.base_max_hp, old_max + 6)

    def test_core_move_display_name_resolves_from_persisted_rule_ids(self):
        e, a, b = self.fixture()
        self.assertTrue(a.moves)
        expected = [(mid, e.r.move(mid)['name']) for mid in a.moves]
        for mid, name in expected:
            # Native 'struggle' and catalog 'move/발버둥' are documented aliases;
            # the source requires displaying the name, not globally unique names.
            self.assertEqual(e.r.move(e.r.move_id(name))['name'], name)
            self.assertEqual(e.r.move(mid)['id'], mid)
        n = self.roundtrip(e); c = n.everyone[0]
        self.assertEqual([(mid, n.r.move(mid)['name']) for mid in c.moves], expected)
        self.assertEqual(c.moves, a.moves)


class ContestStateCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from contest import ContestRules
        cls.nr=Rules(str(ROOT),ruleset='core')
        cls.cr=ContestRules(str(ROOT),ruleset='core')

    def fixture(self,paired=False):
        from contest import ContestEngine
        import contest_features as F
        native=Engine(self.nr,seed=602)
        contest=ContestEngine(self.cr,seed=130)
        cs=[];trainers=[];pokemon=[]
        for i in range(3):
            common=dict(level=25,stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
                        moves=['연속자르기','헤롱헤롱'])
            t=Combatant(self.nr,dict(common,id='contest/t'+str(i),name='same',kind='trainer',
                skills={'명령':'전문','매력':'초보'},classes=['class/코디네이터',F.STYLE],
                edges=['edge/우아함'],feats=['feat/근사한-행위',F.FLOURISH],
                feat_ranks={'feat/근사한-행위':2},
                feature_choices={F.STYLE:['근사함'],F.FLOURISH:['근사함']}))
            p=Combatant(self.nr,dict(common,id='contest/p'+str(i),name='same',kind='pokemon',
                                    trainer_id=t.entity_id,poffins=['근사함']*3))
            native.everyone.extend([t,p]);native.gm.everyone=native.everyone
            c=contest.contestant_from_combatants(native,p,t,'매력',{'근사함':4})
            if paired:contest.trainer_participant(c)
            cs.append(c);trainers.append(t);pokemon.append(p)
        return contest,cs,native,trainers,pokemon

    def save_load(self,contest,cs,native=True):
        from state_codec import dump_contest,load_contest
        payload=json.loads(json.dumps(dump_contest(contest,cs),ensure_ascii=False))
        return load_contest(self.cr,payload,native_rules=self.nr if native else None)

    def test_standalone_ids_raw_alias_and_two_rng_graphs(self):
        from contest import Contestant,ContestEngine
        import random
        e=ContestEngine(self.cr,seed=76)
        cs=[Contestant('same',{},['연속자르기'],'매력',3,'귀여움') for _ in range(3)]
        cs[0].raw_backing=vars(cs[0]);cs[0].rng=random.Random(907)
        n,parts=self.save_load(e,cs,native=False)
        self.assertEqual([c.entity_id for c in cs],[c.entity_id for c in parts])
        self.assertEqual(len({c.entity_id for c in parts}),3)
        self.assertIs(parts[0].raw_backing,vars(parts[0]))
        self.assertEqual(n.rng.getstate(),e.rng.getstate())
        self.assertEqual(parts[0].rng.getstate(),cs[0].rng.getstate())
        self.assertEqual(n.rng.randint(1,20),e.rng.randint(1,20))
        self.assertEqual(parts[0].rng.randint(1,20),cs[0].rng.randint(1,20))
        with self.assertRaises(AttributeError):parts[0].entity_id='replacement'

    def pending(self,variant='standard',model=None):
        e,cs,native,ts,ps=self.fixture(paired=model is not None)
        seen={};target=[]
        class AwaitInput(Exception):pass
        def await_choice(preview):
            seen.update(preview)
            raise AwaitInput()
        def chooser(c,rnd,adj,center):
            target.append(c.entity_id)
            return '연속자르기',1,{'flourish_decision':await_choice}
        kw=dict(variant=variant,contest_id='persist/contest')
        if model:kw.update(trainer_model=model,trainer_order=lambda c,t,r:[c,t] if model=='simultaneous' else [c if r%2 else t])
        with self.assertRaises(AwaitInput):
            e.run(cs,None if variant=='super' else '근사함',chooser,**kw)
        state=e._paired_run if model else e._standard_run
        self.assertIsNotNone(state['pending'])
        self.assertEqual(state['phase'],'perform')
        self.assertEqual(len(e._performance_observations),1)
        return e,cs,native,ts,ps,seen,target[0],kw

    def continue_choice(self,e,cs,target,kw,choose,seen):
        def chooser(c,rnd,adj,center):
            if c.entity_id==target and rnd==1:
                def decision(first):
                    seen.append(first)
                    return choose
                return '연속자르기',1,{'flourish_decision':decision}
            return '연속자르기',0
        return e.run(cs,None if kw['variant']=='super' else '근사함',chooser,**kw)

    def test_standard_and_super_public_choice_resume_without_intro_or_cost_replay(self):
        for variant in ('standard','super'):
            for accept in (False,True):
                with self.subTest(variant=variant,accept=accept):
                    e,cs,native,ts,ps,first,target,kw=self.pending(variant)
                    original_rng=e.rng.getstate()
                    n,parts=self.save_load(e,cs)
                    n,parts=self.save_load(n,parts)
                    self.assertEqual(n.rng.getstate(),original_rng)
                    self.assertTrue(all(c.intro_completed for c in parts))
                    first_saved=next(iter(n._performance_observations.values()))['observed_resolution']['observation']['frame']['rolls']
                    self.assertEqual(first_saved,first['rolls'])
                    restored_native=n._native_intro_bindings[parts[0]][0]
                    self.assertIsNot(restored_native,native)
                    for c,binding in n._native_intro_bindings.items():
                        self.assertIs(binding[1].r,restored_native.r)
                        self.assertIn(binding[1],restored_native.everyone)
                        self.assertIn(binding[2],restored_native.everyone)
                    seen=[];original_seen=[]
                    self.continue_choice(n,parts,target,kw,accept,seen)
                    self.continue_choice(e,cs,target,kw,accept,original_seen)
                    self.assertEqual(seen[0]['rolls'],first['rolls'])
                    self.assertEqual(seen,original_seen)
                    self.assertEqual(n.log_lines,e.log_lines)
                    self.assertEqual(n.rng.getstate(),e.rng.getstate())
                    self.assertEqual([(c.appeal,c.fumble,c.stat_dice) for c in parts],
                                     [(c.appeal,c.fumble,c.stat_dice) for c in cs])
                    self.assertEqual(sum(a.spec.get('ap_spent',0) for a in restored_native.everyone),int(accept))
                    self.assertEqual(len(n._flourish_used),int(accept))
                    finished,fs=self.save_load(n,parts)
                    before=(finished.rng.getstate(),copy.deepcopy(finished.last_standings))
                    with self.assertRaisesRegex(ValueError,'already completed'):
                        self.continue_choice(finished,fs,target,kw,accept,[])
                    self.assertEqual(before,(finished.rng.getstate(),finished.last_standings))

    def test_paired_models_restore_shared_pools_and_resume_pending_actual_run(self):
        for model in ('simultaneous','alternating'):
            with self.subTest(model=model):
                e,cs,native,ts,ps,first,target,kw=self.pending(model=model)
                n,parts=self.save_load(e,cs)
                for c in parts:
                    partner=n._trainer_partners[c]
                    self.assertIs(c.stat_dice,partner.stat_dice)
                    if model=='alternating':
                        self.assertIs(c._paired_state,partner._paired_state)
                        c.double_next=True;self.assertTrue(partner.double_next);c.double_next=False
                    else:self.assertNotIn('_paired_state',vars(c))
                seen=[];original_seen=[]
                self.continue_choice(n,parts,target,kw,True,seen)
                self.continue_choice(e,cs,target,kw,True,original_seen)
                self.assertEqual(seen[0]['rolls'],first['rolls'])
                self.assertEqual(n.last_standings,e.last_standings)
                self.assertEqual(n.rng.getstate(),e.rng.getstate())
                self.assertEqual(n.log_lines,e.log_lines)
                done,ds=self.save_load(n,parts)
                self.assertEqual(done._paired_run['phase'],'complete')
                with self.assertRaisesRegex(ValueError,'already completed'):
                    self.continue_choice(done,ds,target,kw,True,[])

    def test_contest_pending_tampered_first_roll_identity_and_unknown_tag_rejected(self):
        from state_codec import dump_contest,load_contest
        e,cs,*_=self.pending()
        payload=dump_contest(e,cs)
        def attrs(p,node):
            return p['nodes'][node['attrs']['$ref']]['items']
        p=copy.deepcopy(payload)
        nodes=[n for n in p['nodes'].values() if n['kind']=='contestant']
        identity=next(v for k,v in attrs(p,nodes[0]) if k=='_contestant_id')
        for pair in attrs(p,nodes[1]):
            if pair[0]=='_contestant_id':pair[1]=identity
        with self.assertRaisesRegex(StateCodecError,'unique stable'):
            load_contest(self.cr,p,native_rules=self.nr)
        p=copy.deepcopy(payload);p['nodes'][p['root']['$ref']]['kind']='arbitrary.Import'
        with self.assertRaisesRegex(StateCodecError,'unknown graph'):
            load_contest(self.cr,p,native_rules=self.nr)
        p=copy.deepcopy(payload)
        frame=next(n for n in p['nodes'].values() if n['kind']=='dict' and any(pair[0]=='rerolled' for pair in n['items']))
        for pair in frame['items']:
            if pair[0]=='appeal':pair[1]+=1
        with self.assertRaisesRegex(StateCodecError,'public dice'):
            load_contest(self.cr,p,native_rules=self.nr)
        p=copy.deepcopy(payload);p['native_rules']['sha256']='0'*64
        with self.assertRaisesRegex(StateCodecError,'native contest source'):
            load_contest(self.cr,p,native_rules=self.nr)

    def test_contest_callbacks_reentry_and_stale_declaration_rejected(self):
        from state_codec import dump_contest
        e,cs,native,ts,ps=self.fixture()
        seen=[]
        def decision(first):
            seen.append(first)
            with self.assertRaisesRegex(StateCodecError,'executing contest'):
                dump_contest(e,cs)
            with self.assertRaisesRegex(ValueError,'reenter'):
                e.run(cs,'근사함',lambda *a:('연속자르기',0))
            raise LookupError('await choice')
        with self.assertRaises(LookupError):
            e.run(cs,'근사함',lambda *a:('연속자르기',1,{'flourish_decision':decision}))
        n,parts=self.save_load(e,cs)
        before=n.rng.getstate()
        with self.assertRaisesRegex(ValueError,'locked'):
            n.run(parts,'근사함',lambda *a:('연속자르기',0))
        self.assertEqual(before,n.rng.getstate())
        parts[0].callback=lambda:None
        with self.assertRaises(StateCodecError):dump_contest(n,parts)

    def test_contest_checkpoint_restores_pending_cursor_and_backing_alias(self):
        e,cs,native,ts,ps,first,target,kw=self.pending()
        cs[0].backing=vars(cs[0]);e.snapshot('choice')
        saved_rng=e.rng.getstate()
        self.continue_choice(e,cs,target,kw,True,[])
        e.restore('choice',reason='test actual pending checkpoint')
        self.assertEqual(e._standard_run['phase'],'perform')
        self.assertIs(cs[0].backing,vars(cs[0]))
        self.assertEqual(saved_rng,e.rng.getstate())
        self.assertEqual(sum(t.spec.get('ap_spent',0) for t in ts),0)
        seen=[];self.continue_choice(e,cs,target,kw,False,seen)
        self.assertEqual(seen[0]['rolls'],first['rolls'])

    def test_plain_pre_performance_pause_resumes_super_type_and_intro_once(self):
        from contest import Contestant,ContestEngine
        e=ContestEngine(self.cr,seed=13)
        cs=[Contestant(str(i),{},['연속자르기'],'매력',3,'귀여움') for i in range(3)]
        count=[]
        def pause(c,rnd,*args):
            count.append(c)
            if len(count)==2:raise LookupError('choose next move')
            return '연속자르기',0
        with self.assertRaises(LookupError):e.run(cs,None,pause,variant='super')
        self.assertEqual(e._standard_run['slot'],1)
        old_type=e._standard_run['round_type']
        n,parts=self.save_load(e,cs,native=False)
        self.assertEqual(n._standard_run['round_type'],old_type)
        n.run(parts,None,lambda *a:('연속자르기',0),variant='super')
        e.run(cs,None,lambda *a:('연속자르기',0),variant='super')
        self.assertEqual(n.log_lines,e.log_lines)
        self.assertEqual(n.rng.getstate(),e.rng.getstate())

if __name__ == '__main__':
    unittest.main(verbosity=2)
