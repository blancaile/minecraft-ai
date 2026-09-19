from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from harness.gate_a.fixture import (
    CONTROL_DIR,
    ManagedProcess,
    FixtureError,
    _pid_exists,
    cleanup_run,
    prepare_run,
    seal_fixture,
    sha256_file,
    tree_digest,
    validate_network_policy,
    verify_fixture,
)


SERVER_PROPERTIES = """\
broadcast-console-to-ops=false
broadcast-rcon-to-ops=false
enable-query=false
enable-rcon=false
online-mode=false
prevent-proxy-connections=true
rcon.password=
server-ip=127.0.0.1
server-port=0
"""


class FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "server.properties").write_text(SERVER_PROPERTIES, encoding="utf-8")
        (self.source / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        (self.source / "whitelist.json").write_text("[]\n", encoding="utf-8")
        (self.source / "ops.json").write_text("[]\n", encoding="utf-8")
        self.lock = self.root / "dependencies.lock.json"
        self.lock.write_text(
            json.dumps(
                {
                    "schema_version": "gate-a-dependencies-v1.0",
                    "versions": {
                        "minecraft": "1.21.3",
                        "fabric_loader": "0.18.4",
                        "fabric_api": "0.114.1+1.21.3",
                        "java_major": 21,
                    },
                    "artifacts": [
                        {
                            "name": name,
                            "source": f"https://example.invalid/{index}.jar",
                            "bytes": index + 1,
                            "sha256": f"{index + 1:x}" * 64,
                        }
                        for index, name in enumerate(
                            [
                                "minecraft-server-1.21.3",
                                "fabric-loader-0.18.4",
                                "fabric-intermediary-1.21.3",
                                "fabric-api-0.114.1+1.21.3",
                                "temurin-jdk-21.0.12.1+1-linux-x64",
                            ]
                        )
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.fixture = self.root / "fixture"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def seal(self) -> dict[str, object]:
        return seal_fixture(self.source, self.fixture, self.lock, "test-fixture", "v1")

    def prepare(self, run_id: str = "run-001") -> Path:
        self.seal()
        java = {"version": "21.0.1", "vendor": "test", "executable_sha256": "b" * 64}
        with mock.patch("harness.gate_a.fixture._java_provenance", return_value=java):
            return prepare_run(self.fixture, self.root / "runs", run_id)

    def test_seal_and_verify_records_fixed_hashes(self) -> None:
        manifest = self.seal()
        verified = verify_fixture(self.fixture)
        self.assertEqual(manifest, verified)
        self.assertEqual(manifest["payload_sha256"], tree_digest(self.fixture / "payload"))
        self.assertEqual(
            manifest["dependency_manifest_sha256"],
            sha256_file(self.fixture / "dependencies.lock.json"),
        )
        self.assertEqual(manifest["payload_sha256"], manifest["canonical_snapshot_sha256"])

    def test_verify_rejects_payload_drift(self) -> None:
        self.seal()
        (self.fixture / "payload" / "eula.txt").write_text("eula=false\n", encoding="utf-8")
        with self.assertRaisesRegex(FixtureError, "inventory mismatch"):
            verify_fixture(self.fixture)

    def test_verify_rejects_dependency_lock_drift(self) -> None:
        self.seal()
        lock_path = self.fixture / "dependencies.lock.json"
        lock_path.write_text(lock_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(FixtureError, "dependency manifest checksum mismatch"):
            verify_fixture(self.fixture)

    def test_seal_rejects_secret_file(self) -> None:
        (self.source / ".env").write_text("key=value\n", encoding="utf-8")
        with self.assertRaisesRegex(FixtureError, "secret-like"):
            self.seal()

    def test_seal_rejects_secret_content(self) -> None:
        (self.source / "notes.txt").write_text("access_token=do-not-store\n", encoding="utf-8")
        with self.assertRaisesRegex(FixtureError, "secret-like content"):
            self.seal()

    def test_seal_rejects_non_loopback_server(self) -> None:
        (self.source / "server.properties").write_text(
            SERVER_PROPERTIES.replace("server-ip=127.0.0.1", "server-ip=0.0.0.0"),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(FixtureError, "server-ip"):
            self.seal()

    def test_network_policy_rejects_each_exposed_service(self) -> None:
        unsafe_values = {
            "server-ip=127.0.0.1": "server-ip=0.0.0.0",
            "online-mode=false": "online-mode=true",
            "enable-query=false": "enable-query=true",
            "enable-rcon=false": "enable-rcon=true",
            "prevent-proxy-connections=true": "prevent-proxy-connections=false",
        }
        original = (self.source / "server.properties").read_text(encoding="utf-8")
        for safe, unsafe in unsafe_values.items():
            with self.subTest(setting=unsafe):
                (self.source / "server.properties").write_text(
                    original.replace(safe, unsafe), encoding="utf-8"
                )
                with self.assertRaises(FixtureError):
                    validate_network_policy(self.source)
        (self.source / "server.properties").write_text(original, encoding="utf-8")

    @unittest.skipIf(os.name == "nt", "creating symlinks may require Windows developer mode")
    def test_seal_rejects_symlink(self) -> None:
        (self.source / "linked").symlink_to(self.source / "eula.txt")
        with self.assertRaisesRegex(FixtureError, "symlinks"):
            self.seal()

    def test_prepare_uses_new_directory_and_reproducible_snapshot(self) -> None:
        self.seal()
        java = {"version": "21.0.1", "vendor": "test", "executable_sha256": "b" * 64}
        with mock.patch("harness.gate_a.fixture._java_provenance", return_value=java):
            first = prepare_run(self.fixture, self.root / "runs", "run-001")
            second = prepare_run(self.fixture, self.root / "runs", "run-002")
            with self.assertRaisesRegex(FixtureError, "already exists"):
                prepare_run(self.fixture, self.root / "runs", "run-001")
        first_provenance = json.loads((first / CONTROL_DIR / "provenance.json").read_text())
        second_provenance = json.loads((second / CONTROL_DIR / "provenance.json").read_text())
        self.assertTrue(first_provenance["fixture"]["fresh_copy"])
        self.assertEqual(
            first_provenance["fixture"]["copied_payload_sha256"],
            second_provenance["fixture"]["copied_payload_sha256"],
        )
        self.assertEqual(len(first_provenance["dependency_artifacts"]), 5)
        self.assertEqual(
            {item["name"] for item in first_provenance["dependency_artifacts"]},
            {
                "minecraft-server-1.21.3",
                "fabric-loader-0.18.4",
                "fabric-intermediary-1.21.3",
                "fabric-api-0.114.1+1.21.3",
                "temurin-jdk-21.0.12.1+1-linux-x64",
            },
        )
        (first / "payload" / "world-state.dat").write_text("changed", encoding="utf-8")
        self.assertFalse((second / "payload" / "world-state.dat").exists())

    def test_prepare_failure_removes_staging_directory(self) -> None:
        self.seal()
        with mock.patch(
            "harness.gate_a.fixture._java_provenance", side_effect=FixtureError("bad Java")
        ):
            with self.assertRaisesRegex(FixtureError, "bad Java"):
                prepare_run(self.fixture, self.root / "runs", "run-failed")
        self.assertEqual(list((self.root / "runs").iterdir()), [])

    def test_managed_process_stops_only_owned_pid_and_filters_secrets(self) -> None:
        run_dir = self.prepare()
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            command = [
                sys.executable,
                "-c",
                "import os,time; print(os.getenv('M1_002_API_KEY')); time.sleep(60)",
            ]
            with mock.patch.dict(os.environ, {"M1_002_API_KEY": "must-not-leak"}):
                owner = ManagedProcess(run_dir, command)
                owned_pid = owner.start()
                self.assertNotEqual(owned_pid, unrelated.pid)
                time.sleep(0.1)
                owner.stop(timeout_seconds=2)
            self.assertIsNone(unrelated.poll())
            log = (run_dir / CONTROL_DIR / "server-process.log").read_text(encoding="utf-8")
            self.assertNotIn("must-not-leak", log)
            state = json.loads((run_dir / CONTROL_DIR / "process.json").read_text())
            self.assertEqual(state["pid"], owned_pid)
            self.assertEqual(state["state"], "stopped")
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)

    def test_extra_secret_environment_is_rejected_before_start(self) -> None:
        run_dir = self.prepare()
        owner = ManagedProcess(
            run_dir,
            [sys.executable, "-c", "pass"],
            {"ACCESS_TOKEN": "forbidden"},
        )
        with self.assertRaisesRegex(FixtureError, "secret-like"):
            owner.start()

    def test_process_is_stopped_if_state_record_cannot_be_written(self) -> None:
        run_dir = self.prepare()
        owner = ManagedProcess(run_dir, [sys.executable, "-c", "import time; time.sleep(60)"])
        with mock.patch(
            "harness.gate_a.fixture.atomic_write_json", side_effect=OSError("disk full")
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                owner.start()
        self.assertIsNotNone(owner.process)
        self.assertIsNotNone(owner.process.poll())

    @unittest.skipUnless(os.name == "nt", "Windows-specific non-signaling PID probe")
    def test_pid_probe_does_not_send_signal_on_windows(self) -> None:
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with mock.patch(
                "harness.gate_a.fixture.os.kill",
                side_effect=AssertionError("Windows PID probes must not send signals"),
            ):
                self.assertTrue(_pid_exists(process.pid))
                self.assertIsNone(process.poll())
                process.terminate()
                process.wait(timeout=5)
                self.assertFalse(_pid_exists(process.pid))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def test_cleanup_refuses_live_process_then_removes_exact_run(self) -> None:
        run_dir = self.prepare()
        sibling = run_dir.parent / "do-not-remove"
        sibling.mkdir()
        owner = ManagedProcess(run_dir, [sys.executable, "-c", "import time; time.sleep(60)"])
        owner.start()
        try:
            with self.assertRaisesRegex(FixtureError, "live run process"):
                cleanup_run(run_dir.parent, run_dir.name)
        finally:
            owner.stop(timeout_seconds=2)
        cleanup_run(run_dir.parent, run_dir.name)
        self.assertFalse(run_dir.exists())
        self.assertTrue(sibling.exists())

    def test_cleanup_rejects_mismatched_provenance(self) -> None:
        run_dir = self.prepare()
        provenance_path = run_dir / CONTROL_DIR / "provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["run_id"] = "another-run"
        provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
        with self.assertRaisesRegex(FixtureError, "invalid Gate A provenance"):
            cleanup_run(run_dir.parent, run_dir.name)
        self.assertTrue(run_dir.exists())


if __name__ == "__main__":
    unittest.main()
