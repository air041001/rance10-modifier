using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

// Only the image resolver is exercised; no process memory is opened.
internal sealed class TestModule { internal int ModuleMemorySize; }
internal sealed class TestProcess { internal TestModule MainModule=new TestModule(); }
internal sealed class Connection {
    internal TestProcess Process=new TestProcess(); internal uint ModuleBase; internal IntPtr Handle;
    internal byte[] Read(uint address,int size){throw new NotImplementedException();}
}
internal static class Native {
    [StructLayout(LayoutKind.Sequential)]
    internal struct MemoryInfo { internal IntPtr Base; internal UIntPtr Size; internal uint State,Protect; }
    internal static UIntPtr VirtualQueryEx(IntPtr h,IntPtr a,out MemoryInfo info,UIntPtr size){info=new MemoryInfo();return UIntPtr.Zero;}
}
internal static class Harness {
    static readonly string[] Names={".?AVCFastMemory@memory@@",".?AVCGlobalPage@sys43vm@@",".?AVCStructPage@sys43vm@@"};
    static void Put(byte[] image,int offset,uint value){Array.Copy(BitConverter.GetBytes(value),0,image,offset,4);}
    static byte[] Image(uint baseAddress,int displacement){
        byte[] image=new byte[4096];
        for(int i=0;i<Names.Length;i++){
            int descriptor=128+i*256+displacement;
            Array.Copy(Encoding.ASCII.GetBytes(Names[i]+'\0'),0,image,descriptor+8,Names[i].Length+1);
            for(int kind=0;kind<(i==0?1:2);kind++){
                int locator=descriptor+80+kind*32,table=descriptor+160+kind*16;
                Put(image,locator+4,(uint)(kind*32));Put(image,locator+12,baseAddress+(uint)descriptor);
                Put(image,table,baseAddress+(uint)locator);Put(image,table+4,baseAddress+3500);
            }
        }
        return image;
    }
    static void Assert(bool value,string message){if(!value)throw new Exception(message);Console.WriteLine("PASS "+message);}
    static int Main(){
        var first=RuntimeTypes.Decode(Image(0x400000,0),0x400000);
        var other=RuntimeTypes.Decode(Image(0x700000,16),0x700000);
        Assert(first.Count==5 && other.Count==5,"numeric features need only their own types");
        Assert(other["Memory"]-first["Memory"]==0x300010,"module and RTTI positions are derived");
        bool rejected=false;
        try{RuntimeTypes.Decode(Image(0x400000,0),0x400000,true);}catch(InvalidOperationException){rejected=true;}
        Assert(rejected,"missing food types affect only food selection");
        byte[] ambiguous=Image(0x400000,0);Put(ambiguous,2200,0x400000+208);Put(ambiguous,2204,0x400000+3500);
        rejected=false;try{RuntimeTypes.Decode(ambiguous,0x400000);}catch(InvalidOperationException){rejected=true;}
        Assert(rejected,"ambiguous objects are not written");
        Assert(RuntimeProfile.DisplayChapter(0)==1 && RuntimeProfile.DisplayChapter(1)==2,
            "zero based runtime chapters use the correct display labels");
        Assert(RuntimeProfile.DisplayChapter(-1)==null && RuntimeProfile.DisplayChapter(2)==null,
            "unknown chapters are not labelled as the first or second part");
        return 0;
    }
}
