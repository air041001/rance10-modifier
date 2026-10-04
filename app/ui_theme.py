"""Shared colours and fixed-size navigation for the local desktop app."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

PALETTES = {
    'dark': dict(BG='#1c2026', SURFACE='#252b33', TEXT='#e5e5e5', MUTED='#a7aeb9',
                 LINE='#3c444e', BLUE='#c4a46b', TINT='#39352f', GREEN='#8fc8b6',
                 RED='#e89b9b', GOLD='#c4a46b', NAV='#171b20', NAV_ACTIVE='#292f38',
                 CONTROL='#292f38', BORDER='#515964', ACCENT_TEXT='#231f19'),
    'light': dict(BG='#f3f2f0', SURFACE='#ffffff', TEXT='#302f32', MUTED='#706a70',
                  LINE='#d9d6d4', BLUE='#883e49', TINT='#eadcdf', GREEN='#277363',
                  RED='#a83449', GOLD='#883e49', NAV='#e9e6e4', NAV_ACTIVE='#e0d8d8',
                  CONTROL='#f7f5f4', BORDER='#c7bec2', ACCENT_TEXT='#ffffff')
}
globals().update(PALETTES['dark'])
MODE = 'dark'
FONT = 'Microsoft YaHei UI'


def set_palette(mode):
    """Imported colour names are refreshed too; models and helpers stay alive."""
    import sys
    global MODE
    old = dict(PALETTES[MODE])
    MODE = mode if mode in PALETTES else 'dark'
    current = PALETTES[MODE]
    globals().update(current)
    names = ['main', 'numbers_ui', 'cards_ui', 'training_ui', 'setup_ui', 'gallery']
    entry = sys.modules.get('__main__')
    if entry and getattr(getattr(entry, 'App', None), '__module__', None) == '__main__':
        names.append('__main__')
    for name in names:
        module = sys.modules.get(name)
        if module:
            for key, value in current.items():
                if hasattr(module, key):
                    setattr(module, key, value)
    return old, current


def recolour(widget, old, current):
    colours = {}
    for key in old:
        # White text and white surfaces can share a colour in the light theme.
        # Explicit ttk styles handle button text; Tk surfaces take precedence.
        colours.setdefault(old[key], current[key])
    for option in ['background', 'foreground', 'highlightbackground', 'highlightcolor',
                   'insertbackground', 'selectbackground', 'selectforeground',
                   'activebackground', 'activeforeground', 'disabledforeground']:
        try:
            value = str(widget.cget(option))
            if value in colours:
                widget.configure(**{option: colours[value]})
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        recolour(child, old, current)


def surface(master, padding=20):
    return tk.Frame(master, bg=SURFACE, highlightbackground=LINE, highlightthickness=1,
                    borderwidth=0, padx=padding, pady=padding)


def apply_window_theme(master):
    """Colour this app's native title bar; older Windows keeps its default."""
    import ctypes
    import sys
    if sys.platform != 'win32':
        return {}
    try:
        from ctypes import wintypes
        master.update_idletasks()
        get_parent = ctypes.windll.user32.GetParent
        get_parent.argtypes = [wintypes.HWND]
        get_parent.restype = wintypes.HWND
        hwnd = get_parent(master.winfo_id()) or master.winfo_id()
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        setter.restype = ctypes.c_long
        def colour(value):
            return int(value[5:7] + value[3:5] + value[1:3], 16)
        values = {20: int(MODE == 'dark'), 34: colour(LINE),
                  35: colour(BG), 36: colour(TEXT)}
        applied = {}
        for attribute, value in values.items():
            data = wintypes.DWORD(value)
            if setter(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data)) == 0:
                applied[attribute] = value
        return applied
    except (AttributeError, OSError, tk.TclError):
        return {}


