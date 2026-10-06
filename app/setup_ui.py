import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
import app_paths
import assets
import engine
import runtime
import settings
import json
import save_compat
from ui_theme import FONT, GREEN, RED, BG, surface, ScrollBody, flow_buttons


class Setup(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(24, 20))
        self.owner = owner
        self.scroll = ScrollBody(self, background=BG)
        self.scroll.pack(fill="both", expand=True)
        content = self.scroll.body
        config = settings.load()
        self.game = tk.StringVar(value=config.get('game_dir', ''))
        self.saves = tk.StringVar(value=str(settings.save_dir()))
        self.component = tk.StringVar(value=config.get('alice_path', ''))
        ttk.Label(content, text='首次使用先选择游戏目录。餐券与点数可直接连接游戏，卡牌图鉴需要准备一次。',
                  style='Hint.TLabel', wraplength=880).pack(anchor='w', pady=(0, 16))
        paths = surface(content, 18)
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
        self.detect_button = ttk.Button(row, text='识别正在运行的游戏', command=self.detect)
        self.controls += [self.save_button, self.detect_button]
        self.compat_button = ttk.Button(row, text='复制兼容信息', command=self.copy_compatibility)
        flow_buttons(row, [self.save_button, self.detect_button, self.compat_button])
        self.controls.append(self.compat_button)
        self.feedback = ttk.Label(paths, text='图鉴从本机游戏生成；存档与实时功能分别识别所需的数据结构。',
                                  style='SurfaceHint.TLabel', wraplength=850)
        self.feedback.pack(anchor='w', fill='x', pady=(12, 0))

        library = surface(content, 18)
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
        self.download_button = ttk.Button(row, text='从官方源下载并准备', command=lambda: self.prepare(True))
        self.controls += [self.local_button, self.download_button]
        self.character_button = ttk.Button(row, text='更新人物资料', command=self.prepare_characters)
        self.controls.append(self.character_button)
        self.action_row = row
        self.action_row.bind("<Configure>", self.layout_actions)
        self.layout_actions()
        self.library_status = ttk.Label(library, text=self.library_text(), style='SurfaceHint.TLabel', wraplength=850)
        self.library_status.pack(anchor='w', fill='x', pady=(12, 0))
        self.data_button = ttk.Button(content, text='打开配置与缓存目录', command=lambda: os.startfile(str(app_paths.DATA_DIR)))
        self.data_button.pack(anchor='w', pady=(16, 0))
        self.scroll.bind_children(follow_focus=True)
        self.scroll.body.bind("<Configure>", self.wrap_labels, add="+")
        self.update_actions()

    def library_text(self):
        if not app_paths.CATALOG_FILE.exists():
            return '尚未准备图鉴。下载方式首次需要联网，组件只从原项目官方 GitHub 获取。'
        try:
            report = assets.library_status()
        except (ValueError, OSError) as exc:
            return str(exc)
        if report['missing']:
            return '图鉴共 %d 张，已有 %d 张卡面，还需补齐 %d 张。已有组件可离线补齐。' % (report['expected'], report['ready'], report['missing'])
        return '本机图鉴已准备：%d 张卡面，可前往“卡牌扩充”。' % report['ready']

    def library_ready(self, report):
        self.owner.images.reload()
        self.owner.numbers.icons.reload()
        self.owner.numbers.paint_resources()
        self.owner.numbers.render_story()
        self.owner.cards.invalidate()
        self.owner.training.invalidate()
        text = '图鉴已准备：%d 张卡面（本次补齐 %d 张，复用 %d 张）。' % (report['cards'], report['generated'], report['reused'])
        if report['missing_images']:
            text += ' %d 张缺少图片，可用名称与技能查看。' % report['missing_images']
        if report.get('warning'):
            text += '\n' + report['warning']
        if report.get('card_writes') is False:
            text += '\n当前游戏的加卡规则有变化；图鉴可查看，加卡需要适配。'
        self.library_status.configure(text=text, foreground=GREEN)
        self.owner.status.configure(text=text, foreground=GREEN)
        self.owner.tab_changed()

    def repair_existing_library(self):
        """Upgrade an existing library from local resources without downloading."""
        if self.owner.busy:
            self.owner.after(250, self.repair_existing_library)
            return
        config = settings.load()
        if not app_paths.CATALOG_FILE.exists() or not config.get('game_dir'):
            return
        try:
            if not assets.library_status()['missing'] and app_paths.ITEM_FILE.exists():
                return
        except (ValueError, OSError) as exc:
            self.library_status.configure(text=str(exc), foreground=RED)
            return
        def failed(message):
            self.library_status.configure(text='卡牌列表已补全，卡面补齐未完成：' + message + ' 可使用上方准备按钮重试。', foreground=RED)
        self.owner.run(lambda: assets.prepare_library(config['game_dir'], config.get('alice_path', ''),
                       False, self.owner.progress), self.library_ready,
                       '正在从本机游戏补齐旧图鉴的卡面…', failed)

    def layout_actions(self, event=None):
        buttons = [self.local_button, self.download_button, self.character_button]
        width = event.width if event else max(1, self.action_row.winfo_width())
        sizes = [button.winfo_reqwidth() + 12 for button in buttons]
        columns = 3 if sum(sizes) <= width else (2 if sum(sizes[:2]) <= width else 1)
        for i, button in enumerate(buttons):
            button.grid(row=i // columns, column=i % columns, sticky='w', padx=(0, 12), pady=(0, 8))

    def wrap_labels(self, event):
        width = max(280, event.width - 80)
        def visit(widget):
            if widget.winfo_class() == 'TLabel' and int(float(widget.cget('wraplength') or 0)):
                widget.configure(wraplength=width)
            for child in widget.winfo_children():
                visit(child)
        visit(self.scroll.body)

    def browse_game(self):
        path = filedialog.askdirectory(parent=self, title='选择游戏程序所在文件夹')
        if path:
            self.select_game(path)

    def select_game(self, path):
        previous = app_paths.default_save_dir(self.game.get())
        if not self.saves.get().strip() or Path(self.saves.get()).resolve() == previous.resolve():
            self.saves.set(str(app_paths.default_save_dir(path)))
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
            engine.validate_game_directory(game)
            if not saves:
                raise ValueError('请选择存档目录，或重新选择游戏目录以自动识别。')
            if Path(saves).exists() and not Path(saves).is_dir():
                raise ValueError('存档路径是文件，请选择存档文件夹。')
            session = self.owner.training.food_session
            if session.process and session.process.poll() is None and session.game_dir != str(Path(game).resolve()):
                session.close()
                if session.process.poll() is None:
                    raise ValueError('正在取消原目录游戏的餐券指定，目录尚未更改，请稍后重试。')
            return game, saves, component
        def done(data):
            config = settings.save(*data)
            self.game.set(config['game_dir'])
            self.saves.set(config['save_dir'])
            engine.configure()
            self.owner.cards.invalidate()
            self.owner.training.invalidate()
            self.owner.numbers.current = None
            self.owner.numbers.update_story(dict(armed=False))
            self.owner.prepare_icons()
            message = '目录已保存。请准备本机图鉴；实时修改的适配状态会单独显示。'
            if not Path(config['save_dir']).is_dir():
                message = '目录已保存，可先连接实时功能。保存游戏后可在此目录读取存档，或手动选择已有存档目录。'
            self.feedback.configure(text=message, foreground=GREEN)
            self.owner.numbers.refresh()
        self.owner.run(work, done, '正在检查游戏与存档目录…', self.failed)

    def detect(self):
        def done(processes):
            if len(processes) != 1:
                self.failed('请只运行一个游戏实例，或手动选择游戏目录。')
                return
            self.select_game(str(Path(processes[0]['path']).parent))
            self.save_paths()
        self.owner.run(runtime.discover, done, '正在查找已运行的游戏…', self.failed)

    def copy_compatibility(self):
        game = self.game.get().strip()
        def done(info):
            self.clipboard_clear()
            self.clipboard_append(json.dumps(info, ensure_ascii=False, indent=2))
            self.feedback.configure(text='兼容信息已复制，可粘贴到反馈中。内容不含存档、个人路径或游戏文本。', foreground=GREEN)
        self.owner.run(lambda: save_compat.report(game), done, '正在读取兼容信息…', self.failed)

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
            self.library_ready(report)
        self.owner.run(lambda: assets.prepare_library(game, tool, download, self.owner.progress), done,
                       '正在准备卡牌图鉴…', lambda message: self.library_status.configure(text=message, foreground=RED))

    def prepare_characters(self):
        if not app_paths.CATALOG_FILE.exists():
            self.failed('请先准备图鉴。新图鉴会同时准备人物资料。')
            return
        config = settings.load()
        if self.game.get().strip() != config.get('game_dir') or self.saves.get().strip() != str(settings.save_dir()):
            self.failed('目录已变更，请先点击“保存并检查”。')
            return
        import character_data
        def done(report):
            self.owner.training.invalidate()
            self.library_status.configure(text='人物资料已更新：%d位。已有卡面保持可用。' % report['characters'], foreground=GREEN)
        self.owner.run(lambda: character_data.prepare(settings.game_dir(), self.component.get().strip(), self.owner.progress),
                       done, '正在更新人物资料…', lambda message: self.library_status.configure(text=message, foreground=RED))

    def update_actions(self):
        state = 'disabled' if self.owner.busy else 'normal'
        for widget in self.controls + self.entries:
            widget.configure(state=state)
