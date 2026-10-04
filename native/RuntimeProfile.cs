using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

#pragma warning disable 0649 // Descriptor fields are assigned by the JSON deserializer.

internal sealed class FoodProfile {
    public uint Offset, GuardStart, GuardEnd;
    public int Length, FirstLength, SecondOffset, GetCharacter, IsMax;
    public string SpanHash;
}

internal sealed class RuntimeProfile {
    public int Schema, GlobalCount, PlayerGlobal, BonusGlobal, CharacterGlobal, CardGlobal, CodeLength, CodePage;
    public int GameGlobal = -1;
    public string AinHash, ExeHash, CodeHash, FoodError;
    public Dictionary<string,int[]> Fields;
    public Dictionary<string,int> Counts;
    public FoodProfile Food;

    internal static int? DisplayChapter(int value) {
        // GameChapter::Parse maps Chapter1 to 0 and Chapter2 to 1.
        // The enum dump lists ordinal positions, not these runtime values.
        return value == 0 ? (int?)1 : value == 1 ? (int?)2 : null;
    }

    internal static string Hash(byte[] data) {
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(data)).Replace("-", "").ToLowerInvariant();
    }
    internal static string FileHash(string file) {
        using (SHA256 sha = SHA256.Create())
        using (FileStream input = File.OpenRead(file))
            return BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
    }
    internal static RuntimeProfile Load(string file) {
        if (String.IsNullOrEmpty(file)) throw new InvalidOperationException("缺少本机游戏的运行结构资料，请更新完整修改器。");
        var result = new JavaScriptSerializer().Deserialize<RuntimeProfile>(File.ReadAllText(file, Encoding.UTF8));
        if (result == null || result.Schema != 1 || result.GlobalCount < 1 || result.GlobalCount > 10000 ||
            result.CodeLength < 1 || result.CodeLength > 64*1024*1024 || result.Fields == null || result.Counts == null ||
            (result.CodePage != 932 && result.CodePage != 936) ||
            new int[]{result.PlayerGlobal,result.BonusGlobal,result.CharacterGlobal,result.CardGlobal}.Any(i=>i<0 || i>=result.GlobalCount))
            throw new InvalidOperationException("本机运行结构资料无效，请重新读取游戏。");
        foreach (var pair in result.Fields) {
            int count;
            if (!result.Counts.TryGetValue(pair.Key,out count) || count < 1 || count > 4096 ||
                pair.Value == null || pair.Value.Any(i=>i < -1 || i>=count))
                throw new InvalidOperationException("本机字段映射无效，请重新读取游戏。");
        }
        var f = result.Food;
        if (f != null && (f.Length < 8 || f.Length > 8192 || f.Offset + f.Length > result.CodeLength ||
            f.FirstLength < 80 || f.FirstLength > f.SecondOffset || f.SecondOffset >= f.Length ||
            f.GuardStart > f.Offset || f.GuardEnd <= f.Offset + f.Length || f.GuardEnd > result.CodeLength))
            throw new InvalidOperationException("餐券运行结构资料无效，请重新读取游戏。");
        return result;
    }
    internal int[] Normalize(string name, int[] values) {
        if (!Counts.ContainsKey(name) || values.Length != Counts[name])
            throw new InvalidOperationException("运行对象字段数量不同："+name);
        return Fields[name].Select(i=>i<0?0:values[i]).ToArray();
    }
}

