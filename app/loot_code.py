"""Temporary random-box rules. Explicit reward IDs never enter this function."""
import hashlib
import struct
import engine

# sys43vm bytecode ABI. Only instructions present in the inspected box routine
# are accepted. Branches are relocated; calls and string-table indices stay local.
ARGS = {0: 1, 44: 1, 45: 1, 46: 1, 48: 1, 65: 1, 90: 3, 92: 1,
        93: 1, 94: 1, 98: 1, 118: 2, 126: 1, 140: 2, 138: 1}
PLAIN = {1, 2, 4, 5, 7, 9, 10, 11, 19, 20, 21, 22, 23, 24, 25, 26, 41, 42, 47,
         49, 67, 68, 72, 73, 91, 102, 119, 121, 123, 124}
BRANCHES = {44, 45, 46}


def decode(code, start, end, first_hll=False):
    rows, pos = [], start
    while pos < end:
        op = struct.unpack_from('<H', code, pos)[0]
        if op not in ARGS and op not in PLAIN:
            raise ValueError('随机宝箱指令需要适配：%x' % op)
        count = ARGS.get(op, 0)
        args = list(struct.unpack_from('<' + 'i' * count, code, pos + 2))
        rows.append((pos, op, args))
        pos += 2 + count * 4
        if first_hll and op == 90:
            return rows
    engine.require(pos == end, '随机宝箱代码边界无效。')
    return rows


