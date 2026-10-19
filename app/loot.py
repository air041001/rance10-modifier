import base64
import json
import app_paths
import engine
import food
import loot_code
import treasure_code
import save_compat
import settings


class Session(food.Session):
    watch_flag = '--loot-watch'
    label = '宝箱'

    def configure(self, all_cards, unique, guaranteed=False):
        if not all_cards and not unique and not guaranteed:
            return self.cancel()
        flags = dict(all_cards=bool(all_cards), unique=bool(unique), guaranteed=bool(guaranteed))
        snapshot = self.request(dict(action='probe', **flags))['snapshot']
        catalog = None
        if all_cards:
            catalog = engine.catalog_data()
            engine.require(catalog['source']['ex_sha256'] == save_compat.file_hash(settings.game_dir() / 'Rance10EX.ex'),
                           '图鉴属于另一套游戏，请先重新准备当前游戏的图鉴。')
        patches = {}
        if all_cards or unique:
            source = base64.b64decode(snapshot['source_code'])
            code = loot_code.make_code(source, snapshot['profile'], catalog, all_cards, unique)
            patches['patch'] = base64.b64encode(code).decode('ascii')
        if guaranteed:
            source = base64.b64decode(snapshot['drop_source_code'])
            code = treasure_code.make_code(source, snapshot['profile'])
            patches['drop_patch'] = base64.b64encode(code).decode('ascii')
        result = self.request(dict(action='arm', **flags, **patches,
            pid=snapshot['pid'], session=snapshot['session'], global_owner=snapshot['global_owner'],
            ))
        app_paths.initialize()
        import datetime
        with app_paths.LOG_FILE.open('a', encoding='utf-8') as output:
            output.write(json.dumps(dict(action='loot', **flags,
                time=datetime.datetime.now().isoformat(timespec='seconds')), ensure_ascii=False)+'\n')
        return result
