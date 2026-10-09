"""Launch verification without save writes; optional local image-cache upgrade."""
import argparse
import json
import sys
import time
import tempfile
from unittest.mock import patch
from pathlib import Path
from tkinter import font
import app_paths
from game_profile import VERSION


def run():
    # Exercise the same entry module as a normal EXE launch.
    App = getattr(sys.modules.get('__main__'), 'App', None)
    if App is None:
        from main import App
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--upgrade-library', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--ui-scale', type=int, choices=[100, 125, 150, 175, 200, 250, 300])
    parser.add_argument('--dpi-layout-only', action='store_true')
    options = parser.parse_args()
    # Set Tk's point-to-pixel scale before any fonts or widgets are created.
    # Each CLI invocation uses a separate interpreter, like an actual launch.
    import tkinter as tk
    original_init = tk.Tk.__init__
    def init(root, *args, **kwargs):
        original_init(root, *args, **kwargs)
        if options.ui_scale:
            root.tk.call('tk', 'scaling', 96 / 72 * options.ui_scale / 100)
    with patch.object(tk.Tk, '__init__', init):
        app = App(auto_connect=False)
    try:
        if options.dpi_layout_only:
            check_dpi_layout(app, options)
        else:
            check(app, options)
    finally:
        try:
            app.training.food_session.close()
        finally:
            app.destroy()