def configure_styles(master):
    for name in ['TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont']:
        tkfont.nametofont(name, root=master).configure(family=FONT, size=10)
    master.option_add('*TCombobox*Listbox.font', (FONT, 10))
    s = ttk.Style(master)
    if s.theme_use() != 'clam':
        s.theme_use('clam')
    s.configure('.', font=(FONT, 10), background=BG, foreground=TEXT,
                bordercolor=BORDER, lightcolor=CONTROL, darkcolor=CONTROL,
                troughcolor=BG, selectbackground=TINT, selectforeground=TEXT)
    s.map('.', background=[('disabled', BG), ('active', BG)],
          foreground=[('disabled', MUTED)], selectbackground=[('!focus', TINT)],
          selectforeground=[('!focus', TEXT)])
    s.configure('TFrame', background=BG)
    s.configure('TLabel', background=BG, foreground=TEXT)
    s.configure('Surface.TFrame', background=SURFACE)
    s.configure('Surface.TLabel', background=SURFACE, foreground=TEXT)
    s.configure('Hint.TLabel', foreground=MUTED, font=(FONT, 10))
    s.configure('SurfaceHint.TLabel', background=SURFACE, foreground=MUTED, font=(FONT, 10))
    s.configure('Section.TLabel', font=(FONT, 13, 'bold'), foreground=TEXT)
    s.configure('CardTitle.TLabel', font=(FONT, 10, 'bold'), foreground=TEXT, background=SURFACE)
    s.configure('Value.TLabel', font=('Segoe UI', 26), foreground=TEXT, background=SURFACE)
    s.configure('Summary.TLabel', font=(FONT, 10, 'bold'), foreground=TEXT)
    s.configure('TButton', font=(FONT, 9), padding=(12, 7), background=CONTROL,
                foreground=TEXT, borderwidth=1, bordercolor=BORDER,
                lightcolor=SURFACE, darkcolor=SURFACE, relief='flat', focusthickness=0)
    s.map('TButton', background=[('disabled', BG), ('pressed', TINT), ('active', NAV_ACTIVE)],
          foreground=[('disabled', MUTED)], bordercolor=[('active', BLUE)],
          lightcolor=[('active', NAV_ACTIVE)], darkcolor=[('active', NAV_ACTIVE)])
    s.configure('Primary.TButton', font=(FONT, 10, 'bold'), background=BLUE,
                foreground=ACCENT_TEXT, bordercolor=BLUE, lightcolor=BLUE, darkcolor=BLUE)
    s.map('Primary.TButton', background=[('disabled', TINT), ('pressed', GOLD), ('active', BLUE)],
          foreground=[('disabled', MUTED), ('!disabled', ACCENT_TEXT)],
          bordercolor=[('disabled', LINE), ('!disabled', BLUE)],
          lightcolor=[('!disabled', BLUE)], darkcolor=[('!disabled', BLUE)])
    s.configure('TEntry', font=(FONT, 10), fieldbackground=CONTROL, foreground=TEXT, insertcolor=TEXT, padding=(8, 6),
                bordercolor=BORDER, lightcolor=CONTROL, darkcolor=CONTROL)
    s.map('TEntry', background=[('readonly', CONTROL)], bordercolor=[('focus', BLUE)],
          lightcolor=[('focus', CONTROL)], darkcolor=[('focus', CONTROL)])
    s.configure('TCombobox', font=(FONT, 9), fieldbackground=CONTROL, padding=(7, 5),
                background=CONTROL, bordercolor=BORDER, arrowsize=14, arrowcolor=MUTED,
                lightcolor=CONTROL, darkcolor=CONTROL)
    s.map('TCombobox', fieldbackground=[('readonly', CONTROL)],
          foreground=[('readonly', TEXT)], selectbackground=[('readonly', CONTROL)],
          selectforeground=[('readonly', TEXT)],
          background=[('disabled', CONTROL), ('pressed', NAV_ACTIVE), ('active', CONTROL)],
          bordercolor=[('focus', BLUE)], lightcolor=[('focus', CONTROL)], darkcolor=[('focus', CONTROL)])
    s.configure('TSpinbox', font=(FONT, 10), fieldbackground=CONTROL, foreground=TEXT, insertcolor=TEXT,
                padding=(7, 5), arrowsize=13, background=CONTROL, bordercolor=BORDER, arrowcolor=MUTED,
                lightcolor=CONTROL, darkcolor=CONTROL)
    s.map('TSpinbox', background=[('readonly', CONTROL), ('active', CONTROL)],
          bordercolor=[('focus', BLUE)], lightcolor=[('focus', CONTROL)], darkcolor=[('focus', CONTROL)])
    s.configure('TCheckbutton', background=BG, padding=(0, 5), font=(FONT, 10),
                indicatorbackground=CONTROL, indicatorforeground=TEXT,
                bordercolor=BORDER, lightcolor=CONTROL, darkcolor=CONTROL)
    s.map('TCheckbutton', background=[('active', BG)],
          indicatorbackground=[('disabled', SURFACE), ('pressed', TINT), ('selected', TINT)],
          indicatorforeground=[('disabled', MUTED), ('selected', BLUE)])
    s.configure('Surface.TCheckbutton', background=SURFACE)
    s.map('Surface.TCheckbutton', background=[('active', SURFACE)])
    s.configure('Treeview', font=(FONT, 10), rowheight=32, background=SURFACE,
                fieldbackground=SURFACE, foreground=TEXT, borderwidth=0)
    s.configure('Treeview.Heading', font=(FONT, 9, 'bold'), background=CONTROL,
                foreground=MUTED, padding=(8, 8), relief='flat')
    s.map('Treeview', background=[('selected', TINT)], foreground=[('selected', TEXT)])
    for orientation in ['Vertical', 'Horizontal']:
        style = orientation + '.TScrollbar'
        s.configure(style, background=BORDER, troughcolor=BG, borderwidth=0, arrowsize=12,
                    bordercolor=BG, lightcolor=BORDER, darkcolor=BORDER, arrowcolor=MUTED)
        s.map(style, background=[('pressed', BLUE), ('active', MUTED)],
              lightcolor=[('pressed', BLUE), ('active', MUTED)],
              darkcolor=[('pressed', BLUE), ('active', MUTED)])
    s.configure('TPanedwindow', background=BG, sashwidth=12)
    s.configure('TSeparator', background=LINE)
    s.configure('TProgressbar', background=BLUE, troughcolor=CONTROL)
    master.option_add('*TCombobox*Listbox.background', CONTROL)
    master.option_add('*TCombobox*Listbox.foreground', TEXT)
    master.option_add('*TCombobox*Listbox.selectBackground', TINT)
    master.option_add('*TCombobox*Listbox.selectForeground', TEXT)
    return s


