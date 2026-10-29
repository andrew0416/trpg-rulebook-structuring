"""Moment of Action's real acquisition, multi-recipient Orders producer and AP use."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_trainer,build_pokemon
import moment_of_action as M,temporary_ap as TEMP,trainer_feature_acquisition as TFA
import action_points as AP,ap_roll_bonus as ROLL,state_codec as CODEC
import state_grants as G,state_fields as F,trainer_retraining as RETRAIN,priority_limited as PRIORITY
import perception_communicate as COMM
import training_features as TRAINING,items
import test_book_capture_specialist as BASE
import test_book_captured_momentum as MOMENTUM_BASE

FUNDING={'priority':'temporary_first','binding_expiry':'end_effect','reason':'GM chooses temporary points first and native ending on funding loss'}

class MomentOfActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(str(ROOT),ruleset='core')
        cls.errata=Rules(str(ROOT),ruleset='core+errata')
    def setUp(self):self.setup()
    def setup(self,*,acquire=True,combat=True,rules=None):
        self.base=BASE.BookCaptureSpecialistTests();self.base.rules=rules or self.rules
        self.e,self.a=self.base.fixture(skills={'매력':3,'명령':2})
        self.a.side='party'
        self.b,self.c=[Combatant(self.e.r,build_trainer(self.e.r,name,20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[])) for name in ('ally-one','ally-two')]
        self.b.side=self.c.side='party'
        self.e.everyone=self.e.gm.everyone=[self.a,self.b,self.c];self.e.time_actors(self.e.everyone)
        if acquire:
            for uid in (M.TRAINING,M.CLASS,M.FEATURE):TFA.acquire_static(self.e,self.a,uid,acquisition_request_id='acquire/'+uid)
        for target in (self.b,self.c):self.audible(target)
        if combat:self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
    def audible(self,target,allowed=True,mode='auditory'):
        self.e.gm.observe_sensory_environment(self.a,target,paths={mode:allowed},present=True,reason='observed current order communication route')
    def use(self,targets=None,**kw):
        targets=[self.b,self.c] if targets is None else targets
        options={'funding':{t.entity_id:deepcopy(FUNDING) for t in targets},
                 'allies':{t.entity_id:{'allied':True,'reason':'GM observes actual allied relationship'} for t in targets}}
        options.update(kw)
        return self.e.moment_of_action(self.a,targets,**options)
    def snapshot(self):return CODEC.dump_engine(self.e)
    def unchanged(self,callback,error=ValueError):
        before=self.snapshot()
        with self.assertRaises(error):callback()
        self.assertEqual(self.snapshot(),before)
    def restore(self):
        ids=[x.entity_id for x in (self.a,self.b,self.c)]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(self.snapshot(),ensure_ascii=False)))
        index={x.entity_id:x for x in self.e.gm.everyone};self.a,self.b,self.c=[index[uid] for uid in ids]
    def acquire(self,uid,request=None):return TFA.acquire_static(self.e,self.a,uid,acquisition_request_id=request or 'acquire/'+uid)
    def decisions(self,uid):
        result=self.base.decisions(self.e,self.a,uid,request='moment/remove/'+uid)
        sources={key:RETRAIN.owned_source(self.e,self.a,key) for key in RETRAIN._owned(self.a)}
        for child,parent in ((M.CLASS,M.TRAINING),(M.FEATURE,M.CLASS)):
            if child!=uid and child in sources:result['retained_dependencies'][sources[child]]=[sources[parent]]
        return result
    def test_real_acquisition_chain_historical_ranks_replay_and_four_class_capacity(self):
        self.setup(acquire=False,combat=False)
        self.unchanged(lambda:self.acquire(M.FEATURE));self.unchanged(lambda:self.acquire(M.CLASS))
        self.a.spec['skills']={'매력':2,'명령':2}
        self.unchanged(lambda:self.acquire(M.TRAINING))
        self.a.spec['skills']={'매력':3,'명령':1}
        self.unchanged(lambda:self.acquire(M.TRAINING))
        self.a.spec['feats']=[M.TRAINING]
        self.unchanged(lambda:TRAINING.register_owned(self.e,self.a,M.TRAINING))
        self.a.spec['feats']=[]
        self.a.spec['skills']={'매력':3,'명령':2}
        training=self.acquire(M.TRAINING);parent=self.acquire(M.CLASS);child=self.acquire(M.FEATURE)
        self.assertEqual(child['source']['clause_id'],M.CLAUSE)
        self.assertEqual(parent['snapshot']['parent_request'],training['request_id'])
        self.assertEqual(child['snapshot']['parent_request'],parent['request_id'])
        F.base_patch(self.a,{'skills':{'매력':1,'명령':1}},reason='later actual skill change')
        self.assertEqual(self.acquire(M.FEATURE),child);self.assertTrue(TFA.validate_actor(self.a))
        items.register_feats(self.e,self.a)
        self.assertTrue(TRAINING.register_owned(self.e,self.a,M.TRAINING))
        self.assertTrue(TRAINING.owns(self.a,M.TRAINING))
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(20)
        self.e.manual_feat(self.a,M.TRAINING,self.a)
        self.assertEqual(TRAINING.bonus(self.a,'save'),2)
        self.assertEqual(self.a.pending_action_loss,{'standard':1})
        self.unchanged(lambda:self.acquire(M.FEATURE,'duplicate'))
        self.setup(acquire=False,combat=False);self.acquire(M.TRAINING)
        self.a.spec['classes']=['class/운동선수','class/멘토','class/지휘관','class/코디네이터']
        self.unchanged(lambda:self.acquire(M.CLASS))
    def test_imported_parent_or_feature_list_never_creates_actual_source_right(self):
        self.setup(acquire=False)
        self.a.spec['classes']=[M.CLASS]
        self.unchanged(lambda:self.acquire(M.FEATURE))
        self.a.spec['feats']=[M.FEATURE]
        self.unchanged(lambda:self.use())
        self.assertFalse(TEMP.live(self.b));self.assertFalse(TEMP.live(self.c))
    def test_explicit_zero_one_two_targets_standard_debt_and_per_recipient_policies(self):
        for count in (0,1,2):
            self.setup();targets=[self.b,self.c][:count]
            policies={t.entity_id:dict(FUNDING,priority='ordinary_first' if t is self.c else 'temporary_first') for t in targets}
            row=self.use(targets,funding=policies)
            self.assertEqual(len(row['targets']),count);self.assertEqual(len(M._uses(self.a)),1)
            self.assertEqual(self.a.pending_action_loss,{'standard':1});self.assertEqual(TEMP.available(self.a),0)
            self.e.start_of_turn(self.a,initiative_count=20)
            self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a.budget['shift'],1)
            self.assertEqual(PRIORITY.records(self.a)[0]['payment']['phase'],'paid')
            self.assertTrue(self.e.validate_state()['valid'])
            for target in targets:
                grant=TEMP.live(target)[0]
                self.assertIs(grant['issuer_actor'],self.a);self.assertEqual(grant['effect']['funding'],policies[target.entity_id])
    def test_illegal_recipient_identity_and_missing_explicit_inputs_are_atomic(self):
        for callback in (lambda:self.use([self.a]),lambda:self.use([self.b,self.b]),lambda:self.use([self.a,self.b,self.c]),
                         lambda:self.use(funding={}),lambda:self.use(allies={}),
                         lambda:self.use(allies={t.entity_id:{'allied':False,'reason':'not allied'} for t in (self.b,self.c)})):
            self.unchanged(callback)
        self.c.side='enemy';self.unchanged(lambda:self.use());self.c.side='party'
        pokemon=Combatant(self.e.r,build_pokemon(self.e.r,'잉어킹',20,name='pokemon-target',moves=[],abilities=[]))
        pokemon.side='party';self.e.gm.add_combatant(pokemon)
        self.unchanged(lambda:self.use([pokemon]))
        fake=Combatant(self.e.r,deepcopy(self.c.spec));self.unchanged(lambda:self.use([fake]))
    def test_two_actual_target_accounts_spend_and_expire_at_next_round_same_count(self):
        self.use();maximum=AP.maximum(self.b)
        self.e.start_of_turn(self.b,initiative_count=19)
        ROLL.prepare(self.e,self.b,self.b,roll_id='moment-roll',kind='accuracy')
        self.e.accuracy_check(self.b,self.c,self.e.r.move('move/울음소리'),fixed_roll=10,roll_id='moment-roll')
        self.assertEqual(self.b.spec.get('ap_spent',0),0);self.assertEqual(TEMP.available(self.b),0)
        self.assertEqual(TEMP.available(self.c),1);self.e.end_of_turn(self.b)
        self.e.end_round();self.assertEqual(TEMP.available(self.c),1)
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertEqual(TEMP.available(self.c),1)
        self.e.at_initiative_count(20);self.assertFalse(TEMP.live(self.b));self.assertFalse(TEMP.live(self.c))
        self.assertEqual(AP.available(self.b),maximum);self.assertTrue(self.e.validate_state()['valid'])
    def test_second_grant_failure_rolls_back_first_ap_delivery_action_and_sequence(self):
        actual=TEMP.grant;calls=[]
        def fail_second(e,actor,**kw):
            calls.append(actor.entity_id)
            if len(calls)==2:raise RuntimeError('second target installation failed')
            return actual(e,actor,**kw)
        with patch.object(TEMP,'grant',side_effect=fail_second):self.unchanged(lambda:self.use(),RuntimeError)
        self.assertEqual(calls,[self.b.entity_id,self.c.entity_id])
    def test_second_communication_failure_rolls_back_first_delivery_before_action(self):
        self.audible(self.c,False);self.unchanged(lambda:self.use())
        self.assertEqual(COMM._state(self.e)['requests'],{});self.assertFalse(M._uses(self.a))
    def test_current_source_retraining_does_not_destroy_already_issued_ap(self):
        self.setup(combat=False);self.use()
        F.base_patch(self.a,{'skills':{'매력':1,'명령':1}},reason='later skill change preserves historical qualification')
        omitted=self.base.decisions(self.e,self.a,M.CLASS,request='moment/omitted-parent')
        self.unchanged(lambda:self.e.retrain_trainer_source(self.a,M.CLASS,**omitted))
        required=self.decisions(M.CLASS)
        self.unchanged(lambda:self.e.retrain_trainer_source(self.a,M.CLASS,**required))
        self.e.retrain_trainer_source(self.a,M.FEATURE,**self.decisions(M.FEATURE))
        self.e.retrain_trainer_source(self.a,M.CLASS,**self.decisions(M.CLASS))
        self.assertEqual(TEMP.available(self.b),1);self.unchanged(lambda:self.use())
        self.restore();self.assertEqual(TEMP.available(self.b),1)
        self.e.advance_time(10);self.assertFalse(TEMP.live(self.b));self.assertFalse(TEMP.live(self.c))
        self.assertTrue(self.e.validate_state()['valid'])
    def test_codec_retains_real_issuer_links_and_rejects_missing_or_changed_producer(self):
        self.use();self.restore();self.assertIs(TEMP.live(self.b)[0]['issuer_actor'],self.a)
        self.assertTrue(self.e.validate_state()['valid'])
        for mutation in ('amount','issuer','ledger','payment','source'):
            self.setup();self.use();row=TEMP.live(self.b)[0]
            if mutation=='amount':row['effect']['amount']=2
            elif mutation=='issuer':row['origin']['issuer_id']=self.c.entity_id
            elif mutation=='ledger':self.a.spec[M.KEY]=[]
            elif mutation=='payment':PRIORITY.records(self.a)[0]['subject_id']='another-use'
            else:self.a.spec[M.KEY][0]['source']['clause_id']='forged'
            self.assertFalse(self.e.validate_state()['valid'])
            with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
    def test_outside_standard_ten_seconds_and_at_will_overlaps_use_existing_funding(self):
        self.setup(combat=False);self.use();self.use()
        self.assertEqual(TEMP.available(self.b),2);self.assertEqual(TEMP.available(self.c),2)
        self.e.advance_time(9);self.restore();self.assertEqual(TEMP.available(self.b),2)
        self.e.advance_time(1);self.assertEqual(TEMP.available(self.b),0);self.assertEqual(TEMP.available(self.c),0)
        self.assertTrue(self.e.validate_state()['valid'])
    def test_second_target_funding_conflict_rolls_back_first_new_grant(self):
        self.setup(combat=False);self.use([self.c],funding={self.c.entity_id:dict(FUNDING,priority='ordinary_first')})
        self.unchanged(lambda:self.use());self.assertFalse(TEMP.live(self.b));self.assertEqual(TEMP.available(self.c),1)
    def test_established_alternative_communication_requires_actual_current_endpoint_delivery(self):
        self.setup(combat=False);self.audible(self.b,mode='visual')
        policy={'id':'established-signals','source':M.TRAINING,'capabilities':[],'requirements':[],
            'mode':'visual','range':None,'path':'visual','medium':[],'consent':{'kind':'none'},'blockers':[],
            'connection':None,'frequency':{'kind':'at_will','uses':1},'retry':None,'distance_exceptions':[]}
        COMM.send(self.e,self.a,self.b,policy,'established Moment of Action signal',request_id='actual-signals')
        self.unchanged(lambda:self.use([self.b],communication={self.b.entity_id:'invented'}))
        self.unchanged(lambda:self.use([self.c],communication={self.c.entity_id:'actual-signals'}))
        self.audible(self.b,False,mode='visual')
        self.unchanged(lambda:self.use([self.b],communication={self.b.entity_id:'actual-signals'}))
        self.audible(self.b,True,mode='visual')
        self.use([self.b],communication={self.b.entity_id:'actual-signals'});self.assertEqual(TEMP.available(self.b),1)
        self.e.advance_time(1);self.unchanged(lambda:self.use([self.b],communication={self.b.entity_id:'actual-signals'}))
    def test_priority_permission_and_outside_standard_failure_are_atomic(self):
        self.e.start_of_turn(self.c,initiative_count=20);self.unchanged(lambda:self.use());self.e.end_of_turn(self.c)
        self.a.conditions.add('넘어짐');self.unchanged(lambda:self.use());self.a.conditions.remove('넘어짐')
        self.use();self.unchanged(lambda:self.use())
        self.setup(combat=False);self.a.hp=0;self.unchanged(lambda:self.use())
        original=MOMENTUM_BASE.CapturedMomentumTests();original.rules=self.errata;original.core=self.rules;original.setup()
        self.e,self.a=original.e,original.a
        self.b,self.c=[Combatant(self.e.r,build_trainer(self.e.r,name,20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[])) for name in ('pending-ally-one','pending-ally-two')]
        self.a.side=self.b.side=self.c.side='party';self.e.everyone.extend([self.b,self.c]);self.e.time_actors(self.e.everyone)
        F.base_patch(self.a,{'skills':dict(self.a.spec['skills'],매력=3,명령=2)},reason='actual prerequisites for new Orders source')
        for uid in (M.TRAINING,M.CLASS,M.FEATURE):self.acquire(uid)
        self.e.end_of_turn(self.a);self.e.end_encounter()
        self.assertTrue(original.capture());self.assertEqual(self.a.spec['capture_attempts']['capture-1']['momentum']['state'],'pending')
        self.unchanged(lambda:self.use())
    def test_core_and_errata_selection_preserve_the_same_book_source_consumer(self):
        self.setup(rules=self.errata);row=self.use([self.b])
        self.assertEqual(row['source']['clause_id'],M.CLAUSE);self.assertEqual(TEMP.available(self.b),1)
        self.assertTrue(self.e.validate_state()['valid'])

if __name__=='__main__':unittest.main()
