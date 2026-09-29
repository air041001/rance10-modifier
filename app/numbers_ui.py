import tkinter as tk
from tkinter import ttk
import runtime
from ui_theme import GREEN, RED, FONT, surface


class Numbers(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(24, 22))
        self.owner, self.current = owner, None
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', pady=(0, 20))
        self.connection = ttk.Label(toolbar, text='等待连接游戏，首次使用请先设置游戏目录。', style='Hint.TLabel')
        self.connection.pack(side='left')
        self.refresh_button = ttk.Button(toolbar, text='刷新当前数值', command=self.refresh)
        self.refresh_button.pack(side='right')

        row = ttk.Frame(self)
        row.pack(fill='x')
        row.columnconfigure(0, weight=4, uniform='tiles')
        row.columnconfigure(1, weight=5, uniform='tiles')
        food = surface(row, 24)
        food.grid(row=0, column=0, sticky='nsew', padx=(0, 10))
        ttk.Label(food, text='餐券', style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(food, text='当前持有', style='SurfaceHint.TLabel').pack(anchor='w', pady=(16, 0))
        metric = ttk.Frame(food, style='Surface.TFrame')
        metric.pack(fill='x', pady=(2, 4))
        self.food = ttk.Label(metric, text='—', style='Value.TLabel')
        self.food.pack(side='left')
        ttk.Label(metric, text='/ 3 张', style='SurfaceHint.TLabel', font=(FONT, 14)).pack(side='left', padx=(12, 0), pady=(22, 0))
        ttk.Label(food, text='需要时点击，立即补满。', style='SurfaceHint.TLabel').pack(anchor='w', pady=(0, 28))
        self.fill_button = ttk.Button(food, text='补满 3 张餐券', style='Primary.TButton', command=lambda: self.act('fill3'))
        self.fill_button.pack(fill='x', pady=(12, 0))

        points = surface(row, 24)
        points.grid(row=0, column=1, sticky='nsew', padx=(10, 0))
        ttk.Label(points, text='部队加成点数', style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(points, text='总点数 · 包含已经使用的点数', style='SurfaceHint.TLabel').pack(anchor='w', pady=(16, 0))
        self.points = ttk.Label(points, text='—', style='Value.TLabel')
        self.points.pack(anchor='w', pady=(2, 4))
        ttk.Label(points, text='已有加成选择会保留。', style='SurfaceHint.TLabel').pack(anchor='w', pady=(0, 16))
        setting = ttk.Frame(points, style='Surface.TFrame')
        setting.pack(fill='x')
        ttk.Label(setting, text='目标总额', style='Surface.TLabel').pack(side='left', padx=(0, 10))
        self.target = tk.IntVar(value=25)
        self.spin = ttk.Spinbox(setting, from_=0, to=100, textvariable=self.target, width=5)
        self.spin.pack(side='left')
        self.set_button = ttk.Button(setting, text='设置总额', command=self.set_points)
        self.set_button.pack(side='right', padx=(10, 0))
        self.add_button = ttk.Button(points, text='增加 5 点', style='Primary.TButton', command=lambda: self.act('addpoints', 5))
        self.add_button.pack(fill='x', pady=(12, 0))

        instructions = surface(self, 22)
        instructions.pack(fill='x', pady=(22, 0))
        ttk.Label(instructions, text='使用提示', style='CardTitle.TLabel').pack(anchor='w', pady=(0, 12))
        ttk.Label(instructions, text='无需先保存  ·  连接已载入进度的游戏后，点击按钮即可修改。',
                  style='Surface.TLabel', wraplength=820).pack(anchor='w')
        ttk.Label(instructions, text='菜单未刷新时  ·  返回上一页，再打开餐券或部队加成菜单。',
                  style='SurfaceHint.TLabel', wraplength=820).pack(anchor='w', pady=(10, 0))
        ttk.Label(instructions, text='修改之后  ·  可以继续游玩，并在游戏中正常保存进度。',
                  style='SurfaceHint.TLabel', wraplength=820).pack(anchor='w', pady=(10, 0))
        self.state = ttk.Label(self, text='每次点击都会重新读取当前进度。餐券上限为 3 张，部队总额最高 100 点。',
                               style='Hint.TLabel', wraplength=900)
        self.state.pack(anchor='w', fill='x', pady=(20, 0))
        self.bind('<Configure>', lambda e: self.state.configure(wraplength=max(300, e.width - 48)))
        self.update_actions()

    def update_actions(self):
        busy = self.owner.busy
        self.refresh_button.configure(state='disabled' if busy else 'normal')
        for button in [self.fill_button, self.set_button, self.add_button]:
            button.configure(state='normal' if self.current and not busy else 'disabled')
        self.spin.configure(state='disabled' if busy else 'normal')

    def refresh(self):
        self.owner.run(lambda: runtime.run(), self.read, '正在读取餐券与部队点数…', self.failed)

    def read(self, data):
        self.current = data
        self.food.configure(text=str(data['food']))
        self.points.configure(text=str(data['total_points']))
        self.connection.configure(text='●  已连接当前游戏进度', foreground=GREEN)
        self.owner.set_connection(True)
        self.target.set(max(25, data['total_points']))
        self.update_actions()

    def failed(self, message):
        self.current = None
        self.connection.configure(text=message, foreground=RED, wraplength=710)
        self.owner.set_connection(False)
        self.update_actions()

    def set_points(self):
        try:
            amount = int(self.target.get())
        except (ValueError, tk.TclError):
            self.state.configure(text='请输入 0 到 100 之间的整数。', foreground=RED)
            return
        self.act('setpoints', amount)

    def act(self, action, amount=None):
        def done(data):
            self.read(data)
            if action == 'fill3':
                message = '餐券已补满：%d → 3 张。若图标未刷新，请返回上一页再打开当前菜单。' % data['food_before'][0]
            else:
                message = '部队总点数：%d → %d。请重新打开部队加成页，然后可正常保存游戏。' % (data['bonus_before'][2], data['total_points'])
            self.state.configure(text=message, foreground=GREEN)
            self.owner.status.configure(text=message)
            self.owner.refresh_history()
        def failed(message):
            self.state.configure(text=message, foreground=RED)
        self.owner.run(lambda: runtime.run(action, amount), done,
                       '正在补满餐券…' if action == 'fill3' else '正在设置部队总点数…', failed)
