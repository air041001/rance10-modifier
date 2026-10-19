"""Independent symbols and layouts must not become installation addresses."""
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'scripts')]
import treasure_code
from loot_code import Code
from check_treasure_script import evaluate


def fixture(displacement=0, field=3, global_index=0):
    data=bytearray(b'\0'*displacement);functions=[]
    def add(name,argc,returned,emit):
        data.extend(b'\0'*6);index=len(functions)
        functions.append(dict(index=index,name=name,address=len(data),argc=argc,
                              returned=[returned],variables=[]))
        c=Code();emit(c);data.extend(c.finish(len(data)));return index
    def stub(c):c.op(0,0);c.op(47)
    random=add('RAND',1,10,stub)
    type_=add('BattleResult@Type::get',0,92,stub)
    forbidden=add('SceneBattleResult@IsForceNoTreasure::get',0,47,stub)
    chance=add('BattleResult@GetTotalPerTreasure',0,10,stub)
    treasure=add('BattleBonusCalculator::CalcTreasure',0,0,lambda c:c.op(47))
    def bonus(c):
        c.local(0);c.op(0,7);c.op(24);c.jump(46,'win');c.jump(44,'end')
        c.label('win');c.op(48,treasure);c.label('end');c.op(47)
    add('BattleBonusCalculator::Calc',1,0,bonus)
    def calc(c):
        c.op(91);c.op(0,forbidden);c.op(92,0);c.jump(46,'no');c.jump(44,'roll')
        c.label('no');c.op(91);c.op(0,field);c.op(0,0);c.op(25);c.op(1);c.jump(44,'end')
        c.label('roll');c.op(91);c.op(0,field);c.op(0,100);c.op(48,random)
        c.op(4);c.op(0,global_index);c.op(2);c.op(0,chance);c.op(92,0);c.op(21);c.op(25);c.op(1)
        c.label('end');c.op(47)
    add('SceneBattleResult@CalcResult',0,0,calc)
    add('sentinel',0,0,lambda c:c.op(47))
    members=[dict(name='other%d'%i,type=[10]) for i in range(field+1)]
    members[field]=dict(name='m_isGetTreasure',type=[47])
    return dict(code=bytes(data),functions=functions,globals=[dict(index=global_index,name='g_battleResult',type=[13,1])],
                structures=[dict(index=0,name='SceneBattleResult',members=members),dict(index=1,name='BattleResult',members=[])])


class TreasureTests(unittest.TestCase):
    def test_victory_and_prohibition_with_reordered_symbols(self):
        for displacement,field,glob in ((0,3,0),(116,6,4)):
            a=fixture(displacement,field,glob);p=treasure_code.describe(a)
            self.assertEqual(p['Victory'],7)
            self.assertEqual(p['Field'],field);self.assertEqual(p['BattleGlobal'],glob)
            raw=a['code'];end=p['Offset']+p['Length']
            patch=treasure_code.make_code(raw[p['Offset']:end],{'Drop':p})
            changed=raw[:p['Offset']]+patch+raw[end:]
            for kind in (7,8,9):
                for forbidden in (False,True):
                    got,_=evaluate(a,p,changed,kind,forbidden)
                    self.assertEqual(got,kind==7 and not forbidden)

    def test_changed_source_is_rejected_before_patch_generation(self):
        a=fixture();p=treasure_code.describe(a)
        source=a['code'][p['Offset']:p['Offset']+p['Length']]
        with self.assertRaises(ValueError):treasure_code.make_code(b'\xff'+source[1:],{'Drop':p})

    def test_prohibition_must_still_bypass_the_replacement(self):
        a=fixture();p=treasure_code.describe(a)
        raw=bytearray(a['code']);raw[p['Offset']-4:p['Offset']]=b'\0'*4
        a['code']=bytes(raw)
        with self.assertRaises(ValueError):treasure_code.describe(a)

    def test_guaranteed_only_does_not_require_catalog_or_random_pool(self):
        import loot
        a=fixture();p=treasure_code.describe(a)
        import base64
        snapshot=dict(profile={'Drop':p,'Loot':None},pid=1,session=2,global_owner=3,
                      drop_source_code=base64.b64encode(a['code'][p['Offset']:p['Offset']+p['Length']]).decode())
        session=loot.Session()
        with patch.object(session,'request',side_effect=[{'snapshot':snapshot},{'armed':True}]) as request, \
             patch('engine.catalog_data',side_effect=AssertionError('No library needed')), \
             patch('app_paths.initialize'),patch('pathlib.Path.open',unittest.mock.mock_open()):
            session.configure(False,False,True)
        self.assertNotIn('patch',request.call_args.args[0])
        self.assertIn('drop_patch',request.call_args.args[0])
        self.assertTrue(request.call_args.args[0]['guaranteed'])


if __name__=='__main__':unittest.main()