class PageDeck(ttk.Frame):
    """A page switcher whose navigation keeps identical geometry in every state."""
    def __init__(self, master, sidebar):
        super().__init__(master)
        self.sidebar, self.pages, self.items, self.current = sidebar, {}, {}, None
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def add(self, page, text, subtitle=''):
        key = str(page)
        self.pages[key] = page
        page.grid(row=0, column=0, sticky='nsew')
        item = tk.Frame(self.sidebar, bg=NAV, height=58, width=166, cursor='hand2', takefocus=1)
        item.pack(fill='x', pady=4)
        item.pack_propagate(False)
        marker = tk.Frame(item, bg=NAV, width=3)
        marker.pack(side='left', fill='y')
        number = tk.Label(item, text=['▤', '▦', '☆', '◷', '⚙'][len(self.pages)-1], font=('Segoe UI Symbol', 14),
                          bg=NAV, fg=MUTED, width=2)
        number.pack(side='left', padx=(8, 2))
        labels = tk.Frame(item, bg=NAV)
        labels.pack(side='left', fill='both', expand=True, pady=10)
        title = tk.Label(labels, text=text, font=(FONT, 10), bg=NAV, fg=TEXT, anchor='w')
        title.pack(fill='x')
        hint = tk.Label(labels, text=subtitle, font=(FONT, 8), bg=NAV, fg=MUTED, anchor='w')
        hint.pack(fill='x', pady=(2, 0))
        for widget in [item, marker, number, labels, title, hint]:
            widget.bind('<Button-1>', lambda e, k=key: self.select(k))
        item.bind('<Return>', lambda e, k=key: self.select(k))
        item.bind('<space>', lambda e, k=key: self.select(k))
        self.items[key] = (item, marker, number, labels, title, hint)
        if self.current is None:
            self.select(key)
        else:
            self.pages[self.current].tkraise()

    def select(self, page=None):
        if page is None:
            return self.current
        key = str(page)
        if key not in self.pages:
            raise KeyError(key)
        self.current = key
        self.pages[key].tkraise()
        for k, widgets in self.items.items():
            selected = k == key
            item, marker, number, labels, title, hint = widgets
            colour = NAV_ACTIVE if selected else NAV
            for w in [item, number, labels, title, hint]:
                w.configure(bg=colour)
            marker.configure(bg=BLUE if selected else NAV)
            number.configure(fg=BLUE if selected else MUTED)
            title.configure(fg=TEXT)
            hint.configure(fg=MUTED)
        self.event_generate('<<NotebookTabChanged>>', when='tail')
        return key


