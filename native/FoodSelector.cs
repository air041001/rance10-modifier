// Replace only the battle predicate; the game owns candidate creation and playback.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

internal sealed class PausedGame : IDisposable {
    readonly List<IntPtr> opened = new List<IntPtr>();
    readonly List<IntPtr> suspended = new List<IntPtr>();
    readonly HashSet<int> threadIds = new HashSet<int>();
    internal PausedGame(Process process) {
        try {
            process.Refresh();
            // Obtain handles first; never wait for a game-owned lock while paused.
            foreach (ProcessThread thread in process.Threads) {
                IntPtr handle = Native.OpenThread(0xAu, false, thread.Id);
                if (handle == IntPtr.Zero) throw new InvalidOperationException("无法暂停游戏线程，本次未修改。");
                opened.Add(handle);
                threadIds.Add(thread.Id);
            }
            foreach (IntPtr handle in opened) {
                if (Native.Wow64SuspendThread(handle) == UInt32.MaxValue)
                    throw new InvalidOperationException("暂停游戏线程失败，本次未修改。");
                suspended.Add(handle);
                // Suspend is asynchronous. A context read acknowledges suspension.
                byte[] context = new byte[716];
                Buffer.BlockCopy(BitConverter.GetBytes(0x10001u), 0, context, 0, 4);
                if (!Native.Wow64GetThreadContext(handle, context))
                    throw new InvalidOperationException("无法确认游戏暂停，本次未修改。");
            }
            process.Refresh();
            if (process.Threads.Cast<ProcessThread>().Any(thread => !threadIds.Contains(thread.Id)))
                throw new InvalidOperationException("游戏线程刚刚变化，请稍后重试，本次未修改。");
        } catch { Dispose(); throw; }
    }
    public void Dispose() {
        for (int i = suspended.Count - 1; i >= 0; i--) Native.ResumeThread(suspended[i]);
        suspended.Clear();
        foreach (IntPtr handle in opened) Native.CloseHandle(handle);
        opened.Clear();
    }
}

