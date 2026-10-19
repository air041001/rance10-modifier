using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.IO;

// Fake VM memory only: the actual controller runs without opening any process.
internal sealed class LootProfile { internal uint Offset,GuardStart,GuardEnd; internal int Length; internal string SpanHash; }
internal sealed class RuntimeProfile {
    internal int CodeLength=512;
    internal LootProfile Loot,Drop;
    internal string LootError,DropError;
    internal static string Hash(byte[] b) { using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
}
internal sealed class FakeProcess { internal bool HasExited; internal int Id=42; }
internal sealed class GlobalsPage { internal uint Context=5000,Owner; }
internal sealed class Located { internal GlobalsPage Globals; }
internal static class RuntimeSettings { internal static string GameDirectory,ProfilePath; }
internal static class Fake {
    internal static readonly byte[] Memory=new byte[512];
    internal static RuntimeProfile Profile;
    internal static uint Owner=2,IP=100010;
    internal static int Writes,FailAt;
    internal static bool Paused;
    internal static uint[] Callers=new uint[0];
    internal static byte[] Original;
    internal static void Reset() {
        for(int i=0;i<Memory.Length;i++)Memory[i]=(byte)(i%127);
        Original=Memory.ToArray();Owner=2;IP=100010;Writes=FailAt=0;Callers=new uint[0];
        Profile=new RuntimeProfile { Loot=new LootProfile { Offset=64,Length=32,GuardStart=64,GuardEnd=96 },
                                    Drop=new LootProfile { Offset=160,Length=48,GuardStart=150,GuardEnd=220 } };
        foreach(var p in new[]{Profile.Loot,Profile.Drop})p.SpanHash=RuntimeProfile.Hash(Memory.Skip((int)p.Offset).Take(p.Length).ToArray());
    }
}
internal sealed class Connection : IDisposable {
    internal FakeProcess Process=new FakeProcess();
    internal RuntimeProfile Profile { get { return Fake.Profile; } }
    internal long Session=10;
    internal IntPtr Handle=IntPtr.Zero;
    internal Dictionary<string,uint> Types=new Dictionary<string,uint>{{"Stack",123}};
    internal Connection(bool write,bool food) {}
    internal byte[] Read(uint address,int size) {
        if(address==5140)return BitConverter.GetBytes((uint)100000).Concat(BitConverter.GetBytes((uint)100512)).ToArray();
        if(address==5136)return BitConverter.GetBytes(Fake.IP);
        if(address==5188)return BitConverter.GetBytes((uint)123).Concat(BitConverter.GetBytes(Fake.Callers.Length-1)).ToArray();
        if(address==5196)return Fake.Callers.SelectMany(v=>BitConverter.GetBytes(v)).ToArray();
        if(address>=100000 && address+(uint)size<=100512)return Fake.Memory.Skip((int)address-100000).Take(size).ToArray();
        throw new Exception("Unexpected read");
    }
    public void Dispose() {}
}
internal static class Engine {
    internal static GlobalsPage CheckGlobals(Connection c,uint owner){return new GlobalsPage{Owner=Fake.Owner};}
    internal static bool SameGlobals(GlobalsPage a,GlobalsPage b){return a.Owner==b.Owner && a.Context==b.Context;}
    internal static Located Locate(Connection c,bool food){return new Located{Globals=new GlobalsPage{Owner=Fake.Owner}};}
}
internal sealed class PausedGame : IDisposable {
    internal PausedGame(FakeProcess p){if(Fake.Paused)throw new Exception("Nested pause");Fake.Paused=true;}
    public void Dispose(){Fake.Paused=false;}
}
internal static class Native {
    internal static bool WriteProcessMemory(IntPtr h,IntPtr address,byte[] data,UIntPtr size,out UIntPtr written) {
        if(!Fake.Paused)throw new Exception("Unpaused write");
        Fake.Writes++;int count=(int)size.ToUInt64();bool success=Fake.Writes!=Fake.FailAt;
        if(!success){count/=2;Fake.FailAt=0;}
        Array.Copy(data,0,Fake.Memory,(int)address.ToInt64()-100000,count);written=(UIntPtr)(uint)count;return success;
    }
}
internal static class Harness {
    static object Call(string name,params object[] args) {
        try{return typeof(LootSelector).GetMethod(name,BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,args);}
        catch(TargetInvocationException e){throw e.InnerException;}
    }
    static void Assert(bool value,string message){if(!value)throw new Exception(message);}
    static Dictionary<string,object> Command(bool all,bool unique,bool drop) {
        return new Dictionary<string,object>{{"pid",42},{"session",10L},{"global_owner",Fake.Owner},
            {"all_cards",all},{"unique",unique},{"guaranteed",drop},
            {"patch",Convert.ToBase64String(Enumerable.Repeat((byte)230,32).ToArray())},
            {"drop_patch",Convert.ToBase64String(Enumerable.Repeat((byte)231,48).ToArray())}};
    }
    static bool SameOriginal(){return Fake.Memory.SequenceEqual(Fake.Original);}
    static bool Patched(bool pool,bool drop) {
        return Fake.Memory.Skip(64).Take(32).SequenceEqual(pool?Enumerable.Repeat((byte)230,32):Fake.Original.Skip(64).Take(32)) &&
            Fake.Memory.Skip(160).Take(48).SequenceEqual(drop?Enumerable.Repeat((byte)231,48):Fake.Original.Skip(160).Take(48));
    }
    static bool Failed(string name,params object[] args) {try{Call(name,args);return false;}catch(InvalidOperationException){return true;}}
    static int Main() {
        RuntimeSettings.ProfilePath=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"profile.json");
        File.WriteAllText(RuntimeSettings.ProfilePath,"{}");
        for(int bits=1;bits<8;bits++) {
            Fake.Reset();bool all=(bits&1)!=0,unique=(bits&2)!=0,drop=(bits&4)!=0;
            Call("Arm",Command(all,unique,drop));Assert(Patched(all||unique,drop),"combination "+bits);
            Call("Restore");Assert(SameOriginal(),"restore "+bits);
        }
        Console.WriteLine("PASS all seven combinations and restores");
        Fake.Reset();Fake.Profile.Loot=null;Call("Arm",Command(false,false,true));Call("Restore");Assert(SameOriginal(),"drop without pool");
        Fake.Reset();Fake.Profile.Drop=null;Call("Arm",Command(true,false,false));Call("Restore");Assert(SameOriginal(),"pool without drop");
        Console.WriteLine("PASS independent optional features");
        Fake.Reset();Fake.FailAt=2;Assert(Failed("Arm",Command(true,true,true)),"partial write must fail");Assert(SameOriginal(),"arm rollback");
        Console.WriteLine("PASS second-span partial write restores both originals");
        Fake.Reset();Call("Arm",Command(true,true,true));Fake.Writes=0;Fake.FailAt=2;
        Assert(Failed("Restore"),"partial restore must fail");Assert(Patched(true,true),"restore rollback");
        Call("Restore");Assert(SameOriginal(),"restore retry");
        Console.WriteLine("PASS partial restore rollback and retry");
        foreach(uint ip in new uint[]{100070,100180}) {
            Fake.Reset();Fake.IP=ip;Assert(Failed("Arm",Command(true,true,true)),"active guard");Assert(Fake.Writes==0 && SameOriginal(),"guard writes");
        }
        Console.WriteLine("PASS active execution guards for both functions");
        foreach(uint caller in new uint[]{70,180,100070,100180}) {
            Fake.Reset();Fake.Callers=new[]{caller};Assert(Failed("Arm",Command(true,true,true)),"active caller guard");
            Assert(Fake.Writes==0 && SameOriginal(),"caller guard writes");
        }
        Console.WriteLine("PASS active return-stack guards for both address forms");
        Fake.Reset();Call("Arm",Command(true,true,true));
        var probed=(Dictionary<string,object>)Call("Probe",Command(true,true,true));
        var snapshot=(Dictionary<string,object>)probed["snapshot"];
        Assert(Convert.FromBase64String((string)snapshot["source_code"]).SequenceEqual(Fake.Original.Skip(64).Take(32)),"pool probe original");
        Assert(Convert.FromBase64String((string)snapshot["drop_source_code"]).SequenceEqual(Fake.Original.Skip(160).Take(48)),"drop probe original");
        Call("Restore");
        Console.WriteLine("PASS probe returns original bytes while both rules are active");
        Fake.Reset();Call("Arm",Command(true,true,true));Fake.Owner=3;
        Assert(!(bool)Call("Current"),"save switch detected");Call("Restore");Assert(SameOriginal(),"save switch restore");
        Console.WriteLine("PASS changed save globals restore both spans");
        Fake.Reset();Call("Arm",Command(true,true,true));Fake.Memory[160]=240;Fake.Writes=0;
        Assert(Failed("Restore") && Fake.Writes==0,"foreign change not overwritten");
        Fake.Memory[160]=231;Call("Restore");Assert(SameOriginal(),"foreign restoration retry");
        Console.WriteLine("PASS foreign changes are preserved");
        Fake.Reset();Call("Arm",Command(false,false,true));Call("Arm",Command(true,true,false));Assert(Patched(true,false),"toggle combinations");
        Call("Restore");Assert(SameOriginal(),"final restore");
        Console.WriteLine("PASS toggling between guaranteed-only and pool-only");
        return 0;
    }
}