// Resolve actual loaded C++ types, including translated or packed executables.
// Header offsets are accepted only when the sys43vm object graph also validates.
internal static class RuntimeTypes {
    static readonly Dictionary<string,Tuple<string,int>> Wanted = new Dictionary<string,Tuple<string,int>> {
        {"Memory",Tuple.Create(".?AVCFastMemory@memory@@",0)},
        {"Global",Tuple.Create(".?AVCGlobalPage@sys43vm@@",0)},
        {"GlobalKind",Tuple.Create(".?AVCGlobalPage@sys43vm@@",32)},
        {"Struct",Tuple.Create(".?AVCStructPage@sys43vm@@",0)},
        {"StructKind",Tuple.Create(".?AVCStructPage@sys43vm@@",32)},
        {"String",Tuple.Create(".?AVCStringPage@sys43vm@@",0)},
        {"StringKind",Tuple.Create(".?AVCStringPage@sys43vm@@",32)},
        {"Array",Tuple.Create(".?AVCArrayPage@sys43vm@@",0)},
        {"ArrayKind",Tuple.Create(".?AVCArrayPage@sys43vm@@",32)},
        {"Stack",Tuple.Create(".?AVCIntStack@sys43vm@@",0)}
    };
    static IEnumerable<int> Find(byte[] data, byte[] pattern) {
        for (int i=0;i+pattern.Length<=data.Length;i++) {
            if(data[i]!=pattern[0])continue;
            int j=1;while(j<pattern.Length && data[i+j]==pattern[j])j++;
            if(j==pattern.Length)yield return i;
        }
    }
    internal static Dictionary<string,uint> Resolve(Connection c, bool includeFood=false) {
        int size = c.Process.MainModule.ModuleMemorySize;
        if(size<4096 || size>256*1024*1024)throw new InvalidOperationException("游戏引擎映像大小需要适配。");
        byte[] image=new byte[size];
        ulong start=c.ModuleBase, end=start+(uint)size, address=start;
        while(address<end) {
            Native.MemoryInfo info;
            if(Native.VirtualQueryEx(c.Handle,new IntPtr((long)address),out info,(UIntPtr)(uint)Marshal.SizeOf(typeof(Native.MemoryInfo))).ToUInt64()==0)break;
            ulong lo=Math.Max(start,(ulong)info.Base.ToInt64()),hi=Math.Min(end,(ulong)info.Base.ToInt64()+info.Size.ToUInt64());
            if(hi<=address)break;
            uint protection=info.Protect&255;
            if(info.State==0x1000 && (info.Protect&256)==0 && protection!=0 && protection!=1) {
                byte[] part=c.Read((uint)lo,(int)(hi-lo));
                if(part!=null)Buffer.BlockCopy(part,0,image,(int)(lo-start),part.Length);
            }
            address=hi;
        }
        return Decode(image,c.ModuleBase,includeFood);
    }
    internal static Dictionary<string,uint> Decode(byte[] image,uint moduleBase,bool includeFood=false) {
        ulong start=moduleBase,end=start+(uint)image.Length;
        var result=new Dictionary<string,uint>();
        foreach(var wanted in Wanted.Where(p=>includeFood || new[]{"Memory","Global","GlobalKind","Struct","StructKind"}.Contains(p.Key))) {
            var matches=new HashSet<uint>();
            foreach(int name in Find(image,Encoding.ASCII.GetBytes(wanted.Value.Item1+'\0'))) {
                if(name<8)continue;
                uint descriptor=moduleBase+(uint)name-8;
                foreach(int reference in Find(image,BitConverter.GetBytes(descriptor))) {
                    int locator=reference-12;
                    if(locator<0 || locator+20>image.Length || BitConverter.ToUInt32(image,locator)!=0 ||
                        BitConverter.ToInt32(image,locator+4)!=wanted.Value.Item2 || BitConverter.ToUInt32(image,locator+8)!=0)continue;
                    uint col=moduleBase+(uint)locator;
                    foreach(int table in Find(image,BitConverter.GetBytes(col))) {
                        if((table&3)!=0 || table+8>image.Length)continue;
                        uint method=BitConverter.ToUInt32(image,table+4);
                        if(method>=start && method<end)matches.Add(moduleBase+(uint)table+4);
                    }
                }
            }
            if(matches.Count!=1)throw new InvalidOperationException("游戏引擎对象类型需要适配："+wanted.Key);
            result[wanted.Key]=matches.First();
        }
        return result;
    }
}
