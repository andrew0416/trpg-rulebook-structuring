"""Hunter pack rules: Teamwork and Pack Hunt consumers, Hunter's Reflexes, Pack Master and Don't Look Away.

Reuses the acquisition scene helpers without inheriting any test method.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

import test_book_hunter_acquisition as fixture
from engine import Rules, Engine
import ability_transitions as ABILITIES
import action_points as AP
import combat_timing as TIMING
import hunter as HU
import turn as TURN


class HunterPackTests(fixture.HunterScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(fixture.ROOT, ruleset='core')

    # ---------------------------------------------------------------- helpers
    def foe(self, name, pos, speed):
        return self.add(name, 'pokemon', pos, side='foe', species='피카츄', types=['전기'],
            moves=['move/막치기', 'move/몸통박치기', 'move/전광석화'], speed=speed)

    def away(self, actor, destination=(12, 6), face=15):
        """The actor leaves its cell toward a far point; adjacent enemies take their Attacks of Opportunity."""
        pseudo = deepcopy(actor)
        pseudo.pos = destination
        with patch.object(Engine, 'd20', return_value=face):
            return self.e.approach(actor, pseudo, movement_mode='land')

    def modifier(self, actor):
        """The modifier printed by the actual last accuracy roll of this actor."""
        line = self.accuracy_log(actor)[-1]
        return int(line.split('명중 d20=')[1].split('=')[0].split('+' if '+' in line.split('명중 d20=')[1].split('=')[0] else '-')[1]) * (1 if '+' in line.split('명중 d20=')[1].split('=')[0] else -1)

    def bonus(self, attacker, move='struggle', target=None):
        move = self.e.r.move(move) if isinstance(move, str) else move
        return HU.teamwork_bonus(self.e, attacker, target or self.q, move)

    # ---------------------------------------------------------------- Teamwork (Ability consumer)
    def test_teamwork_adds_two_once_to_an_allys_melee_attack_against_the_foe_adjacent_to_the_holder(self):
        # p (Teamwork) is adjacent to q; v is another party Pokemon without a Hunter owner.
        self.assertEqual(self.bonus(self.v), 2)
        self.assertEqual(self.bonus(self.v, 'move/전기쇼크'), 0)           # ranged: not a melee attack
        self.assertEqual(self.bonus(self.p), 0)                           # the holder's own attack has no other adjacent holder
        self.assertEqual(self.bonus(self.q, target=self.v), 0)            # a foe attacking the party does not benefit
        self.e.gm.set_position(self.t, (3, 3), reason='actual second adjacent cell')
        self.acquire()                                                    # the Hunter now holds Teamwork too, adjacent to q
        self.assertTrue(ABILITIES.active(self.t, 'ability/팀워크'))
        self.assertEqual(self.bonus(self.v), 2)                           # two adjacent holders: the same +2, no stacking
        self.assertEqual(self.bonus(self.p), 2)                           # p benefits from the Trainer's Teamwork
        self.e.gm.set_position(self.p, (8, 8), reason='actual departure')
        self.e.gm.set_position(self.t, (1, 1), reason='actual departure')
        self.assertEqual(self.bonus(self.v), 0)                           # no holder adjacent to the foe
        # Actual roll: the ally's melee struggle against q with p adjacent carries the +2.
        self.e.gm.set_position(self.p, (3, 2), reason='actual return')
        self.e.gm.set_position(self.v, (5, 3), reason='actual adjacent attacker')
        self.combat(self.v, count=25)
        self.use(self.v, self.q, 'struggle', face=10)
        self.assertIn('d20=10+2=12', self.accuracy_log(self.v)[-1])
        self.e.gm.set_position(self.p, (8, 8), reason='actual departure')
        self.next_round(self.v, count=25)
        self.use(self.v, self.q, 'struggle', face=10)
        self.assertIn('d20=10+0=10', self.accuracy_log(self.v)[-1])
        self.restore()
        self.valid()

    # ---------------------------------------------------------------- Hunter's Reflexes
    def test_reflexes_allow_three_opportunity_attacks_a_round_for_the_hunter_and_owned_pokemon_only(self):
        self.whole()
        for actor, limit in ((self.t, 3), (self.p, 3), (self.u, 3), (self.b, 1), (self.v, 1), (self.q, 1)):
            self.assertEqual(HU.opportunity_limit(self.e, actor), limit, actor.name)
        # Four foes adjacent to p and to v: each departure provokes; p answers three, v one.
        self.e.gm.set_position(self.p, (6, 6), reason='actual pack position')
        self.e.gm.set_position(self.v, (8, 6), reason='actual ally position')
        foes = [self.foe('actual foe ' + str(i), pos, 10 + i) for i, pos in enumerate(((7, 5), (7, 6), (7, 7), (6, 7)))]
        self.combat(foes[0], count=40)
        for index, foe in enumerate(foes):
            if index:
                self.turn(foe, count=40 - index)
            self.away(foe, destination=(1, 1))
        self.assertEqual(self.p.spec[HU.OPPORTUNITY_USES], {'round':self.e.round_no, 'round_started':self.e.round_start_seconds, 'used':3})
        self.assertEqual(len([line for line in self.e.log_lines if '[기회 공격] ' + self.p.name in line]), 3)
        self.assertEqual(len([line for line in self.e.log_lines if '[기회 공격] ' + self.v.name in line]), 1)
        self.assertTrue(self.v.aoo_used)
        self.assertFalse(TURN.can_aoo(self.e, self.p))
        self.assertFalse(TURN.can_aoo(self.e, self.v))
        # A new round restores every limit.
        self.e.gm.set_position(foes[0], (7, 6), reason='actual return')
        self.next_round(foes[0], count=40)
        self.assertTrue(TURN.can_aoo(self.e, self.p))
        self.assertTrue(TURN.can_aoo(self.e, self.v))
        self.restore()
        self.valid()
        self.assertEqual(HU.opportunity_limit(self.e, self.p), 3)
        # Retraining the Feature ends the limit for the Pokemon too.
        self.retrain(HU.PACK_MASTER)
        self.retrain(HU.LOOK_AWAY)
        self.retrain(HU.REFLEXES)
        self.assertEqual((HU.opportunity_limit(self.e, self.t), HU.opportunity_limit(self.e, self.p)), (1, 1))

    def test_reflexes_count_the_hunters_own_attacks_as_adjacent_for_owned_teamwork_and_as_melee_for_owned_pack_hunt(self):
        self.setup(ally_ability='팀워크')             # v (not the Hunter's) also holds Teamwork beside q
        self.e.gm.set_position(self.v, (5, 2), reason='actual adjacent ally holder')
        ranged = self.e.r.move('move/전기쇼크')
        self.assertEqual(self.bonus(self.t, ranged), 0)
        self.whole()
        self.assertEqual(self.bonus(self.t, ranged), 2)                   # the Hunter's ranged attack: p's Teamwork
        self.e.gm.set_position(self.p, (8, 8), reason='actual departure')
        self.assertEqual(self.bonus(self.t, ranged), 0)                   # v's Teamwork is not the Hunter's Pokemon's
        self.assertEqual(self.bonus(self.b, ranged), 0)                   # another Trainer gains nothing
        self.e.gm.set_position(self.p, (3, 2), reason='actual return')
        self.assertEqual(self.bonus(self.p, ranged), 0)                   # the Pokemon's own ranged attack is not covered
        # Actual rolls: the Hunter's ranged attack from afar gets +2 over its own baseline.
        self.combat(self.t, count=30)
        self.use(self.t, self.q, 'move/전기쇼크', face=10)
        baseline = self.modifier(self.t) - 2
        self.retrain(HU.PACK_MASTER)
        self.retrain(HU.LOOK_AWAY)
        self.retrain(HU.REFLEXES)
        self.next_round(self.t, count=30)
        self.use(self.t, self.q, 'move/전기쇼크', face=10)
        self.assertEqual(self.modifier(self.t), baseline)
        self.valid()

    # ---------------------------------------------------------------- Pack Hunt (Ability consumer) and its trigger
    def test_pack_hunt_triggers_on_an_allys_melee_damage_to_the_adjacent_foe_and_the_free_ac5_attack_costs_a_tick(self):
        self.setup(ally_ability='무리사냥')            # v also holds Pack Hunt but stands away from q
        self.rejected(lambda:HU.pack_hunt(self.e, self.u), 'actual printed trigger')
        self.rejected(lambda:HU.pack_hunt(self.e, self.p), 'actual Pack Hunt Ability')
        self.combat(self.p, count=30)
        self.use(self.p, self.q, 'move/몸통박치기', face=15)
        record = HU.pack_hunt_trigger(self.u)
        self.assertEqual((record['ally_id'], record['foe_id'], record['move_id'], record['melee'], record['reflexes']),
                         (self.p.entity_id, self.q.entity_id, 'move/몸통박치기', True, False))
        self.assertIsNone(HU.pack_hunt_trigger(self.v))                   # not adjacent to the foe
        hp, ap = self.q.hp, list(getattr(self.u, '_action_history', []))
        with patch.object(Engine, 'd20', return_value=15):
            receipt = HU.pack_hunt(self.e, self.u)
        self.assertEqual((receipt['hit'], receipt['natural'], receipt['hp_before'] - receipt['hp_after']), (True, 15, self.e.tick(self.q)))
        self.assertEqual(self.q.hp, hp - self.e.tick(self.q))
        self.assertIn('AC 5+', self.accuracy_log(self.u)[-1])
        self.assertEqual(self.u._action_history, ap + ['free'])
        self.assertIsNone(HU.pack_hunt_trigger(self.u))
        self.assertIsNone(receipt['pack_master'])
        self.rejected(lambda:HU.pack_hunt(self.e, self.u), 'actual printed trigger')
        # A miss consumes the trigger without HP loss; the holder's own melee damage never triggers itself.
        self.turn(self.v, count=25)
        self.e.gm.set_position(self.v, (5, 2), reason='actual adjacent ally')
        self.use(self.v, self.q, 'move/몸통박치기', face=15)
        self.assertIsNotNone(HU.pack_hunt_trigger(self.u))
        self.assertIsNone(HU.pack_hunt_trigger(self.v))
        hp = self.q.hp
        with patch.object(Engine, 'd20', return_value=2):
            receipt = HU.pack_hunt(self.e, self.u)
        self.assertEqual((receipt['hit'], self.q.hp), (False, hp))
        # Ranged damage is not a melee attack; a lapsed trigger cannot be answered; the foe must still be adjacent.
        self.next_round(self.p, count=30)
        self.use(self.p, self.q, 'move/전기쇼크', face=15)
        self.assertIsNone(HU.pack_hunt_trigger(self.u))
        self.turn(self.v, count=18)
        self.use(self.v, self.q, 'move/몸통박치기', face=15)
        self.assertIsNotNone(HU.pack_hunt_trigger(self.u))
        self.restore()
        self.valid()
        self.assertIsNotNone(HU.pack_hunt_trigger(self.u))
        self.next_round(self.p, count=30)
        self.rejected(lambda:HU.pack_hunt(self.e, self.u), 'lapsed')
        self.use(self.p, self.q, 'move/몸통박치기', face=15)
        self.e.gm.set_position(self.u, (9, 9), reason='actual departure before answering')
        self.rejected(lambda:HU.pack_hunt(self.e, self.u), 'adjacent foe')

    # ---------------------------------------------------------------- Pack Master
    def test_pack_master_rewrites_teamwork_for_the_hunters_pokemon_and_buffs_after_a_pack_hunt_hit_until_the_next_turn_ends(self):
        self.whole()
        ranged = self.e.r.move('move/전기쇼크')
        # Teamwork of the Hunter's Pokemon now covers allies' non-melee attacks against the adjacent foe.
        self.assertEqual((self.bonus(self.v, ranged), self.bonus(self.b, ranged), self.bonus(self.u, ranged)), (2, 2, 2))
        other = self.foe('actual second foe', (8, 2), 12)
        self.assertEqual(self.bonus(self.v, ranged, target=other), 0)
        # A Pack Hunt hit: +2 accuracy and +5 damage against that foe until the end of the attacker's next turn.
        self.combat(self.p, count=30)
        self.use(self.p, self.q, 'move/몸통박치기', face=15)
        with patch.object(Engine, 'd20', return_value=15):
            receipt = HU.pack_hunt(self.e, self.u)
        self.assertTrue(receipt['pack_master'])
        self.assertEqual((HU.pack_master_bonus(self.e, self.u, self.q, 'accuracy'), HU.pack_master_bonus(self.e, self.u, self.q, 'damage')), (2, 5))
        self.assertEqual((HU.pack_master_bonus(self.e, self.u, other, 'accuracy'), HU.pack_master_bonus(self.e, self.p, self.q, 'accuracy')), (0, 0))
        self.restore()
        self.valid()
        self.assertEqual(len(HU.pack_master_records(self.u, self.q)), 1)
        # The actual attack by u against q carries both bonuses (accuracy log and damage roll modifier).
        self.turn(self.u, count=20)
        before = self.q.hp
        with patch.object(Engine, 'roll_damage', wraps=self.e.roll_damage) as damage:
            self.use(self.u, self.q, 'move/몸통박치기', face=10)
        self.assertIn('d20=10+4=14', self.accuracy_log(self.u)[-1])      # +2 Teamwork (p adjacent) +2 Pack Master
        self.assertTrue(any('데미지' in line and '+5' in line for line in self.e.log_lines[-12:]) or self.q.hp < before)
        # A second Pack Hunt hit replaces (never stacks) the bonus; the bonus ends with u's next turn.
        self.e.gm.set_position(self.v, (5, 2), reason='actual ally beside the foe')
        self.turn(self.v, count=18)
        self.use(self.v, self.q, 'move/몸통박치기', face=15)
        with patch.object(Engine, 'd20', return_value=15):
            HU.pack_hunt(self.e, self.u)
        self.assertEqual(HU.pack_master_bonus(self.e, self.u, self.q, 'accuracy'), 2)
        self.assertEqual(len(HU.pack_master_records(self.u, self.q)), 1)
        self.next_round(self.u, count=30)
        self.assertEqual(HU.pack_master_bonus(self.e, self.u, self.q, 'accuracy'), 2)
        self.e.end_of_turn(self.u)
        self.assertEqual(HU.pack_master_records(self.u), [])
        self.valid()
        # The Hunter's own Pack Hunt (class choice) earns the Hunter the same bonus; retraining Pack Master ends it.
        self.setup(pack=('팀워크', '팀워크'))
        self.whole(branch='ability/무리사냥')
        self.e.gm.set_position(self.t, (5, 3), reason='actual Hunter beside the foe')
        self.combat(self.p, count=30)
        self.use(self.p, self.q, 'move/몸통박치기', face=15)
        with patch.object(Engine, 'd20', return_value=15):
            receipt = HU.pack_hunt(self.e, self.t)
        self.assertTrue(receipt['hit'] and receipt['pack_master'])
        self.assertEqual(HU.pack_master_bonus(self.e, self.t, self.q, 'damage'), 5)
        self.retrain(HU.PACK_MASTER)
        self.assertEqual(HU.pack_master_records(self.t), [])
        self.valid()

    # ---------------------------------------------------------------- Don't Look Away
    def test_dont_look_away_answers_an_opportunity_hit_by_the_hunter_or_a_pack_pokemon_once_per_round(self):
        self.setup(ally_ability='팀워크')
        self.e.gm.set_position(self.v, (5, 1), reason='actual ally beside the foe')
        self.e.gm.set_position(self.t, (5, 3), reason='actual Hunter beside the foe')
        self.whole()
        self.rejected(lambda:HU.dont_look_away(self.e, self.t), 'actual printed trigger')
        ap = AP.available(self.t)
        self.combat(self.q, count=30)
        self.away(self.q)
        # p (Teamwork), u (Pack Hunt), the Hunter and v (another Trainer's Teamwork Pokemon) all hit; the last Hunter-side hit is pending.
        hits = [line for line in self.e.log_lines if '[기회 공격]' in line]
        self.assertEqual(len(hits), 4)
        record = HU.look_away_trigger(self.t)
        self.assertEqual((record['round'], record['target_id']), (self.e.round_no, self.q.entity_id))
        self.assertIn(record['attacker_id'], {self.p.entity_id, self.u.entity_id, self.t.entity_id})
        hp = self.q.hp
        receipt = HU.dont_look_away(self.e, self.t)
        self.assertEqual((receipt['hp_before'] - receipt['hp_after'], receipt['slowed'], AP.available(self.t)), (self.e.tick(self.q), True, ap - 1))
        self.assertIn('둔화', self.q.conditions)
        self.assertEqual(self.q.hp, hp - self.e.tick(self.q))
        self.assertEqual(self.t._action_history[-1], 'free')
        self.assertIsNone(HU.look_away_trigger(self.t))
        self.restore()
        self.valid()
        # Once per round: another hit this round records a trigger that cannot be answered until the next round.
        self.e.gm.set_position(self.q, (4, 2), reason='actual return')
        self.turn(self.v, count=20)
        self.e.gm.set_position(self.v, (9, 9), reason='actual ally away')
        self.turn(self.p, count=18)
        self.e.gm.set_position(self.p, (3, 2), reason='actual pack position')
        foe = self.foe('actual second foe', (3, 3), 9)
        self.turn(foe, count=10)
        self.away(foe, destination=(1, 8))
        self.assertIsNotNone(HU.look_away_trigger(self.t))
        self.rejected(lambda:HU.dont_look_away(self.e, self.t), 'already triggered this round')
        # The Slow lasts one round: it ends at the same initiative count of the next round.
        self.next_round(self.q, count=30)
        self.assertNotIn('둔화', self.q.conditions)
        self.rejected(lambda:HU.dont_look_away(self.e, self.t), 'lapsed')
        # Only the Hunter and their Pokemon with Pack Hunt or Teamwork record the trigger.
        self.e.gm.set_position(self.p, (9, 8), reason='actual pack away')
        self.e.gm.set_position(self.u, (9, 7), reason='actual pack away')
        self.e.gm.set_position(self.t, (9, 6), reason='actual Hunter away')
        self.e.gm.set_position(self.v, (5, 1), reason='actual ally holder beside the foe')
        self.e.gm.set_position(self.q, (4, 2), reason='actual return')
        self.t.spec.pop(HU.LOOK_AWAY_TRIGGER, None)
        self.away(self.q)
        self.assertTrue(any('[기회 공격] ' + self.v.name in line for line in self.e.log_lines[-12:]))
        self.assertIsNone(HU.look_away_trigger(self.t))
        # Without AP the answer is refused and the trigger stays; retraining the Feature discards it.
        self.e.gm.set_position(self.q, (4, 2), reason='actual return')
        self.e.gm.set_position(self.t, (5, 3), reason='actual Hunter beside the foe')
        self.next_round(self.q, count=30)
        self.away(self.q)
        self.assertIsNotNone(HU.look_away_trigger(self.t))
        AP.charge(self.t, AP.available(self.t))
        self.rejected(lambda:HU.dont_look_away(self.e, self.t), 'requires 1 AP')
        self.retrain(HU.PACK_MASTER)
        self.retrain(HU.LOOK_AWAY)
        self.assertIsNone(HU.look_away_trigger(self.t))
        self.valid()


if __name__ == '__main__':
    unittest.main()
