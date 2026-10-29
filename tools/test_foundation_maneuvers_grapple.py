"""Grapple common relation behavior through actual native owners."""
from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import test_category3_physics_maneuvers as native
from engine import Rules
import grapple_state as GR,common_checks as C,turn as TURN,combat_timing as TIME

class GrappleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(Path(__file__).resolve().parents[1])
    actor=native.Tests.actor
    setUp=native.Tests.setUp
    options=native.Tests.options

    def enter(self,**changes):return self.e.grapple(self.a,self.b,**self.options(**changes))
    def snapshot(self):return deepcopy((self.a.pos,self.b.pos,getattr(self.a,"budget",None),getattr(self.b,"budget",None),self.a.conditions,self.b.conditions,getattr(self.e,GR.FIELD,None),self.e.rng.getstate()))
    def turn_b(self):
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
    def turn_a_next(self):
        active=getattr(self.e,'_active_turn_actor',None)
        if active:self.e.end_of_turn(active)
        self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
    def test_initiation_accuracy_opposed_roles_and_actual_standard(self):
        row=self.enter(fixed_accuracy=4)
        self.assertEqual(row['dominant'],self.a.entity_id)
        self.assertEqual(GR.relation(self.e,self.b)['id'],row['id'])
        self.assertEqual(self.a.budget,dict(standard=0,shift=1,swift=1))
        self.assertEqual(self.a.evasion('물리'),0);self.assertIn('취약',self.b.conditions)
        GR.validate_world(self.e)
    def test_miss_and_tie_never_install_relation(self):
        for choices in ({'fixed_accuracy':1},{'defender_options':{'fixed':[3]*4}}):
            self.setUp();self.assertFalse(self.enter(**choices));self.assertIsNone(GR.relation(self.e,self.a));self.assertNotIn('취약',self.b.conditions);self.assertEqual(self.a.budget['standard'],0)
    def test_actual_trainer_and_pokemon_both_obey_grapple_movement_and_outside_accuracy(self):
        from builder import build_pokemon
        from engine import Combatant,Engine
        self.b=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,extra={'side':'wild'}))
        self.b.pos=(2,1);self.b.spec['skills'].update({'전투':4,'육상':4})
        self.e=Engine(self.r,7);self.e.grid=native.Grid(8,8);self.e.everyone=[self.a,self.b,self.w];self.e.gm.everyone=self.e.everyone
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20);self.w.pos=(6,4)
        row=self.enter(fixed_accuracy=20);self.assertEqual(row['dominant'],self.a.entity_id)
        self.assertEqual((self.a.kind,self.b.kind),('trainer','pokemon'))
        move=dict(id='maneuver/붙잡기',name='actual grapple accuracy',type='노말',**{'class':'변화'},ac=4,range='근접, 대상1',keywords=[])
        for actor,other in ((self.a,self.b),(self.b,self.a)):
            if actor is self.b:self.turn_b()
            self.assertIn('취약',actor.conditions);self.assertEqual(GR.relation(self.e,actor)['id'],row['id'])
            before=self.snapshot()
            self.assertFalse(TURN.spend(self.e,actor,'shift','walk',movement=True))
            self.assertFalse(TURN.movement_permission(self.e,actor));self.e.approach(actor,self.w)
            self.assertEqual(before,self.snapshot())
            self.assertTrue(self.e.accuracy_check(actor,other,move,fixed_roll=4)[0])
            self.assertFalse(self.e.accuracy_check(actor,self.w,move,fixed_roll=4)[0])
            self.assertTrue(self.e.accuracy_check(actor,self.w,move,fixed_roll=10)[0])
    def test_same_turn_cannot_use_ongoing_full_action_and_ordinary_movement_is_blocked(self):
        self.enter();before=self.snapshot()
        with self.assertRaises(ValueError):self.e.grapple_action(self.a,'end')
        self.assertFalse(TURN.spend(self.e,self.a,'shift','walk',movement=True));self.assertEqual(before,self.snapshot())
    def test_outside_accuracy_penalty_and_inside_target_are_actual(self):
        self.enter();self.e.everyone.append(self.w)
        move=dict(id='maneuver/붙잡기',name='test',type='노말',**{'class':'변화'},ac=4,range='근접, 대상1',keywords=[])
        self.assertTrue(self.e.accuracy_check(self.a,self.b,move,fixed_roll=4)[0])
        self.assertFalse(self.e.accuracy_check(self.a,self.w,move,fixed_roll=4)[0])
        self.assertTrue(self.e.accuracy_check(self.a,self.w,move,fixed_roll=10)[0])
    def test_contest_reverses_dominance_and_full_cost_then_winner_can_end(self):
        self.enter();self.turn_b()
        out=self.e.grapple_action(self.b,'contest',challenger_skill='육상',defender_skill='전투',challenger_options={'fixed':[5]*4},defender_options={'fixed':[1]*4},winner_choice='keep')
        self.assertEqual(out['winner_id'],self.b.entity_id);self.assertEqual(GR.relation(self.e,self.a)['dominant'],self.b.entity_id)
        self.assertEqual(self.b.budget,dict(standard=0,shift=0,swift=1))
        self.turn_a_next()
        self.e.grapple_action(self.a,'contest',challenger_skill='전투',defender_skill='육상',challenger_options={'fixed':[1]*4},defender_options={'fixed':[2]*4},winner_choice='end')
        self.assertIsNone(GR.relation(self.e,self.a));self.assertIsNone(GR.relation(self.e,self.b))
        self.assertNotIn('취약',self.a.conditions);self.assertNotIn('취약',self.b.conditions)
    def test_secure_bonus_is_next_check_only_and_defender_keeps_tie(self):
        self.enter();self.turn_a_next();self.e.grapple_action(self.a,'secure')
        self.assertEqual(GR.relation(self.e,self.a)['secure'],{self.a.entity_id:3})
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
        out=self.e.grapple_action(self.b,'contest',challenger_skill='전투',defender_skill='전투',challenger_options={'fixed':[3,3,3,2]},defender_options={'fixed':[2]*4},winner_choice='keep')
        self.assertEqual(out['winner_id'],self.a.entity_id);self.assertEqual(GR.relation(self.e,self.a)['secure'],{})
    def test_release_preserves_independent_vulnerability(self):
        self.e.apply_status(self.b,'취약');self.enter();self.turn_a_next()
        self.e.grapple_action(self.a,'end')
        self.assertNotIn('취약',self.a.conditions);self.assertIn('취약',self.b.conditions)
        self.assertTrue(TURN.movement_permission(self.e,self.a));self.assertTrue(TURN.movement_permission(self.e,self.b))
    def test_forced_separation_and_scene_end_clear_both_bindings(self):
        import forced_movement as FORCED
        self.enter();FORCED.displace(self.e,self.a,self.b,direction=(1,0),distance=2,source=GR.SOURCE)
        self.assertIsNone(GR.relation(self.e,self.a));self.assertIsNone(GR.relation(self.e,self.b))
        self.setUp();self.enter();self.e.end_scene();self.assertIsNone(GR.relation(self.e,self.a));self.assertNotIn('취약',self.b.conditions)
    def test_drag_uses_declared_actual_weight_penalty_native_terrain_and_both_paths(self):
        value=GR.native_policy();value['drag_penalties']={'2':2};self.b.spec['weight_class']=2
        self.enter(declaration=value);self.turn_a_next();self.e.grid.slow.add((1,2))
        out=self.e.grapple_action(self.a,'drag',path=[dict(actor=[1,2],partner=[2,2]),dict(actor=[1,3],partner=[2,3])])
        self.assertEqual((self.a.pos,self.b.pos),((1,3),(2,3)));self.assertEqual(out['partner_position'],(2,3));self.assertEqual(self.a.budget['shift'],0)
        self.assertIsNotNone(GR.relation(self.e,self.b))
    def test_missing_drag_coefficient_is_pre_cost_pending_and_obstruction_rolls_back(self):
        self.enter();self.turn_a_next();before=self.snapshot()
        result=self.e.grapple_action(self.a,'drag',path=[dict(actor=[1,2],partner=[2,2])]);self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.snapshot(),before)
        self.setUp();value=GR.native_policy();value['drag_penalties']={'2':1};self.b.spec['weight_class']=2;self.enter(declaration=value);self.turn_a_next();self.e.grid.blocking.add((2,2));before=self.snapshot()
        with self.assertRaises(ValueError):self.e.grapple_action(self.a,'drag',path=[dict(actor=[1,2],partner=[2,2])])
        self.assertEqual(self.snapshot(),before)
    def test_late_joint_movement_failure_restores_positions_costs_and_relation(self):
        import effects_ext as EXT
        value=GR.native_policy();value['drag_penalties']={'2':1};self.b.spec['weight_class']=2;self.enter(declaration=value);self.turn_a_next();before=self.snapshot()
        with patch.object(EXT,'on_enter_cell',side_effect=ValueError('late hazard')):
            with self.assertRaisesRegex(ValueError,'late hazard'):self.e.grapple_action(self.a,'drag',path=[dict(actor=[1,2],partner=[2,2])])
        self.assertEqual(self.snapshot(),before)
    def test_dominant_attack_native_unarmed_damage_is_automatic_not_a_critical_roll(self):
        self.enter();self.turn_a_next();hp=self.b.hp
        with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as ac:
            out=self.e.grapple_action(self.a,'attack',request_id='squeeze1')
        self.assertEqual(ac.call_count,0);self.assertGreater(out['damage'],0);self.assertLess(self.b.hp,hp)
        self.assertEqual(self.a._action_history[-1],'full');before=self.snapshot()
        self.assertEqual(self.e.grapple_action(self.a,'attack',request_id='squeeze1'),out);self.assertEqual(self.snapshot(),before)
    def test_phasing_escape_requires_actual_capability_own_turn_and_legal_range(self):
        self.enter();self.turn_b();before=self.snapshot()
        escape=dict(capability='Phasing',cost='shift',destination=[4,1])
        with self.assertRaises(ValueError):self.e.grapple_action(self.b,'escape',escape=escape)
        self.assertEqual(self.snapshot(),before);self.b.spec['capabilities']=['Phasing']
        self.assertTrue(self.e.grapple_action(self.b,'escape',escape=escape)['ended']);self.assertEqual(self.b.pos,(4,1));self.assertEqual(self.b.budget['shift'],0)
        self.assertIsNone(GR.relation(self.e,self.a))
    def test_authored_remote_entry_requires_actual_qualification_and_distance(self):
        value=GR.native_policy();entry=value['initiation'];entry['geometry']=dict(range=4,remote=True,vertical=False);entry['requirements']=[dict(id='remote',who='actor',condition={'kind':'capability','names':['Telekinetic']},reason='authored remote grapple')]
        self.b.pos=(4,1);before=self.snapshot()
        with self.assertRaises(ValueError):self.enter(declaration=value)
        self.assertEqual(self.snapshot(),before);self.a.spec['capabilities']=['Telekinetic'];self.assertTrue(self.enter(declaration=value))
    def test_json_gm_roundtrip_and_tampering(self):
        import state_codec as CODEC
        self.enter();self.e.gm.snapshot("grapple")
        text=CODEC.dump_engine(self.e);loaded=CODEC.load_engine(self.r,text)
        GR.validate_world(loaded);self.assertTrue(GR.has_pending(loaded))
        row=GR.relation(self.e,self.a);row['dominant']=self.b.entity_id
        with self.assertRaises(ValueError):self.e.gm.snapshot()
        self.e.gm.restore("grapple");self.assertEqual(GR.relation(self.e,self.a)['dominant'],self.a.entity_id)


    def test_escape_does_not_require_starting_turn_in_relation_and_has_native_terrain_callback(self):
        import effects_ext as EXT
        self.a.spec['capabilities']=['Phasing'];self.enter()
        with patch.object(EXT,'on_enter_cell',wraps=EXT.on_enter_cell) as entered:
            out=self.e.grapple_action(self.a,'escape',escape=dict(capability='Phasing',cost='shift',destination=[1,3]))
        self.assertTrue(out['ended']);self.assertEqual(entered.call_count,1);self.assertIsNone(GR.relation(self.e,self.b))
    def test_actual_pokemon_teleporter_escape_uses_native_capability_cost_and_once_round_record(self):
        from engine import Combatant,Engine
        self.b=Combatant(self.r,dict(id='pokemon/B',name='B',kind='pokemon',size='Medium',side='wild',pos=(2,1),level=20,stats=dict(hp=20,atk=10,**{'def':10},spa=10,spd=10,spe=1),skills={'전투':4,'육상':4},movement={'land':6,'teleport':4},weight_kg=30))
        self.e=Engine(self.r,7);self.e.grid=native.Grid(8,8);self.e.everyone=[self.a,self.b];self.e.gm.everyone=self.e.everyone
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        self.enter();self.turn_b();result=self.e.grapple_action(self.b,'escape',escape=dict(capability='Teleporter',cost='shift',destination=[5,1]))
        self.assertTrue(result['ended']);self.assertEqual(self.b.pos,(5,1));self.assertEqual(self.b.budget['shift'],0);self.assertEqual(self.b.spec['_teleport']['used_round'],self.e.round_no);self.assertIsNone(GR.relation(self.e,self.a))
    def test_observed_skill_feature_entry_retries_without_repaying_or_rolling_hit_again(self):
        import skill_feature_actions as SF
        self.a.spec['feats']=[SF.MONKEY];self.b.spec['feats']=[SF.MONKEY]
        import test_category3_maneuver_features as featured
        options=self.options(challenger_skill='전투',defender_skill='육상',
            challenger_options=featured.Tests.opts(self,'ga',faces=4),
            defender_options=featured.Tests.opts(self,'gb',bad=True,faces=2))
        with patch.object(self.e,'accuracy_check',wraps=self.e.accuracy_check) as ac:
            with self.assertRaises(ValueError):self.e.grapple(self.a,self.b,**options)
            calls=ac.call_count;before=self.e.rng.getstate()
            options['defender_options']=featured.Tests.opts(self,'gb',faces=2)
            row=self.e.grapple(self.a,self.b,**options)
        self.assertEqual(ac.call_count,calls);self.assertEqual(self.e.rng.getstate(),before);self.assertEqual(self.a._action_history,['standard','free']);self.assertEqual(row['dominant'],self.a.entity_id)


    def test_native_faint_releases_both_participants_immediately(self):
        self.enter();self.e.lose_hp(self.b,self.b.hp);self.e.check_fainted(self.b)
        self.assertTrue(self.b.fainted);self.assertIsNone(GR.relation(self.e,self.a));self.assertIsNone(GR.relation(self.e,self.b));self.assertTrue(TURN.movement_permission(self.e,self.a))
    def test_repeated_secure_requires_declared_stacking_and_duplicate_membership_is_rejected(self):
        self.enter();self.turn_a_next();self.e.grapple_action(self.a,'secure');self.turn_a_next();before=self.snapshot()
        self.assertIsInstance(self.e.grapple_action(self.a,'secure'),C.PendingDecision);self.assertEqual(self.snapshot(),before)
        with self.assertRaises(ValueError):self.e.grapple(self.a,self.b,**self.options())
        self.assertEqual(self.snapshot(),before)


    def test_late_relation_installation_failure_restores_both_bindings_status_cost_and_rng(self):
        from engine import Engine
        original=Engine.apply_effect;calls=[]
        def fail_second(engine,*args,**kwargs):
            result=original(engine,*args,**kwargs);calls.append(1)
            if len(calls)==2:raise ValueError('second grapple status failed')
            return result
        before=self.snapshot()
        with patch.object(Engine,'apply_effect',fail_second):
            with self.assertRaisesRegex(ValueError,'second grapple'):self.enter()
        self.assertEqual(self.snapshot(),before);self.assertIsNone(GR.relation(self.e,self.a));self.assertIsNone(GR.relation(self.e,self.b))

if __name__=='__main__':unittest.main()

