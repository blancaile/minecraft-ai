"""Boot the actual distributable on a disposable Fabric server. No Jev credential/network call.

Only copies the final jar to mods/: verifies nested dependencies rather than relying on
Loom's development runtime. Commands target a new isolated world under build/.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

LAUNCHER = "https://meta.fabricmc.net/v2/versions/loader/1.21.3/0.18.4/1.0.1/server/jar"


def main() -> None:
    artifact = Path(sys.argv[1]).resolve()
    if not artifact.is_file():
        raise RuntimeError(f"JAR missing: {artifact}")
    root = Path("build/server-smoke").resolve()
    if root.exists():
        raise RuntimeError("Smoke directory already exists; run clean before repeating")
    (root / "mods").mkdir(parents=True)
    shutil.copy2(artifact, root / "mods" / artifact.name)
    urllib.request.urlretrieve(LAUNCHER, root / "server.jar")
    # Reuse the repository's existing test-fixture EULA acknowledgement.
    shutil.copy2("harness/gate_a/fixtures/server-1.21.3-v1/payload/eula.txt", root / "eula.txt")
    (root / "server.properties").write_text(
        "online-mode=false\nserver-ip=127.0.0.1\nserver-port=25579\n"
        "enable-rcon=false\nmax-players=4\nview-distance=3\nsimulation-distance=3\n"
        "level-type=minecraft:flat\ngenerate-structures=false\nspawn-protection=0\n"
        'generator-settings={"layers":[{"block":"minecraft:bedrock","height":1},'
        '{"block":"minecraft:stone","height":2},{"block":"minecraft:grass_block","height":1}],'
        '"biome":"minecraft:plains","lakes":false,"features":false}\n'
        "level-seed=314159\nsync-chunk-writes=true\n", encoding="utf-8")
    messages: queue.Queue[str] = queue.Queue()
    process = subprocess.Popen(["java", "-Xms512M", "-Xmx2G", "-jar", "server.jar", "nogui"],
        cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="strict", bufsize=1)
    def read() -> None:
        assert process.stdout
        with (root / "console.log").open("w", encoding="utf-8") as output:
            for line in process.stdout:
                output.write(line); output.flush()
                messages.put(line)
                print(line, end="", flush=True)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    def wait_for(text: str, seconds: float = 30) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Server exited {process.returncode} waiting for {text!r}")
            try:
                line = messages.get(timeout=0.2)
            except queue.Empty:
                continue
            if text in line:
                return
        raise TimeoutError(f"No server event {text!r}")
    def send(command: str) -> None:
        assert process.stdin
        process.stdin.write(command + "\n"); process.stdin.flush()
    try:
        wait_for('Done (', 300)
        send('gamerule doMobSpawning false')
        send('gamerule doDaylightCycle false')
        send('forceload add -16 -16 16 16')
        time.sleep(2)
        send('fill -10 80 -10 10 80 10 minecraft:stone')
        send('fill -10 81 -10 10 84 10 minecraft:air')
        send('jev spawn 0.5 81 0.5')
        wait_for('Spawned JevBot')
        time.sleep(1)
        send('data get entity JevBot Pos')
        send('jev observe')
        wait_for('Observation written:')
        send('jev smoke')
        wait_for('SMOKE_PASSED', 30)
        send('data get entity JevBot Pos')
        send('jev goal 0.5 81 8.5')
        send('jev start')
        wait_for('Set apiKey in config/jev-control.json')
        send('jev step FORWARD')
        wait_for('MANUAL_COMPLETED')
        send('jev step FORWARD')
        send('jev stop')
        wait_for('state=CANCELLED')
        send('jev despawn')
        wait_for('Despawn requested')
        time.sleep(1)
        send('jev spawn 2.5 81 0.5')
        wait_for('Spawned JevBot')
        send('jev despawn')
        wait_for('Despawn requested')
        send('stop')
        code = process.wait(timeout=60)
        reader.join(timeout=5)
        if code != 0:
            raise RuntimeError(f"Server exit code {code}")
        records = [json.loads(line) for file in (root / 'logs/jev-control').glob('*.jsonl')
                   for line in file.read_text(encoding='utf-8').splitlines()]
        assert any(x['event'] == 'terminal' and x['data']['status'] == 'SMOKE_PASSED' for x in records)
        assert any(x['event'] == 'terminal' and x['data']['status'] == 'CANCELLED' for x in records)
        assert any(x['event'] == 'result' and sum(v*v for v in x['data']['displacement']) > 0.0025 for x in records)
        assert not any(x['event'] == 'decision' for x in records), 'No model should be invoked in this smoke'
        summary = {'result': 'PASS', 'jar_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                   'minecraft': '1.21.3', 'fabric_loader': '0.18.4', 'model_invoked': False,
                   'checks': ['bundled dependencies', 'dedicated server boot', 'spawn', 'observation',
                              'physical movement', 'finite input release', 'missing key rejection',
                              'cancel', 'despawn and respawn', 'clean shutdown']}
        (root / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, indent=2))
    finally:
        if process.poll() is None:
            send('stop')
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)

if __name__ == '__main__':
    main()
