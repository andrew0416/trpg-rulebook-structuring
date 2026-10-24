"""S-p2cfe-2: actual families for imported book and registered CSV Species Savant."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon, build_trainer
from engine import Combatant, Engine, Rules
import class_passive_combat as C
import state_codec as CODEC
import state_grants as G
import trainer_feature_acquisition as A
import world_entities as W

CSV='C2CSV/input/db/feats.csv:R7:main'
STATS=('hp','atk','def','spa','spd','spe')


class SpeciesSavantFamilySourceRevisionTests(unittest.TestCase):
    def world(self,source=CSV,selected='Ivysaur'):
        self.e=Engine(Rules(ROOT,ruleset='core'),seed=7)
        extra={'feats':[] if source is None else [source],'edges':[],'exp_bank':10,
            'class_passive_choices':{C.SPECIES_SAVANT:{'evolution_group':selected}}}
        self.t=Combatant(self.e.r,build_trainer(self.e.r,'actual family owner',20,
            dict.fromkeys(STATS,10),moves=[],abilities=[],extra=extra))
        self.e.gm.add_combatant(self.t,reason='actual registered imported Feature owner')

    def candidate(self,species,*,owner=None,forged_label=None):
        extra={} if owner is None else {'trainer_id':owner.entity_id}
        if forged_label is not None:extra['evolution_group']=forged_label
        return Combatant(self.e.r,build_pokemon(self.e.r,species,20,moves=[],abilities=[],extra=extra))

    def pokemon(self,species,*,owner=None,forged_label=None):
        p=self.candidate(species,owner=owner,forged_label=forged_label)
        self.e.gm.add_combatant(p,reason='actual stock species and current owner registration')
        return p

    def bonus(self,p,amount):
        self.assertEqual(p.stats,{stat:p.spec['stats'][stat]+amount for stat in STATS})

    def snapshot(self):
        return deepcopy(CODEC.dump_engine(self.e))

    def cold_restore(self):
        ids=[actor.entity_id for actor in (self.t,self.p,self.q)]
        payload=json.loads(json.dumps(self.snapshot(),ensure_ascii=False))
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),payload)
        self.t,self.p,self.q=[W.actor_index(self.e)[uid] for uid in ids]

    def test_actual_csv_and_imported_book_use_real_unlabelled_family_and_reject_forged_target_label(self):
        for source,selected in ((CSV,'Ivysaur'),(C.SPECIES_SAVANT,'pokemon/이상해씨')):
            with self.subTest(source=source):
                self.world(source,selected)
                self.assertEqual(self.e.r._selected_rule(source),source)
                p=self.pokemon('이상해씨',owner=self.t)
                evolved=self.pokemon('이상해풀',owner=self.t)
                unrelated=self.pokemon('파이리',owner=self.t,forged_label=selected)
                wild=self.pokemon('이상해씨',forged_label=selected)
                for member in (p,evolved):
                    self.assertNotIn('evolution_group',member.spec)
                    self.bonus(member,1);self.e.register_abilities(member);self.bonus(member,1)
                    row=G.state(member)['sources'][C._source_id(self.t,member,C.SPECIES_SAVANT)]
                    self.assertEqual(row['acquisition_source'],source)
                    self.assertNotIn('source_variant',row)
                self.bonus(unrelated,0);self.bonus(wild,0)
                self.assertEqual(A.receipts(self.t),[])
                self.assertIsNone(C._species_book_receipt(self.t))

    def test_legacy_free_label_and_changed_family_facts_refuse_before_actual_registration(self):
        for source in (CSV,C.SPECIES_SAVANT):
            with self.subTest(source=source):
                self.world(source,'bulbasaur-line')
                p=self.candidate('이상해풀',owner=self.t,forged_label='bulbasaur-line')
                before=self.snapshot()
                with self.assertRaisesRegex(ValueError,'explicit resolved evolution family'):
                    self.e.gm.add_combatant(p,reason='unsupported historical free label is not a family fact')
                self.assertEqual(self.snapshot(),before)
                self.assertNotIn(p.entity_id,W.actor_index(self.e));self.bonus(p,0)
                self.t.spec['class_passive_choices'][C.SPECIES_SAVANT]['evolution_group']='Bulbasaur'
                self.e.gm.add_combatant(p,reason='explicit actual catalog species selection replaces unresolved label')
                self.bonus(p,1);self.assertEqual(A.receipts(self.t),[])
                q=self.candidate('이상해풀',owner=self.t)
                changed=dict(deepcopy(self.e.r.learnsets['이상해풀']),evolution=['unreviewed lineage'])
                with patch.dict(self.e.r.learnsets,{'이상해풀':changed}):
                    before=self.snapshot()
                    with self.assertRaisesRegex(ValueError,'resolved evolution family|target evolution family is unresolved'):
                        self.e.gm.add_combatant(q,reason='changed native family facts cannot project stats')
                    self.assertEqual(self.snapshot(),before)
                self.assertNotIn(q.entity_id,W.actor_index(self.e));self.bonus(q,0)

    def test_imported_sources_cold_restore_and_gm_restore_then_retract_all_six_stats(self):
        for source in (CSV,C.SPECIES_SAVANT):
            with self.subTest(source=source):
                self.world(source,'pokemon/디그다')
                self.p=self.pokemon('닥트리오',owner=self.t)
                self.q=self.pokemon('디그다 알로라',owner=self.t,forged_label='pokemon/디그다')
                self.cold_restore();self.bonus(self.p,1);self.bonus(self.q,0)
                self.assertEqual(self.t.spec['feats'],[source]);self.assertEqual(A.receipts(self.t),[])
                self.e.gm.snapshot('actual imported family')
                self.t.spec['feats'].remove(source)
                self.e.register_abilities(self.p);self.e.register_abilities(self.q)
                self.bonus(self.p,0);self.bonus(self.q,0)
                self.e.gm.restore('actual imported family',reason='restore actual selected stock family and source')
                index=W.actor_index(self.e);self.t=index[self.t.entity_id];self.p=index[self.p.entity_id];self.q=index[self.q.entity_id]
                self.e.register_abilities(self.p);self.bonus(self.p,1);self.bonus(self.q,0)
                self.assertEqual(A.receipts(self.t),[])

    def test_real_book_acquisition_keeps_exact_receipt_family_and_historical_prerequisites(self):
        self.world(source=None)
        trio=[self.pokemon('디그다',owner=self.t) for _ in range(3)]
        evolved=self.pokemon('닥트리오',owner=self.t)
        regional=self.pokemon('디그다 알로라',owner=self.t)
        receipt=C.acquire_species_savant(self.e,self.t,acquisition_request_id='actual/book-family',
            selected_species='Diglett',prerequisite_ids=[p.entity_id for p in trio])
        self.assertEqual(receipt['source']['clause_id'],'C03-126')
        self.assertEqual(receipt['selection']['acquisition_snapshot']['family'],
            sorted(('pokemon/디그다','pokemon/닥트리오')))
        self.assertEqual(len({row['entity_id'] for row in receipt['selection']['acquisition_snapshot']['prerequisites']}),3)
        saved=deepcopy(receipt)
        self.t.spec['class_passive_choices'][C.SPECIES_SAVANT]['evolution_group']='invented historical label'
        for p in (*trio,evolved):
            self.e.register_abilities(p);self.bonus(p,1)
        self.bonus(regional,0)
        self.assertEqual(C._species_book_receipt(self.t),saved)
        self.assertEqual(A.receipts(self.t),[saved])
        row=G.state(evolved)['sources'][C._source_id(self.t,evolved,C.SPECIES_SAVANT)]
        self.assertEqual((row['source_variant'],row['acquisition_receipt_id']),('C03-126',saved['receipt_id']))
        A.validate_actor(self.t)


if __name__=='__main__':
    unittest.main(verbosity=2)
