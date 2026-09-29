import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import datetime
import unicodedata
import engine
import app_paths
from gallery import Gallery
from ui_theme import BG, SURFACE, TEXT, MUTED, LINE, BLUE, TINT, GOLD, FONT, surface, ScrollBody


class Cards(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(24, 18, 24, 16))
        self.owner = owner
        self.context, self.saves, self.selected, self.visible = None, [], set(), []
        self.active, self.preview_photo, self.loaded = None, None, False

        row = surface(self, 12)
        row.pack(fill='x')
        ttk.Label(row, text='目标存档', style='Surface.TLabel').pack(side='left', padx=(0, 12))
        self.savebox = ttk.Combobox(row, state='readonly', font=(FONT, 10))
        self.savebox.pack(side='left', fill='x', expand=True)
        self.savebox.bind('<<ComboboxSelected>>', lambda e: self.load_selected())
        self.refresh_button = ttk.Button(row, text='刷新存档', command=self.refresh)
        self.refresh_button.pack(side='left', padx=(10, 0))
        self.hint = ttk.Label(self, text='先保存到手动存档位，添加卡牌后重新读档生效。',
                              style='Hint.TLabel', wraplength=990)
        self.hint.pack(fill='x', pady=(9, 12))

        row = ttk.Frame(self)
        row.pack(fill='x', pady=(0, 12))
        self.count_text = tk.StringVar(value='选择存档，查看持有卡牌')
        ttk.Label(row, textvariable=self.count_text, style='Summary.TLabel').pack(side='left')
        goalbox = ttk.Frame(row)
        goalbox.pack(side='right')
        ttk.Label(goalbox, text='目标数量', style='Hint.TLabel').pack(side='left', padx=(0, 8))
        self.goal_value = tk.IntVar(value=200)
        self.goal_spin = ttk.Spinbox(goalbox, from_=1, to=600, textvariable=self.goal_value, width=5, font=(FONT, 10))
        self.goal_spin.pack(side='left')
        self.goal_value.trace_add('write', lambda *a: self.update_actions())

        filters = ttk.Frame(self)
        filters.pack(fill='x', pady=(0, 6))
        filters.columnconfigure(0, weight=1)
        self.query = tk.StringVar()
        self.search = ttk.Entry(filters, textvariable=self.query, font=(FONT, 11), width=25)
        self.search.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.query.trace_add('write', lambda *a: self.filter())
        self.faction = tk.StringVar(value='全部阵营')
        self.factionbox = ttk.Combobox(filters, values=['全部阵营'] + engine.ORG_NAMES[1:],
                       textvariable=self.faction, state='readonly', width=10, font=(FONT, 10))
        self.factionbox.grid(row=0, column=1, padx=(0, 10))
        self.factionbox.bind('<<ComboboxSelected>>', lambda e: self.filter())
        self.rarity = tk.StringVar(value='全部稀有度')
        self.raritybox = ttk.Combobox(filters, values=['全部稀有度', '普通', '特级', '超稀有'],
                       textvariable=self.rarity, state='readonly', width=10, font=(FONT, 10))
        self.raritybox.grid(row=0, column=2, padx=(0, 10))
        self.raritybox.bind('<<ComboboxSelected>>', lambda e: self.filter())
        self.version = tk.StringVar(value='全部版本')
        self.versionbox = ttk.Combobox(filters, values=['全部版本', 'Lv版本', '其他版本'],
                       textvariable=self.version, state='readonly', width=9, font=(FONT, 10))
        self.versionbox.grid(row=0, column=3)
        self.versionbox.bind('<<ComboboxSelected>>', lambda e: self.filter())
        checks = ttk.Frame(self)
        checks.pack(fill='x', pady=(0, 10))
        ttk.Label(checks, text='卡名 / 技能', style='Hint.TLabel').pack(side='left', padx=(0, 18))
        self.only_missing = tk.BooleanVar(value=False)
        self.only_available = tk.BooleanVar(value=False)
        self.only_selected = tk.BooleanVar(value=False)
        for text, var in [('仅未持有', self.only_missing), ('仅可添加', self.only_available), ('已选清单', self.only_selected)]:
            ttk.Checkbutton(checks, text=text, variable=var, command=self.filter).pack(side='left', padx=(0, 14))
        self.mode = tk.StringVar(value='卡图')
        modebox = ttk.Combobox(checks, values=['卡图', '列表'], textvariable=self.mode, state='readonly', width=5, font=(FONT, 10))
        modebox.pack(side='right')
        modebox.bind('<<ComboboxSelected>>', lambda e: self.switch_view())

        actions = ttk.Frame(self)
        actions.pack(side='bottom', fill='x', pady=(12, 0))
        buttons = ttk.Frame(actions)
        buttons.pack(fill='x')
        self.suggest_button = ttk.Button(buttons, text='选卡补到目标', command=self.suggest)
        self.suggest_button.pack(side='left')
        self.clear_button = ttk.Button(buttons, text='清空勾选', command=self.clear)
        self.clear_button.pack(side='left', padx=(8, 0))
        self.apply_button = ttk.Button(buttons, text='备份并添加', style='Primary.TButton', command=self.apply)
        self.apply_button.pack(side='right')
        self.result_text = ttk.Label(actions, text='点击卡图查看技能；点击方框或双击卡图勾选。', style='Hint.TLabel')
        self.result_text.pack(anchor='w', pady=(8, 0))

        center = ttk.Panedwindow(self, orient='horizontal')
        center.pack(fill='both', expand=True)
        self.left = ttk.Frame(center)
        center.add(self.left, weight=1)
        self.gallery = Gallery(self.left, owner.images, self.detail, self.toggle)
        self.gallery.pack(fill='both', expand=True)
        self.list_frame = ttk.Frame(self.left)
        cols = ('check', 'name', 'rarity', 'faction', 'star', 'owned')
        self.tree = ttk.Treeview(self.list_frame, columns=cols, show='headings', selectmode='browse')
        for key, label, width in [('check', '选', 40), ('name', '卡牌', 210), ('rarity', '稀有度', 78),
                                  ('faction', '阵营', 78), ('star', '星级', 54), ('owned', '状态', 96)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=width, stretch=key == 'name',
                             anchor='center' if key in ['check', 'star', 'rarity', 'owned'] else 'w')
        scrollbar = ttk.Scrollbar(self.list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.tag_configure('checked', background=TINT)
        self.tree.tag_configure('owned', foreground='#8a96a7')
        self.tree.tag_configure('unavailable', foreground='#8a96a7')
        self.tree.bind('<<TreeviewSelect>>', self.list_detail)
        self.tree.bind('<Button-1>', self.list_click)
        self.tree.bind('<Double-1>', self.list_double)
        self.tree.bind('<space>', self.list_space)

        right = surface(center, 16)
        right.configure(width=252)
        right.pack_propagate(False)
        center.add(right, weight=0)
        self.choose_button = ttk.Button(right, text='选入清单', command=self.choose_active)
        self.choose_button.pack(side='bottom', fill='x', pady=(10, 0))
        self.detail_scroll = ScrollBody(right)
        self.detail_scroll.pack(fill='both', expand=True)
        detailbody = self.detail_scroll.body
        self.title = ttk.Label(detailbody, text='选择卡牌查看详情', style='CardTitle.TLabel', wraplength=194, anchor='center', justify='center')
        self.title.pack(fill='x', pady=(0, 10))
        self.card_hint = ttk.Label(detailbody, text='点击卡图看详情。', style='SurfaceHint.TLabel', wraplength=194, anchor='center', justify='center')
        self.card_hint.pack(fill='x', pady=(8, 8))
        self.preview = ttk.Label(detailbody, anchor='center', style='Surface.TLabel')
        self.preview.pack(fill='x')
        self.details = ttk.Label(detailbody, text='', style='Surface.TLabel', wraplength=194, justify='left', anchor='nw')
        self.details.pack(fill='x', pady=(14, 0))
        self.detail_scroll.bind_children()
        self.bind('<Configure>', lambda e: self.hint.configure(wraplength=max(400, e.width - 48)))
        self.update_actions()

    def refresh(self):
        if not app_paths.CATALOG_FILE.exists():
            self.owner.status.configure(text='请在“设置与图鉴”中先准备卡牌图鉴。')
            self.owner.tabs.select(self.owner.setup)
            return
        def work():
            engine.check_version()
            return engine.list_saves()
        self.owner.run(work, self.saves_loaded, '正在读取存档列表…')

    def invalidate(self):
        self.context, self.saves, self.selected, self.visible = None, [], set(), []
        self.active, self.loaded, self.preview_photo = None, False, None
        self.savebox['values'] = []
        self.savebox.set('')
        self.tree.delete(*self.tree.get_children())
        self.gallery.set_cards([], set())
        self.preview.configure(image='')
        self.details.configure(text='')
        self.title.configure(text='选择卡牌查看详情')
        self.card_hint.configure(text='请刷新目标存档。')
        self.count_text.set('选择存档，查看持有卡牌')
        self.update_actions()

    def saves_loaded(self, saves):
        self.loaded = True
        self.saves = [s for s in saves if not s.get('error')]
        labels = []
        for s in self.saves:
            name = '%d号' % s['slot'] if s['manual'] else '自动%d（只读）' % (s['slot'] - 5000)
            labels.append('%s | %s | %d张 | %s' % (name, s['time'], s['count'], s['comment'].replace('\n', ' ')))
        self.savebox['values'] = labels
        if not labels:
            self.context = None
            self.owner.status.configure(text='没有找到可用存档，请先在游戏中保存。')
            return
        idx = next((i for i, s in enumerate(self.saves) if s['manual']), 0)
        self.savebox.current(idx)
        self.load_selected()

    def load_selected(self):
        idx = self.savebox.current()
        if idx < 0 or self.owner.busy:
            return
        self.context = None
        self.selected.clear()
        self.owner.run(lambda: engine.inspect(self.saves[idx]['path']), self.context_loaded, '正在读取目标存档的卡牌…')

    def context_loaded(self, context):
        self.context, self.selected, self.active = context, set(), None
        self.only_selected.set(False)
        if context['manual']:
            text = '目标：%d号（%s）。添加后请重新读取这个存档；游玩中未保存的进度不在这里。' % (context['slot'], context['time'])
        else:
            text = '自动存档仅供查看。请保存到空的手动存档位，再点“刷新存档”。'
        self.hint.configure(text=text)
        self.filter()
        if self.visible:
            self.detail(self.visible[0])

    def goal(self):
        try:
            return min(600, max(1, int(self.goal_value.get())))
        except (ValueError, tk.TclError):
            return 200

    def filter(self):
        if not self.context:
            return
        q = unicodedata.normalize('NFKC', self.query.get().strip()).casefold()
        result = []
        for r in self.context['cards']:
            if self.only_selected.get():
                if r['id'] not in self.selected:
                    continue
            else:
                if self.only_missing.get() and r['owned']:
                    continue
                if self.only_available.get() and not r['available']:
                    continue
                if self.rarity.get() != '全部稀有度' and r['rarity'] != self.rarity.get():
                    continue
                if self.version.get() == 'Lv版本' and not r['basic']:
                    continue
                if self.version.get() == '其他版本' and r['basic']:
                    continue
                if self.faction.get() != '全部阵营' and r['faction'] != self.faction.get():
                    continue
                if q and q not in unicodedata.normalize('NFKC', r['id'] + ' ' + r['skills'] + ' ' + r['details']).casefold():
                    continue
            result.append(r)
        self.visible = result
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(result):
            checked = r['id'] in self.selected
            status = '已持有' if r['owned'] else ('可添加' if r['available'] else '暂不可加')
            self.tree.insert('', 'end', iid=str(i), values=('☑' if checked else ('—' if r['owned'] or not r['available'] else '☐'),
                            r['id'], r['rarity'], r['faction'], r['star'], status),
                             tags=('owned',) if r['owned'] else (('unavailable',) if not r['available'] else (('checked',) if checked else ())))
        self.gallery.set_cards(result, self.selected, self.active)
        self.result_text.configure(text='显示 %d 张  ·  特级 %d 张  ·  超稀有 %d 张  ·  当前可添加 %d 张' %
                                  (len(result), sum(r['rarity'] == '特级' for r in result),
                                   sum(r['rarity'] == '超稀有' for r in result),
                                   sum(r['available'] and not r['owned'] for r in result)))
        if result:
            self.detail(next((r for r in result if r['id'] == self.active), result[0]))
        else:
            self.active, self.preview_photo = None, None
            self.title.configure(text='没有匹配的卡牌')
            self.preview.configure(image='')
            self.card_hint.configure(text='调整搜索词或筛选条件。')
            self.details.configure(text='')
        self.update_actions()

    def switch_view(self):
        self.gallery.pack_forget()
        self.list_frame.pack_forget()
        (self.gallery if self.mode.get() == '卡图' else self.list_frame).pack(fill='both', expand=True)

    def detail(self, r):
        changed = self.active != r['id']
        self.active = r['id']
        self.title.configure(text=r['id'])
        self.preview_photo = self.owner.images.get(r['id'], (176, 264))
        self.preview.configure(image=self.preview_photo if self.preview_photo else '')
        self.card_hint.configure(text='%s  ·  %s  ·  ★%s\n%s' % (r['rarity'], r['faction'], r['star'],
                                '已持有' if r['owned'] else ('可以添加' if r['available'] else '暂不可添加')))
        text = '基础HP %s   基础AT %s\n\n%s\n\n%s' % (r['hp'], r['atk'], r['details'],
               '沿用角色当前培养星级。' if r['available'] else r['unavailable_reason'])
        if r['appearance'] == 3:
            text += '\n\n特殊出现版本，请按需单独选择。'
        self.details.configure(text=text)
        if changed:
            self.detail_scroll.reset()
        self.gallery.active = r['id']
        self.gallery.schedule()
        self.update_actions()

    def choose_active(self):
        r = next((r for r in self.visible if r['id'] == self.active), None)
        if r:
            self.toggle(r)

    def toggle(self, r):
        if self.owner.busy or r['owned']:
            return
        if not r['available']:
            self.owner.status.configure(text=r['unavailable_reason'])
            return
        if r['id'] in self.selected:
            self.selected.remove(r['id'])
        else:
            if len(self.selected) >= 200:
                self.owner.status.configure(text='单次最多添加200张，请减少勾选。')
                return
            self.selected.add(r['id'])
        self.detail(r)
        if self.only_selected.get():
            self.filter()
        else:
            for i, row in enumerate(self.visible):
                if row['id'] == r['id']:
                    checked = r['id'] in self.selected
                    self.tree.set(str(i), 'check', '☑' if checked else '☐')
                    self.tree.item(str(i), tags=('checked',) if checked else ())
                    break
            self.gallery.set_cards(self.visible, self.selected, self.active, reset=False)
            self.update_actions()

    def list_detail(self, event=None):
        selected = self.tree.selection()
        if selected and int(selected[0]) < len(self.visible):
            self.detail(self.visible[int(selected[0])])

    def list_click(self, event):
        if self.tree.identify_column(event.x) == '#1':
            iid = self.tree.identify_row(event.y)
            if iid:
                self.toggle(self.visible[int(iid)])

    def list_double(self, event):
        if self.tree.identify_column(event.x) != '#1':
            iid = self.tree.identify_row(event.y)
            if iid:
                self.toggle(self.visible[int(iid)])

    def list_space(self, event):
        if self.tree.selection():
            self.toggle(self.visible[int(self.tree.selection()[0])])
        return 'break'

    def suggest(self):
        if not self.context or self.owner.busy:
            return
        ids = engine.suggest(self.context, self.goal(), self.selected)[:max(0, 200 - len(self.selected))]
        self.selected.update(ids)
        self.only_selected.set(True)
        self.filter()
        if self.visible:
            self.detail(self.visible[0])
        self.owner.status.configure(text='已勾选%d张，尚未写入。可以查看图片、取消或换选。' % len(self.selected))

    def clear(self):
        if self.owner.busy:
            return
        self.selected.clear()
        self.only_selected.set(False)
        self.filter()

    def update_actions(self):
        if not hasattr(self, 'apply_button'):
            return
        c, busy = self.context, self.owner.busy
        self.refresh_button.configure(state='disabled' if busy else 'normal')
        self.savebox.configure(state='disabled' if busy else 'readonly')
        self.suggest_button.configure(state='normal' if c and not busy else 'disabled')
        self.clear_button.configure(state='disabled' if busy else 'normal')
        if hasattr(self, 'choose_button'):
            card = next((r for r in self.visible if r['id'] == self.active), None)
            can_choose = bool(card and card['available'] and not card['owned'] and not busy)
            label = ('移出清单' if card and card['id'] in self.selected else '选入清单')
            if card and (card['owned'] or not card['available']):
                label = '已持有' if card['owned'] else '暂不可添加'
            self.choose_button.configure(state='normal' if can_choose else 'disabled', text=label)
        ready = bool(c and c['manual'] and not c['pending'] and self.selected and not busy)
        self.apply_button.configure(state='normal' if ready else 'disabled', text='备份并添加 %d 张' % len(self.selected))
        if c:
            after = c['count'] + len(self.selected)
            self.count_text.set('存档 %d 张  ·  已选 %d 张  →  %d 张' % (c['count'], len(self.selected), after))

    def apply(self):
        if not self.context or self.owner.busy or not self.selected:
            return
        c = self.context
        ids = [r['id'] for r in c['cards'] if r['id'] in self.selected]
        self.owner.run(lambda: engine.apply(c['path'], ids, c['sha']), self.applied, '正在备份、添加并校验存档…')

    def applied(self, report):
        self.owner.backup = report['backup']
        self.owner.log(dict(action='cards', time=datetime.datetime.now().isoformat(timespec='seconds'),
                            slot=self.context['slot'], before=report['before_count'], after=report['after_count'],
                            backup=report['backup'], cards=[x['card'] for x in report['cards']]))
        self.owner.refresh_history()
        self.selected.clear()
        slot = self.context['slot']
        messagebox.showinfo('卡牌已添加', '%d → %d张\n\n请退出再进入游戏读档菜单，重新读取%d号。\n'
                            '直接在旧游戏画面中保存，会把旧数据写回来。\n\n原档已备份，可在“记录与备份”查看。' %
                            (report['before_count'], report['after_count'], slot), parent=self)
        self.load_selected()
