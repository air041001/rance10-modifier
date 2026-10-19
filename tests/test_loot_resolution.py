"""Regression cases for native-template resolution before card creation."""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from check_loot_script import Check
from test_loot import String, P
import loot_code


class ResolutionTests(unittest.TestCase):
    def resolve(self, pool, owned=(), stock=(), seed=0, chapter=1):
        width = loot_code.Code(); width.op(0, 3)
        raw = width.finish(0)
        p = dict(P, Random=105, ResolverRules=[dict(Id=3, Width=loot_code.decode(raw,0,len(raw)),
                    WidthEnd=len(raw), WidthSkip=[], Variants=[4,5,6])])
        code = loot_code.Code()
        loot_code.insert(code,p,1,None,False,True); code.op(0,1); code.op(47)
        second = len(code.data)
        loot_code.insert(code,p,2,None,False,True); code.op(0,1); code.op(47)
        loot_code.resolver_code(code,p)
        raw = code.finish(0)
        vm = Check.__new__(Check)
        vm.p=p; vm.strings=['','cards','Id','template','A1','A2','A3']
        vm.globals={p['CardGlobal']:'player'}
        vm.owned=set(owned); vm.stock=set(stock); vm.owner_wrappers=set(); vm.turn=set()
        vm.functions={i:dict(index=i,argc=1,returned=[10]) for i in (p['Owned'],p['Random'])}
        vm.rng=random.Random(seed); vm.forced_bonus=False; vm.steps=0
        local={i:0 for i in range(12)}
        local.update({5:String(),6:String(),7:[String()]+[String(v) for v in pool],8:len(pool)})
        vm.execute(loot_code.decode(raw,0,len(raw)),0 if chapter==1 else second,local)
        return [s.value for s in local[7][1:local[8]+1]], local[11]

    def test_template_selects_only_remaining_version_in_both_chapters(self):
        for chapter in (1,2):
            for remaining in ('A1','A2','A3'):
                for seed in range(8):
                    result,fallback=self.resolve(['template'],{'A1','A2','A3'}-{remaining},seed=seed,chapter=chapter)
                    self.assertEqual(result,[remaining]); self.assertFalse(fallback)

    def test_pending_versions_are_excluded_before_resolution(self):
        self.assertEqual(self.resolve(['template'],owned={'A1'},stock={'A2'})[0],['A3'])

    def test_exhausted_template_cannot_force_fallback_while_another_entry_is_new(self):
        self.assertEqual(self.resolve(['template','new'],owned={'A1','A2','A3'}),(['new'],False))

    def test_all_owned_restores_the_original_template_without_looping(self):
        self.assertEqual(self.resolve(['template'],owned={'A1','A2','A3'}),(['template'],True))

    def test_family_contributes_one_entry_and_keeps_existing_pool_weights(self):
        result,_=self.resolve(['template','template','new','new','new'],owned={'A1','A2'})
        self.assertEqual(result,['A3','A3','new','new','new'])

    def test_resolution_samples_all_eligible_versions(self):
        seen={self.resolve(['template'],seed=i)[0][0] for i in range(40)}
        self.assertEqual(seen,{'A1','A2','A3'})


if __name__=='__main__': unittest.main()
