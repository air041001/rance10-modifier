using System;
using System.Linq;

internal sealed class BattlePage {
    internal int Handle;
    internal uint Pointer, Data;
    internal byte[] Metadata;
    internal int[] Flags, Points;
}

internal static class BattleResults {
    internal static readonly string[] Countries = { "利萨斯", "赫尔曼", "赛斯", "自由都市" };

    internal static int TargetValue(string action, int before, int amount, int country) {
        if(country<1 || country>4)throw new InvalidOperationException("请选择四国之一的战果。");
        if(before<0 || before>3)throw new InvalidOperationException("当前战果超出0到3的范围，请刷新。");
        if(action=="fillbattle3")return 3;
        if(action!="addbattle" || (amount!=-1 && amount!=1))throw new InvalidOperationException("战果每次增加或减少1点。");
        return Math.Max(0,Math.Min(3,before+amount));
    }

    internal static BattlePage Read(Connection c, GlobalsPage globals) {
        var profile=c.Profile.Battle;
        if(profile==null)throw new InvalidOperationException(c.Profile.BattleError ?? "这个游戏的战果数据需要适配。");
        if(!c.Types.ContainsKey("Array") || !c.Types.ContainsKey("ArrayKind"))
            throw new InvalidOperationException("战果数组对象类型需要适配。");
        var vm=new VmPages(c,globals);
        int handle=vm.Global(profile.FlagGlobal);
        uint pointer;
        byte[] metadata=vm.Page(handle,3,out pointer);
        int[] flags=vm.Values(handle,3);
        if(flags.Length<=profile.LastIndex)throw new InvalidOperationException("尚未读到四国战果，请载入游戏进度。");
        int[] points=flags.Skip(profile.FirstIndex).Take(4).ToArray();
        if(points.Any(value=>value<0 || value>profile.Maximum))
            throw new InvalidOperationException("当前四国战果数据需要适配。");
        uint confirmed;
        if(!metadata.SequenceEqual(vm.Page(handle,3,out confirmed)) || pointer!=confirmed ||
            vm.Global(profile.FlagGlobal)!=handle || !Engine.SameGlobals(globals,Engine.CheckGlobals(c,globals.Owner)))
            throw new InvalidOperationException("游戏正在切换进度，请刷新战果。");
        return new BattlePage { Handle=handle, Pointer=pointer, Data=BitConverter.ToUInt32(metadata,16),
            Metadata=metadata, Flags=flags, Points=points };
    }

    internal static BattlePage Write(Connection c, LiveObject food, LiveObject bonus, BattlePage before,
            string action, int amount, int country, out int writes) {
        writes=0;
        // Resolve and write under a short pause so a simultaneous load cannot
        // free the flags array between the last reference check and the write.
        using(var paused=new PausedGame(c.Process)) {
            var globals=Engine.CheckGlobals(c,food.Globals.Owner);
            if(!Engine.SameGlobals(globals,food.Globals) || !Engine.SameGlobals(globals,bonus.Globals))
                throw new InvalidOperationException("游戏正在切换进度，本次未修改。");
            BattlePage fresh=Read(c,globals);
            if(fresh.Handle!=before.Handle || fresh.Pointer!=before.Pointer || fresh.Data!=before.Data ||
                !fresh.Metadata.SequenceEqual(before.Metadata) || !fresh.Flags.SequenceEqual(before.Flags))
                throw new InvalidOperationException("战果刚刚变化，请刷新后重试。");
            int value=TargetValue(action,fresh.Points[country-1],amount,country);
            int index=c.Profile.Battle.FirstIndex+country-1;
            if(value==fresh.Flags[index])return fresh;
            var vm=new VmPages(c,globals);
            if(!vm.Record(globals.PlayerHandle,"PlayerCommonParam").SequenceEqual(food.Values) ||
                !vm.Record(globals.BonusHandle,"PartyBonusSwitcher").SequenceEqual(bonus.Values))
                throw new InvalidOperationException("游戏资源刚刚变化，请刷新后重试。");
            UIntPtr written;
            if(!Native.WriteProcessMemory(c.Handle,new IntPtr((long)(fresh.Data+(uint)index*4)),
                    BitConverter.GetBytes(value),(UIntPtr)4,out written) || written.ToUInt64()!=4)
                throw new InvalidOperationException("战果写入失败。");
            writes=4;
            BattlePage after=Read(c,globals);
            int[] expected=(int[])fresh.Flags.Clone();
            expected[index]=value;
            if(after.Handle!=fresh.Handle || after.Data!=fresh.Data || !after.Flags.SequenceEqual(expected))
                throw new InvalidOperationException("战果写入后校验未通过，请刷新并查看游戏。");
            if(!vm.Record(globals.PlayerHandle,"PlayerCommonParam").SequenceEqual(food.Values) ||
                !vm.Record(globals.BonusHandle,"PartyBonusSwitcher").SequenceEqual(bonus.Values))
                throw new InvalidOperationException("游戏资源同时发生变化，请刷新并查看游戏。");
            return after;
        }
    }
}
