"""Guarantee eligible victory treasure rolls; preserve the native prohibition."""
import hashlib
import engine
from loot_code import Code, decode


def describe(ain):
    ordered = sorted(ain['functions'], key=lambda f: f['address'])
    named = {}
    for f in ordered:
        named.setdefault(f['name'], f)
    ends = {f['index']: ordered[i+1]['address']-6 for i, f in enumerate(ordered[:-1])}
    def function(name, argc, result):
        f = named.get(name)
        engine.require(f is not None and f['argc'] == argc and f['returned'][0] == result,
                       '宝箱必掉落调用需要适配：'+name)
        return f
    def rows(f): return decode(ain['code'], f['address'], ends[f['index']])
    calc = function('SceneBattleResult@CalcResult', 0, 0)
    getter = function('BattleResult@Type::get', 0, 92)
    rand = function('RAND', 1, 10)
    forbidden = function('SceneBattleResult@IsForceNoTreasure::get', 0, 47)
    scene = next((s for s in ain['structures'] if s['name']=='SceneBattleResult'), None)
    fields = [] if scene is None else [(i,m) for i,m in enumerate(scene['members']) if m['name']=='m_isGetTreasure']
    engine.require(len(fields)==1 and fields[0][1]['type'][0]==47, '宝箱结算状态需要适配。')
    field = fields[0][0]
    battle = next((g for g in ain['globals'] if g['name']=='g_battleResult'), None)
    engine.require(battle is not None and battle['type'][0]==13 and
                   any(s['index']==battle['type'][1] and s['name']=='BattleResult' for s in ain['structures']),
                   '宝箱战斗结算对象需要适配。')
    # Infer victory from the original bonus dispatcher, not from translated text.
    bonus = rows(function('BattleBonusCalculator::Calc', 1, 0))
    treasure = function('BattleBonusCalculator::CalcTreasure', 0, 0)
    engine.require([(o,a) for _,o,a in bonus[:3]]==[(5,[]),(0,[0]),(2,[])] and
                   bonus[3][1]==0 and [o for _,o,_ in bonus[4:7]]==[24,46,44] and
                   any(o==48 and a==[treasure['index']] and bonus[5][2][0]<=at<bonus[6][2][0]
                       for at,o,a in bonus), '宝箱胜利结算条件需要适配。')
    victory = bonus[3][2][0]
    body = rows(calc)
    expected = [(91,[]),(0,[field]),(0,[100]),(48,[rand['index']]),
                (4,[]),(0,[battle['index']]),(2,[]),(0,[named['BattleResult@GetTotalPerTreasure']['index']]),
                (92,[0]),(21,[]),(25,[]),(1,[])]
    sites = [i for i in range(len(body)-len(expected))
             if [(o,a) for _,o,a in body[i:i+len(expected)]]==expected]
    engine.require(len(sites)==1, '未找到独立的宝箱概率判定。')
    i = sites[0]; start = body[i][0]; end = body[i+len(expected)][0]
    guard = body[i-11:i]
    # Only the random branch is replaced. The original force-no-treasure path
    # must still skip this entire span and assign false to the same field.
    engine.require(len(guard)==11 and [(o,a) for _,o,a in guard[:3]]==
                   [(91,[]),(0,[forbidden['index']]),(92,[0])] and
                   guard[3][1:]==(46,[guard[5][0]]) and guard[4][1:]==(44,[start]) and
                   [(o,a) for _,o,a in guard[5:10]]==[(91,[]),(0,[field]),(0,[0]),(25,[]),(1,[])] and
                   guard[10][1:]==(44,[end]), '剧情禁止宝箱的分支需要适配。')
    positions = {at for at,_,_ in body}
    engine.require(all(a[0] in positions and not start<a[0]<end for _,o,a in body if o in (44,45,46)),
                   '宝箱概率判定含有额外入口，需要适配。')
    return dict(Offset=start,Length=end-start,SpanHash=hashlib.sha256(ain['code'][start:end]).hexdigest(),
                GuardStart=calc['address'],GuardEnd=ends[calc['index']],
                BattleGlobal=battle['index'],GetType=getter['index'],Field=field,Victory= victory)


def make_code(source, profile):
    p = profile['Drop']
    engine.require(len(source)==p['Length'] and hashlib.sha256(source).hexdigest()==p['SpanHash'],
                   '宝箱必掉落原始代码不一致。')
    c = Code()
    c.op(91); c.op(0,p['Field'])
    c.op(4); c.op(0,p['BattleGlobal']); c.op(2)
    c.op(0,p['GetType']); c.op(92,0)
    c.op(0,p['Victory']); c.op(24); c.op(25); c.op(1)
    # Jump over padding: POP is not a no-op when the operand stack is empty.
    c.op(44,p['Offset']+p['Length'])
    engine.require(len(c.data)==len(source), '宝箱必掉落代码空间需要适配。')
    return bytes(c.data)