def describe(ain, codepage=932):
    ordered = sorted(ain['functions'], key=lambda f: f['address'])
    by_name = {f['name']: f for f in ordered}
    by_index = {f['index']: f for f in ordered}
    ends = {f['index']: ordered[i+1]['address'] - 6 for i, f in enumerate(ordered[:-1])}

    def function(name, argc, returned):
        f = by_name.get(name)
        engine.require(f is not None and f['argc'] == argc and f['returned'][0] == returned,
                       '随机宝箱调用需要适配：' + name)
        return f

    def rows(f, first_hll=False):
        return decode(ain['code'], f['address'], ends[f['index']], first_hll)

    wrapper = function('TadaFunc::CardBox', 1, 10)
    calls = [args[0] for _, op, args in rows(wrapper) if op == 48]
    engine.require(len(calls) == 1, '随机宝箱入口不明确。')
    box = by_index[calls[0]]
    types = [v['type'][0] for v in box['variables']]
    engine.require(box['argc'] == 1 and box['returned'][0] == 10 and
                   types == [10, 10, 10, 10, 10, 12, 12, 79, 10, 10, 10, 10],
                   '随机宝箱局部字段需要适配。')
    for index, name in [(0, 'fg'), (1, 'ra'), (2, 'q'), (3, 'loop'), (4, 'loop_max'),
                        (5, 'v'), (8, 'aa'), (9, 'bb'), (10, 'ttxx')]:
        engine.require(box['variables'][index]['name'] == name, '随机宝箱局部用途需要适配。')
    start, end = box['address'], ends[box['index']]
    body = rows(box)
    engine.require(1000 <= end-start <= 512000, '随机宝箱代码长度无效。')
    positions = {p for p, _, _ in body}
    engine.require(all(args[0] in positions for _, op, args in body if op in BRANCHES),
                   '随机宝箱有跨函数分支，需要适配。')
    # Both chapter paths check their count before drawing. Insert before those
    # checks so an empty original pool can still be expanded. Later fixed/bonus
    # handling is copied intact, including the special rare-box fallback.
    checks = []
    pattern = [(5, []), (0, [8]), (2, []), (0, [0]), (24, [])]
    for i in range(len(body)-9):
        if [(op, args) for _, op, args in body[i:i+5]] != pattern:
            continue
        tail = body[i+5:i+12]
        if tail[0][1] == 46 and tail[1][1] == 44 and tail[2][1] == 65 and tail[3][1] == 48 and tail[4][1:]==(0, [0]) and tail[5][1]==47:
            checks.append(body[i][0])
    engine.require(len(checks) == 2, '未找到两部独立的随机宝箱卡池检查。')
    # The first path is Chapter2; verify the entry actually branches on tt[0]==2.
    globals_ = {g['name']: g for g in ain['globals']}
    flag = globals_.get('tt')
    cards = globals_.get('g_playerCard')
    engine.require(flag is not None and cards is not None, '随机宝箱全局对象缺失。')
    chapter = [(4, []), (0, [flag['index']]), (2, []), (0, [0]), (2, []), (0, [2]), (24, [])]
    engine.require(any([(op, args) for _, op, args in body[i:i+7]] == chapter
                       for i in range(min(80, len(body)-7))), '随机宝箱章节分支需要适配。')
    find = function('findPlayerCardFromIdExceptStock', 1, 21)
    owned = []
    for f in ordered:
        if f['argc'] != 1 or f['returned'][0] != 10 or len(f['variables']) != 2:
            continue
        if f['variables'][0]['type'][0] != 12 or f['variables'][1]['type'][0] != 21:
            continue
        try:
            ops = rows(f)
        except (ValueError, KeyError, struct.error):
            continue
        if [(op, args) for _, op, args in ops[:5]] == [(5, []), (0, [0]), (2, []), (121, []), (48, [find['index']])]:
            owned.append(f)
    engine.require(len(owned) == 1, '未找到按卡牌版本判断持有的入口。')
    stock = function('PlayerCardCollection@FindStockIndexFromId', 1, 10)
    exists = function('PlayerCard::IsExistId', 1, 47)
    strings = [args[0] for _, op, args in rows(exists) if op == 65]
    engine.require(len(strings) == 2, '卡牌数据表名称需要适配。')
    empty = next(args[0] for _, op, args in body if op == 65)
    col = rows(function('EX_SA2Int', 5, 10), True)[-1]
    realloc = rows(by_name['SceneGetCard@CreateCard'], True)[-1]
    engine.require(col[1] == realloc[1] == 90 and realloc[2][2] == 12, '宝箱表格或数组操作需要适配。')
    identifiers = {1: set(), 2: set()}
    pool_strings = set()
    if 'strings' in ain:
        for i in range(len(body)-5):
            chunk = body[i:i+6]
            if ([(op, args) for _, op, args in chunk[:3]] == [(5, []), (0, [5]), (2, [])] and
                    chunk[3][1] == 65 and chunk[4][1] == 68 and chunk[5][1] == 119):
                # No-repeat works before a library exists. Its VM strings stay
                # in the game; the text scope is used only after a matching
                # library has supplied the installation's actual code page.
                value = ain['strings'][chunk[3][2][0]].encode('latin-1').decode('cp%d' % codepage, errors='replace')
                pool_strings.add(chunk[3][2][0])
                identifiers[2 if chunk[0][0] < checks[0] else 1].add(value)
    resolver = describe_resolver(ain, body, pool_strings, rows, by_index, owned[0]['index'])
    boolean_calls = []
    for index in {a[0] for _, o, a in body if o == 48}:
        try:
            ops = rows(by_index[index])
        except ValueError:
            continue
        destinations = {a[0] for _, o, a in ops if o in BRANCHES}
        returns = [i for i, (_, o, _) in enumerate(ops) if o == 47]
        if returns and all(i and ops[i-1][1] == 0 and ops[i-1][2] in ([0], [1]) and
                           ops[i][0] not in destinations for i in returns):
            boolean_calls.append(index)
    return dict(Offset=start, Length=end-start, SpanHash=hashlib.sha256(ain['code'][start:end]).hexdigest(),
                GuardStart=start, GuardEnd=end, Chapter2Site=checks[0], Chapter1Site=checks[1],
                TableString=strings[0], IdString=strings[1], EmptyString=empty,
                GetColumn=col[2], Realloc=realloc[2], ReadString=function('EX_A2String', 5, 12)['index'],
                Height=function('EX_Height', 2, 10)['index'], Owned=owned[0]['index'],
                Stock=stock['index'], CardGlobal=cards['index'],
                Chapter1Ids=sorted(identifiers[1]), Chapter2Ids=sorted(identifiers[2]),
                BooleanCalls=boolean_calls, **resolver)


