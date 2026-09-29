import ctypes
import json
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import engine
import app_paths
import settings
from game_profile import VERSION
from setup_ui import Setup
from gallery import Images
from numbers_ui import Numbers
from cards_ui import Cards
from ui_theme import BG, SURFACE, TEXT, MUTED, LINE, NAV, FONT, GREEN, RED, PageDeck, configure_styles


class App(tk.Tk):
    def __init__(self, auto_connect=True):
        app_paths.initialize()
        super().__init__()
        self.title('兰斯10修改器 · v' + VERSION)
        self.geometry('1300x880')
        self.minsize(1120, 800)
        self.configure(bg=BG)
        icon = app_paths.RESOURCE_DIR / 'app.ico'
        if icon.is_file():
            self.iconbitmap(default=str(icon))
        self.busy, self.backup = False, None
        self.mailbox = queue.Queue()
        self.progress_mailbox = queue.Queue()
        self.protocol('WM_DELETE_WINDOW', self.close)
        # A global *Font option overrides ttk's section and value styles.
        # Use explicit ttk styles so headings and numeric values retain their size.
        self.style()

        sidebar = tk.Frame(self, bg=NAV, width=190)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=NAV, padx=20, pady=28)
        brand.pack(fill='x')
        tk.Label(brand, text='RANCE X', font=('Georgia', 21, 'bold'), bg=NAV, fg='#e8c57e', anchor='w').pack(fill='x')
        tk.Label(brand, text='兰斯10修改器', font=(FONT, 11), bg=NAV, fg='#c6d1e0', anchor='w').pack(fill='x', pady=(9, 0))
        navigation = tk.Frame(sidebar, bg=NAV, padx=9)
        navigation.pack(fill='x', pady=(10, 0))
        info = tk.Frame(sidebar, bg=NAV, padx=20, pady=22)
        info.pack(side='bottom', fill='x')
        tk.Frame(info, bg='#35445a', height=1).pack(fill='x', pady=(0, 18))
        tk.Label(info, text='即时数值  ·  按需修改\n卡牌扩充  ·  读档生效', font=(FONT, 9),
                 bg=NAV, fg='#9aacc3', justify='left', anchor='w').pack(fill='x')
        tk.Label(info, text='本地工具  /  v' + VERSION, font=(FONT, 8), bg=NAV,
                 fg='#74859d', anchor='w').pack(fill='x', pady=(16, 0))

        workspace = tk.Frame(self, bg=BG)
        workspace.pack(side='left', fill='both', expand=True)
        header = tk.Frame(workspace, bg=SURFACE, padx=26, pady=17)
        header.pack(fill='x')
        heading = tk.Frame(header, bg=SURFACE)
        heading.pack(side='left', fill='x', expand=True)
        self.page_title = tk.Label(heading, text='餐券与部队点数', font=(FONT, 20, 'bold'),
                                  bg=SURFACE, fg=TEXT, anchor='w')
        self.page_title.pack(fill='x')
        self.page_hint = tk.Label(heading, text='游戏运行时修改，点击后即时生效', font=(FONT, 10),
                                 bg=SURFACE, fg=MUTED, anchor='w')
        self.page_hint.pack(fill='x', pady=(5, 0))
        self.connection = tk.Label(header, text='●  等待连接游戏', font=(FONT, 9),
                                   bg='#edf2f7', fg=MUTED, padx=14, pady=9)
        self.connection.pack(side='right', padx=(12, 0))
        tk.Frame(workspace, bg=LINE, height=1).pack(fill='x')
        self.images = Images(self)
        self.tabs = PageDeck(workspace, navigation)
        self.numbers = Numbers(self.tabs, self)
        self.cards = Cards(self.tabs, self)
        self.records = ttk.Frame(self.tabs, padding=(24, 20))
        self.setup = Setup(self.tabs, self)
        self.tabs.add(self.numbers, text='游玩中修改', subtitle='餐券与部队点数')
        self.tabs.add(self.cards, text='卡牌扩充', subtitle='选卡 · 图鉴 · 技能')
        self.tabs.add(self.records, text='记录与备份', subtitle='修改记录与原始存档')
        self.tabs.add(self.setup, text='设置与图鉴', subtitle='目录 · 连接 · 图鉴准备')
        self.build_records()
        self.tabs.bind('<<NotebookTabChanged>>', self.tab_changed)
        footer = ttk.Frame(workspace, padding=(24, 8, 24, 10))
        footer.pack(side='bottom', fill='x')
        self.status = ttk.Label(footer, text='就绪。餐券与点数即时生效，加卡后请重新读档。', style='Hint.TLabel', wraplength=820)
        self.status.pack(side='left', fill='x', expand=True)
        self.top = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text='保持窗口在最前', variable=self.top,
                         command=lambda: self.attributes('-topmost', self.top.get())).pack(side='right')
        footer.bind('<Configure>', lambda e: self.status.configure(wraplength=max(380, e.width - 200)))
        tk.Frame(workspace, bg=LINE, height=1).pack(side='bottom', fill='x')
        self.tabs.pack(fill='both', expand=True)
        self.after(100, self.drain)
        if not settings.load().get('game_dir'):
            self.tabs.select(self.setup)
        elif auto_connect:
            self.after(250, self.numbers.refresh)

    def style(self):
        self.theme = configure_styles(self)

    def set_connection(self, connected):
        self.connection.configure(text='●  游戏已连接' if connected else '●  游戏未连接',
                                  fg=GREEN if connected else RED,
                                  bg='#e9f6f0' if connected else '#fceef0')

    def build_records(self):
        ttk.Label(self.records, text='每次修改都有记录，添加卡牌会自动保留原始存档。', style='Hint.TLabel').pack(anchor='w', pady=(0, 16))
        bar = ttk.Frame(self.records)
        bar.pack(fill='x', pady=(0, 14))
        ttk.Button(bar, text='打开原档备份', command=self.open_backup).pack(side='left')
        ttk.Button(bar, text='打开使用说明', command=lambda: os.startfile(str(app_paths.RESOURCE_DIR / '使用说明.txt'))).pack(side='left', padx=10)
        ttk.Button(bar, text='刷新记录', command=self.refresh_history).pack(side='left')
        self.history = tk.Text(self.records, bg=SURFACE, fg=TEXT, relief='flat', wrap='word', padx=20, pady=18,
                               highlightbackground=LINE, highlightthickness=1,
                               spacing1=5, spacing3=5, font=(FONT, 11), state='disabled')
        self.history.pack(fill='both', expand=True)
        self.refresh_history()

    def refresh_history(self):
        if not hasattr(self, 'history'):
            return
        lines = []
        path = app_paths.LOG_FILE
        if path.exists():
            for text in path.read_text(encoding='utf-8').splitlines()[-40:]:
                try:
                    r = json.loads(text)
                    when = r.get('time', '').replace('T', ' ')
                    if r.get('action') == 'fill3':
                        summary = '餐券：%s → %s张' % (r['food_before'][0], r['food'])
                    elif r.get('action') in ['setpoints', 'addpoints']:
                        summary = '部队总点数：%s → %s' % (r['bonus_before'][2], r['total_points'])
                    elif r.get('action') == 'cards':
                        summary = '%s号存档加卡：%s → %s张\n    %s' % (r['slot'], r['before'], r['after'], '、'.join(r['cards']))
                    else:
                        continue
                    lines.append(when + '  ' + summary)
                except (ValueError, KeyError, TypeError):
                    continue
        content = '\n\n'.join(reversed(lines)) if lines else '本修改器还没有执行修改。\n\n餐券与部队点数：点击按钮后即时生效，随后可正常保存游戏。\n\n卡牌扩充：先保存当前进度，选择存档与卡牌；添加完成后重新读档。'
        self.history.configure(state='normal')
        self.history.delete('1.0', 'end')
        self.history.insert('1.0', content)
        self.history.configure(state='disabled')

    def open_backup(self):
        path = Path(self.backup) if self.backup else settings.backup_dir()
        if path.exists():
            os.startfile(str(path))

    def log(self, record):
        with app_paths.LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def tab_changed(self, event=None):
        titles = {str(self.numbers): ('餐券与部队点数', '游戏运行时修改，点击后即时生效'),
                  str(self.cards): ('卡牌扩充', '查看卡面与技能，按存档选择要添加的卡牌'),
                  str(self.records): ('记录与备份', '查看修改记录，找到添加卡牌前的原始存档'),
                  str(self.setup): ('设置与图鉴', '选择你的游戏目录，准备本机卡牌图鉴')}
        title, hint = titles[self.tabs.select()]
        self.page_title.configure(text=title)
        self.page_hint.configure(text=hint)
        if self.tabs.select() == str(self.cards) and not self.cards.loaded:
            if self.busy:
                self.after(200, self.tab_changed)
            else:
                self.cards.refresh()

    def update_actions(self):
        self.numbers.update_actions()
        self.cards.update_actions()
        if hasattr(self, 'setup'):
            self.setup.update_actions()

    def progress(self, message):
        self.progress_mailbox.put(message)

    def run(self, action, success, text, failure=None):
        if self.busy:
            return
        self.busy = True
        self.status.configure(text=text, foreground=MUTED)
        self.update_actions()
        def worker():
            try:
                self.mailbox.put((success, action(), None, None))
            except Exception as exc:
                self.mailbox.put((failure, str(exc), traceback.format_exc(), text))
        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        while not self.progress_mailbox.empty():
            self.status.configure(text=self.progress_mailbox.get(), foreground=MUTED)
        while not self.mailbox.empty():
            callback, data, trace, operation = self.mailbox.get()
            self.busy = False
            if trace:
                app_paths.ERROR_FILE.write_text(trace, encoding='utf-8-sig')
                self.status.configure(text=data, foreground=RED)
                if callback:
                    callback(data)
                else:
                    messagebox.showerror('操作未完成', data, parent=self)
            else:
                self.status.configure(text='已完成。', foreground=GREEN)
                callback(data)
            self.update_actions()
        self.after(100, self.drain)

    def close(self):
        if self.busy:
            self.status.configure(text='正在完成操作，请完成后关闭窗口。')
            return
        self.destroy()


if __name__ == '__main__':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:
        if '--self-test' in sys.argv:
            from smoke import run
            run()
        else:
            App().mainloop()
    except Exception:
        error = traceback.format_exc()
        app_paths.initialize()
        app_paths.ERROR_FILE.write_text(error, encoding='utf-8-sig')
        if '--self-test' in sys.argv:
            raise
        ctypes.windll.user32.MessageBoxW(None, '启动失败，错误详情保存在：\n' + str(app_paths.ERROR_FILE) + '\n' + error[-600:], '兰斯10修改器', 16)
