import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import app_paths
import assets
import engine
import runtime
import settings
from ui_theme import FONT, GREEN, RED, surface


class Setup(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(24, 20))
        self.owner = owner
        config = settings.load()
        self.game = tk.StringVar(value=config.get('game_dir', ''))
        self.saves = tk.StringVar(value=str(settings.save_dir()))
        self.component = tk.StringVar(value=config.get('alice_path', ''))
        ttk.Label(self, text='首次使用先选择游戏目录。餐券与点数可直接连接游戏，卡牌图鉴需要准备一次。',
                  style='Hint.TLabel', wraplength=880).pack(anchor='w', pady=(0, 16))
        paths = surface(self, 18)
        paths.pack(fill='x')
        ttk.Label(paths, text='游戏与存档', style='CardTitle.TLabel').pack(anchor='w', pady=(0, 10))
        self.controls = []
        self.entries = []
        for label, value, command in [('游戏目录 · 包含 Rance10.exe', self.game, self.browse_game),
                                     ('存档目录 · 包含 LocalSave*.asd', self.saves, self.browse_saves)]:
            ttk.Label(paths, text=label, style='SurfaceHint.TLabel').pack(anchor='w', pady=(5, 5))
            row = ttk.Frame(paths, style='Surface.TFrame')
            row.pack(fill='x', pady=(0, 8))
            entry = ttk.Entry(row, textvariable=value, font=(FONT, 10))
            entry.pack(side='left', fill='x', expand=True)
            button = ttk.Button(row, text='选择目录', command=command)
            button.pack(side='right', padx=(10, 0))
            self.entries.append(entry)
            self.controls.append(button)
        row = ttk.Frame(paths, style='Surface.TFrame')
        row.pack(fill='x', pady=(8, 0))
        self.save_button = ttk.Button(row, text='保存并检查', style='Primary.TButton', command=self.save_paths)
        self.save_button.pack(side='left')
        self.detect_button = ttk.Button(row, text='识别正在运行的游戏', command=self.detect)
        self.detect_button.pack(side='left', padx=10)
        self.controls += [self.save_button, self.detect_button]
        self.feedback = ttk.Label(paths, text='游戏版本按文件内容核对，尚未适配的版本会停止修改。',
                                  style='SurfaceHint.TLabel', wraplength=850)
        self.feedback.pack(anchor='w', fill='x', pady=(12, 0))

        library = surface(self, 18)
        library.pack(fill='x', pady=(16, 0))
        ttk.Label(library, text='卡牌图鉴', style='CardTitle.TLabel').pack(anchor='w', pady=(0, 8))
        ttk.Label(library, text='卡牌数据和图片从你的本机游戏生成，缓存会保留到下次使用。',
                  style='SurfaceHint.TLabel', wraplength=850).pack(anchor='w')
        row = ttk.Frame(library, style='Surface.TFrame')
        row.pack(fill='x', pady=(12, 8))
        entry = ttk.Entry(row, textvariable=self.component, font=(FONT, 10))
        entry.pack(side='left', fill='x', expand=True)
        button = ttk.Button(row, text='选择本地组件', command=self.browse_component)
        button.pack(side='right', padx=(10, 0))
        self.entries.append(entry)
        self.controls.append(button)
        ttk.Label(library, text='可选：选择 alice-tools 0.13.0 的 alice.exe，以离线准备图鉴。',
                  style='SurfaceHint.TLabel', wraplength=850).pack(anchor='w')
        row = ttk.Frame(library, style='Surface.TFrame')
        row.pack(fill='x', pady=(12, 0))
        self.local_button = ttk.Button(row, text='使用本地组件准备', command=lambda: self.prepare(False))
        self.local_button.pack(side='left')
        self.download_button = ttk.Button(row, text='从官方源下载并准备', command=lambda: self.prepare(True))
        self.download_button.pack(side='left', padx=10)
        self.controls += [self.local_button, self.download_button]
        self.library_status = ttk.Label(library, text=self.library_text(), style='SurfaceHint.TLabel', wraplength=850)
        self.library_status.pack(anchor='w', fill='x', pady=(12, 0))
        ttk.Button(self, text='打开配置与缓存目录', command=lambda: os.startfile(str(app_paths.DATA_DIR))).pack(anchor='w', pady=(16, 0))
        self.update_actions()

    def library_text(self):
        return '本机图鉴已准备，可前往“卡牌扩充”。' if app_paths.CATALOG_FILE.exists() else '尚未准备图鉴。下载方式首次需要联网，组件只从原项目官方 GitHub 获取。'

    def browse_game(self):
        path = filedialog.askdirectory(parent=self, title='选择游戏程序所在文件夹')
        if path:
            self.game.set(path)

    def browse_saves(self):
        path = filedialog.askdirectory(parent=self, title='选择存档目录', initialdir=str(app_paths.documents_dir()))
        if path:
            self.saves.set(path)

    def browse_component(self):
        path = filedialog.askopenfilename(parent=self, title='选择 alice.exe', filetypes=[('alice.exe', 'alice.exe')])
        if path:
            self.component.set(path)

    def save_paths(self):
        game, saves, component = self.game.get().strip(), self.saves.get().strip(), self.component.get().strip()
        def work():
            if not game:
                raise ValueError('请选择游戏目录。')
            engine.validate_game(game)
            if not Path(saves).is_dir():
                raise ValueError('没有找到存档目录。请先在游戏中保存一次，或手动选择正确目录。')
            return game, saves, component
        def done(data):
            config = settings.save(*data)
            self.game.set(config['game_dir'])
            self.saves.set(config['save_dir'])
            engine.configure()
            self.owner.cards.invalidate()
            self.owner.numbers.current = None
            self.feedback.configure(text='游戏版本检查通过，目录设置已保存。', foreground=GREEN)
            self.owner.numbers.refresh()
        self.owner.run(work, done, '正在检查游戏版本与目录…', self.failed)

    def detect(self):
        def done(processes):
            if len(processes) != 1:
                self.failed('请只运行一个游戏实例，或手动选择游戏目录。')
                return
            self.game.set(str(Path(processes[0]['path']).parent))
            self.save_paths()
        self.owner.run(runtime.discover, done, '正在查找已运行的游戏…', self.failed)

    def failed(self, message):
        self.feedback.configure(text=message, foreground=RED)

    def prepare(self, download):
        if not settings.load().get('game_dir'):
            self.failed('请先保存并检查游戏目录。')
            return
        if self.game.get().strip() != settings.load()['game_dir'] or self.saves.get().strip() != str(settings.save_dir()):
            self.failed('目录已变更，请先点击“保存并检查”。')
            return
        game, tool = settings.game_dir(), self.component.get().strip()
        def done(report):
            config = settings.load()
            settings.save(config['game_dir'], settings.save_dir(), tool)
            self.owner.images.reload()
            self.owner.cards.invalidate()
            text = '图鉴已准备：%d 张卡面。' % report['cards']
            if report['missing_images']:
                text += ' %d 张缺少图片，可用名称与技能查看。' % report['missing_images']
            self.library_status.configure(text=text, foreground=GREEN)
            self.owner.status.configure(text=text, foreground=GREEN)
        self.owner.run(lambda: assets.prepare_library(game, tool, download, self.owner.progress), done,
                       '正在准备卡牌图鉴…', lambda message: self.library_status.configure(text=message, foreground=RED))

    def update_actions(self):
        state = 'disabled' if self.owner.busy else 'normal'
        for widget in self.controls + self.entries:
            widget.configure(state=state)