def check(app, options):
    app.withdraw()
    app.geometry('1120x800')
    app.update()
    app.deiconify()
    app.attributes('-alpha', 0)
    app.update()
    upgrade = None
    if options.upgrade_library:
        import assets
        before = assets.library_status()
        app.setup.repair_existing_library()
        deadline = time.monotonic() + 90
        while app.busy:
            app.update()
            assert time.monotonic() < deadline, 'Existing library upgrade did not finish'
            time.sleep(.02)
        after = assets.library_status()
        assert after['missing'] == 0, app.setup.library_status.cget('text')
        upgrade = dict(before=before, after=after)
    geometry = []
    app.training.context_loaded(dict(training_cards=[], manual=True, pending=[], slot=1,
                                    star_cap=200, enhancement_cap=10))
    app.update()
    assert app.training.active is None and not app.training.characters
    assert app.training.star_button.instate(['disabled'])
    assert app.training.food_button.instate(['disabled'])
    app.training.loaded = True  # No background read is needed for geometry checks.
    for page in [app.setup, app.numbers, app.training, app.records, app.setup]:
        app.tabs.select(page)
        app.update()
        geometry.append([[row[0].winfo_width(), row[0].winfo_height()] for row in app.tabs.items.values()])
    # The two PlayerCommonParam resources share the same record but use
    # different fields. Exercise the actual friendship button and its labels.
    before = dict(success=True, food=1, friend_points=2, total_points=20,
                  food_before=[1, 0, 2], bonus_before=[0, 1, 20])
    after = dict(before, friend_points=3)
    app.tabs.select(app.numbers)
    app.numbers.read(before)
    with patch('runtime.run', return_value=after) as run_numeric:
        app.numbers.friend_button.invoke()
        deadline = time.monotonic() + 10
        while app.busy:
            app.update()
            assert time.monotonic() < deadline, 'Friendship action did not finish'
            time.sleep(.02)
        run_numeric.assert_called_once_with('fillfriend3', None)
    assert app.numbers.friend_points.cget('text') == '3'
    assert app.numbers.food.cget('text') == '1' and app.numbers.points.cget('text') == '20'
    assert '2 → 3' in app.numbers.state.cget('text')
    app.numbers.scroll.see(app.numbers.friend_button)
    app.update()
    canvas = app.numbers.scroll.canvas
    top = app.numbers.friend_button.winfo_rooty() - canvas.winfo_rooty()
    assert 0 <= top and top + app.numbers.friend_button.winfo_height() <= canvas.winfo_height()
    app.numbers.failed('等待连接游戏。')
    assert app.numbers.friend_button.instate(['disabled'])
    app.tabs.select(app.setup)
    app.update()
    setup_controls = []
    for button in [app.setup.compat_button, app.setup.local_button, app.setup.download_button, app.setup.character_button, app.setup.data_button]:
        app.setup.scroll.see(button)
        app.update()
        canvas = app.setup.scroll.canvas
        top = button.winfo_rooty() - canvas.winfo_rooty()
        assert button.winfo_height() > 20 and 0 <= top and top + button.winfo_height() <= canvas.winfo_height()
        assert button.winfo_width() >= button.winfo_reqwidth()
        setup_controls.append(button.cget('text'))
    with tempfile.TemporaryDirectory(prefix='missing-library-') as folder:
        with patch.object(app_paths, 'CATALOG_FILE', Path(folder) / 'absent.json'):
            for page in [app.cards, app.training]:
                page.loaded = False
                app.tabs.items[str(page)][4].event_generate('<Button-1>')
                app.update()
                assert app.tabs.select() == str(page), 'Missing data changed the selected page'
                assert page.gate.winfo_ismapped() and not page.content.winfo_ismapped()
    state = dict(version=VERSION, frozen=bool(getattr(sys, 'frozen', False)),
                 resources=str(app_paths.RESOURCE_DIR), data=str(app_paths.DATA_DIR),
                 helper=(app_paths.RESOURCE_DIR / 'LiveValues.exe').is_file(),
                 instructions=(app_paths.RESOURCE_DIR / '使用说明.txt').is_file(),
                 navigation=geometry,
                 missing_library_stays_on_page=True, setup_controls_visible=setup_controls,
                 empty_character_roster_ok=True,
                 friendship_button_and_resource_isolation_ok=True,
                 library_upgrade=upgrade,
                 value_font=font.Font(app, font=app.theme.lookup('Value.TLabel', 'font')).actual(),
                 window_bottom=app.winfo_rooty() + app.winfo_height())
    import runtime
    import settings
    state['native_discovery_ok'] = isinstance(runtime.discover(), list)
    if settings.load().get('game_dir'):
        try:
            state['live_probe'] = {k: v for k, v in runtime.run('probe').items() if k in ['food', 'friend_points', 'total_points']}
        except ValueError as exc:
            # An installed library remains usable when the game is closed.
            state['live_probe_error'] = str(exc)
        if app_paths.CATALOG_FILE.exists():
            import engine
            saves = [s for s in engine.list_saves() if s['manual'] and not s.get('error')]
            if saves:
                navigation = []
                for page in [app.cards, app.training]:
                    if page == app.training and not app_paths.CHARACTER_FILE.exists():
                        continue
                    page.invalidate()
                    app.tabs.items[str(page)][4].event_generate('<Button-1>')
                    deadline = time.monotonic() + 30
                    while app.busy or page.context is None:
                        app.update()
                        assert time.monotonic() < deadline, 'Normal navigation did not load the feature'
                        time.sleep(.02)
                    assert app.tabs.select() == str(page)
                    assert not page.gate.winfo_ismapped()
                    navigation.append(type(page).__name__)
                state['normal_navigation'] = navigation
                context = app.cards.context
                app.tabs.select(app.cards)
                app.update()
                state['cards'] = dict(displayed=len(app.cards.visible), image_loaded=bool(app.cards.preview_photo))
                all_cards = context['cards']
                nude_cards = [row for row in app.cards.visible if row['nude']]
                state['cards']['nude'] = len(nude_cards)
                if nude_cards:
                    assert all(app.images.get(row['id']) is not None for row in nude_cards), 'Nude card images are missing'
                    app.cards.detail(nude_cards[0])
                    app.update()
                    assert app.cards.preview_photo is not None
                    state['cards']['nude_images_loaded'] = True
                app.cards.rarity.set('特级')
                app.cards.filter()
                app.update()
                state['cards']['rare'] = len(app.cards.visible)
                assert all(r['rarity'] == '特级' for r in app.cards.visible)
                app.cards.rarity.set('超稀有')
                app.cards.filter()
                app.update()
                state['cards']['ultra_rare'] = len(app.cards.visible)
                assert all(r['rarity'] == '超稀有' for r in app.cards.visible)
                app.cards.rarity.set('全部稀有度')
                types = {}
                for kind in ['人物', '通用', '物品']:
                    app.cards.kind.set(kind)
                    app.cards.filter()
                    app.update()
                    types[kind] = len(app.cards.visible)
                    assert all(r['kind'] == kind for r in app.cards.visible)
                    assert all(app.images.get(r['id']) is not None for r in app.cards.visible)
                assert types == {kind: sum(r['kind'] == kind for r in all_cards) for kind in types}, types
                if app.cards.visible:
                    item = app.cards.visible[0]
                    app.cards.detail(item)
                    app.update()
                    assert '共享物品★' in app.cards.card_hint.cget('text')
                    assert item['description'] in app.cards.details.cget('text')
                state['cards']['types'] = types
                state['cards']['item_preview_loaded'] = bool(app.cards.preview_photo)
                app.cards.kind.set('全部类型')
                scopes = {}
                for scope, appearances in [('第一部及特殊', (1, 3)), ('第二部', (2,))]:
                    app.cards.appearance.set(scope)
                    app.cards.filter()
                    app.update()
                    scopes[scope] = len(app.cards.visible)
                    assert len(app.cards.visible) == sum(r['appearance'] in appearances for r in all_cards)
                app.cards.appearance.set('全部范围')
                app.cards.filter()
                state['cards']['scopes'] = scopes
                if app_paths.CHARACTER_FILE.exists():
                    import training
                    cultivation = training.inspect(context['path'])
                    app.training.context_loaded(cultivation)
                    app.tabs.select(app.training)
                    app.update()
                    state['training'] = dict(characters=len(app.training.characters),
                         cards=len(app.training.rows), image_loaded=bool(app.training.photo),
                         story_text=app.training.story_text.cget('text'))
                    if app.training.characters:
                        character = app.training.active
                        assert character in app.training.characters
                        app.training.query.set(character)
                        app.update()
                        assert character in app.training.characters, 'Held character search failed'
                        state['training']['search_checked'] = character
                    app.training.query.set('not-an-existing-character')
                    app.update()
                    assert not app.training.characters
                    assert app.training.star_button.instate(['disabled'])
    assert state['helper'] and state['instructions']
    assert all(sizes == geometry[0] for sizes in geometry)
    check_new_ui(app, state)
    Path(options.output).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


