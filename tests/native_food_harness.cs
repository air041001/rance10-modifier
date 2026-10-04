using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;

internal static class RuntimeSettings { internal static string GameDirectory,ProfilePath; }
internal sealed class FoodProfile {
    internal uint Offset=0x449b38,GuardStart=0x449b10,GuardEnd=0x44a2f0;
    internal int Length=368,FirstLength=114,SecondOffset=256;
    internal string SpanHash="unused";
}
internal sealed class RuntimeProfile {
    internal FoodProfile Food=new FoodProfile(); internal string FoodError;
    internal int CodeLength=14572638,CodePage=936,CharacterGlobal=257,CardGlobal=259;
    internal Dictionary<string,int> Counts=new Dictionary<string,int>();
    internal int[] Normalize(string name,int[] values){return values;}
}
internal sealed class GlobalsPage { internal uint Owner=0x20000, Data=0x30000, Context=0x40000; internal int PlayerHandle=1; }
internal sealed class LiveObject { internal GlobalsPage Globals; }
internal sealed class Connection : IDisposable {
    internal Process Process=Process.GetCurrentProcess(); internal IntPtr Handle=(IntPtr)1;
    internal uint ModuleBase=0x400000, Marker=0x7945d8; internal long Session=1;
    internal RuntimeProfile Profile=new RuntimeProfile();
    internal Dictionary<string,uint> Types=new Dictionary<string,uint>{{"Stack",0x7987e4}};
    internal Dictionary<uint,byte[]> Memory=new Dictionary<uint,byte[]>();
    internal Connection(bool write, bool includeFood=false) { }
    internal byte[] Read(uint address,int size) {
        if(size==0)return new byte[0];
        foreach(var part in Memory)if(address>=part.Key && address+(uint)size<=part.Key+part.Value.Length)
            return part.Value.Skip((int)(address-part.Key)).Take(size).ToArray();
        return null;
    }
    internal void Put(uint address, params uint[] values) {
        Memory[address]=values.SelectMany(BitConverter.GetBytes).ToArray();
    }
    public void Dispose() { }
}
internal static class Engine {
    internal static GlobalsPage Page=new GlobalsPage();
    internal static GlobalsPage CheckGlobals(Connection c,uint owner) { return Page; }
    internal static bool SameGlobals(GlobalsPage a,GlobalsPage b) { return Object.ReferenceEquals(a,b); }
    internal static LiveObject Locate(Connection c,bool b) { return new LiveObject{Globals=Page}; }
}
internal static class Native {
    internal static Connection C;
    internal static int Suspended,Resumed,Writes,Mode;
    internal static IntPtr OpenThread(uint access,bool inherit,int id) { return (IntPtr)id; }
    internal static uint Wow64SuspendThread(IntPtr handle) { Suspended++;return 0; }
    internal static bool Wow64GetThreadContext(IntPtr h,byte[] ctx) { return true; }
    internal static uint ResumeThread(IntPtr handle) { Resumed++;return 1; }
    internal static bool CloseHandle(IntPtr handle) { return true; }
    internal static bool WriteProcessMemory(IntPtr handle,IntPtr address,byte[] data,UIntPtr count,out UIntPtr written) {
        Writes++;
        int size=(int)count.ToUInt64();
        bool fail=Mode==2 || Mode==1 && Writes==1;
        if(fail)size=3;
        uint pos=(uint)address.ToInt64();
        foreach(var part in C.Memory)if(pos>=part.Key && pos+size<=part.Key+part.Value.Length)
            Array.Copy(data,0,part.Value,(int)(pos-part.Key),size);
        written=(UIntPtr)(uint)size;return !fail;
    }
}
internal static class Harness {
    static uint code=0x1000000, offset=0x449b38;
    static byte[] original=Enumerable.Repeat((byte)7,368).ToArray();
    static byte[] replacement=Enumerable.Repeat((byte)9,368).ToArray();
    static void Set(string name,object value) { typeof(FoodSelector).GetField(name,BindingFlags.NonPublic|BindingFlags.Static).SetValue(null,value); }
    static void Reset() {
        Native.C=new Connection(true);Native.Mode=Native.Writes=Native.Suspended=Native.Resumed=0;
        Native.C.Memory[code+offset]=(byte[])original.Clone();
        Native.C.Put(Engine.Page.Context+136,code+100,code,code+14572638);
        Native.C.Put(Engine.Page.Context+188,Native.C.ModuleBase+0x3987e4,UInt32.MaxValue);
        Set("connection",Native.C);Set("globals",Engine.Page);Set("codeBase",code);Set("patch",new byte[368]);
    }
    static string Write(byte[] expected) {
        try { typeof(FoodSelector).GetMethod("Write",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,new object[]{Engine.Page,expected,replacement});return "ok"; }
        catch(TargetInvocationException ex) { return ex.InnerException.Message; }
        finally { if(Native.Suspended!=Native.Resumed)throw new Exception("A game thread was left paused"); }
    }
    static void Assert(bool check,string name) { if(!check)throw new Exception(name);Console.WriteLine("PASS "+name); }
    static void TargetFixture(uint stage) {
        Reset();
        var c=Native.C;
        c.Types["Struct"]=0x80001;c.Types["StructKind"]=0x80002;
        c.Types["Array"]=0x80003;c.Types["ArrayKind"]=0x80004;
        c.Profile.Counts["Character"]=6;c.Profile.Counts["FoodTicketEvent"]=3;c.Profile.Counts["CharacterCollection"]=1;
        c.Put(Engine.Page.Context+8,0x70000,12);
        var pointers=new Dictionary<int,uint>{{42,0x120000},{10,0x220000},{12,0x320000},{19,0x420000},{20,0x520000}};
        uint[] table=new uint[12];
        foreach(var entry in pointers) {
            uint block=0x71000+(uint)(entry.Key/4)*32;
            table[entry.Key/4]=block;
            c.Put(block+(uint)(entry.Key%4)*4,entry.Value);
        }
        c.Put(0x70000,table);
        Page(42,0x120000,"Struct",4,new uint[]{10,50,0,100,0,12});
        Page(12,0x320000,"Struct",4,new uint[]{10,stage,10});
        Page(19,0x420000,"Struct",4,new uint[]{20});
        Page(20,0x520000,"Array",3,new uint[]{42});
        c.Put(Engine.Page.Data+(uint)c.Profile.CharacterGlobal*4,19);
        Set("targetHandle",42);Set("targetNameHandle",10);Set("targetStoryHandle",12);
        Set("targetPage",(uint)0x120000);Set("targetStringPage",(uint)0x220000);Set("targetStoryPage",(uint)0x320000);
        Set("targetMaximum",2);
    }
    static void Page(int handle,uint pointer,string kind,uint type,uint[] values) {
        Native.C.Put(pointer,Native.C.Types[kind],type,0,Native.C.Marker,pointer+64,
            (uint)values.Length*4,(uint)values.Length*4,1,Native.C.Types[kind+"Kind"],Engine.Page.Context,(uint)handle);
        Native.C.Put(pointer+64,values);
    }
    static bool Current() { return (bool)typeof(FoodSelector).GetMethod("CurrentTarget",BindingFlags.NonPublic|BindingFlags.Static).Invoke(null,null); }
    static object Get(string name) { return typeof(FoodSelector).GetField(name,BindingFlags.NonPublic|BindingFlags.Static).GetValue(null); }
    static int Main() {
        Reset();Assert(Write(original)=="ok" && Native.C.Read(code+offset,368).SequenceEqual(replacement),"write and readback");
        Reset();Native.Mode=1;Assert(Write(original).Contains("原筛选已恢复") && Native.C.Read(code+offset,368).SequenceEqual(original),"partial write is restored");
        Reset();Assert(Write(new byte[368]).Contains("没有覆盖其他修改") && Native.Writes==0,"changed code is not overwritten");
        Reset();Native.C.Put(Engine.Page.Context+136,code+offset,code,code+14572638);
        Assert(Write(original).Contains("正在生成") && Native.Writes==0,"active predicate blocks writing");
        Reset();Native.C.Put(Engine.Page.Context+188,Native.C.ModuleBase+0x3987e4,0,offset+34);
        Assert(Write(original).Contains("正在生成") && Native.Writes==0,"callee returning into predicate blocks writing");
        TargetFixture(1);Assert(Current() && (int)Get("targetStage")==1 && Native.Writes==0,"story progress is read without a write");
        TargetFixture(2);Assert(!Current() && (string)Get("endReason")=="completed","last story finishes the target");
        TargetFixture(1);Native.C.Put(0x71000+(uint)(10/4)*32+(uint)(10%4)*4,0x230000);
        Assert(!Current() && (string)Get("endReason")=="changed","replaced game page clears the target");
        return 0;
    }
}
