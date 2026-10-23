"""Confusion through actual paid object, weapon, ignition and whole Pass owners."""
from copy import deepcopy
import json,random,unittest
from unittest.mock import patch
import test_physical_object_attacks as BASE
import test_pass_moves as PASS_TEST
import test_physical_tool_attacks as TOOL_TEST
import test_physical_combustion as FIRE_TEST
import confusion_attacks as CONFUSION
import physical_object_attacks as OBJECTS
import physical_combustion as FIRE
import world_entities as W
import temporary_hp as TEMP
from engine import Engine


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        BASE.Tests.setUpClass();PASS_TEST.Tests.setUpClass();TOOL_TEST.Tests.setUpClass();FIRE_TEST.Tests.setUpClass()
        cls.base=BASE.Tests();cls.pass_test=PASS_TEST.Tests();cls.tool_test=TOOL_TEST.Tests();cls.fire_test=FIRE_TEST.Tests()

    def confuse(self,e,a):e.apply_status(a,'혼란');e.rng.seed(1)

    def test_paid_object_hit_miss_and_self_stage_share_actual_loss_and_temporary_hp(self):
        for name,hit in (('화염방사',True),('화염방사',False),('엄청난힘',True)):
            with self.subTest(name=name,hit=hit):
                e,a,b,mid,uid=self.base.fixture(name);self.confuse(e,a);TEMP.grant(e,a,3);hp=a.hp
                row=self.base.attack(e,a,mid,uid,hit=hit,damage=12 if hit else 0)
                loss=a.staged('atk' if name=='엄청난힘' else 'spa')//2
                self.assertEqual(row['confusion']['face'],1);self.assertEqual(row['confusion']['result']['amount'],loss)
                self.assertEqual((a.hp,a.temp_hp),(hp-max(0,loss-3),max(0,3-loss)))
                self.assertEqual((a.budget['standard'],a.move_uses[mid]),(0,1))
                if name=='엄청난힘':self.assertEqual(a.stages['atk'],-1)
                self.assertEqual(e._physical_objects[uid][OBJECTS.FIELD]['attacks'][-1]['confusion'],row['confusion'])
                self.base.valid(e)

    def test_actual_weapon_and_ignition_use_same_confusion_consumer(self):
        e,a,b,key,rope,tool=self.tool_test.fixture();self.confuse(e,a);hp=a.hp
        row=self.tool_test.attack(e,a,rope,tool)
        self.assertEqual(row['confusion']['face'],1);self.assertEqual(hp-a.hp,a.staged('atk')//2)
        self.assertEqual(row['applied_damage'],2);self.tool_test.valid(e)
        e,a,b,mid,uid=self.fire_test.fixture(species='리자몽');self.confuse(e,a);hp=a.hp
        row=self.fire_test.ignite(e,a,mid,uid)
        self.assertTrue(e.object_fire_state(uid)['burning']);self.assertEqual(hp-a.hp,a.staged('spa')//2)
        self.assertEqual(e._physical_objects[uid][FIRE.FIELD]['attacks'][row['event_id']]['confusion'],row['confusion'])
        self.fire_test.valid(e)

    def test_whole_pass_draws_once_for_mixed_objects_only_and_empty_paths(self):
        for ropes,creature in ((True,True),(True,False),(False,False)):
            with self.subTest(ropes=ropes,creature=creature):
                e,a,b,mid,adj=self.pass_test.fixture(ropes=ropes,creature=creature);self.confuse(e,a);hp=a.hp
                draws=[];original=random.Random.randint
                def observe(rng,lo,hi):
                    value=original(rng,lo,hi)
                    if (lo,hi)==(1,2):draws.append(value)
                    return value
                with patch.object(random.Random,'randint',observe):row=self.pass_test.execute(e,a,mid,adj)
                self.assertEqual(draws,[1]);self.assertEqual(a.pos,(4,0));self.assertEqual(hp-a.hp,a.staged('atk')//2)
                self.assertEqual((a.budget['standard'],a.budget['shift'],a.move_uses[mid]),(0,0,1))
                if creature:
                    child=e._move_completions[row['completion_id']]
                    self.assertNotIn('confusion',child)
                    self.assertEqual(child['confusion_parent'],{'producer':'pass','event_id':row['event_id']})
                for obj in e._physical_objects.values():
                    for receipt in obj.get(OBJECTS.FIELD,{}).get('attacks',[]):self.assertNotIn('confusion',receipt)
                self.base.valid(e)

    def test_pass_late_confusion_failure_rolls_back_path_all_recipients_costs_and_rng(self):
        e,a,b,mid,adj=self.pass_test.fixture();self.confuse(e,a);before=e.export_state()
        original=CONFUSION.finish_native
        def fail(*args,**kw):original(*args,**kw);raise ValueError('late parent self-loss')
        with patch.object(CONFUSION,'finish_native',fail):
            with self.assertRaisesRegex(ValueError,'late parent'):self.pass_test.execute(e,a,mid,adj)
        self.assertEqual(e.export_state(),before)
        self.assertEqual(self.pass_test.execute(e,a,mid,adj)['confusion']['face'],1)

    def test_completed_object_and_pass_replay_survive_both_restores_without_self_hit(self):
        for kind in ('object','pass'):
            with self.subTest(kind=kind):
                if kind=='object':
                    e,a,b,mid,uid=self.base.fixture(hp=5)
                    execute=lambda world,actor:self.base.attack(world,actor,mid,uid)
                else:
                    e,a,b,mid,adj=self.pass_test.fixture()
                    execute=lambda world,actor:self.pass_test.execute(world,actor,mid,adj)
                self.confuse(e,a);first=execute(e,a);snapshot=e.gm.snapshot();saved=e.export_state()
                e.lose_hp(a,1);e.gm.restore(snapshot)
                for world in (e,Engine.import_state(e.r,json.loads(json.dumps(saved,ensure_ascii=False)))):
                    actor=W.actor_index(world)[a.entity_id];before=world.export_state()
                    self.assertEqual(execute(world,actor),first);self.assertEqual(world.export_state(),before)
                    self.base.valid(world)

    def test_refused_other_conditions_and_tampered_parent_link_are_not_admitted(self):
        e,a,b,mid,uid=self.base.fixture();self.confuse(e,a);e.apply_status(a,'잠듦');before=e.export_state()
        with self.assertRaisesRegex(ValueError,'conditions'):self.base.attack(e,a,mid,uid)
        self.assertEqual(e.export_state(),before)
        e,a,b,mid,adj=self.pass_test.fixture();self.confuse(e,a);row=self.pass_test.execute(e,a,mid,adj)
        child=e._move_completions[row['completion_id']]
        child['confusion_parent']['event_id']='foreign'
        self.assertFalse(e.validate_state()['valid'])
        child['confusion_parent']['event_id']=row['event_id'];self.base.valid(e)

    def test_native_creature_child_cannot_lose_its_parent_observation(self):
        import pass_moves as PASS
        e,a,b,mid,adj=self.pass_test.fixture(ropes=False);self.confuse(e,a)
        row=self.pass_test.execute(e,a,mid,adj);self.base.valid(e)
        parent=getattr(e,PASS.KEY).pop(row['event_id'])
        self.assertFalse(e.validate_state()['valid'])
        getattr(e,PASS.KEY)[row['event_id']]=parent;self.base.valid(e)


if __name__=='__main__':unittest.main()
