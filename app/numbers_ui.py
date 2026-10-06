import queue
import threading
import tkinter as tk
from tkinter import ttk
import runtime
import settings
from game_icons import Icons
from ui_theme import BG, GREEN, RED, MUTED, FONT, surface, ScrollBody, px


class Numbers(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(20, 16))
        self.owner, self.current, self.chapter = owner, None, None
        self.icons, self.story_target, self.story_photo = Icons(owner), None, None
        self.probes, self.probing, self.generation = queue.Queue(), False, 0
        self.scroll = ScrollBody(self, background=BG)
        self.scroll.pack(fill='both', expand=True)
        content = self.scroll.body
        toolbar = ttk.Frame(content)
        toolbar.pack(fill='x', pady=(0, 16))
        toolbar.columnconfigure(0, weight=1)
        self.connection = ttk.Label(toolbar, text='先载入游戏进度，再连接修改器。', style='Hint.TLabel')
        self.connection.grid(row=0, column=0, sticky='ew')
        self.chapter_mode = tk.StringVar(value='自动识别')
        self.chapter_box = ttk.Combobox(toolbar, values=['自动识别', '第一部', '第二部'],
                                       textvariable=self.chapter_mode, state='readonly', width=9)
        self.chapter_box.grid(row=0, column=1, padx=(8, 10))
        self.chapter_box.bind('<<ComboboxSelected>>', self.change_chapter)
        self.refresh_button = ttk.Button(toolbar, text='刷新数值', command=self.refresh)
        self.refresh_button.grid(row=0, column=2)
        self.resources = ttk.Frame(content)
        self.resources.pack(fill='x')
        self.panels = [surface(self.resources, 18) for _ in range(3)]
        food, friendship, points = self.panels
        self.food_title, self.food_icon = self.heading(food, '餐券 / 金块')
        self.food, self.food_unit = self.metric(food, '/ 3 张')
        self.food_slots = self.slots(food)
        self.food_note = ttk.Label(food, text='第一部餐券，第二部金块。', style='SurfaceHint.TLabel', wraplength=px(self, 230))
        self.food_note.pack(fill='x', pady=(8, 12))
        self.fill_button = ttk.Button(food, text='补满餐券 / 金块', style='Primary.TButton', command=lambda: self.act('fill3'))
        self.fill_button.pack(side='bottom', fill='x')
        self.friend_title, self.friend_icon = self.heading(friendship, '友情')
        self.friend_points, _ = self.metric(friendship, '/ 3 点')
        self.friend_slots = self.slots(friendship)
        self.friend_note = ttk.Label(friendship, text='第二部在游戏中选择友情人物。', style='SurfaceHint.TLabel', wraplength=px(self, 230))
        self.friend_note.pack(fill='x', pady=(8, 12))
        self.friend_button = ttk.Button(friendship, text='补满 3 点友情', style='Primary.TButton', command=lambda: self.act('fillfriend3'))
        self.friend_button.pack(side='bottom', fill='x')
        _, self.points_icon = self.heading(points, '部队加成点数')
        self.points, _ = self.metric(points, '总点数')
        point_note = ttk.Label(points, text='包含已用点数，已有加成会保留。', style='SurfaceHint.TLabel', wraplength=px(self, 230))
        point_note.pack(fill='x', pady=(2, 12))
        for panel, note in zip(self.panels, [self.food_note, self.friend_note, point_note]):
            panel.bind('<Configure>', lambda e, label=note: label.configure(wraplength=max(1, e.width - 38)))
        self.add_button = ttk.Button(points, text='增加 5 点', style='Primary.TButton', command=lambda: self.act('addpoints', 5))
        self.add_button.pack(side='bottom', fill='x')
        setting = ttk.Frame(points, style='Surface.TFrame')
        setting.pack(side='bottom', fill='x', pady=(0, 12))
        ttk.Label(setting, text='设为', style='SurfaceHint.TLabel').pack(side='left', padx=(0, 6))
        self.target = tk.IntVar(value=25)
        self.spin = ttk.Spinbox(setting, from_=0, to=100, textvariable=self.target, width=4)
        self.spin.pack(side='left')
        self.set_button = ttk.Button(setting, text='设置总额', command=self.set_points)
        self.set_button.pack(side='right', padx=(6, 0))
        story = surface(content, 16)
        story.pack(fill='x', pady=(16, 0))
        self.story_preview = ttk.Label(story, style='Surface.TLabel', anchor='center', width=5)
        self.story_preview.pack(side='left', padx=(0, 16))
        actions = ttk.Frame(story, style='Surface.TFrame')
        actions.pack(side='right', padx=(12, 0))
        self.story_link = ttk.Button(actions, text='选择故事人物 →', command=owner.show_story_selector)
        self.story_link.pack(fill='x')
        self.story_cancel = ttk.Button(actions, text='取消指定', command=lambda: owner.training.cancel_food())
        self.story_copy = ttk.Frame(story, style='Surface.TFrame')
        self.story_copy.pack(side='left', fill='both', expand=True)
        self.story_name = ttk.Label(self.story_copy, text='尚未指定人物', style='CardTitle.TLabel')
        self.story_name.pack(anchor='w', pady=(4, 6))
        self.story_progress = ttk.Label(self.story_copy, text='选择想看的餐券人物。', style='Surface.TLabel')
        self.story_progress.pack(anchor='w')
        self.story_note = ttk.Label(self.story_copy, text='当前使用游戏的随机餐券候选。', style='SurfaceHint.TLabel', wraplength=500)
        self.story_note.pack(fill='x', pady=(6, 4))
        self.story_copy.bind('<Configure>', lambda e: [label.configure(wraplength=max(1, e.width))
                            for label in [self.story_name, self.story_progress, self.story_note]])
        self.state = ttk.Label(content, text='每次点击都会核对当前进度；菜单未刷新时，返回上一页再打开。', style='Hint.TLabel', wraplength=800)
        self.state.pack(fill='x', pady=(14, 16))
        recent = ttk.Frame(content)
        recent.pack(fill='x')
        ttk.Label(recent, text='最近操作', style='Summary.TLabel').pack(side='left')
        ttk.Button(recent, text='查看全部', command=lambda: owner.tabs.select(owner.records)).pack(side='right')
        self.recent = ttk.Frame(content)
        self.recent.pack(fill='x', pady=(8, 0))
        self.resources.bind('<Configure>', self.layout)
        content.bind('<Configure>', lambda e: self.state.configure(wraplength=max(250, e.width - 8)), add='+')
        self.scroll.bind_children()
        self.paint_resources()
        self.update_story({})
        self.update_actions()

    @staticmethod
    def heading(panel, text):
        row = ttk.Frame(panel, style='Surface.TFrame')
        row.pack(fill='x', pady=(0, 10))
        icon = ttk.Label(row, style='Surface.TLabel')
        icon.pack(side='left', padx=(0, 6))
        label = ttk.Label(row, text=text, style='CardTitle.TLabel')
        label.pack(side='left')
        return label, icon

    @staticmethod
    def metric(panel, unit):
        row = ttk.Frame(panel, style='Surface.TFrame')
        row.pack(fill='x', pady=(0, 4))
        value = ttk.Label(row, text='—', style='Value.TLabel')
        value.pack(side='left')
        label = ttk.Label(row, text=unit, style='SurfaceHint.TLabel')
        label.pack(side='left', padx=(4, 0), pady=(14, 0))
        return value, label

    @staticmethod
    def slots(panel):
        row = ttk.Frame(panel, style='Surface.TFrame')
        row.pack(fill='x')
        labels = [ttk.Label(row, style='Surface.TLabel') for _ in range(3)]
        for label in labels:
            label.pack(side='left', padx=(0, 3))
        return labels

    def layout(self, event=None):
        width = event.width if event else self.resources.winfo_width()
        minimum = max(px(self, 260), self.spin.master.winfo_reqwidth() + 38)
        columns = max(1, min(3, (width + 12) // (minimum + 12)))
        if getattr(self, '_columns', None) == columns:
            return
        self._columns = columns
        for index in range(3):
            self.resources.columnconfigure(index, weight=int(index < columns),
                                           uniform='resources' if index < columns else '', minsize=0)
        for i, panel in enumerate(self.panels):
            panel.grid(row=i // columns, column=i % columns, columnspan=1, sticky='nsew',
                       padx=(0 if i % columns == 0 else 6, 0 if i % columns == columns-1 else 6),
                       pady=(0 if i < columns else 12, 0))

    def paint_resources(self):
        second = self.chapter == 2
        kind = 'gold' if second else 'ticket'
        title = '金块' if second else ('餐券' if self.chapter == 1 else '餐券 / 金块')
        self.food_title.configure(text=title)
        self.food_unit.configure(text='/ 3 个' if second else '/ 3 张')
        self.fill_button.configure(text='补满 3 个金块' if second else '补满 3 张餐券' if self.chapter == 1 else '补满餐券 / 金块')
        self.food_note.configure(text='第二部金块，用于购买卡牌。' if second else '第一部餐券，观看故事时消耗。' if self.chapter == 1 else '第一部餐券，第二部金块。')
        self.friend_note.configure(text='补满后，在游戏里选择友情人物。' if second else '友情用于第二部；第一部使用餐券。')
        for label, resource in [(self.food_icon, kind), (self.friend_icon, 'friend'), (self.points_icon, 'army')]:
            label.configure(image=self.icons.get(resource, px(self, 24)))
        food = self.current['food'] if self.current else 0
        friend = self.current.get('friend_points', 0) if self.current and self.chapter != 1 else 0
        for labels, resource, value in [(self.food_slots, kind, food), (self.friend_slots, 'friend', friend)]:
            for index, label in enumerate(labels):
                label.configure(image=self.icons.get(resource, px(self, 36), index >= value))

    def update_story(self, state):
        if state.get('armed') and state.get('character'):
            previous = self.story_target or {}
            self.story_target = dict(state)
            if previous.get('character') == state['character'] and not state.get('card_id'):
                self.story_target['card_id'] = previous.get('card_id')
        elif state.get('reason') == 'completed' and state.get('character'):
            previous = self.story_target or {}
            self.story_target = dict(state, card_id=state.get('card_id') or previous.get('card_id'))
        elif state:
            self.story_target = None
        self.render_story()

    def render_story(self):
        target = self.story_target if self.chapter != 2 else None
        self.story_photo = self.owner.images.get(target.get('card_id'), (54, 81)) if target else None
        self.story_preview.configure(image=self.story_photo or '', text='' if self.story_photo else '◇')
        if target:
            armed = bool(target.get('armed'))
            self.story_name.configure(text=target['character'] + '  ·  餐券人物')
            self.story_progress.configure(text='已看 %d / %d' % (target['completed'], target['maximum']))
            self.story_note.configure(text='后续战后餐券筛选此人物；剧情条件由游戏判断。' if armed else '故事已看完，指定已结束。可以换一位人物。')
            self.story_link.configure(text='更换人物 →')
        else:
            self.story_name.configure(text='友情人物' if self.chapter == 2 else '尚未指定人物')
            self.story_progress.configure(text='补满友情后，在游戏中选择。' if self.chapter == 2 else '选择想看的餐券人物。')
            self.story_note.configure(text='第二部沿用游戏自己的友情人物选择。' if self.chapter == 2 else '当前使用游戏的随机餐券候选。')
            self.story_link.configure(text='在游戏中选择' if self.chapter == 2 else '选择故事人物 →')
        if self.story_target and self.story_target.get('armed'):
            self.story_cancel.pack(fill='x', pady=(6, 0))
            if self.chapter == 2:
                self.story_note.configure(text='仍有餐券人物指定：%s。可点击取消；界面切换不会改变指定。' % self.story_target['character'])
        else:
            self.story_cancel.pack_forget()
        self.update_actions()

    def set_recent(self, rows):
        for child in self.recent.winfo_children():
            child.destroy()
        if not rows:
            ttk.Label(self.recent, text='尚无修改记录。', style='Hint.TLabel').pack(anchor='w', pady=8)
        for when, summary in rows[-3:][::-1]:
            ttk.Separator(self.recent).pack(fill='x')
            row = ttk.Frame(self.recent, padding=(0, 8))
            row.pack(fill='x')
            ttk.Label(row, text=when[-8:-3], style='Hint.TLabel', width=7).pack(side='left')
            ttk.Label(row, text=summary.split('\n')[0], style='Hint.TLabel').pack(side='left', fill='x', expand=True)

    def update_actions(self):
        busy = self.owner.busy
        self.refresh_button.configure(state='disabled' if busy else 'normal')
        for button in [self.fill_button, self.set_button, self.add_button]:
            button.configure(state='normal' if self.current and not busy else 'disabled')
        self.friend_button.configure(state='normal' if self.current and self.chapter != 1 and not busy else 'disabled')
        self.spin.configure(state='disabled' if busy else 'normal')
        self.story_link.configure(state='disabled' if busy or self.chapter == 2 else 'normal')
        self.story_cancel.configure(state='disabled' if busy else 'normal')

    def refresh(self):
        self.generation += 1
        self.owner.run(runtime.run, self.read, '正在读取当前游戏数值…', self.failed)

    def start_poll(self):
        self.after(5000, self.poll)

    def poll(self):
        while not self.probes.empty():
            generation, game, data, error = self.probes.get_nowait()
            self.probing = False
            if generation == self.generation and game == settings.load().get('game_dir') and not self.owner.busy:
                if error:
                    self.failed(error)
                else:
                    self.read(data, automatic=True)
        if not self.probing and not self.owner.busy and self.owner.tabs.select() == str(self) and settings.load().get('game_dir'):
            self.probing = True
            generation, game = self.generation, settings.load()['game_dir']
            def probe():
                try:
                    self.probes.put((generation, game, runtime.run(), None))
                except Exception as exc:
                    self.probes.put((generation, game, None, str(exc)))
            threading.Thread(target=probe, daemon=True).start()
        self.after(1000 if self.probing else 5000, self.poll)

    def read(self, data, automatic=False):
        target = self.story_target
        if target and target.get('reason') == 'completed' and any(
                target.get(key) is not None and data.get(key) != target[key]
                for key in ['pid', 'session', 'global_owner', 'player_owner']):
            self.story_target = None
        self.current = data
        self.food.configure(text=str(data['food']))
        self.points.configure(text=str(data['total_points']))
        self.owner.set_connection(True)
        if not automatic:
            self.target.set(max(25, data['total_points']))
        self.apply_chapter()

    def change_chapter(self, event=None):
        self.apply_chapter()
        mode = self.chapter_mode.get()
        self.state.configure(text='恢复自动识别，按当前游戏章节显示。' if mode == '自动识别' else
                             '界面已切换为%s；不会改变游戏章节或资源数值。' % mode, foreground=MUTED)

    def apply_chapter(self):
        manual = {'第一部': 1, '第二部': 2}.get(self.chapter_mode.get())
        self.chapter = manual or (self.current.get('chapter') if self.current else None)
        if self.current:
            part = {1: '第一部', 2: '第二部'}.get(self.chapter)
            text = part + (' · 手动显示' if manual else ' · 自动识别') if part else '已连接 · 章节未识别'
            self.connection.configure(text=text, foreground=GREEN)
            self.friend_points.configure(text='—' if self.chapter == 1 else str(self.current.get('friend_points', 0)))
        self.paint_resources()
        self.render_story()

    def failed(self, message):
        self.current, self.chapter = None, None
        if self.story_target and not self.story_target.get('armed'):
            self.story_target = None
        for label in [self.food, self.friend_points, self.points]:
            label.configure(text='—')
        self.connection.configure(text=message, foreground=MUTED, wraplength=500)
        self.owner.set_connection(False)
        self.apply_chapter()

    def set_points(self):
        try:
            amount = int(self.target.get())
        except (ValueError, tk.TclError):
            self.state.configure(text='请输入 0 到 100 之间的整数。', foreground=RED)
            return
        self.act('setpoints', amount)

    def act(self, action, amount=None):
        self.generation += 1
        def done(data):
            self.read(data)
            if action == 'fill3':
                message = '%s：%d → %d，已补满。' % (self.food_title.cget('text'), data['food_before'][0], data['food'])
            elif action == 'fillfriend3':
                message = '友情：%d → %d 点，已补满。' % (data['food_before'][2], data['friend_points'])
            else:
                message = '部队总点数：%d → %d。已有加成会保留。' % (data['bonus_before'][2], data['total_points'])
            self.state.configure(text=message, foreground=GREEN)
            self.owner.status.configure(text=message)
            self.owner.refresh_history()
        def failed(message):
            self.state.configure(text=message, foreground=RED)
        self.owner.run(lambda: runtime.run(action, amount), done, '正在修改当前游戏数值…', failed)
