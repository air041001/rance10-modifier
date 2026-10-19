"""Offline treasure-roll checks; no game process or save writes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import live_profile
import treasure_code
import loot_code


def evaluate(ain, profile, source, result_type, forbidden=False, chance=0, roll=100):
    """Execute the complete native CalcResult with only engine calls stubbed."""
    p = profile
    f = next(f for f in ain['functions'] if f['name']=='SceneBattleResult@CalcResult')
    instructions = {at:(op,args) for at,op,args in
                    loot_code.decode(source, f['address'], p['GuardEnd'])}
    stack, scene, globals_, pos = [], {}, {g['index']:g['name'] for g in ain['globals']}, f['address']
    counters = {'missed':2, 'random_calls':0}
    def pop(n):
        if not n:return []
        assert len(stack)>=n, (pos,stack)
        values=stack[-n:];del stack[-n:];return values
    steps=0
    while True:
        steps+=1;assert steps<10000
        op,args=instructions[pos];pos+=2+4*len(args)
        if op==0:stack.append(args[0])
        elif op==1:stack.pop()
        elif op==2:
            page,index=pop(2);stack.append(page[index])
        elif op==4:stack.append(globals_)
        elif op==91:stack.append(scene)
        elif op==7:stack.append(not stack.pop())
        elif op==9:
            a,b=pop(2);stack.append(a+b)
        elif op in (21,24):
            a,b=pop(2);stack.append(a<=b if op==21 else a==b)
        elif op==25:
            page,index,value=pop(3);page[index]=value;stack.append(value)
        elif op==41:stack.extend(stack[-2:])
        elif op==42:
            a,b,c=pop(3);stack.extend([c,a,b,c])
        elif op==102:stack[-2:]=stack[-2:][::-1]
        elif op==44:pos=args[0]
        elif op in (45,46):
            if bool(stack.pop())==(op==46):pos=args[0]
        elif op==48:
            f=ain['functions'][args[0]]
            assert f['name']=='RAND' and pop(f['argc'])==[100]
            counters['random_calls']+=1;stack.append(roll)
        elif op==92:
            values=pop(args[0]);method=stack.pop();stack.pop()
            f=ain['functions'][method];name=f['name'];value=0
            if name=='SceneBattleResult@IsForceNoTreasure::get':value=forbidden
            elif name=='BattleResult@Type::get':value=result_type
            elif name=='BattleResult@GetTotalPerTreasure':value=chance
            elif name=='PlayerCommonParam@TreasureNotGetCount::get':value=counters['missed']
            elif name=='PlayerCommonParam@TreasureNotGetCount::set':counters['missed']=values[0]
            elif not (name.startswith('PlayerCommonParam@') or name=='BattleResult@GetTotalExp'):
                raise AssertionError(('Unexpected method',name))
            if f['returned'][0]!=0:stack.append(value)
        elif op==47:
            assert not stack
            return bool(scene[p['Field']]),counters
        else:raise AssertionError(('Unexpected opcode',op,pos))


def check(game):
    ain=live_profile.parse_ain((Path(game)/'Rance10.ain').read_bytes())
    p=treasure_code.describe(ain)
    raw=ain['code'];offset=p['Offset'];end=offset+p['Length']
    patch=treasure_code.make_code(raw[offset:end],{'Drop':p})
    changed=raw[:offset]+patch+raw[end:]
    assert raw[:offset]==changed[:offset] and raw[end:]==changed[end:]
    count=0
    for result_type in (p['Victory'], p['Victory']+1, p['Victory']+2):
        for forbidden in (False,True):
            for chance in (0,25,100):
                for roll in (1,100):
                    expected=result_type==p['Victory'] and not forbidden
                    got,c=evaluate(ain,p,changed,result_type,forbidden,chance,roll)
                    assert got==expected
                    assert c['random_calls']==0
                    assert c['missed']==(2 if forbidden else 0 if expected else 3)
                    original,c=evaluate(ain,p,raw,result_type,forbidden,chance,roll)
                    assert original==(not forbidden and roll<=chance)
                    count+=2
    return dict(game=Path(game).name,checks=count,span=len(patch),success=True)


if __name__=='__main__':print(json.dumps(check(sys.argv[1]),ensure_ascii=False,indent=2))