def describe_resolver(ain, body, pool_strings, rows, functions, owned):
    """Extract only native template cases reachable from this box's own pool.

    No translated names or installation addresses are baked into the patch.
    Random families retain their native width/turn rules; deterministic cases
    retain their original branches. Creation and unrelated event cases are
    never copied.
    """
    generator = functions[[a[0] for _, op, a in body if op == 48][-1]]
    source = rows(generator)
    random = next(f['index'] for f in functions.values() if f['name'] == 'tran')
    rules = []
    head = [(5, []), (0, [0]), (2, []), (121, [])]
    for i in range(len(source)-7):
        chunk = source[i:i+8]
        if ([(o, a) for _, o, a in chunk[:4]] != head or
                [o for _, o, _ in chunk[4:]] != [65, 73, 46, 44]):
            continue
        ident, start, end = chunk[4][2][0], chunk[6][2][0], chunk[7][2][0]
        if ident not in pool_strings:
            continue
        block = [r for r in source if start <= r[0] < end]
        positions = {r[0] for r in block} | {end}
        engine.require(block and all(a[0] in positions for _, o, a in block if o in BRANCHES),
                       '宝箱版本转换含有跨分支跳转，需要适配。')
        # Only local assignments and read-only calls are allowed here.
        for j, (_, op, args) in enumerate(block):
            if op == 25:
                engine.require(j >= 3 and (block[j-3][1] == 5 or block[j-1][1:] == (48, [random])),
                               '宝箱版本转换含有额外写入，需要适配。')
            if op != 48 or args[0] == random:
                continue
            callee = rows(functions[args[0]])
            ops = [(o, a) for _, o, a in callee if o != 126]
            if ops == head + [(48, [owned]), (47, []), (0, [0]), (47, [])]:
                continue
            # The turn accessor's setter is guarded by argument >= 0. These
            # cases call it with -1; the getter itself is identified by name.
            getter = next((f['index'] for f in functions.values()
                           if f['name'] == 'GameContext@Turn::get'), None)
            engine.require(j > 0 and block[j-1][1:] == (0, [-1]) and
                           ops[:7] == [(5, []), (0, [0]), (2, []), (0, [0]),
                                       (22, []), (46, callee[5][2]), (44, callee[6][2])] and
                           any(o == 0 and a == [getter] for o, a in ops),
                           '宝箱版本转换调用需要适配。')
        random_calls = [j for j, (_, o, a) in enumerate(block) if o == 48 and a == [random]]
        rule = dict(Id=ident, End=end, Rows=block)
        if random_calls:
            engine.require(len(random_calls) == 1, '宝箱随机版本规则需要适配。')
            call = random_calls[0]
            # Prefix ends with local ra = tran(width). Save only width setup
            # and the width expression, omitting the random draw/assignment.
            setup = next(j for j in range(call-1, -1, -1)
                         if block[j][1:] == (5, []) and block[j+1][1:] == (0, [1]))
            width = block[:call]
            variants = []
            tail = block[call+3:]
            for k in range(0, len(tail), 13):
                part = tail[k:k+13]
                expected = [(5, []), (0, [1]), (2, []), (0, [len(variants)+1]), (24, [])]
                engine.require(len(part) == 13 and [(o, a) for _, o, a in part[:5]] == expected and
                               [o for _, o, _ in part[5:]] == [46, 44, 5, 0, 2, 65, 68, 119] and
                               part[8][2] == [0] and part[5][2] == [part[7][0]] and
                               part[6][2] == [part[-1][0]+2],
                               '宝箱随机版本列表需要适配。')
                variants.append(part[10][2][0])
            engine.require(1 <= len(variants) <= 32, '宝箱随机版本数量需要适配。')
            # A fixed width or native aa value, not a call that creates a card.
            engine.require(block[call+1][1:] == (25, []) and block[call+2][1:] == (1, []),
                           '宝箱随机版本赋值需要适配。')
            rule.update(Width=width, WidthEnd=block[call][0], Variants=variants,
                        WidthSkip=[block[setup][0], block[setup+1][0]])
        else:
            for j, (_, op, args) in enumerate(block[:-1]):
                if op == 5:
                    engine.require(block[j+1][1] == 0 and block[j+1][2][0] in (0, 6),
                                   '宝箱确定版本的局部字段需要适配。')
        rules.append(rule)
    engine.require(rules, '未找到宝箱版本转换规则。')
    # The optional first-part bonus has two literal fallback entries.
    fallback = []
    for i, (_, op, args) in enumerate(body):
        if op == 48 and functions[args[0]]['argc'] == 1 and functions[args[0]]['variables'][0]['type'][0] == 80:
            fallback.append(i)
    engine.require(len(fallback) == 1, '宝箱额外奖励入口需要适配。')
    after = body[fallback[0]+1:]
    writes = [i for i in range(len(after)-5)
              if [(o, a) for _, o, a in after[i:i+3]] == [(5, []), (0, [5]), (2, [])]
              and [o for _, o, _ in after[i+3:i+6]] == [65, 68, 119]]
    engine.require(len(writes) == 2, '宝箱额外奖励候选需要适配。')
    site = after[writes[0]][0]
    # Both fallback strings lie inside the last aa==0 branch.
    exit_ = next(a[0] for at, o, a in reversed(body[:fallback[0]+1] + after[:writes[0]]) if o == 44)
    return dict(ResolverRules=rules, Random=random, BonusSite=site, BonusEnd=exit_,
                BonusIds=[after[i+3][2][0] for i in writes])


