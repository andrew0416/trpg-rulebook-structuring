"""Commander target transformations enter existing native grouped Order owners."""
from pathlib import Path
from copy import deepcopy
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from commander_fixture import CommanderFixture
from native_scenario_fixture import prepare_body
import commander as C,trainer_feature_acquisition as T,training_features as TRAIN
import priority_limited as PRIORITY,temporary_ap as TEMP,action_points as AP
import moment_of_action as MOMENT,ace_trainer as ACE,chronicler as CH
import world_entities as W


class CommanderNativeOwnerTests(CommanderFixture,unittest.TestCase):
    def test_moment_three_actual_trainer_recipients_share_one_native_priority_producer_and_restore(self):
        self.scene();self.leaders(battle=True)
        for uid in (MOMENT.TRAINING,MOMENT.CLASS,MOMENT.FEATURE):self.acquire(uid)
        self.choice('cheerleader','Cheered')
        extra=Combatant(self.r,{'name':'third actual allied Trainer','kind':'trainer','level':40,
            'stats':{'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':12},'moves':[],'abilities':[],
            'classes':[],'feats':[],'movement':{'land':6},'size':'중형'})
        self.e.gm.add_combatant(extra,pos=(4,5),side='party',reason='actual third Order recipient')
        prepare_body(self.e,extra,size='중형',offsets=[(0,0)],reason='observed actual body');self.hears(extra)
        targets=[self.q,self.s,extra];ids=[a.entity_id for a in targets]
        policy={'priority':'temporary_first','binding_expiry':'end_effect','reason':'explicit actual funding policy'}
        options={'funding':{uid:deepcopy(policy) for uid in ids},
            'allies':{uid:{'allied':True,'reason':'actual same-side party'} for uid in ids}}
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(20);result=self.e.issue_orders(self.a,MOMENT.FEATURE,self.q,modifier=C.BATTLE,
            additional_targets=[self.s,extra],options=options)
        self.assertEqual(set(result['target_ids']),set(ids));self.assertEqual(len(MOMENT._uses(self.a)),1)
        self.assertEqual(len(PRIORITY.records(self.a)),1)
        self.assertEqual(set(MOMENT._uses(self.a)[0]['targets']),set(ids))
        for target in targets:self.assertEqual(TEMP.all_records(target)[0]['effect']['amount'],1)
        self.restore();self.valid()
        self.imported_payload_rejected(MOMENT._uses(self.a)[0]['commander_activation'],'missing/activation','Moment|Commander|acquisition')

    def test_critical_moment_actual_trained_ally_keeps_one_priority_and_scene_use(self):
        import test_book_ace_trainer_full as FIX
        f=FIX.AceTrainerFullTests();f.rules=Rules(ROOT,ruleset='core');f.setup()
        f.family(ACE.CRITICAL);f.all_training();f.train([TRAIN.FOCUSED])
        for uid,options in ((C.CLASS,{'branch':'feat/유린-지시'}),(C.LEADERSHIP,{}),(C.SCHEME,{})):
            T.acquire_static(f.e,f.t,uid,acquisition_request_id='actual-commander/'+uid,**options)
        owner=Combatant(f.rules,{'name':'actual other training owner','kind':'trainer','level':40,
            'stats':{'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':12},'skills':{'명령':6},
            'exp_bank':100,'moves':[],'abilities':[],'classes':[],'feats':[],'movement':{'land':6},'size':'중형'})
        f.e.gm.add_combatant(owner,pos=(10,10),side='party',reason='actual allied training owner')
        prepare_body(f.e,owner,size='중형',offsets=[(0,0)],reason='actual registered Trainer body')
        other=Combatant(f.rules,{'name':'actual allied-owner trained Pokemon','kind':'pokemon','level':40,
            'trainer_id':owner.entity_id,'trainer':owner.name,'species':'피카츄','types':['전기'],
            'stats':{'hp':100,'atk':10,'def':5,'spa':10,'spd':5,'spe':13},'skills':{'육상':'3d6'},
            'moves':['move/막치기'],'abilities':[],'movement':{'land':6},'size':'중형'})
        f.e.gm.add_combatant(other,pos=(11,10),side='party',reason='actual allied-owned Pokemon')
        prepare_body(f.e,other,size='중형',offsets=[(0,0)],reason='actual registered Pokemon body')
        f.e.gm.observe_loyalty(other,6,reason='actual willing Training recipient')
        T.acquire_static(f.e,owner,TRAIN.FOCUSED,acquisition_request_id='actual-other/Focused')
        f.e.train_pokemon(owner,[(other,[TRAIN.FOCUSED])],minutes=30,reason='actual allied-owner Training',
            request_id='actual-other/training',safe=True)
        for target in (f.p,f.q,other,owner):
            f.e.gm.observe_sensory_environment(f.t,target,paths={'auditory':True},present=True,reason='actual Critical Moment delivery')
        f.close();f.e.start_round(f.e.everyone)
        f.reject(lambda:f.e.issue_orders(f.t,ACE.CRITICAL,owner,modifier=C.SCHEME),'Training Feature')
        f.e.issue_orders(f.t,ACE.CRITICAL,f.p,modifier=C.SCHEME,additional_targets=[f.q,other])
        self.assertEqual(len(PRIORITY.records(f.t)),1)
        for target in (f.p,f.q,other):self.assertEqual(TRAIN.bonus(target,'accuracy'),3)
        f.e.start_of_turn(f.t,initiative_count=60)
        self.assertEqual((f.t.budget['standard'],f.t.budget['swift']),(0,0))
        f.restore();f.valid()

    def test_profiling_actual_allied_trainer_consumes_original_ap_and_archived_target_only(self):
        import test_book_chronicler_actions as FIX
        f=FIX.ChroniclerActionTests();f.rules=Rules(ROOT,ruleset='core');f.setup();f.whole()
        for uid,options in ((C.CLASS,{'branch':'feat/유린-지시'}),(C.LEADERSHIP,{}),(C.BATTLE,{})):
            T.acquire_static(f.e,f.t,uid,acquisition_request_id='actual-commander/'+uid,**options)
        f.q=f.add('actual allied Trainer','trainer',(2,4),classes=[],feats=[],exp_bank=100)
        f.archive_subject(f.b,'pokemon','actual-profile-foe');f.communication()
        f.e.gm.observe_sensory_environment(f.t,f.q,paths={'auditory':True},present=True,reason='actual allied Trainer hears Order')
        f.combat(f.t);initial=AP.available(f.t)
        f.e.issue_orders(f.t,CH.PROFILING,f.p,modifier=C.BATTLE,additional_targets=[f.q])
        self.assertEqual(AP.available(f.t),initial-4)
        self.assertEqual((f.t.budget['standard'],f.t.budget['swift']),(0,0))
        f.restore();f.valid();f.next_turn(f.q)
        self.assertEqual(CH.accuracy_bonus(f.e,f.q,f.b,{'id':'move/몸통박치기'}),2)
        self.assertTrue(CH.defensive_ignored(f.e,f.q,f.b))


if __name__=='__main__':unittest.main()
