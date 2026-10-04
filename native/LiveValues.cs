using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class RuntimeSettings {
    internal static string GameDirectory;
    internal static string ProfilePath;
}

internal static class Native {
    [StructLayout(LayoutKind.Sequential)]
    internal struct MemoryInfo {
        public IntPtr Base, AllocationBase; public uint AllocationProtect;
        public ushort Partition; public UIntPtr Size;
        public uint State, Protect, Type;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern UIntPtr VirtualQueryEx(IntPtr handle, IntPtr address,
        out MemoryInfo info, UIntPtr size);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern bool ReadProcessMemory(IntPtr handle, IntPtr address,
        [Out] byte[] buffer, UIntPtr length, out UIntPtr read);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern bool WriteProcessMemory(IntPtr handle, IntPtr address,
        byte[] buffer, UIntPtr length, out UIntPtr written);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern IntPtr OpenThread(uint access, bool inherit, int id);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint Wow64SuspendThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern bool Wow64GetThreadContext(IntPtr thread, [In, Out] byte[] context);
}

internal sealed class Connection : IDisposable {
    public Process Process; public IntPtr Handle; public uint Marker, ModuleBase;
    public long Session;
    public RuntimeProfile Profile;
    public Dictionary<string,uint> Types;
    public Connection(bool write, bool includeFood=false) {
        if (String.IsNullOrWhiteSpace(RuntimeSettings.GameDirectory))
            throw new InvalidOperationException("请先在设置中选择游戏目录。");
        string game = Path.GetFullPath(Path.Combine(RuntimeSettings.GameDirectory, "Rance10.exe"));
        List<Process> processes = new List<Process>();
        foreach (Process p in Process.GetProcessesByName("Rance10")) {
            try {
                if (String.Equals(Path.GetFullPath(p.MainModule.FileName), game,
                    StringComparison.OrdinalIgnoreCase)) processes.Add(p); else p.Dispose();
            } catch { p.Dispose(); }
        }
        if (processes.Count != 1) {
            foreach (Process p in processes) p.Dispose();
            throw new InvalidOperationException("请先启动同目录的兰斯10，并且只运行一个实例。");
        }
        Process = processes[0];
        try {
            Profile = RuntimeProfile.Load(RuntimeSettings.ProfilePath);
            if (RuntimeProfile.FileHash(game) != Profile.ExeHash)
                throw new InvalidOperationException("游戏程序刚刚变化，请重新读取游戏。");
            Session = Process.StartTime.ToUniversalTime().Ticks;
            ModuleBase = checked((uint)Process.MainModule.BaseAddress.ToInt64());
            string ainPath = Path.Combine(Path.GetDirectoryName(game), "Rance10.ain");
            if (RuntimeProfile.FileHash(ainPath) != Profile.AinHash)
                throw new InvalidOperationException("游戏脚本刚刚变化，请重新读取游戏。");
            Handle = Native.OpenProcess(write ? 0x438u : 0x410u, false, Process.Id);
            if (Handle == IntPtr.Zero) throw new InvalidOperationException("无法访问游戏进程。请让游戏和工具以相同权限运行。");
            Types = RuntimeTypes.Resolve(this, includeFood);
            Marker = Types["Memory"];
        } catch { Dispose(); throw; }
    }
    public byte[] Read(uint address, int size) {
        byte[] buffer = new byte[size]; UIntPtr read;
        Native.ReadProcessMemory(Handle, new IntPtr((long)address), buffer, (UIntPtr)(uint)size, out read);
        if (read.ToUInt64() != (ulong)size) return null;
        return buffer;
    }
    internal void VerifyScript(GlobalsPage page) {
        byte[] bounds = Read(page.Context+140,8);
        if(bounds==null)throw new InvalidOperationException("游戏正在切换进度，请稍后重试。");
        uint start=BitConverter.ToUInt32(bounds,0),end=BitConverter.ToUInt32(bounds,4);
        if(start<0x10000 || end<=start || end-start!=Profile.CodeLength)
            throw new InvalidOperationException("运行中的脚本和所选游戏目录不同，请重新启动该目录的游戏。");
        byte[] code=Read(start,Profile.CodeLength);
        if(code==null)throw new InvalidOperationException("暂时无法读取运行脚本，请稍后重试。");
        if(Profile.Food!=null)Array.Clear(code,(int)Profile.Food.Offset,Profile.Food.Length);
        if(RuntimeProfile.Hash(code)!=Profile.CodeHash)
            throw new InvalidOperationException("运行中的脚本内容与所选目录不同，请重新启动该目录的游戏。");
    }
    public void Dispose() {
        if (Handle != IntPtr.Zero) { Native.CloseHandle(Handle); Handle = IntPtr.Zero; }
        if (Process != null) { Process.Dispose(); Process = null; }
    }
}

internal sealed class GlobalsPage {
    public uint Owner, Data, Context;
    public int PlayerHandle, BonusHandle;
}

internal sealed class LiveObject {
    public uint Owner, Data;
    public int[] Values;
    public GlobalsPage Globals; public bool IsBonus;
}

internal static class Engine {

