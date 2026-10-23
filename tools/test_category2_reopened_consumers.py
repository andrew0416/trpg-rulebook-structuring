"""Previously waiting clauses through their actual paid move and state consumers."""
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
from grid import Grid
from state_codec import dump_engine, load_engine
import combat_timing as TIME
import combat_stage_sources as STAGES
import coat_effects as COATS
import move_completion as COMPLETE
import custom_condition_effects as CUSTOM
import effects as FX
import effects_ext as EXT
import state_grants as GRANTS


class ReopenedConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rules(ROOT, ruleset='core')

    def world(self, moves, *, types=(), kind='trainer'):
        e = Engine(self.r, 901)
        e.grid = Grid(12, 12)
        def actor(name, pos, side, known=(), actor_types=(), pokemon=False):
            if pokemon:
                spec = build_pokemon(self.r, '피카츄', 40, moves=list(known),
                                     abilities=[], pos=pos, side=side,
                                     extra={'name': name, 'types': list(actor_types)})
            else:
                spec = build_trainer(self.r, name, 30,
                    {'hp': 100, 'atk': 20, 'def': 20, 'spa': 20, 'spd': 20, 'spe': 20},
                    moves=list(known), pos=pos, side=side,
                    extra={'types': list(actor_types), 'abilities': []})
            value = Combatant(self.r, spec)
            e.gm.add_combatant(value)
            return value
        a = actor('source', (2, 3), 'party', moves, types, kind == 'pokemon')
        b = actor('first', (3, 3), 'enemy')
        c = actor('second', (3, 4), 'enemy')
        outside = actor('outside', (10, 10), 'enemy')
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=30)
        return e, a, b, c, outside

    def next_turn(self, e, actor):
        e.end_of_turn(e._active_turn_actor)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(actor, initiative_count=30)

    def cast(self, e, a, target, mid, *, face=10, area=False):
        with patch.object(e, 'd20', return_value=face):
            if area:
                return e.use_move_on(a, target, mid, e.everyone)
            return e.use_move(a, target, mid)

    def restored(self, e):
        return load_engine(self.r, json.loads(json.dumps(dump_engine(e))))

    def test_native_area_type_removal_follows_all_damage_and_exact_owner_boundary(self):
        for mid, original, lost, expected in (
            ('move/불사르기', ['불꽃'], '불꽃', ['노말']),
            ('move/전광쌍격', ['전기', '풀'], '전기', ['풀']),
        ):
            for kind in ('trainer', 'pokemon'):
                with self.subTest(move=mid, kind=kind):
                    e, a, b, c, _ = self.world([mid], types=original, kind=kind)
                    if lost == '전기':
                        e.gm.set_position(c, (4, 3), reason='actual second close-blast target')
                    real_damage = e.roll_damage
                    observed = []
                    def damage(user, target, move, *args, **kwargs):
                        observed.append((target.entity_id, list(user.types)))
                        return real_damage(user, target, move, *args, **kwargs)
                    before = b.hp, c.hp
                    with patch.object(e, 'roll_damage', side_effect=damage):
                        self.cast(e, a, b, mid, area=True)
                    self.assertEqual(observed, [(b.entity_id, original), (c.entity_id, original)])
                    self.assertLess(b.hp, before[0]); self.assertLess(c.hp, before[1])
                    self.assertEqual(a.types, expected)
                    self.assertEqual(a.move_uses[mid], 1)
                    self.assertEqual(a.budget['standard'], 0)
                    self.assertEqual(len(TIME.records(a)), 1)
                    n = self.restored(e); user, first = n.everyone[:2]
                    n.end_of_turn(user); n.start_of_turn(first, initiative_count=20)
                    self.assertEqual(user.types, expected)
                    if lost == '전기':
                        self.next_turn(n, user)
                    else:
                        n.end_encounter(n.everyone)
                    self.assertEqual(user.types, original)
                    self.assertFalse(TIME.records(user))

    def test_native_type_loss_is_after_use_including_all_misses(self):
        for mid, original, expected in (
            ('move/불사르기', ['불꽃'], ['노말']),
            ('move/전광쌍격', ['전기'], []),
        ):
            with self.subTest(move=mid):
                e, a, b, c, _ = self.world([mid], types=original)
                before = b.hp, c.hp
                self.cast(e, a, b, mid, face=1, area=True)
                self.assertEqual((b.hp, c.hp), before)
                self.assertEqual(a.types, expected)
                self.assertEqual(len(TIME.records(a)), 1)
                row = list(e._move_completions.values())[-1]
                self.assertEqual(row['phase'], 'complete')
                before = dump_engine(e)
                COMPLETE.refresh(e, row['id'])
                self.assertEqual(dump_engine(e), before)

    def test_non_electric_user_has_no_electric_removal_source(self):
        e, a, b, _, _ = self.world(['move/전광쌍격'], types=['풀'])
        self.cast(e, a, b, 'move/전광쌍격', area=True)
        self.assertEqual(a.types, ['풀'])
        self.assertFalse(TIME.records(a))

    def test_after_use_declaration_cannot_replace_actual_completion_producer(self):
        for mid, types in (('move/불사르기', ['불꽃']),
                           ('move/전광쌍격', ['전기']),
                           ('move/마지막수단', ['노말'])):
            for forged_flag in (False, True):
                with self.subTest(move=mid, after_all_targets=forged_flag):
                    e, a, b, *_ = self.world([mid], types=types)
                    effect = next(x for x in self.r.move_mech(mid)[0]['effects_exec']
                                  if x.get('on') == 'after use')
                    def state():
                        return (e.rng.getstate(), json.dumps(dict(types=a.types,
                            counters=a.counters, budget=a.budget, uses=a.move_uses,
                            timing=TIME.records(a)), sort_keys=True))
                    before = state()
                    result = FX.run_effects(e, a, b, [effect], dict(engine=e,
                        attacker=a, target=b, move=self.r.move(mid), hit=True,
                        after_all_targets=forged_flag), mid)
                    self.assertEqual(result.pending[0].status, 'condition_unknown')
                    self.assertEqual(state(), before)

    def test_native_sports_reach_each_real_burst_target_and_consume_independently(self):
        for mid, attack in (('move/흙놀이', 'move/전기쇼크'),
                            ('move/물놀이', 'move/불꽃세례')):
            with self.subTest(move=mid):
                e, a, b, c, outside = self.world([mid, attack])
                self.cast(e, a, b, mid, area=True)
                self.assertEqual([len(COATS.live(x)) for x in (a,b,c,outside)], [0,1,1,0])
                for holder in (b,c):
                    self.assertEqual(COATS.live(holder)[0]['effect_instance']['applied_by_actor_id'], a.entity_id)
                n = self.restored(e); user, first, second = n.everyone[:3]
                before = dump_engine(n)
                for _ in range(2):
                    self.assertLess(EXT.effectiveness_hook(n,user,first,self.r.move(attack),{},1,{}), 1)
                self.assertEqual(dump_engine(n), before)
                self.next_turn(n,user)
                self.cast(n,user,first,attack)
                self.assertFalse(COATS.live(first)); self.assertEqual(len(COATS.live(second)),1)
                self.assertEqual(first.spec['effect_instance_history'][-1]['effect_instance']['state'],'consumed')

    def test_water_sport_learning_grant_exists_without_casting_and_ends_on_forgetting(self):
        for kind in ('trainer', 'pokemon'):
            with self.subTest(kind=kind):
                e,a,*_ = self.world(['move/물놀이'],kind=kind)
                self.assertIn('물줄기', GRANTS.effective_capabilities(a))
                self.assertFalse(a.move_uses)
                e.gm.set_move(a,'move/물놀이',add=False,reason='actual forgotten move')
                self.assertNotIn('물줄기', GRANTS.effective_capabilities(a))

    def test_tar_shot_native_cone_keeps_speed_loss_after_its_coat_is_consumed(self):
        e,a,b,c,outside = self.world(['move/타르샷','move/불꽃세례'])
        e.gm.set_position(c,(4,3),reason='actual second cone target')
        self.cast(e,a,b,'move/타르샷',area=True)
        self.assertEqual((b.stages['spe'],c.stages['spe'],outside.stages['spe']),(-1,-1,0))
        self.assertEqual((len(COATS.live(b)),len(COATS.live(c))),(1,1))
        n=self.restored(e);user,first,second=n.everyone[:3]
        self.next_turn(n,user); self.cast(n,user,first,'move/불꽃세례')
        self.assertFalse(COATS.live(first));self.assertEqual(len(COATS.live(second)),1)
        self.assertEqual((first.stages['spe'],second.stages['spe']),(-1,-1))

    def test_native_tar_shot_consumes_on_matching_hit_even_if_final_damage_is_zero(self):
        e,a,b,*_ = self.world(['move/타르샷','move/불꽃세례'])
        self.cast(e,a,b,'move/타르샷',area=True)
        self.next_turn(e,a); hp=b.hp
        with patch.object(e,'roll_damage',return_value=0):
            self.cast(e,a,b,'move/불꽃세례')
        self.assertEqual(b.hp,hp)
        self.assertFalse(COATS.live(b))
        self.assertEqual(b.stages['spe'],-1)

    def test_native_stockpile_cap_zero_and_other_stage_sources_survive_json(self):
        e,a,*_ = self.world(['move/비축하기','move/꿀꺽'])
        STAGES.add_base(a,'independent','def',2,source='observed/other',ends='explicit_revoke')
        for i in range(4):
            if i:
                self.next_turn(e,a);self.next_turn(e,a)
            self.cast(e,a,a,'move/비축하기')
            value=min(i+1,3)
            self.assertEqual((a.counters['stockpile'],a.stages['def'],a.stages['spd']),(value,2+value,value))
        n=self.restored(e);user=n.everyone[0]
        self.next_turn(n,user);self.cast(n,user,user,'move/꿀꺽')
        self.assertEqual((user.counters['stockpile'],user.stages['def'],user.stages['spd']),(0,2,0))
        self.restored(n)

    def test_resistance_coats_require_positive_actual_damage_and_preserve_misses(self):
        for mid,attack in (('move/흙놀이','move/전기쇼크'),('move/물놀이','move/불꽃세례')):
            with self.subTest(move=mid):
                e,a,b,*_=self.world([mid,attack])
                self.cast(e,a,b,mid,area=True)
                self.next_turn(e,a)
                with patch.object(e,'roll_damage',return_value=0):self.cast(e,a,b,attack)
                self.assertEqual(len(COATS.live(b)),1)
                self.next_turn(e,a);self.next_turn(e,a)
                self.cast(e,a,b,attack,face=1)
                self.assertEqual(len(COATS.live(b)),1)

    def test_native_trump_card_reads_previous_count_and_increments_after_actual_damage(self):
        e,a,b,*_ = self.world(['move/마지막수단'])
        real_damage=e.roll_damage;observed=[]
        def damage(user,target,move,*args,**kwargs):
            observed.append((user.counters.get('last_resort',0),e.damage_base(user,move,target=target)))
            return real_damage(user,target,move,*args,**kwargs)
        with patch.object(e,'roll_damage',side_effect=damage):
            self.cast(e,a,b,'move/마지막수단')
        self.assertEqual(observed,[(0,6)]);self.assertEqual(a.counters['last_resort'],1)
        n=self.restored(e);user,first=n.everyone[:2]
        self.next_turn(n,user);self.next_turn(n,user)
        self.assertEqual(n.damage_base(user,self.r.move('move/마지막수단'),target=first),8)
        self.cast(n,user,first,'move/마지막수단')
        self.assertEqual(user.counters['last_resort'],2)

    def test_salt_cure_native_holder_turn_current_types_and_actual_recall(self):
        e,a,b,*_ = self.world(['move/소금절이'])
        self.cast(e,a,b,'move/소금절이')
        self.assertEqual(len(CUSTOM.records(b)),1)
        before=b.hp;e.end_of_turn(a);e.start_of_turn(b,initiative_count=20)
        self.assertEqual(b.hp,before-e.tick(b))
        n=self.restored(e);user,holder=n.everyone[:2]
        n.gm.set_types(holder,['물','강철'],reason='actual current double-vulnerable types')
        before=holder.hp;self.next_turn(n,holder)
        self.assertEqual(holder.hp,before-2*n.tick(holder))
        n.gm.recall(holder,reason='actual volatile-ending recall')
        self.assertFalse(CUSTOM.records(holder));self.assertNotIn('소금절이',holder.conditions)
        self.restored(n)


if __name__ == '__main__':
    unittest.main()
