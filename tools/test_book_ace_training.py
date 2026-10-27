"""Ace Trainer's two book contracts share actual training, AP and base CS owners."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules
import test_category2_training_state as fixture
import training_features as T
import action_points as AP
import combat_stage_sources as CS
import downtime as DT
import effects as FX
import pokemon_party as PARTY
import state_codec as CODEC
import state_grants as G


class AceTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')

    def setUp(self):
        helper=fixture.TrainingStateTests()
        helper.r=self.rules
        helper.setUp()
        self.e,self.t,self.ps,self.other=helper.e,helper.t,helper.ps,helper.enemy
        self.t.spec['classes']=[T.ACE]

    def train(self, targets=None, *, stats=None, regimes=None, source='C03-123', request='ace-1', **options):
        targets=self.ps if targets is None else targets
        stats={p.entity_id:s for p,s in zip(targets,CS.STATS)} if stats is None else stats
        return self.e.train_pokemon(self.t,[(p,[] if regimes is None else regimes) for p in targets],
            minutes=options.pop('minutes',30),reason='observed actual Ace training',request_id=request,
            safe=options.pop('safe',True),trained_stats=stats,source_clause_id=source,**options)

    def state(self):
        actors=[self.t,*self.ps,self.other]
        return deepcopy((self.e.elapsed_seconds,self.e.rng.getstate(),getattr(self.e,'_activity_jobs',None),
            [(p.spec,p.stages,p.registry,p.custom_conditions,getattr(p,'_action_history',[])) for p in actors]),
            {id(actor):('actor',actor.entity_id) for actor in actors})

    def test_exact_book_sources_and_distinct_training_feature_prerequisites(self):
        for clause,expected in T.ACE_SOURCES.items():
            with self.subTest(source=clause):
                self.assertEqual(hashlib.sha256((ROOT/expected['file']).read_bytes()).hexdigest(),expected['sha256'])
                self.assertEqual(T._ace_source(self.rules,clause),expected)
        self.t.spec['feats']=[]
        before=self.state()
        with self.assertRaisesRegex(ValueError,'Training feature'):self.train()
        self.assertEqual(self.state(),before)
        receipt=self.train(source='C04-009')
        self.assertEqual(receipt['source_clause_id'],'C04-009')
        self.assertEqual(self.t.spec['ap_removed'],1)
        self.assertEqual([p.stages[s] for p,s in zip(self.ps,CS.STATS)],[1]*4)

    def test_one_real_session_trains_each_recipient_and_drains_only_one_AP(self):
        available=AP.available(self.t)
        receipt=self.train(regimes=[T.FOCUSED])
        self.assertEqual((self.e.elapsed_seconds,self.t._action_history,self.t.spec['ap_removed']),(1800,['extended'],1))
        self.assertEqual(AP.available(self.t),available-1)
        self.assertFalse(self.t.spec.get('ap_spent',0))
        self.assertEqual(len(receipt['trained_stat_sources']),len(self.ps))
        for p,stat in zip(self.ps,CS.STATS):
            self.assertEqual(T.bonus(p,'accuracy'),1)
            self.assertEqual(p.staged(stat),int(p.stats[stat]*1.2))
            self.assertEqual(sum(CS.total(CS.validate(p),s) for s in CS.STATS),1)
            self.assertEqual(len(T.validate_trained(p)),1)
        self.assertFalse(self.t.spec.get('experience_training'))
        self.assertTrue(self.e.validate_state()['valid'])

    def test_completed_request_replays_after_rest_and_lost_qualification_without_repayment(self):
        receipt=self.train()
        DT.extended_rest(self.e,self.t,4)
        DT.extended_rest(self.e,self.ps[0],4)
        self.t.spec['classes']=[]
        self.t.spec['feats']=[]
        self.t.spec['skills']['명령']=1
        before=self.state()
        self.assertEqual(self.train(),receipt)
        self.assertEqual(self.state(),before)
        self.assertFalse(T.stat_records(self.ps[0]))
        with self.assertRaises(ValueError):self.train(request='new-ace')
        with self.assertRaises(ValueError):self.train(minutes=31)
        self.assertEqual(self.state(),before)

    def test_invalid_source_stats_duration_ownership_AP_and_qualification_are_atomic(self):
        invalid=[{'minutes':29},{'safe':False},{'source':'C04-010'},
            {'stats':{}},{'stats':{p.entity_id:'hp' for p in self.ps}},
            {'stats':{**{p.entity_id:'atk' for p in self.ps},'unknown':'spe'}},
            {'targets':[self.ps[0],self.ps[0]],'stats':{self.ps[0].entity_id:'atk'}},
            {'targets':[self.other],'stats':{self.other.entity_id:'atk'}}]
        for options in invalid:
            with self.subTest(options=options):
                before=self.state()
                with self.assertRaises(ValueError):self.train(**options)
                self.assertEqual(self.state(),before)
        for field,value in [('ap_removed',AP.maximum(self.t)),('classes',[]),('skills',{'명령':2})]:
            old=deepcopy(self.t.spec.get(field))
            self.t.spec[field]=value
            before=self.state()
            with self.subTest(field=field):
                with self.assertRaises(ValueError):self.train()
                self.assertEqual(self.state(),before)
            if old is None:self.t.spec.pop(field,None)
            else:self.t.spec[field]=old
        self.e.encounter_active=True
        before=self.state()
        with self.assertRaises(ValueError):self.train()
        self.assertEqual(self.state(),before)

    def test_stat_replacement_uses_one_slot_and_preserves_independent_training(self):
        p=self.ps[0]
        self.e.train_pokemon(self.t,[(p,[T.FOCUSED])],minutes=30,reason='ordinary training',request_id='ordinary',safe=True)
        self.train([p],stats={p.entity_id:'atk'})
        self.assertEqual((T.bonus(p,'accuracy'),p.stages['atk']),(1,1))
        self.train([p],stats={p.entity_id:'spe'},request='replacement')
        self.assertEqual((p.stages['atk'],p.stages['spe'],len(T.stat_records(p))),(0,1,1))
        self.assertEqual(T.bonus(p,'accuracy'),1)
        self.e.train_pokemon(self.t,[(p,[T.AGILITY])],minutes=30,reason='new ordinary regime',request_id='ordinary-2',safe=True)
        self.assertEqual((T.bonus(p,'accuracy'),T.bonus(p,'movement'),p.stages['spe']),(0,1,1))
        self.assertEqual(self.t.spec['ap_removed'],2)

    def test_actual_completed_hour_can_fund_stat_training_without_a_second_clock_or_credit_reuse(self):
        self.e.complete_training_hour(self.t,self.ps,safe=True,reason='actual completed training hour',request_id='ace-hour')
        jobs=len(self.e._activity_jobs['jobs'])
        receipt=self.train(from_training=True)
        self.assertEqual((self.e.elapsed_seconds,len(self.e._activity_jobs['jobs'])),(3600,jobs))
        self.assertEqual((receipt['time_cost_seconds'],self.t.spec['ap_removed']),(0,1))
        self.assertTrue(all(T.stat_records(p) for p in self.ps))
        before=self.state()
        with self.assertRaises(ValueError):self.train(from_training=True,request='reuse-hour')
        self.assertEqual(self.state(),before)

    def test_actual_stage_resets_and_capped_source_withdrawal_preserve_independent_CS(self):
        p=self.ps[0]
        self.e.gm.set_stage(p,'atk',value=6,reason='actual ordinary stage')
        self.train([p],stats={p.entity_id:'atk'})
        self.assertEqual(p.stages['atk'],6)
        self.e.change_stage(p,'atk',-2)
        self.assertEqual(p.stages['atk'],4)
        source=T.stat_records(p)[0][G.TAG]
        G.revoke(p,source,engine=self.e)
        self.assertEqual(p.stages['atk'],3)
        self.assertFalse(T.stat_records(p))
        self.train([p],stats={p.entity_id:'def'},request='reset-training')
        reset=next(row for row in self.rules.moves_mech['move/흑안개']['effects'] if row['type']=='reset_stages')
        FX.h_reset_stages(self.e,p,p,{**reset,'target':'self'},{})
        self.assertEqual((p.stages['atk'],p.stages['def']),(0,1))
        self.e.end_encounter([self.t,p])
        self.assertEqual(p.stages['def'],1)

    def test_recipient_rest_expires_only_its_stat_while_trainer_rest_recovers_AP_separately(self):
        self.train(regimes=[T.FOCUSED])
        self.e.end_scene()
        self.assertEqual(self.t.spec['ap_removed'],1)
        DT.extended_rest(self.e,self.ps[0],4)
        self.assertFalse(T.stat_records(self.ps[0]))
        self.assertEqual(T.bonus(self.ps[0],'accuracy'),1)
        self.assertTrue(T.stat_records(self.ps[1]))
        self.assertEqual(self.t.spec['ap_removed'],1)
        DT.extended_rest(self.e,self.t,4)
        self.assertEqual(self.t.spec['ap_removed'],0)
        self.assertTrue(T.stat_records(self.ps[1]))
        self.assertEqual(T.bonus(self.ps[1],'accuracy'),0)
        DT.extended_rest(self.e,self.ps[1],4)
        self.assertFalse(T.stat_records(self.ps[1]))

    def test_native_codec_GM_restore_and_transfer_keep_past_training_until_recipient_rest(self):
        self.train()
        self.e.gm.snapshot('ace-trained')
        DT.extended_rest(self.e,self.ps[0],4)
        self.e.gm.restore('ace-trained')
        self.assertIs(T.stat_records(self.ps[0])[0]['owner'],self.t)
        engine=CODEC.load_engine(self.rules,json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        actors={a.entity_id:a for a in engine.everyone}
        owner,target,other=actors[self.t.entity_id],actors[self.ps[0].entity_id],actors[self.other.entity_id]
        self.assertIs(T.stat_records(target)[0]['owner'],owner)
        PARTY.configure(engine,owner,mode='unlimited',reason='actual roster',roster=[actors[p.entity_id] for p in self.ps])
        PARTY.configure(engine,other,mode='unlimited',reason='actual empty roster',roster=[])
        PARTY.transfer(engine,owner,target=target,new_owner=other,reason='actual transfer',request_id='ace-transfer')
        self.assertEqual(target.stages['atk'],1)
        self.assertIs(T.stat_records(target)[0]['owner'],owner)
        self.assertTrue(engine.validate_state()['valid'])
        DT.extended_rest(engine,target,4)
        self.assertEqual(target.stages['atk'],0)
        self.assertFalse(T.stat_records(target))

    def test_failure_after_first_actual_base_stage_rolls_back_time_action_AP_and_all_recipients(self):
        original=CS.add_base
        calls=[]
        def fail_second(actor,*args,**kwargs):
            calls.append(actor.entity_id)
            if len(calls)==2:raise ValueError('injected second actual trained source failure')
            return original(actor,*args,**kwargs)
        before=self.state()
        with patch.object(CS,'add_base',side_effect=fail_second):
            with self.assertRaisesRegex(ValueError,'injected second'):self.train()
        self.assertEqual(len(calls),2)
        self.assertEqual(self.state(),before)
        self.assertTrue(all(not T.stat_records(p) for p in self.ps))

    def test_native_world_validation_rejects_forged_recipient_source_or_second_trained_stat(self):
        self.train()
        saved=CODEC.dump_engine(self.e)
        p=self.ps[0]
        row=T.stat_records(p)[0]
        source=row[G.TAG]
        p.spec[G.KEY]['sources'][source]['stat']='spe'
        with self.assertRaisesRegex(ValueError,'trained stat'):T.validate_trained(p)
        self.assertFalse(self.e.validate_state()['valid'])
        engine=CODEC.load_engine(self.rules,json.loads(json.dumps(saved,ensure_ascii=False)))
        target=next(a for a in engine.everyone if a.entity_id==p.entity_id)
        target.registry.append(dict(T.stat_records(target)[0]))
        with self.assertRaisesRegex(ValueError,'one trained'):T.validate_trained(target)
        def node(payload,reference):return payload['nodes'][reference['$ref']]
        def field(payload,reference,key):return dict(node(payload,reference)['items'])[key]
        for tamper in ('removed row','changed session','changed recorded source'):
            with self.subTest(tamper=tamper):
                payload=deepcopy(saved)
                target_node=next(n for n in payload['nodes'].values() if n['kind']=='actor' and n['entity_id']==p.entity_id)
                registry=node(payload,field(payload,target_node['attrs'],'registry'))
                live_ref=next(ref for ref in registry['items'] if dict(node(payload,ref)['items']).get(G.TAG)==source)
                if tamper=='removed row':
                    registry['items'].remove(live_ref)
                    del payload['nodes'][live_ref['$ref']]
                elif tamper=='changed session':
                    next(pair for pair in node(payload,live_ref)['items'] if pair[0]=='session')[1]='uncompleted-session'
                else:
                    owner_node=next(n for n in payload['nodes'].values() if n['kind']=='actor' and n['entity_id']==self.t.entity_id)
                    history=field(payload,field(payload,owner_node['attrs'],'custom_conditions'),'_training_sessions')
                    session=field(payload,history,'ace-1')
                    entries=node(payload,field(payload,session,'trained_stat_sources'))
                    entry=next(ref for ref in entries['items'] if dict(node(payload,ref)['items']).get('pokemon_id')==p.entity_id)
                    next(pair for pair in node(payload,entry)['items'] if pair[0]=='source')[1]='unrecorded-trained-source'
                with self.assertRaisesRegex(CODEC.StateCodecError,'training_reward_contract'):
                    CODEC.load_engine(self.rules,json.loads(json.dumps(payload,ensure_ascii=False)))


if __name__=='__main__':unittest.main()
