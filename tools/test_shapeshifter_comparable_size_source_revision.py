"""Actual Shapeshifter admissions, scoped GM size facts and historical bodies."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from builder import build_pokemon
from native_scenario_fixture import prepare_body, assert_rejected_unchanged
import test_category2_body_modes as FIXTURE
import body_modes as MODE
import body_state as BODY
import state_codec as CODEC
import world_entities as WORLD


class ShapeshifterComparableSizeSourceRevisionTests(unittest.TestCase):
    setUpClass = classmethod(FIXTURE.Tests.setUpClass.__func__)
    setUp = FIXTURE.Tests.setUp
    add = FIXTURE.Tests.add
    pokemon = FIXTURE.Tests.pokemon
    begin = FIXTURE.Tests.begin

    def ditto(self, pos=(12, 3)):
        actor = self.add(build_pokemon(
            self.r, '메타몽', 10, moves=[], abilities=[],
            extra={'trainer_id': self.a.entity_id, 'height_m': 0.5,
                   'weight_kg': 4, 'weight_class': 1}))
        actor.pos = pos
        prepare_body(self.e, actor, size=actor.spec['size'], offsets=[(0, 0)],
                     reason='actual original small Ditto body occupies this observed cell')
        self.e.gm.observe_loyalty(actor, 6, reason='actual known obedience')
        return actor

    def proposal(self, *, description='observed Pikachu appearance', size='소형', height=0.4,
                 offsets=None):
        return {'appearance': {'kind': 'pokemon', 'description': description, 'size': size},
                'height_m': height, 'offsets': [(0, 0)] if offsets is None else offsets,
                'mass_ratio': 1}

    def judgement(self, actor, proposal, *, comparable=True):
        before = self.e.export_state()
        pending = MODE.shapeshift_size_choices(self.e, actor, **proposal)
        self.assertEqual(pending['status'], 'PolicyInputsRequired')
        self.assertEqual(self.e.export_state(), before)
        return {'value': comparable,
                'reason': 'GM compares this exact intended appearance with this actual original body',
                'scope': pending['decision_scope']}

    def apply(self, actor, proposal, choice=None):
        return self.e.change_body_mode(
            actor, 'shapeshift', **proposal, pokemon_size_choice=choice,
            reason='actual current observed Pokemon appearance admission')

    def test_actual_admission_pays_standard_preserves_own_mechanics_and_can_return(self):
        actor = self.ditto()
        own = deepcopy((actor.spec['species'], actor.spec['types'], actor.stats,
                        actor.moves, actor.abilities, actor.spec.get('movement')))
        self.begin(actor)
        proposal = self.proposal()
        choice = self.judgement(actor, proposal)
        out = self.apply(actor, proposal, choice)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(BODY.cells(actor), {(12, 3)})
        self.assertEqual(out['height_m'], 0.4)
        self.assertEqual(BODY.weight_kg(actor), 4)
        self.assertFalse(out['appearance_limits']['grants_copied_mechanics'])
        self.assertEqual((actor.spec['species'], actor.spec['types'], actor.stats,
                          actor.moves, actor.abilities, actor.spec.get('movement')), own)
        self.assertNotIn('move/변신', actor.moves)
        retained = actor.spec[MODE.KEY]['pokemon_size_observation']
        basis = json.loads(retained['policy']['values']['basis_json'])
        self.assertEqual(basis['actor_id'], actor.entity_id)
        self.assertEqual(basis['original']['height_m'], 0.5)
        self.assertEqual(basis['intended']['appearance'], proposal['appearance'])
        self.assertEqual(retained['choice'], choice)
        self.assertEqual(MODE.shapeshift_size_status(actor)['status'], 'retained_admission_observation')
        self.begin(actor)
        self.e.change_body_mode(actor, 'normal', reason='actual paid return to original body')
        self.assertNotIn(MODE.KEY, actor.spec)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(BODY.projection(actor)['height_m'], 0.5)
        self.assertEqual((actor.spec['species'], actor.spec['types'], actor.stats,
                          actor.moves, actor.abilities, actor.spec.get('movement')), own)

    def test_missing_or_negative_current_judgement_rejects_before_payment_and_rng(self):
        actor = self.ditto()
        self.begin(actor)
        proposal = self.proposal(description='observed gigantic Pokemon appearance',
                                 size='초거대', height=14,
                                 offsets=[(x, y) for x in range(4) for y in range(4)])
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, proposal),
            reason_pattern='explicit current GM Pokemon size observation required')
        # The actual GM judgement supplies the qualitative answer; no height,
        # category-step or mass ratio is inferred as a similarity threshold.
        negative = self.judgement(actor, proposal, comparable=False)
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, proposal, negative),
            reason_pattern='not comparable in size')
        unscoped = {'value': True, 'reason': 'unbound blanket approval'}
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, self.proposal(), unscoped),
            reason_pattern='current scoped GM Pokemon size judgement required')
        self.assertNotIn(MODE.KEY, actor.spec)
        self.assertEqual(actor.budget['standard'], 1)

    def test_foreign_stale_body_and_intended_geometry_scopes_and_late_map_failure_are_atomic(self):
        actor = self.ditto()
        other = self.ditto(pos=(16, 3))
        proposal = self.proposal()
        choice = self.judgement(actor, proposal)
        self.begin(other)
        assert_rejected_unchanged(
            self.e, lambda: self.apply(other, proposal, choice),
            reason_pattern='GM decision scope changed')
        self.begin(actor)
        changed = self.proposal(height=0.6, offsets=[(0, 0), (0, 1)])
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, changed, choice),
            reason_pattern='GM decision scope changed')
        actor.spec['height_m'] = 0.6  # An actual new observation of the original body.
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, proposal, choice),
            reason_pattern='GM decision scope changed')
        current = self.judgement(actor, changed)
        self.e.grid.blocking.add((12, 4))
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, changed, current),
            reason_pattern='changed body does not fit actual map')
        self.e.grid.blocking.remove((12, 4))
        self.apply(actor, changed, current)
        self.assertEqual(actor.budget['standard'], 0)
        self.assertEqual(BODY.cells(actor), {(12, 3), (12, 4)})
        self.assertEqual(json.loads(actor.spec[MODE.KEY]['pokemon_size_observation']
                                    ['policy']['values']['basis_json'])['original']['height_m'], 0.6)

    def test_legacy_gm_and_fresh_rules_json_keep_unknown_past_then_require_paid_current_reapplication(self):
        actor = self.ditto()
        legacy = {'mode': 'shapeshift', 'source': 'capability/형상변환자',
                  'size_ratio': 1, 'mass_ratio': 1, 'mass_weight_class': None,
                  'appearance': {'kind': 'pokemon', 'description': 'observed historical huge Pokemon appearance'},
                  'height_m': 14, 'reason': 'retained actual historical appearance observation',
                  'footprint': {'kind': 'observed_cells', 'offsets': [(0, 0)],
                                'reason': 'retained historical occupied body observation'}}
        actor.spec[MODE.KEY] = deepcopy(legacy)
        self.assertEqual(MODE.validate(actor), legacy)
        self.assertEqual(MODE.shapeshift_size_status(actor)['status'], 'source_observation_required')
        self.assertNotIn('pokemon_size_observation', actor.spec[MODE.KEY])
        self.e.gm.snapshot('historical-shape')
        self.begin(actor)
        self.e.change_body_mode(actor, 'normal', reason='paid exit from historical observed body')
        self.assertEqual(actor.budget['standard'], 0)
        self.e.gm.restore('historical-shape')
        self.assertEqual(actor.spec[MODE.KEY], legacy)
        fresh = Rules(ROOT, ruleset='core')
        self.e = CODEC.load_engine(fresh, json.loads(json.dumps(CODEC.dump_engine(self.e), ensure_ascii=False)))
        actor = WORLD.actor_index(self.e)[actor.entity_id]
        self.assertEqual(actor.spec[MODE.KEY]['appearance'], legacy['appearance'])
        self.assertEqual(actor.spec[MODE.KEY]['height_m'], 14)
        self.assertEqual(MODE.shapeshift_size_status(actor)['status'], 'source_observation_required')
        self.assertNotIn('pokemon_size_observation', actor.spec[MODE.KEY])
        self.begin(actor)
        proposal = self.proposal()
        assert_rejected_unchanged(
            self.e, lambda: self.apply(actor, proposal),
            reason_pattern='explicit current GM Pokemon size observation required')
        choice = self.judgement(actor, proposal)
        historical_before = deepcopy(actor.spec[MODE.KEY])
        self.apply(actor, proposal, choice)
        self.assertEqual(actor.budget['standard'], 0)
        receipt = self.e.rulings.log[-1]
        self.assertEqual(receipt['before'], historical_before)
        self.assertEqual(receipt['after'], actor.spec[MODE.KEY])
        self.assertNotIn('pokemon_size_observation', receipt['before'])
        self.assertIn('pokemon_size_observation', receipt['after'])
        self.assertEqual(MODE.shapeshift_size_status(actor)['status'], 'retained_admission_observation')


if __name__ == '__main__':
    unittest.main()
