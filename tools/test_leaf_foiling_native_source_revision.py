"""S-p2cfe-7: actual CSV Foiling Foliage uses the existing paid native action."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
from grid import Grid
from ruleset import RuleFilter
import move_state as MOVES
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import trainer_feature_acquisition as ACQUIRE
import type_ace as TA
import world_entities as W

CSV='C2CSV/input/db/feats.csv:R265:main'
SIX=('몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장')


class LeafFoilingNativeSourceRevisionTests(unittest.TestCase):
    def add(self,spec,pos):
        actor=Combatant(self.e.r,spec)
        self.e.gm.add_combatant(actor,pos=pos,side='party',reason='actual Foiling participant')
        NATIVE.prepare_body(self.e,actor,size=actor.spec.get('size','중형'),offsets=[(0,0)],
            reason='actual complete participant body')
        return actor

    def world(self,source=CSV):
        self.e=Engine(Rules(ROOT,ruleset='core'),seed=265)
        self.e.grid=Grid(10,8);self.source=source
        skill=TA.SKILLS['풀'][0]
        self.t=self.add(build_trainer(self.e.r,'actual Foiling owner',30,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),moves=[],abilities=[],skills={skill:6},
            extra={'feats':[] if source is None else [source],'classes':[],'edges':[],
                'exp_bank':100,'type_link_skills':{'풀':skill}}),(1,1))
        self.p=self.add(build_pokemon(self.e.r,'이상해씨',30,moves=list(SIX),abilities=[],
            extra={'trainer_id':self.t.entity_id}),(2,2))
        self.q=self.add(build_pokemon(self.e.r,'이상해풀',30,moves=[],abilities=[],
            extra={'trainer_id':self.t.entity_id}),(2,3))

    def perform(self,move='씨뿌리기',**options):
        args={'seconds':180,'reason':'actual three-minute focused Foiling activity','feature':self.source}
        args.update(options)
        return TA.foiling(self.e,self.t,self.p,move,**args)

    def snapshot(self):return deepcopy(CODEC.dump_engine(self.e))

    def rejected(self,operation,pattern=None):
        before=self.snapshot()
        with self.assertRaisesRegex(ValueError,pattern) if pattern else self.assertRaises(ValueError):
            operation()
        self.assertEqual(self.snapshot(),before)

    def exemption(self,move):
        view=MOVES.describe(self.e.r,self.p.spec)
        self.assertEqual(set(view['exempt']),{self.e.r.move_id(move)})
        self.assertEqual(view['slot_count'],5)
        return view

    def cold_restore(self):
        ids=[a.entity_id for a in (self.t,self.p,self.q)]
        payload=json.loads(json.dumps(self.snapshot(),ensure_ascii=False))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),payload)
        self.t,self.p,self.q=[W.actor_index(self.e)[uid] for uid in ids]

    def test_actual_csv_native_action_pays_once_advances_minutes_and_replaces_only_one_exemption(self):
        self.world();self.assertEqual(self.e.r._selected_rule(CSV),CSV)
        self.assertIsNone(TA.acquired(self.t,TA.uid('Foiling Foliage')))
        known=list(self.p.moves);elapsed=self.e.elapsed_seconds
        history=list(getattr(self.t,'_action_history',[]))
        result=self.perform();self.exemption('씨뿌리기')
        self.assertEqual(result['rule_id'],CSV)
        self.assertEqual(self.e.elapsed_seconds,elapsed+180)
        self.assertEqual(self.t._action_history,history+['extended'])
        self.perform('성장');view=self.exemption('성장')
        self.assertIn('move/씨뿌리기',view['counted'])
        self.assertEqual(self.e.elapsed_seconds,elapsed+360)
        self.assertEqual(self.t._action_history,history+['extended','extended'])
        self.assertEqual(self.p.moves,known)
        self.assertEqual({row['rule_id'] for row in view['sources']},{CSV})

    def test_actual_encounter_and_sleep_refuse_csv_action_without_cost_time_or_choice_changes(self):
        for blocked in ('encounter','sleep'):
            with self.subTest(blocked=blocked):
                self.world();self.perform()
                if blocked=='encounter':self.e.begin_encounter(self.e.everyone)
                else:self.e.apply_status(self.t,'잠듦',source='move/수면가루',applied_by=self.p)
                self.rejected(lambda:self.perform('성장'),'active encounter' if blocked=='encounter' else 'Extended action unavailable')
                self.exemption('씨뿌리기')

    def test_invalid_moves_foreign_unregistered_and_other_or_excluded_source_are_atomic(self):
        self.world();self.perform()
        for move in ('몸통박치기','덩굴채찍','버섯포자'):
            with self.subTest(move=move):self.rejected(lambda move=move:self.perform(move))
        self.rejected(lambda:self.perform(feature='C2CSV/input/db/feats.csv:R264:main'),'exact book or CSV')
        foreign=self.add(build_pokemon(self.e.r,'이상해씨',30,moves=list(SIX),abilities=[]),(6,2))
        self.rejected(lambda:TA.foiling(self.e,self.t,foreign,'씨뿌리기',feature=CSV,seconds=180,
            reason='actual foreign recipient cannot use the owned Feature'),'your actual Pokemon')
        unregistered=Combatant(self.e.r,build_pokemon(self.e.r,'이상해씨',30,moves=list(SIX),abilities=[],
            extra={'trainer_id':self.t.entity_id}))
        self.rejected(lambda:TA.foiling(self.e,self.t,unregistered,'씨뿌리기',feature=CSV,seconds=180,
            reason='unregistered sheet is not an actual native recipient'))
        self.world();previous=self.e.r.ruleset
        self.e.r.ruleset=RuleFilter({'sources':['core'],'variants':[],'exclude_units':[CSV]})
        self.e.r._apply_ruleset()
        try:self.rejected(lambda:self.perform())
        finally:self.e.r.ruleset=previous;self.e.r._apply_ruleset()

    def test_real_book_default_is_not_double_charged_and_csv_json_gm_restore_keeps_exact_choice(self):
        self.world(source=None)
        ACQUIRE.acquire_static(self.e,self.t,TA.CLASS,branch='풀',acquisition_request_id='foiling/actual-type-ace')
        feature=TA.uid('Foiling Foliage')
        ACQUIRE.acquire_static(self.e,self.t,feature,acquisition_request_id='foiling/actual-book-feature')
        receipt=deepcopy(TA.acquired(self.t,feature))
        elapsed=self.e.elapsed_seconds;history=list(getattr(self.t,'_action_history',[]))
        TA.foiling(self.e,self.t,self.p,'씨뿌리기',seconds=180,reason='actual book three-minute action')
        self.exemption('씨뿌리기')
        self.assertEqual(self.e.elapsed_seconds,elapsed+180)
        self.assertEqual(self.t._action_history,history+['extended'])
        self.e.gm.observe_foiling_foliage(self.t,self.p,'씨뿌리기',reason='record the already completed native book choice')
        self.assertEqual((self.e.elapsed_seconds,self.t._action_history),(elapsed+180,history+['extended']))
        self.assertEqual(TA.acquired(self.t,feature),receipt)
        self.world();self.perform('성장');elapsed=self.e.elapsed_seconds
        self.cold_restore();self.exemption('성장')
        self.assertEqual(self.e.elapsed_seconds,elapsed)
        self.assertEqual(self.t._action_history,['extended'])
        self.e.gm.snapshot('actual CSV exemption');self.perform('씨뿌리기');self.exemption('씨뿌리기')
        self.e.gm.restore('actual CSV exemption',reason='restore actual paid selected exemption')
        index=W.actor_index(self.e);self.t=index[self.t.entity_id];self.p=index[self.p.entity_id];self.q=index[self.q.entity_id]
        view=self.exemption('성장');self.assertEqual({row['rule_id'] for row in view['sources']},{CSV})
        self.assertEqual((self.e.elapsed_seconds,self.t._action_history),(elapsed,['extended']))


if __name__=='__main__':unittest.main(verbosity=2)
