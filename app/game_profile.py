VERSION = '1.3.1'
PROFILE_ID = 'rance10-zh-v8-01'
GAME_HASHES = {
    'Rance10.exe': '39a508c05b13afc5427f0b722fce5c4edeced126587e037d585cf0e70d279297',
    'Rance10.ain': '85a7b91d74186aa44b2b5319fc036988344fbe45c9cc7cf7cbe2c3a4c5115247',
    'Rance10EX.ex': 'd340aaf2b0856e784943181734d5b7f47637a0cb750aebd1fb3db581ba678837',
}
# Card fields and every skill field except the display-only description.
CATALOG_DIGEST = '971bb4b6bc112f25ee28b5435885dea62b8f5bc42b4b68ae4648ee05fc48ea09'
CHARACTER_DIGEST = '20909a623a08f0ed760d1dc1cf3c5af106b79e2c1ae6f892ff0028933e96310b'
ALICE_VERSION = '0.13.0'
ALICE_SHA256 = '4123746e53a6b51eaae06c18ce145ecc8f866a0fc376541d8e9e529aa805a6de'
ALICE_URL = 'https://github.com/nunuhara/alice-tools/releases/download/0.13.0/alice-tools-0.13.0.zip'


def catalog_digest(data):
    import hashlib
    import json
    critical = dict(cards=data['cards'], skills=[{k: v for k, v in row.items() if k != '说明'}
                                                for row in data['skills']])
    return hashlib.sha256(json.dumps(critical, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':')).encode('utf-8')).hexdigest()
