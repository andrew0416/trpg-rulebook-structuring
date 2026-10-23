"""F49: actual native Massive Damage survives HP replacement, caps and policies."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
import test_category2_class_actor_state_reactions as BASE
import class_actor_state_reactions as R
import trainer_feature_acquisition as ACQUIRE
import moment_of_action as MOMENT
import cheerleader as CHEER
import keep_fighting as KEEP
import state_fields as FIELDS
import state_codec as CODEC
import world_entities as WORLD
import campaign_injury_policy as INJURY
import frequency as FREQUENCY
import effects_ext as EXT
from engine import Rules


class MassiveReactionRescueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='all')

    def setUp(self):
        self.ruling_state = deepcopy(vars(self.rules.rulings))

    def tearDown(self):
        vars(self.rules.rulings).clear()
        vars(self.rules.rulings).update(self.ruling_state)

    def fixture(self, *, rescue=False, hp=None, temp=0, cap=None, injuries=0,
                immune=False, disabled=False):
        base = BASE.ClassActorStateReactionTests()
        base.rules = self.rules
        # The established source-import fixture builds the owner with the
        # actual reaction source, rather than adding a feat via state patch.
        e, owner, partner, enemy = base.fixture(feats=[R.THIS_WILL_NOT_STAND], partner_types=('드래곤',))
        e.end_encounter()
        if rescue:
            FIELDS.base_patch(owner, {'skills': {'매력': 6, '명령': 2}}, reason='actual Master Charm acquisition')
            for source in (MOMENT.TRAINING, MOMENT.CLASS, MOMENT.FEATURE,
                           CHEER.BRIGADE, CHEER.SUPPORT, 'feat/신나게-방해', KEEP.FEATURE):
                ACQUIRE.acquire_static(e, owner, source, acquisition_request_id='f49/acquire/' + source)
            e.rulings.add_answer('keep_fighting', True, reason='accept actual HP crossing', scope='permanent')
        if immune:
            # A real ability transition supplies the native Massive-injury immunity.
            e.gm.set_ability(partner, '옹골참', reason='actual Sturdy target')
        if disabled:
            INJURY.configure(e, injury_mode='disabled', death_enabled=False,
                             center_heals_all=False, reason='actual adopted no-injury campaign')
        if injuries:
            e.gm.set_injuries(partner, value=injuries, reason='actual preexisting injuries')
        if cap is not None:
            partner.damage_cap = {'value': cap}
        e.gm.set_temp_hp(partner, temp, reason='actual initial temporary HP')
        e.gm.set_hp(partner, value=partner.base_max_hp if hp is None else hp, reason='actual initial HP')
        enemy.stats['atk'] = enemy.spec['stats']['atk'] = 100
        e.gm.set_position(enemy, (2, 0), reason='actual adjacent melee attacker')
        e.begin_encounter(e.everyone)
        e.start_round(e.everyone)
        e.start_of_turn(enemy, initiative_count=10)
        return e, owner, partner, enemy

    def hit(self, e, owner, partner, enemy, *, critical=False):
        receipt = {}
        requested = e.resolve_attack_damage(enemy, partner, e.r.move('move/몸통박치기'),
                                            crit=critical, set_damage=True, _damage_observation=receipt)
        pending = [r for r in e.pending_class_actor_state_reactions(owner) if r['source'] == R.THIS_WILL_NOT_STAND]
        self.assertFalse(hasattr(partner, '_native_damage_observation'))
        # The existing Cheerleader outer transaction copies mutable kwargs;
        # its committed reaction is the observable native receipt in that path.
        if not receipt and len(pending) == 1:
            receipt = pending[0]['damage_receipt']
        return requested, receipt, pending

    def test_actual_massive_after_one_hp_rescue_preserves_both_source_ids_and_scene_limit(self):
        e, owner, partner, enemy = self.fixture(rescue=True, hp=1)
        requested, receipt, pending = self.hit(e, owner, partner, enemy)
        self.assertEqual((partner.hp, partner.temp_hp, partner.injuries), (1, 12, 1))
        self.assertEqual(receipt['net_hp_loss'], 0)
        self.assertEqual(receipt['native_damage'], {
            'amount_after_temporary_hp': requested, 'maximum_hp': partner.base_max_hp, 'massive': True})
        self.assertEqual(len(pending), 1)
        event = pending[0]
        self.assertFalse(event['critical'])
        self.assertTrue(event['massive'])
        self.assertEqual(event['native_clause_id'], 'input/ch04-trainer-classes.md:1454-1458')
        self.assertEqual(event['clause_id'], 'C2CSV/input/db/feats.csv:R240:main')
        e.resolve_class_actor_state_reaction(owner, event['id'], use=True)
        self.assertEqual(tuple(partner.stages[s] for s in ('atk', 'spa', 'spe')), (1, 1, 1))
        self.assertFalse(self.hit(e, owner, partner, enemy)[2])

    def test_actual_cap_and_temporary_hp_boundaries_control_massive_not_requested_damage(self):
        # True maximum is 60 here. Test the exact 30 boundary and absorbed/capped negatives.
        for cap, temp in ((None, 73), (None, 72), (29, 0), (30, 0), (0, 0), (50, 21), (None, 1000)):
            with self.subTest(cap=cap, temp=temp):
                e, owner, partner, enemy = self.fixture(cap=cap, temp=temp)
                maxhp = partner.base_max_hp
                requested, receipt, pending = self.hit(e, owner, partner, enemy)
                actual = max(0, min(requested, cap) - temp) if cap is not None else max(0, requested - temp)
                self.assertEqual((requested, maxhp), (102, 60))
                self.assertEqual(receipt['native_damage'], {
                    'amount_after_temporary_hp': actual, 'maximum_hp': maxhp, 'massive': actual >= 30})
                self.assertEqual(len(pending), int(actual >= 30))

    def test_actual_true_maximum_survives_preexisting_injury_recovery_ceiling(self):
        e, owner, partner, enemy = self.fixture(injuries=4, cap=25, hp=29)
        # Stay below the independent raw-Massive/heavy-order pending boundary.
        enemy.stats['atk'] = enemy.spec['stats']['atk'] = 24
        self.assertLess(partner.max_hp / 2, 25)
        requested, receipt, pending = self.hit(e, owner, partner, enemy)
        self.assertGreater(requested, 25)
        self.assertEqual(receipt['native_damage'], {
            'amount_after_temporary_hp': 25, 'maximum_hp': 60, 'massive': False})
        self.assertFalse(pending)

    def test_massive_fact_is_independent_of_sturdy_and_disabled_injury_retention(self):
        for policy in ('immune', 'disabled'):
            with self.subTest(policy=policy):
                e, owner, partner, enemy = self.fixture(cap=30, **{policy: True})
                _, receipt, pending = self.hit(e, owner, partner, enemy)
                # Sturdy prevents Massive's injury; the independent half-HP
                # marker still adds one. Disabled campaign retains neither.
                self.assertEqual(partner.injuries, 1 if policy == 'immune' else 0)
                self.assertTrue(receipt['native_damage']['massive'])
                self.assertEqual(len(pending), 1)

    def test_critical_remains_independent_when_all_damage_is_absorbed(self):
        e, owner, partner, enemy = self.fixture(temp=1000)
        _, receipt, pending = self.hit(e, owner, partner, enemy, critical=True)
        self.assertEqual(receipt['net_hp_loss'], 0)
        self.assertFalse(receipt['native_damage']['massive'])
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]['critical'])
        self.assertFalse(pending[0]['massive'])

    def test_original_native_hit_fact_survives_later_healing_and_small_followup_damage(self):
        e, owner, partner, enemy = self.fixture(cap=30)
        original, followed = EXT.after_damage, []
        def after_damage(engine, actor):
            original(engine, actor)
            if actor.entity_id == partner.entity_id and not followed:
                followed.append(True)
                engine.heal(actor, 30)
                engine.take_damage(actor, 1)
        with patch.object(EXT, 'after_damage', side_effect=after_damage):
            _, receipt, pending = self.hit(e, owner, partner, enemy)
        self.assertEqual(followed, [True])
        self.assertLess(receipt['net_hp_loss'], 30)
        self.assertEqual(receipt['native_damage'], {
            'amount_after_temporary_hp': 30, 'maximum_hp': 60, 'massive': True})
        self.assertEqual(len(pending), 1)

    def test_native_move_late_failure_rolls_back_then_json_reaction_resolves_once(self):
        e, owner, partner, enemy = self.fixture(rescue=True, hp=1)
        before = CODEC.dump_engine(e)
        real = R.observe_attack_damage
        def late(*args, **options):
            real(*args, **options)
            raise ValueError('late actual F49 reaction observation')
        with patch.object(type(e), 'd20', new=lambda engine: 18), patch.object(R, 'observe_attack_damage', side_effect=late):
            with self.assertRaisesRegex(ValueError, 'late actual F49'):
                e.use_move(enemy, partner, 'move/몸통박치기', set_damage=True)
        self.assertEqual(CODEC.dump_engine(e), before)
        self.assertFalse(hasattr(partner, '_native_damage_observation'))
        with patch.object(type(e), 'd20', new=lambda engine: 18):
            e.use_move(enemy, partner, 'move/몸통박치기', set_damage=True)
        event = e.pending_class_actor_state_reactions(owner)[0]
        facts = deepcopy(event['damage_receipt']['native_damage'])
        loaded = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(e), ensure_ascii=False)))
        actors = WORLD.actor_index(loaded)
        actual_owner, actual_partner = actors[owner.entity_id], actors[partner.entity_id]
        restored = loaded.pending_class_actor_state_reactions(actual_owner)[0]
        self.assertEqual(restored['damage_receipt']['native_damage'], facts)
        before = CODEC.dump_engine(loaded)
        with self.assertRaises(ValueError):
            loaded.resolve_class_actor_state_reaction(actual_owner, restored['id'], use='yes')
        self.assertEqual(CODEC.dump_engine(loaded), before)
        original = FREQUENCY.consume_activation
        def fail_after_payment(*args, **kwargs):
            original(*args, **kwargs)
            raise ValueError('late F49 actual frequency payment')
        with patch.object(FREQUENCY, 'consume_activation', side_effect=fail_after_payment):
            with self.assertRaisesRegex(ValueError, 'late F49 actual frequency'):
                loaded.resolve_class_actor_state_reaction(actual_owner, restored['id'], use=True)
        self.assertEqual(CODEC.dump_engine(loaded), before)
        loaded.resolve_class_actor_state_reaction(actual_owner, restored['id'], use=True)
        self.assertEqual(tuple(actual_partner.stages[s] for s in ('atk', 'spa', 'spe')), (1, 1, 1))
        with self.assertRaises(ValueError):
            loaded.resolve_class_actor_state_reaction(actual_owner, restored['id'], use=True)
        self.assertTrue(loaded.validate_state()['valid'])
