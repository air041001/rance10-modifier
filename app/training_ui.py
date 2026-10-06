import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import app_paths
import engine
import training
import food
from ui_theme import FONT, GREEN, MUTED, BG, surface, ScrollBody, LibraryGate, px, flow_buttons


class Training(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(24, 18, 24, 16))
        self.owner = owner
        self.context, self.saves, self.rows = None, [], []
        self.active, self.photo, self.loaded = None, None, False
        self.food_session = food.Session(self.food_changed)
        self.content = ScrollBody(self, background=BG, autohide=True, stretch=True)
        self.content.pack(fill="both", expand=True)
        content = self.content.body
        top = surface(content, 12)
        top.pack(fill='x')
        ttk.Label(top, text='目标存档', style='Surface.TLabel').pack(side='left', padx=(0, 12))
        self.savebox = ttk.Combobox(top, state='readonly', font=(FONT, 10))
        self.savebox.pack(side='left', fill='x', expand=True)
        self.savebox.bind('<<ComboboxSelected>>', lambda e: self.load_selected())
        self.refresh_button = ttk.Button(top, text='刷新存档', command=self.refresh)
        self.refresh_button.pack(side='left', padx=(10, 0))
        self.live_button = ttk.Button(top, text='读取当前游戏', command=self.load_live)
        self.live_button.pack(side='left', padx=(10, 0))
        self.source_hint = tk.StringVar(value='选择存档可修改培养；读取当前游戏可直接指定餐券人物，无需保存。')
        source_label = ttk.Label(content, textvariable=self.source_hint, style='Hint.TLabel')
        source_label.pack(fill='x', pady=(9, 12))
        source_label.bind('<Configure>', lambda e: source_label.configure(wraplength=max(1, e.width)))

        center = tk.PanedWindow(content, orient='horizontal', bg=BG, borderwidth=0,
                               sashwidth=12, opaqueresize=True, height=px(self, 380))
        center.pack(fill='both', expand=True)
        left = ttk.Frame(center, width=px(self, 310))
        center.add(left, minsize=px(self, 100), stretch='never')
        self.query = tk.StringVar()
        self.search = ttk.Entry(left, textvariable=self.query)
        self.search.pack(fill='x', pady=(0, 10))
        self.query.trace_add('write', lambda *a: self.filter())
        self.summary = ttk.Label(left, text='搜索人物名或阵营', style='Hint.TLabel')
        self.summary.pack(anchor='w', pady=(0, 8))
        body = ttk.Frame(left)
        body.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(body, columns=('name', 'star', 'story'), show='headings', selectmode='browse')
        for key, name, width in [('name', '人物', 130), ('star', '★等级', 65), ('story', '故事', 70)]:
            self.tree.heading(key, text=name)
            self.tree.column(key, width=px(self, width), minwidth=px(self, 45), stretch=key == 'name')
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        horizontal = ttk.Scrollbar(body, orient='horizontal', command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.select_character)

        right = surface(center, 16)
        center.add(right, minsize=px(self, 100), stretch='always')
        self.detail_scroll = ScrollBody(right)
        self.detail_scroll.pack(fill='both', expand=True)
        detail = self.detail_scroll.body
        self.title = ttk.Label(detail, text='选择人物查看培养与餐券故事', style='CardTitle.TLabel')
        self.title.pack(anchor='w', pady=(0, 12))
        def layout_panes(event):
            vertical = event.width < px(self, 780)
            orientation = 'vertical' if vertical else 'horizontal'
            if str(center.cget('orient')) != orientation:
                center.configure(orient=orientation, height=px(self, 500 if vertical else 380))
                left.pack_propagate(not vertical)
                left.configure(height=px(self, 180) if vertical else 0)
                center.sash_place(0, px(self, 310), px(self, 180))
        center.bind('<Configure>', layout_panes)
        header = ttk.Frame(detail, style='Surface.TFrame')
        header.pack(fill='x')
        self.preview = ttk.Label(header, style='Surface.TLabel')
        self.preview.pack(side='left', padx=(0, 16))
        text = ttk.Frame(header, style='Surface.TFrame')
        text.pack(side='left', fill='x', expand=True)
        self.stats = ttk.Label(text, text='', style='Surface.TLabel', justify='left')
        self.stats.pack(anchor='w', pady=(0, 12))
        ttk.Label(text, text='已持有的卡牌版本', style='SurfaceHint.TLabel').pack(anchor='w', pady=(0, 6))
        self.variant = ttk.Combobox(text, state='readonly', width=18)
        self.variant.pack(fill='x')
        self.variant.bind('<<ComboboxSelected>>', lambda e: self.show_card())

        ttk.Separator(detail).pack(fill='x', pady=16)
        ttk.Label(detail, text='人物★等级 · 所有版本共享', style='CardTitle.TLabel').pack(anchor='w')
        row = ttk.Frame(detail, style='Surface.TFrame')
        row.pack(fill='x', pady=(10, 6))
        self.star = tk.IntVar(value=50)
        self.star_spin = ttk.Spinbox(row, from_=1, to=200, textvariable=self.star, width=5)
        self.star_spin.pack(side='left')
        self.star_button = ttk.Button(row, text='备份并提高★', style='Primary.TButton', command=lambda: self.apply('star'))
        self.star_button.pack(side='left', padx=(12, 0))
        ttk.Label(detail, text='提高★会清空本级经验，并重设升级门槛。最高200。',
                  style='SurfaceHint.TLabel', wraplength=530).pack(anchor='w')

        ttk.Separator(detail).pack(fill='x', pady=16)
        self.enhancement_title = ttk.Label(detail, text='同卡强化 · 只影响所选版本', style='CardTitle.TLabel')
        self.enhancement_title.pack(anchor='w')
        row = ttk.Frame(detail, style='Surface.TFrame')
        row.pack(fill='x', pady=(10, 6))
        self.enhancement = tk.IntVar(value=1)
        self.enhancement_spin = ttk.Spinbox(row, from_=1, to=10, textvariable=self.enhancement, width=5)
        self.enhancement_spin.pack(side='left')
        self.enhancement_button = ttk.Button(row, text='备份并提高强化', command=lambda: self.apply('enhancement'))
        self.enhancement_button.pack(side='left', padx=(12, 0))
        ttk.Label(detail, text='直接增加重复卡的强化，不增加编队卡牌总数。最高+10。',
                  style='SurfaceHint.TLabel', wraplength=530).pack(anchor='w')

        ttk.Separator(detail).pack(fill='x', pady=16)
        ttk.Label(detail, text='餐券小故事 · 进度与条件', style='CardTitle.TLabel').pack(anchor='w')
        self.story_text = ttk.Label(detail, text='选择人物后查看。', style='Surface.TLabel', justify='left', wraplength=530)
        self.story_text.pack(fill='x', pady=(10, 8))
        ttk.Label(detail, text='先在游戏中读档，再点“读取当前游戏”并指定人物。再次读档后需要重新指定。',
                  style='SurfaceHint.TLabel', wraplength=530).pack(anchor='w')
        row = ttk.Frame(detail, style='Surface.TFrame')
        row.pack(fill='x', pady=(0, 10))
        self.food_button = ttk.Button(row, text='指定战后餐券人物', style='Primary.TButton', command=self.arm_food)
        self.cancel_food_button = ttk.Button(row, text='取消指定', command=self.cancel_food)
        flow_buttons(row, [self.food_button, self.cancel_food_button])
        self.food_status = ttk.Label(detail, text=self.food_session.state['message'], style='Surface.TLabel',
                                     wraplength=530, justify='left')
        self.food_status.pack(anchor='w', pady=(0, 8))
        ttk.Label(detail, text='请在战斗结束前指定；已生成的候选不会即时替换。指定期间只出现这个人物。'
                  '没有符合条件的下一段故事时仍不会出现。取消、换档或关闭工具后恢复随机；地图餐券不受影响。'
                  '更换游戏目录后，请先准备该游戏的人物资料。',
                  style='SurfaceHint.TLabel', wraplength=530).pack(anchor='w')
        self.detail_scroll.bind_children()
        self.detail_scroll.body.bind('<Configure>', self.wrap_detail, add='+')
        def bind_outer(widget):
            widget.bind('<MouseWheel>', self.content.wheel)
            for child in widget.winfo_children():
                bind_outer(child)
        for area in [top, source_label]:
            bind_outer(area)
        self.gate = LibraryGate(self, self.content, owner, self.refresh)
        self.update_actions()
        self.after(200, self.poll_food)

    def wrap_detail(self, event):
        width = max(1, event.width - 6)
        if getattr(self, '_detail_wrap_width', None) == width:
            return
        self._detail_wrap_width = width
        for widget in self.detail_scroll.body.winfo_children():
            if isinstance(widget, ttk.Label) and (widget is self.title or int(widget.cget('wraplength') or 0) > 0):
                widget.configure(wraplength=width)

    def poll_food(self):
        self.food_session.poll()
        self.after(200, self.poll_food)

    def food_changed(self, state):
        if state.get('revision', 0) < self.food_session.state.get('revision', 0):
            state = self.food_session.state
        self.food_status.configure(text=state['message'], foreground=GREEN if state.get('success', True) else MUTED)
        self.owner.numbers.update_story(state)
        self.update_actions()

    def arm_food(self):
        if self.active and not self.owner.busy:
            target = self.active
            self.owner.run(lambda: self.food_session.arm(target), self.food_changed,
                           '正在指定战后餐券人物…')

    def load_live(self):
        if not self.owner.busy:
            self.owner.run(self.food_session.inspect, self.live_loaded, '正在读取当前游戏人物与故事进度…')

    def live_loaded(self, context):
        self.gate.ready()
        self.loaded = True
        self.savebox.set('当前运行进度 · 餐券人物')
        self.source_hint.set('当前游戏名单。餐券指定即时生效；修改★或强化请另选存档。')
        self.context = context
        self.rows = context['training_cards']
        self.filter()
        with_story = sum(bool(rows[0]['story'] and rows[0]['story']['maximum']) for rows in self.characters.values())
        self.owner.status.configure(text='已读取当前游戏：%d 位人物，%d 位有餐券故事资料。' % (len(self.characters), with_story))
        self.update_actions()
        self.detail_scroll.see(self.food_button)

    def cancel_food(self):
        if not self.owner.busy:
            self.owner.run(self.food_session.cancel, self.food_changed, '正在恢复随机餐券候选…')

    def invalidate(self):
        self.gate.ready()
        self.context, self.saves, self.rows = None, [], []
        self.active, self.photo, self.loaded = None, None, False
        self.savebox['values'] = []
        self.savebox.set('')
        self.tree.delete(*self.tree.get_children())
        self.variant['values'] = []
        self.variant.set('')
        self.preview.configure(image='')
        self.stats.configure(text='')
        self.title.configure(text='选择人物查看培养与餐券故事')
        self.story_text.configure(text='请选择人物。')
        self.update_actions()

    def refresh(self):
        self.context = None
        self.loaded = True
        if not app_paths.CATALOG_FILE.exists() or not app_paths.CHARACTER_FILE.exists():
            missing = '人物资料' if app_paths.CATALOG_FILE.exists() else '卡牌图鉴和人物资料'
            self.gate.show('当前缺少' + missing + '。点击“前往准备图鉴”；已有图鉴可只点击“更新人物资料”。')
            return
        self.gate.ready()
        def work():
            engine.catalog()
            return engine.list_saves()
        self.owner.run(work, self.saves_loaded, '正在读取培养存档列表…', self.load_failed)

    def load_failed(self, message):
        self.context = None
        self.gate.show('读取人物培养未完成：' + message)

    def saves_loaded(self, saves):
        old = self.context['path'] if self.context else None
        self.saves = [s for s in saves if not s.get('error')]
        self.loaded = True
        self.savebox['values'] = [('%d号' % s['slot'] if s['manual'] else '自动%d（只读）' % (s['slot'] - 5000))
                                  + ' | ' + s['time'] + ' | %d张' % s['count'] for s in self.saves]
        if not self.saves:
            self.invalidate()
            self.loaded = True
            self.owner.status.configure(text='没有找到可读取的存档。')
            return
        index = next((i for i, s in enumerate(self.saves) if s['path'] == old), 0)
        self.savebox.current(index)
        self.load_selected()

    def load_selected(self):
        index = self.savebox.current()
        if index < 0 or self.owner.busy:
            return
        path = self.saves[index]['path']
        self.context = None
        self.update_actions()
        self.owner.run(lambda: training.inspect(path), self.context_loaded, '正在读取人物培养与餐券进度…', self.load_failed)

    def context_loaded(self, context):
        self.context = context
        self.source_hint.set('当前名单来自存档。培养修改须重新读档；餐券指定会另外核对当前游戏。')
        self.rows = context['training_cards']
        self.filter()
        self.owner.status.configure(text='%d号存档 · 人物培养与餐券故事已读取。' % context['slot'])
        self.update_actions()

    def filter(self):
        keep = self.active
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().strip().casefold()
        self.characters = {}
        for row in self.rows:
            if query and query not in (row['character'] + row['faction'] + row['id']).casefold():
                continue
            self.characters.setdefault(row['character'], []).append(row)
        for name, rows in self.characters.items():
            r = rows[0]
            story = r['story']
            self.tree.insert('', 'end', iid=name, values=(name, r['star'],
                             '%d/%d' % (story['completed'], story['maximum']) if story else '资料缺失'))
        self.summary.configure(text='%d 位持有人物' % len(self.characters))
        if self.characters:
            name = keep if keep in self.characters else next(iter(self.characters))
            self.tree.selection_set(name)
            self.tree.focus(name)
            self.select_character()
        else:
            self.active = None
            self.photo = None
            self.preview.configure(image='')
            self.stats.configure(text='')
            self.variant['values'] = []
            self.variant.set('')
            self.title.configure(text='没有匹配的人物')
            self.story_text.configure(text='')
            self.update_actions()

    def select_character(self, event=None):
        selection = self.tree.selection()
        if not selection or selection[0] not in self.characters:
            return
        name = selection[0]
        changed = name != self.active
        old_variant = self.variant.get()
        self.active = name
        rows = self.characters[name]
        self.variant['values'] = [r['id'] for r in rows]
        if old_variant in self.variant['values'] and not changed:
            self.variant.set(old_variant)
        else:
            self.variant.current(0)
        row = rows[0]
        self.title.configure(text=name + '  /  ' + row['faction'])
        self.stats.configure(text='人物 ★%d\n本级经验  %d / %d\n持有 %d 个卡牌版本' %
                             (row['star'], row['exp'], row['next_exp'], len(rows)))
        self.star.set(min(200, row['star'] + 5))
        info = row['story']
        if info:
            lines = []
            for event in info['rows']:
                condition = event['condition']
                label = '无额外剧情条件' if condition == '条件成立' else condition
                lines.append('%s  %s%s' % (event['letter'], event['state'],
                             ('\n    条件：' + label) if event['state'] != '无此故事' else ''))
            self.story_text.configure(text='\n\n'.join(lines))
        else:
            self.story_text.configure(text='本机游戏数据中未找到这个人物的餐券故事资料，不能指定。')
        self.show_card()
        if changed:
            self.detail_scroll.reset()

    def show_card(self):
        row = self.card()
        if not row:
            return
        self.photo = self.owner.images.get(row['id'], (96, 144))
        self.preview.configure(image=self.photo or '', text='' if self.photo else '暂无卡面')
        summary = '人物 ★%d\n本级经验  %d / %d\n持有 %d 个卡牌版本' % (
            row['star'], row['exp'], row['next_exp'], len(self.characters[self.active]))
        if row['overridden']:
            summary += '\n此版本有临时等级覆盖，游戏显示可能不同。'
        self.stats.configure(text=summary)
        self.enhancement_title.configure(text='同卡强化 · 当前 +%d' % row['enhancement'])
        self.enhancement.set(min(10, row['enhancement'] + 1))
        self.update_actions()

    def card(self):
        return next((r for r in self.rows if r['id'] == self.variant.get()), None)

    def update_actions(self):
        if hasattr(self, 'gate'):
            self.gate.update_actions()
        busy, context = self.owner.busy, self.context
        self.refresh_button.configure(state='disabled' if busy else 'normal')
        self.live_button.configure(state='disabled' if busy else 'normal')
        self.savebox.configure(state='disabled' if busy else 'readonly')
        self.variant.configure(state='disabled' if busy else 'readonly')
        can_write = bool(context and context['manual'] and not context['pending'] and self.card() and not busy)
        self.star_button.configure(state='normal' if can_write else 'disabled')
        self.enhancement_button.configure(state='normal' if can_write else 'disabled')
        self.food_button.configure(state='normal' if self.active and not busy else 'disabled')
        self.cancel_food_button.configure(state='normal' if self.food_session.state.get('armed') and not busy else 'disabled')

    def apply(self, kind):
        row = self.card()
        if not row or self.owner.busy or not self.context:
            return
        try:
            value = self.star.get() if kind == 'star' else self.enhancement.get()
        except tk.TclError:
            messagebox.showerror('数值无效', '请输入整数。', parent=self)
            return
        before = row['star'] if kind == 'star' else row['enhancement']
        cap = self.context['star_cap'] if kind == 'star' else self.context['enhancement_cap']
        if not before < value <= cap:
            messagebox.showerror('数值无效', '请设置比当前值更高的整数，最高%d。' % cap, parent=self)
            return
        target = row['character'] if kind == 'star' else row['id']
        slot, path, sha = self.context['slot'], self.context['path'], self.context['sha']
        detail = ('人物★：%d → %d\n同一人物所有版本共享；本级经验将清零。' % (before, value)
                  if kind == 'star' else '这张卡的强化：+%d → +%d\n不增加卡牌总数。' % (before, value))
        if not messagebox.askyesno('确认培养修改', '%d号存档\n%s\n\n%s\n\n先备份，再写入。完成后须重新读档，'
                                  '请勿从旧画面保存覆盖。' % (slot, target, detail), parent=self):
            return
        self.owner.run(lambda: training.apply(path, kind, target, value, sha), self.applied,
                       '正在备份并修改人物培养…')

    def applied(self, report):
        self.owner.backup = report['backup']
        self.owner.log(dict(report, time=datetime.datetime.now().isoformat(timespec='seconds')))
        self.owner.refresh_history()
        self.owner.cards.invalidate()
        messagebox.showinfo('培养修改已完成', '%s：%s → %s\n\n请重新读取%d号存档，'
                            '再打开编队查看数值。\n原档已备份，可在“记录与备份”中找到。' %
                            (report['target'], report['before'], report['after'], report['slot']), parent=self)
        self.load_selected()