class Code:
    def __init__(self):
        self.data, self.labels, self.fixups = bytearray(), {}, []

    def op(self, op, *args):
        self.data += struct.pack('<H', op) + b''.join(struct.pack('<i', arg) for arg in args)

    def label(self, name):
        engine.require(name not in self.labels, '宝箱代码标签重复。')
        self.labels[name] = len(self.data)

    def jump(self, op, name):
        self.op(op, 0)
        self.fixups.append((len(self.data)-4, name))

    def local(self, index):
        # SH_LOCALREF is defined in tools' ABI but is not implemented by the
        # Rance10 retail VM. Use the same basic form as its own scripts.
        self.op(5); self.op(0, index); self.op(2)

    def set(self, index):
        self.op(5); self.op(102); self.op(0, index); self.op(102); self.op(25); self.op(1)

    def integer(self, index, value):
        self.op(5); self.op(0, index); self.op(0, value); self.op(25); self.op(1)

    def increment(self, index):
        self.op(5); self.op(0, index); self.op(41); self.op(49); self.op(1); self.op(1)

    def assign_string(self, local):
        self.local(local); self.op(102); self.op(68); self.op(119)

    def finish(self, offset):
        for at, label in self.fixups:
            struct.pack_into('<i', self.data, at, offset+self.labels[label])
        return bytes(self.data)


def ranges(indices):
    result = []
    for index in indices:
        if result and index == result[-1][1]+1:
            result[-1][1] = index
        else:
            result.append([index, index])
    return result


def eligible_rows(catalog, chapter, profile=None):
    skills = {s['Id'] for s in catalog['skills']}
    first = set((profile or {}).get('Chapter1Ids', []))
    second = set((profile or {}).get('Chapter2Ids', []))
    def scope(row):
        ident, appearance = row['Id'], row['出现']
        if appearance == 2:
            return {2}
        if appearance == 1:
            return {1, 2} if ident in second else {1}
        known = ({1} if ident in first else set()) | ({2} if ident in second else set())
        if known:
            return known
        family = {r['出现'] for r in catalog['cards'] if r['识别名'] == row['识别名'] and r['出现'] in (1, 2)}
        # Special-only story characters use Chapter1 unless their ordinary
        # versions belong exclusively to Chapter2. Actual box entries override.
        return {2} if family == {2} else {1}
    return [i for i, row in enumerate(catalog['cards']) if engine.eligible(row, {}, skills) and chapter in scope(row)]


