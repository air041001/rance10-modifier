"""Temporary random-box rules. Explicit reward IDs never enter this function."""
import hashlib
import struct
import engine

# sys43vm bytecode ABI. Only instructions present in the inspected box routine
# are accepted. Branches are relocated; calls and string-table indices stay local.
ARGS = {0: 1, 44: 1, 45: 1, 46: 1, 48: 1, 65: 1, 90: 3, 92: 1,
        93: 1, 94: 1, 98: 1, 118: 2, 126: 1, 140: 2, 138: 1}
PLAIN = {1, 2, 4, 5, 7, 9, 10, 19, 20, 21, 22, 23, 24, 25, 41, 42, 47,
         49, 67, 68, 73, 91, 102, 119, 121, 123, 124}
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
    if 'strings' in ain:
        for i in range(len(body)-5):
            chunk = body[i:i+6]
            if ([(op, args) for _, op, args in chunk[:3]] == [(5, []), (0, [5]), (2, [])] and
                    chunk[3][1] == 65 and chunk[4][1] == 68 and chunk[5][1] == 119):
                # No-repeat works before a library exists. Its VM strings stay
                # in the game; the text scope is used only after a matching
                # library has supplied the installation's actual code page.
                value = ain['strings'][chunk[3][2][0]].encode('latin-1').decode('cp%d' % codepage, errors='replace')
                identifiers[2 if chunk[0][0] < checks[0] else 1].add(value)
    return dict(Offset=start, Length=end-start, SpanHash=hashlib.sha256(ain['code'][start:end]).hexdigest(),
                GuardStart=start, GuardEnd=end, Chapter2Site=checks[0], Chapter1Site=checks[1],
                TableString=strings[0], IdString=strings[1], EmptyString=empty,
                GetColumn=col[2], Realloc=realloc[2], ReadString=function('EX_A2String', 5, 12)['index'],
                Height=function('EX_Height', 2, 10)['index'], Owned=owned[0]['index'],
                Stock=stock['index'], CardGlobal=cards['index'],
                Chapter1Ids=sorted(identifiers[1]), Chapter2Ids=sorted(identifiers[2]))


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
        for n, (first, last) in enumerate(ranges(eligible)):
            loop = prefix+'row%d' % n
            c.integer(3, first); c.label(loop)
            c.increment(8)
            c.local(7); c.local(4); c.local(8); c.op(9); c.op(2)
            c.op(65, p['TableString']); c.local(10); c.local(3); c.op(65, p['EmptyString']); c.op(0, 0)
            c.op(48, p['ReadString']); c.op(68); c.op(119)
            c.increment(3); c.local(3); c.op(0, last); c.op(21); c.jump(46, loop)
    c.label(filter_)
    c.local(8); c.set(1); c.integer(8, 0); c.integer(3, 1)
    loop = prefix+'candidate'
    c.label(loop)
    c.local(3); c.local(1); c.op(21); c.jump(45, end_)
    c.local(7); c.local(4); c.local(3); c.op(9); c.op(2); c.op(121); c.assign_string(5)
    if unique:
        c.local(5); c.op(121); c.op(48, p['Owned']); c.jump(46, next_)
        c.op(4); c.op(0, p['CardGlobal']); c.op(2)
        c.op(0, p['Stock']); c.local(5); c.op(121); c.op(92, 1)
        c.op(0, 0); c.op(22); c.jump(46, next_)
    c.increment(8); c.local(7); c.local(8); c.op(2); c.local(5); c.op(121); c.op(68); c.op(119)
    c.label(next_); c.increment(3); c.jump(44, loop)
    c.label(end_)
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
    while i < len(rows):
        at, op, args = rows[i]
        c.label(('source', at))
        if at in sites:
            insert(c, p, sites[at], catalog, all_cards, unique)
        # Keep retail VM instructions; tools' ABI also lists unsupported
        # shorthand opcodes which must not be introduced by this patch.
        consumed, op, args = compact(rows, i, targets | set(sites))
        if op in BRANCHES:
            c.jump(op, ('source', args[0]))
        else:
            c.op(op, *args)
        i += consumed
    result = c.finish(offset)
    engine.require(len(result) <= len(source), '这套游戏的宝箱规则没有足够代码空间，需要适配。')
    # Every original branch is relocated and every path returns before padding.
    return result + struct.pack('<H', 1) * ((len(source)-len(result))//2)
