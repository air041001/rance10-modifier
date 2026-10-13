using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// Own only the random-box routine. Fixed IDs and the card-get scene are intact.
internal static class LootSelector {
    static Connection connection;
    static GlobalsPage globals;
    static uint codeBase;
    static byte[] original, patch;
    static bool allCards, unique, restoring;
    static volatile bool inputClosed;
    static long revision;

    static uint CodeBase(Connection c, GlobalsPage page) {
        byte[] bounds=c.Read(page.Context+140,8);
        if(bounds==null)throw new InvalidOperationException("游戏正在切换画面，请稍后重试。");
        uint start=BitConverter.ToUInt32(bounds,0),end=BitConverter.ToUInt32(bounds,4);
        if(start<0x10000 || end-start!=c.Profile.CodeLength)
            throw new InvalidOperationException("宝箱运行脚本需要重新读取。");
        return start;
    }
    static bool Current() {
        return connection!=null && !connection.Process.HasExited &&
            Engine.SameGlobals(globals,Engine.CheckGlobals(connection,globals.Owner)) &&
            CodeBase(connection,globals)==codeBase;
    }
    static void Forget() {
        if(connection!=null)connection.Dispose();
        connection=null; globals=null; original=patch=null; restoring=allCards=unique=false;
    }
    static void Write(GlobalsPage page,byte[] expected,byte[] replacement) {
        var p=connection.Profile.Loot;
        using(var paused=new PausedGame(connection.Process)) {
            if(!Engine.SameGlobals(page,Engine.CheckGlobals(connection,page.Owner)) || CodeBase(connection,page)!=codeBase)
                throw new InvalidOperationException("游戏正在换档，请稍后重试。");
            byte[] ip=connection.Read(page.Context+136,4),stack=connection.Read(page.Context+188,8);
            if(ip==null || stack==null || BitConverter.ToUInt32(stack,0)!=connection.Types["Stack"])
                throw new InvalidOperationException("无法核对宝箱抽取的执行位置。");
            uint current=BitConverter.ToUInt32(ip,0);
            int top=BitConverter.ToInt32(stack,4);
            if(top< -1 || top>255)throw new InvalidOperationException("游戏调用栈需要适配。");
            if(current>=codeBase+p.GuardStart && current<codeBase+p.GuardEnd)
                throw new InvalidOperationException("正在生成宝箱候选，返回稳定画面后再切换规则。");
            byte[] returns=connection.Read(page.Context+196,(top+1)*4);
            if(returns==null)throw new InvalidOperationException("暂时无法核对游戏调用栈。");
            for(int i=0;i<=top;i++) {
                uint caller=BitConverter.ToUInt32(returns,i*4);
                // Check both script offsets and pointers into the VM code.
                if((caller>=p.GuardStart && caller<p.GuardEnd) ||
                   (caller>=codeBase+p.GuardStart && caller<codeBase+p.GuardEnd))
                    throw new InvalidOperationException("正在生成宝箱候选，返回稳定画面后再切换规则。");
            }
            uint address=codeBase+p.Offset;
            byte[] before=connection.Read(address,p.Length);
            if(before==null || !before.SequenceEqual(expected))
                throw new InvalidOperationException("宝箱规则已被其他修改改变，没有覆盖。");
            UIntPtr written;
            bool success=Native.WriteProcessMemory(connection.Handle,new IntPtr((long)address),replacement,(UIntPtr)(uint)p.Length,out written);
            byte[] after=connection.Read(address,p.Length);
            if(!success || written.ToUInt64()!=(ulong)p.Length || after==null || !after.SequenceEqual(replacement)) {
                Native.WriteProcessMemory(connection.Handle,new IntPtr((long)address),before,(UIntPtr)(uint)p.Length,out written);
                after=connection.Read(address,p.Length);
                if(after==null || !after.SequenceEqual(before))throw new InvalidOperationException("宝箱规则恢复失败，请重新启动游戏。");
                throw new InvalidOperationException("本次未开启，原宝箱规则已恢复。");
            }
        }
    }
    static void Restore() {
        if(connection==null)return;
        restoring=true;
        if(connection.Process.HasExited){Forget();return;}
        GlobalsPage page=globals;
        if(!Current()) {
            page=Engine.Locate(connection,false).Globals;
            if(CodeBase(connection,page)!=codeBase){Forget();return;}
        }
        var p=connection.Profile.Loot;
        byte[] now=connection.Read(codeBase+p.Offset,p.Length);
        if(now!=null && now.SequenceEqual(original)){Forget();return;}
        if(now==null || !now.Select((value,i)=>value==patch[i] || value==original[i]).All(v=>v))
            throw new InvalidOperationException("宝箱代码被其他程序改变，没有覆盖。");
        Write(page,now,original); Forget();
    }
    static void Arm(Dictionary<string,object> command) {
        Restore();
        connection=new Connection(true,true);
        try {
            var p=connection.Profile.Loot;
            if(p==null)throw new InvalidOperationException(connection.Profile.LootError??"随机宝箱规则需要适配。");
            globals=Engine.Locate(connection,false).Globals;
            if(connection.Process.Id!=Convert.ToInt32(command["pid"]) || connection.Session!=Convert.ToInt64(command["session"]) ||
                globals.Owner!=Convert.ToUInt32(command["global_owner"]))
                throw new InvalidOperationException("游戏进度刚刚变化，请重新开启宝箱规则。");
            codeBase=CodeBase(connection,globals);
            original=connection.Read(codeBase+p.Offset,p.Length);
            if(original==null || RuntimeProfile.Hash(original)!=p.SpanHash)
                throw new InvalidOperationException("随机宝箱已被另一修改改变，未覆盖。");
            patch=Convert.FromBase64String((string)command["patch"]);
            allCards=Convert.ToBoolean(command["all_cards"]); unique=Convert.ToBoolean(command["unique"]);
            if(patch.Length!=p.Length || (!allCards && !unique))throw new InvalidOperationException("宝箱规则参数无效。");
            Write(globals,original,patch);
        } catch {
            byte[] now=original==null?null:connection.Read(codeBase+connection.Profile.Loot.Offset,original.Length);
            if(original==null || patch==null || (now!=null && now.SequenceEqual(original)))Forget();
            else restoring=true;
            throw;
        }
    }
    static Dictionary<string,object> State(bool success,bool reply,string message) {
        return new Dictionary<string,object> { {"success",success},{"reply",reply},{"armed",connection!=null},
            {"all_cards",allCards},{"unique",unique},{"restoring",restoring},{"message",message} };
    }
    static void Emit(Dictionary<string,object> state) {
        state["revision"]=++revision;
        Console.WriteLine(new JavaScriptSerializer().Serialize(state)); Console.Out.Flush();
    }
    internal static int Watch(string[] args) {
        Console.InputEncoding=Console.OutputEncoding=new UTF8Encoding(false);
        Process parent=null;
        try {
            parent=Process.GetProcessById(Int32.Parse(args[Array.IndexOf(args,"--parent-pid")+1]));
            RuntimeSettings.GameDirectory=args[Array.IndexOf(args,"--game-dir")+1];
            RuntimeSettings.ProfilePath=args[Array.IndexOf(args,"--runtime-profile")+1];
            var commands=new Queue<Dictionary<string,object>>();
            var input=new Thread(delegate() {
                try {
                    string line;
                    while((line=Console.ReadLine())!=null) {
                        var command=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(line);
                        lock(commands){commands.Enqueue(command);}
                    }
                } catch {} finally{inputClosed=true;}
            });
            input.IsBackground=true;input.Start();
            DateTime retry=DateTime.MinValue;
            while(!inputClosed && !parent.HasExited) {
                Dictionary<string,object> command=null;
                lock(commands){if(commands.Count>0)command=commands.Dequeue();}
                if(command!=null) {
                    Dictionary<string,object> result;
                    try {
                        string action=(string)command["action"];
                        if(action=="arm") {Arm(command);result=State(true,true,"宝箱规则已开启，下次生成随机候选时生效。");}
                        else if(action=="cancel") {Restore();result=State(true,true,"已恢复游戏原来的宝箱规则。");}
                        else if(action=="probe") {
                            using(var c=new Connection(false,true)) {
                                var p=c.Profile.Loot;
                                if(p==null)throw new InvalidOperationException(c.Profile.LootError??"随机宝箱规则需要适配。");
                                var page=Engine.Locate(c,false).Globals;
                                byte[] body=c.Read(CodeBase(c,page)+p.Offset,p.Length);
                                if(body==null || (RuntimeProfile.Hash(body)!=p.SpanHash &&
                                    (connection==null || c.Process.Id!=connection.Process.Id || !body.SequenceEqual(patch))))
                                    throw new InvalidOperationException("宝箱规则与当前游戏不同，或已被其他修改改变。");
                                result=State(true,true,"已读取当前随机宝箱规则。");
                                result["snapshot"]=new Dictionary<string,object> { {"pid",c.Process.Id},{"session",c.Session},
                                    {"global_owner",page.Owner},{"source_code",Convert.ToBase64String(RuntimeProfile.Hash(body)==p.SpanHash?body:original)},
                                    {"profile",new JavaScriptSerializer().DeserializeObject(File.ReadAllText(RuntimeSettings.ProfilePath,Encoding.UTF8))} };
                            }
                        } else throw new InvalidOperationException("未知宝箱操作。");
                    } catch(Exception ex){result=State(false,true,ex.Message);}
                    object request; if(command.TryGetValue("request_id",out request))result["request_id"]=request;
                    Emit(result);
                }
                if(connection!=null && DateTime.UtcNow>=retry) {
                    try {
                        if(restoring || !Current()) {Restore();Emit(State(true,false,"读档或进度切换，宝箱规则已取消；需要时重新开启。"));}
                    } catch(Exception ex) {restoring=true;Emit(State(false,false,"正在恢复宝箱规则："+ex.Message));retry=DateTime.UtcNow.AddSeconds(3);}
                }
                Thread.Sleep(100);
            }
            return 0;
        } catch(Exception ex){Emit(State(false,true,ex.Message));return 1;}
        finally {
            while(connection!=null){try{Restore();}catch{Thread.Sleep(1000);}}
            if(parent!=null)parent.Dispose();
        }
    }
}
