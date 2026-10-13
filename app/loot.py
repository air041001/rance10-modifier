import base64
import json
import app_paths
import engine
import food
import loot_code
import save_compat
import settings


class Session(food.Session):
    watch_flag = '--loot-watch'
    label = '宝箱'

    def configure(self, all_cards, unique):
        if not all_cards and not unique:
            return self.cancel()
        snapshot = self.request(dict(action='probe'))['snapshot']
        catalog = None
        if all_cards:
            catalog = engine.catalog_data()
            engine.require(catalog['source']['ex_sha256'] == save_compat.file_hash(settings.game_dir() / 'Rance10EX.ex'),
                           '图鉴属于另一套游戏，请先重新准备当前游戏的图鉴。')
        source = base64.b64decode(snapshot['source_code'])
        code = loot_code.make_code(source, snapshot['profile'], catalog, all_cards, unique)
        result = self.request(dict(action='arm', all_cards=bool(all_cards), unique=bool(unique),
            pid=snapshot['pid'], session=snapshot['session'], global_owner=snapshot['global_owner'],
            patch=base64.b64encode(code).decode('ascii')))
        app_paths.initialize()
        import datetime
        with app_paths.LOG_FILE.open('a', encoding='utf-8') as output:
            output.write(json.dumps(dict(action='loot', all_cards=bool(all_cards), unique=bool(unique),
                time=datetime.datetime.now().isoformat(timespec='seconds')), ensure_ascii=False)+'\n')
        return result