def check_new_ui(app, state):
    """Exercise desktop state transitions with simulated events, without writes."""
    import ui_theme
    app.cards.loaded = app.training.loaded = True
    # Fresh installations correctly display the prerequisite gate. Show the
    # empty content explicitly for the separate filter geometry checks.
    app.cards.gate.ready()
    app.training.gate.ready()
    app.tabs.select(app.numbers)
    first = dict(food=2, friend_points=1, total_points=22, chapter=1,
                 battle_points=[0, 1, 2, 3], battle_before=[0, 1, 2, 3])
    app.numbers.read(first)
    assert app.numbers.food_title.cget('text') == '餐券'
    assert app.numbers.friend_title.cget('text') == '战果'
    assert app.numbers.friend_points.cget('text') == '0'
    assert not app.numbers.friend_button.instate(['disabled'])
    assert app.numbers.battle_minus.instate(['disabled'])
    assert not app.numbers.battle_plus.instate(['disabled'])
    app.numbers.battle_country.set('自由都市')
    app.numbers.paint_resources()
    assert app.numbers.friend_points.cget('text') == '3'
    assert app.numbers.battle_plus.instate(['disabled'])
    assert not app.numbers.battle_minus.instate(['disabled'])
    app.numbers.battle_country.set('赫尔曼')
    app.numbers.paint_resources()
    from unittest.mock import patch
    changed = dict(first, success=True, battle_points=[0, 2, 2, 3],
                   food_before=[2, 0, 1], bonus_before=[0, 1, 22],
                   battle_country=2, battle_country_name='赫尔曼')
    with patch('runtime.run', return_value=changed) as operation:
        app.numbers.battle_plus.invoke()
        deadline = time.monotonic() + 10
        while app.busy:
            app.update()
            assert time.monotonic() < deadline, 'Battle result action did not finish'
            time.sleep(.02)
        operation.assert_called_once_with('addbattle', 1, country=2)
    assert app.numbers.friend_points.cget('text') == '2'
    assert app.numbers.current['friend_points'] == 1 and app.numbers.current['food'] == 2
    assert '赫尔曼战果：1 → 2' in app.numbers.state.cget('text')
    app.numbers.read(dict(first, battle_points=None, battle_error='战果需要适配'))
    assert app.numbers.friend_button.instate(['disabled'])
    assert not app.numbers.fill_button.instate(['disabled'])
    app.numbers.read(first)
    app.numbers.chapter_mode.set('第二部')
    app.numbers.change_chapter()
    assert app.numbers.food_title.cget('text') == '金块'
    assert app.numbers.friend_title.cget('text') == '友情'
    assert app.numbers.friend_points.cget('text') == '1'
    assert not app.numbers.country_box.winfo_ismapped()
    assert app.numbers.current['chapter'] == 1 and app.numbers.current['food'] == 2
    app.numbers.read(first, automatic=True)
    assert app.numbers.food_title.cget('text') == '金块'
    assert not app.numbers.friend_button.instate(['disabled'])
    app.numbers.chapter_mode.set('自动识别')
    app.numbers.change_chapter()
    assert app.numbers.food_title.cget('text') == '餐券'
    app.numbers.read(dict(first, chapter=2))
    assert app.numbers.food_title.cget('text') == '金块'
    assert not app.numbers.friend_button.instate(['disabled'])
    assert app.numbers.story_link.instate(['disabled'])
    app.numbers.read(first)
    app.numbers.update_story(dict(armed=True, character='测试人物', completed=1, maximum=2,
                                 card_id='fixture', pid=987, session=123, global_owner='a', player_owner='b'))
    assert app.numbers.story_progress.cget('text') == '已看 1 / 2'
    app.numbers.update_story(dict(armed=True, character='测试人物', completed=2, maximum=3))
    assert app.numbers.story_progress.cget('text') == '已看 2 / 3'
    assert app.numbers.story_target['card_id'] == 'fixture'
    app.numbers.update_story(dict(armed=False, reason='changed'))
    assert app.numbers.story_target is None
    app.numbers.update_story(dict(armed=False, reason='completed', character='测试人物', completed=2, maximum=2,
                                 pid=987, session=123, global_owner='a', player_owner='b'))
    assert app.numbers.story_progress.cget('text') == '已看 2 / 2'
    app.numbers.read(dict(first, pid=987, session=123, global_owner='c', player_owner='d'))
    assert app.numbers.story_target is None
    app.numbers.update_story(dict(armed=True, character='测试人物', completed=1, maximum=3))
    original = ui_theme.MODE
    layouts = []
    for mode in [original, 'light' if original == 'dark' else 'dark']:
        if ui_theme.MODE != mode:
            app.toggle_theme(persist=False)
        app.apply_window_theme()
        for style in ['TEntry', 'TCombobox', 'TSpinbox', 'TCheckbutton', 'Vertical.TScrollbar']:
            for widget_state in [(), ('focus',), ('active',), ('disabled',)]:
                for option in ['bordercolor', 'lightcolor', 'darkcolor']:
                    value = app.theme.lookup(style, option, widget_state)
                    assert value in ui_theme.PALETTES[mode].values(), (style, option, widget_state, value)
        if app.window_theme.get(35) is not None:
            import ctypes
            from ctypes import wintypes
            parent = ctypes.windll.user32.GetParent
            parent.argtypes, parent.restype = [wintypes.HWND], wintypes.HWND
            hwnd = parent(app.winfo_id()) or app.winfo_id()
            getter = ctypes.windll.dwmapi.DwmGetWindowAttribute
            getter.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            getter.restype = ctypes.c_long
            for attribute, expected in app.window_theme.items():
                # Some DWM attributes are setters only on older Windows builds.
                actual = wintypes.DWORD()
                if attribute in (34, 35, 36) and getter(hwnd, attribute, ctypes.byref(actual), ctypes.sizeof(actual)) == 0:
                    assert actual.value == expected, (attribute, actual.value, expected, mode)
        assert all(panel.cget('bg') == ui_theme.SURFACE for panel in app.numbers.panels)
        app.numbers.read(first, automatic=True)
        assert app.connection.cget('bg') == ui_theme.BG
        assert app.connection.cget('fg') == ui_theme.GREEN
        assert app.cget('bg') == ui_theme.BG
        assert app.numbers.story_progress.cget('text') == '已看 1 / 3'
        for geometry in ['1280x820', '900x700']:
            app.geometry(geometry)
            app.update()
            for page in [app.numbers, app.cards, app.training, app.setup]:
                app.tabs.select(page)
                app.update()
                if page == app.numbers:
                    assert page.chapter_box.winfo_rootx() + page.chapter_box.winfo_width() <= page.winfo_rootx() + page.winfo_width()
                    buttons = [page.fill_button, page.friend_button, page.add_button, page.set_button, page.story_link]
                    scroll = page.scroll
                    for button in buttons:
                        scroll.see(button)
                        app.update()
                        top = button.winfo_rooty() - scroll.canvas.winfo_rooty()
                        assert 0 <= top and top + button.winfo_height() <= scroll.canvas.winfo_height(), button.cget('text')
                        assert button.winfo_width() >= button.winfo_reqwidth(), button.cget('text')
                    layouts.append(dict(theme=mode, size=geometry, resource_columns=page._columns))
                if page == app.cards:
                    for box in [page.search, page.factionbox, page.raritybox, page.versionbox, page.kindbox, page.appearancebox]:
                        right = box.winfo_rootx() + box.winfo_width()
                        assert right <= page.winfo_rootx() + page.winfo_width(), 'Card filter is clipped'
                    assert page.gallery.canvas.winfo_width() >= page.gallery.W, ('gallery', page.gallery.canvas.winfo_width(), page.gallery.W, page.winfo_width(), page.detail_panel.winfo_width(), app.winfo_width(), app.sidebar.winfo_width())
                if page == app.setup:
                    for button in [page.compat_button, page.local_button, page.download_button, page.character_button, page.data_button]:
                        page.scroll.see(button)
                        app.update()
                        top = button.winfo_rooty() - page.scroll.canvas.winfo_rooty()
                        assert 0 <= top and top + button.winfo_height() <= page.scroll.canvas.winfo_height()
                        assert button.winfo_width() >= button.winfo_reqwidth()
                assert app.theme_button.winfo_width() >= app.theme_button.winfo_reqwidth()
                assert app.theme_button.winfo_rootx() + app.theme_button.winfo_width() <= app.winfo_rootx() + app.winfo_width()
            # Theme switch must not change stable navigation sizes.
            assert len({(row[0].winfo_width(), row[0].winfo_height()) for row in app.tabs.items.values()}) == 1
    if ui_theme.MODE != original:
        app.toggle_theme(persist=False)
    assert all(panel.cget('bg') == ui_theme.SURFACE for panel in app.numbers.panels)
    app.numbers.update_story(dict(armed=False))
    state['desktop_ui'] = dict(themes_and_sizes=layouts, chapter_labels=True,
                              controls_follow_theme=True, native_titlebar_attributes=app.window_theme,
                              manual_chapter_survives_refresh=True,
                              entry_module_theme_and_connection_colours=True,
                              story_progress_and_load_reset=True, theme_keeps_target=True,
                              narrow_card_filters_visible=True)