// sys43vm stores four page pointers per heap-table block. Strings do not
// contain an object handle/context; resolve them through this same table.
internal sealed class VmPages {
    readonly Connection c;
    readonly GlobalsPage globals;
    internal VmPages(Connection connection, GlobalsPage page) { c = connection; globals = page; }
    byte[] Read(uint address, int size) {
        byte[] data = c.Read(address, size);
        if (data == null) throw new InvalidOperationException("游戏数据正在变化，请稍后刷新。");
        return data;
    }
    uint Word(uint address) { return BitConverter.ToUInt32(Read(address, 4), 0); }
    internal uint Pointer(int handle) {
        if (handle < 0 || handle >= 10000000) throw new InvalidOperationException("游戏对象标识超出适配范围。");
        byte[] heap = Read(globals.Context + 8, 8);
        uint table = BitConverter.ToUInt32(heap, 0), blocks = BitConverter.ToUInt32(heap, 4);
        if (table < 0x10000 || blocks == 0 || blocks > 2500000 || handle / 4 >= blocks)
            throw new InvalidOperationException("游戏对象表与适配版本不一致。");
        uint block = Word(checked(table + (uint)(handle / 4) * 4));
        if (block < 0x10000) throw new InvalidOperationException("游戏对象已经释放，请刷新。");
        uint pointer = Word(checked(block + (uint)(handle % 4) * 4));
        if (pointer < 0x10000) throw new InvalidOperationException("游戏对象已经释放，请刷新。");
        return pointer;
    }
    internal byte[] Page(int handle, int type, out uint pointer) {
        pointer = Pointer(handle);
        int length = type == 2 ? 36 : 44;
        byte[] meta = Read(pointer, length);
        uint wrapper = c.ModuleBase + (type == 2 ? 0x398e74u : type == 3 ? 0x398ee8u : 0x399138u);
        uint kind = c.ModuleBase + (type == 2 ? 0x398e68u : type == 3 ? 0x398f00u : 0x399088u);
        if (BitConverter.ToUInt32(meta, 0) != wrapper || BitConverter.ToInt32(meta, 4) != type ||
            BitConverter.ToUInt32(meta, 12) != c.Marker || BitConverter.ToUInt32(meta, 28) == 0 ||
            BitConverter.ToUInt32(meta, 32) != kind ||
            BitConverter.ToUInt32(meta, 20) > BitConverter.ToUInt32(meta, 24) ||
            (type != 2 && (BitConverter.ToUInt32(meta, 36) != globals.Context || BitConverter.ToInt32(meta, 40) != handle)))
            throw new InvalidOperationException("游戏对象结构与适配版本不一致，请刷新。");
        return meta;
    }
    internal int[] Values(int handle, int type, int expected = -1) {
        uint pointer;
        byte[] meta = Page(handle, type, out pointer);
        uint length = BitConverter.ToUInt32(meta, 20), data = BitConverter.ToUInt32(meta, 16);
        if ((length & 3) != 0 || length > 40000 || (expected >= 0 && length != expected * 4) ||
            (length > 0 && data < 0x10000))
            throw new InvalidOperationException("游戏数组或字段数量与适配版本不一致。");
        byte[] raw = length == 0 ? new byte[0] : Read(data, (int)length);
        if (!meta.SequenceEqual(Read(pointer, meta.Length)) || Pointer(handle) != pointer)
            throw new InvalidOperationException("游戏数据刚刚更新，请重新刷新。");
        int[] result = new int[length / 4];
        Buffer.BlockCopy(raw, 0, result, 0, raw.Length);
        return result;
    }
    internal string Text(int handle) {
        uint pointer;
        byte[] meta = Page(handle, 2, out pointer);
        uint length = BitConverter.ToUInt32(meta, 20), data = BitConverter.ToUInt32(meta, 16);
        if (length == 0 || length > 4096 || data < 0x10000)
            throw new InvalidOperationException("游戏人物或卡牌名称结构不一致。");
        byte[] raw = Read(data, (int)length);
        int zero = Array.IndexOf(raw, (byte)0);
        if (zero < 0) throw new InvalidOperationException("游戏字符串没有终止符。");
        if (!meta.SequenceEqual(Read(pointer, meta.Length)) || Pointer(handle) != pointer)
            throw new InvalidOperationException("游戏名称刚刚更新，请重新刷新。");
        return Encoding.GetEncoding(936, EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback).GetString(raw, 0, zero);
    }
    internal int Global(int index) { return (int)Word(globals.Data + (uint)index * 4); }
    internal int[] Characters() { return Values(Values(Global(257), 4, 1)[0], 3); }
    internal List<Dictionary<string, object>> Cards() {
        var result = new List<Dictionary<string, object>>();
        int[] orgs = Values(Values(Global(259), 4, 6)[0], 3, 10);
        for (int index = 0; index < orgs.Length; index++) {
            int[] cards = Values(Values(orgs[index], 4, 9)[0], 3);
            foreach (int handle in cards) {
                int[] card = Values(handle, 4, 13);
                if (card[6] <= 0 || card[6] > 11) throw new InvalidOperationException("卡牌份数与适配版本不一致。");
                result.Add(new Dictionary<string, object> { {"id", Text(card[9])}, {"faction", index + 1},
                    {"count", card[6]}, {"overridden", card[4] >= 0 || card[5] >= 0} });
            }
        }
        return result;
    }
    internal Dictionary<string, object> Snapshot() {
        int[] handles = Characters();
        var characters = new List<Dictionary<string, object>>();
        foreach (int handle in handles) {
            int[] value = Values(handle, 4, 7), story = Values(value[5], 4, 3);
            string name = Text(value[0]);
            if (value[1] < 0 || value[1] > 200 || story[1] < 0 || story[1] > 3 || Text(story[0]) != name)
                throw new InvalidOperationException("人物等级或故事记录与适配版本不一致。");
            characters.Add(new Dictionary<string, object> { {"handle", handle}, {"page", Pointer(handle)},
                {"name", name}, {"star", value[1]}, {"exp", value[2]}, {"next_exp", value[3]}, {"stage", story[1]},
                {"story_handle", value[5]}, {"story_page", Pointer(value[5])}, {"story_key", Text(story[2])} });
        }
        var cards = Cards();
        if (!Engine.SameGlobals(globals, Engine.CheckGlobals(c, globals.Owner)) || !handles.SequenceEqual(Characters()))
            throw new InvalidOperationException("游戏正在换档或取得卡牌，请稍后刷新。");
        return new Dictionary<string, object> { {"pid", c.Process.Id}, {"session", c.Session},
            {"characters", characters}, {"cards", cards} };
    }
}

