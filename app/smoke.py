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
    from main import App
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--upgrade-library', action='store_true')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    app = App(auto_connect=False)
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
    app.training.loaded = True  # No background read is needed for geometry checks.
    for page in [app.setup, app.numbers, app.training, app.records, app.setup]:
        app.tabs.select(page)
        app.update()
        geometry.append([[row[0].winfo_width(), row[0].winfo_height()] for row in app.tabs.items.values()])
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
                 library_upgrade=upgrade,
                 value_font=font.Font(app, font=app.theme.lookup('Value.TLabel', 'font')).actual(),
                 window_bottom=app.winfo_rooty() + app.winfo_height())
    import runtime
    import settings
    state['native_discovery_ok'] = isinstance(runtime.discover(), list)
    if settings.load().get('game_dir'):
        try:
            state['live_probe'] = {k: v for k, v in runtime.run('probe').items() if k in ['food', 'total_points']}
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
                assert types == {'人物': 662, '通用': 145, '物品': 177}, types
                sword = next(r for r in app.cards.visible if r['id'] == '利萨斯圣剑')
                app.cards.detail(sword)
                app.update()
                assert '共享物品★' in app.cards.card_hint.cget('text')
                assert '使用过的圣剑' in app.cards.details.cget('text')
                state['cards']['types'] = types
                state['cards']['item_preview_loaded'] = bool(app.cards.preview_photo)
                app.cards.kind.set('全部类型')
                scopes = {}
                for scope, expected in [('第一部及特殊', 857), ('第二部', 127)]:
                    app.cards.appearance.set(scope)
                    app.cards.filter()
                    app.update()
                    scopes[scope] = len(app.cards.visible)
                    assert len(app.cards.visible) == expected
                app.cards.appearance.set('全部范围')
                app.cards.filter()
                state['cards']['scopes'] = scopes
                if app_paths.CHARACTER_FILE.exists():
                    import training
                    cultivation = training.inspect(context['path'])
                    app.training.context_loaded(cultivation)
                    app.tabs.select(app.training)
                    app.update()
                    assert app.training.active is not None
                    state['training'] = dict(characters=len(app.training.characters),
                         cards=len(app.training.rows), image_loaded=bool(app.training.photo),
                         story_text=app.training.story_text.cget('text'))
                    app.training.query.set('玛丽斯')
                    app.update()
                    assert '玛丽斯' in app.training.characters
                    app.training.query.set('not-an-existing-character')
                    app.update()
                    assert not app.training.characters
                    assert app.training.star_button.instate(['disabled'])
    assert state['helper'] and state['instructions']
    assert all(sizes == geometry[0] for sizes in geometry)
    Path(options.output).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    app.destroy()