    internal static GlobalsPage CheckGlobals(Connection c, uint owner) {
        int globalBytes=c.Profile.GlobalCount*4;
        if (owner < 0x1000c || owner > 0xffffffdf) return null;
        byte[] meta = c.Read(owner - 12, 44);
        if (meta == null || BitConverter.ToUInt32(meta, 0) != c.Types["Global"] ||
            BitConverter.ToUInt32(meta, 12) != c.Marker ||
            BitConverter.ToUInt32(meta, 20) != globalBytes ||
            BitConverter.ToUInt32(meta, 24) != globalBytes ||
            BitConverter.ToUInt32(meta, 28) == 0 ||
            BitConverter.ToUInt32(meta, 32) != c.Types["GlobalKind"])
            return null;
        uint data = BitConverter.ToUInt32(meta, 16);
        uint context = BitConverter.ToUInt32(meta, 36);
        if ((data & 3) != 0 || data < 0x10000 || context < 0x10000) return null;
        byte[] value = c.Read(data + (uint)c.Profile.PlayerGlobal * 4, 4);
        if (value == null) return null;
        int handle = BitConverter.ToInt32(value, 0);
        if (handle <= 0 || handle >= 10000000) return null;
        byte[] bonus = c.Read(data + (uint)c.Profile.BonusGlobal * 4, 4);
        if (bonus == null) return null;
        int bonusHandle = BitConverter.ToInt32(bonus, 0);
        if (bonusHandle <= 0 || bonusHandle >= 10000000) return null;
        return new GlobalsPage { Owner = owner, Data = data, Context = context,
            PlayerHandle = handle, BonusHandle = bonusHandle };
    }

    static bool ValidValues(int[] v) {
        return v.Length == 12 && v[0] >= 0 && v[0] <= 3 && v[1] >= 0 &&
            v[2] >= 0 && v[3] >= 0 && v[4] >= 0 && v[4] <= 100 &&
            (v[5] == 0 || v[5] == 1) && (v[6] == Int32.MaxValue || (v[6] >= 0 && v[6] < 10000000)) &&
            v[7] >= 0 && v[8] >= 0 && v[8] <= 1000 &&
            v[9] >= 0 && v[9] <= 100000 && v[10] >= 0 && v[10] <= 1000 &&
            (v[11] == 0 || v[11] == 1);
    }