def insert(c, p, chapter, catalog, all_cards, unique):
    prefix = 'loot%d_' % chapter
    done, filter_, next_, end_, cleanup = [prefix+n for n in ('done', 'filter', 'next', 'end', 'cleanup')]
    # Even a one-entry pool is a random-box result. Fixed/captured reward IDs
    # take SceneGetCard's explicit-ID path and never call this routine.
    # Do not infer a fixed reward from the random pool's current size.
    c.local(8); c.set(2)  # Original count; the original entries remain until a new entry is accepted.
    c.integer(4, 0)       # Source offset.
    if all_cards:
        eligible = eligible_rows(catalog, chapter, p)
        engine.require(eligible, '本机图鉴没有该部可掉落的卡牌。')
        count = len(catalog['cards'])
        c.op(65, p['TableString']); c.op(0, 0); c.op(48, p['Height'])
        c.op(0, count); c.op(24); c.jump(45, filter_)  # A different running EX uses the original pool.
        c.op(65, p['TableString']); c.op(65, p['IdString']); c.op(0, 0); c.op(90, *p['GetColumn']); c.set(10)
        c.local(10); c.op(0, 0); c.op(22); c.jump(45, filter_)
        c.local(2); c.set(4)
        c.local(7); c.local(2); c.op(0, count+1); c.op(9); c.op(90, *p['Realloc'])
        c.integer(8, 0)
        intervals = ranges(eligible)
        loop = prefix+'row'
        c.integer(3, intervals[0][0]); c.label(loop)
        c.increment(8)
        c.local(7); c.local(4); c.local(8); c.op(9); c.op(2)
        c.op(65, p['TableString']); c.local(10); c.local(3); c.op(65, p['EmptyString']); c.op(0, 0)
        c.op(48, p['ReadString']); c.op(68); c.op(119)
        c.increment(3)
        for n, ((_, last), (first, _)) in enumerate(zip(intervals, intervals[1:])):
            next_range = prefix+'gap%d' % n
            c.local(3); c.op(0, last+1); c.op(24); c.jump(45, next_range)
            c.integer(3, first)
            c.label(next_range)
        c.local(3); c.op(0, intervals[-1][1]); c.op(21); c.jump(46, loop)
    c.label(filter_)
    c.local(8); c.set(1); c.integer(8, 0); c.integer(3, 1)
    resolving = unique and bool(p.get('ResolverRules'))
    if resolving:
        extra = max(len(r.get('Variants', [])) for r in p['ResolverRules'])
        c.local(7); c.local(4); c.local(1); c.op(9); c.op(0, extra+1); c.op(9)
        c.op(90, *p['Realloc'])
    loop = prefix+'candidate'
    c.label(loop)
    c.local(3); c.local(1); c.op(21); c.jump(45, end_)
    c.local(7); c.local(4); c.local(3); c.op(9); c.op(2); c.op(121); c.assign_string(5)
    if resolving:
        c.op(0, chapter-1); c.jump(44, 'resolve_entry')
        c.label('resolve_return%d' % chapter)
        c.local(5); c.op(121); c.op(65, p['EmptyString']); c.op(73); c.jump(46, next_)
    if unique:
        held(c, p, next_)
    c.increment(8); c.local(7); c.local(8); c.op(2); c.local(5); c.op(121); c.op(68); c.op(119)
    c.label(next_); c.increment(3); c.jump(44, loop)
    c.label(end_)
    if resolving:
        c.local(8); c.op(0, 0); c.op(24); c.set(11)
    c.local(8); c.op(0, 0); c.op(24); c.jump(45, cleanup)
    c.local(2); c.set(8)   # All excluded: none were overwritten, so use the original pool.
    c.label(cleanup)
    # Later game bonus logic inspects the entire array, not just aa. Remove
    # rejected/source entries so they cannot re-enter through that path.
    c.local(7); c.local(8); c.op(0, 1); c.op(9); c.op(90, *p['Realloc'])
    c.local(8); c.op(0, 2); c.op(22); c.jump(46, done)
    # The game's fixed rare-box fallback writes indices 1 and 2.
    c.local(7); c.op(0, 3); c.op(90, *p['Realloc'])
    c.label(done)


def held(c, p, target):
    """Branch when local v is owned or already pending receipt."""
    c.local(5); c.op(121); c.op(48, p['Owned']); c.jump(46, target)
    c.op(4); c.op(0, p['CardGlobal']); c.op(2)
    c.op(0, p['Stock']); c.local(5); c.op(121); c.op(92, 1)
    c.op(0, 0); c.op(22); c.jump(46, target)


