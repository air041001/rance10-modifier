"""Shared colours and fixed-size navigation for the local desktop app."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

BG = '#f3f5f9'
SURFACE = '#ffffff'
TEXT = '#1e293b'
MUTED = '#64748b'
LINE = '#e0e6ee'
BLUE = '#2563eb'
TINT = '#ebf2ff'
GREEN = '#18765b'
RED = '#b42338'
GOLD = '#946112'
NAV = '#192536'
NAV_ACTIVE = '#2b3d55'
FONT = 'Microsoft YaHei UI'


def surface(master, padding=20):
    return tk.Frame(master, bg=SURFACE, highlightbackground=LINE, highlightthickness=1,
                    borderwidth=0, padx=padding, pady=padding)


def configure_styles(master):
    for name in ['TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont']:
        tkfont.nametofont(name, root=master).configure(family=FONT, size=10)
    master.option_add('*TCombobox*Listbox.font', (FONT, 10))
    s = ttk.Style(master)
    s.theme_use('clam')
    s.configure('.', font=(FONT, 10), background=BG, foreground=TEXT)
    s.configure('TFrame', background=BG)
    s.configure('TLabel', background=BG, foreground=TEXT)
    s.configure('Surface.TFrame', background=SURFACE)
    s.configure('Surface.TLabel', background=SURFACE, foreground=TEXT)
    s.configure('Hint.TLabel', foreground=MUTED, font=(FONT, 10))
    s.configure('SurfaceHint.TLabel', background=SURFACE, foreground=MUTED, font=(FONT, 10))
    s.configure('Section.TLabel', font=(FONT, 15, 'bold'), foreground=TEXT)
    s.configure('CardTitle.TLabel', font=(FONT, 13, 'bold'), foreground=TEXT, background=SURFACE)
    s.configure('Value.TLabel', font=('Segoe UI', 42, 'bold'), foreground=TEXT, background=SURFACE)
    s.configure('Summary.TLabel', font=(FONT, 12, 'bold'), foreground=TEXT)
    s.configure('TButton', font=(FONT, 10), padding=(16, 10), background=SURFACE,
                foreground=TEXT, borderwidth=1, bordercolor='#d2dbe7',
                lightcolor=SURFACE, darkcolor=SURFACE, relief='flat', focusthickness=0)
    s.map('TButton', background=[('disabled', '#edf0f4'), ('pressed', '#e2e8f0'), ('active', '#f0f4f9')],
          foreground=[('disabled', '#95a0b0')], bordercolor=[('active', '#9fb2ca')],
          lightcolor=[('active', '#f0f4f9')], darkcolor=[('active', '#f0f4f9')])
    s.configure('Primary.TButton', font=(FONT, 10, 'bold'), background=BLUE,
                foreground='white', bordercolor=BLUE, lightcolor=BLUE, darkcolor=BLUE)
    s.map('Primary.TButton', background=[('disabled', '#cbd5e1'), ('pressed', '#1744b4'), ('active', '#1d53d2')],
          foreground=[('disabled', '#7a889c'), ('!disabled', 'white')],
          bordercolor=[('disabled', '#cbd5e1'), ('!disabled', BLUE)],
          lightcolor=[('!disabled', BLUE)], darkcolor=[('!disabled', BLUE)])
    s.configure('TEntry', font=(FONT, 11), fieldbackground=SURFACE, padding=(10, 8),
                bordercolor='#ccd6e3', lightcolor=SURFACE, darkcolor=SURFACE)
    s.configure('TCombobox', font=(FONT, 10), fieldbackground=SURFACE, padding=(9, 7),
                background=SURFACE, bordercolor='#ccd6e3', arrowsize=14)
    s.map('TCombobox', fieldbackground=[('readonly', SURFACE)],
          foreground=[('readonly', TEXT)], selectbackground=[('readonly', SURFACE)],
          selectforeground=[('readonly', TEXT)])
    s.configure('TSpinbox', font=(FONT, 11), fieldbackground=SURFACE, padding=(8, 7), arrowsize=13,
                background=SURFACE, bordercolor='#ccd6e3')
    s.configure('TCheckbutton', background=BG, padding=(0, 5), font=(FONT, 10))
    s.map('TCheckbutton', background=[('active', BG)])
    s.configure('Surface.TCheckbutton', background=SURFACE)
    s.map('Surface.TCheckbutton', background=[('active', SURFACE)])
    s.configure('Treeview', font=(FONT, 10), rowheight=36, background=SURFACE,
                fieldbackground=SURFACE, foreground=TEXT, borderwidth=0)
    s.configure('Treeview.Heading', font=(FONT, 10, 'bold'), background='#edf2f8',
                foreground='#42526b', padding=(9, 10), relief='flat')
    s.map('Treeview', background=[('selected', '#dfebff')], foreground=[('selected', TEXT)])
    s.configure('Vertical.TScrollbar', background='#c1cbd8', troughcolor=BG, borderwidth=0, arrowsize=12)
    s.configure('TPanedwindow', background=BG, sashwidth=10)
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
        item = tk.Frame(self.sidebar, bg=NAV, height=62, width=172, cursor='hand2', takefocus=1)
        item.pack(fill='x', pady=4)
        item.pack_propagate(False)
        marker = tk.Frame(item, bg=NAV, width=3)
        marker.pack(side='left', fill='y')
        number = tk.Label(item, text='%02d' % len(self.pages), font=('Consolas', 13, 'bold'),
                          bg=NAV, fg='#73849c', width=3)
        number.pack(side='left', padx=(8, 2))
        labels = tk.Frame(item, bg=NAV)
        labels.pack(side='left', fill='both', expand=True, pady=10)
        title = tk.Label(labels, text=text, font=(FONT, 10, 'bold'), bg=NAV, fg='#cad5e4', anchor='w')
        title.pack(fill='x')
        hint = tk.Label(labels, text=subtitle, font=(FONT, 8), bg=NAV, fg='#8c9bb0', anchor='w')
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
            marker.configure(bg='#6c9dff' if selected else NAV)
            number.configure(fg='#91b6ff' if selected else '#73849c')
            title.configure(fg='white' if selected else '#cad5e4')
            hint.configure(fg='#b3c3db' if selected else '#8c9bb0')
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
    def __init__(self, master, background=SURFACE):
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