def check_dpi_layout(app, options):
    """Check readable navigation and reachable controls at display scales."""
    import ui_theme
    app.attributes('-alpha', 0)
    app.cards.loaded = app.training.loaded = True
    app.cards.gate.ready()
    app.training.gate.ready()
    app.training.context_loaded(dict(training_cards=[], manual=True, pending=[], slot=1,
                                    star_cap=200, enhancement_cap=10))
    app.numbers.read(dict(food=2, friend_points=1, total_points=22, chapter=1, battle_points=[0, 1, 2, 3]))
    scale = options.ui_scale or round(float(app.tk.call('tk', 'scaling')) * 72 / 96 * 100)
    result = dict(version=VERSION, frozen=bool(getattr(sys, 'frozen', False)), scale=scale,
                  initial_size=app.initial_size, layouts=[])
    def settle():
        # Windows delivers native geometry notifications asynchronously.
        for _ in range(3):
            app.update()
            time.sleep(.02)
    def readable(widget):
        assert widget.winfo_width() >= widget.winfo_reqwidth(), ('width', widget.cget('text'), widget.winfo_width(), widget.winfo_reqwidth())
        assert widget.winfo_height() >= widget.winfo_reqheight(), ('height', widget.cget('text'), widget.winfo_height(), widget.winfo_reqheight())
    def contained(widget, container):
        assert widget.winfo_rootx() >= container.winfo_rootx(), ('left', str(widget))
        assert widget.winfo_rootx()+widget.winfo_width() <= container.winfo_rootx()+container.winfo_width(), ('right', str(widget))
    def reachable(button, scroll):
        # Nested panes can reflow when their outer scrollbar appears. Settle
        # that resize and bring the target into each containing viewport.
        ancestor = scroll.master
        outer = None
        while ancestor is not None:
            if isinstance(ancestor, ui_theme.ScrollBody):
                outer = ancestor
                break
            ancestor = getattr(ancestor, 'master', None)
        for _ in range(3):
            scroll.see(button)
            settle()
            if outer:
                outer.see(button)
                settle()
        readable(button)
        contained(button, scroll.canvas)
        y = button.winfo_rooty() - scroll.canvas.winfo_rooty()
        assert 0 <= y and y+button.winfo_height() <= scroll.canvas.winfo_height(), ('vertical', button.cget('text'), y, scroll.canvas.winfo_height())
    sizes = [app.initial_size, (ui_theme.px(app, 900), ui_theme.px(app, 700)),
             (ui_theme.px(app, 1280), ui_theme.px(app, 820))]
    # Exercise a 4K-sized client area as well as the real monitor's smaller
    # work area. This is simulated geometry, not a physical-monitor test.
    app.maxsize(6000, 4000)
    sizes.append((3840, 2160))
    for mode in ['dark', 'light']:
        if ui_theme.MODE != mode:
            app.toggle_theme(persist=False)
        for width, height in sizes:
            app.geometry(f'{width}x{height}')
            settle()
            readable(app.brand_title)
            nav_heights = []
            for row in app.tabs.items.values():
                for label in row[4:]:
                    readable(label)
                app.navigation_scroll.see(row[0])
                app.update()
                contained(row[0], app.sidebar)
                nav_heights.append(row[0].winfo_height())
            assert len(set(nav_heights)) == 1
            for page in [app.numbers, app.cards, app.training, app.records, app.setup]:
                app.tabs.select(page)
                settle()
                readable(app.theme_button)
                contained(app.theme_button, app)
                readable(app.page_title)
                if page == app.numbers:
                    for button in [page.fill_button, page.friend_button, page.battle_minus, page.battle_plus,
                                   page.set_button, page.add_button, page.story_link]:
                        reachable(button, page.scroll)
                    readable(page.country_box)
                    reachable(page.country_box, page.scroll)
                    readable(page.chapter_box)
                    contained(page.chapter_box, page.scroll.canvas)
                elif page == app.cards:
                    for box in [page.factionbox, page.raritybox, page.versionbox, page.kindbox, page.appearancebox]:
                        readable(box)
                        contained(box, page)
                    assert page.gallery.canvas.winfo_width() >= page.gallery.W, ('gallery', page.gallery.canvas.winfo_width(), page.gallery.W, page.winfo_width(), page.detail_panel.winfo_width(), app.winfo_width(), app.sidebar.winfo_width(), page.center.winfo_width(), page.center.sashpos(0))
                    readable(page.choose_button)
                    for button in [page.apply_button, page.suggest_button, page.choose_button]:
                        reachable(button, page.content)
                    assert int(app.theme.lookup('Treeview', 'rowheight')) >= font.nametofont('TkDefaultFont').metrics('linespace')
                elif page == app.training:
                    for button in [page.star_button, page.enhancement_button, page.food_button, page.cancel_food_button]:
                        reachable(button, page.detail_scroll)
                        y = button.winfo_rooty() - page.content.canvas.winfo_rooty()
                        assert 0 <= y and y+button.winfo_height() <= page.content.canvas.winfo_height(), ('outer training', button.cget('text'), y, button.winfo_height(), page.content.canvas.winfo_height(), page.content.body.winfo_height(), page.content.body.winfo_reqheight(), page.content.canvas.yview())
                    assert page.active is None
                elif page == app.setup:
                    for button in [page.save_button, page.detect_button, page.compat_button, page.local_button, page.download_button, page.character_button, page.data_button]:
                        reachable(button, page.scroll)
            result['layouts'].append(dict(theme=mode, size=[app.winfo_width(), app.winfo_height()],
                sidebar_width=app.sidebar.winfo_width(), nav_height=nav_heights[0], resource_columns=app.numbers._columns,
                gallery_cell=[app.cards.gallery.W, app.cards.gallery.H]))
    # A synthetic thumbnail exercises the actual scaled image and hitbox,
    # without requiring any particular character in the user's collection.
    from PIL import Image
    gallery = app.cards.gallery
    app.tabs.select(app.cards)
    settle()
    row = dict(id='Lv48 测试人物', faction='其他', star=10, rarity='特级', owned=False, available=True)
    details, selected = [], []
    with tempfile.TemporaryDirectory(prefix='dpi-card-') as folder:
        folder = Path(folder)
        Image.new('RGB', (64, 96), '#c4a46b').save(folder / 'fixture.png')
        with patch.object(app_paths, 'IMAGE_DIR', folder), \
             patch.object(app.images, 'entries', {row['id']: dict(file='fixture.png')}), \
             patch.object(gallery, 'on_detail', details.append), \
             patch.object(gallery, 'on_toggle', selected.append):
            gallery.set_cards([row], set())
            settle()
            photo = app.images.get(row['id'])
            assert (photo.width(), photo.height()) == ui_theme.px(app, (136, 204))
            gutter = max(0, (gallery.canvas.winfo_width() - gallery.cols * gallery.W) // 2)
            gallery.canvas.event_generate('<Button-1>', x=gutter+ui_theme.px(app, 24), y=ui_theme.px(app, 24))
            settle()
            assert details == [row] and selected == [row], 'Scaled checkbox click missed its card'
    result['scaled_thumbnail_and_checkbox'] = True
    Path(options.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
