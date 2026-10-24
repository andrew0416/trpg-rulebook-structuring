"""Q30 complete source definitions through actual grants and completed attacks."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Combatant,Rules
import fast_combat as FAST
import items as ITEMS
import move_completion as COMPLETE
import native_scenario_fixture as NATIVE
import optional_weapon_framework as FW
import state_codec as CODEC
import state_grants as G
import static_feature_state_grants as STATIC
import turn as TURN
import weapon_actions as WEAPONS
import world_entities as WORLD

WATER='move/물대포'
TACKLE='move/몸통박치기'


class FantasyQ30SourceVariantTests(unittest.TestCase):
    def world(self,*,fiery=False,baseline=()):
        def actor(key,pos,side,holder=False):
            extra={'skills':{'전투':7,'육상':7,'집중':7,'오컬트학':3},
                'movement':{'land':6,'power':3},'movement_basis':'current',
                'feats':([STATIC.FIERY_OWNER] if fiery else [FW.STEELHEART]) if holder else [],
                'edges':['edge/원소-교감'] if holder and not fiery else [],
                'edge_choices':{'edge/원소-교감':'강철'} if holder and not fiery else {},
                'static_feature_choices':{STATIC.FIERY_OWNER:'spa'} if holder and fiery else {},
                'capabilities':list(baseline) if holder else []}
            stats=dict.fromkeys(('hp','atk','def','spa','spd','spe'),30);stats['hp']=1000
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':40,'stats':stats,
                'moves':[TACKLE,WATER],'abilities':[],'pos':pos,'side':side,'extra':extra},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual Q30 holder and opposing combatant bodies'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=149203,
            grid={'width':12,'height':8},actors=[actor('holder',(2,2),'party',True),
                actor('first',(3,2),'foe'),actor('second',(2,3),'foe')])
        self.a,self.b,self.c=[actors[key] for key in ('holder','first','second')]
        for actor in self.e.everyone:ITEMS.register_feats(self.e,actor)

    def choice(self,choices,value):
        return {'value':value,'reason':'actual complete Q30 source definition selected',
                'scope':choices(self.e)['decision_scope']}

    def ordinary(self):
        return TURN.equip_weapon(self.e,self.a,{'name':'ordinary Q30 staff','kind':'소형 근접무기','grade':'간단','moves':[]})

    def turn(self,actor,*,new_round=False):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        if new_round or not self.e.encounter_active:self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=20)

    def hit(self,actor,target,move,*,tick=False,face=15,**options):
        # Reset through the existing budget owner for another controlled paid
        # activation in this test turn; no completion/history or free grant is made.
        TURN.reset_budget(self.e,actor)
        hp=target.hp;before=set(getattr(self.e,COMPLETE.KEY,{}));uses=actor.move_uses.get(move,0)
        with patch.object(FAST,'roll',return_value=face):
            dealt=self.e.use_move(actor,target,move,set_damage=True,**options)
        row=next(row for key,row in getattr(self.e,COMPLETE.KEY).items() if key not in before)
        result=COMPLETE.recipient_result(row,target)
        self.assertEqual((result['hit'],result['cancelled']),(face!=1,False))
        self.assertEqual(target.hp,hp-dealt-(self.e.tick_loss(target) if tick else 0))
        self.assertEqual(actor.budget['standard'],0)
        self.assertEqual(actor.move_uses[move],uses+1)
        return row

    def restore(self):
        ids=[a.entity_id for a in (self.a,self.b,self.c)]
        self.e=CODEC.load_engine(Rules(str(ROOT),ruleset='all'),json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
        self.a,self.b,self.c=[WORLD.actor_index(self.e)[uid] for uid in ids]

    def test_fiery_complete_grants_reconcile_native_struggle_warmth_immunity_stat_and_restore(self):
        self.world(fiery=True);source='feature:'+self.a.entity_id+':'+STATIC.FIERY_OWNER
        initial=self.a.stats['spa'];self.assertEqual(initial,self.a.spec['stats']['spa']+1)
        receipt=self.a.spec[G.KEY]['sources'][source]
        self.assertEqual((receipt['fiery_variant'],receipt['fiery_source_choice']),('korean_firestarter',None))
        self.assertEqual(receipt['grants']['capabilities'],['불쏘시개'])
        self.turn(self.a)
        row=self.hit(self.a,self.b,'struggle',struggle_choice={'capability':'Firestarter','special':True})
        self.assertEqual((row['target_moves'][self.b.entity_id]['type'],row['target_moves'][self.b.entity_id]['class']),('불꽃','특수'))
        choice=self.choice(STATIC.fiery_soul_source_choices,'english_heater')
        STATIC.select_fiery_soul_source(self.e,self.a,choice)
        self.assertEqual(self.a.stats['spa'],initial)
        self.assertEqual(self.a.spec[G.KEY]['sources'][source]['grants']['capabilities'],['따끈따끈'])
        self.assertEqual(self.e.capability_traits(self.a)['thermal_descriptions'],['warm'])
        self.e.apply_status(self.a,'화상');self.assertNotIn('화상',self.a.conditions)
        state=deepcopy(self.a.spec[G.KEY]);STATIC.select_fiery_soul_source(self.e,self.a,choice)
        ITEMS.register_feats(self.e,self.a);self.assertEqual(self.a.spec[G.KEY],state)
        NATIVE.assert_rejected_unchanged(self.e,lambda:self.e.use_move(self.a,self.b,'struggle',
            struggle_choice={'capability':'Firestarter','special':True}),reason_pattern='actual Struggle capability')
        self.e.gm.snapshot('q30-heater');self.e.gm.restore('q30-heater');self.restore()
        self.assertEqual(self.a.spec[G.KEY]['sources'][source]['fiery_source_choice'],choice)
        self.assertEqual(self.e.capability_traits(self.a)['thermal_descriptions'],['warm'])
        self.assertEqual(self.a.stats['spa'],initial)
        self.e.apply_status(self.a,'화상');self.assertNotIn('화상',self.a.conditions)
        self.a.spec['feats']=[];ITEMS.register_feats(self.e,self.a)
        self.assertNotIn('따끈따끈',G.effective_capabilities(self.a))
        self.assertEqual(self.a.stats['spa'],initial-1);self.assertNotIn('화상',self.a.status_immune)

    def test_fiery_source_scope_and_real_actor_reject_atomically_preserving_independent_baseline(self):
        self.world(fiery=True,baseline=['불쏘시개'])
        choice=self.choice(STATIC.fiery_soul_source_choices,'english_heater')
        bad=deepcopy(choice);bad['scope']['profile_hash']='not-current-profile'
        clone=Combatant(self.e.r,deepcopy(self.a.spec))
        for actor,decision,pattern in ((self.a,bad,'scope changed'),(self.b,choice,'actual current owned'),
                (clone,choice,'actual registered')):
            NATIVE.assert_rejected_unchanged(self.e,lambda a=actor,d=decision:STATIC.select_fiery_soul_source(self.e,a,d),reason_pattern=pattern)
        STATIC.select_fiery_soul_source(self.e,self.a,choice)
        self.assertEqual(set(G.effective_capabilities(self.a)),{'불쏘시개','따끈따끈'})
        self.a.spec['feats']=[];ITEMS.register_feats(self.e,self.a)
        self.assertEqual(G.effective_capabilities(self.a),['불쏘시개'])
        self.turn(self.a)
        row=self.hit(self.a,self.b,'struggle',struggle_choice={'capability':'Firestarter','special':False})
        self.assertEqual(row['target_moves'][self.b.entity_id]['type'],'불꽃')
        NATIVE.assert_rejected_unchanged(self.e,lambda:STATIC.select_fiery_soul_source(self.e,self.a,choice),reason_pattern='actual current owned')

    def test_incoming_default_requires_effective_melee_and_ticks_actual_ordinary_weapon_once(self):
        self.world();key=self.ordinary()
        self.assertIsNone(FW.profile_for_weapon(self.e,self.a,self.a.custom_conditions['equipped_weapons'][key]['weapon']))
        self.turn(self.b);ranged=self.hit(self.b,self.a,WATER)
        self.assertIsInstance(WEAPONS.range_spec(self.e,ranged['target_moves'][self.a.entity_id],self.b)['origin'],int)
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[])
        self.turn(self.c);melee=self.hit(self.c,self.a,TACKLE)
        self.assertEqual(WEAPONS.range_spec(self.e,melee['target_moves'][self.a.entity_id],self.c)['origin'],'melee')
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[self.c.entity_id])
        self.assertEqual((self.a.spec[FW.HITS]['policy_variant'],self.a.spec[FW.HITS]['source_choice']),('english_incoming_melee',None))
        self.turn(self.a)
        self.hit(self.a,self.b,key)
        row=self.hit(self.a,self.c,key,tick=True)
        state=deepcopy((self.a.spec[FW.HITS],self.c.hp,self.a.budget,self.a.move_uses))
        COMPLETE.finish_target(self.e,row['id'],self.a,self.c,**{k:row['results'][self.c.entity_id][k] for k in ('hit','dealt','cancelled')})
        FW.observe_hit(self.e,row,self.a,self.c)
        self.assertEqual((self.a.spec[FW.HITS],self.c.hp,self.a.budget,self.a.move_uses),state)
        self.e.gm.snapshot('q30-incoming');self.e.gm.restore('q30-incoming');self.restore()
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[self.c.entity_id])
        self.hit(self.a,self.c,key,tick=True)
        self.turn(self.a,new_round=True);self.hit(self.a,self.c,key)
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[])

    def test_complete_korean_any_range_and_unmarked_actual_history_survive_new_choice_until_round_boundary(self):
        self.world();key=self.ordinary()
        choice=self.choice(FW.steelheart_source_choices,'korean_book_outgoing')
        FW.select_steelheart_source(self.e,self.a,choice)
        self.turn(self.a)
        self.e.gm.set_stat(self.b,'def',value=1000,reason='actual minimum-one physical damage before resistance')
        self.e.gm.set_types(self.b,['바위','강철'],reason='actual native Normal resistance permits zero-loss weapon hit')
        prior=self.hit(self.a,self.b,WATER)
        self.assertIsInstance(WEAPONS.range_spec(self.e,prior['target_moves'][self.b.entity_id],self.a)['origin'],int)
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[self.b.entity_id])
        # The earlier real native event is retained in the exact old three-field
        # schema. It gains neither a fictional historical choice nor new foe IDs.
        history=self.a.spec[FW.HITS]
        history.pop('policy_variant');history.pop('source_choice')
        incoming=self.choice(FW.steelheart_source_choices,'english_incoming_melee')
        FW.select_steelheart_source(self.e,self.a,incoming)
        self.e.gm.snapshot('q30-actual-old-outgoing');self.e.gm.restore('q30-actual-old-outgoing');self.restore()
        row=self.hit(self.a,self.b,key,tick=True)
        self.assertEqual(COMPLETE.recipient_result(row,self.b)['dealt'],0)
        self.assertEqual(set(self.a.spec[FW.HITS]),{'round','targets','receipts'})
        bad=deepcopy(incoming);bad['scope']['profile_hash']='not-current-profile'
        NATIVE.assert_rejected_unchanged(self.e,lambda:FW.select_steelheart_source(self.e,self.a,bad),reason_pattern='scope changed')
        NATIVE.assert_rejected_unchanged(self.e,lambda:FW.select_steelheart_source(self.e,self.b,incoming),reason_pattern='actual acquired weapon feature')
        self.turn(self.a,new_round=True)
        self.hit(self.a,self.b,WATER)
        self.assertEqual(self.a.spec[FW.HITS]['policy_variant'],'english_incoming_melee')
        self.assertEqual(self.a.spec[FW.HITS]['targets'],[])
        self.hit(self.a,self.b,key)
        # A real paid miss adds no target/history receipt and cannot arm Tick.
        before=deepcopy(self.a.spec[FW.HITS]);self.hit(self.a,self.c,key,face=1)
        self.assertEqual(self.a.spec[FW.HITS],before)


if __name__=='__main__':unittest.main()
