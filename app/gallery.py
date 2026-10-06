from collections import OrderedDict
import json
import math
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import engine
import app_paths
from ui_theme import BG, SURFACE, TEXT, MUTED, LINE, BLUE, TINT, GOLD, FONT, CONTROL, ACCENT_TEXT, px


class Images:
    def __init__(self, master):
        self.master = master
        self.reload()
        self.cache = OrderedDict()

    def reload(self):
        path = app_paths.IMAGE_DIR / 'manifest.json'
        try:
            self.entries = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except (ValueError, OSError):
            self.entries = {}
        if not isinstance(self.entries, dict):
            self.entries = {}
        if hasattr(self, 'cache'):
            self.cache.clear()

    def get(self, ident, size=(136, 204)):
        size = px(self.master, size)
        key = (ident, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        entry = self.entries.get(ident)
        if not isinstance(entry, dict) or not isinstance(entry.get('file'), str):
            return None
        path = app_paths.IMAGE_DIR / entry['file']
        if not path.is_file() or path.resolve().parent != app_paths.IMAGE_DIR.resolve():
            return None
        try:
            with Image.open(path) as im:
                image = ImageTk.PhotoImage(im.convert('RGB').resize(size, Image.Resampling.LANCZOS), master=self.master)
        except (OSError, ValueError):
            return None
        self.cache[key] = image
        while len(self.cache) > 100:
            self.cache.popitem(last=False)
        return image


class Gallery(ttk.Frame):
    W, H = 170, 290

    def __init__(self, master, images, on_detail, on_toggle):
        super().__init__(master)
        self.images, self.on_detail, self.on_toggle = images, on_detail, on_toggle
        self.W, self.H = px(self, (170, 290))
        self.cards, self.selected, self.active, self.cols = [], set(), None, 1
        self.photos = []
        self.pending = False
        self.canvas = tk.Canvas(self, bg=BG, borderwidth=0, highlightthickness=0, yscrollincrement=24)
        self.scroll = ttk.Scrollbar(self, orient='vertical', command=self.scroll_to)
        self.canvas.configure(yscrollcommand=self.view_changed)
        self.scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', self.layout)
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<Button-1>', self.click)
        self.canvas.bind('<Double-1>', self.double_click)
        self.canvas.bind('<space>', self.space)

    def p(self, value):
        return px(self, value)

    def set_cards(self, cards, selected, active=None, reset=True):
        self.cards, self.selected, self.active = cards, set(selected), active
        if reset:
            self.canvas.yview_moveto(0)
        self.layout()

    def layout(self, event=None):
        self.cols = max(1, self.canvas.winfo_width() // self.W)
        self.canvas.configure(scrollregion=(0, 0, self.cols * self.W, max(1, math.ceil(len(self.cards) / self.cols)) * self.H))
        self.schedule()

    def schedule(self):
        if not self.pending:
            self.pending = True
            self.after_idle(self.draw)

    def view_changed(self, *args):
        self.scroll.set(*args)
        self.schedule()

    def scroll_to(self, *args):
        self.canvas.yview(*args)
        self.schedule()

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) * 3, 'units')
        self.schedule()
        return 'break'

    def draw(self):
        self.pending = False
        self.canvas.delete('all')
        self.photos = []
        if not self.cards:
            self.canvas.create_text(self.p(24), self.p(28), anchor='nw', width=max(1, self.canvas.winfo_width()-self.p(48)), text='没有符合条件的卡牌。可调整搜索或筛选。',
                                    fill=MUTED, font=(FONT, 11))
            return
        top = max(0, int(self.canvas.canvasy(0) // self.H) - 1)
        bottom = int(self.canvas.canvasy(self.canvas.winfo_height()) // self.H) + 2
        gutter = max(0, (self.canvas.winfo_width() - self.cols * self.W) // 2)
        for index in range(top * self.cols, min(len(self.cards), bottom * self.cols)):
            r = self.cards[index]
            x, y = gutter + (index % self.cols) * self.W, (index // self.cols) * self.H
            checked = r['id'] in self.selected
            tags = ('card', 'i%d' % index)
            outline = BLUE if checked or r['id'] == self.active else LINE
            fill = TINT if checked else SURFACE
            self.rounded(x + self.p(5), y + self.p(4), x + self.W - self.p(5), y + self.H - self.p(6),
                         radius=self.p(3), fill=fill, outline=outline, width=self.p(2 if checked else 1), tags=tags)
            image = self.images.get(r['id'])
            if image:
                self.photos.append(image)
                self.canvas.create_image(x + self.W // 2, y + self.p(16), image=image, anchor='n', tags=tags)
            else:
                self.canvas.create_rectangle(x + self.p(17), y + self.p(16), x + self.p(153), y + self.p(220), fill=CONTROL, outline='', tags=tags)
                self.canvas.create_text(x + self.W // 2, y + self.p(113), text='暂无卡面', fill=MUTED, font=(FONT, 10), tags=tags)
            self.canvas.create_text(x + self.W // 2, y + self.p(230), text=r['id'], width=self.p(146),
                                    font=(FONT, 9, 'bold'), fill=TEXT, anchor='n', tags=tags)
            self.canvas.create_text(x + self.W // 2, y + self.p(272), text='%s  ·  ★%s' % (r['faction'], r['star']),
                                    font=(FONT, 8), fill=MUTED, tags=tags)
            if r['rarity'] != '普通':
                colour, ink = ('#f9e9bf', GOLD) if r['rarity'] == '特级' else ('#e9ddff', '#6942a6')
                self.rounded(x + self.p(105), y + self.p(12), x + self.p(158), y + self.p(35), radius=self.p(4), fill=colour, outline='', tags=tags)
                self.canvas.create_text(x + self.p(132), y + self.p(23), text=r['rarity'], fill=ink, font=(FONT, 8, 'bold'), tags=tags)
            if r['owned'] or not r['available']:
                label = '已持有' if r['owned'] else '不可加'
                self.rounded(x + self.p(12), y + self.p(12), x + self.p(62), y + self.p(35), radius=self.p(4), fill='#39485c', outline='', tags=tags)
                self.canvas.create_text(x + self.p(37), y + self.p(23), text=label, fill='white', font=(FONT, 8), tags=tags)
            else:
                self.rounded(x + self.p(12), y + self.p(12), x + self.p(36), y + self.p(36), radius=self.p(4),
                             fill=BLUE if checked else SURFACE, outline=BLUE, width=1, tags=tags)
                if checked:
                    self.canvas.create_text(x + self.p(24), y + self.p(24), text='✓', fill=ACCENT_TEXT, font=('Segoe UI', 12, 'bold'), tags=tags)

    def rounded(self, x1, y1, x2, y2, radius=8, **options):
        r = radius
        points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2,
                  x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.canvas.create_polygon(points, smooth=True, splinesteps=12, **options)

    def hit(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x, y, x, y)
        for item in reversed(items):
            for tag in self.canvas.gettags(item):
                if tag.startswith('i') and tag[1:].isdigit():
                    index = int(tag[1:])
                    if index < len(self.cards):
                        return index, x, y
        return None

    def click(self, event):
        self.canvas.focus_set()
        found = self.hit(event)
        if not found:
            return
        index, x, y = found
        r = self.cards[index]
        self.active = r['id']
        self.on_detail(r)
        gutter = max(0, (self.canvas.winfo_width() - self.cols * self.W) // 2)
        localx = x - gutter - (index % self.cols) * self.W
        localy = y - (index // self.cols) * self.H
        if self.p(12) <= localx <= self.p(36) and self.p(12) <= localy <= self.p(36) and not r['owned'] and r['available']:
            self.on_toggle(r)
        self.schedule()

    def double_click(self, event):
        found = self.hit(event)
        if found:
            index, x, y = found
            gutter = max(0, (self.canvas.winfo_width() - self.cols * self.W) // 2)
            localx = x - gutter - (index % self.cols) * self.W
            localy = y - (index // self.cols) * self.H
            if not (self.p(12) <= localx <= self.p(36) and self.p(12) <= localy <= self.p(36)):
                self.on_toggle(self.cards[index])

    def space(self, event):
        row = next((r for r in self.cards if r['id'] == self.active), None)
        if row:
            self.on_toggle(row)
        return 'break'
