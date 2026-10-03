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
    public Connection(bool write) {
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
            string hash;
            using (SHA256 sha = SHA256.Create())
            using (FileStream input = File.OpenRead(game))
                hash = BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
            if (hash != "39a508c05b13afc5427f0b722fce5c4edeced126587e037d585cf0e70d279297")
                throw new InvalidOperationException("游戏程序与已验证版本不同，已停止定位和修改。");
            Session = Process.StartTime.ToUniversalTime().Ticks;
            ModuleBase = checked((uint)Process.MainModule.BaseAddress.ToInt64());
            Marker = checked(ModuleBase + 0x3945d8);
            string ainPath = Path.Combine(Path.GetDirectoryName(game), "Rance10.ain");
            using (SHA256 sha = SHA256.Create())
            using (FileStream input = File.OpenRead(ainPath))
                hash = BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
            if (hash != "85a7b91d74186aa44b2b5319fc036988344fbe45c9cc7cf7cbe2c3a4c5115247")
                throw new InvalidOperationException("游戏数据与已验证版本不同，已停止定位和修改。");
            Handle = Native.OpenProcess(write ? 0x438u : 0x410u, false, Process.Id);
            if (Handle == IntPtr.Zero) throw new InvalidOperationException("无法访问游戏进程。请让游戏和工具以相同权限运行。");
        } catch { Dispose(); throw; }
    }
    public byte[] Read(uint address, int size) {
        byte[] buffer = new byte[size]; UIntPtr read;
        Native.ReadProcessMemory(Handle, new IntPtr((long)address), buffer, (UIntPtr)(uint)size, out read);
        if (read.ToUInt64() != (ulong)size) return null;
        return buffer;
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
    // This exact AIN has 361 globals. Index 256 is g_playerCommonParam,
    // of struct type 865. Its first member is int m_foodTicket.
    const int GlobalBytes = 361 * 4;
    const int PlayerGlobalIndex = 256;

    internal static GlobalsPage CheckGlobals(Connection c, uint owner) {
        if (owner < 0x1000c || owner > 0xffffffdf) return null;
        byte[] meta = c.Read(owner - 12, 44);
        if (meta == null || BitConverter.ToUInt32(meta, 0) != c.ModuleBase + 0x399024 ||
            BitConverter.ToUInt32(meta, 12) != c.Marker ||
            BitConverter.ToUInt32(meta, 20) != GlobalBytes ||
            BitConverter.ToUInt32(meta, 24) != GlobalBytes ||
            BitConverter.ToUInt32(meta, 28) == 0 ||
            BitConverter.ToUInt32(meta, 32) != c.ModuleBase + 0x39903c)
            return null;
        uint data = BitConverter.ToUInt32(meta, 16);
        uint context = BitConverter.ToUInt32(meta, 36);
        if ((data & 3) != 0 || data < 0x10000 || context < 0x10000) return null;
        byte[] value = c.Read(data + PlayerGlobalIndex * 4, 4);
        if (value == null) return null;
        int handle = BitConverter.ToInt32(value, 0);
        if (handle <= 0 || handle >= 10000000) return null;
        byte[] bonus = c.Read(data + 261 * 4, 4);
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
        int bytes = bonus ? 12 : 48;
        int expectedHandle = bonus ? globals.BonusHandle : globals.PlayerHandle;
        if (owner < 0x1000c || owner > 0xffffffdf) return null;
        byte[] meta = c.Read(owner - 12, 44);
        if (meta == null || BitConverter.ToUInt32(meta, 0) != c.ModuleBase + 0x399138 ||
            BitConverter.ToUInt32(meta, 12) != c.Marker ||
            BitConverter.ToUInt32(meta, 20) != bytes || BitConverter.ToUInt32(meta, 24) != bytes ||
            BitConverter.ToUInt32(meta, 28) == 0 ||
            BitConverter.ToUInt32(meta, 32) != c.ModuleBase + 0x399088 ||
            BitConverter.ToUInt32(meta, 36) != globals.Context ||
            BitConverter.ToInt32(meta, 40) != expectedHandle)
            return null;
        uint data = BitConverter.ToUInt32(meta, 16);
        if ((data & 3) != 0 || data < 0x10000) return null;
        byte[] body = c.Read(data, bytes); if (body == null) return null;
        int[] values = new int[bytes / 4];
        for (int i = 0; i < values.Length; i++) values[i] = BitConverter.ToInt32(body, i * 4);
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
        int expectedBytes = bonus ? 12 : 48;
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
                        if ((length != expectedBytes && length != GlobalBytes) ||
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
                bool targetBonus = action != "fill3";
                LiveObject target = targetBonus ? bonus : food;
                int field = targetBonus ? 2 : 0;
                int value = 3;
                if (action == "addpoints") {
                    if (amount < 1 || amount > 50) throw new InvalidOperationException("每次增加1到50点。");
                    value = checked(target.Values[2] + amount);
                } else if (action == "setpoints") value = amount;
                else if (action == "verify-write") value = target.Values[field];
                else if (action != "fill3") throw new InvalidOperationException("未知操作。");
                if (targetBonus && (value < target.Values[2] || value > 100))
                    throw new InvalidOperationException("总点数只能增加，最高100；当前总点数为" + target.Values[2] + "。");
                LiveObject fresh = Confirm(c, target);
                if (fresh == null || !fresh.Values.SequenceEqual(target.Values))
                    throw new InvalidOperationException("游戏数值正在变化，本次未修改。请刷新后重试。");
                UIntPtr written;
                if (!Native.WriteProcessMemory(c.Handle, new IntPtr((long)(fresh.Data + (uint)(field * 4))),
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
            return new Dictionary<string, object> {
                {"success", true}, {"version", "1.0"}, {"action", action}, {"save_required", false},
                {"pid", c.Process.Id}, {"food", food.Values[0]}, {"total_points", bonus.Values[2]},
                {"food_before", oldFood}, {"food_after", food.Values},
                {"bonus_before", oldBonus}, {"bonus_after", bonus.Values},
                {"food_address", "0x" + food.Data.ToString("x")},
                {"bonus_address", "0x" + bonus.Data.ToString("x")},
                {"global_owner", "0x" + food.Globals.Owner.ToString("x")},
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
