"""Book Rider and Ride as One consume actual mounting and native turn slots."""
from copy import copy,deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path('D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import control_mount as M,training_features as T,trainer_feature_acquisition as A
import trainer_retraining as RETRAIN,state_grants as G,state_codec as CODEC
import world_entities as W,initiative as INIT,initiative_schedule as S,turn as TURN
import state_fields as FIELDS,pokemon_party as PARTY


class RideAsOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='all')
        cls.rules.load_source_policy_package((ROOT/'data/examples/scripting-repulse.json').read_text(encoding='utf-8'))

    def setup(self,*,acquire=True,mounted=False):
        self.e=Engine(self.rules,seed=924)
        common=dict(level=20,stats={'hp':60,'atk':10,'def':5,'spa':10,'spd':5,'spe':10},
                    moves=['move/몸통박치기'],abilities=[],movement={'land':6,'swim':3,'sky':0})
        self.a=Combatant(self.rules,dict(deepcopy(common),name='actual rider',kind='trainer',
            skills={'곡예':3,'육상':3,'명령':3,'매력':3},edges=['edge/탑승-기량'],
            feats=[T.AGILITY,T.FOCUSED,T.INSPIRED],classes=[],exp_bank=30))
        self.e.gm.add_combatant(self.a,pos=(0,0),side='party',reason='actual rider')
        mon=dict(deepcopy(common),name='actual mount',kind='pokemon',trainer_id=self.a.entity_id,trainer=self.a.name,
                 skills={'육상':'2d6'},stats=dict(common['stats'],spe=25))
        self.p=Combatant(self.rules,mon)
        self.e.gm.add_combatant(self.p,pos=(0,0),side='party',reason='actual mount')
        self.enemy=Combatant(self.rules,dict(deepcopy(common),name='actual enemy',kind='trainer',
            skills={'육상':3,'명령':3},stats=dict(common['stats'],spe=18)))
        self.e.gm.add_combatant(self.enemy,pos=(1,0),side='foe',reason='actual third participant')
        self.e.gm.observe_loyalty(self.p,6,reason='actual willing mount')
        if acquire:self.acquire(M.RIDER);self.acquire(M.RIDE_AS_ONE)
        if mounted:self.board()

    def acquire(self,uid):return A.acquire_static(self.e,self.a,uid,acquisition_request_id='ride/acquire/'+uid)
    def board(self):
        result=self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)
        self.assertTrue(result['passed']);return result
    def snap(self):return CODEC.dump_engine(self.e)
    def reject(self,fn):
        before=self.snap()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.snap(),before)
    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
    def restore(self):
        ids=[c.entity_id for c in (self.a,self.p,self.enemy)]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
        index=W.actor_index(self.e);self.a,self.p,self.enemy=[index[uid] for uid in ids]
    def train(self):
        return self.e.train_pokemon(self.a,[(self.p,[T.AGILITY])],minutes=30,
            reason='actual completed Agility training',request_id='ride/training',safe=True)
    def schedule(self):
        self.e.prepare_initiative_schedule(self.e.everyone,source='gm/ride-as-one')
        self.e.start_round(self.e.everyone)
    def close(self,actor):self.e.start_of_turn(actor);self.e.end_of_turn(actor)
    def retrain(self,uid):
        owned=RETRAIN._owned(self.a)
        sources={key:'feature:'+self.a.entity_id+':'+key for key in owned}
        native=RETRAIN._native_dependencies(self.e,self.a,owned)
        retained={source:[sources[parent] for parent in native.get(key,[])] for key,source in sources.items() if key!=uid}
        return RETRAIN.retrain(self.e,self.a,uid,request_id='ride/retrain/'+uid,reason='actual retraining',
            gm_decision={'allowed':True,'reason':'actual retained prerequisite review'},retained_dependencies=retained)

    def test_actual_book_acquisition_parents_skill_alternatives_tags_and_historical_replay(self):
        self.setup(acquire=False)
        self.reject(lambda:self.acquire(M.RIDE_AS_ONE))
        self.a.spec['edges']=[];self.reject(lambda:self.acquire(M.RIDER));self.a.spec['edges']=['edge/탑승-기량']
        self.a.spec['feats'].remove(T.AGILITY);self.reject(lambda:self.acquire(M.RIDER));self.a.spec['feats'].append(T.AGILITY)
        FIELDS.base_patch(self.a,{'skills':{'곡예':2,'육상':2}},reason='no Novice riding skill')
        self.reject(lambda:self.acquire(M.RIDER))
        FIELDS.base_patch(self.a,{'skills':{'곡예':2,'육상':3}},reason='Novice Athletics alternative')
        before=self.a.stats['spe'];parent=self.acquire(M.RIDER);child=self.acquire(M.RIDE_AS_ONE)
        self.assertEqual(self.a.stats['spe'],before+2)
        self.assertEqual(parent['source']['span'],[902,904]);self.assertEqual(child['source']['clause_id'],'C04-039')
        FIELDS.base_patch(self.a,{'skills':{'곡예':1,'육상':1}},reason='later ranks do not rewrite acquisition facts')
        self.assertEqual(self.acquire(M.RIDER),parent);self.assertEqual(self.acquire(M.RIDE_AS_ONE),child)
        self.restore();self.assertEqual(self.a.stats['spe'],before+2);self.valid()
        self.setup(acquire=False)
        FIELDS.base_patch(self.a,{'skills':{'곡예':3,'육상':2}},reason='actual acquired Agility with later rank loss; Novice Acrobatics alternative')
        self.assertEqual(self.acquire(M.RIDER)['snapshot']['acrobatics'],3)
        self.valid()

    def test_imported_name_capacity_and_forged_stat_source_do_not_invent_acquisition(self):
        self.setup(acquire=False)
        self.a.spec['classes']=[M.RIDER]
        with self.assertRaisesRegex(ValueError,'source-specific'):self.acquire(M.RIDE_AS_ONE)
        self.a.spec['classes']=['class/선동가','class/로그','class/무술가','class/닌자']
        with self.assertRaises(ValueError):self.acquire(M.RIDER)
        self.a.spec['classes']=[];self.acquire(M.RIDER);self.acquire(M.RIDE_AS_ONE)
        sid='feature:'+self.a.entity_id+':'+M.RIDE_AS_ONE
        self.a.spec[G.KEY]['stat_sources']['spe']['sources'][sid]['acquisition_stat_tag']['delta']=2
        with self.assertRaises(CODEC.StateCodecError):self.snap()

    def test_native_training_doubles_only_agility_while_actual_rider_is_mounted(self):
        self.setup();self.train()
        self.assertEqual((self.e.move_profile(self.p,'land')[0],INIT.value(self.rules,self.p).value),(7,29))
        self.board();self.assertEqual((self.e.move_profile(self.p,'land')[0],INIT.value(self.rules,self.p).value),(8,33))
        self.assertEqual(T.bonus(self.a,'movement'),0)
        self.e.dismount(self.a,reason='actual dismount')
        self.assertEqual((self.e.move_profile(self.p,'land')[0],INIT.value(self.rules,self.p).value),(7,29))
        self.assertTrue(T.records(self.p));self.valid()

    def test_agility_training_and_native_orders_each_double_but_other_regimes_do_not(self):
        self.setup();self.train();self.board();self.e.start_round(self.e.everyone)
        self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual mounted Order path')
        result=self.e.manual_feat(self.a,T.AGILITY,self.p)
        self.assertEqual(result['status'],'applied');self.assertEqual(T.bonus(self.p,'initiative'),16)
        self.assertEqual(self.e.move_profile(self.p,'land')[0],10)
        self.assertEqual(INIT.value(self.rules,self.p,engine=self.e).value,41)
        self.e.start_of_turn(self.a)
        self.assertEqual(T.bonus(self.p,'initiative'),8)
        self.assertEqual(T.bonus(self.p,'accuracy'),0);self.assertEqual(T.bonus(self.p,'evasion'),0)
        self.e.end_of_turn(self.a);self.close(self.p);self.close(self.enemy);self.e.end_round()
        self.e.start_round(self.e.everyone)
        focused=self.e.manual_feat(self.a,T.FOCUSED,self.p)
        self.assertEqual(focused['status'],'applied');self.assertEqual(T.bonus(self.p,'accuracy'),1)
        self.assertEqual(T.bonus(self.p,'initiative'),8)
        self.valid()

    def test_speed_evasion_max_tie_caps_and_existing_disabled_or_physical_evasion(self):
        self.setup(mounted=True)
        self.assertEqual((self.a.evasion('물리',engine=self.e),self.p.evasion('물리',engine=self.e)),(5,5))
        self.e.gm.set_stat(self.p,'spe',value=12,reason='actual equal Speed Evasion')
        self.assertEqual((self.a.evasion('특수',engine=self.e),self.p.evasion('특수',engine=self.e)),(3,3))
        self.e.gm.set_stat(self.a,'def',value=30,reason='independent Physical Evasion')
        self.assertEqual(self.a.evasion('물리',engine=self.e),6)
        self.assertEqual(self.p.evasion('물리',engine=self.e),3)
        self.e.apply_status(self.p,'구속',source='gm/actual stuck')
        self.assertEqual(self.p.evasion('물리',engine=self.e),1)
        self.assertEqual(self.a.evasion('특수',engine=self.e),2)
        self.e.cure_status(self.p,'구속');self.e.gm.set_stat(self.p,'spe',value=40,reason='actual high mount Speed')
        self.e.gm.set_stat(self.a,'spe',value=40,reason='actual high rider Speed')
        self.assertEqual(self.p.evasion('특수',engine=self.e),7)
        self.p.evasion_mod=6
        self.assertEqual(self.p.evasion('특수',engine=self.e),9)
        self.e.dismount(self.a,reason='end actual mounted sharing')
        self.assertEqual(self.a.evasion('특수',engine=self.e),6);self.valid()

    def test_native_attack_and_external_program_consume_the_mounted_evasion(self):
        self.setup(mounted=True);self.e.start_round(self.e.everyone);self.e.start_of_turn(self.enemy)
        before=self.a.hp
        doc=deepcopy(self.rules.source_policy_document('external/repulse'))
        doc['id']='external/ride-as-one-native-attack';variant=doc['variants'][0];variant['inputs']={}
        variant['values']={'operations':[{'id':'mounted-hit','operation':'combat.hit','arguments':{
            'attacker':{'$actor':'actor'},'target':{'$actor':'target'},'move_id':'move/몸통박치기','set_damage':True}}]}
        with patch.object(type(self.e),'d20',new=lambda engine:6):
            result=self.e.execute_source_policy_operations(self.enemy,self.a,doc,request_id='ride/script')
        self.assertEqual(result['status'],'PolicyOperationsCompleted');self.assertEqual(self.a.hp,before)
        self.assertEqual(self.enemy.budget['standard'],0)
        prior=self.snap();self.assertTrue(self.e.execute_source_policy_operations(self.enemy,self.a,doc,request_id='ride/script')['replayed'])
        self.assertEqual(self.snap(),prior);self.valid()

    def test_slower_rider_takes_first_initiative_and_other_turn_survives_codec_and_dismount(self):
        self.setup(mounted=True);self.schedule()
        self.assertEqual(self.e.initiative_schedule_status()['next']['actor_id'],self.p.entity_id)
        self.e.start_of_turn(self.a)
        self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.a.budget,{'standard':1,'shift':1,'swift':1})
        self.assertTrue(TURN.spend(self.e,self.a,'standard'))
        self.e.gm.snapshot('mounted-first');self.e.end_of_turn(self.a);self.e.gm.restore('mounted-first')
        self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.a.budget['standard'],0)
        self.restore()
        self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.a.budget['standard'],0)
        self.e.end_of_turn(self.a);self.e.dismount(self.a,reason='actual dismount after selected turn')
        self.close(self.enemy);self.close(self.p);self.e.end_round()
        self.assertEqual([c['actor'] for c in self.e._turn_closures],[self.a,self.enemy,self.p])
        self.assertEqual(self.a.custom_conditions['combat_turn_serial'],1)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'],1);self.valid()

    def test_faster_mount_can_keep_first_turn_and_each_round_allows_a_fresh_choice(self):
        self.setup(mounted=True);self.schedule();self.close(self.p);self.close(self.enemy);self.close(self.a);self.e.end_round()
        self.assertFalse(self.e._initiative_schedule.get('mounted_exchanges'))
        self.schedule();self.close(self.a);self.close(self.enemy);self.close(self.p);self.e.end_round()
        self.assertEqual(len(self.e._initiative_schedule['mounted_exchanges']),1)
        self.assertEqual(self.a.custom_conditions['combat_turn_serial'],2)
        self.assertEqual(self.p.custom_conditions['combat_turn_serial'],2);self.valid()

    def test_unmounted_foreign_actor_and_already_used_turn_cannot_exchange(self):
        self.setup();self.schedule();self.reject(lambda:self.e.start_of_turn(self.a))
        foreign=copy(self.a)
        self.reject(lambda:self.e.start_of_turn(foreign))
        self.close(self.p);self.close(self.enemy);self.close(self.a);self.e.end_round()
        self.e.end_encounter();self.board();self.schedule();self.close(self.a)
        self.reject(lambda:self.e.start_of_turn(self.a))
        self.close(self.enemy);self.close(self.p);self.e.end_round();self.valid()

    def test_late_native_start_failure_rolls_back_exchange_and_forgery_cannot_restore(self):
        self.setup(mounted=True);self.schedule();before=self.snap()
        self.reject(lambda:self.e.start_of_turn(self.a,initiative_count='invalid-count'))
        with patch('party_actions.require_turn',side_effect=ValueError('actual turn permission')):
            self.reject(lambda:self.e.start_of_turn(self.a))
        with patch('turn.reset_budget',side_effect=ValueError('late real turn reset')):
            with self.assertRaises(ValueError):self.e.start_of_turn(self.a)
        self.assertEqual(self.snap(),before);self.e.start_of_turn(self.a)
        row=self.e._initiative_schedule['mounted_exchanges'][0];row['later']=1
        with self.assertRaises(CODEC.StateCodecError):self.snap()

    def test_source_withdrawal_reverses_only_its_tags_and_stops_new_sharing(self):
        self.setup(mounted=True)
        G._source(self.a,'independent-speed','effect');G.stat(self.a,'spe',3,'independent-speed')
        self.reject(lambda:self.retrain(M.RIDER))
        self.retrain(M.RIDE_AS_ONE)
        self.assertEqual(self.a.stats['spe'],14)
        self.assertEqual(self.a.evasion('특수',engine=self.e),2)
        self.retrain(M.RIDER);self.assertEqual(self.a.stats['spe'],13)
        self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
        self.restore();self.assertEqual(self.a.stats['spe'],13);self.valid()


if __name__=='__main__':unittest.main()