    static LiveObject CheckObject(Connection c, uint owner, GlobalsPage globals, bool bonus) {
        string name=bonus?"PartyBonusSwitcher":"PlayerCommonParam";
        int bytes=c.Profile.Counts[name]*4;
        int expectedHandle = bonus ? globals.BonusHandle : globals.PlayerHandle;
        if (owner < 0x1000c || owner > 0xffffffdf) return null;
        byte[] meta = c.Read(owner - 12, 44);
        if (meta == null || BitConverter.ToUInt32(meta, 0) != c.Types["Struct"] ||
            BitConverter.ToInt32(meta,4)!=4 ||
            BitConverter.ToUInt32(meta, 12) != c.Marker ||
            BitConverter.ToUInt32(meta, 20) != bytes || BitConverter.ToUInt32(meta, 24) != bytes ||
            BitConverter.ToUInt32(meta, 28) == 0 ||
            BitConverter.ToUInt32(meta, 32) != c.Types["StructKind"] ||
            BitConverter.ToUInt32(meta, 36) != globals.Context ||
            BitConverter.ToInt32(meta, 40) != expectedHandle)
            return null;
        uint data = BitConverter.ToUInt32(meta, 16);
        if ((data & 3) != 0 || data < 0x10000) return null;
        byte[] body = c.Read(data, bytes); if (body == null) return null;
        int[] values = new int[bytes / 4];
        for (int i = 0; i < values.Length; i++) values[i] = BitConverter.ToInt32(body, i * 4);
        values=c.Profile.Normalize(name,values);
        if (!bonus && !ValidValues(values)) return null;
        if (bonus && (values[0] < 0 || values[1] <= 0 || values[1] >= 10000000 ||
            values[2] < 0 || values[2] > 100000)) return null;
        return new LiveObject { Owner = owner, Data = data, Values = values, Globals = globals, IsBonus = bonus };
    }

    internal static bool SameGlobals(GlobalsPage a, GlobalsPage b) {
        return a != null && b != null && a.Owner == b.Owner && a.Data == b.Data &&
            a.Context == b.Context && a.PlayerHandle == b.PlayerHandle && a.BonusHandle == b.BonusHandle;
    }

    static LiveObject Confirm(Connection c, LiveObject current) {
        GlobalsPage globals = CheckGlobals(c, current.Globals.Owner);
        if (!SameGlobals(globals, current.Globals)) return null;
        LiveObject player = CheckObject(c, current.Owner, globals, current.IsBonus);
        if (player == null || player.Data != current.Data) return null;
        // The reference is checked again after reading the player object.
        if (!SameGlobals(CheckGlobals(c, globals.Owner), globals)) return null;
        return player;
    }

    internal static LiveObject Locate(Connection c, bool bonus) {
        int expectedBytes=c.Profile.Counts[bonus?"PartyBonusSwitcher":"PlayerCommonParam"]*4;
        int globalBytes=c.Profile.GlobalCount*4;
        // Scan anew on each manual action; no stale address survives a load or restart.
        var globalPages = new Dictionary<uint, GlobalsPage>();
        var playerOwners = new HashSet<uint>();
        ulong address = 0, total = 0;
        while (address < 0x100000000UL) {
            Native.MemoryInfo info;
            if (Native.VirtualQueryEx(c.Handle, new IntPtr((long)address), out info,
                (UIntPtr)(uint)Marshal.SizeOf(typeof(Native.MemoryInfo))).ToUInt64() == 0) break;
            ulong start = (ulong)info.Base.ToInt64(), size = info.Size.ToUInt64();
            if (size == 0 || start + size <= address) break;
            uint p = info.Protect & 255;
            if (info.State == 0x1000 && info.Type == 0x20000 &&
                (p == 4 || p == 8 || p == 64 || p == 128) && (info.Protect & 256) == 0) {
                for (ulong chunk = start; chunk < start + size && chunk < 0x100000000UL; chunk += 1048576) {
                    int count = (int)Math.Min(1048640UL, start + size - chunk);
                    byte[] buffer = new byte[count]; UIntPtr read;
                    Native.ReadProcessMemory(c.Handle, new IntPtr((long)chunk), buffer,
                        (UIntPtr)(uint)count, out read);
                    int available = (int)read.ToUInt64(); total += (uint)available;
                    for (int i = 0; i + 20 <= available; i += 4) {
                        if (BitConverter.ToUInt32(buffer, i) != c.Marker) continue;
                        int length = BitConverter.ToInt32(buffer, i + 8);
                        if ((length != expectedBytes && length != globalBytes) ||
                            BitConverter.ToInt32(buffer, i + 12) != length) continue;
                        uint owner = checked((uint)(chunk + (uint)i));
                        if (length == expectedBytes) playerOwners.Add(owner);
                        else {
                            GlobalsPage globals = CheckGlobals(c, owner);
                            if (globals != null) globalPages[globals.Owner] = globals;
                        }
                    }
                    if (total > 1536UL * 1024 * 1024)
                        throw new InvalidOperationException("扫描超过范围，本次未修改。请关闭再打开工具后重试。");
                }
            }
            address = start + size;
        }
        if (globalPages.Count != 1)
            throw new InvalidOperationException(globalPages.Count == 0 ?
                "游戏已启动，尚未读取到当前进度。请载入进度，等画面稳定后刷新状态。" :
                "游戏正在切换进度，本次未修改。请等画面稳定后刷新状态。");
        GlobalsPage currentGlobals = globalPages.Values.First();
        c.VerifyScript(currentGlobals);
        if (!SameGlobals(CheckGlobals(c, currentGlobals.Owner), currentGlobals))
            throw new InvalidOperationException("游戏正在切换进度，请稍后刷新状态。");
        var hits = new Dictionary<uint, LiveObject>();
        foreach (uint owner in playerOwners) {
            LiveObject value = CheckObject(c, owner, currentGlobals, bonus);
            if (value != null) hits[value.Data] = value;
        }
        if (hits.Count != 1)
            throw new InvalidOperationException(hits.Count == 0 ?
                "已连接游戏，暂时无法读取当前数值。请等画面稳定后刷新状态，无需保存。" :
                "当前进度存在多个数据对象，本次未修改。请稍后刷新状态。");
        LiveObject verified = Confirm(c, hits.Values.First());
        if (verified == null) throw new InvalidOperationException("游戏状态发生变化，请稍后刷新状态。");
        return verified;
    }