class LibraryGate(tk.Frame):
    """Explain prerequisites without moving away from the chosen feature."""
    def __init__(self, master, content, owner, retry):
        super().__init__(master, bg=BG)
        self.content, self.owner = content, owner
        panel = surface(self, 24)
        panel.pack(fill='x', pady=(12, 0))
        ttk.Label(panel, text='准备本机图鉴后即可使用', style='CardTitle.TLabel').pack(anchor='w')
        self.message = ttk.Label(panel, style='SurfaceHint.TLabel', wraplength=650, justify='left')
        self.message.pack(fill='x', pady=(12, 16))
        actions = ttk.Frame(panel, style='Surface.TFrame')
        actions.pack(fill='x')
        self.prepare_button = ttk.Button(actions, text='前往准备图鉴', style='Primary.TButton',
                                         command=lambda: owner.tabs.select(owner.setup))
        self.prepare_button.pack(side='left')
        self.retry_button = ttk.Button(actions, text='重新检查', command=retry)
        self.retry_button.pack(side='left', padx=(10, 0))
        self.bind('<Configure>', lambda e: self.message.configure(wraplength=max(280, e.width - 60)))

    def show(self, message):
        self.message.configure(text=message)
        self.content.pack_forget()
        self.pack(fill='both', expand=True)

    def ready(self):
        self.pack_forget()
        self.content.pack(fill='both', expand=True)

    def update_actions(self):
        for button in [self.prepare_button, self.retry_button]:
            button.configure(state='disabled' if self.owner.busy else 'normal')


class ScrollBody(tk.Frame):
    """A card detail column can scroll as one piece at smaller window sizes."""
    def __init__(self, master, background=None):
        background = SURFACE if background is None else background
        super().__init__(master, bg=background, borderwidth=0)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, borderwidth=0, yscrollincrement=24)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.canvas, bg=background)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.canvas.bind('<MouseWheel>', self.wheel)

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) * 3, 'units')
        return 'break'

    def see(self, widget):
        self.update_idletasks()
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = top + widget.winfo_height()
        visible = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        total = max(1, self.body.winfo_height())
        if top < visible:
            self.canvas.yview_moveto(max(0, top - 12) / total)
        elif bottom > visible + height:
            self.canvas.yview_moveto(max(0, bottom - height + 12) / total)

    def bind_children(self, follow_focus=False):
        def bind(widget):
            widget.bind('<MouseWheel>', self.wheel)
            if follow_focus:
                widget.bind('<FocusIn>', lambda e: self.see(e.widget), add='+')
            for child in widget.winfo_children():
                bind(child)
        bind(self.body)

    def reset(self):
        self.canvas.yview_moveto(0)
