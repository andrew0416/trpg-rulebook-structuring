"""C07-120: observed actual groups contest through native Full/check/choice owners."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category3_physics_maneuvers as native
from engine import Rules,Engine,Combatant
import common_checks as C,grapple_state as GR,turn as TURN
import skill_feature_actions as SF,skill_maneuver_actions as SM


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(native.ROOT)
    actor=native.Tests.actor

    def setUp(self):self.world()

    def world(self,*,pokemon=False):
        self.e=Engine(self.r,7)
        self.a=self.actor('A','party',(1,1));self.b=self.actor('B','wild',(2,1))
        if pokemon:
            from builder import build_pokemon
            self.c=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,extra={'side':'wild'}))
            self.c.pos=(1,2);self.c.spec['skills'].update({'전투':4,'육상':4})
        else:self.c=self.actor('C','wild',(1,2))
        self.outside=self.actor('Outside','wild',(6,4))
        self.members=[self.a,self.b,self.c]
        self.e.everyone=[*self.members,self.outside];self.e.gm.everyone=self.e.everyone
        self.e.grid=native.Grid(8,8)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def observe(self,**changes):
        options=dict(dominant=self.a,source='gm/observation',reason='GM observed these actual actors already grappling')
        options.update(changes)
        return GR.observe(self.e,self.members,**options)

    def turn(self,actor):
        active=getattr(self.e,'_active_turn_actor',None)
        if active:self.e.end_of_turn(active)
        self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=10)

    def checks(self,tag='group',faces=(1,2,5)):
        return {actor.entity_id:dict(skill='육상' if i%2==0 else '전투',options={'roll_id':tag+str(i),'fixed':[face]*4})
                for i,(actor,face) in enumerate(zip(self.members,faces))}

    def choices(self,**changes):
        result={actor.entity_id:'keep' for actor in self.members};result.update(changes);return result

    def contest(self,*,actor=None,checks=None,choices=None,request_id='group',**changes):
        return self.e.grapple_action(self.b if actor is None else actor,'contest',
            participant_checks=self.checks(request_id) if checks is None else checks,
            winner_choices=self.choices() if choices is None else choices,request_id=request_id,**changes)

    def snapshot(self):
        return deepcopy(([(c.entity_id,c.pos,c.hp,c.conditions,getattr(c,'budget',None),getattr(c,'_action_history',[])) for c in self.e.everyone],
                         getattr(self.e,GR.FIELD,None),self.e.rng.getstate()))

    def observed_rolls(self,checks):
        return {actor.entity_id:SF.event(self.e,actor,checks[actor.entity_id]['options']['roll_id']).first for actor in self.members}

    def assert_released(self):
        for actor in self.members:
            self.assertIsNone(GR.relation(self.e,actor));self.assertTrue(TURN.movement_permission(self.e,actor))

    def test_gm_observes_actual_trainer_and_pokemon_group_without_maneuver_or_roll(self):
        self.world(pokemon=True);before=self.snapshot();row=self.observe()
        self.assertEqual([self.a.kind,self.c.kind],['trainer','pokemon'])
        self.assertEqual(row['participants'],[c.entity_id for c in self.members]);self.assertEqual(row['dominant'],self.a.entity_id)
        self.assertEqual(row['observation']['source'],'gm/observation');self.assertIn('GM observed',row['observation']['reason'])
        self.assertEqual(row['source'],GR.SOURCE);self.assertEqual(row['eligible'],{})
        self.assertEqual(self.e.rng.getstate(),before[-1]);self.assertEqual(self.a.budget,before[0][0][4]);self.assertFalse(self.e._ap_rolls)
        for actor in self.members:
            self.assertEqual(GR.relation(self.e,actor)['id'],row['id']);self.assertIn('취약',actor.conditions)
            self.assertNotIn(SM.RECEIPTS,actor.custom_conditions)
        self.assertIn('observed actual grapple',self.e.rulings.report());GR.validate_world(self.e)
        stable=self.snapshot();self.assertEqual(self.observe(),row);GR.boundary(self.e);self.assertEqual(self.snapshot(),stable)

    def test_observation_rejects_forged_duplicate_unavailable_and_unowned_dominant(self):
        cases=[([self.a,self.b,self.b],self.a,'GM'),([self.a,self.b,self.actor('Ghost','wild',(1,2))],self.a,'GM'),
               (self.members,self.outside,'GM'),(self.members,self.a,'')]
        for members,dominant,reason in cases:
            before=self.snapshot()
            with self.assertRaises(ValueError):GR.observe(self.e,members,dominant=dominant,reason=reason)
            self.assertEqual(self.snapshot(),before)
        self.c.captured=True;before=self.snapshot()
        with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.snapshot(),before);self.c.captured=False
        self.e.grapple(self.a,self.b,**native.Tests.options(self));before=self.snapshot()
        with self.assertRaises(ValueError):self.observe()
        self.assertEqual(self.snapshot(),before)

    def test_third_observed_status_failure_rolls_back_all_members_and_gm_record(self):
        original=Engine.apply_effect;calls=[];before=self.snapshot();report=self.e.rulings.report()
        def fail_third(engine,*args,**kwargs):
            result=original(engine,*args,**kwargs);calls.append(1)
            if len(calls)==3:raise ValueError('third actual status failed')
            return result
        with patch.object(Engine,'apply_effect',fail_third):
            with self.assertRaisesRegex(ValueError,'third actual'):self.observe()
        self.assertEqual(len(calls),3);self.assertEqual(self.snapshot(),before);self.assertEqual(self.e.rulings.report(),report)
        for actor in self.members:self.assertIsNone(GR.relation(self.e,actor))

    def test_every_actual_participant_rolls_and_third_highest_wins_native_full(self):
        self.world(pokemon=True);self.observe();self.turn(self.b);checks=self.checks();calls=[];original=Engine.skill_roll
        def observed(engine,actor,skill,**options):
            calls.append((actor.entity_id,skill));return original(engine,actor,skill,**options)
        with patch.object(Engine,'skill_roll',observed):result=self.contest(checks=checks)
        self.assertEqual(sorted(calls),sorted((c.entity_id,checks[c.entity_id]['skill']) for c in self.members))
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assertEqual(GR.relation(self.e,self.a)['dominant'],self.c.entity_id)
        self.assertEqual(set(result['check_totals']),set(checks));self.assertGreater(result['check_totals'][self.c.entity_id],result['check_totals'][self.b.entity_id])
        self.assertEqual(self.b.budget,dict(standard=0,shift=0,swift=1));self.assertEqual(self.b._action_history,['full'])
        before=self.snapshot();self.assertEqual(self.contest(checks=checks),result);self.assertEqual(self.snapshot(),before)
        changed=deepcopy(checks);changed[self.c.entity_id]['options']['fixed']=[1]*4
        with self.assertRaisesRegex(ValueError,'changed intent'):self.contest(checks=changed)
        GR.validate_world(self.e)

    def test_complete_member_checks_skills_and_distinct_ids_are_required_before_full(self):
        self.observe();self.turn(self.b)
        incomplete=self.checks();incomplete.pop(self.c.entity_id)
        forged=self.checks();forged[self.outside.entity_id]=forged.pop(self.c.entity_id)
        invalid_skill=self.checks();invalid_skill[self.c.entity_id]['skill']='곡예'
        duplicate=self.checks();duplicate[self.c.entity_id]['options']['roll_id']=duplicate[self.a.entity_id]['options']['roll_id']
        no_id=self.checks();no_id[self.c.entity_id]['options'].pop('roll_id')
        bad_dice=self.checks();bad_dice[self.c.entity_id]['options']['fixed']=[7]*4
        for checks in (incomplete,forged,invalid_skill,duplicate,no_id,bad_dice):
            before=self.snapshot()
            with self.assertRaises(ValueError):self.contest(checks=checks)
            self.assertEqual(self.snapshot(),before)
        before=self.snapshot()
        with self.assertRaises(ValueError):self.contest(request_id=None,checks=self.checks())
        self.assertEqual(self.snapshot(),before)

    def test_actual_turn_start_and_role_gate_precede_all_participant_cost(self):
        self.observe();before=self.snapshot()
        with self.assertRaises(ValueError):self.contest(actor=self.a)
        with self.assertRaises(ValueError):self.contest(actor=self.b)
        self.assertEqual(self.snapshot(),before)
        self.turn(self.a);before=self.snapshot()
        with self.assertRaisesRegex(ValueError,'nondominant'):self.contest(actor=self.a)
        self.assertEqual(self.snapshot(),before)
        self.turn(self.b);self.contest();self.assertEqual(GR.relation(self.e,self.a)['dominant'],self.c.entity_id)
        with self.assertRaises(ValueError):self.e.grapple_action(self.c,'end')
        self.turn(self.c);self.assertTrue(self.e.grapple_action(self.c,'end')['success']);self.assert_released()

    def test_actual_highest_winner_own_end_choice_releases_only_relation_vulnerability(self):
        self.e.apply_status(self.c,'취약');self.observe();self.turn(self.b)
        choices=self.choices();choices[self.c.entity_id]='end'
        result=self.contest(choices=choices)
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assert_released()
        self.assertNotIn('취약',self.a.conditions);self.assertNotIn('취약',self.b.conditions);self.assertIn('취약',self.c.conditions)
        before=self.snapshot();self.assertEqual(self.contest(choices=choices),result);self.assertEqual(self.snapshot(),before)

    def test_incumbent_highest_tie_uses_existing_defender_policy(self):
        self.observe();self.turn(self.b)
        result=self.contest(checks=self.checks(faces=(3,3,3)))
        self.assertEqual(len(set(result['check_totals'].values())),1)
        self.assertEqual(result['winner_id'],self.a.entity_id);self.assertEqual(GR.relation(self.e,self.c)['dominant'],self.a.entity_id)

    def test_nonincumbent_highest_tie_waits_for_actual_gm_choice_without_reroll_or_repayment(self):
        self.observe();self.turn(self.b);checks=self.checks(faces=(1,5,5))
        pending=self.contest(checks=checks);self.assertIsInstance(pending,C.PendingDecision)
        self.assertEqual(set(pending.basis['highest_ids']),{self.b.entity_id,self.c.entity_id})
        self.assertEqual(self.b.custom_conditions[SM.ACTIVE],GR.SOURCE+'/contest:'+checks[self.b.entity_id]['options']['roll_id'])
        self.assertNotIn(SM.ACTIVE,self.a.custom_conditions)
        originals=self.observed_rolls(checks);rng=self.e.rng.getstate();self.assertEqual(self.b._action_history,['full'])
        with self.assertRaisesRegex(ValueError,'highest'):self.contest(checks=checks,tie_winner={'actor_id':self.a.entity_id,'reason':'GM cannot select the loser'})
        self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.b._action_history,['full'])
        result=self.contest(checks=checks,tie_winner={'actor_id':self.c.entity_id,'reason':'GM resolves the actual tied highest checks'})
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.b._action_history,['full'])
        for actor in self.members:self.assertIs(self.observed_rolls(checks)[actor.entity_id],originals[actor.entity_id])

    def test_missing_actual_winner_choice_survives_json_and_gm_restore_with_observed_rolls(self):
        import state_codec as CODEC
        self.observe();self.turn(self.b);checks=self.checks();choices={self.b.entity_id:'keep'}
        pending=self.contest(checks=checks,choices=choices);self.assertIsInstance(pending,C.PendingDecision)
        self.assertEqual(pending.basis['winner_id'],self.c.entity_id);rng=self.e.rng.getstate()
        self.e.gm.snapshot('observed-grapple-choice');loaded=CODEC.load_engine(self.r,CODEC.dump_engine(self.e))
        index={c.entity_id:c for c in loaded.everyone};loaded_b=index[self.b.entity_id]
        choices[self.c.entity_id]='end'
        result=loaded.grapple_action(loaded_b,'contest',participant_checks=checks,winner_choices=choices,request_id='group')
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assertEqual(loaded.rng.getstate(),rng);self.assertEqual(loaded_b._action_history,['full'])
        for actor in self.members:self.assertIsNone(GR.relation(loaded,index[actor.entity_id]))
        self.e.grapple_action(self.b,'contest',participant_checks=checks,winner_choices=choices,request_id='group')
        self.e.gm.restore('observed-grapple-choice');GR.validate_world(self.e)
        result=self.contest(checks=checks,choices=choices)
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.b._action_history,['full']);self.assert_released()

    def test_native_rng_observations_are_retained_while_actual_winner_decides(self):
        self.observe();self.turn(self.b);checks=self.checks()
        for check in checks.values():check['options'].pop('fixed')
        initial=self.e.rng.getstate();pending=self.contest(checks=checks,choices={})
        self.assertIsInstance(pending,C.PendingDecision);observed=self.e.rng.getstate();self.assertNotEqual(initial,observed)
        rolls=self.observed_rolls(checks);winner=pending.basis.get('winner_id');options={}
        if winner is None:
            winner=pending.basis['highest_ids'][0];options['tie_winner']={'actor_id':winner,'reason':'GM chooses an actually observed highest tie'}
        result=self.contest(checks=checks,choices={winner:'keep'},**options)
        self.assertEqual(result['winner_id'],winner);self.assertEqual(self.e.rng.getstate(),observed);self.assertEqual(self.b._action_history,['full'])
        for actor in self.members:self.assertIs(self.observed_rolls(checks)[actor.entity_id],rolls[actor.entity_id])

    def test_later_skill_feature_choice_retries_all_real_participants_without_repaying(self):
        self.observe();self.turn(self.b)
        for actor in self.members:actor.spec['feats']=[SF.MONKEY]
        checks=self.checks(faces=(2,3,4));seen=[]
        for actor in self.members:
            checks[actor.entity_id]['options'].update(feature=SF.MONKEY,feature_options={'decision':lambda first:False})
        def bad(first):seen.append(first);return 'invalid decision'
        checks[self.c.entity_id]['options']['feature_options']['decision']=bad
        with self.assertRaisesRegex(ValueError,'boolean'):self.contest(checks=checks)
        self.assertEqual(len(seen),1);originals=self.observed_rolls(checks);rng=self.e.rng.getstate()
        checks[self.c.entity_id]['options']['feature_options']['decision']=lambda first:False
        result=self.contest(checks=checks)
        self.assertEqual(result['winner_id'],self.c.entity_id);self.assertEqual(self.b._action_history,['full']);self.assertEqual(self.e.rng.getstate(),rng)
        for actor in self.members:self.assertIs(self.observed_rolls(checks)[actor.entity_id],originals[actor.entity_id])

    def test_secure_and_actual_static_bind_modify_their_owners_once(self):
        self.c.spec['moves']=[GR.BIND];self.c.moves=[GR.BIND]
        self.observe();self.turn(self.a);self.e.grapple_action(self.a,'secure');self.turn(self.b)
        result=self.contest(checks=self.checks(faces=(2,2,2)))
        totals=result['check_totals'];self.assertEqual(totals[self.a.entity_id]-totals[self.b.entity_id],3)
        self.assertEqual(totals[self.c.entity_id]-totals[self.b.entity_id],2);self.assertEqual(result['winner_id'],self.a.entity_id)
        self.assertEqual(GR.relation(self.e,self.c)['secure'],{})
        self.turn(self.b);result=self.contest(checks=self.checks('next',faces=(2,2,2)),request_id='next')
        self.assertEqual(result['winner_id'],self.c.entity_id)

    def test_each_member_uses_native_movement_outside_accuracy_and_explicit_attack_target(self):
        self.observe()
        move=dict(id=GR.SOURCE,name='group grapple accuracy',type='노말',**{'class':'변화'},ac=4,range='근접, 대상1',keywords=[])
        for actor in self.members:
            before=self.snapshot();self.assertFalse(TURN.movement_permission(self.e,actor));self.assertFalse(TURN.spend(self.e,actor,'shift','walk',movement=True));self.assertEqual(self.snapshot(),before)
            for other in self.members:
                if other is not actor:self.assertTrue(self.e.accuracy_check(actor,other,move,fixed_roll=4)[0])
            self.assertFalse(self.e.accuracy_check(actor,self.outside,move,fixed_roll=4)[0])
        self.turn(self.a);before=self.snapshot()
        with self.assertRaises(ValueError):self.e.grapple_action(self.a,'attack')
        with self.assertRaises(ValueError):self.e.grapple_action(self.a,'attack',target=self.outside)
        self.assertEqual(self.snapshot(),before);hp_b,hp_c=self.b.hp,self.c.hp
        result=self.e.grapple_action(self.a,'attack',target=self.c,request_id='actual-c')
        self.assertGreater(result['damage'],0);self.assertEqual(self.b.hp,hp_b);self.assertLess(self.c.hp,hp_c)
        self.assertEqual(self.a._action_history,['full'])

    def test_changed_observed_geometry_faint_and_scene_end_use_existing_whole_relation_release(self):
        for event in ('geometry','altitude','faint','scene'):
            self.world();self.observe();stable=self.snapshot();GR.boundary(self.e);self.assertEqual(self.snapshot(),stable)
            if event=='geometry':self.c.pos=(4,4);GR.boundary(self.e)
            elif event=='altitude':self.c.spec['_movement_altitude']=1;GR.boundary(self.e)
            elif event=='faint':self.e.lose_hp(self.c,self.c.hp);self.e.check_fainted(self.c)
            else:self.e.end_scene()
            self.assert_released()
            for actor in self.members:self.assertNotIn('취약',actor.conditions)

    def test_existing_capability_escape_releases_observed_group_and_undeclared_drag_stays_pending(self):
        self.observe();self.turn(self.a);before=self.snapshot()
        self.assertIsInstance(self.e.grapple_action(self.a,'drag',path=[]),C.PendingDecision);self.assertEqual(self.snapshot(),before)
        self.turn(self.b);self.b.spec['capabilities']=['Phasing']
        result=self.e.grapple_action(self.b,'escape',escape=dict(capability='Phasing',cost='shift',destination=[4,1]))
        self.assertTrue(result['ended']);self.assertEqual(self.b.pos,(4,1));self.assertEqual(self.b.budget['shift'],0);self.assert_released()

    def test_late_winner_release_failure_restores_group_but_keeps_observed_full_and_rolls(self):
        import combat_timing as TIME
        self.observe();self.turn(self.b);checks=self.checks();choices=self.choices();choices[self.c.entity_id]='end'
        before=deepcopy(getattr(self.e,GR.FIELD));original=TIME.expire;calls=[]
        def fail_later(engine,actor,record,**options):
            result=original(engine,actor,record,**options);calls.append(actor.entity_id)
            if len(calls)==2:raise ValueError('late observed group release failed')
            return result
        with patch.object(TIME,'expire',fail_later):
            with self.assertRaisesRegex(ValueError,'late observed'):self.contest(checks=checks,choices=choices)
        self.assertEqual(getattr(self.e,GR.FIELD),before);self.assertEqual(self.b._action_history,['full'])
        for actor in self.members:self.assertIsNotNone(GR.relation(self.e,actor));self.assertIn('취약',actor.conditions)
        self.assertEqual(len(self.observed_rolls(checks)),3);rng=self.e.rng.getstate()
        result=self.contest(checks=checks,choices=choices);self.assertIsInstance(result,C.PendingDecision);self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.b._action_history,['full'])

    def test_signed_observed_membership_and_pending_declaration_tampering_are_rejected(self):
        self.observe();row=GR.relation(self.e,self.a);row['participants'].append(self.outside.entity_id)
        with self.assertRaises(ValueError):GR.validate_world(self.e)
        row['participants'].pop();GR._save(row);row['observation']['participants'].pop();GR._save(row)
        with self.assertRaises(ValueError):GR.validate_world(self.e)
        self.world();self.observe();self.turn(self.b);checks=self.checks(faces=(1,5,5));self.assertIsInstance(self.contest(checks=checks),C.PendingDecision)
        changed=deepcopy(checks);changed[self.a.entity_id]['skill']='전투'
        rng=self.e.rng.getstate()
        with self.assertRaises(ValueError):self.contest(checks=changed)
        self.assertEqual(self.e.rng.getstate(),rng);self.assertEqual(self.b._action_history,['full'])


if __name__=='__main__':unittest.main()
