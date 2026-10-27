"""Arcanist source choices use actual acquisitions, weapons and native attacks."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import arcanist as A,trainer_feature_acquisition as T,acquired_features as AC
import action_points as AP,frequency as F,optional_weapon_framework as OW
import state_codec as CODEC,state_grants as G,world_entities as W
import weapon_actions as WA,combat_precision_features as CPF,combat_timing as TIME
import turn,move_defense_reactions as DEFENSE,state_fields as SF


class ArcanistFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='fantasy')
        cls.base_rulings=deepcopy(cls.rules.rulings)
        import setup_move_state,stellar_tera_blast
        setup_move_state._policy(cls.rules);stellar_tera_blast._policy(cls.rules)

    def scene(self,*,features=(A.RECOUP,A.INVEST,A.AUTHENTIC,A.META),occult=6,element='물',edition='supplement',positions=((2,2),(3,2),(3,3)),skills_extra=None):
        self.rules.rulings=deepcopy(self.base_rulings)
        self.e=Engine(self.rules,seed=102655);self.e.grid=Grid(20,20);self.edition=edition
        stats={'hp':200,'atk':20,'def':5,'spa':25,'spd':5,'spe':20}
        self.people=[]
        for n,pos in enumerate(positions):
            actor=Combatant(self.rules,build_trainer(self.rules,'Arcanist body '+str(n),40,stats,
                moves=['move/물대포','move/몸통박치기','move/파괴광선','move/방어'],pos=pos,
                side='party' if n==0 else 'foe',skills={'오컬트학':occult,'전투':5,'육상':5,'곡예':5,'직감':5,'집중':5,'은신':5,'포켓몬학':5,'협박':5,**(skills_extra or {})},
                extra={'edges':['edge/원소-교감'] if n==0 else [],
                    'edge_choices':{'edge/원소-교감':element} if n==0 else {},
                    'chronicler_archive_choices':{'class/기록자':'profile'},
                    'movement':{'land':6},'movement_basis':'current'}))
            self.e.gm.add_combatant(actor)
            prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed complete actual Arcanist scene body')
            self.people.append(actor)
        self.a,self.b,self.c=self.people;self.initial_spa=self.a.stats['spa']
        for feature in features:self.acquire(feature)

    def acquire(self,feature=A.CLASS,*,rank=None,manipulation=None,edition=None,request=None):
        if feature!=A.TRAINING:
            parent=(A.META if rank==1 else A.AUTHENTIC) if feature==A.SIGNATURE else A.TRAINING if feature==A.CLASS else A.CLASS
            if A.acquired(self.a,parent)is None:self.acquire(parent,edition=edition)
        selection={'edition':'supplement' if feature==A.TRAINING else edition or self.edition}
        if feature==A.SIGNATURE:selection['manipulation']=manipulation
        return T.acquire_static(self.e,self.a,feature,acquisition_request_id=request or 'arcanist/acquire/'+feature+str(rank),rank=rank,selection=selection)

    def combat(self,actor=None):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.a,initiative_count=20)

    def weapon(self,*,moves=('move/렌딩-스펠','move/베인'),uid='arcanist/soul',kind='소형 근접무기'):
        W.register_object(self.e,uid,location={'kind':'unknown'},reason='actual observed Arcane weapon',owner_id=self.a.entity_id,weight_kg=1,kind='physical_object')
        OW.observe_weapon(self.e,self.a,uid,name=uid,kind=kind,grade='좋음',arcane=True,metal=False,moves=list(moves),reason='actual observed Arcane form and quality')
        OW.bond(self.e,self.a,uid,family='arcane');self.key=OW.equip(self.e,self.a,uid);self.uid=uid
        return uid

    def attack(self,move='move/물대포',*,manipulation=None,roll=10,target=None,actor=None,signature_rank=None,aim=None,**options):
        actor=actor or self.a
        if manipulation:A.arm(self.e,actor,move,manipulation,signature_rank=signature_rank,**options)
        with patch.object(Engine,'d20',return_value=roll):
            weapon_id=self.uid if hasattr(self,'uid') and actor is self.a and move in OW.policy(self.rules)['arcane_moves'] else None
            if weapon_id is not None:
                prepared=WA.prepare(self.e,actor,self.rules.move(move),weapon_id=weapon_id)
                prepared=A.prepare(self.e,actor,prepared);rng=WA.range_spec(self.e,prepared,actor)
                if rng.get('shape') and aim is None:aim=actor.pos if rng['shape']=='burst' else (target or self.b).pos
            return self.e.use_move_on(actor,target or self.b,move,self.e.everyone,weapon_id=weapon_id,set_damage=True,aim=aim)

    def completion(self):return list(self.e._move_completions.values())[-1]
    def temporary_ap(self):
        import moment_of_action as M
        issuer=Combatant(self.rules,build_trainer(self.rules,'actual AP issuer',40,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=[],abilities=[],
            extra={'skills':{'매력':5,'명령':5},'movement':{'land':6},'size':'중형'}))
        self.e.gm.add_combatant(issuer,pos=(2,1),side='party',reason='actual allied Cheerleader')
        prepare_body(self.e,issuer,size='중형',offsets=[(0,0)],reason='actual issuer body')
        for uid in (M.TRAINING,M.CLASS,M.FEATURE):T.acquire_static(self.e,issuer,uid,acquisition_request_id='arcanist/issuer/'+uid)
        self.e.gm.observe_sensory_environment(issuer,self.a,paths={'auditory':True},present=True,reason='actual audible instruction')
        self.e.moment_of_action(issuer,[self.a],funding={self.a.entity_id:{'priority':'temporary_first','binding_expiry':'end_effect','reason':'explicit GM temporary funding expiry choice'}},allies={self.a.entity_id:{'allied':True,'reason':'actual allied relationship'}})
    def rejected(self,fn,pattern='.'):
        return assert_rejected_unchanged(self.e,fn,reason_pattern=pattern)
    def valid(self):
        result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
    def restore(self):
        ids=[a.entity_id for a in self.people]
        self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        self.people=[W.actor_index(self.e)[uid] for uid in ids];self.a,self.b,self.c=self.people

    def test_book_csv_all_acquisitions_real_class_rank_spa_and_replay_codec(self):
        for edition in ('supplement','local_csv'):
            self.scene(edition=edition)
            self.acquire(A.SIGNATURE,rank=1,manipulation='directed_barrier')
            self.acquire(A.SIGNATURE,rank=2,manipulation='energy_link')
            self.assertEqual(len(A.records(self.a)),8)
            self.assertEqual(AC.owned_rule_count(self.a,A.CLASS),1)
            self.assertEqual([r['source_id'] for r in AC.class_instances(self.a)],[A.CLASS])
            self.assertEqual(AC.feature_rank(self.a,A.SIGNATURE),2)
            self.assertEqual(self.a.stats['spa'],self.initial_spa+8)
            for row in A.records(self.a):
                feature=row['feature_id'];snapshot=row['snapshot']
                self.assertEqual(snapshot['source'],A.source(self.rules,feature,snapshot['selection']['edition'],snapshot['rank_number']))
                before=self.e.export_state()
                self.acquire(feature,rank=snapshot['rank_number'],manipulation=snapshot['selection'].get('manipulation'))
                self.assertEqual(self.e.export_state(),before)
            self.valid();self.restore();self.valid()

    def test_prerequisites_exact_boundaries_class_capacity_and_source_tamper(self):
        self.scene(features=(),occult=2,skills_extra={'통찰':5})
        self.rejected(lambda:self.acquire(A.TRAINING),'Occult')
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],오컬트학=3)},reason='actual Novice Occult observation')
        self.acquire();self.rejected(lambda:self.acquire(A.META),'Occult')
        SF.base_patch(self.a,{'skills':dict(self.a.spec['skills'],오컬트학=4)},reason='actual Adept Occult observation')
        self.acquire(A.META);self.rejected(lambda:self.acquire(A.AUTHENTIC),'Occult')
        self.acquire(A.SIGNATURE,rank=1,manipulation='warp_energy')
        self.rejected(lambda:self.acquire(A.SIGNATURE,rank=2,manipulation='lock_of_fate'),'Occult')
        for feature,selection in (('class/닌자',None),('class/오컬트마니아',{'ability':'ability/징조'}),('class/멘토',{'source':'local_translation','skills':['직감','협박'],'tutoring_policy':'kr_errata'})):
            T.acquire_static(self.e,self.a,feature,acquisition_request_id='arcanist/extra/'+feature,selection=selection)
        self.assertEqual(len(AC.class_instances(self.a)),4)
        self.rejected(lambda:T.acquire_static(self.e,self.a,'class/기록자',acquisition_request_id='arcanist/fifth'),'four slots')
        row=A.acquired(self.a,A.META);row['snapshot']['source']['sha256']='0'*64
        with self.assertRaises(ValueError):T.validate_actor(self.a)

    def test_imported_feature_names_and_non_special_trigger_cannot_activate(self):
        self.scene(features=())
        self.a.spec['feats']=[A.CLASS,A.META,A.AUTHENTIC]
        self.rejected(lambda:A.arm(self.e,self.a,'move/물대포','directed_barrier'),'actual acquired')
        self.scene();self.combat()
        A.arm(self.e,self.a,'move/몸통박치기','directed_barrier')
        self.rejected(lambda:self.attack('move/몸통박치기'),'Special')

    def test_energy_finesse_native_even_effect_and_real_weapon_condition(self):
        import attack_damage_history as HISTORY
        for roll,trigger in ((2,True),(3,False),(16,True),(17,True)):
            self.scene();self.weapon();self.combat();before=self.b.hp
            with patch.object(Engine,'accuracy_check',return_value=(True,roll,False)):
                self.attack('move/렌딩-스펠',manipulation='energy_finesse',roll=roll)
            row=self.completion();prepared=row['move']
            self.assertEqual(CPF.effect_natural(self.e,self.a,prepared,roll)==1000,roll%2==0)
            self.assertEqual(self.a.spec['ap_spent'],1)
            self.assertEqual(self.a._action_history.count('swift'),1)
            applications=HISTORY.records(self.b)
            losses=[x for x in applications if x.get('application_kind')=='hp_loss']
            self.assertEqual(len(losses),int(trigger))
            if trigger:
                self.assertEqual(losses[0]['receipt']['source'],'move/렌딩-스펠')
                self.assertEqual(HISTORY.amount(losses[0]),self.e.tick_loss(self.b))
            self.assertEqual(before-self.b.hp,sum(HISTORY.amount(x) for x in applications))
            self.assertTrue(any(x.get('application_kind','damage')=='damage' and HISTORY.amount(x)>0 for x in applications))
            self.assertEqual(CPF.effect_natural(self.e,self.a,self.rules.move('move/물대포'),2),2)
        self.scene();self.combat();A.arm(self.e,self.a,'move/물대포','energy_finesse')
        self.rejected(lambda:self.attack(),'Arcane Weapon Move')

    def test_warp_all_five_real_native_target_shapes_and_nonarea_rejection(self):
        expected={'burst1':('burst',1),'cone2':('cone',2),'close_blast2':('close_blast',2),'line4':('line',4),'two_targets4':(None,None)}
        for mode,shape in expected.items():
            with self.subTest(mode=mode):
                self.scene();self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
                self.attack('move/아케인-퓨리',manipulation='warp_energy',range_mode=mode)
                row=self.completion();rng=WA.range_spec(self.e,row['move'],self.a)
                self.assertEqual((rng.get('shape'),rng.get('size')),shape)
                if mode=='two_targets4':self.assertEqual((rng['origin'],rng['targets']),(4,2))
                self.assertEqual(self.a.move_uses['move/아케인-퓨리'],1)
                self.assertEqual(self.a.spec['ap_spent'],1)
                self.assertEqual(self.a._action_history.count('swift'),1)
        self.scene();self.combat();A.arm(self.e,self.a,'move/물대포','warp_energy',range_mode='burst1')
        self.rejected(lambda:self.attack(),'area Move')

    def test_directed_barrier_real_target_only_dr_and_same_count_full_round_expiry(self):
        self.scene();self.combat();self.attack(manipulation='directed_barrier',roll=1)
        tick=self.e.tick(self.a)
        self.assertEqual(A.reduction(self.e,self.b,self.a),tick)
        self.assertEqual(A.reduction(self.e,self.c,self.a),0)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b,initiative_count=10)
        hp=self.a.hp;self.attack(actor=self.b,target=self.a)
        self.assertLess(self.a.hp,hp)
        self.e.end_of_turn(self.b);self.e.start_round(self.e.everyone)
        self.assertEqual(A.reduction(self.e,self.b,self.a),tick)
        self.e.start_of_turn(self.a,initiative_count=20)
        self.assertEqual(A.reduction(self.e,self.b,self.a),0)

    def test_overdrive_hit_pays_one_unpreventable_tick_aoe_bonus_and_miss_pays_none(self):
        import attack_damage_history as HISTORY
        self.scene(positions=((2,2),(3,2),(4,2)));self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        self.attack('move/아케인-퓨리')
        baseline=[sum(HISTORY.amount(x) for x in HISTORY.records(t)) for t in (self.b,self.c)]
        self.scene(positions=((2,2),(3,2),(4,2)));self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        hp=self.a.hp;tick=self.e.tick(self.a)
        self.attack('move/아케인-퓨리',manipulation='power_overdrive')
        self.assertEqual(self.a.hp,hp-tick)
        self.assertTrue(self.completion()['arcanist']['overdrive_paid'])
        self.assertEqual(self.a.spec['ap_spent'],1)
        self.assertEqual(len(self.completion()['targets']),2)
        self.assertEqual([sum(HISTORY.amount(x) for x in HISTORY.records(t)) for t in (self.b,self.c)],
                         [damage+tick+6 for damage in baseline])
        self.scene();self.combat();hp=self.a.hp
        self.attack(manipulation='power_overdrive',roll=1)
        self.assertEqual(self.a.hp,hp);self.assertFalse(self.completion()['arcanist']['overdrive_paid'])

    def test_berserk_blow_native_critical_target_vulnerable_and_area_refusal(self):
        self.scene();self.combat()
        observed=[];native=Engine.roll_damage
        def observe(engine,attacker,target,move,*args,**kwargs):
            result=native(engine,attacker,target,move,*args,**kwargs)
            observed.append((kwargs.get('crit',args[0] if args else False),result))
            return result
        hp=self.b.hp
        with patch.object(Engine,'roll_damage',observe):
            self.attack(manipulation='berserk_blow',roll=17)
        self.assertEqual(len(observed),1)
        self.assertTrue(observed[0][0]);self.assertGreater(observed[0][1],0)
        self.assertEqual(hp-self.b.hp,observed[0][1])
        self.assertIn('취약',self.b.conditions);self.assertNotIn('취약',self.a.conditions)
        row=self.completion();self.assertEqual(A.critical_bonus(self.e,self.a,row['move']),3)
        self.assertEqual(F.state(self.a)['activations'][A.AUTHENTIC]['used'],1)
        self.scene();self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        A.arm(self.e,self.a,'move/아케인-퓨리','berserk_blow')
        self.rejected(lambda:self.attack('move/아케인-퓨리'),'one-target')

    def test_energy_link_non_normal_next_actual_hit_conversion_not_miss_or_preview(self):
        import attack_damage_history as HISTORY
        self.scene()
        next_attacker=Combatant(self.rules,build_trainer(self.rules,'actual next Normal attacker',40,
            {'hp':200,'atk':20,'def':5,'spa':25,'spd':5,'spe':20},moves=['move/몸통박치기'],
            pos=(4,2),side='party',extra={'movement':{'land':6},'movement_basis':'current'}))
        self.e.gm.add_combatant(next_attacker)
        prepare_body(self.e,next_attacker,size='중형',offsets=[(0,0)],reason='actual additional Normal attack participant')
        self.combat();self.attack(manipulation='energy_link')
        move=self.rules.move('move/몸통박치기')
        converted,boost=A.link_damage(self.e,self.c,self.b,move,actual=False)
        self.assertEqual(converted['type'],'물');self.assertFalse(boost)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.c,initiative_count=10)
        self.attack('move/몸통박치기',actor=self.c,roll=1)
        self.assertFalse([r['arcanist_link'] for r in TIME.records(self.b) if 'arcanist_link'in r][-1]['consumed'])
        self.e.end_of_turn(self.c);self.e.start_of_turn(next_attacker,initiative_count=5)
        hp=self.b.hp
        self.attack('move/몸통박치기',actor=next_attacker,target=self.b,roll=10)
        self.assertTrue(self.completion()['results'][self.b.entity_id]['hit'])
        self.assertLess(self.b.hp,hp)
        self.assertTrue([r['arcanist_link'] for r in TIME.records(self.b) if 'arcanist_link'in r][-1]['consumed'])
        self.assertEqual(HISTORY.last_damage(self.b)['move_type'],'물')

    def test_energy_link_normal_korean_all_and_english_next_source_choice(self):
        for policy in ('korean_all','english_next'):
            self.scene(element='노말');self.weapon();self.combat()
            self.attack('move/렌딩-스펠',manipulation='energy_link',link_policy=policy)
            self.e.end_of_turn(self.a);self.e.start_of_turn(self.c,initiative_count=10)
            self.attack('move/몸통박치기',actor=self.c)
            link=[r['arcanist_link'] for r in TIME.records(self.b) if 'arcanist_link'in r][-1]
            self.assertEqual(link['consumed'],policy=='english_next')
            _,boost=A.link_damage(self.e,self.c,self.b,self.rules.move('move/몸통박치기'),actual=False)
            self.assertEqual(boost,policy=='korean_all')

    def test_enlarged_power_real_ranged_melee_and_existing_area_source_omission(self):
        self.scene();self.combat();self.attack(manipulation='enlarged_power')
        rng=WA.range_spec(self.e,self.completion()['move'],self.a)
        self.assertEqual((rng['shape'],rng['size']),('blast',2))
        self.scene();self.weapon();self.combat();self.attack('move/렌딩-스펠',manipulation='enlarged_power')
        self.assertEqual(WA.range_spec(self.e,self.completion()['move'],self.a)['shape'],'burst')
        self.scene();self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        self.attack('move/아케인-퓨리',manipulation='enlarged_power')
        self.assertEqual(WA.range_spec(self.e,self.completion()['move'],self.a)['size'],3)

    def test_lock_fate_real_intercept_watch_and_shield_cannot_prevent_but_miss_remains(self):
        self.scene();self.combat(self.b);self.attack('move/방어',actor=self.b,target=self.b)
        self.e.end_of_turn(self.b);self.e.start_of_turn(self.a,initiative_count=10)
        hp=self.b.hp;self.attack(manipulation='lock_of_fate')
        self.assertLess(self.b.hp,hp)
        row=self.completion();self.assertTrue(DEFENSE._prohibited(self.e,row['move'],'shield'))
        self.scene();self.combat()
        self.e.watch_move_defense(self.b,[{'actor_id':self.c.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual intended interception')
        hp=self.b.hp;self.attack(manipulation='lock_of_fate',roll=1)
        self.assertEqual(self.b.hp,hp);self.assertIsNone(self.e._passive_pending)

    def test_signature_rank_one_two_costs_scene_quota_and_swift_are_distinct(self):
        for rank,kind,maximum in ((1,'directed_barrier',2),(2,'energy_link',1)):
            self.scene();self.acquire(A.SIGNATURE,rank=1,manipulation='directed_barrier')
            if rank==2:self.acquire(A.SIGNATURE,rank=2,manipulation=kind)
            for _ in range(maximum):
                self.combat();self.attack(manipulation=kind,signature_rank=rank)
                self.assertEqual(self.a.spec.get('ap_spent',0),0)
                self.assertEqual(self.a._action_history.count('swift'),1)
            self.combat();A.arm(self.e,self.a,'move/물대포',kind,signature_rank=rank)
            self.rejected(lambda:self.attack(),'Scene frequency')
            self.assertNotIn(A.AUTHENTIC,F.state(self.a)['activations'])

    def test_recoup_real_miss_restores_daily_and_actual_ap_once_codec(self):
        self.scene();self.combat();before=AP.available(self.a)
        self.attack('move/파괴광선',manipulation='directed_barrier',roll=1)
        token=self.completion()['id'];self.assertEqual(AP.available(self.a),before-1)
        self.restore();A.recoup(self.e,self.a,token)
        self.assertEqual(AP.available(self.a),before)
        self.assertEqual(self.a.move_uses['move/파괴광선'],0)
        self.assertTrue(self.completion()['arcanist']['payment']['refunded'])
        self.rejected(lambda:A.recoup(self.e,self.a,token),'actual completed')
        self.valid()
        self.scene();self.combat();before=AP.available(self.a)
        self.attack(roll=1);token=self.completion()['id']
        self.assertNotIn('arcanist',self.completion())
        A.recoup(self.e,self.a,token)
        self.assertEqual(AP.available(self.a),before)
        self.assertTrue(self.completion()['arcanist_recouped'])

    def test_recoup_partial_hit_non_special_prevented_or_forged_claim_rejected(self):
        self.scene(positions=((2,2),(3,2),(4,2)));self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        with patch.object(Engine,'accuracy_check',side_effect=[(False,1,False),(True,10,False)]):
            self.attack('move/아케인-퓨리',manipulation='power_overdrive')
        self.assertEqual({t.entity_id for t in self.completion()['targets']},{self.b.entity_id,self.c.entity_id})
        self.assertEqual(sorted(r['hit'] for r in self.completion()['results'].values()),[False,True])
        token=self.completion()['id'];self.rejected(lambda:A.recoup(self.e,self.a,token),'missing every target')
        self.scene();self.combat();self.attack('move/몸통박치기',roll=1)
        token=self.completion()['id'];self.rejected(lambda:A.recoup(self.e,self.a,token),'Special Move')
        self.rejected(lambda:A.recoup(self.e,self.a,'claimed/nonexistent'),'actual completed')
        self.scene();self.combat();self.attack(manipulation='directed_barrier')
        row=self.completion();row['results'][self.b.entity_id]['hit']=False
        with self.assertRaisesRegex(ValueError,'native misses'):A.recoup(self.e,self.a,row['id'])
        self.scene();self.combat();self.attack(manipulation='directed_barrier',roll=1)
        token=self.completion()['id'];self.completion()['arcanist']['payment']['ordinary']=99
        with self.assertRaisesRegex(ValueError,'receipt changed'):A.recoup(self.e,self.a,token)

    def test_recoup_signature_and_authentic_restore_only_triggered_frequency(self):
        for signature in (False,True):
            self.scene()
            if signature:
                self.acquire(A.SIGNATURE,rank=1,manipulation='directed_barrier')
                self.acquire(A.SIGNATURE,rank=2,manipulation='energy_link')
            self.combat();self.attack(manipulation='energy_link',signature_rank=2 if signature else None,roll=1)
            row=self.completion();key=row['arcanist']['key']
            A.recoup(self.e,self.a,row['id'])
            self.assertNotIn(key,F.state(self.a)['activations'])
            self.assertEqual(F.state(self.a)['activations'][A.RECOUP]['used'],1)
        self.scene()
        self.attack(manipulation='energy_link',roll=1)
        first=self.completion()['id']
        self.attack('move/파괴광선',manipulation='berserk_blow',roll=1)
        second=self.completion()['id']
        self.assertEqual(F.state(self.a)['activations'][A.AUTHENTIC]['used'],2)
        A.recoup(self.e,self.a,first)
        self.assertEqual(F.state(self.a)['activations'][A.AUTHENTIC]['used'],1)
        self.assertEqual(F.state(self.a)['activations'][A.RECOUP]['used'],1)
        A.recoup(self.e,self.a,second)
        self.assertEqual(F.state(self.a)['activations'][A.AUTHENTIC]['used'],0)
        self.assertEqual(F.state(self.a)['activations'][A.RECOUP]['used'],2)

    def test_recoup_refunds_actual_temporary_spend_without_creating_ordinary_ap(self):
        import temporary_ap as TEMP
        self.scene();self.temporary_ap();self.combat()
        ordinary=self.a.spec.get('ap_spent',0);before=AP.available(self.a)
        self.attack(manipulation='directed_barrier',roll=1)
        row=self.completion();self.assertEqual(row['arcanist']['payment']['ordinary'],0)
        self.assertEqual(TEMP.available(self.a),0)
        spent=TEMP.live(self.a)[0]['payments'][0]
        spent['state']='refunded'
        with self.assertRaisesRegex(ValueError,'actual unique native'):TEMP.validate_world(self.e,W.actor_index(self.e))
        spent['state']='spent'
        A.recoup(self.e,self.a,row['id'])
        self.assertEqual((TEMP.available(self.a),self.a.spec.get('ap_spent',0),AP.available(self.a)),(1,ordinary,before))
        self.restore();self.valid()

    def test_late_native_failure_rolls_back_cost_swift_rng_hp_targets_and_recoup(self):
        self.scene();self.combat();A.arm(self.e,self.a,'move/물대포','power_overdrive')
        before=self.e.export_state()
        observed=[];native=Engine.resolve_attack_damage;hp=(self.a.hp,self.b.hp)
        def late(engine,attacker,target,*args,**kwargs):
            native(engine,attacker,target,*args,**kwargs)
            observed.append((attacker.hp,target.hp))
            raise ValueError('actual late damage failure')
        with patch.object(Engine,'resolve_attack_damage',late):
            with self.assertRaisesRegex(ValueError,'late damage failure'):self.attack()
        self.assertEqual(len(observed),1)
        self.assertLess(observed[0][0],hp[0]);self.assertLess(observed[0][1],hp[1])
        self.assertEqual(self.e.export_state(),before)
        self.attack(roll=1);token=self.completion()['id'];before=self.e.export_state()
        with patch('action_point_account.ActionPointAccount.refund_spend',side_effect=ValueError('actual refund failure')):
            with self.assertRaisesRegex(ValueError,'refund failure'):A.recoup(self.e,self.a,token)
        self.assertEqual(self.e.export_state(),before)

    def test_pending_grouped_weapon_move_restores_native_activation_aliases_and_pays_once(self):
        import passive_events as EVENTS,move_completion as COMPLETE
        from test_native_return_continuation import NativeReturnContinuationTests as RETURNS
        self.scene()
        self.e.gm.set_position(self.c,(4,2),reason='actual second body inside Arcane Fury Cone 2')
        self.weapon(moves=('move/아케인-퓨리','move/베인'));self.combat()
        key=RETURNS.policy(self,'arcanist-grouped-return')
        hp=[target.hp for target in (self.b,self.c)];available=AP.available(self.a)
        with self.assertRaises(EVENTS.PassiveEventPending):
            self.attack('move/아케인-퓨리',manipulation='directed_barrier')
        event=self.e._passive_pending;token=self.completion()['id']
        self.assertEqual([target.entity_id for target in self.completion()['targets']],[self.b.entity_id,self.c.entity_id])
        self.assertLess(self.b.hp,hp[0]);self.assertEqual(self.c.hp,hp[1])
        self.assertEqual((AP.available(self.a),self.a.move_uses['move/아케인-퓨리'],self.a._action_history.count('swift')),
                         (available-1,1,1))
        self.restore();self.valid();first_hp=self.b.hp;rng=self.e.rng.getstate()
        with patch.object(Engine,'d20',side_effect=AssertionError('shared native accuracy cannot reroll')):
            with self.assertRaises(EVENTS.PassiveEventPending):RETURNS.choose(self,event,key)
        later=self.e._passive_pending;self.assertNotEqual(later,event)
        self.assertEqual(self.b.hp,first_hp);self.assertLess(self.c.hp,hp[1])
        self.assertEqual((AP.available(self.a),self.a.move_uses['move/아케인-퓨리'],self.a._action_history.count('swift')),
                         (available-1,1,1))
        self.restore();self.valid();actual_hp=[target.hp for target in (self.b,self.c)]
        with patch.object(Engine,'d20',side_effect=AssertionError('saved native accuracy cannot reroll')):
            total=RETURNS.choose(self,later,key)
        row=self.e._move_completions[token]
        self.assertEqual(total,sum(COMPLETE.recipient_result(row,target)['dealt'] for target in COMPLETE.actual_recipients(row)))
        self.assertEqual((row['phase'],len(row['native_returns'])),('complete',2))
        self.assertEqual([target.hp for target in (self.b,self.c)],actual_hp)
        self.assertEqual((self.e.rng.getstate(),AP.available(self.a),self.a.spec['ap_spent']), (rng,available-1,1))
        self.assertEqual((self.a.move_uses['move/아케인-퓨리'],self.a._action_history.count('swift'),self.a.stages['atk']), (1,1,2))
        self.assertEqual(self.a._action_history.count('standard'),1)
        for returned in (event,later):COMPLETE.require_returned_event(self.e,returned)
        before=self.e.export_state();self.assertEqual(self.e.deliver_passive_event(later),'already_delivered')
        self.assertEqual(self.e.export_state(),before)
        self.restore();self.valid()

    def test_physical_weapon_cached_move_cannot_bypass_actual_source_with_or_without_paid_investment(self):
        for invested in (False,True):
            with self.subTest(invested=invested):
                self.scene();self.weapon()
                if invested:A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트')
                self.combat()
                forbidden='move/아케인-스톰' if invested else 'move/아케인-퓨리'
                target_id=self.b.entity_id
                def attempt(boundary):
                    def forged(e,a):
                        a.custom_conditions['equipped_weapons'][self.key]['available_moves'].append(forbidden)
                        G.materialize(a,'moves')
                        if boundary=='consumer':
                            return e.use_move_on(a,W.actor_index(e)[target_id],forbidden,e.everyone,weapon_id=self.uid,set_damage=True)
                        return e.export_state()
                    return G.transition(self.e,self.a,forged,include_grid=True,include_rulings=True)
                for boundary in ('consumer','codec'):
                    self.rejected(lambda:attempt(boundary),'physical weapon Move permission')
                self.restore();self.valid()

    def test_ordinary_weapon_cached_move_requires_native_choices_and_preserves_legacy_restore(self):
        self.scene(features=())
        weapon={'name':'actual scripted ordinary baton','kind':'소형 근접무기','grade':'간단',
                'moves':['상처내기!'],'extension':{'campaign':'ordinary scripted weapon'}}
        key=turn.equip_weapon(self.e,self.a,weapon);self.combat();target_id=self.b.entity_id
        self.assertEqual(self.a.custom_conditions['equipped_weapons'][key]['weapon'],weapon)
        self.assertIn('move/상처내기',self.a.moves)
        prepared=WA.prepare(self.e,self.a,self.e.r.move('move/상처내기'),weapon_id=key)
        forged=deepcopy(prepared);forged['id']='move/강타'
        self.rejected(lambda:OW.adapt_move(self.e,self.a,forged),'not granted')
        for boundary in ('consumer','codec'):
            def attempt():
                def forged(e,a):
                    a.custom_conditions['equipped_weapons'][key]['available_moves'].append('move/강타')
                    G.materialize(a,'moves')
                    if boundary=='consumer':
                        return e.use_move_on(a,W.actor_index(e)[target_id],'move/강타',e.everyone,weapon_id=key,set_damage=True)
                    return e.export_state()
                return G.transition(self.e,self.a,forged,include_grid=True,include_rulings=True)
            self.rejected(attempt,'physical weapon Move permission')
        self.e.gm.set_skill(self.a,'전투',3,reason='actual ordinary weapon qualification loss')
        self.restore();self.valid();self.assertIn('move/상처내기',self.a.moves)
        self.assertEqual(self.a.custom_conditions['equipped_weapons'][key]['weapon'],weapon)
        self.rejected(lambda:self.e.use_move_on(self.a,self.b,'move/상처내기',self.e.everyone,
            weapon_id=key,set_damage=True),'rank prerequisite')
        self.e.gm.set_skill(self.a,'전투',5,reason='actual ordinary weapon qualification recovery')
        self.combat()
        with patch.object(Engine,'d20',return_value=20):
            self.assertGreater(self.e.use_move_on(self.a,self.b,'move/상처내기',self.e.everyone,
                weapon_id=key,set_damage=True),0)
        self.restore();self.valid()

    def test_living_weapon_cached_move_cannot_bypass_native_borrowing_consumers(self):
        from test_living_weapon_caps_shield_source_revision import LivingWeaponCapsShieldSourceRevisionTests as FIXTURE
        f=FIXTURE();f.world(holder='trainer',species='단칼빙',rank=5)
        f.equip('english_own_living_weapon');f.turn(f.a)
        prepared=WA.prepare(f.e,f.p,f.e.r.move('move/상처내기'),weapon_id=f.key)
        marker=deepcopy(prepared['_living_borrow']);borrower_id=f.p.entity_id;target_id=f.t.entity_id
        for boundary,pattern in (('holder','physical weapon Move permission'),
                ('borrower_prepare','ordinary weapon move requires an equipped granting weapon'),
                ('borrower_adapt','Living Weapon borrowed authority changed'),
                ('codec','physical weapon Move permission')):
            def attempt():
                def forged(e,a):
                    a.custom_conditions['equipped_weapons'][f.key]['available_moves'].append('move/강타')
                    G.materialize(a,'moves');borrower=W.actor_index(e)[borrower_id]
                    if boundary=='holder':
                        return e.use_move_on(a,W.actor_index(e)[target_id],'move/강타',e.everyone,weapon_id=f.key,set_damage=True)
                    if boundary=='borrower_prepare':
                        return WA.prepare(e,borrower,e.r.move('move/강타'),weapon_id=f.key)
                    if boundary=='borrower_adapt':
                        move=deepcopy(e.r.move('move/강타'));move['_living_borrow']=deepcopy(marker)
                        return OW.adapt_move(e,borrower,move)
                    return e.export_state()
                return G.transition(f.e,f.a,forged,include_grid=True,include_rulings=True)
            assert_rejected_unchanged(f.e,attempt,reason_pattern=pattern)
        f.restore();f.turn(f.p)
        with patch.object(Engine,'d20',return_value=20):
            self.assertGreater(f.e.use_move_on(f.p,f.t,'move/상처내기',f.e.everyone,
                weapon_id=f.key,set_damage=True),0)
        self.assertTrue(f.e.validate_state()['valid'])

    def test_investment_two_ap_actual_weapon_moves_equip_release_and_rebind(self):
        self.scene();self.weapon();before=AP.available(self.a)
        sheet_moves=list(self.a.spec['moves']);ordinary=('move/렌딩-스펠','move/베인')
        result=A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트')
        self.assertEqual(AP.available(self.a),before-2)
        self.assertIn('move/아케인-퓨리',self.a.moves);self.assertIn('move/매직-버스트',self.a.moves)
        for mid in ordinary:self.assertIn(mid,self.a.moves)
        self.assertEqual(self.a.spec['moves'],sheet_moves)
        self.assertEqual(self.a.spec['ap_bound'][result['instance']],2)
        self.restore();self.valid()
        for mid in ordinary:self.assertIn(mid,self.a.moves)
        self.assertEqual(self.a.spec['moves'],sheet_moves);self.combat()
        self.attack('move/아케인-퓨리');self.assertEqual(self.a.move_uses['move/아케인-퓨리'],1)
        turn.unequip_weapon(self.e,self.a,self.key)
        self.assertNotIn('move/아케인-퓨리',self.a.moves);self.assertIn(A.BIND,self.a.spec)
        for mid in ordinary:self.assertNotIn(mid,self.a.moves)
        self.assertEqual(self.a.spec['moves'],sheet_moves)
        self.key=OW.equip(self.e,self.a,self.uid)
        self.assertIn('move/아케인-퓨리',self.a.moves)
        self.combat();A.release_investment(self.e,self.a)
        self.assertEqual(AP.available(self.a),before);self.assertNotIn('move/아케인-퓨리',self.a.moves)
        self.assertIn('move/렌딩-스펠',self.a.moves);self.attack('move/렌딩-스펠');self.valid()
        self.assertEqual(self.a.spec['moves'],sheet_moves)

    def test_investment_duplicate_wrong_form_second_binding_replacement_and_rollback(self):
        self.scene();self.weapon()
        self.rejected(lambda:A.invest(self.e,self.a,'move/렌딩-스펠','move/매직-버스트'),'duplicate')
        self.rejected(lambda:A.invest(self.e,self.a,'move/아케인-퓨리','move/아케인-스톰'),'weapon form')
        with patch('arcanist.reconcile_investment',side_effect=ValueError('actual grant failure')):
            self.rejected(lambda:A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트'),'grant failure')
        result=A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트')
        self.rejected(lambda:A.invest(self.e,self.a,'move/레조넌스-빔','move/원뿔의-힘'),'only one')
        W.register_object(self.e,'arcanist/new',location={'kind':'unknown'},reason='actual new Arcane focus',owner_id=self.a.entity_id,weight_kg=1,kind='physical_object')
        OW.observe_weapon(self.e,self.a,'arcanist/new',name='new focus',kind='소형 근접무기',grade='좋음',arcane=True,metal=False,moves=[],reason='actual replacement form')
        OW.bond(self.e,self.a,'arcanist/new',family='arcane')
        self.assertNotIn(A.BIND,self.a.spec);self.assertNotIn(result['instance'],self.a.spec['ap_bound'])
        self.assertNotIn('move/아케인-퓨리',self.a.moves);self.valid()

    def test_investment_real_temporary_funding_expiry_ends_same_reservation(self):
        import temporary_ap as TEMP
        self.scene();self.weapon();self.temporary_ap()
        self.assertEqual(TEMP.available(self.a),1)
        result=A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트')
        self.restore();self.e.advance_time(10)
        self.assertNotIn(A.BIND,self.a.spec);self.assertNotIn(result['instance'],self.a.spec['ap_bound'])
        self.assertNotIn('move/아케인-퓨리',self.a.moves);self.assertIn('move/렌딩-스펠',self.a.moves)
        self.valid()

    def test_investment_source_withdrawal_releases_only_actual_owned_reservation(self):
        self.scene();self.weapon();A.invest(self.e,self.a,'move/아케인-퓨리','move/매직-버스트')
        sid=next(sid for sid,row in G.state(self.a)['sources'].items() if row.get('static_acquisition',{}).get('feature_id')==A.INVEST)
        before=self.a.stats['spa']
        def apply(e,a):
            G.revoke(a,sid,engine=e);a.spec['feats'].remove(A.INVEST)
        G.transition(self.e,self.a,apply)
        self.assertNotIn(A.BIND,self.a.spec);self.assertFalse(self.a.spec['ap_bound'])
        self.assertEqual(self.a.stats['spa'],before-1)
        self.assertNotIn('move/아케인-퓨리',self.a.moves);self.assertIn('move/렌딩-스펠',self.a.moves)
        self.valid();self.restore();self.valid()


if __name__=='__main__':unittest.main()
