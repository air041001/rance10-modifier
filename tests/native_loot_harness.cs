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
internal sealed class FakeProcess {
    internal int Id=Fake.Pid;
    readonly long generation=Fake.Generation;
    internal bool HasExited { get { return !Fake.Running || generation!=Fake.Generation; } }
}
internal sealed class GlobalsPage { internal uint Context=Fake.Context,Owner; }
internal sealed class Located { internal GlobalsPage Globals; }
internal static class RuntimeSettings { internal static string GameDirectory,ProfilePath; }
internal static class Fake {
    internal static readonly byte[] Memory=new byte[512];
    internal static RuntimeProfile Profile;
    internal static uint Owner=2,IP=100010,Base=100000,Context=5000;
    internal static int Pid=42;
    internal static long Generation=10;
    internal static bool Running=true,Ready=true;
    internal static int Writes,FailAt;
    internal static bool Paused;
    internal static uint[] Callers=new uint[0];
    internal static byte[] Original;
    internal static void Reset() {
        for(int i=0;i<Memory.Length;i++)Memory[i]=(byte)(i%127);
        Original=Memory.ToArray();Owner=2;IP=100010;Writes=FailAt=0;Callers=new uint[0];
        Base=100000;Context=5000;Pid=42;Generation=10;Running=Ready=true;
        Profile=new RuntimeProfile { Loot=new LootProfile { Offset=64,Length=32,GuardStart=64,GuardEnd=96 },
                                    Drop=new LootProfile { Offset=160,Length=48,GuardStart=150,GuardEnd=220 } };
        foreach(var p in new[]{Profile.Loot,Profile.Drop})p.SpanHash=RuntimeProfile.Hash(Memory.Skip((int)p.Offset).Take(p.Length).ToArray());
    }
}
internal sealed class Connection : IDisposable {
    internal FakeProcess Process=new FakeProcess();
    internal RuntimeProfile Profile { get { return Fake.Profile; } }
    internal long Session=Fake.Generation;
    internal IntPtr Handle=IntPtr.Zero;
    internal Dictionary<string,uint> Types=new Dictionary<string,uint>{{"Stack",123}};
    internal Connection(bool write,bool food) {if(!Fake.Running)throw new InvalidOperationException("No game running");}
    internal byte[] Read(uint address,int size) {
        if(address==Fake.Context+140)return BitConverter.GetBytes(Fake.Base).Concat(BitConverter.GetBytes(Fake.Base+512)).ToArray();
        if(address==Fake.Context+136)return BitConverter.GetBytes(Fake.IP);
        if(address==Fake.Context+188)return BitConverter.GetBytes((uint)123).Concat(BitConverter.GetBytes(Fake.Callers.Length-1)).ToArray();
        if(address==Fake.Context+196)return Fake.Callers.SelectMany(v=>BitConverter.GetBytes(v)).ToArray();
        if(address>=Fake.Base && address+(uint)size<=Fake.Base+512)return Fake.Memory.Skip((int)(address-Fake.Base)).Take(size).ToArray();
        throw new Exception("Unexpected read");
    }
    public void Dispose() {}
}
internal static class Engine {
    internal static GlobalsPage CheckGlobals(Connection c,uint owner){if(!Fake.Ready)throw new InvalidOperationException("Loading");return new GlobalsPage{Owner=Fake.Owner};}
    internal static bool SameGlobals(GlobalsPage a,GlobalsPage b){return a.Owner==b.Owner && a.Context==b.Context;}
    internal static Located Locate(Connection c,bool food){if(!Fake.Ready)throw new InvalidOperationException("Loading");return new Located{Globals=new GlobalsPage{Owner=Fake.Owner}};}
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
        Array.Copy(data,0,Fake.Memory,(int)(address.ToInt64()-Fake.Base),count);written=(UIntPtr)(uint)count;return success;
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
    static Dictionary<string,object> State(){return (Dictionary<string,object>)Call("State",true,false,"");}
    static void RestoreMemory(){Array.Copy(Fake.Original,Fake.Memory,Fake.Memory.Length);}
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
        for(int bits=1;bits<8;bits++) {
            Fake.Reset();bool all=(bits&1)!=0,unique=(bits&2)!=0,drop=(bits&4)!=0;
            Call("Enable",Command(all,unique,drop));int initial=Fake.Writes;
            for(int reload=0;reload<6;reload++) {
                Fake.Owner++;Fake.Context+=1000;
                Assert((bool)Call("Maintain") && Patched(all||unique,drop),"reload preserves rules");
                Assert(Fake.Writes==initial,"unchanged code should not be restored/repatched");
            }
            RestoreMemory();Call("Maintain");Assert(Patched(all||unique,drop),"same-owner code reset");
            Assert((bool)State()["enabled"] && (bool)State()["armed"],"selection survives refresh");
            Call("Cancel");Assert(SameOriginal() && !(bool)State()["enabled"],"cancel selection");
        }
        Console.WriteLine("PASS reload, retry and code reset preserve all seven selections");
        Fake.Reset();Call("Enable",Command(true,true,true));Fake.Ready=false;Call("Tick");
        Assert((bool)State()["enabled"] && (bool)State()["waiting"] && !(bool)State()["armed"],"loading keeps intent");
        Fake.Ready=true;Fake.Owner++;Call("Tick");Assert((bool)State()["armed"] && Patched(true,true),"resume after loading");
        RestoreMemory();Fake.IP=Fake.Base+180;Call("Tick");Assert((bool)State()["waiting"] && SameOriginal(),"retry guard waits");
        Fake.IP=Fake.Base+10;Call("Tick");Assert((bool)State()["armed"] && Patched(true,true),"guard later reapplies");
        Call("Cancel");
        Console.WriteLine("PASS loading and active-function waits keep choices and later resume");
        Fake.Reset();Call("Enable",Command(true,true,true));Fake.Base+=10000;Fake.Context+=1000;Fake.Owner++;Fake.IP=Fake.Base+10;RestoreMemory();
        Call("Maintain");Assert(Patched(true,true) && (bool)State()["armed"],"new VM allocation");Call("Cancel");
        Console.WriteLine("PASS relocated VM is reattached without writing stale addresses");
        Fake.Reset();Call("Enable",Command(true,true,true));Fake.Running=false;Call("Tick");
        Assert((bool)State()["enabled"] && (bool)State()["waiting"],"game closed keeps intent");
        Fake.Running=true;Fake.Pid++;Fake.Generation++;Fake.Owner++;RestoreMemory();Call("Tick");
        Assert(Patched(true,true) && (bool)State()["armed"],"new game session");Call("Cancel");
        Console.WriteLine("PASS game restart refreshes process/session identity");
        Fake.Reset();Call("Enable",Command(true,true,true));Fake.Ready=false;Call("Tick");
        Assert(Failed("Cancel"),"cancel during transition may defer restore");Assert(!(bool)State()["enabled"],"cancel clears intent first");
        Fake.Ready=true;Fake.Owner++;RestoreMemory();Fake.Writes=0;Call("Tick");
        Assert(SameOriginal() && Fake.Writes==0 && !(bool)State()["armed"],"cancelled choices stay cancelled");
        Console.WriteLine("PASS cancelling during reload prevents automatic re-enable");
        Fake.Reset();Call("Enable",Command(true,true,true));Fake.Memory[160]=240;Fake.Writes=0;Call("Tick");
        Assert((bool)State()["waiting"] && Fake.Writes==0,"auto resume preserves foreign code");
        Fake.Memory[160]=231;Call("Cancel");
        Console.WriteLine("PASS auto resume never overwrites foreign changes");
        return 0;
    }
}
