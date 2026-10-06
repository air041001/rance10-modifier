import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import datetime
import unicodedata
import engine
import app_paths
from gallery import Gallery
from ui_theme import BG, SURFACE, TEXT, MUTED, LINE, BLUE, TINT, GOLD, FONT, surface, ScrollBody, LibraryGate, px, flow_buttons


class Cards(ttk.Frame):
    def __init__(self, master, owner):
        super().__init__(master, padding=(20, 16))
        self.owner = owner
        self.context, self.saves, self.selected, self.visible = None, [], set(), []
        self.active, self.preview_photo, self.loaded = None, None, False
        self.content = ScrollBody(self, background=BG, autohide=True, stretch=True)
        self.content.pack(fill="both", expand=True)
        content = self.content.body

        row = surface(content, 12)
        row.pack(fill='x')
        ttk.Label(row, text='目标存档', style='Surface.TLabel').pack(side='left', padx=(0, 12))
        self.savebox = ttk.Combobox(row, state='readonly', font=(FONT, 10))
        self.savebox.pack(side='left', fill='x', expand=True)
        self.savebox.bind('<<ComboboxSelected>>', lambda e: self.load_selected())
        self.refresh_button = ttk.Button(row, text='刷新存档', command=self.refresh)
        self.refresh_button.pack(side='left', padx=(10, 0))
        self.hint = ttk.Label(content, text='先保存到手动存档位，添加卡牌后重新读档生效。',
                              style='Hint.TLabel', wraplength=990)
        self.hint.pack(fill='x', pady=(9, 12))

        row = ttk.Frame(content)
        row.pack(fill='x', pady=(0, 12))
        self.count_text = tk.StringVar(value='选择存档，查看持有卡牌')
        ttk.Label(row, textvariable=self.count_text, style='Summary.TLabel').pack(side='left')
        goalbox = ttk.Frame(row)
        goalbox.pack(side='right')
        ttk.Label(goalbox, text='目标数量', style='Hint.TLabel').pack(side='left', padx=(0, 8))
        self.goal_value = tk.IntVar(value=200)
        self.goal_spin = ttk.Spinbox(goalbox, from_=1, to=984, textvariable=self.goal_value, width=5, font=(FONT, 10))
        self.goal_spin.pack(side='left')
        self.goal_value.trace_add('write', lambda *a: self.update_actions())

        filters = ttk.Frame(content)
        self.filters = filters
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
        extra = ttk.Frame(filters)
        self.extra_filters = extra
        extra.grid(row=1, column=0, columnspan=4, sticky='w', pady=(8, 0))
        self.kind = tk.StringVar(value='全部类型')
        self.kindbox = ttk.Combobox(extra, values=['全部类型', '人物', '通用', '物品'],
                       textvariable=self.kind, state='readonly', width=10, font=(FONT, 10))
        self.kindbox.pack(side='left', padx=(0, 10))
        self.kindbox.bind('<<ComboboxSelected>>', lambda e: self.filter())
        self.appearance = tk.StringVar(value='全部范围')
        self.appearancebox = ttk.Combobox(extra, values=['全部范围', '第一部及特殊', '第二部', '特殊出现'],
                       textvariable=self.appearance, state='readonly', width=14, font=(FONT, 10))
        self.appearancebox.pack(side='left')
        self.appearancebox.bind('<<ComboboxSelected>>', lambda e: self.filter())
        filters.bind('<Configure>', self.layout_filters)
        checks = ttk.Frame(content)
        checks.pack(fill='x', pady=(0, 10))
        check_controls = [ttk.Label(checks, text='卡名 / 技能', style='Hint.TLabel')]
        self.only_missing = tk.BooleanVar(value=False)
        self.only_available = tk.BooleanVar(value=False)
        self.only_selected = tk.BooleanVar(value=False)
        for text, var in [('仅未持有', self.only_missing), ('仅可添加', self.only_available), ('已选清单', self.only_selected)]:
            check_controls.append(ttk.Checkbutton(checks, text=text, variable=var, command=self.filter))
        self.mode = tk.StringVar(value='卡图')
        modebox = ttk.Combobox(checks, values=['卡图', '列表'], textvariable=self.mode, state='readonly', width=5, font=(FONT, 10))
        flow_buttons(checks, check_controls + [modebox])
        modebox.bind('<<ComboboxSelected>>', lambda e: self.switch_view())

        actions = ttk.Frame(content)
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

        center = ttk.Panedwindow(content, orient='horizontal')
        self.center = center
        center.pack(fill='both', expand=True)
        self.left = ttk.Frame(center)
        center.add(self.left, weight=1)
        self.gallery = Gallery(self.left, owner.images, self.detail, self.toggle)
        self.gallery.pack(fill='both', expand=True)
        self.list_frame = ttk.Frame(self.left)
        cols = ('check', 'name', 'kind', 'rarity', 'faction', 'star', 'owned')
        self.tree = ttk.Treeview(self.list_frame, columns=cols, show='headings', selectmode='browse')
        for key, label, width in [('check', '选', 40), ('name', '卡牌', 190), ('kind', '类型', 54), ('rarity', '稀有度', 72),
                                  ('faction', '阵营', 78), ('star', '星级', 54), ('owned', '状态', 96)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=px(self, width), minwidth=px(self, width), stretch=key == 'name',
                             anchor='center' if key in ['check', 'star', 'rarity', 'owned'] else 'w')
        scrollbar = ttk.Scrollbar(self.list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        horizontal = ttk.Scrollbar(self.list_frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.tag_configure('checked', background=TINT)
        self.tree.tag_configure('owned', foreground=MUTED)
        self.tree.tag_configure('unavailable', foreground=MUTED)
        self.tree.bind('<<TreeviewSelect>>', self.list_detail)
        self.tree.bind('<Button-1>', self.list_click)
        self.tree.bind('<Double-1>', self.list_double)
        self.tree.bind('<space>', self.list_space)

        right = surface(center, 16)
        self.detail_panel = right
        right.configure(width=px(self, 252))
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
        detailbody.bind('<Configure>', lambda e: [label.configure(wraplength=max(1, e.width))
                        for label in [self.title, self.card_hint, self.details]])
        def layout_detail(event):
            # Keep at least one complete card visible; the detail text wraps
            # and scrolls when the display leaves less room for the right pane.
            minimum_left = self.gallery.W + self.gallery.scroll.winfo_reqwidth()
            right_width = min(px(self, 252), event.width - minimum_left - 12)
            right_width = max(self.choose_button.winfo_reqwidth() + 34, right_width)
            if event.width > minimum_left + right_width:
                center.sashpos(0, event.width - right_width - 12)
        center.bind('<Configure>', layout_detail)
        def bind_outer(widget):
            if widget is center:
                return  # Card grid and detail column keep their own scrolling.
            widget.bind('<MouseWheel>', self.content.wheel)
            for child in widget.winfo_children():
                bind_outer(child)
        bind_outer(content)
        self.bind('<Configure>', lambda e: self.hint.configure(wraplength=max(400, e.width - 48)))
        self.gate = LibraryGate(self, self.content, owner, self.refresh)
        self.update_actions()

    def theme_changed(self):
        self.tree.tag_configure('checked', background=TINT)
        self.tree.tag_configure('owned', foreground=MUTED)
        self.tree.tag_configure('unavailable', foreground=MUTED)
        self.gallery.canvas.configure(bg=BG)
        self.gallery.schedule()

    def layout_filters(self, event):
        boxes = [self.factionbox, self.raritybox, self.versionbox]
        width = event.width
        broad = width >= max(px(self, 820), sum(b.winfo_reqwidth()+10 for b in boxes) + px(self, 220))
        self.search.grid_configure(row=0, column=0, columnspan=1 if broad else 4,
                                   sticky='ew', padx=(0, 10 if broad else 0), pady=(0, 0 if broad else 8))
        row, column, used = (0, 1, px(self, 220)) if broad else (1, 0, 0)
        for box in boxes:
            size = box.winfo_reqwidth() + 10
            if not broad and used and used + size > width:
                row, column, used = row+1, 0, 0
            box.grid_configure(row=row, column=column, sticky='w', padx=(0, 10), pady=(0, 8))
            used, column = used + size, column+1
        self.extra_filters.grid_configure(row=row+1, columnspan=4, sticky='ew')
        for box in [self.kindbox, self.appearancebox]:
            box.pack_forget()
        extra_row, used = 0, self.kindbox.winfo_reqwidth() + 10
        self.kindbox.grid(row=0, column=0, sticky='w', padx=(0, 10))
        if used + self.appearancebox.winfo_reqwidth() > width:
            extra_row = 1
        self.appearancebox.grid(row=extra_row, column=1 if extra_row == 0 else 0, sticky='w', pady=(8 if extra_row else 0, 0))

    def refresh(self):
        self.context = None
        self.loaded = True
        if not app_paths.CATALOG_FILE.exists():
            self.gate.show('当前还没有可用的本机卡牌图鉴。点击“前往准备图鉴”，完成后再点“重新检查”。')
            return
        self.gate.ready()
        def work():
            engine.catalog()
            return engine.list_saves()
        self.owner.run(work, self.saves_loaded, '正在读取存档列表…', self.load_failed)

    def load_failed(self, message):
        self.context = None
        self.gate.show('读取卡牌未完成：' + message)

    def invalidate(self):
        self.gate.ready()
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
        self.owner.run(lambda: engine.inspect(self.saves[idx]['path']), self.context_loaded, '正在读取目标存档的卡牌…', self.load_failed)

    def context_loaded(self, context):
        self.context, self.selected, self.active = context, set(), None
        self.goal_spin.configure(to=len(context['cards']))
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
            maximum = len(self.context['cards']) if self.context else 984
            return min(maximum, max(1, int(self.goal_value.get())))
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
                if self.kind.get() != '全部类型' and r['kind'] != self.kind.get():
                    continue
                scope = self.appearance.get()
                if scope == '第一部及特殊' and r['appearance'] not in (1, 3):
                    continue
                if scope == '第二部' and r['appearance'] != 2:
                    continue
                if scope == '特殊出现' and r['appearance'] != 3:
                    continue
                if q and q not in unicodedata.normalize('NFKC', r['id'] + ' ' + r['skills'] + ' ' + r['details'] + ' ' + r['description']).casefold():
                    continue
            result.append(r)
        self.visible = result
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(result):
            checked = r['id'] in self.selected
            status = '已持有' if r['owned'] else ('可添加' if r['available'] else '暂不可加')
            self.tree.insert('', 'end', iid=str(i), values=('☑' if checked else ('—' if r['owned'] or not r['available'] else '☐'),
                            r['id'], r['kind'], r['rarity'], r['faction'], r['star'], status),
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
        star_label = '共享物品★' if r['kind'] == '物品' else '培养★'
        self.card_hint.configure(text='%s · %s · %s\n%s%s · %s' % (r['kind'], r['rarity'], r['faction'], star_label, r['star'],
                                '已持有' if r['owned'] else ('可以添加' if r['available'] else '暂不可添加')))
        note = '物品使用当前进度的共享物品星级。' if r['kind'] == '物品' else (
               '添加时按游戏规则建立角色，初始培养★%s。' % r['star'] if r['new_character'] else '沿用角色当前培养星级。')
        text = '基础HP %s   基础AT %s\n\n%s\n\n%s' % (r['hp'], r['atk'], r['details'],
               note if r['available'] else r['unavailable_reason'])
        if r['description']:
            text = r['description'] + '\n\n' + text
        if r['appearance'] == 2:
            text += '\n\n第二部版本，请按需单独选择。'
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
        ids = engine.suggest(self.context, self.goal(), self.selected)
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
        if hasattr(self, 'gate'):
            self.gate.update_actions()
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
        self.owner.training.invalidate()
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
