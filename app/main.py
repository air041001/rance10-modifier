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
from training_ui import Training
import ui_theme
from ui_theme import BG, SURFACE, TEXT, MUTED, LINE, NAV, FONT, GREEN, RED, PageDeck, configure_styles, px, ScrollBody, flow_buttons


class App(tk.Tk):
    def __init__(self, auto_connect=True):
        app_paths.initialize()
        super().__init__()
        ui_theme.set_palette(settings.load().get('theme', 'dark'))
        self.title('兰斯10修改器 · v' + VERSION)
        self.initial_size = ui_theme.fit_window(self)
        self.configure(bg=BG)
        icon = app_paths.RESOURCE_DIR / 'app.ico'
        if icon.is_file():
            self.iconbitmap(default=str(icon))
        self.busy, self.backup = False, None
        self._connected = False
        self.mailbox = queue.Queue()
        self.progress_mailbox = queue.Queue()
        self.cosmetics = queue.Queue()
        self.protocol('WM_DELETE_WINDOW', self.close)
        # A global *Font option overrides ttk's section and value styles.
        # Use explicit ttk styles so headings and numeric values retain their size.
        self.style()

        sidebar = self.sidebar = tk.Frame(self, bg=NAV, width=px(self, 180))
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=NAV, padx=20, pady=24)
        brand.pack(fill='x')
        self.brand_title = tk.Label(brand, text='RANCE X', font=('Segoe UI', 19, 'bold'), bg=NAV, fg=ui_theme.BLUE, anchor='w')
        self.brand_title.pack(fill='x')
        tk.Label(brand, text='兰斯10修改器', font=(FONT, 10), bg=NAV, fg=TEXT, anchor='w').pack(fill='x', pady=(6, 0))
        info = tk.Frame(sidebar, bg=NAV, padx=20, pady=22)
        info.pack(side='bottom', fill='x')
        tk.Frame(info, bg=LINE, height=1).pack(fill='x', pady=(0, 18))
        tk.Label(info, text='即时数值  ·  按需修改\n卡牌扩充  ·  读档生效', font=(FONT, 9),
                 bg=NAV, fg=MUTED, justify='left', anchor='w').pack(fill='x')
        tk.Label(info, text='本地工具  /  v' + VERSION, font=(FONT, 8), bg=NAV,
                 fg=MUTED, anchor='w').pack(fill='x', pady=(16, 0))
        self.navigation_scroll = ScrollBody(sidebar, background=NAV, autohide=True)
        self.navigation_scroll.pack(fill='both', expand=True, pady=(10, 0))
        navigation = self.navigation_scroll.body
        navigation.configure(padx=9)

        workspace = tk.Frame(self, bg=BG)
        workspace.pack(side='left', fill='both', expand=True)
        header = tk.Frame(workspace, bg=BG, padx=20, pady=18)
        header.pack(fill='x')
        header.columnconfigure(0, weight=1)
        heading = tk.Frame(header, bg=BG)
        heading.grid(row=0, column=0, sticky='ew')
        self.page_title = tk.Label(heading, text='游玩中修改', font=(FONT, 16, 'bold'),
                                  bg=BG, fg=TEXT, anchor='w')
        self.page_title.pack(fill='x')
        self.page_hint = tk.Label(heading, text='当前游戏的资源与部队加成', font=(FONT, 9),
                                 bg=BG, fg=MUTED, anchor='w', wraplength=600)
        self.page_hint.pack(fill='x', pady=(5, 0))
        self.theme_button = ttk.Button(header, text='浅色' if ui_theme.MODE == 'dark' else '深色', command=self.toggle_theme)
        self.theme_button.grid(row=0, column=2, padx=(12, 0))
        self.connection = tk.Label(header, text='●  等待连接', font=(FONT, 9), bg=BG, fg=MUTED)
        self.connection.grid(row=0, column=1, padx=(12, 0))
        heading.bind('<Configure>', lambda e: [label.configure(wraplength=max(1, e.width))
                     for label in [self.page_title, self.page_hint]])
        tk.Frame(workspace, bg=LINE, height=1).pack(fill='x')
        self.images = Images(self)
        self.tabs = PageDeck(workspace, navigation)
        self.numbers = Numbers(self.tabs, self)
        self.cards = Cards(self.tabs, self)
        self.training = Training(self.tabs, self)
        self.records = ttk.Frame(self.tabs, padding=(24, 20))
        self.setup = Setup(self.tabs, self)
        self.tabs.add(self.numbers, text='游玩中修改', subtitle='餐券 · 友情 · 点数')
        self.tabs.add(self.cards, text='卡牌扩充', subtitle='选卡 · 图鉴 · 技能')
        self.tabs.add(self.training, text='人物培养', subtitle='★等级 · 强化 · 餐券故事')
        self.tabs.add(self.records, text='记录与备份', subtitle='修改记录与原始存档')
        self.tabs.add(self.setup, text='设置与图鉴', subtitle='目录 · 连接 · 图鉴准备')
        self.update_idletasks()
        sidebar.configure(width=max(px(self, 180), brand.winfo_reqwidth(), info.winfo_reqwidth(),
                                    navigation.winfo_reqwidth() + self.navigation_scroll.scrollbar.winfo_reqwidth()))
        self.navigation_scroll.bind_children(follow_focus=True)
        self.build_records()
        self.tabs.bind('<<NotebookTabChanged>>', self.tab_changed)
        footer = ttk.Frame(workspace, padding=(24, 8, 24, 10))
        footer.pack(side='bottom', fill='x')
        self.status = ttk.Label(footer, text='就绪。资源与点数即时生效，加卡后请重新读档。', style='Hint.TLabel', wraplength=820)
        self.status.pack(side='left', fill='x', expand=True)
        self.top = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text='保持窗口在最前', variable=self.top,
                         command=lambda: self.attributes('-topmost', self.top.get())).pack(side='right')
        self.status.bind('<Configure>', lambda e: self.status.configure(wraplength=max(1, e.width)))
        tk.Frame(workspace, bg=LINE, height=1).pack(side='bottom', fill='x')
        self.tabs.pack(fill='both', expand=True)
        self.after(100, self.drain)
        self.after_idle(self.apply_window_theme)
        self.bind('<Map>', lambda event: self.after_idle(self.apply_window_theme)
                  if event.widget is self else None)
        if not settings.load().get('game_dir'):
            self.tabs.select(self.setup)
        elif auto_connect:
            self.after(250, self.numbers.refresh)
            self.after(750, self.setup.repair_existing_library)
        if auto_connect:
            self.numbers.start_poll()
            self.prepare_icons()

    def style(self):
        self.theme = configure_styles(self)

    def apply_window_theme(self):
        self.window_theme = ui_theme.apply_window_theme(self)

    def toggle_theme(self, persist=True):
        old, current = ui_theme.set_palette('light' if ui_theme.MODE == 'dark' else 'dark')
        ui_theme.recolour(self, old, current)
        self.style()
        self.apply_window_theme()
        self.theme_button.configure(text='浅色' if ui_theme.MODE == 'dark' else '深色')
        self.set_connection(self._connected)
        self.tabs.select(self.tabs.select())
        self.cards.theme_changed()
        self.numbers.icons.reload()
        self.numbers.paint_resources()
        self.numbers.render_story()
        if persist:
            settings.save_theme(ui_theme.MODE)

    def prepare_icons(self):
        game = settings.load().get('game_dir')
        if not game:
            return
        def work():
            import game_icons
            try:
                game_icons.prepare_available(game)
            except Exception:
                # Missing optional art uses the matching ticket/gold/friend glyph.
                pass
            self.cosmetics.put(game)
        threading.Thread(target=work, daemon=True).start()

    def show_story_selector(self):
        if self.busy:
            return
        self.training.loaded = True
        self.training.query.set('')
        if self.numbers.story_target:
            self.training.active = self.numbers.story_target['character']
        self.tabs.select(self.training)
        self.training.load_live()

    def set_connection(self, connected):
        self._connected = connected
        self.connection.configure(text='●  游戏已连接' if connected else '●  等待连接',
                                  fg=ui_theme.GREEN if connected else ui_theme.MUTED, bg=ui_theme.BG)

    def build_records(self):
        hint = ttk.Label(self.records, text='每次修改都有记录，加卡与培养修改会自动保留原始存档。', style='Hint.TLabel')
        hint.pack(fill='x', pady=(0, 16))
        hint.bind('<Configure>', lambda e: hint.configure(wraplength=max(1, e.width)))
        bar = ttk.Frame(self.records)
        bar.pack(fill='x', pady=(0, 14))
        flow_buttons(bar, [ttk.Button(bar, text='打开原档备份', command=self.open_backup),
                          ttk.Button(bar, text='打开使用说明', command=lambda: os.startfile(str(app_paths.RESOURCE_DIR / '使用说明.txt'))),
                          ttk.Button(bar, text='刷新记录', command=self.refresh_history)])
        self.history = tk.Text(self.records, bg=SURFACE, fg=TEXT, relief='flat', wrap='word', padx=20, pady=18,
                               highlightbackground=LINE, highlightthickness=1,
                               spacing1=5, spacing3=5, font=(FONT, 11), state='disabled')
        self.history.pack(fill='both', expand=True)
        self.refresh_history()

    def refresh_history(self):
        if not hasattr(self, 'history'):
            return
        lines, recent = [], []
        path = app_paths.LOG_FILE
        if path.exists():
            for text in path.read_text(encoding='utf-8').splitlines()[-40:]:
                try:
                    r = json.loads(text)
                    when = r.get('time', '').replace('T', ' ')
                    if r.get('action') == 'fill3':
                        summary = '餐券 / 金块：%s → %s' % (r['food_before'][0], r['food'])
                    elif r.get('action') == 'fillfriend3':
                        summary = '第二部友情：%s → %s点' % (r['food_before'][2], r['friend_points'])
                    elif r.get('action') in ['fillbattle3', 'addbattle']:
                        index = r['battle_country'] - 1
                        summary = '%s战果：%s → %s点' % (r['battle_country_name'], r['battle_before'][index], r['battle_points'][index])
                    elif r.get('action') in ['setpoints', 'addpoints']:
                        summary = '部队总点数：%s → %s' % (r['bonus_before'][2], r['total_points'])
                    elif r.get('action') == 'cards':
                        summary = '%s号存档加卡：%s → %s张\n    %s' % (r['slot'], r['before'], r['after'], '、'.join(r['cards']))
                    elif r.get('action') in ['star', 'enhancement']:
                        summary = '%s号存档 · %s · %s：%s → %s' % (r['slot'], r['target'],
                                   '人物★' if r['action'] == 'star' else '同卡强化', r['before'], r['after'])
                    else:
                        continue
                    lines.append(when + '  ' + summary)
                    recent.append((when, summary))
                except (ValueError, KeyError, TypeError):
                    continue
        content = '\n\n'.join(reversed(lines)) if lines else '本修改器还没有执行修改。\n\n餐券、金块、战果、友情与部队点数：点击按钮后即时生效，随后可正常保存游戏。\n\n卡牌扩充：先保存当前进度，选择存档与卡牌；添加完成后重新读档。'
        self.history.configure(state='normal')
        self.history.delete('1.0', 'end')
        self.history.insert('1.0', content)
        self.history.configure(state='disabled')
        self.numbers.set_recent(recent)

    def open_backup(self):
        path = Path(self.backup) if self.backup else settings.backup_dir()
        if path.exists():
            os.startfile(str(path))

    def log(self, record):
        with app_paths.LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def tab_changed(self, event=None):
        titles = {str(self.numbers): ('游玩中修改', '当前游戏的资源与部队加成'),
                  str(self.cards): ('卡牌扩充', '查看卡面与技能，按存档选择要添加的卡牌'),
                  str(self.training): ('人物培养与餐券故事', '存档培养 · 当前游戏人物 · 指定战后餐券候选'),
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
        elif self.tabs.select() == str(self.training) and not self.training.loaded:
            if self.busy:
                self.after(200, self.tab_changed)
            else:
                self.training.refresh()

    def update_actions(self):
        self.numbers.update_actions()
        self.cards.update_actions()
        self.training.update_actions()
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
        while not self.cosmetics.empty():
            game = self.cosmetics.get()
            if game == settings.load().get('game_dir'):
                self.numbers.icons.reload()
                self.numbers.paint_resources()
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
        if self.training.food_session.process and self.training.food_session.process.poll() is None:
            self.run(self.training.food_session.close, lambda result: self.destroy(), '正在取消餐券指定并关闭…')
        else:
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
            if '--output' in sys.argv:
                try:
                    output = Path(sys.argv[sys.argv.index('--output') + 1])
                    output.write_text(json.dumps({'self_test_failed': True, 'error': error},
                                                 ensure_ascii=False, indent=2), encoding='utf-8')
                except (IndexError, OSError):
                    pass
            sys.exit(1)
        ctypes.windll.user32.MessageBoxW(None, '启动失败，错误详情保存在：\n' + str(app_paths.ERROR_FILE) + '\n' + error[-600:], '兰斯10修改器', 16)
