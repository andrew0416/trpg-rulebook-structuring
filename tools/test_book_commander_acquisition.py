"""Whole Commander gift/acquisition, literal source boundaries and restore."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from commander_fixture import CommanderFixture
import commander as C,commander_orders as O,acquired_features as A,state_fields as SF


class CommanderAcquisitionTests(CommanderFixture,unittest.TestCase):
    def test_each_of_five_real_gifts_waives_expert_only_for_selected_bundle(self):
        for bundle,definition in C.BUNDLES.items():
            with self.subTest(bundle=bundle):
                self.scene(acquire=False,command=3)
                SF.base_patch(self.a,{'skills':{'명령':3}},reason='actual Novice Commander')
                receipt=self.acquire(C.CLASS,branch=bundle)
                self.assertEqual(receipt['snapshot']['branch'],bundle)
                for feature in (bundle,*definition['children']):self.assertTrue(C.gifted(self.a,feature))
                self.assertEqual({uid for uid in C.BUNDLES if A.owned_rule_count(self.a,uid)},{bundle})
                self.assertTrue(all(C.acquired(self.a,uid) is None for uid in C.FEATURES if uid!=C.CLASS))
                self.restore();self.valid()

    def test_class_rank_missing_or_multiple_selection_and_repeated_gift_reject_atomically(self):
        self.scene(acquire=False,command=2)
        self.rejected(lambda:self.acquire(C.CLASS,branch='feat/유린-지시'),'Command rank')
        self.rejected(lambda:self.acquire(C.CLASS),'five printed Orders')
        self.rejected(lambda:self.acquire(C.CLASS,branch=['feat/유린-지시','feat/명사수-지시']),'five printed Orders')
        self.scene(command=3)
        self.rejected(lambda:self.acquire(C.CLASS,branch='feat/명사수-지시'),'replay|gift|branch')

    def test_ordinary_bundle_expert_threshold_and_child_gift_receipts(self):
        self.scene(acquire=False,command=3)
        SF.base_patch(self.a,{'skills':{'명령':4,'협박':4}},reason='both below Expert')
        self.rejected(lambda:self.acquire('feat/유린-지시'),'Expert skill')
        SF.base_patch(self.a,{'skills':{'명령':5,'협박':4}},reason='actual Expert Command')
        self.acquire('feat/유린-지시')
        self.assertTrue(C.gifted(self.a,O.STRIKE));self.assertIsNone(C.acquired(self.a,C.CLASS))
        self.restore();self.valid()

    def test_followup_prerequisites_and_historical_command_not_current_rank(self):
        self.scene(acquire=False)
        self.rejected(lambda:self.acquire(C.MOBILIZE),'actual acquired Commander prerequisite')
        self.scene(command=3)
        self.rejected(lambda:self.acquire(C.BATTLE),'actual acquired Commander prerequisite')
        self.acquire(C.LEADERSHIP);self.acquire(C.BATTLE);self.acquire(C.MOBILIZE)
        self.rejected(lambda:self.acquire(C.TIP),'Command rank')
        SF.base_patch(self.a,{'skills':{'명령':5}},reason='actual Expert Command');self.acquire(C.TIP)
        self.rejected(lambda:self.acquire(C.SCHEME),'Command rank')
        SF.base_patch(self.a,{'skills':{'명령':6}},reason='actual Master Command');self.acquire(C.SCHEME)
        SF.base_patch(self.a,{'skills':{'명령':1}},reason='later changed current Command')
        self.restore();self.valid();self.assertIsNotNone(C.acquired(self.a,C.SCHEME))

    def test_core_mastermind_is_literal_and_local_complex_selection_is_replayable(self):
        self.scene()
        self.rejected(lambda:self.acquire(C.COMPLEX),'literal Mastermind')
        selected={'prerequisite_source':'local_translation'}
        receipt=self.acquire(C.COMPLEX,selection=selected)
        self.assertGreaterEqual(len(receipt['snapshot']['known_orders']),2)
        self.assertEqual(self.acquire(C.COMPLEX,selection=selected),receipt)
        self.rejected(lambda:self.acquire(C.COMPLEX,selection={'prerequisite_source':'core'}),'optional selection')
        self.restore();self.valid()

    def test_core_mastermind_external_declaration_retains_actual_source_scope_and_is_not_class_alias(self):
        import acquisition_qualification as Q
        from copy import deepcopy
        self.scene(acquire=False);self.acquire('feat/유린-지시')
        declaration={'identity':'Mastermind','source':{
            'file':'output/source-audit/2026-10-10/ptu-core-1.05.pdf','sha256':C.CORE_SHA},
            'locator':{'pages':[81,81]},'qualification':{'provider':self.a.entity_id,
            'stage':'commander_prerequisite','checks':[Q.check('Mastermind','prerequisite',True,
                'Explicit external GM observation of this Trainer owning literal Mastermind; no native Mastermind acquisition is inferred')],
            'waivers':[]}}
        for field,value in (('identity','Commander'),('source',{'file':'input/ch04-trainer-classes.md','sha256':C.SOURCE_SHA}),
                ('locator',{'pages':[80,80]})):
            altered=deepcopy(declaration);altered[field]=value
            self.rejected(lambda altered=altered:self.acquire(C.COMPLEX,selection={
                'prerequisite_source':'core','mastermind_declaration':altered}),'Mastermind')
        for field,value in (('provider','other/actor'),('stage','acquire'),('checks',[Q.check('Mastermind','prerequisite',False,'not owned')])):
            altered=deepcopy(declaration);altered['qualification'][field]=value
            self.rejected(lambda altered=altered:self.acquire(C.COMPLEX,selection={
                'prerequisite_source':'core','mastermind_declaration':altered}),'Mastermind')
        selected={'prerequisite_source':'core','mastermind_declaration':declaration}
        receipt=self.acquire(C.COMPLEX,selection=selected)
        self.assertEqual(receipt['snapshot']['mastermind_declaration'],declaration)
        self.assertIsNone(C.acquired(self.a,C.CLASS));self.assertEqual(self.acquire(C.COMPLEX,selection=selected),receipt)
        self.restore();self.valid();self.imported_payload_rejected('commander_prerequisite','fake_stage','Mastermind|acquisition')

    def test_perfect_aim_retains_original_block_locator_and_acquires_actual_feat(self):
        self.scene(bundle='feat/정밀-지시',command=3)
        block=self.r.selection.units['block/완벽한-에임'];feat=self.r.selection.units[O.PERFECT]
        self.assertEqual(block['source'],feat['source']);self.assertEqual(feat['source']['lines'],[816,819])
        self.assertEqual(block['kind'],'entity:block');self.assertEqual(feat['kind'],'entity:feat')
        self.assertTrue(C.gifted(self.a,O.PERFECT));self.assertIn('Orders',feat['tags'])
        self.restore();self.valid()

    def test_imported_class_or_order_names_do_not_create_receipt_or_permission(self):
        self.scene(acquire=False);self.a.spec['classes']=[C.CLASS];self.a.spec['feats']=[C.MOBILIZE,O.LONG]
        self.combat()
        self.rejected(lambda:C.mobilize(self.e,self.a,self.p),'source-specific Commander')
        self.rejected(lambda:O.use(self.e,self.a,self.p,O.LONG),'acquired Orders bundle')

    def test_source_and_gift_json_tampering_rejected_with_fresh_rules(self):
        self.scene(bundle='feat/정밀-지시');self.acquire(C.MOBILIZE);self.combat()
        C.mobilize(self.e,self.a,self.p);self.restore();self.valid()
        self.imported_payload_rejected(C.SOURCE_SHA,'0'*64,'source|Commander|acquisition')
        self.imported_payload_rejected('commander/acquire/'+C.CLASS,'forged/class/request','source|gift|Commander|acquisition')

    def test_core_and_official_errata_rulesets_keep_commander_source_and_actual_consumer(self):
        for ruleset in ('core','core+errata'):
            with self.subTest(ruleset=ruleset):
                self.scene(ruleset=ruleset);self.acquire(C.MOBILIZE);self.combat()
                row=C.mobilize(self.e,self.a,self.p)
                self.assertEqual(row['source']['interpretation']['sha256'],C.CORE_SHA)
                self.next_turn(self.p);self.assertTrue(C.no_opportunity(self.e,self.p))
                self.restore();self.valid()


if __name__=='__main__':unittest.main()
