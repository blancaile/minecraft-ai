"""Boot the actual distributable on an isolated Paper server. No Jev credential/network call.

Only copies the final jar to plugins/. Never connects to the shared server.
"""
from __future__ import annotations
import hashlib
import argparse
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

SERVER_SHA256 = 'e708e8c132dc143ffd73528cccb9532e2eb17628b1a0eee74469bf466c7003f8'
LAUNCHER = f'https://fill-data.papermc.io/v1/objects/{SERVER_SHA256}/paper-1.21.11-116.jar'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--server-jar', type=Path)
    parser.add_argument('--extra-plugin', type=Path, action='append', default=[], help='Optional compatibility-test plugin JAR; never distributed with Jev')
    parser.add_argument('--multiverse-first-spawn', action='store_true', help='Reproduce shared-server first-join relocation in the isolated fixture')
    options = parser.parse_args()
    artifact = options.artifact.resolve()
    if not artifact.is_file():
        raise RuntimeError(f"JAR missing: {artifact}")
    root = Path('.runtime-harness') / ('paper-smoke-' + uuid.uuid4().hex[:12])
    root = root.resolve()
    (root / 'plugins').mkdir(parents=True)
    shutil.copy2(artifact, root / 'plugins' / artifact.name)
    for companion in options.extra_plugin:
        if companion.name == artifact.name:
            raise RuntimeError('Companion must not replace the Jev artifact')
        shutil.copy2(companion, root / 'plugins' / companion.name)
    if options.multiverse_first_spawn:
        if not any(p.name.startswith('multiverse-core-') for p in options.extra_plugin):
            raise RuntimeError('--multiverse-first-spawn requires a Multiverse companion JAR')
        config = root / 'plugins/Multiverse-Core/config.yml'
        config.parent.mkdir(parents=True)
        config.write_text("spawn:\n  first-spawn-override: true\n  first-spawn-location: world\n  enable-join-destination: false\n", encoding='utf-8')
    cached = options.server_jar or Path('.runtime-harness/cache/paper-1.21.11-116.jar')
    if not cached.is_file():
        cached.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(LAUNCHER, headers={'User-Agent': 'JevControl/0.2 (https://github.com/blancaile/minecraft-ai)'})
        with urllib.request.urlopen(request, timeout=60) as response, cached.open('wb') as output:
            shutil.copyfileobj(response, output)
    if hashlib.sha256(cached.read_bytes()).hexdigest() != SERVER_SHA256:
        raise RuntimeError('Paper server checksum mismatch')
    shutil.copy2(cached, root / 'server.jar')
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
    print(f'EVIDENCE_DIRECTORY={root}', flush=True)
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
                if any(s in line for s in ('Jev', 'JEV_', 'ERROR', 'Exception', 'Done (')):
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
    def inbox(command: str, *, expired: bool = False) -> dict:
        request_id = str(uuid.uuid4())
        folder = root / 'plugins/JevControl/inbox'
        stage = folder / (request_id + '.upload')
        stage.write_text(json.dumps({'id': request_id, 'command': command,
            'expires_at_ms': int(time.time() * 1000) + (-1000 if expired else 10000)}), encoding='utf-8')
        stage.rename(folder / (request_id + '.json'))
        receipt = root / 'plugins/JevControl/receipts' / (request_id + '.json')
        deadline = time.monotonic() + 15
        while not receipt.is_file() and time.monotonic() < deadline:
            time.sleep(0.1)
        result = json.loads(receipt.read_text(encoding='utf-8'))
        assert result['id'] == request_id
        return result
    def observe() -> dict:
        reply = inbox('jev observe')
        assert reply['success'], reply
        files = sorted((root / 'plugins/JevControl/traces').glob('observe-*.jsonl'), key=lambda p: p.stat().st_mtime_ns)
        return json.loads(files[-1].read_text(encoding='utf-8'))['data']
    try:
        wait_for('Done (', 300)
        if options.multiverse_first_spawn:
            assert 'first-spawn-override: true' in (root / 'plugins/Multiverse-Core/config.yml').read_text(encoding='utf-8')
            assert '[Multiverse-Core] Enabling Multiverse-Core' in (root / 'console.log').read_text(encoding='utf-8')
        reply = inbox('jev status')
        assert reply['success'] and 'bot=none' in reply['output'][0], reply
        assert not inbox('jev status', expired=True)['success']
        assert not inbox('stop')['success']
        assert not inbox('jev site MissingPlayer')['success']
        assert not inbox('jev spawn-near MissingPlayer')['success']
        send('gamerule doMobSpawning false')
        send('gamerule doDaylightCycle false')
        send('forceload add -16 -16 16 16')
        time.sleep(2)
        send('fill -10 80 -10 10 80 10 minecraft:stone')
        send('fill -10 81 -10 10 84 10 minecraft:air')
        send('jev spawn 0.5 81 0.5')
        wait_for('Spawned JevBot')
        time.sleep(1)
        site_reply = inbox('jev site JevBot')
        assert site_reply['success'], site_reply
        site = json.loads(site_reply['output'][0].removeprefix('JEV_OK '))
        assert site['world'] == 'world' and site['yaw'] == 0 and site['terrain_changed'] is False, site
        assert site['spawn_position'][1] == 81 and max(abs(site['spawn_position'][i] - site['player_position'][i]) for i in (0, 2)) <= 10.5, site
        send('data get entity JevBot Pos')
        send('jev observe')
        wait_for('Observation written:')
        send('jev smoke')
        wait_for('SMOKE_PASSED', 30)
        send('data get entity JevBot Pos')
        send('jev goal 0.5 81 8.5')
        send('jev start')
        wait_for('Set apiKey in plugins/JevControl/jev-control.json')
        send('jev step FORWARD')
        wait_for('MANUAL_COMPLETED')
        send('jev step FORWARD')
        send('jev stop')
        wait_for('state=CANCELLED')
        # Reload with a live bot; old classloader must remove its body and tasks.
        send('bukkit:reload confirm')
        wait_for('JEV_DISABLED')
        wait_for('JEV_READY', 60)
        send('jev status')
        wait_for('bot=none')
        send('jev spawn 2.5 81 0.5')
        wait_for('Spawned JevBot')
        time.sleep(1)
        send('jev smoke')
        wait_for('SMOKE_PASSED')
        send('jev despawn')
        wait_for('Despawn requested')
        time.sleep(1)
        send('jev spawn 2.5 81 0.5')
        wait_for('Spawned JevBot')
        send('jev despawn')
        wait_for('Despawn requested')
        # Gravity and collision use game state, not only adapter success messages.
        send('jev spawn 0.5 84 0.5')
        wait_for('Spawned JevBot')
        time.sleep(1.5)
        state = observe()
        assert abs(state['self']['position'][1] - 81) < 0.01 and state['self']['on_ground'], state['self']
        send('fill -2 81 4 2 84 4 minecraft:stone')
        wait_for('Successfully filled')
        for _ in range(8):
            assert inbox('jev step FORWARD')['success']
            wait_for('MANUAL_COMPLETED')
        blocked = observe()
        assert blocked['self']['position'][2] < 3.71, blocked['self']
        assert any(c['knowledge'] == 'UNKNOWN' for c in blocked['local_cells'])
        assert inbox('jev step TURN_LEFT')['success']
        wait_for('MANUAL_COMPLETED')
        assert abs(observe()['self']['yaw'] + 15) < 0.01
        assert inbox('jev step JUMP_FORWARD')['success']
        wait_for('MANUAL_COMPLETED')
        send('jev despawn')
        wait_for('Despawn requested')
        send('stop')
        code = process.wait(timeout=60)
        reader.join(timeout=5)
        if code != 0:
            raise RuntimeError(f"Server exit code {code}")
        records = [json.loads(line) for file in (root / 'plugins/JevControl/traces').glob('*.jsonl')
                   for line in file.read_text(encoding='utf-8').splitlines()]
        assert any(x['event'] == 'terminal' and x['data']['status'] == 'SMOKE_PASSED' for x in records)
        assert any(x['event'] == 'terminal' and x['data']['status'] == 'CANCELLED' for x in records)
        assert any(x['event'] == 'result' and sum(v*v for v in x['data']['displacement']) > 0.0025 for x in records)
        assert not any(x['event'] == 'decision' for x in records), 'No model should be invoked in this smoke'
        assert any(x['event'] == 'result' and x['data']['outcome'] == 'BLOCKED' for x in records)
        assert any(x['event'] == 'result' and x['data']['action'] == 'JUMP_FORWARD' and x['data']['displacement'][1] > 0 for x in records)
        assert all(x['data']['actual_ticks'] in (4, 8) for x in records if x['event'] == 'result')
        summary = {'result': 'PASS', 'jar_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
                   'minecraft': '1.21.11', 'paper_build': 116, 'model_invoked': False,
                   'extra_plugins': [{'name': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in options.extra_plugin],
                   'multiverse_first_spawn_override': options.multiverse_first_spawn,
                   'checks': ['single plugin JAR', 'dedicated server boot', 'spawn', 'observation',
                              'physical movement', 'finite input release', 'missing key rejection',
                              'cancel', 'despawn and respawn', 'reload cleanup and respawn', 'gravity',
                              'wall collision', 'occlusion UNKNOWN', 'rotation', 'jump', 'exact bounded ticks',
                              'inbox receipt', 'expired command rejection', 'foreign command rejection', 'clean shutdown',
                              'nearby fixture inspection', 'offline reference rejection']}
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
