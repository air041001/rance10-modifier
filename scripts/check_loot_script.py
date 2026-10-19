"""Offline regression of emitted bytecode against an installed game's script.

Starts after native pool construction with controlled pools. Executes the real
patched selection path AND original template generator; creation is intercepted.
No game process, save, or game files are written.
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.extend([str(ROOT/'app'), str(ROOT/'tests')])
import live_profile
import loot_code
from test_loot import String


class Check:
    def __init__(self, game, encoding):
        self.ain = a = live_profile.parse_ain((Path(game)/'Rance10.ain').read_bytes(), True)
        self.p = p = loot_code.describe(a, encoding)
        self.strings = [s.encode('latin1').decode('cp%d' % encoding) for s in a['strings']]
        self.functions = {f['index']: f for f in a['functions']}
        ordered = sorted(a['functions'], key=lambda f: f['address'])
        self.ends = {f['index']: ordered[i+1]['address']-6 for i, f in enumerate(ordered[:-1])}
        self.source = a['code'][p['Offset']:p['Offset']+p['Length']]
        body = loot_code.decode(a['code'], p['Offset'], p['Offset']+p['Length'])
        self.generator = [args[0] for _, op, args in body if op == 48][-1]
        self.generated_rows = self.rows(self.generator)
        self.create = [args[0] for _, op, args in self.generated_rows if op == 48][-1]
        self.owner_wrappers, self.turn = set(), set()
        for r in p['ResolverRules']:
            for _, op, args in r['Rows']:
                if op != 48 or args[0] == p['Random']: continue
                calls = [a[0] for _, o, a in self.rows(args[0]) if o == 48]
                (self.owner_wrappers if p['Owned'] in calls else self.turn).add(args[0])
        self.bonus = next(args[0] for _, op, args in body if op == 48 and
                          self.functions[args[0]]['variables'] and
                          self.functions[args[0]]['variables'][0]['type'][0] == 80)
        self.compiled = {}

    def rows(self, fid):
        return loot_code.decode(self.ain['code'], self.functions[fid]['address'], self.ends[fid])

    def compile(self, full=False, catalog=None):
        if full in self.compiled: return self.compiled[full]
        original = loot_code.Code.finish
        captured = {}
        def capture(c, offset):
            captured.update(c.labels)
            return original(c, offset)
        loot_code.Code.finish = capture
        try:
            patch = loot_code.make_code(self.source, {'Loot': self.p}, catalog, full, True)
        finally:
            loot_code.Code.finish = original
        rows = loot_code.decode(patch, 0, len(patch))
        positions = {self.p['Offset']+at for at, _, _ in rows}
        assert all(args[0] in positions for _, op, args in rows if op in loot_code.BRANCHES)
        assert not {93, 94} & {op for _, op, _ in rows}
        value = (rows, captured)
        self.compiled[full] = value
        return value

    def run(self, pool, owned=(), stock=(), chapter=1, turn=3, seed=0,
            bonus=False, shared=(), full=False, catalog=None, table_size=None, gender=1):
        p = self.p
        rows, labels = self.compile(full, catalog)
        self.owned, self.stock, self.shared = set(owned), set(stock), set(shared)
        self.rng, self.forced_bonus, self.turn_value = random.Random(seed), bonus, turn
        self.catalog, self.table_size = catalog, table_size
        self.steps, self.created = 0, []
        flags = [0]*1000
        flags[0], flags[3], flags[405] = chapter, gender, int(bonus)
        self.globals = {g['index']: flags if g['name']=='tt' else
                        'player' if g['index']==p['CardGlobal'] else String()
                        for g in self.ain['globals']}
        local = {i: 0 for i in range(12)}
        local.update({0: int(bonus), 5: String(), 6: String(),
                      7: [String()] + [String(s) for s in pool], 8: len(pool)})
        start = labels['source', p['Chapter%dSite' % chapter]-p['Offset']]
        self.execute(rows, start, local, p['Offset'])
        assert len(self.created) <= 1
        return self.created[0] if self.created else None

    def execute(self, rows, pos, local, base=0):
        instructions = {at: (op, args) for at, op, args in rows}
        stack = []
        def pop(n):
            if not n: return []
            assert len(stack) >= n, (pos, n, stack)
            result = stack[-n:]; del stack[-n:]; return result
        def scalar(v): return v.value if isinstance(v, String) else v
        while True:
            self.steps += 1
            assert self.steps < 2000000, 'Nonterminating box'
            op, args = instructions[pos]; pos += 2+4*len(args)
            if op==0: stack.append(args[0])
            elif op in (1,119): stack.pop()
            elif op==4: stack.append(self.globals)
            elif op==5: stack.append(local)
            elif op==2:
                page,index=pop(2); stack.append(page[index])
            elif op==25:
                page,index,value=pop(3); page[index]=value; stack.append(value)
            elif op==41: stack.extend(stack[-2:])
            elif op==42:
                a,b,c=pop(3); stack.extend([c,a,b,c])
            elif op==49:
                page,index=pop(2); page[index]+=1
            elif op==102: stack[-2:]=stack[-2:][::-1]
            elif op==65: stack.append(String(self.strings[args[0]]))
            elif op==68:
                target,value=pop(2); target.value=value.value; stack.append(String(value.value))
            elif op==121: stack.append(String(stack.pop().value))
            elif op==67:
                a,b=pop(2); stack.append(String(a.value+b.value))
            elif op in (9,10,19,20,21,22,23,24,72,73):
                a,b=map(scalar,pop(2))
                stack.append({9:lambda:a+b,10:lambda:a-b,19:lambda:a<b,20:lambda:a>b,
                              21:lambda:a<=b,22:lambda:a>=b,23:lambda:a!=b,24:lambda:a==b,
                              72:lambda:a!=b,73:lambda:a==b}[op]())
            elif op==44: pos=args[0]-base
            elif op in (45,46):
                if bool(stack.pop())==(op==46): pos=args[0]-base
            elif op==90:
                if args==self.p['Realloc']:
                    array,size=pop(2); del array[size:]
                    array.extend(String() for _ in range(max(0,size-len(array))))
                elif args==[20,0,-1]:
                    page,index=pop(2); stack.append(String(str(page[index])))
                elif args==self.p['GetColumn']:
                    pop(3); stack.append(0)
                else: raise AssertionError(('HLL',args))
            elif op==92:
                values=pop(args[0]); method=stack.pop(); this=stack.pop()
                assert this=='player' and method==self.p['Stock']
                stack.append(0 if values[0].value in self.stock else -1)
            elif op==48:
                f=self.functions[args[0]]; values=pop(f['argc']); ident=f['index']
                if ident==self.p['Owned'] or ident in self.owner_wrappers:
                    value=int(values[0].value in self.owned)
                elif ident in self.turn:
                    assert values==[-1]; value=self.turn_value
                elif ident==self.p['Random']:
                    width=values[0]; assert width>0
                    if self.forced_bonus and width==5 and base:
                        # Called from the native bonus condition, not family
                        # reservoir draws (the resolver is after ENDFUNC).
                        entry=self.compiled[False][1]['resolve_entry'] if False in self.compiled else 10**9
                        if pos<entry: value=1; self.forced_bonus=False
                        else: value=self.rng.randint(1,width)
                    else: value=self.rng.randint(1,width)
                elif ident==self.generator:
                    loc={i: String() if v['type'][0]==12 else 0 for i,v in enumerate(f['variables'])}
                    loc[0]=String(values[0].value)
                    value=self.execute(self.generated_rows,f['address'],loc)
                elif ident==self.create:
                    self.created.append(values[0].value); value=1
                elif ident==self.bonus:
                    array=values[0]; items=[s.value for s in array if s.value]
                    remaining=[s for s in items if s not in self.shared]
                    if remaining:
                        array[:]=[String(s) for s in remaining]+[String() for _ in range(len(array)-len(remaining))]
                        value=len(remaining)
                    else: value=len(items)
                elif f['name']=='LOG_TADA': value=None
                elif ident==self.p['Height']:
                    value=len(self.catalog['cards']) if self.table_size is None else self.table_size
                elif ident==self.p['ReadString']:
                    value=String(self.catalog['cards'][values[2]]['Id'])
                else: raise AssertionError(('Unhandled call',ident,f['name']))
                if f['returned'][0]!=0: stack.append(value)
            elif op==47:
                assert len(stack)==1, ('Unbalanced return',stack,pos)
                return stack.pop()
            else: raise AssertionError(('Opcode',op,pos))


def check(game, encoding):
    vm=Check(game,encoding); p=vm.p; tests=0
    families=[r for r in p['ResolverRules'] if 'Variants' in r]
    for family in families:
        template=vm.strings[family['Id']]
        versions=[vm.strings[i] for i in family['Variants']]
        for survivor in versions:
            held=set(versions)-{survivor}
            for seed in range(3):
                got=vm.run([template],owned=held,turn=12,seed=seed)
                assert got==survivor, (template,survivor,got)
                tests+=1
        got=vm.run([template],owned=versions,turn=12)
        assert got in versions; tests+=1
        # Pending versions are excluded along with held versions.
        got=vm.run([template],stock=versions[:-1],turn=12)
        assert got==versions[-1]; tests+=1
        # A fully exhausted family must not hide another family's new entry.
        other=next(r for r in families if r is not family)
        got=vm.run([template,vm.strings[other['Id']]],owned=versions,turn=12)
        assert got not in versions; tests+=1
    concrete=vm.strings[families[0]['Variants'][0]]
    bonus=[vm.strings[i] for i in p['BonusIds']]
    for shared in ([],[concrete]):
        got=vm.run([concrete]+bonus,owned=bonus,bonus=True,shared=shared)
        assert got==concrete,(shared,got); tests+=1
        got=vm.run([concrete]+bonus,owned=bonus[:1],bonus=True,shared=shared)
        assert got not in bonus[:1],got; tests+=1
    for r in p['ResolverRules']:
        if 'Variants' in r: continue
        template=vm.strings[r['Id']]
        for turn in (1,3,10,11,15):
            got=vm.run([template],chapter=2,turn=turn)
            assert got and got!=template,(template,got)
            nxt=vm.run([template,concrete],owned={got},chapter=2,turn=turn)
            assert nxt!=got,(template,turn,got,nxt)
            tests+=2
    # Full-drop expansion uses many disjoint eligible ranges, both chapters,
    # current ownership, pending receipts, and the mismatched-table fallback.
    from test_loot import card
    first=[vm.strings[i] for r in families for i in r['Variants']]
    second=[vm.run([vm.strings[r['Id']]],chapter=2) for r in p['ResolverRules'] if 'Variants' not in r]
    catalog=dict(cards=[],skills=[])
    for i,ident in enumerate(first+second):
        catalog['cards'].append(card(ident,1 if i<len(first) else 2))
        if i % 4 == 0:
            catalog['cards'].append(card('excluded%d'%i,1,1))
    for chapter,ids in ((1,first),(2,second)):
        got=vm.run([vm.strings[families[0]['Id']]],owned=ids[:-1],chapter=chapter,
                   full=True,catalog=catalog)
        assert got==ids[-1],(chapter,got,ids[-1]); tests+=1
    got=vm.run([vm.strings[families[0]['Id']]],owned=first[:5],turn=12,
               full=True,catalog=catalog,table_size=0)
    assert got==first[5],got; tests+=1
    return dict(game=Path(game).name, checks=tests, templates=len(p['ResolverRules']), success=True)


if __name__=='__main__':
    print(json.dumps(check(sys.argv[1],int(sys.argv[2])),ensure_ascii=False,indent=2))
