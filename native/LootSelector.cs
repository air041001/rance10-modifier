using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

// Own the random pool and/or eligible-victory roll. Restore both atomically.
internal static class LootSelector {
    static Connection connection;
    static GlobalsPage globals;
    static uint codeBase;
    sealed class Entry {
        internal LootProfile Layout;
        internal byte[] Original, Patch;
    }
    static readonly List<Entry> entries=new List<Entry>();
    static bool allCards, unique, guaranteed, restoring, armed;
    // These rules contain script IDs, not handles into a particular save.
    // Keep the user's successful selection while the VM reloads its objects.
    static Dictionary<string,object> requested;
    static string notice="";
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
        connection=null; globals=null; entries.Clear(); restoring=allCards=unique=guaranteed=armed=false;
    }
    static bool Guarded(uint value) {
        return entries.Any(e=>(value>=e.Layout.GuardStart && value<e.Layout.GuardEnd) ||
            (value>=codeBase+e.Layout.GuardStart && value<codeBase+e.Layout.GuardEnd));
    }
    static void Write(GlobalsPage page,byte[][] expected,byte[][] replacement) {
        using(var paused=new PausedGame(connection.Process)) {
            if(!Engine.SameGlobals(page,Engine.CheckGlobals(connection,page.Owner)) || CodeBase(connection,page)!=codeBase)
                throw new InvalidOperationException("游戏正在换档，请稍后重试。");
            byte[] ip=connection.Read(page.Context+136,4),stack=connection.Read(page.Context+188,8);
            if(ip==null || stack==null || BitConverter.ToUInt32(stack,0)!=connection.Types["Stack"])
                throw new InvalidOperationException("无法核对宝箱抽取的执行位置。");
            uint current=BitConverter.ToUInt32(ip,0);
            int top=BitConverter.ToInt32(stack,4);
            if(top< -1 || top>255)throw new InvalidOperationException("游戏调用栈需要适配。");
            if(Guarded(current))
                throw new InvalidOperationException("正在结算战斗或生成宝箱，返回稳定画面后再切换规则。");
            byte[] returns=connection.Read(page.Context+196,(top+1)*4);
            if(returns==null)throw new InvalidOperationException("暂时无法核对游戏调用栈。");
            for(int i=0;i<=top;i++) {
                uint caller=BitConverter.ToUInt32(returns,i*4);
                // Check both script offsets and pointers into the VM code.
                if(Guarded(caller))
                    throw new InvalidOperationException("正在结算战斗或生成宝箱，返回稳定画面后再切换规则。");
            }
            // Verify every span before writing any span, while the game is paused.
            for(int i=0;i<entries.Count;i++) {
                var p=entries[i].Layout;
                byte[] before=connection.Read(codeBase+p.Offset,p.Length);
                if(before==null || !before.SequenceEqual(expected[i]))
                    throw new InvalidOperationException("宝箱规则已被其他修改改变，没有覆盖。");
            }
            for(int i=0;i<entries.Count;i++) {
                var p=entries[i].Layout;uint address=codeBase+p.Offset;UIntPtr written;
                bool success=Native.WriteProcessMemory(connection.Handle,new IntPtr((long)address),replacement[i],(UIntPtr)(uint)p.Length,out written);
                byte[] after=connection.Read(address,p.Length);
                if(success && written.ToUInt64()==(ulong)p.Length && after!=null && after.SequenceEqual(replacement[i]))continue;
                // A partial write to either rule restores both pre-write spans.
                for(int j=0;j<entries.Count;j++) {
                    var r=entries[j].Layout;
                    Native.WriteProcessMemory(connection.Handle,new IntPtr((long)(codeBase+r.Offset)),expected[j],(UIntPtr)(uint)r.Length,out written);
                }
                bool restored=entries.Select((e,j)=> {
                    byte[] now=connection.Read(codeBase+e.Layout.Offset,e.Layout.Length);
                    return now!=null && now.SequenceEqual(expected[j]);
                }).All(v=>v);
                if(!restored)throw new InvalidOperationException("宝箱规则恢复失败，请重新启动游戏。");
                throw new InvalidOperationException("本次切换未完成，已恢复切换前的宝箱规则。");
            }
        }
    }
    static void Restore() {
        if(connection==null)return;
        restoring=true;armed=false;
        if(connection.Process.HasExited){Forget();return;}
        GlobalsPage page=globals;
        if(!Current()) {
            page=Engine.Locate(connection,false).Globals;
            if(CodeBase(connection,page)!=codeBase){Forget();return;}
        }
        byte[][] current=entries.Select(e=>connection.Read(codeBase+e.Layout.Offset,e.Layout.Length)).ToArray();
        if(entries.Select((e,i)=>current[i]!=null && current[i].SequenceEqual(e.Original)).All(v=>v)){Forget();return;}
        if(entries.Select((e,i)=>current[i]==null || !current[i].Select((v,j)=>v==e.Patch[j] || v==e.Original[j]).All(v=>v)).Any(v=>v))
            throw new InvalidOperationException("宝箱代码被其他程序改变，没有覆盖。");
        Write(page,current,entries.Select(e=>e.Original).ToArray()); Forget();
    }
    static bool Flag(Dictionary<string,object> command,string name) {
        object value;return command.TryGetValue(name,out value) && Convert.ToBoolean(value);
    }
    static LootProfile Layout(RuntimeProfile profile,string name) {
        var p=name=="patch"?profile.Loot:profile.Drop;
        if(p==null)throw new InvalidOperationException((name=="patch"?profile.LootError:profile.DropError)??"这项宝箱规则需要适配。");
        return p;
    }
    static void Arm(Dictionary<string,object> command) {
        Restore();
        connection=new Connection(true,true);
        try {
            globals=Engine.Locate(connection,false).Globals;
            if(connection.Process.Id!=Convert.ToInt32(command["pid"]) || connection.Session!=Convert.ToInt64(command["session"]) ||
                globals.Owner!=Convert.ToUInt32(command["global_owner"]))
                throw new InvalidOperationException("游戏进度刚刚变化，请重新开启宝箱规则。");
            codeBase=CodeBase(connection,globals);
            allCards=Flag(command,"all_cards");unique=Flag(command,"unique");guaranteed=Flag(command,"guaranteed");
            if(!allCards && !unique && !guaranteed)throw new InvalidOperationException("宝箱规则参数无效。");
            foreach(string name in new[]{"patch","drop_patch"}) {
                if(name=="patch"?!(allCards || unique):!guaranteed)continue;
                var p=Layout(connection.Profile,name);
                byte[] original=connection.Read(codeBase+p.Offset,p.Length);
                if(original==null || RuntimeProfile.Hash(original)!=p.SpanHash)
                    throw new InvalidOperationException("宝箱规则已被另一修改改变，未覆盖。");
                byte[] patch=Convert.FromBase64String((string)command[name]);
                if(patch.Length!=p.Length)throw new InvalidOperationException("宝箱规则参数无效。");
                entries.Add(new Entry { Layout=p,Original=original,Patch=patch });
            }
            Write(globals,entries.Select(e=>e.Original).ToArray(),entries.Select(e=>e.Patch).ToArray());
            armed=true;
        } catch {
            bool original=entries.All(e=> {
                byte[] now=connection.Read(codeBase+e.Layout.Offset,e.Layout.Length);
                return now!=null && now.SequenceEqual(e.Original);
            });
            if(original)Forget();else restoring=true;
            throw;
        }
    }
    static void Enable(Dictionary<string,object> command) {
        Arm(command);
        requested=new Dictionary<string,object>(command);notice="";
    }
    static void Cancel() {
        // Clear intent first so a deferred restore can never re-enable it.
        requested=null;notice="";Restore();
    }
    static bool Maintain() {
        if(requested==null)return false;
        if(connection!=null && connection.Process.HasExited)Forget();
        if(connection!=null) {
            GlobalsPage page=Current()?globals:Engine.Locate(connection,false).Globals;
            if(CodeBase(connection,page)==codeBase) {
                byte[][] now=entries.Select(e=>connection.Read(codeBase+e.Layout.Offset,e.Layout.Length)).ToArray();
                if(entries.Select((e,i)=>now[i]==null).Any(v=>v))
                    throw new InvalidOperationException("暂时无法读取宝箱规则。");
                if(entries.Select((e,i)=>!now[i].SequenceEqual(e.Patch) && !now[i].SequenceEqual(e.Original)).Any(v=>v))
                    throw new InvalidOperationException("宝箱代码被其他程序改变，没有覆盖。");
                bool changed=!armed || !Engine.SameGlobals(globals,page) || restoring;
                if(entries.Select((e,i)=>!now[i].SequenceEqual(e.Patch)).Any(v=>v)) {
                    // Reload/retry may reset either span. Reapply to the newly
                    // validated page, with the same guards and atomic rollback.
                    Write(page,now,entries.Select(e=>e.Patch).ToArray());changed=true;
                }
                globals=page;restoring=false;armed=true;return changed;
            }
            // This VM no longer executes the old code allocation. Do not write
            // to its stale address; locate and verify the replacement VM below.
            Forget();
        }
        Dictionary<string,object> command=new Dictionary<string,object>(requested);
        using(var c=new Connection(false,true)) {
            var page=Engine.Locate(c,false).Globals;
            command["pid"]=c.Process.Id;command["session"]=c.Session;command["global_owner"]=page.Owner;
        }
        Arm(command);return true;
    }
    static void Tick() {
        try {
            if(requested!=null) {
                if(!Maintain())return;
                notice="宝箱选项已自动应用到当前进度；读档和重新战斗后会继续保持。";
                Emit(State(true,false,notice));
            } else if(restoring && connection!=null) {
                Restore();notice="已恢复游戏原来的宝箱规则。";
                Emit(State(true,false,notice));
            }
        } catch(Exception ex) {
            armed=false;
            string message=(requested!=null?"宝箱选项已保留，等待自动应用：":"正在恢复宝箱规则：")+ex.Message;
            if(message!=notice){notice=message;Emit(State(false,false,message));}
        }
    }
    static Dictionary<string,object> State(bool success,bool reply,string message) {
        return new Dictionary<string,object> { {"success",success},{"reply",reply},{"armed",armed && !restoring},
            {"enabled",requested!=null},{"waiting",requested!=null && (!armed || restoring)},
            {"all_cards",requested!=null?Flag(requested,"all_cards"):allCards},
            {"unique",requested!=null?Flag(requested,"unique"):unique},
            {"guaranteed",requested!=null?Flag(requested,"guaranteed"):guaranteed},
            {"restoring",restoring},{"message",message} };
    }
    static Dictionary<string,object> Probe(Dictionary<string,object> command) {
        using(var c=new Connection(false,true)) {
            var page=Engine.Locate(c,false).Globals;uint address=CodeBase(c,page);
            var snapshot=new Dictionary<string,object> { {"pid",c.Process.Id},{"session",c.Session},
                {"global_owner",page.Owner},{"profile",new JavaScriptSerializer().DeserializeObject(File.ReadAllText(RuntimeSettings.ProfilePath,Encoding.UTF8))} };
            foreach(string name in new[]{"patch","drop_patch"}) {
                if(name=="patch"?!(Flag(command,"all_cards") || Flag(command,"unique")):!Flag(command,"guaranteed"))continue;
                var p=Layout(c.Profile,name);byte[] body=c.Read(address+p.Offset,p.Length);
                var own=connection!=null && c.Process.Id==connection.Process.Id && address==codeBase?
                    entries.FirstOrDefault(e=>e.Layout.Offset==p.Offset && e.Layout.Length==p.Length):null;
                if(body==null || (RuntimeProfile.Hash(body)!=p.SpanHash && (own==null || !body.SequenceEqual(own.Patch))))
                    throw new InvalidOperationException("宝箱规则与当前游戏不同，或已被其他修改改变。");
                snapshot[name=="patch"?"source_code":"drop_source_code"]=Convert.ToBase64String(
                    RuntimeProfile.Hash(body)==p.SpanHash?body:own.Original);
            }
            var result=State(true,true,"已读取当前宝箱规则。");result["snapshot"]=snapshot;return result;
        }
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
                        if(action=="arm") {Enable(command);result=State(true,true,"宝箱规则已开启，读档或重新战斗后会自动保持；手动取消或关闭修改器时结束。");}
                        else if(action=="cancel") {Cancel();result=State(true,true,"已恢复游戏原来的宝箱规则。");}
                        else if(action=="probe") result=Probe(command);
                        else throw new InvalidOperationException("未知宝箱操作。");
                    } catch(Exception ex){result=State(false,true,ex.Message);}
                    object request; if(command.TryGetValue("request_id",out request))result["request_id"]=request;
                    Emit(result);
                }
                if((connection!=null || requested!=null) && DateTime.UtcNow>=retry) {
                    Tick();retry=DateTime.UtcNow.AddMilliseconds(500);
                }
                Thread.Sleep(100);
            }
            return 0;
        } catch(Exception ex){Emit(State(false,true,ex.Message));return 1;}
        finally {
            requested=null;
            while(connection!=null){try{Restore();}catch{Thread.Sleep(1000);}}
            if(parent!=null)parent.Dispose();
        }
    }
}