internal static class FoodSelector {
    const uint Offset = 0x449b38;
    const int Length = 368, CodeLength = 14572638;
    const string OriginalHash = "967127b7fe972215b3900d3f6f3d84571a4aa29943b86f5b642a4a3da5a68171";
    static Connection connection;
    static GlobalsPage globals;
    static uint codeBase;
    static byte[] original, patch;
    static string character;
    static bool restoring;
    static volatile bool inputClosed;
    static int targetHandle, targetNameHandle;
    static int targetStoryHandle, targetMaximum;
    static uint targetPage, targetStringPage, targetStoryPage;

    static string Hash(byte[] value) {
        using (SHA256 sha = SHA256.Create())
            return BitConverter.ToString(sha.ComputeHash(value)).Replace("-", "").ToLowerInvariant();
    }
    static uint CodeBase(Connection c, GlobalsPage page) {
        byte[] bounds = c.Read(page.Context + 140, 8);
        if (bounds == null) throw new InvalidOperationException("游戏正在切换画面，请稍后重试。");
        uint start = BitConverter.ToUInt32(bounds, 0), end = BitConverter.ToUInt32(bounds, 4);
        if (start < 0x10000 || end <= start || end - start != CodeLength)
            throw new InvalidOperationException("餐券筛选程序与适配版本不一致。");
        return start;
    }
    static bool CurrentGlobals() {
        if (connection == null || connection.Process.HasExited) return false;
        GlobalsPage now = Engine.CheckGlobals(connection, globals.Owner);
        return Engine.SameGlobals(globals, now) && CodeBase(connection, now) == codeBase;
    }
    static bool CurrentTarget() {
        if (!CurrentGlobals()) return false;
        var vm = new VmPages(connection, globals);
        return vm.Pointer(targetHandle) == targetPage && vm.Pointer(targetNameHandle) == targetStringPage &&
            vm.Pointer(targetStoryHandle) == targetStoryPage && vm.Values(targetHandle, 4, 7)[0] == targetNameHandle &&
            vm.Values(targetHandle, 4, 7)[5] == targetStoryHandle &&
            vm.Values(targetStoryHandle, 4, 3)[1] < targetMaximum && vm.Characters().Contains(targetHandle);
    }
    static void Forget() {
        if (connection != null) connection.Dispose();
        connection = null; globals = null; original = patch = null; character = null; restoring = false;
    }
    static void Write(GlobalsPage page, byte[] expected, byte[] replacement) {
        using (var paused = new PausedGame(connection.Process)) {
            if (!Engine.SameGlobals(page, Engine.CheckGlobals(connection, page.Owner)) ||
                CodeBase(connection, page) != codeBase)
                throw new InvalidOperationException("游戏正在换档，本次未修改。");
            if (replacement == patch && !CurrentTarget())
                throw new InvalidOperationException("游戏人物刚刚变化，本次未指定，请重新读取。");
            byte[] pointer = connection.Read(page.Context + 136, 4);
            if (pointer == null) throw new InvalidOperationException("无法核对游戏执行位置。");
            uint ip = BitConverter.ToUInt32(pointer, 0);
            // Includes the surrounding finder, rather than only the lambda body.
            if (ip >= codeBase + 0x449b10 && ip < codeBase + 0x44a2f0)
                throw new InvalidOperationException("正在生成餐券候选，请回到稳定画面后重试。");
            // Check callers too: a lambda can currently be inside a getter/HLL.
            // CIntStack is a vtable, top index, and 256 inline return offsets.
            byte[] stack = connection.Read(page.Context + 188, 8);
            if (stack == null || BitConverter.ToUInt32(stack, 0) != connection.ModuleBase + 0x3987e4)
                throw new InvalidOperationException("无法核对餐券筛选的调用位置，本次未修改。");
            int top = BitConverter.ToInt32(stack, 4);
            if (top < -1 || top > 255) throw new InvalidOperationException("游戏调用栈与适配版本不一致。");
            byte[] returns = connection.Read(page.Context + 196, (top + 1) * 4);
            if (returns == null) throw new InvalidOperationException("无法核对游戏调用栈。");
            for (int index = 0; index <= top; index++) {
                uint caller = BitConverter.ToUInt32(returns, index * 4);
                if (caller >= 0x449b10 && caller < 0x44a2f0)
                    throw new InvalidOperationException("正在生成餐券候选，请回到稳定画面后重试。");
            }
            uint address = codeBase + Offset;
            byte[] before = connection.Read(address, Length);
            if (before == null || !before.SequenceEqual(expected))
                throw new InvalidOperationException("餐券筛选状态已改变，没有覆盖其他修改。");
            UIntPtr written;
            bool success = Native.WriteProcessMemory(connection.Handle, new IntPtr((long)address),
                replacement, (UIntPtr)Length, out written);
            byte[] after = connection.Read(address, Length);
            if (!success || written.ToUInt64() != Length || after == null || !after.SequenceEqual(replacement)) {
                Native.WriteProcessMemory(connection.Handle, new IntPtr((long)address), before,
                    (UIntPtr)Length, out written);
                after = connection.Read(address, Length);
                if (after == null || !after.SequenceEqual(before))
                    throw new InvalidOperationException("写入和恢复均失败，请关闭游戏并重新启动。");
                throw new InvalidOperationException("指定未完成，原筛选已恢复。");
            }
        }
    }
    static void Restore() {
        if (connection == null) return;
        restoring = true;
        if (connection.Process.HasExited) { Forget(); return; }
        GlobalsPage page = globals;
        if (!CurrentGlobals()) {
            // A load rebuilds VM pages; resolve anew before deciding what to restore.
            page = Engine.Locate(connection, false).Globals;
            if (CodeBase(connection, page) != codeBase) { Forget(); return; }
        }
        byte[] now = connection.Read(codeBase + Offset, Length);
        if (now != null && now.SequenceEqual(original)) { Forget(); return; }
        if (restoring && now != null && now.Select((value, i) => value == patch[i] || value == original[i]).All(value => value))
            Write(page, now, original);
        else Write(page, patch, original);
        Forget();
    }
    static void Arm(Dictionary<string, object> command) {
        Restore();
        byte[] candidate = Convert.FromBase64String((string)command["patch"]);
        if (candidate.Length != Length) throw new InvalidOperationException("餐券筛选代码长度不匹配。");
        connection = new Connection(true);
        try {
            globals = Engine.Locate(connection, false).Globals;
            codeBase = CodeBase(connection, globals);
            original = connection.Read(codeBase + Offset, Length);
            if (original == null || Hash(original) != OriginalHash)
                throw new InvalidOperationException("餐券筛选函数与适配版本不一致，或另一修改器已指定人物。");
            patch = candidate;
            if (!original.Skip(114).Take(142).SequenceEqual(patch.Skip(114).Take(142)))
                throw new InvalidOperationException("餐券指定改变了筛选函数以外的代码，没有修改。");
            character = (string)command["character"];
            if (connection.Process.Id != Convert.ToInt32(command["pid"]) || connection.Session != Convert.ToInt64(command["session"]))
                throw new InvalidOperationException("游戏已重新启动，请重新读取人物。");
            var vm = new VmPages(connection, globals);
            targetHandle = Convert.ToInt32(command["character_handle"]);
            targetPage = Convert.ToUInt32(command["character_page"]);
            if (!vm.Characters().Contains(targetHandle) || vm.Pointer(targetHandle) != targetPage)
                throw new InvalidOperationException("游戏正在换档，请重新读取人物。");
            int[] value = vm.Values(targetHandle, 4, 7), story = vm.Values(value[5], 4, 3);
            targetNameHandle = value[0]; targetStringPage = vm.Pointer(targetNameHandle);
            if (vm.Text(targetNameHandle) != character || vm.Text(story[0]) != character ||
                vm.Text(story[2]) != (string)command["story_key"] || story[1] != Convert.ToInt32(command["stage"]))
                throw new InvalidOperationException("人物或故事进度刚刚改变，请重新读取。");
            int maximum = Convert.ToInt32(command["maximum"]);
            targetMaximum = maximum;
            targetStoryHandle = Convert.ToInt32(command["story_handle"]);
            targetStoryPage = Convert.ToUInt32(command["story_page"]);
            if (value[5] != targetStoryHandle || vm.Pointer(targetStoryHandle) != targetStoryPage ||
                maximum <= 0 || maximum > 3 || story[1] >= maximum)
                throw new InvalidOperationException("当前人物的故事进度不符合指定要求。");
            var expectedCards = new HashSet<string>(((System.Collections.IEnumerable)command["card_ids"]).Cast<object>().Select(v => (string)v));
            if (!vm.Cards().Any(card => expectedCards.Contains((string)card["id"])))
                throw new InvalidOperationException("当前游戏不再持有该人物卡，请重新读取。");
            Write(globals, original, patch);
        } catch {
            byte[] now = original == null ? null : connection.Read(codeBase + Offset, Length);
            if (patch == null || original == null || (now != null && now.SequenceEqual(original))) Forget();
            else restoring = true;
            throw;
        }
    }
    static Dictionary<string, object> State(bool success, bool reply, string message) {
        return new Dictionary<string, object> { {"success", success}, {"reply", reply},
            {"armed", connection != null}, {"restoring", restoring}, {"character", character},
            {"message", message} };
    }
    static void Emit(Dictionary<string, object> state) {
        Console.WriteLine(new JavaScriptSerializer().Serialize(state));
        Console.Out.Flush();
    }
    internal static int Watch(string[] args) {
        Console.InputEncoding = Console.OutputEncoding = new UTF8Encoding(false);
        Process parent = null;
        try {
            int parentIndex = Array.IndexOf(args, "--parent-pid"), gameIndex = Array.IndexOf(args, "--game-dir");
            if (parentIndex < 0 || gameIndex < 0) throw new InvalidOperationException("运行组件缺少启动参数。");
            parent = Process.GetProcessById(Int32.Parse(args[parentIndex + 1]));
            RuntimeSettings.GameDirectory = args[gameIndex + 1];
            var commands = new Queue<Dictionary<string, object>>();
            Thread input = new Thread(delegate() {
                try {
                    string line;
                    while ((line = Console.ReadLine()) != null) {
                        Dictionary<string, object> command;
                        try { command = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(line); }
                        catch { command = new Dictionary<string, object> { {"action", "invalid"} }; }
                        lock (commands) commands.Enqueue(command);
                    }
                } finally { inputClosed = true; }
            });
            input.IsBackground = true; input.Start();
            DateTime retry = DateTime.MinValue;
            while (!inputClosed && !parent.HasExited) {
                Dictionary<string, object> command = null;
                lock (commands) { if (commands.Count > 0) command = commands.Dequeue(); }
                if (command != null) {
                    Dictionary<string, object> result;
                    try {
                        string action = (string)command["action"];
                        if (action == "arm") {
                            Arm(command);
                            result = State(true, true, "已指定“" + character + "”。后续战后只筛选此人物，剧情条件仍由游戏判断。取消后恢复随机。");
                        } else if (action == "cancel") {
                            Restore(); result = State(true, true, "指定已取消，恢复游戏原来的随机候选。");
                        } else if (action == "probe") {
                            using (var c = new Connection(false)) {
                                GlobalsPage page = Engine.Locate(c, false).Globals;
                                byte[] body = c.Read(CodeBase(c, page) + Offset, Length);
                                if (body == null || (Hash(body) != OriginalHash &&
                                    (connection == null || c.Process.Id != connection.Process.Id || !body.SequenceEqual(patch))))
                                    throw new InvalidOperationException("餐券筛选函数与适配版本不一致。");
                                result = State(true, true, "已读取当前运行中的人物和故事进度，本次未写入。");
                                var snapshot = new VmPages(c, page).Snapshot();
                                snapshot["source_code"] = Convert.ToBase64String(Hash(body) == OriginalHash ? body : original);
                                result["snapshot"] = snapshot;
                            }
                        } else throw new InvalidOperationException("未知餐券操作。");
                    } catch (Exception ex) { result = State(false, true, ex.Message); }
                    object requestId;
                    if (command.TryGetValue("request_id", out requestId)) result["request_id"] = requestId;
                    Emit(result);
                }
                if (connection != null && DateTime.UtcNow >= retry) {
                    try {
                        if (restoring || !CurrentTarget()) {
                            Restore(); Emit(State(true, false, "进度已切换或指定人物故事已完成。本次指定已取消，恢复随机餐券候选。"));
                        }
                    } catch (Exception ex) {
                        restoring = true;
                        Emit(State(false, false, "正在取消指定：" + ex.Message));
                        retry = DateTime.UtcNow.AddSeconds(3);
                    }
                }
                Thread.Sleep(100);
            }
            return 0;
        } catch (Exception ex) { Emit(State(false, true, ex.Message)); return 1; }
        finally {
            // Also runs after the UI crashes. Keep the restore owner alive while the
            // game is transitioning; never abandon an installed patch silently.
            while (connection != null) {
                try { Restore(); }
                catch { Thread.Sleep(1000); }
            }
            if (parent != null) parent.Dispose();
        }
    }
}
