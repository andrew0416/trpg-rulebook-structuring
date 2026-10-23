"""Actual food completion after native timed HP loss, through Engine.use_item."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_pokemon
import state_codec as CODEC
import world_entities as WORLD
import food_effects as FOOD
import consumption_execution as PAYMENTS
import items as ITEMS
import item_maturation as MATURATION

EVIDENCE = []
FOODS = (
    ('item/흉내허브', 'C2CSV/inventory:232:10', 'snack'),
    ('item/다이버섯', 'C2CSV/inventory:92:7', 'snack'),
    ('item/회복허브', 'C2CSV/item-data:66:1', 'snack'),
    ('item/단맛-과자', 'C2CSV/inventory:91:7', 'snack'),
    ('item/초코바', None, 'snack'),
    ('item/맛있는물', None, 'drink'),
    ('item/이유식', 'book_xp20_level15', 'baby'),
)


class IntakeCompletionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(str(ROOT), ruleset='core')

    def fixture(self, item, *, hp=1, species='피카츄'):
        engine = Engine(self.rules, seed=4501)
        actor = Combatant(self.rules, build_pokemon(
            self.rules, species, 10, name='native intake completion',
            moves=[], abilities=[], extra={'items': {item: 1}}))
        engine.gm.add_combatant(actor, reason='actual food owner and consumer')
        actor.hp = hp
        return engine, actor

    def timer(self, engine, actor):
        effect = {'type': 'hp_loss', 'value': 1,
                  'repeat': {'seconds': 5, 'times': 1}}
        self.assertEqual(engine.apply_effect(actor, actor, effect, None, True, 0,
                         'external/intake-completion-timer'), (1, 0))

    def options(self, policy, resumable=False, **extra):
        options = dict(duration_minutes=1, duration_reason='observed sixty-second intake')
        if policy is not None:
            options['food_policy'] = policy
        if resumable:
            options.update(resumable=True, request_id='native-intake-completion')
        options.update(extra)
        return options

    def invoke(self, label, engine, actor, item, options):
        before = CODEC.dump_engine(engine)
        try:
            result = engine.use_item(actor, item, **options)
            error = None
        except Exception as exc:
            result, error = None, exc
        after = CODEC.dump_engine(engine)
        EVIDENCE.append(dict(case=label, item=item, options=deepcopy(options),
                             actor_id=actor.entity_id, before=before, after=after,
                             result=result, error=None if error is None else
                             {'type': type(error).__name__, 'message': str(error)}))
        return before, after, result, error

    def restored(self, engine, actor):
        data = CODEC.dump_engine(engine)
        def observed(e, a):
            return deepcopy(dict(elapsed=e.elapsed_seconds, hp=a.hp, fainted=a.fainted,
                dead=a.dead, spec=a.spec, buffs=a.buffs, conditions=sorted(a.conditions),
                slots=FOOD.slots(a), counters=a.counters,
                action_history=getattr(a, '_action_history', []),
                physical=getattr(e, '_physical_objects', {}),
                clocks={key: dict(status=row['status'], cursor=row['cursor'],
                                  activity_status=row.get('activity', {}).get('status'))
                        for key, row in getattr(e, '_clock_invocations', {}).items()}))
        before = observed(engine, actor)
        restored = CODEC.load_engine(self.rules, json.loads(json.dumps(data)))
        recovered = WORLD.actor_index(restored)[actor.entity_id]
        after = observed(restored, recovered)
        EVIDENCE.append(dict(case='json-roundtrip', actor_id=actor.entity_id,
                             before=before, after=after))
        self.assertEqual(before, after)
        CODEC.dump_engine(restored)  # validate the restored native receipt/clock graph
        return restored, recovered

    def no_benefit(self, actor):
        self.assertEqual(FOOD.slots(actor), 0)
        self.assertEqual(actor.buffs, [])
        self.assertFalse(actor.spec.get('drink_history'))
        self.assertNotIn('baby_food', actor.spec)
        self.assertNotIn('extended', getattr(actor, '_action_history', []))

    def completion_error(self, error):
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), 'conscious food consumer required at completion')

    def test_ordinary_timer_failure_restores_time_timer_stock_receipts_and_slot(self):
        for item, policy, kind in FOODS:
            with self.subTest(item=item):
                e, actor = self.fixture(item)
                self.timer(e, actor)
                before, after, result, error = self.invoke(
                    'ordinary-faint', e, actor, item, self.options(policy))
                self.completion_error(error)
                self.assertIsNone(result)
                self.assertEqual(before, after)
                self.assertEqual((e.elapsed_seconds, actor.hp, actor.fainted), (0, 1, False))
                self.assertEqual(actor.spec['items'][item], 1)
                self.assertEqual(PAYMENTS.validate(actor), {})
                self.no_benefit(actor)
                e, actor = self.restored(e, actor)
                # The native timer was also restored; advancing it still faints.
                e.advance_time(5, [actor])
                self.assertEqual((e.elapsed_seconds, actor.hp, actor.fainted), (5, 0, True))
                self.assertEqual(actor.spec['items'][item], 1)
                self.no_benefit(actor)

    def test_resumable_failure_preserves_elapsed_timer_but_not_completion(self):
        for item, policy, kind in FOODS:
            with self.subTest(item=item):
                e, actor = self.fixture(item)
                self.timer(e, actor)
                options = self.options(policy, True)
                _, _, result, error = self.invoke('resumable-faint', e, actor, item, options)
                self.completion_error(error)
                self.assertIsNone(result)
                self.assertEqual((e.elapsed_seconds, actor.hp, actor.fainted), (60, 0, True))
                self.assertEqual(actor.spec['items'][item], 1)
                self.assertEqual(PAYMENTS.validate(actor), {})
                self.no_benefit(actor)
                clock = e._clock_invocations[options['request_id']]
                self.assertEqual((clock['status'], clock['cursor'], clock['activity']['status']),
                                 ('complete', 60, 'pending'))
                e, actor = self.restored(e, actor)
                before, after, _, error = self.invoke('resumable-faint-replay', e, actor, item, options)
                self.completion_error(error)
                self.assertEqual(before, after)

    def test_conscious_native_timer_control_keeps_existing_food_outcomes(self):
        for resumable in (False, True):
            for item, policy, kind in FOODS:
                with self.subTest(item=item, resumable=resumable):
                    e, actor = self.fixture(item, hp=5)
                    self.timer(e, actor)
                    options = self.options(policy, resumable)
                    _, _, result, error = self.invoke('conscious-control', e, actor, item, options)
                    self.assertIsNone(error)
                    self.assertEqual(e.elapsed_seconds, 60)
                    self.assertFalse(actor.fainted)
                    self.assertEqual(actor.hp, 24 if kind == 'drink' else 4)
                    self.assertEqual(actor.spec['items'][item], 0)
                    paid = list(PAYMENTS.validate(actor).values())
                    self.assertEqual(len(paid), 1)
                    self.assertEqual(paid[0]['item_stock']['item_id'], item)
                    self.assertEqual(paid[0]['outcome'], 'paid' if kind == 'baby' else 'applied')
                    self.assertEqual(FOOD.slots(actor), 1 if kind == 'snack' else 0)
                    self.assertEqual(actor._action_history, ['extended'])
                    if kind == 'snack':
                        self.assertEqual(result['status'], 'digestion_buff_gained')
                        self.assertEqual(actor.buffs[0]['item'], item)
                        if policy:
                            self.assertEqual(actor.buffs[0]['csv_food_source']['clause_id'], policy)
                    elif kind == 'drink':
                        self.assertEqual(result['healed'], 20)
                        self.assertEqual(len(actor.spec['drink_history']), 1)
                    else:
                        self.assertTrue(result['eligible'])
                        self.assertEqual(actor.spec['baby_food']['policy'], policy)
                    e, actor = self.restored(e, actor)
                    if resumable:
                        before, after, replay, error = self.invoke('conscious-replay', e, actor, item, options)
                        self.assertIsNone(error)
                        self.assertEqual(replay, result)
                        self.assertEqual(before, after)

    def test_other_recipient_cannot_finish_after_native_timer_faints_them(self):
        item, policy, _ = FOODS[0]
        e, giver = self.fixture(item, hp=5)
        recipient = Combatant(self.rules, build_pokemon(
            self.rules, '이브이', 10, name='actual other recipient', moves=[], abilities=[]))
        e.gm.add_combatant(recipient, reason='distinct food recipient')
        recipient.hp = 1
        self.timer(e, recipient)
        before = CODEC.dump_engine(e)
        with self.assertRaisesRegex(ValueError, 'conscious food consumer required at completion'):
            e.use_item(giver, item, recipient, **self.options(policy))
        self.assertEqual(before, CODEC.dump_engine(e))
        self.assertEqual((giver.hp, recipient.hp, giver.spec['items'][item]), (5, 1, 1))
        self.no_benefit(recipient)
        self.restored(e, recipient)

    def shell_fixture(self):
        e, actor = self.fixture('item/나무열매쥬스', species='단단지')
        WORLD.register_object(e, 'native-berry', location={'kind': 'unknown'},
                              reason='actual maturation input', kind='item_instance',
                              item_rule_id='item/오랭열매', owner_id=actor.entity_id)
        ITEMS.equip_held(e, actor, 'item/오랭열매', source_instance_id='native-berry')
        key = next(iter(actor.spec[MATURATION.KEY]))
        e.advance_time(86400, [actor])
        self.assertEqual(actor.spec[MATURATION.KEY][key]['stage'], 'juice')
        self.timer(e, actor)
        return e, actor, key

    def test_shell_start_payment_respects_existing_ordinary_and_resumable_boundaries(self):
        for resumable in (False, True):
            with self.subTest(resumable=resumable):
                e, actor, key = self.shell_fixture()
                options = self.options(None, resumable, shell_batch_id=key)
                before, after, _, error = self.invoke('shell-faint', e, actor, 'item/나무열매쥬스', options)
                self.completion_error(error)
                row = actor.spec[MATURATION.KEY][key]
                self.no_benefit(actor)
                self.assertEqual(actor.spec['items']['item/나무열매쥬스'], 1)
                if resumable:
                    self.assertEqual((e.elapsed_seconds, actor.hp, actor.fainted), (86460, 0, True))
                    self.assertEqual((row['stage'], row['removal']['at']), ('consumed', 86400))
                    paid = list(PAYMENTS.validate(actor).values())
                    self.assertEqual((len(paid), paid[-1]['outcome']), (2, 'paid'))
                    self.assertIs(e._clock_invocations[options['request_id']]['activity']['payment'],
                                  paid[-1]['item_stock'])
                else:
                    self.assertEqual(before, after)
                    self.assertEqual((e.elapsed_seconds, actor.hp, row['stage']), (86400, 1, 'juice'))
                self.restored(e, actor)


if __name__ == '__main__':
    unittest.main()
