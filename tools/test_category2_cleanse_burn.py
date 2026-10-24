"""C09-087 native burn boundaries and the affected actual consumers."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,unittest
ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
import test_category2_cleanse_tags as _fixture_test_category2_cleanse_tags
from engine import Rules
from grid import Grid
import cleanse_tags as TAG,cleanse_tag_burn as B,state_grants as G
import invisibility_state as V,world_entities as W,state_codec as CODEC
import skill_feature_actions as SF,common_checks as C


class BurnTests(unittest.TestCase):
    actor=_fixture_test_category2_cleanse_tags.CleanseTagTests.actor
    craft=_fixture_test_category2_cleanse_tags.CleanseTagTests.craft
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        _fixture_test_category2_cleanse_tags.CleanseTagTests.setUp(self)
        self.b=self.actor('expert-user','trainer');self.b.spec['skills']['오컬트학']=5
        self.e.everyone=[self.a,self.b,self.p,self.q];self.e.gm.everyone=self.e.everyone
        for c,pos in ((self.a,(1,1)),(self.b,(2,1)),(self.p,(3,1)),(self.q,(4,1))):
            c.pos=pos;c.spec.update(size='Medium',movement={'land':6},capabilities=[])
            c.spec['skills']['집중']=4
        self.p.spec['capabilities']=['Invisibility','Phasing','Teleporter']
        self.e.grid=Grid(90,90)
        self.craft();self.place('tag:one')
    def place(self,uid):W.observe_location(self.e,self.e._physical_objects[uid],{'kind':'grid','cell':list(self.b.pos)},reason='GM observed real tag within user reach')
    def burn(self,*,event='actual-burn',engine=None,actor=None,tag='tag:one',checks=None):
        if checks is None:checks={self.p.entity_id:{'fixed':[2,2,3,3]}}
        e=engine or self.e
        choice=None if B.KEY in e._physical_objects[tag] else dict(value='english_both_inclusive',
            reason='These existing native controls explicitly exercise the English both-required and inclusive-tie rule',scope=B.source_choices(e)['decision_scope'])
        return e.gm.observe_cleanse_burn(actor or self.b,tag,event_id=event,reason='GM observed this actual original tag burned by this user',checks=checks,source_choice=choice)
    def validate(self,e=None):
        e=e or self.e
        return CODEC.dump_engine(e)
    def restore(self):
        e=CODEC.load_engine(Rules(str(ROOT),ruleset='core'),json.loads(json.dumps(self.validate())))
        B.validate_world(e,W.actor_index(e));return e,W.actor_index(e)
    def loss(self,c=None):return next(iter(G.capability_losses(c or self.p)))
    def test_original_other_user_equal_focus_both_loss_and_native_receipts(self):
        profile=deepcopy(self.e._physical_objects['tag:one'][TAG.PROFILE]);budget=deepcopy(getattr(self.b,'budget',None))
        row=self.burn();self.assertEqual(row['power'],10)
        self.assertEqual(row['targets'][self.p.entity_id]['result'],{'total':10,'lost':True})
        self.assertEqual(G.effective_capabilities(self.p),['Teleporter'])
        obj=self.e._physical_objects['tag:one'];self.assertEqual(obj[TAG.PROFILE],profile)
        self.assertEqual(obj['destroyed']['by_actor_id'],self.b.entity_id);self.assertEqual(getattr(self.b,'budget',None),budget)
        options=row['targets'][self.p.entity_id]['skill_options'];self.assertEqual(SF.event(self.e,self.p,options['roll_id']).final.total,10)
        self.validate()
        before=self.validate()
        with self.assertRaises(ValueError):self.burn()
        with self.assertRaises(ValueError):TAG.level(self.e,'tag:one')
        self.assertEqual(self.validate(),before)
    def test_less_equal_greater_real_focus_and_exact_aliases(self):
        for faces,lost in (([2]*4,True),([2,2,3,3],True),([3]*4,False)):
            self.setUp();self.p.spec['capabilities']=['capability/투명','통과','Teleporter','Phasing Extra']
            row=self.burn(checks={self.p.entity_id:{'fixed':faces}})
            self.assertEqual(row['targets'][self.p.entity_id]['result']['lost'],lost)
            self.assertEqual(G.effective_capabilities(self.p),['Teleporter','Phasing Extra'] if lost else self.p.spec['capabilities'])
    def test_30m_boundary_all_kinds_both_required_no_wall_exception(self):
        for c in (self.a,self.b,self.p,self.q):c.spec['capabilities']=[]
        self.a.spec['capabilities']=['Invisibility','Phasing'];self.a.pos=(32,1)
        self.p.spec['capabilities']=['Invisibility','Phasing'];self.p.pos=(33,1)
        self.q.spec['capabilities']=['Phasing'];self.e.grid.walls.add(((2,1),(3,1)))
        row=self.burn(checks={self.a.entity_id:{'fixed':[2,2,3,3]}})
        self.assertEqual(list(row['targets']),[self.a.entity_id]);self.assertEqual(G.effective_capabilities(self.a),[])
        self.assertEqual(G.effective_capabilities(self.p),['Invisibility','Phasing']);self.assertEqual(G.effective_capabilities(self.q),['Phasing'])
        self.setUp();self.p.spec['capabilities']=['Invisibility'];self.assertEqual(self.burn(checks={})['targets'],{})
    def test_invalid_rank_original_access_source_options_are_atomic(self):
        cases=[lambda:self.b.spec['skills'].__setitem__('오컬트학',4),lambda:W.observe_location(self.e,self.e._physical_objects['tag:one'],{'kind':'grid','cell':[80,80]},reason='far object'),
            lambda:self.e._physical_objects['tag:one'][TAG.PROFILE].__setitem__('level',99)]
        for change in cases:
            self.setUp();change();before=deepcopy((self.e.rng.getstate(),self.e._physical_objects,self.b.spec,self.p.spec))
            with self.assertRaises(ValueError):self.burn()
            self.assertEqual((self.e.rng.getstate(),self.e._physical_objects,self.b.spec,self.p.spec),before)
        self.setUp()
        for options in ({'total':0},{'fixed':[7]*4},{'roll_id':'fake'}):
            before=self.validate()
            with self.assertRaises(ValueError):self.burn(checks={self.p.entity_id:options})
            self.assertEqual(self.validate(),before)
        native=self.rules._selected_rule
        with patch.object(self.rules,'_selected_rule',side_effect=lambda uid,**kw:'other' if uid==TAG.ITEM else native(uid,**kw)):
            with self.assertRaises(ValueError):self.burn()
        self.assertIsInstance(self.burn(checks={}),C.PendingDecision);self.assertNotIn('destroyed',self.e._physical_objects['tag:one'])
    def test_multi_target_observed_failure_resume_same_burn_same_first_dice(self):
        self.q=self.actor('z-target','trainer');self.q.pos=(4,1)
        self.q.spec.update(size='Medium',movement={'land':6},capabilities=['Invisibility','Phasing'])
        self.e.everyone[3]=self.q
        self.q.spec['feats']=[SF.MONKEY];self.q.spec['skills'].update({'전투':4,'집중':4,'육상':4})
        checks={self.p.entity_id:{'fixed':[2,2,3,3]},self.q.entity_id:dict(fixed=[3]*4,feature=SF.MONKEY,feature_options={'decision':lambda first:None})}
        with self.assertRaisesRegex(ValueError,'boolean'):self.burn(checks=checks)
        row=self.e._physical_objects['tag:one'][B.KEY];self.assertEqual(row['status'],'pending')
        first=SF.event(self.e,self.p,row['targets'][self.p.entity_id]['skill_options']['roll_id'])
        self.assertEqual(first.state,'final');self.assertIn('destroyed',self.e._physical_objects['tag:one'])
        e,index=self.restore();before=e.rng.getstate()
        checks[self.q.entity_id]['feature_options']={'decision':lambda first:False}
        result=self.burn(engine=e,actor=index[self.b.entity_id],checks=checks)
        self.assertEqual(result['status'],'complete');self.assertEqual(e.rng.getstate(),before)
        self.assertEqual(SF.event(e,index[self.p.entity_id],row['targets'][self.p.entity_id]['skill_options']['roll_id']).first,first.first)
        self.assertEqual(G.effective_capabilities(index[self.p.entity_id]),['Teleporter'])
        self.assertEqual(G.effective_capabilities(index[self.q.entity_id]),['Invisibility','Phasing'])
        self.validate(e)
    def test_299_300_and_live_baseline_grants_learning_contributions(self):
        G.grant(self.p,'capabilities','Invisibility','independent-invisibility','fixture')
        self.burn();self.e.advance_time(299);self.assertEqual(G.effective_capabilities(self.p),['Teleporter'])
        G.set_baseline(self.p,'capabilities',['Phasing','Teleporter','NewBaseline'])
        G.grant(self.p,'capabilities','투명','new-grant','fixture');G.revoke(self.p,'independent-invisibility')
        G.grant_moves(self.p,['move/물대포'],'learned-water','fixture')
        self.assertEqual(G.effective_capabilities(self.p),['Teleporter','NewBaseline','물줄기'])
        self.e.advance_time(1);self.assertEqual(G.effective_capabilities(self.p),['Phasing','Teleporter','NewBaseline','투명','물줄기'])
        G.revoke(self.p,'learned-water');self.assertNotIn('물줄기',G.effective_capabilities(self.p))
        self.assertNotIn('Invisibility',G.effective_capabilities(self.p));self.validate()
    def test_independent_losses_expire_separately_and_do_not_restore_snapshots(self):
        self.burn();self.e.advance_time(100)
        G.transition(self.e,self.p,lambda e,c:G.capability_loss(e,c,'other-loss',['Invisibility','Phasing'],rule_id='fixture/independent',receipt='actual-other-source',duration=300))
        self.e.advance_time(200);self.assertEqual(G.effective_capabilities(self.p),['Teleporter'])
        self.e.advance_time(99);self.assertEqual(G.effective_capabilities(self.p),['Teleporter'])
        self.e.advance_time(1);self.assertEqual(G.effective_capabilities(self.p),['Invisibility','Phasing','Teleporter'])
        self.validate()
    def test_unknown_partial_round_preserved_and_actual_observation_resolves(self):
        self.burn();self.e.advance_time(295);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=10);self.e.end_encounter()
        row=G.capability_losses(self.p)[self.loss()];self.assertEqual(row['elapsed_bounds'],[295,305])
        with self.assertRaisesRegex(ValueError,'observe actual'):G.effective_capabilities(self.p)
        e,index=self.restore();p=index[self.p.entity_id]
        with self.assertRaises(ValueError):G.effective_capabilities(p)
        with self.assertRaises(ValueError):B.observe_loss_elapsed(e,p,self.loss(p),306,reason='outside')
        e.gm.observe_cleanse_loss_elapsed(p,self.loss(p),299,reason='GM observed four seconds in final partial round')
        self.assertEqual(G.effective_capabilities(p),['Teleporter']);e.advance_time(1)
        self.assertEqual(G.effective_capabilities(p),['Invisibility','Phasing','Teleporter']);self.validate(e)
    def test_uncertain_loss_named_queries_keep_unrelated_actual_teleporter_escape(self):
        import movement_actions as MOVE
        self.p.spec['movement']['teleport']=4
        self.p.spec['capabilities'].extend(['도달','Naturewalk (forest)'])
        self.burn();self.e.advance_time(295);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=10);self.e.end_encounter()
        self.assertEqual(G.effective_capabilities(self.p,only=('Teleporter',)),['Teleporter'])
        self.assertEqual(G.effective_capabilities(self.p,only=('도달',)),['도달'])
        self.assertEqual(G.effective_capabilities(self.p,only=()),[])
        for only in (None,('Phasing',),('Invisibility',)):
            with self.assertRaisesRegex(ValueError,'observe actual'):G.effective_capabilities(self.p,only=only)
        before=deepcopy(self.p.spec)
        self.assertTrue(MOVE.naturewalk_terrains(self.e,self.p));self.assertEqual(self.p.spec,before)
        import body_state as BODY
        self.assertEqual(BODY.melee_reach(self.p),2)
        self.assertEqual(BODY.observe_melee_reach(self.e,self.p,3,anatomy='long_limbs',reason='actual GM anatomy observation'),3)
        for c in (self.b,self.p):c.spec['skills']['전투']=4
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        self.e.grapple(self.b,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[3]*4},defender_options={'fixed':[2]*4})
        self.e.end_of_turn(self.b);self.e.start_of_turn(self.p,initiative_count=10)
        with self.assertRaisesRegex(ValueError,'observe actual'):self.e.grapple_action(self.p,'escape',escape=dict(capability='Phasing',cost='shift',destination=[6,1]))
        out=self.e.grapple_action(self.p,'escape',escape=dict(capability='Teleporter',cost='shift',destination=[6,1]))
        self.assertTrue(out['ended']);self.assertEqual(self.p.pos,(6,1));self.assertEqual(self.p.budget['shift'],0)
    def test_forced_visibility_changes_native_move_accuracy_and_existing_cooldown(self):
        G.set_baseline(self.p,'moves',['move/물대포']);move=self.rules.move('move/물대포')
        base=next(n for n in range(2,16) if self.e.accuracy_check(self.q,self.p,move,fixed_roll=n)[0])
        self.e.change_invisibility(self.p,True,reason='actual activation');self.e.advance_time(37)
        with self.assertRaisesRegex(ValueError,'invisibility'):self.e.use_move(self.p,self.q,'move/물대포')
        self.assertFalse(self.e.accuracy_check(self.q,self.p,move,fixed_roll=base)[0])
        self.burn();self.assertIs(self.e.invisibility_state(self.p)['active'],False)
        self.assertEqual(self.p.spec[V.KEY]['ended_elapsed'],37);self.assertEqual(self.e.invisibility_state(self.p)['ready_after_elapsed'],194)
        self.assertTrue(self.e.accuracy_check(self.q,self.p,move,fixed_roll=base)[0]);self.e.use_move(self.p,self.q,'move/물대포',set_damage=True)
        self.e.advance_time(299)
        with self.assertRaisesRegex(ValueError,'capability'):self.e.change_invisibility(self.p,True,reason='lost')
        self.e.advance_time(1);self.assertIs(self.e.invisibility_state(self.p)['active'],False)
        self.e.change_invisibility(self.p,True,reason='new actual activation');self.assertIs(self.e.invisibility_state(self.p)['active'],True)
    def test_uncertain_active_invisibility_preflight_preserves_real_tag_and_rng(self):
        self.e.change_invisibility(self.p,True,reason='actual activation');self.e.advance_time(30)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=10);self.e.end_encounter()
        before=self.validate()
        with self.assertRaisesRegex(ValueError,'observe actual invisibility'):self.burn()
        self.assertEqual(self.validate(),before)
        self.e.observe_invisibility_elapsed(self.p,34,reason='observed final partial round')
        self.burn();self.assertEqual(self.p.spec[V.KEY]['ended_elapsed'],34)
    def test_public_phasing_consumer_blocks_and_unrelated_teleporter_survives(self):
        self.assertTrue(TAG.phasing_passage(self.e,self.p,(4,1)))
        self.burn()
        with self.assertRaisesRegex(ValueError,'Phasing'):TAG.phasing_passage(self.e,self.p,(4,1))
        self.assertIn('Teleporter',G.effective_capabilities(self.p));self.e.advance_time(300)
        self.assertTrue(TAG.phasing_passage(self.e,self.p,(4,1)))
    def test_actual_grapple_phasing_refused_teleporter_escape_keeps_native_cost(self):
        for c in (self.b,self.p):c.spec['skills']['전투']=4
        self.p.spec['movement']['teleport']=4
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
        self.e.grapple(self.b,self.p,challenger_skill='전투',defender_skill='전투',fixed_accuracy=20,
            challenger_options={'fixed':[3]*4},defender_options={'fixed':[2]*4})
        self.burn();self.e.end_of_turn(self.b);self.e.start_of_turn(self.p,initiative_count=10)
        before=deepcopy((self.p.pos,self.p.budget,self.e.rng.getstate()))
        with self.assertRaisesRegex(ValueError,'Phasing'):self.e.grapple_action(self.p,'escape',escape=dict(capability='Phasing',cost='shift',destination=[6,1]))
        self.assertEqual((self.p.pos,self.p.budget,self.e.rng.getstate()),before)
        out=self.e.grapple_action(self.p,'escape',escape=dict(capability='Teleporter',cost='shift',destination=[6,1]))
        self.assertTrue(out['ended']);self.assertEqual(self.p.pos,(6,1));self.assertEqual(self.p.budget['shift'],0)
    def test_extended_invisibility_investment_survives_temporary_loss_native_480_history(self):
        import invisibility_edge as EDGE
        self.p.spec.update(trainer_id=self.a.entity_id,tutor_points=8,wild=False)
        self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge='C2CSV/input/db/poke-edges.csv:R52:main',safe=True)
        self.assertEqual(self.p.spec['tutor_points'],7);self.e.change_invisibility(self.p,True,reason='actual extended activation')
        self.e.advance_time(300);self.burn()
        self.assertEqual((self.p.spec[V.KEY]['duration_seconds'],self.p.spec[V.KEY]['ended_elapsed']),(480,300))
        self.assertEqual(self.e.invisibility_state(self.p)['ready_after_elapsed'],720)
        self.assertEqual((self.p.spec['tutor_points'],EDGE.records(self.p)[0]['status']),(7,'active'))
        e,index=self.restore();p=index[self.p.entity_id];e.advance_time(300)
        self.assertEqual((p.spec['tutor_points'],EDGE.records(p)[0]['status']),(7,'active'))
        with self.assertRaises(ValueError):e.change_invisibility(p,True,reason='still native cooldown')
        e.advance_time(120);e.change_invisibility(p,True,reason='new actual extended activation')
        self.assertEqual(p.spec[V.KEY]['duration_seconds'],480)
    def test_actual_carried_original_is_released_and_burned_once(self):
        self.b.spec['movement']['power']=2
        self.e.gm.set_carried_objects(self.b,[{'id':'tag:one','weight_kg':0.01}],reason='actual user holds original tag')
        self.burn();obj=self.e._physical_objects['tag:one']
        self.assertNotIn('carrier_id',obj);self.assertEqual(self.b.spec['_carried_load']['objects'],[])
        self.assertIn('destroyed',obj);self.validate()
    def test_terminal_and_losses_survive_gm_and_fresh_json_and_reject_tamper(self):
        self.e.change_invisibility(self.p,True,reason='actual activation');self.e.advance_time(17);self.burn();self.e.gm.snapshot('burned')
        self.validate();before=deepcopy((self.e._physical_objects,G.capability_losses(self.p),self.p.spec[V.KEY],self.e.elapsed_seconds))
        e,index=self.restore();p=index[self.p.entity_id]
        self.assertEqual((e._physical_objects,G.capability_losses(p),p.spec[V.KEY],e.elapsed_seconds),before)
        e.advance_time(300);self.e.advance_time(300);self.e.gm.restore('burned')
        self.assertEqual((self.e._physical_objects,G.capability_losses(self.p),self.p.spec[V.KEY],self.e.elapsed_seconds),before);self.validate()
        for edit in (lambda:e._physical_objects['tag:one'][B.KEY]['targets'][self.p.entity_id]['result'].__setitem__('total',1),
            lambda:G.capability_losses(index[self.p.entity_id])[self.loss(index[self.p.entity_id])].__setitem__('elapsed_bounds',[1,1])):
            e,index=self.restore();edit()
            with self.assertRaises(ValueError):CODEC.dump_engine(e)
    def test_final_world_failure_preserves_observed_focus_without_partial_loss(self):
        before=self.validate()
        with patch.object(W,'finish_physical_use',side_effect=ValueError('terminal world failure')):
            with self.assertRaisesRegex(ValueError,'terminal world failure'):self.burn()
        self.assertEqual(self.validate(),before)
        original=G.capability_loss
        def fail_after(*args,**kw):original(*args,**kw);raise ValueError('injected world failure')
        with patch.object(G,'capability_loss',side_effect=fail_after):
            with self.assertRaisesRegex(ValueError,'injected'):self.burn()
        row=self.e._physical_objects['tag:one'][B.KEY];self.assertEqual(row['status'],'pending')
        self.assertEqual(G.effective_capabilities(self.p),['Invisibility','Phasing','Teleporter'])
        event=SF.event(self.e,self.p,row['targets'][self.p.entity_id]['skill_options']['roll_id']);self.assertEqual(event.state,'final')
        before=self.e.rng.getstate();self.burn();self.assertEqual(self.e.rng.getstate(),before);self.validate()


if __name__=='__main__':unittest.main()
