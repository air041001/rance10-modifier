"""Read-only launch verification for development and packaged builds."""
import argparse
import json
import sys
from pathlib import Path
from tkinter import font
import app_paths
from game_profile import VERSION


def run():
    from main import App
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    app = App(auto_connect=False)
    app.withdraw()
    app.geometry('1120x800')
    app.update()
    app.deiconify()
    app.attributes('-alpha', 0)
    app.update()
    geometry = []
    app.training.loaded = True  # No background read is needed for geometry checks.
    for page in [app.setup, app.numbers, app.training, app.records, app.setup]:
        app.tabs.select(page)
        app.update()
        geometry.append([[row[0].winfo_width(), row[0].winfo_height()] for row in app.tabs.items.values()])
    state = dict(version=VERSION, frozen=bool(getattr(sys, 'frozen', False)),
                 resources=str(app_paths.RESOURCE_DIR), data=str(app_paths.DATA_DIR),
                 helper=(app_paths.RESOURCE_DIR / 'LiveValues.exe').is_file(),
                 instructions=(app_paths.RESOURCE_DIR / '使用说明.txt').is_file(),
                 navigation=geometry,
                 value_font=font.Font(app, font=app.theme.lookup('Value.TLabel', 'font')).actual(),
                 setup_bottom=app.setup.download_button.winfo_rooty() + app.setup.download_button.winfo_height(),
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
                app.cards.loaded = True
                context = engine.inspect(saves[0]['path'])
                app.cards.context_loaded(context)
                app.tabs.select(app.cards)
                app.update()
                state['cards'] = dict(displayed=len(app.cards.visible), image_loaded=bool(app.cards.preview_photo))
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
    assert state['setup_bottom'] < state['window_bottom']
    Path(options.output).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    app.destroy()