    public static Dictionary<string, object> Run(string action, int amount) {
        bool writing = action != "probe";
        using (Connection c = new Connection(writing)) {
            LiveObject food = Locate(c, false);
            LiveObject bonus = Locate(c, true);
            if (!SameGlobals(food.Globals, bonus.Globals))
                throw new InvalidOperationException("游戏正在切换进度，请稍后刷新。");
            food = Confirm(c, food); bonus = Confirm(c, bonus);
            if (food == null || bonus == null) throw new InvalidOperationException("游戏状态发生变化，请刷新。");
            int[] oldFood = (int[])food.Values.Clone(), oldBonus = (int[])bonus.Values.Clone();
            int writes = 0;
            if (writing) {
                bool targetBonus = action == "setpoints" || action == "addpoints" || action == "verify-write";
                LiveObject target = targetBonus ? bonus : food;
                int field = targetBonus || action == "fillfriend3" ? 2 : 0;
                int value = 3;
                if (action == "addpoints") {
                    if (amount < 1 || amount > 50) throw new InvalidOperationException("每次增加1到50点。");
                    value = checked(target.Values[2] + amount);
                } else if (action == "setpoints") value = amount;
                else if (action == "verify-write") value = target.Values[field];
                else if (action != "fill3" && action != "fillfriend3") throw new InvalidOperationException("未知操作。");
                // A modified game can already hold more than three friendship
                // points. Refill never reduces that independent resource.
                if (action == "fillfriend3") value = Math.Max(value, target.Values[field]);
                if (targetBonus && (value < target.Values[2] || value > 100))
                    throw new InvalidOperationException("总点数只能增加，最高100；当前总点数为" + target.Values[2] + "。");
                LiveObject fresh = Confirm(c, target);
                if (fresh == null || !fresh.Values.SequenceEqual(target.Values))
                    throw new InvalidOperationException("游戏数值正在变化，本次未修改。请刷新后重试。");
                UIntPtr written;
                int actualField=c.Profile.Fields[targetBonus?"PartyBonusSwitcher":"PlayerCommonParam"][field];
                if (!Native.WriteProcessMemory(c.Handle, new IntPtr((long)(fresh.Data + (uint)(actualField * 4))),
                    BitConverter.GetBytes(value), (UIntPtr)4, out written) || written.ToUInt64() != 4)
                    throw new InvalidOperationException("写入失败。");
                writes = 4;
                LiveObject after = Confirm(c, fresh);
                if (after == null || after.Values[field] != value)
                    throw new InvalidOperationException("写入后状态发生变化，请刷新并查看游戏。");
                for (int i = 0; i < fresh.Values.Length; i++)
                    if (i != field && after.Values[i] != fresh.Values[i])
                        throw new InvalidOperationException("游戏同时更新了其他数值，请刷新并查看游戏。");
                if (targetBonus) bonus = after; else food = after;
            }
            int? chapter = null;
            int? rawChapter = null;
            if (c.Profile.GameGlobal >= 0 && c.Profile.GameGlobal < c.Profile.GlobalCount &&
                c.Profile.Fields.ContainsKey("GameContext")) {
                try {
                    var vm = new VmPages(c, food.Globals);
                    int value = vm.Record(vm.Global(c.Profile.GameGlobal), "GameContext")[0];
                    if (SameGlobals(food.Globals, CheckGlobals(c, food.Globals.Owner))) {
                        rawChapter = value;
                        chapter = RuntimeProfile.DisplayChapter(value);
                    }
                } catch (InvalidOperationException) { /* Only the chapter label is optional. */ }
            }
            return new Dictionary<string, object> {
                {"success", true}, {"version", "1.0"}, {"action", action}, {"save_required", false},
                {"pid", c.Process.Id}, {"chapter", chapter}, {"chapter_raw", rawChapter}, {"session", c.Session},
                {"food", food.Values[0]}, {"friend_points", food.Values[2]}, {"total_points", bonus.Values[2]},
                {"food_before", oldFood}, {"food_after", food.Values},
                {"bonus_before", oldBonus}, {"bonus_after", bonus.Values},
                {"food_address", "0x" + food.Data.ToString("x")},
                {"bonus_address", "0x" + bonus.Data.ToString("x")},
                {"global_owner", "0x" + food.Globals.Owner.ToString("x")},
                {"player_owner", "0x" + food.Owner.ToString("x")},
                {"writes", writes}, {"time", DateTime.Now.ToString("s")}
            };
        }
    }
}

internal static class Program {
    [STAThread]
    static int Main(string[] args) {
        if (args.Contains("--food-watch")) return FoodSelector.Watch(args);
        int exit = 0; Dictionary<string, object> result;
        try {
            string action = "probe"; int amount = 0;
            if (args.Contains("--fill3")) action = "fill3";
            if (args.Contains("--fillfriend3")) action = "fillfriend3";
            foreach (string candidate in new string[] { "setpoints", "addpoints", "verify-write" }) {
                int pos = Array.IndexOf(args, "--" + candidate);
                if (pos < 0) continue;
                action = candidate;
                if (candidate != "verify-write") amount = Int32.Parse(args[pos + 1]);
            }
            if (args.Contains("--discover")) {
                List<Dictionary<string, object>> found = new List<Dictionary<string, object>>();
                foreach (Process p in Process.GetProcessesByName("Rance10")) {
                    try {
                        found.Add(new Dictionary<string, object> { {"pid", p.Id}, {"path", p.MainModule.FileName} });
                    } catch { } finally { p.Dispose(); }
                }
                result = new Dictionary<string, object> { {"success", true}, {"processes", found} };
            } else {
                int directory = Array.IndexOf(args, "--game-dir");
                if (directory < 0 || directory + 1 >= args.Length)
                    throw new InvalidOperationException("请先选择游戏目录。");
                RuntimeSettings.GameDirectory = Path.GetFullPath(args[directory + 1]);
                int profile=Array.IndexOf(args,"--runtime-profile");
                if(profile<0 || profile+1>=args.Length)throw new InvalidOperationException("缺少本机运行结构资料，请更新完整修改器。");
                RuntimeSettings.ProfilePath=args[profile+1];
                result = Engine.Run(action, amount);
            }
        } catch (Exception ex) {
            exit = 1; result = new Dictionary<string, object> { {"success", false}, {"error", ex.Message} };
        }
        int output = Array.IndexOf(args, "--report");
        if (output >= 0 && output + 1 < args.Length)
            File.WriteAllText(args[output + 1], new JavaScriptSerializer().Serialize(result), Encoding.UTF8);
        return exit;
    }
}
