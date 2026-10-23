"""Action activation and equipment/rewind invariants; source ch07 action economy and ch09 held items."""
import hashlib,json,sys,unittest
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import test_frequencies as _fixture_test_frequencies
import test_reference_rules as _fixture_test_reference_rules
from engine import Combatant
import items as ITEMS

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture_test_frequencies.FrequencyTests.setUpClass();_fixture_test_reference_rules.ReferenceRuleTests.setUpClass()
    def area(self):
        e,a,b,m=_fixture_test_frequencies.FrequencyTests().fixture()
        second=deepcopy(a.spec);second.pop('id',None);second['name']='second'
        c=Combatant(e.r,second)
        e.targets_in_range=lambda *args:[b,c]
        e.everyone=e.gm.everyone=[a,b,c]
        return e,a,b,c,m
    def plate(self):
        e,a,b=_fixture_test_reference_rules.ReferenceRuleTests().fixture('물방울플레이트')
        e.everyone=e.gm.everyone=[a,b]
        return e,a,b
    def dr(self,a):
        return ITEMS.item_damage_reduction(a,{'type':'물','class':'물리'})
    def test_exhausted_action_rejects_entire_area(self):
        e,a,b,c,m=self.area();a.budget={'standard':0,'shift':1,'swift':1}
        e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(0,0));self.assertEqual(a.move_uses,{})
    def test_area_setup_does_not_activate_on_secondary_target(self):
        e,a,b,c,m=self.area()
        e.r.moves_mech[m]['effects'].insert(0,{'type':'set_up_move','setup':[]})
        e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(0,0));self.assertEqual(a.setup_move,m)
    def test_area_miss_still_allows_second_target_and_counts_once(self):
        e,a,b,c,m=self.area()
        e.r.moves[m].update(range='원거리',ac=2)
        e.accuracy_check=lambda attacker,target,*args,**kwargs:(target is c,10,False)
        e.use_move_on(a,b,m,[a,b,c])
        self.assertEqual((b.injuries,c.injuries),(0,1));self.assertEqual(a.move_uses[m],1)
    def test_rewind_equipped_then_remove_clears_effects(self):
        e,a,b=self.plate();e.gm.snapshot()
        ITEMS.unregister_item(e,a);e.gm.restore()
        self.assertEqual(self.dr(a),15)
        ITEMS.unregister_item(e,a);self.assertEqual(self.dr(a),0)
    def test_rewind_before_equipping_removes_registration(self):
        e,a,b=self.plate();ITEMS.unregister_item(e,a);e.gm.snapshot()
        ITEMS.register_item(e,a,'물방울플레이트');e.gm.restore()
        self.assertEqual(self.dr(a),0)
        ITEMS.register_item(e,a,'물방울플레이트');self.assertEqual(self.dr(a),15)
    def test_rewind_restores_action_budget_and_absent_pending_loss(self):
        e,a,b=self.plate();a.budget={'standard':1,'shift':1,'swift':1};e.gm.snapshot()
        a.budget['standard']=0;a.pending_action_loss={'standard':1}
        e.gm.restore()
        self.assertEqual(a.budget['standard'],1)
        self.assertFalse(getattr(a,'pending_action_loss',None))
    def test_rewind_preserves_snapshot_on_repeated_restore(self):
        e,a,b=self.plate();e.gm.snapshot()
        for _ in range(2):
            e.gm.restore();ITEMS.unregister_item(e,a);self.assertEqual(self.dr(a),0)
    def test_item_alias_does_not_stack(self):
        e,a,b=self.plate()
        ITEMS.register_item(e,a,'item/물방울플레이트')
        self.assertEqual(self.dr(a),15)
    def test_item_alias_can_remove_same_item(self):
        e,a,b=self.plate()
        ITEMS.unregister_item(e,a,'item/물방울플레이트')
        self.assertEqual(self.dr(a),0)
    def test_gm_item_replacement_replaces_passives(self):
        e,a,b=self.plate()
        e.gm.set_item(a,'불구슬플레이트')
        self.assertEqual(self.dr(a),0)
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),15)
        e.gm.set_item(a,None)
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),0)

    def potion(self):
        e,a,b=self.plate()
        a.item=None;a.spec['items']={'상처약':2}
        a.budget={'standard':1,'shift':1,'swift':1}
        a.hp-=30;b.hp-=30
        return e,a,b
    def test_self_heal_without_shift_is_atomic(self):
        e,a,b=self.potion();a.budget['shift']=0
        before=(a.hp,dict(a.budget),dict(a.spec['items']))
        e.use_item(a,'상처약',a)
        self.assertEqual((a.hp,a.budget,a.spec['items']),before)
    def test_self_heal_without_standard_is_atomic(self):
        e,a,b=self.potion();a.budget['standard']=0
        before=(a.hp,dict(a.budget),dict(a.spec['items']))
        e.use_item(a,'상처약',a)
        self.assertEqual((a.hp,a.budget,a.spec['items']),before)
    def test_self_heal_uses_full_action_but_no_future_loss(self):
        e,a,b=self.potion();hp=a.hp
        e.use_item(a,'상처약',a)
        self.assertEqual(a.hp,hp+20)
        self.assertEqual(a.budget,{'standard':0,'shift':0,'swift':1})
        self.assertFalse(getattr(a,'pending_action_loss',None))
        self.assertEqual(a.spec['items']['상처약'],1)
    def test_recipient_refusal_is_atomic(self):
        e,a,b=self.potion();before=(b.hp,dict(a.budget),dict(a.spec['items']))
        e.use_item(a,'상처약',b,accepted=False)
        self.assertEqual((b.hp,a.budget,a.spec['items']),before)
        self.assertFalse(getattr(b,'pending_action_loss',None))
    def test_medic_canonical_edge_id_prevents_recipient_loss(self):
        e,a,b=self.potion();a.spec['edges']=['edge/메딕-훈련'];a.spec.setdefault('skills',{})['의학']=3;hp=b.hp
        e.use_item(a,'상처약',b)
        self.assertEqual(b.hp,hp+20)
        self.assertFalse(getattr(b,'pending_action_loss',None))
    def test_other_heal_penalty_applies_only_next_turn(self):
        e,a,b=self.potion();e.use_item(a,'상처약',b)
        e.start_of_turn(b)
        self.assertEqual(b.budget,{'standard':0,'shift':1,'swift':0})
        e.start_of_turn(b)
        self.assertEqual(b.budget,{'standard':1,'shift':1,'swift':1})

    def test_trainer_cannot_stack_two_accessories(self):
        e,a,b=self.plate()
        ITEMS.register_item(e,a,'불구슬플레이트')
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),0)
        self.assertEqual(self.dr(a),15)
    def test_accessory_slot_released_after_removal(self):
        e,a,b=self.plate();ITEMS.unregister_item(e,a)
        ITEMS.register_item(e,a,'불구슬플레이트')
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),15)
    def test_different_trainer_slots_can_coexist(self):
        e,a,b=self.plate();ITEMS.register_item(e,a,'방화복')
        self.assertEqual(self.dr(a),15)
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),10)
    def test_pokemon_only_one_held_item_even_different_trainer_slots(self):
        e,a,b=self.plate();a.kind='pokemon'
        with self.assertRaisesRegex(ValueError,'held-item slot'):ITEMS.register_item(e,a,'방진고글')
        self.assertNotIn('가루',getattr(a,'keyword_immune',set()))
    def test_generic_brace_without_type_never_grants_global_dr(self):
        e,a,b=_fixture_test_reference_rules.ReferenceRuleTests().fixture('타입깁스')
        self.assertEqual(a.damage_reduction,0)
        for ty in ITEMS.TYPES:
            self.assertEqual(ITEMS.item_damage_reduction(a,{'type':ty,'class':'물리'}),0)

    def test_alternative_slot_uses_free_head_with_occupied_accessory(self):
        e,a,b=self.plate();ITEMS.register_item(e,a,'방진고글')
        self.assertIn('가루',a.keyword_immune)
        self.assertEqual(self.dr(a),15)
    def test_two_slot_equipment_blocks_both_head_and_body(self):
        e,a,b=self.plate();ITEMS.register_item(e,a,'방역복')
        ITEMS.register_item(e,a,'방화복');ITEMS.register_item(e,a,'방진고글')
        self.assertEqual(ITEMS.item_damage_reduction(a,{'type':'불꽃','class':'물리'}),0)
        self.assertNotIn('가루',getattr(a,'keyword_immune',set()))

    def test_unconscious_item_user_cannot_heal_even_free(self):
        for hp,conds in [(0,set()),(10,{'기절'})]:
            e,a,b=self.potion();a.hp=hp;a.conditions=conds;before=(b.hp,dict(a.spec['items']))
            e.use_item(a,'상처약',b,free=True)
            self.assertEqual((b.hp,a.spec['items']),before)
    def test_unconscious_user_cannot_move(self):
        from grid import Grid
        for hp,conds in [(0,set()),(10,{'기절'})]:
            e,a,b=self.potion();e.grid=Grid(10,10);a.pos=(0,0);b.pos=(5,0);a.hp=hp;a.conditions=conds
            before=dict(a.budget);e.approach(a,b)
            self.assertEqual(a.pos,(0,0));self.assertEqual(a.budget,before)
    def test_unconscious_user_cannot_throw_ball(self):
        for hp,conds in [(0,set()),(10,{'기절'})]:
            e,a,b=self.potion();a.hp=hp;a.conditions=conds;b.side='wild'
            e.accuracy_check=lambda *args:(_ for _ in ()).throw(AssertionError('must not roll'))
            e.throw_ball(a,b)
            self.assertFalse(b.captured)
    def test_capture_without_standard_cannot_roll(self):
        e,a,b=self.potion();b.side='wild';b.kind=b.spec['kind']='pokemon';a.spec['items']['몬스터볼']=1;a.pos=(0,0);b.pos=(1,0);a.budget['standard']=0
        e.accuracy_check=lambda *args:(_ for _ in ()).throw(AssertionError('must not roll'))
        e.throw_ball(a,b);self.assertFalse(b.captured)
    def test_missed_capture_still_costs_standard(self):
        e,a,b=self.potion();b.side='wild';b.kind=b.spec['kind']='pokemon';a.spec['items']['몬스터볼']=1;a.pos=(0,0);b.pos=(1,0)
        self.assertFalse(e.throw_ball(a,b,fixed_accuracy=1));self.assertEqual(a.budget['standard'],0)

if __name__=='__main__':
    class RecordedResult(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='STATE-'+t._testMethodName,status='pass'))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='STATE-'+t._testMethodName,status='fail'))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='STATE-'+t._testMethodName,status='error'))
    r=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests))
    paths=[p for folder,pat in [('engine','*.py'),('data','*.json')] for p in (ROOT/folder).glob(pat)]
    paths += [ROOT/'tools/synthetic_rule_fixture.py',ROOT/'tools/mechanize_items.py',Path(__file__),ROOT/'tools/test_frequencies.py',ROOT/'tools/test_reference_rules.py',ROOT/'input/ch05-pokemon.md',ROOT/'input/ch07-combat.md',ROOT/'input/ch09-equipment.md']
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),scope='Area activation, item identity and GM state lifecycle only.',results=r.rows,input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (ROOT/'output/state-lifecycle-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if r.wasSuccessful() else 1)