def copied_case(c, rows, end, prefix, locals_, skip=()):
    """Relocate a validated read-only native case into the box's scratch locals."""
    rows = [(at, op, list(args)) for at, op, args in rows]
    jumps = {at: args[0] for at, op, args in rows if op == 44}
    for _, op, args in rows:
        if op in BRANCHES:
            seen = set()
            while args[0] in jumps and args[0] not in seen:
                seen.add(args[0]); args[0] = jumps[args[0]]
    for i, (_, op, _) in enumerate(rows[:-1]):
        if op == 5:
            engine.require(rows[i+1][1] == 0 and rows[i+1][2][0] in locals_,
                           '宝箱版本转换的局部字段需要适配。')
            rows[i+1][2][0] = locals_[rows[i+1][2][0]]
    protected = {a[0] for _, o, a in rows if o in BRANCHES} | set(skip)
    i = 0
    while i < len(rows):
        at, op, args = rows[i]
        c.label((prefix, at))
        if at in skip:
            i += 1
            continue
        if op == 44 and (args[0] == (rows[i+1][0] if i+1 < len(rows) else end) or
                         (i and rows[i-1][1] == 44 and at not in protected)):
            i += 1
            continue
        consumed, op, args = compact(rows, i, protected)
        if op in BRANCHES:
            c.jump(op, (prefix, args[0]))
        else:
            c.op(op, *args)
        i += consumed
    c.label((prefix, end))


def resolver_code(c, p):
    # The caller leaves its return selector below all temporary operands.
    # Only scratch locals 5,6,9,10,11 and array tail entries are changed.
    c.label('resolve_entry')
    c.op(65, p['EmptyString']); c.assign_string(6)
    for n, rule in enumerate(p['ResolverRules']):
        next_ = ('resolver_next', n)
        c.local(5); c.op(121); c.op(65, rule['Id']); c.op(73); c.jump(45, next_)
        if 'Variants' in rule:
            copied_case(c, rule['Width'], rule['WidthEnd'], ('width', n), {1: 10, 2: 9}, rule['WidthSkip'])
            c.set(9)
            c.local(7); c.local(4); c.local(1); c.op(9)
            for index, ident in enumerate(rule['Variants'], 1):
                c.op(41); c.op(0, index); c.op(9); c.op(2)
                c.op(65, ident); c.op(68); c.op(119)
            c.op(1); c.op(1)
            c.jump(44, 'resolve_family')
        else:
            copied_case(c, rule['Rows'], rule['End'], ('case', n), {0: 5, 6: 6})
            c.jump(44, 'resolve_done')
        c.label(next_)
    c.jump(44, 'resolve_done')
    # Uniform reservoir sample among the family's currently unowned versions.
    # Each original pool entry still contributes one entry, preserving family
    # weights instead of making five-version families five times as common.
    c.label('resolve_family'); c.integer(10, 1); c.integer(11, 0)
    c.label('resolve_variant')
    c.local(7); c.local(4); c.local(1); c.op(9); c.local(10); c.op(9); c.op(2); c.op(121); c.assign_string(5)
    held(c, p, 'resolve_variant_next')
    c.increment(11); c.local(11); c.op(48, p['Random']); c.op(0, 1); c.op(24)
    c.jump(45, 'resolve_variant_next')
    c.local(5); c.op(121); c.assign_string(6)
    c.label('resolve_variant_next'); c.increment(10)
    c.local(10); c.local(9); c.op(21); c.jump(46, 'resolve_variant')
    c.local(6); c.op(121); c.assign_string(5)
    c.label('resolve_done')
    c.jump(46, 'resolve_return2'); c.jump(44, 'resolve_return1')


def bonus_guard(c, p):
    # If the original pool was entirely owned, retain normal fallback behavior.
    # Otherwise this branch follows a one-entry result from the native shared
    # history filter. Do not replace that new entry with two owned bonus cards.
    c.local(11); c.jump(46, 'bonus_original')
    for i, ident in enumerate(p['BonusIds']):
        c.op(65, ident); c.assign_string(5)
        held(c, p, ('bonus_owned', i))
        c.jump(44, 'bonus_original')
        c.label(('bonus_owned', i))
    c.local(7); c.op(0, 0); c.op(2); c.op(121); c.op(65, p['EmptyString']); c.op(73)
    c.jump(46, 'bonus_keep_first')
    # Successful shared-history filtering returns a zero-based array. Empty
    # results keep the original one-based array. Normalize the single survivor.
    c.local(7); c.op(0, 1); c.op(2); c.local(7); c.op(0, 0); c.op(2); c.op(121); c.op(68); c.op(119)
    c.label('bonus_keep_first'); c.integer(8, 1)
    c.jump(44, ('source', p['BonusEnd']-p['Offset']))
    c.label('bonus_original')


