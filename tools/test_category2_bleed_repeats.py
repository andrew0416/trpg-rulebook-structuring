"""Bleed uses actual weapon admission and the shared target-turn repeat owner."""
from pathlib import Path
from unittest.mock import patch
import json, sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'engine'), str(ROOT/'tools')]
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import turn as TURN
import combat_timing as TIME
import effect_lifetime_policy as POLICY
from state_codec import StateCodecError

MOVE = 'move/출혈'


class BleedRepeatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='core')

    def world(self, pokemon=False, equip=True):
        e = Engine(self.rules, 521)
        stats = dict.fromkeys(('hp','atk','def','spa','spd','spe'), 20)
        stats['hp'] = 100
        a = Combatant(self.rules, build_trainer(self.rules, 'Bleed weapon user', 30,
            stats, pos=(1,1), side='party'))
        a.spec['skills']['전투'] = '달인'
        if pokemon:
            spec = build_pokemon(self.rules, '피죤', 60, moves=[], abilities=[],
                pos=(2,1), side='wild')
        else:
            spec = build_trainer(self.rules, 'Bleed target', 30, stats,
                pos=(2,1), side='wild')
        b = Combatant(self.rules, spec)
        c = Combatant(self.rules, build_trainer(self.rules, 'other target', 30,
            stats, pos=(2,2), side='wild'))
        for actor in (a,b,c):
            e.gm.add_combatant(actor)
        if equip:
            TURN.equip_weapon(e,a,{'name':'Bleed blade','kind':'소형 근접무기',
                'grade':'좋음','moves':['출혈']})
        e.start_round(e.everyone)
        e.start_of_turn(a, initiative_count=30)
        return e,a,b,c

    def hit(self,e,a,b):
        with patch.object(e,'d20',return_value=10):
            return e.use_move(a,b,MOVE,set_damage=True)

    def target_start(self,e,b):
        e.start_of_turn(b,initiative_count=20)

    def next_round(self,e,a,b):
        e.end_of_turn(b)
        e.end_round()
        e.start_round(e.everyone)
        e.start_of_turn(a,initiative_count=30)
        e.end_of_turn(a)
        self.target_start(e,b)

    def records(self,b):
        return [r for r in TIME.records(b) if r.get('source')==MOVE]

    def test_native_weapon_hit_defers_exactly_three_ticks_to_actual_target_starts(self):
        for pokemon in (False,True):
            with self.subTest(pokemon=pokemon):
                e,a,b,c = self.world(pokemon)
                before = b.hp
                damage = self.hit(e,a,b)
                self.assertGreater(damage,0)
                self.assertEqual(b.hp,before-damage)
                self.assertEqual(a.budget['standard'],0)
                self.assertEqual(a.move_uses[MOVE],1)
                self.assertEqual(len(self.records(b)),1)
                self.assertEqual(self.records(b)[0]['lifetime_deliveries'],[])
                self.assertIs(self.records(b)[0]['lifetime_actor'],a)
                self.assertIs(self.records(b)[0]['lifetime_target'],b)
                self.assertFalse(self.records(a));self.assertFalse(self.records(c))
                e.end_of_turn(a)
                after_attack = b.hp
                tick = e.tick(b)
                self.target_start(e,b)
                self.assertEqual(b.hp,after_attack-tick)
                POLICY.boundary(e,'turn_start',b)
                self.assertEqual(b.hp,after_attack-tick)
                self.next_round(e,a,b)
                self.assertEqual(b.hp,after_attack-2*tick)
                self.next_round(e,a,b)
                self.assertEqual(b.hp,after_attack-3*tick)
                self.assertFalse(self.records(b))
                history = b.custom_conditions['effect_lifetime_history'][-1]
                self.assertEqual((history['source'],history['state']),(MOVE,'consumed'))
                self.assertEqual(len(history['deliveries']),3)
                self.next_round(e,a,b)
                self.assertEqual(b.hp,after_attack-3*tick)

    def test_miss_pays_native_action_and_scene_frequency_without_repeat_state(self):
        e,a,b,c = self.world()
        before = b.hp
        with patch.object(e,'d20',return_value=1):
            self.assertEqual(e.use_move(a,b,MOVE,set_damage=True),0)
        self.assertEqual((a.budget['standard'],a.move_uses[MOVE]),(0,1))
        self.assertEqual(b.hp,before)
        self.assertFalse(self.records(b))
        e.end_of_turn(a);self.target_start(e,b)
        self.assertEqual(b.hp,before)

    def test_unrelated_turns_and_elapsed_seconds_do_not_consume_target_ticks(self):
        e,a,b,c = self.world();self.hit(e,a,b)
        before = b.hp
        e.end_of_turn(a)
        e.start_of_turn(c,initiative_count=25);e.end_of_turn(c)
        e.advance_time(1)
        self.assertEqual(b.hp,before)
        self.assertEqual(self.records(b)[0]['lifetime_deliveries'],[])
        self.target_start(e,b)
        self.assertEqual(b.hp,before-e.tick(b))

    def test_second_native_hit_retains_independent_remaining_delivery_counts(self):
        e,a,b,c = self.world();self.hit(e,a,b);e.end_of_turn(a)
        self.target_start(e,b)
        # Scene x2 retains its native one-round gap between the two uses.
        self.next_round(e,a,b)
        e.end_of_turn(b);e.end_round();e.start_round(e.everyone)
        e.start_of_turn(a,initiative_count=30);self.hit(e,a,b)
        self.assertEqual(sorted(len(r['lifetime_deliveries']) for r in self.records(b)),[0,2])
        self.assertEqual(a.move_uses[MOVE],2)
        e.end_of_turn(a);before=b.hp;tick=e.tick(b);self.target_start(e,b)
        self.assertEqual(b.hp,before-2*tick)
        self.next_round(e,a,b)
        self.assertEqual(len(self.records(b)),1)
        self.assertEqual(len(self.records(b)[0]['lifetime_deliveries']),2)
        self.next_round(e,a,b)
        self.assertFalse(self.records(b))
        self.assertEqual(len([x for x in b.custom_conditions['effect_lifetime_history'] if x['source']==MOVE]),2)

    def test_gm_and_json_restore_continue_third_tick_with_same_actual_participants(self):
        e,a,b,c=self.world();self.hit(e,a,b);e.end_of_turn(a)
        self.target_start(e,b);self.next_round(e,a,b)
        e.gm.snapshot('two Bleed deliveries')
        n=Engine.import_state(self.rules,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        actors={x.entity_id:x for x in n.everyone};na,nb=actors[a.entity_id],actors[b.entity_id]
        self.assertIs(self.records(nb)[0]['lifetime_actor'],na)
        self.assertIs(self.records(nb)[0]['lifetime_target'],nb)
        before=b.hp;tick=e.tick(b)
        self.next_round(e,a,b);self.assertEqual(b.hp,before-tick)
        e.gm.restore('two Bleed deliveries')
        self.assertEqual(b.hp,before)
        self.assertIs(self.records(b)[0]['lifetime_actor'],a)
        self.next_round(e,a,b);self.assertEqual(b.hp,before-tick)
        self.next_round(n,na,nb);self.assertEqual(nb.hp,before-tick)
        self.assertFalse(self.records(b));self.assertFalse(self.records(nb))

    def test_weapon_ownership_is_required_before_payment_or_accuracy(self):
        e,a,b,c=self.world(equip=False)
        e.gm.set_move(a,MOVE,True,'independent move does not provide an actual weapon')
        before=(a.budget.copy(),a.move_uses.copy(),b.hp,e.rng.getstate())
        with self.assertRaises(ValueError):e.use_move(a,b,MOVE,set_damage=True)
        self.assertEqual(before,(a.budget,a.move_uses,b.hp,e.rng.getstate()))
        self.assertFalse(self.records(b))

    def test_forged_remaining_count_or_delivery_is_rejected_without_loading(self):
        for field in ('times','delivery'):
            with self.subTest(field=field):
                e,a,b,c=self.world();self.hit(e,a,b)
                record=self.records(b)[0]
                if field=='times':record[POLICY.KEY]['repeat']['times']=4
                else:record['lifetime_deliveries'].append({'event':'turn_start','token':(0,b.entity_id,0),'receipt':object()})
                with self.assertRaises(StateCodecError):e.export_state()
                with self.assertRaises(ValueError):e.gm.snapshot('forged Bleed')


if __name__=='__main__':unittest.main()
