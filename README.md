# minecraft-ai

jevでminecraftの疑似プレイヤーを作る。
jevのapiキーは、.envに"jev_api_key": "value"という形で保存されている。

## JEV API の疎通確認

Python 3.10 以上で、プロジェクト直下から実行する。

```powershell
python .\jev_client.py
```

`jev_client.py` は `.env` の `jev_api_key` を読み、Jev の `systemone` API に
Minecraft の次の行動を問い合わせる。追加パッケージは不要。