def compact(rows, index, protected):
    """Remove discarded postfix results and redundant two-branch ifs.

    No new VM opcodes are introduced. A branch into any omitted instruction
    prevents that rewrite; integer increments keep the original page/index.
    """
    at, op, args = rows[index]
    # page/index DUP2 REF DUP_X2 POP INC POP discards the old integer value.
    postfix = [(41, []), (2, []), (42, []), (1, []), (49, []), (1, [])]
    chunk = rows[index:index+6]
    if (index >= 2 and rows[index-2][1] == 5 and rows[index-1][1] == 0 and
            [(code, values) for _, code, values in chunk] == postfix and
            not any(pos in protected for pos, _, _ in chunk[1:])):
        return 6, 49, []
    # IFNZ next / JUMP else / next: is simply IFZ else (and vice versa).
    if (op in (45, 46) and index+2 < len(rows) and rows[index+1][1] == 44 and
            args[0] == rows[index+2][0] and rows[index+1][0] not in protected):
        return 2, 91-op, rows[index+1][2]
    return 1, op, args


def make_code(source, profile, catalog=None, all_cards=False, unique=False):
    p = profile['Loot']
    engine.require(all_cards or unique, '请选择一种宝箱规则。')
    engine.require(hashlib.sha256(source).hexdigest() == p['SpanHash'] and len(source) == p['Length'],
                   '随机宝箱原始代码不一致。')
    engine.require(not all_cards or catalog is not None, '全掉落需要先准备本机图鉴。')
    offset = p['Offset']
    # Normalize branch targets once. Calls and all other arguments retain
    # their installation-specific values.
    rows = [(at, op, [args[0]-offset] if op in BRANCHES else args)
            for at, op, args in decode(source, 0, len(source))]
    targets = {args[0] for _, op, args in rows if op in BRANCHES}
    c, i = Code(), 0
    sites = {p['Chapter1Site']-offset: 1, p['Chapter2Site']-offset: 2}
    resolving = unique and bool(p.get('ResolverRules'))
    bonus_site = p.get('BonusSite', -1)-offset
    bonus_end = p.get('BonusEnd', -1)-offset
    hooks = set(sites) | ({bonus_site, bonus_end} if resolving else set())
    while i < len(rows):
        at, op, args = rows[i]
        c.label(('source', at))
        if at in sites:
            insert(c, p, sites[at], catalog, all_cards, unique)
        if resolving and at == bonus_site:
            bonus_guard(c, p)
        if resolving and at == bonus_end:
            c.local(11); c.jump(46, 'bonus_filtered')
            insert(c, {k: v for k, v in p.items() if k != 'ResolverRules'}, 3, None, False, True)
            c.label('bonus_filtered')
        # A proven Boolean callee produces exactly 0/1. Its comparison to 1
        # can be removed before an immediate conditional branch. The callee
        # body remains untouched, including all its native state changes.
        if (op == 0 and args == [1] and i and rows[i-1][1] == 48 and
                rows[i-1][2][0] in p.get('BooleanCalls', []) and i+2 < len(rows) and
                rows[i+1][1] == 24 and rows[i+2][1] in (45, 46) and
                not ({at, rows[i+1][0]} & (targets | hooks))):
            c.label(('source', rows[i+1][0])); i += 2
            continue
        # Keep retail VM instructions; tools' ABI also lists unsupported
        # shorthand opcodes which must not be introduced by this patch.
        consumed, op, args = compact(rows, i, targets | hooks)
        if op in BRANCHES:
            c.jump(op, ('source', args[0]))
        else:
            c.op(op, *args)
        i += consumed
    if resolving:
        resolver_code(c, p)
    result = c.finish(offset)
    engine.require(len(result) <= len(source), '这套游戏的宝箱规则没有足够代码空间，需要适配。')
    # Every original branch is relocated and every path returns before padding.
    return result + struct.pack('<H', 1) * ((len(source)-len(result))//2)
