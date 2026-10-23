"""Real environmental results share actual Move costs and physical identity."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
from engine import Engine,Combatant
from builder import build_pokemon
import test_category2_csv_item_transfers as BASE
import physical_combustion as FIRE
import physical_object_attacks as HP
import world_entities as W


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):BASE.Tests.setUpClass();cls.base=BASE.Tests()

    def fixture(self,name='화염방사',combustible=True,species=None,observed=True):
        e,trainer,b,mid=self.base.fixture(name,held=(None,None))
        a=trainer
        if species:
            a=Combatant(e.r,build_pokemon(e.r,species,30,moves=[mid],abilities=[],pos=(0,0),
                extra={'trainer_id':trainer.entity_id,'loyalty':2}))
            e.everyone=e.gm.everyone=[trainer,b,a]
        else:e.everyone=e.gm.everyone=[a,b]
        uid='environment/forest'
        W.register_object(e,uid,location={'kind':'grid','cell':(1,0)},reason='actual forest at observed location')
        if observed:e.observe_object_combustion(a,uid,combustible=combustible,source='gm/actual-forest-material',reason='GM observes exposed actual material')
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        return e,a,b,mid,uid

    def ignite(self,e,a,mid,uid,event='fire/1',hit=True,ignite=True):
        return e.ignite_physical_object(a,uid,mid,event_id=event,hit=hit,ignite=ignite,
            source='gm/actual-fire-contact',reason='GM adjudicates ignition of this actual environment')

    def valid(self,e):
        result=e.validate_state();self.assertTrue(result['valid'],result['issues'])

    def test_actual_charizard_ignites_forest_without_fictitious_hp_and_pays_native_move(self):
        e,a,b,mid,uid=self.fixture(species='리자몽');obj=e._physical_objects[uid]
        row=self.ignite(e,a,mid,uid)
        self.assertEqual(e.object_fire_state(uid),dict(object_id=uid,burning=True,ignition_ids=['fire/1']))
        self.assertNotIn(HP.FIELD,obj);self.assertNotIn('hp',obj)
        self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],0)
        self.assertEqual(row['intent']['actor_id'],a.entity_id);self.assertIs(obj,e._physical_objects[uid]);self.valid(e)

    def test_actual_conkeldurr_door_and_pikachu_server_reuse_hp_destruction_owner(self):
        for species,name,uid in [('노보청','엄청난힘','environment/door'),('피카츄','전기쇼크','environment/server')]:
            with self.subTest(species=species):
                e,a,b,mid,unused=self.fixture(name,species=species)
                W.register_object(e,uid,location={'kind':'grid','cell':(1,0)},reason='actual source example object')
                e.configure_object_durability(a,uid,max_hp=5,reduction=3,minimum_damage=0,source='gm/actual-example-profile',reason='GM observes this particular object')
                row=e.attack_physical_object(a,uid,mid,event_id='break/1',hit=True,damage_before_dr=9,source='gm/actual-hit',reason='actual nonliving source example')
                self.assertEqual(row['hp_after'],0);self.assertTrue(W.physical_lifecycle(e._physical_objects[uid])['destroyed'])
                self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],0)
                if name=='엄청난힘':self.assertEqual((a.stages['atk'],a.stages['def']),(-1,-1))
                self.valid(e)

    def test_miss_nonigniting_hit_and_noncombustible_material_pay_without_fire(self):
        for combustible,hit in [(True,False),(True,True),(False,True)]:
            e,a,b,mid,uid=self.fixture(combustible=combustible)
            self.ignite(e,a,mid,uid,hit=hit,ignite=False)
            self.assertFalse(e.object_fire_state(uid)['burning']);self.assertEqual(a.move_uses[mid],1);self.assertEqual(a.budget['standard'],0);self.valid(e)

    def test_material_source_range_cost_ownership_and_conflicting_event_refuse_atomically(self):
        for case in ('unobserved','noncombustible','nonfire','range','cost','obedience','unknown','miss'):
            with self.subTest(case=case):
                e,a,b,mid,uid=self.fixture(name='전기쇼크' if case=='nonfire' else '화염방사',combustible=case!='noncombustible',observed=case!='unobserved',species='리자몽' if case=='obedience' else None)
                if case=='range':W.observe_location(e,e._physical_objects[uid],{'kind':'grid','cell':(10,0)},reason='actual distant forest')
                if case=='cost':a.budget['standard']=0
                if case=='obedience':a.spec['loyalty']=1
                if case=='unknown':mid=e.r.move_id('불꽃세례')
                before=e.export_state()
                with self.assertRaises(ValueError):self.ignite(e,a,mid,uid,hit=case!='miss')
                self.assertEqual(e.export_state(),before)
        e,a,b,mid,uid=self.fixture();first=self.ignite(e,a,mid,uid);before=e.export_state()
        self.assertEqual(self.ignite(e,a,mid,uid),first);self.assertEqual(e.export_state(),before)
        with self.assertRaises(ValueError):self.ignite(e,a,mid,uid,ignite=False)
        self.assertEqual(e.export_state(),before)

    def test_fire_survives_scene_and_explicit_extinction_preserves_other_ignitions(self):
        e,a,b,mid,uid=self.fixture('불꽃세례');self.ignite(e,a,mid,uid)
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        self.ignite(e,a,mid,uid,'fire/2');e.end_of_turn(a);e.end_scene([a,b],round_elapsed_seconds=10)
        self.assertEqual(e.object_fire_state(uid)['ignition_ids'],['fire/1','fire/2'])
        kw=dict(event_id='extinction/1',ignition_ids=['fire/1'],source='gm/observed-rain-result',reason='GM observes one affected source extinguished')
        first=e.observe_fire_extinguished(a,uid,**kw);before=e.export_state()
        self.assertEqual(e.observe_fire_extinguished(a,uid,**kw),first);self.assertEqual(e.export_state(),before)
        self.assertEqual(e.object_fire_state(uid)['ignition_ids'],['fire/2'])
        with self.assertRaises(ValueError):e.observe_fire_extinguished(a,uid,**dict(kw,event_id='extinction/2'))
        self.assertEqual(e.export_state(),before)
        e.observe_fire_extinguished(a,uid,**dict(kw,event_id='extinction/2',ignition_ids=['fire/2']))
        self.assertFalse(e.object_fire_state(uid)['burning']);self.valid(e)

    def test_gm_json_restore_and_replay_keep_same_fire_without_repaying(self):
        e,a,b,mid,uid=self.fixture();row=self.ignite(e,a,mid,uid);e.gm.snapshot('actual-fire')
        e.observe_fire_extinguished(a,uid,event_id='out/1',ignition_ids=['fire/1'],source='gm/x',reason='observed extinguished')
        e.gm.restore('actual-fire',reason='restore actual ignition')
        self.assertTrue(e.object_fire_state(uid)['burning'])
        loaded=Engine.import_state(e.r,json.loads(json.dumps(e.export_state())));aa=W.actor_index(loaded)[a.entity_id]
        before=loaded.export_state();self.assertEqual(self.ignite(loaded,aa,mid,uid),row);self.assertEqual(loaded.export_state(),before);self.valid(loaded)

    def test_late_outcome_failure_rolls_back_cost_frequency_identity_and_rng(self):
        e,a,b,mid,uid=self.fixture();before=e.export_state();obj=e._physical_objects[uid];real=FIRE._record
        def fail(rows,key,payload):
            real(rows,key,payload);raise ValueError('late environmental outcome failure')
        with patch.object(FIRE,'_record',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late environmental'):self.ignite(e,a,mid,uid)
        self.assertIs(e._physical_objects[uid],obj);self.assertEqual(e.export_state(),before)
        self.ignite(e,a,mid,uid);self.valid(e)

    def test_no_material_reset_historical_corruption_or_hp_event_collision(self):
        e,a,b,mid,uid=self.fixture('불꽃세례');self.ignite(e,a,mid,uid);before=e.export_state()
        with self.assertRaises(ValueError):e.observe_object_combustion(a,uid,combustible=False,source='gm/changed',reason='reclassify')
        self.assertEqual(e.export_state(),before)
        e.end_of_turn(a);e.start_round([a,b]);e.start_of_turn(a,initiative_count=20)
        e.configure_object_durability(a,uid,max_hp=5,reduction=0,minimum_damage=0,source='gm/hp',reason='actual separate durability observation')
        before=e.export_state()
        with self.assertRaisesRegex(ValueError,'identity'):
            e.attack_physical_object(a,uid,mid,event_id='fire/1',hit=True,damage_before_dr=1,source='gm/x',reason='same event cannot pay twice')
        self.assertEqual(e.export_state(),before)
        e.attack_physical_object(a,uid,mid,event_id='hp/1',hit=True,damage_before_dr=6,source='gm/x',reason='actual destruction')
        self.assertFalse(e.object_fire_state(uid)['burning']);self.valid(e)
        e._physical_objects[uid][FIRE.FIELD]['attacks']['fire/1']['intent']['ignite']=False
        self.assertFalse(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
