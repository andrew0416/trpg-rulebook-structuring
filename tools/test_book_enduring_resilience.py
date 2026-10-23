"""Resilience's actual damage/status producers, shared costs and source boundary."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
import enduring_awareness as A,enduring_resilience as R
import trainer_feature_acquisition as TFA,state_fields as FIELDS,state_codec as CODEC
import action_points as AP,frequency as FREQ,condition_instances as CI
import custom_condition_effects as CUSTOM,pokemon_party as PARTY,move_completion as COMPLETE
import class_actor_state_reactions as REACTIONS
import test_book_capture_specialist as RETRAIN_FIXTURE


class ResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='all')
        cls.rules.load_source_policy_package((ROOT/'data/examples/scripting-repulse.json').read_text(encoding='utf-8'))
    def setup(self,*,acquire=True,combat=True):
        self.e=Engine(self.rules,seed=812);self.e.grid=Grid(12,8)
        self.a=Combatant(self.rules,build_trainer(self.rules,'Enduring owner',30,
            {'hp':40,'atk':12,'def':12,'spa':12,'spd':12,'spe':12},abilities=[],
            skills={'육상':5,'집중':3},extra={'classes':[A.ENDURING],'feats':[],'edges':[],'exp_bank':30}))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual Enduring owner')
        self.ps=[]
        for i in range(3):
            pokemon=Combatant(self.rules,build_pokemon(self.rules,'이브이',30,name='defender-'+str(i),
                moves=['몸통박치기'],abilities=['두꺼운지방'],extra={'trainer_id':self.a.entity_id,'trainer':self.a.name,'types':['노말']}))
            self.e.gm.add_combatant(pokemon,pos=(1,i),side='party',reason='actual owned defensive Pokemon')
            self.ps.append(pokemon)
        self.p=self.ps[0]
        self.enemy=Combatant(self.rules,build_pokemon(self.rules,'이브이',30,name='actual attacker',
            moves=['불꽃펀치','사이코노이즈','몸통박치기'],abilities=[],extra={'types':['노말']}))
        self.e.gm.add_combatant(self.enemy,pos=(2,0),side='foe',reason='actual enemy Move producer')
        self.a.spec['feats'].append(A.AWARENESS)
        rows=[{'pokemon':p,'ability':'두꺼운지방','defensive_reason':'actual elemental damage resistance'} for p in self.ps]
        self.e.gm.confirm_awareness(self.a,rows,reason='actual three distinct owned defensive abilities')
        if acquire:self.acquire()
        self.answer(True)
        if combat:self.e.start_round(self.e.everyone);self.e.start_of_turn(self.enemy,initiative_count=20)
    def acquire(self):return TFA.acquire_static(self.e,self.a,R.FEATURE,acquisition_request_id='resilience/acquire')
    def answer(self,value):
        self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!='resilience']
        self.e.rulings.add_answer('resilience',value,reason='explicit actual Resilience decision',scope='permanent')
    def state(self):return CODEC.dump_engine(self.e)
    def valid(self):
        report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
    def reject(self,fn):
        before=self.state()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.state(),before)
    def attack(self,*,natural=20,move='move/불꽃펀치',target=None):
        with patch.object(type(self.e),'d20',new=lambda e:natural):
            return self.e.use_move(self.enemy,target or self.p,move,set_damage=True)
    def restore(self):
        ids=[a.entity_id for a in [self.a,*self.ps,self.enemy]]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.state(),ensure_ascii=False)))
        index={a.entity_id:a for a in self.e.everyone}
        self.a,*others=[index[uid] for uid in ids];self.ps=others[:3];self.p=self.ps[0];self.enemy=others[3]

    def test_book_acquisition_requires_confirmed_awareness_expert_either_skill_and_historical_source(self):
        self.setup(acquire=False,combat=False)
        record=deepcopy(self.a.spec['_awareness_acquisition']);self.a.spec.pop('_awareness_acquisition')
        self.reject(self.acquire);self.a.spec['_awareness_acquisition']=record
        FIELDS.base_patch(self.a,{'skills':{'육상':4,'집중':4}},reason='both only Adept');self.reject(self.acquire)
        FIELDS.base_patch(self.a,{'skills':{'육상':3,'집중':5}},reason='Expert Focus alternative')
        receipt=self.acquire();self.assertEqual(receipt['source']['clause_id'],R.CLAUSE)
        self.assertEqual(receipt['source']['span'],[812,816])
        FIELDS.base_patch(self.a,{'skills':{'육상':3,'집중':3}},reason='later rank loss is not reacquisition')
        self.assertEqual(self.acquire(),receipt);self.valid()
        self.a.spec['feats'].append('Resilience');before=(AP.available(self.a),self.p.hp)
        with self.assertRaises(ValueError):self.e.apply_status(self.p,'화상')
        self.assertEqual((AP.available(self.a),self.p.hp),before)

    def test_native_critical_damage_is_normal_and_same_attack_status_costs_only_two_ap(self):
        self.setup();before=AP.available(self.a);hp=self.p.hp;seen=[]
        original=type(self.e).roll_damage
        def observe(e,attacker,target,move,crit=False,*args,**kw):
            seen.append(crit);return original(e,attacker,target,move,crit,*args,**kw)
        with patch.object(type(self.e),'roll_damage',new=observe), patch.object(
                REACTIONS,'observe_attack_damage',wraps=REACTIONS.observe_attack_damage) as observation:
            dealt=self.attack()
        self.assertEqual(seen,[False]);self.assertGreater(dealt,0);self.assertEqual(hp-self.p.hp,dealt)
        self.assertNotIn('화상',self.p.conditions);self.assertEqual(AP.available(self.a),before-2)
        self.assertEqual(len(R._uses(self.a)),1);self.assertTrue(R._uses(self.a)[0]['trigger']['critical'])
        self.assertIs(observation.call_args.kwargs['critical'],True)
        self.assertEqual(observation.call_args.args[1]['target'].entity_id,self.p.entity_id)
        self.valid()
        self.setup();self.answer(False)
        with patch.object(type(self.e),'roll_damage',new=observe):critical=self.attack()
        self.assertTrue(seen[-1]);self.assertGreater(critical,dealt);self.assertIn('화상',self.p.conditions)
        self.assertFalse(R._uses(self.a));self.valid()

    def test_actual_legacy_parameterized_and_custom_grants_prevent_without_installing_state(self):
        for branch in ('legacy','parameterized','custom','native_custom_move'):
            with self.subTest(branch=branch):
                self.setup();before=AP.available(self.a)
                if branch=='legacy':result=self.e.apply_status(self.p,'화상',source='move/불꽃펀치',applied_by=self.enemy)
                elif branch=='parameterized':
                    result=CI.grant(self.e,self.p,'사슬묶기',source='move/사슬묶기',parameters={'move_id':'move/몸통박치기'},applied_by=self.enemy)
                elif branch=='custom':
                    definition=CUSTOM.definition(self.rules,'move/소금절이')
                    result=CUSTOM.grant(self.e,self.enemy,self.p,definition['raw'],'move/소금절이')
                else:
                    self.attack(natural=10,move='move/사이코노이즈');result=False
                self.assertFalse(result);self.assertFalse(self.p.conditions);self.assertFalse(CI.records(self.p))
                self.assertEqual(AP.available(self.a),before-2);self.assertEqual(len(R._uses(self.a)),1);self.valid()

    def test_target_scene_quota_survives_codec_and_only_new_scene_refreshes_each_pokemon(self):
        self.setup();before=AP.available(self.a)
        self.assertFalse(self.e.apply_status(self.p,'화상'));self.assertFalse(self.e.apply_status(self.ps[1],'화상'))
        self.assertEqual(AP.available(self.a),before-4);self.restore()
        self.assertTrue(self.e.apply_status(self.p,'화상'));self.assertEqual(len(R._uses(self.a)),2)
        scene=FREQ.state(self.a)['scene']
        self.e.end_of_turn(self.enemy);self.e.end_encounter(self.e.everyone)
        self.assertEqual(FREQ.state(self.a)['scene'],scene)
        self.e.cure_status(self.p,'화상');self.assertTrue(self.e.apply_status(self.p,'화상'))
        self.assertEqual(len(R._uses(self.a)),2)
        self.e.end_scene(self.e.everyone);self.assertEqual(FREQ.state(self.a)['scene'],scene+1)
        self.e.start_round(self.e.everyone);self.e.at_initiative_count(20);self.e.cure_status(self.p,'화상')
        self.assertFalse(self.e.apply_status(self.p,'화상'));self.assertEqual(len(R._uses(self.a)),3);self.valid()

    def test_foreign_pokemon_trainer_unconscious_decline_and_insufficient_ap_do_not_activate(self):
        for case in ('foreign','trainer','unconscious','decline','ap'):
            with self.subTest(case=case):
                self.setup();target=self.enemy if case=='foreign' else self.a if case=='trainer' else self.p
                if case=='unconscious':self.e.gm.set_hp(self.a,value=0,reason='actual unavailable trainer')
                elif case=='decline':self.answer(False)
                elif case=='ap':AP.charge(self.a,AP.available(self.a)-1)
                before=AP.available(self.a)
                self.assertTrue(self.e.apply_status(target,'화상'));self.assertFalse(R._uses(self.a))
                self.assertEqual(AP.available(self.a),before);self.valid()

    def test_immunity_duplicate_non_affliction_force_and_pure_damage_preview_do_not_spend(self):
        self.setup();before=AP.available(self.a)
        self.e.gm.set_types(self.p,['불꽃'],reason='actual Burn immunity')
        self.assertFalse(self.e.apply_status(self.p,'화상'));self.assertFalse(R._uses(self.a))
        self.e.gm.set_types(self.p,['노말'],reason='actual ordinary recipient')
        self.assertTrue(self.e.apply_status(self.p,'화상',force=True));self.assertFalse(self.e.apply_status(self.p,'화상'))
        self.assertTrue(self.e.apply_status(self.ps[1],'취약'));self.assertFalse(R._uses(self.a))
        self.e.roll_damage(self.enemy,self.p,self.rules.move('move/몸통박치기'),crit=True,set_damage=True)
        self.assertEqual(AP.available(self.a),before);self.assertFalse(R._uses(self.a));self.valid()
        self.reject(lambda:self.e.manual_feat(self.a,R.FEATURE,self.p))

    def test_actual_owner_transfer_and_source_withdrawal_stop_future_protection_preserve_history(self):
        self.setup(combat=False);self.e.apply_status(self.p,'화상')
        other=Combatant(self.rules,build_trainer(self.rules,'actual new owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),abilities=[]))
        self.e.gm.add_combatant(other,pos=(0,3),side='party',reason='actual transfer owner')
        PARTY.configure(self.e,self.a,mode='unlimited',reason='actual original roster',roster=self.ps)
        PARTY.configure(self.e,other,mode='unlimited',reason='actual empty receiving roster',roster=[])
        PARTY.transfer(self.e,self.a,target=self.p,new_owner=other,reason='actual voluntary transfer',request_id='resilience/transfer')
        self.assertTrue(self.e.apply_status(self.p,'화상'));self.assertEqual(len(R._uses(self.a)),1);self.valid()
        fixture=RETRAIN_FIXTURE.BookCaptureSpecialistTests()
        options=fixture.decisions(self.e,self.a,R.FEATURE,request='resilience/withdraw')
        self.e.retrain_trainer_source(self.a,R.FEATURE,**options)
        self.assertTrue(self.e.apply_status(self.ps[1],'화상'));self.assertEqual(len(R._uses(self.a)),1);self.valid()

    def test_invalid_decision_and_late_native_completion_failure_roll_back_new_reaction(self):
        self.setup();self.answer(['invalid']);self.reject(self.attack);self.answer(True)
        original=COMPLETE.finish_target
        def late(*args,**kw):original(*args,**kw);raise ValueError('after actual Resilience damage and status prevention')
        with patch.object(COMPLETE,'finish_target',side_effect=late):self.reject(self.attack)
        self.attack();self.assertEqual(len(R._uses(self.a)),1);self.valid()
        self.restore();R._uses(self.a)[0]['ap']=0
        self.assertFalse(self.e.validate_state()['valid'])

    def test_external_program_calls_actual_native_attack_and_replay_never_spends_again(self):
        self.setup();doc=deepcopy(self.rules.source_policy_document('external/repulse'))
        doc['id']='external/resilience-native-attack';variant=doc['variants'][0];variant['inputs']={}
        variant['values']={'operations':[{'id':'actual-hit','operation':'combat.hit','arguments':{
            'attacker':{'$actor':'actor'},'target':{'$actor':'target'},'move_id':'move/불꽃펀치','set_damage':True}}]}
        with patch.object(type(self.e),'d20',new=lambda e:20):
            result=self.e.execute_source_policy_operations(self.enemy,self.p,doc,request_id='resilience/script')
        self.assertEqual(result['status'],'PolicyOperationsCompleted');self.assertEqual(len(R._uses(self.a)),1)
        self.assertNotIn('화상',self.p.conditions);before=self.state()
        replay=self.e.execute_source_policy_operations(self.enemy,self.p,doc,request_id='resilience/script')
        self.assertTrue(replay['replayed']);self.assertEqual(before,self.state());self.valid()


if __name__=='__main__':unittest.main()
