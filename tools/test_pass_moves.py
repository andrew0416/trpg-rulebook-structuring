"""Actual paid Pass movement with native creature and real material recipients."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Engine
from grid import Grid
import test_physical_object_attacks as BASE
import physical_object_attacks as OBJECTS
import world_entities as WORLD
import movement_actions as MOVEMENT
import move_activation as ACTIVATION
import pass_moves as PASS
import turn as TURN


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):BASE.Tests.setUpClass();cls.base=BASE.Tests()

    def fixture(self,name='풀베기',ropes=True,creature=True):
        e,a,b,mid,door=self.base.fixture(name)
        e.grid=Grid(12,8);b.side='foe';b.pos=(2,0) if creature else (9,7)
        WORLD.observe_location(e,e._physical_objects[door],{'kind':'grid','cell':(9,0)},reason='door outside path')
        adjudications={}
        if ropes:
            for uid,cell in [('rope1',(1,0)),('rope2',(3,0))]:
                WORLD.register_object(e,uid,location={'kind':'grid','cell':cell},reason='actual rope',
                    kind='item_instance',item_rule_id='item/단단한-로프')
                e.configure_rope(a,uid,length_feet=25,reason='actual sturdy rope')
                adjudications[uid]={'hit':True,'damage_before_dr':35}
        return e,a,b,mid,adjudications

    def execute(self,e,a,mid,adjudications,destination=(4,0),event='pass/1'):
        return e.use_pass_move(a,mid,destination,event_id=event,object_adjudications=adjudications,
            source='gm/observed-object-hits',reason='actual Pass object hits and pre-DR damage')

    def test_cut_moves_attacks_all_real_targets_once_breaks_rope_and_pays_once_without_aoo(self):
        e,a,b,mid,adjudications=self.fixture();hp=b.hp
        with patch.object(TURN,'trigger_aoo',wraps=TURN.trigger_aoo) as aoo:
            row=self.execute(e,a,mid,adjudications)
            aoo.assert_not_called()
        self.assertEqual(a.pos,(4,0));self.assertEqual(row['distance'],4)
        self.assertEqual(row['targets'],[['object','rope1'],['creature',b.entity_id],['object','rope2']])
        self.assertLess(b.hp,hp);self.assertEqual(a.move_uses[mid],1)
        self.assertEqual((a.budget['standard'],a.budget['shift']),(0,0))
        self.assertEqual(a._action_history.count('standard'),1);self.assertEqual(a._action_history.count('shift'),1)
        for uid in adjudications:
            obj=e._physical_objects[uid];self.assertTrue(WORLD.physical_lifecycle(obj)['destroyed'])
            self.assertEqual(len(obj[OBJECTS.FIELD]['attacks']),1)
            self.assertTrue(obj[OBJECTS.FIELD]['attacks'][0]['material_policy']['ignore_all_dr'])
        completion=e._move_completions[row['completion_id']]
        self.assertEqual(completion['phase'],'complete');self.assertEqual(completion['started'],[b.entity_id])
        self.assertFalse(e.approach(a,b,1));self.assertEqual(a.pos,(4,0));self.base.valid(e)

    def test_slash_retains_rope_dr_and_real_misses_still_pay_move_and_movement(self):
        e,a,b,mid,adjudications=self.fixture('베어가르기',creature=False)
        adjudications['rope1']={'hit':False,'damage_before_dr':0}
        row=self.execute(e,a,mid,adjudications)
        self.assertEqual(e._physical_objects['rope1'][OBJECTS.FIELD]['hp'],30)
        self.assertEqual(e._physical_objects['rope2'][OBJECTS.FIELD]['hp'],15)
        self.assertEqual([r['dealt'] for r in row['results']],[0,15])
        self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.pos,(4,0));self.base.valid(e)

    def test_large_native_body_is_only_attacked_once_across_multiple_traversed_cells(self):
        e,a,b,mid,adjudications=self.fixture(ropes=False);b.pos=(1,0);b.spec['size']='대형'
        row=self.execute(e,a,mid,adjudications)
        self.assertEqual(row['targets'],[['creature',b.entity_id]])
        self.assertEqual(e._move_completions[row['completion_id']]['started'],[b.entity_id])
        self.base.valid(e)

    def test_actual_empty_path_uses_move_and_stops_at_endpoint(self):
        e,a,b,mid,adjudications=self.fixture(ropes=False,creature=False)
        row=self.execute(e,a,mid,adjudications)
        self.assertEqual(row['targets'],[]);self.assertIsNone(row['completion_id'])
        self.assertEqual(a.pos,(4,0));self.assertEqual(a.move_uses[mid],1);self.base.valid(e)

    def test_two_creatures_share_one_native_completion_and_keep_individual_accuracy(self):
        from engine import Combatant
        from builder import build_trainer
        e,a,b,mid,adj=self.fixture(ropes=False);b.pos=(1,0)
        third=Combatant(e.r,build_trainer(e.r,'third',10,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),
            abilities=[],moves=[mid],pos=(3,0)))
        third.side='foe';e.everyone.append(third)
        calls=[];original=Engine.accuracy_check
        def observe(staged,attacker,target,*args,**kw):
            calls.append(target.entity_id)
            return original(staged,attacker,target,*args,**kw)
        with patch.object(Engine,'accuracy_check',observe):row=self.execute(e,a,mid,adj)
        self.assertEqual(calls,[b.entity_id,third.entity_id]);self.assertEqual(a.move_uses[mid],1)
        self.assertEqual(e._move_completions[row['completion_id']]['started'],[b.entity_id,third.entity_id])
        self.base.valid(e)

    def test_cut_bypasses_only_five_dr_on_ordinary_objects_and_creatures_but_all_rope_dr(self):
        import effects_ext as EXT
        e,a,b,mid,adj=self.fixture(ropes=False);b.damage_reduction=20
        _,move,mm,policy=OBJECTS._move(e,a,mid)
        defense,reduction=EXT.defense_hook(e,a,b,move,mm,'def')
        self.assertEqual(reduction,15);self.assertEqual(defense,b.staged('def'))
        WORLD.observe_location(e,e._physical_objects['door'],{'kind':'grid','cell':(1,0)},reason='ordinary object on Pass path')
        row=self.execute(e,a,mid,{'door':{'hit':True,'damage_before_dr':12}})
        self.assertEqual(e._physical_objects['door'][OBJECTS.FIELD]['hp'],8)
        self.assertEqual(e._physical_objects['door'][OBJECTS.FIELD]['attacks'][0]['calculation']['after_defense'],12)
        self.assertEqual(EXT.reduction_after_ignore(20,[{'type':'ignore_defense_modifiers','ignore':['damage reduction']}]),0)
        self.assertEqual(EXT.reduction_after_ignore(3,mm['effects_exec']),0)
        self.base.valid(e)

    def test_invalid_path_endpoint_complete_target_set_and_budget_reject_atomically(self):
        for failure in ('too-far','not-straight','wall','endpoint','missing','extra','shift','standard','allied-body','unknown-object'):
            e,a,b,mid,adjudications=self.fixture();dest=(4,0)
            if failure=='too-far':dest=(5,0)
            if failure=='not-straight':dest=(4,1)
            if failure=='wall':e.grid.walls.add(((0,0),(1,0)))
            if failure=='endpoint':dest=(2,0)
            if failure=='missing':adjudications.pop('rope2')
            if failure=='extra':adjudications['door']={'hit':True,'damage_before_dr':1}
            if failure=='shift':a.budget['shift']=0
            if failure=='standard':a.budget['standard']=0
            if failure=='allied-body':b.side=a.side
            if failure=='unknown-object':
                WORLD.register_object(e,'new-object',location={'kind':'grid','cell':(2,0)},reason='unprofiled actual object')
            before=e.export_state();rng=e.rng.getstate();objects={uid:obj for uid,obj in e._physical_objects.items()}
            with self.assertRaises(ValueError,msg=failure):self.execute(e,a,mid,adjudications,dest)
            self.assertEqual(e.export_state(),before,failure);self.assertEqual(e.rng.getstate(),rng)
            for uid,obj in objects.items():self.assertIs(e._physical_objects[uid],obj)

    def test_diagonal_distance_uses_existing_alternating_steps_and_slow_terrain(self):
        e,a,b,mid,adj=self.fixture(ropes=False,creature=False)
        row=self.execute(e,a,mid,adj,destination=(3,3))
        self.assertEqual(row['distance'],4);self.assertEqual(a._diagonal_steps,3)
        e,a,b,mid,adj=self.fixture(ropes=False,creature=False);a._diagonal_steps=1
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'four metres'):self.execute(e,a,mid,adj,destination=(3,3))
        self.assertEqual(e.export_state(),before)
        e,a,b,mid,adj=self.fixture(ropes=False,creature=False);e.grid.slow.add((1,0))
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'four metres'):self.execute(e,a,mid,adj)
        self.assertEqual(e.export_state(),before)

    def test_public_free_flags_fake_activation_and_direct_pass_cannot_bypass_path(self):
        e,a,b,mid,adj=self.fixture();before=e.export_state()
        for call in (lambda:e.use_move(a,b,mid),lambda:e.use_move_on(a,b,mid,[a,b]),
                     lambda:self.base.attack(e,a,mid,'rope1'),
                     lambda:MOVEMENT.follow_paid_path(e,a,[(1,0)],mode='land',maximum_distance=4,pass_scope={}),
                     lambda:ACTIVATION.open_scope(e,a,mid,[b],shared=False,_prepaid={}).__enter__()):
            with self.assertRaises(ValueError):call()
            self.assertEqual(e.export_state(),before)

    def test_failed_native_recipient_rolls_back_earlier_movement_object_damage_rng_and_costs(self):
        e,a,b,mid,adj=self.fixture();before=e.export_state();rng=e.rng.getstate()
        original=Engine.use_move
        def fail_after_native(staged,*args,**kw):
            original(staged,*args,**kw)
            raise ValueError('actual native recipient failed')
        with patch.object(Engine,'use_move',fail_after_native):
            with self.assertRaisesRegex(ValueError,'recipient failed'):self.execute(e,a,mid,adj)
        self.assertEqual(e.export_state(),before);self.assertEqual(e.rng.getstate(),rng)

    def test_complete_receipts_replay_restore_and_validate_cross_owner_integrity(self):
        e,a,b,mid,adj=self.fixture();row=self.execute(e,a,mid,adj);before=e.export_state()
        self.assertEqual(self.execute(e,a,mid,adj),row);self.assertEqual(e.export_state(),before)
        changed=deepcopy(adj);changed['rope1']['damage_before_dr']+=1
        with self.assertRaisesRegex(ValueError,'conflicts'):self.execute(e,a,mid,changed)
        self.assertEqual(e.export_state(),before)
        e.gm.snapshot('pass');e.end_of_turn(a);e.gm.restore('pass',reason='restore actual paid Pass')
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())))
        actor=WORLD.actor_index(loaded)[a.entity_id];self.assertEqual(actor.pos,(4,0));self.base.valid(loaded)
        self.assertEqual(self.execute(loaded,actor,mid,adj),row)
        loaded._pass_moves['pass/1']['distance']=99
        self.assertFalse(loaded.validate_state()['valid'])
        with self.assertRaises(ValueError):Engine.import_state(e.r,json.loads(json.dumps(loaded.export_state())))


if __name__=='__main__':unittest.main()
