"""Hermetic Gate A fixture preparation and exact-process lifecycle helpers.

This module deliberately does not know about a body candidate.  It seals a
small, immutable server template, verifies it before every run, and copies it
to a new run directory.  The external controller introduced by M1-004 can use
``ManagedProcess`` without importing candidate code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


FIXTURE_SCHEMA_VERSION = "gate-a-fixture-v1.0"
PROVENANCE_SCHEMA_VERSION = "gate-a-run-provenance-v1.0"
CONTROL_DIR = ".gate-a"
MANIFEST_NAME = "fixture-manifest.json"
DEPENDENCY_LOCK_NAME = "dependencies.lock.json"
PAYLOAD_NAME = "payload"
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SECRET_NAME_RE = re.compile(
    r"(^|[._-])(api[_-]?key|secret|token|password|credential|private[_-]?key)([._-]|$)",
    re.IGNORECASE,
)
SECRET_FILE_NAMES = {".env", "id_rsa", "id_ed25519", "credentials.json"}
SECRET_CONTENT_RE = re.compile(
    rb"(?im)^\s*(?:api[_-]?key|access[_-]?token|secret|password|credential)\s*[:=]\s*[^\s#]+"
)
SAFE_ENV_NAMES = {
    "COMSPEC",
    "JAVA_HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "TZ",
    "WINDIR",
}
CONFIG_PATHS = ("eula.txt", "server.properties", "whitelist.json", "ops.json")


class FixtureError(ValueError):
    """Raised when fixture provenance or isolation cannot be proven."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureError(f"cannot read JSON {path.name}: {error}") from error


def _safe_relative_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise FixtureError(f"directory does not exist: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise FixtureError(f"symlinks are forbidden in fixtures: {path.relative_to(root)}")
        if path.is_file():
            files.append(path.relative_to(root))
        elif not path.is_dir():
            raise FixtureError(f"special files are forbidden in fixtures: {path.relative_to(root)}")
    return sorted(files, key=lambda item: item.as_posix())


def file_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": relative.as_posix(),
            "bytes": (root / relative).stat().st_size,
            "sha256": sha256_file(root / relative),
        }
        for relative in _safe_relative_files(root)
    ]


def inventory_digest(inventory: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json_bytes(list(inventory))).hexdigest()


def tree_digest(root: Path) -> str:
    return inventory_digest(file_inventory(root))


def _validate_identifier(value: str, label: str) -> None:
    if not IDENTIFIER_RE.fullmatch(value):
        raise FixtureError(f"invalid {label}: {value!r}")


def _parse_properties(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise FixtureError(f"invalid server.properties line {number}")
        key, value = line.split("=", 1)
        if key in result:
            raise FixtureError(f"duplicate server.properties key: {key}")
        result[key] = value
    return result


def validate_network_policy(payload: Path) -> None:
    properties_path = payload / "server.properties"
    if not properties_path.is_file():
        raise FixtureError("fixture requires server.properties")
    properties = _parse_properties(properties_path)
    required = {
        "server-ip": "127.0.0.1",
        "server-port": "0",
        "online-mode": "false",
        "enable-query": "false",
        "enable-rcon": "false",
        "broadcast-rcon-to-ops": "false",
        "broadcast-console-to-ops": "false",
        "prevent-proxy-connections": "true",
    }
    for key, expected in required.items():
        actual = properties.get(key)
        if actual != expected:
            raise FixtureError(f"network policy requires {key}={expected}, got {actual!r}")
    if properties.get("rcon.password", ""):
        raise FixtureError("rcon.password must be empty")


def validate_secret_policy(root: Path) -> None:
    for relative in _safe_relative_files(root):
        name = relative.name
        if name.lower() in SECRET_FILE_NAMES or SECRET_NAME_RE.search(name):
            raise FixtureError(f"secret-like file is forbidden: {relative.as_posix()}")
        path = root / relative
        if path.stat().st_size <= 1024 * 1024 and SECRET_CONTENT_RE.search(path.read_bytes()):
            raise FixtureError(f"secret-like content is forbidden: {relative.as_posix()}")


def config_digest(payload: Path, config_paths: Iterable[str] = CONFIG_PATHS) -> str:
    records: list[dict[str, Any]] = []
    for raw_path in sorted(config_paths):
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise FixtureError(f"unsafe config path: {raw_path}")
        path = payload / relative
        if not path.is_file():
            raise FixtureError(f"missing fixture config: {raw_path}")
        records.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    return inventory_digest(records)


def validate_dependency_lock(lock: Mapping[str, Any]) -> None:
    required_versions = {
        "minecraft": "1.21.3",
        "fabric_loader": "0.18.4",
        "fabric_api": "0.114.1+1.21.3",
        "java_major": 21,
    }
    if lock.get("schema_version") != "gate-a-dependencies-v1.0":
        raise FixtureError("unsupported dependency lock schema")
    versions = lock.get("versions")
    if not isinstance(versions, dict):
        raise FixtureError("dependency lock requires versions")
    for key, expected in required_versions.items():
        if versions.get(key) != expected:
            raise FixtureError(f"dependency version {key} must be {expected!r}")
    artifacts = lock.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise FixtureError("dependency lock requires artifacts")
    names: set[str] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise FixtureError("dependency artifact must be an object")
        name = artifact.get("name")
        sha256 = artifact.get("sha256")
        if not isinstance(name, str) or name in names:
            raise FixtureError(f"invalid or duplicate dependency name: {name!r}")
        if not isinstance(sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise FixtureError(f"invalid dependency SHA-256: {name}")
        if not isinstance(artifact.get("source"), str) or not artifact["source"].startswith("https://"):
            raise FixtureError(f"dependency source must be HTTPS: {name}")
        if not isinstance(artifact.get("bytes"), int) or artifact["bytes"] <= 0:
            raise FixtureError(f"dependency byte size must be positive: {name}")
        names.add(name)
    required_names = {
        "minecraft-server-1.21.3",
        "fabric-loader-0.18.4",
        "fabric-intermediary-1.21.3",
        "fabric-api-0.114.1+1.21.3",
        "temurin-jdk-21.0.12.1+1-linux-x64",
    }
    if names != required_names:
        raise FixtureError(
            f"dependency set mismatch (missing={sorted(required_names - names)}, "
            f"extra={sorted(names - required_names)})"
        )


def seal_fixture(
    source: Path,
    fixture: Path,
    dependency_lock: Path,
    fixture_id: str,
    fixture_version: str,
) -> dict[str, Any]:
    """Create a sealed fixture without overwriting an existing target."""
    _validate_identifier(fixture_id, "fixture_id")
    _validate_identifier(fixture_version, "fixture_version")
    if fixture.exists():
        raise FixtureError(f"fixture already exists: {fixture}")
    validate_secret_policy(source)
    validate_network_policy(source)
    lock = load_json(dependency_lock)
    if not isinstance(lock, dict):
        raise FixtureError("dependency lock must be an object")
    validate_dependency_lock(lock)

    fixture.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{fixture.name}.", dir=fixture.parent))
    try:
        payload = staging / PAYLOAD_NAME
        shutil.copytree(source, payload)
        shutil.copy2(dependency_lock, staging / DEPENDENCY_LOCK_NAME)
        inventory = file_inventory(payload)
        lock_hash = sha256_file(staging / DEPENDENCY_LOCK_NAME)
        manifest = {
            "schema_version": FIXTURE_SCHEMA_VERSION,
            "fixture_id": fixture_id,
            "fixture_version": fixture_version,
            "versions": lock["versions"],
            "payload_sha256": inventory_digest(inventory),
            "canonical_snapshot_sha256": inventory_digest(inventory),
            "effective_config_sha256": config_digest(payload),
            "dependency_manifest_sha256": lock_hash,
            "files": inventory,
            "isolation": {
                "fresh_copy_required": True,
                "runtime_network": "loopback_only",
                "secrets": "forbidden",
                "world_policy": "new_from_fixed_seed",
            },
        }
        atomic_write_json(staging / MANIFEST_NAME, manifest)
        os.replace(staging, fixture)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_fixture(fixture: Path) -> dict[str, Any]:
    manifest = load_json(fixture / MANIFEST_NAME)
    lock_path = fixture / DEPENDENCY_LOCK_NAME
    payload = fixture / PAYLOAD_NAME
    if not isinstance(manifest, dict) or manifest.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise FixtureError("unsupported fixture manifest schema")
    for field in (
        "fixture_id",
        "fixture_version",
        "versions",
        "payload_sha256",
        "canonical_snapshot_sha256",
        "effective_config_sha256",
        "dependency_manifest_sha256",
        "files",
        "isolation",
    ):
        if field not in manifest:
            raise FixtureError(f"fixture manifest missing {field}")
    validate_secret_policy(payload)
    validate_network_policy(payload)
    lock = load_json(lock_path)
    if not isinstance(lock, dict):
        raise FixtureError("dependency lock must be an object")
    validate_dependency_lock(lock)
    if manifest["versions"] != lock["versions"]:
        raise FixtureError("fixture and dependency versions differ")
    if sha256_file(lock_path) != manifest["dependency_manifest_sha256"]:
        raise FixtureError("dependency manifest checksum mismatch")
    actual_inventory = file_inventory(payload)
    if actual_inventory != manifest["files"]:
        raise FixtureError("fixture file inventory mismatch")
    actual_digest = inventory_digest(actual_inventory)
    if actual_digest != manifest["payload_sha256"]:
        raise FixtureError("fixture payload checksum mismatch")
    if actual_digest != manifest["canonical_snapshot_sha256"]:
        raise FixtureError("fixture canonical snapshot mismatch")
    if config_digest(payload) != manifest["effective_config_sha256"]:
        raise FixtureError("fixture config checksum mismatch")
    isolation = manifest["isolation"]
    expected_isolation = {
        "fresh_copy_required": True,
        "runtime_network": "loopback_only",
        "secrets": "forbidden",
        "world_policy": "new_from_fixed_seed",
    }
    if isolation != expected_isolation:
        raise FixtureError("fixture isolation policy mismatch")
    return manifest


def _java_provenance(java_executable: str) -> dict[str, Any]:
    resolved = shutil.which(java_executable) if not Path(java_executable).is_absolute() else java_executable
    if not resolved:
        raise FixtureError(f"Java executable not found: {java_executable}")
    executable = Path(resolved).resolve()
    try:
        completed = subprocess.run(
            [str(executable), "-XshowSettings:properties", "-version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except OSError as error:
        raise FixtureError(f"cannot execute Java: {error}") from error
    output = f"{completed.stdout}\n{completed.stderr}"
    match = re.search(r"^\s*java\.version\s*=\s*(\S+)", output, re.MULTILINE)
    version = match.group(1) if match else ""
    if completed.returncode != 0 or not re.match(r"^(?:1\.)?21(?:\D|$)", version):
        raise FixtureError(f"Java 21 required, observed {version or 'unknown'}")
    vendor_match = re.search(r"^\s*java\.vendor\s*=\s*(.+)$", output, re.MULTILINE)
    return {
        "version": version,
        "vendor": vendor_match.group(1).strip() if vendor_match else "unknown",
        "executable_sha256": sha256_file(executable),
    }


def prepare_run(
    fixture: Path,
    runs_root: Path,
    run_id: str,
    java_executable: str = "java",
) -> Path:
    """Verify and copy a fixture to a never-before-used run directory."""
    _validate_identifier(run_id, "run_id")
    manifest = verify_fixture(fixture)
    dependencies = load_json(fixture / DEPENDENCY_LOCK_NAME)
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = runs_root / run_id
    if run_dir.exists():
        raise FixtureError(f"run directory already exists: {run_id}")
    staging = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=runs_root))
    try:
        payload = staging / PAYLOAD_NAME
        shutil.copytree(fixture / PAYLOAD_NAME, payload)
        copied_inventory = file_inventory(payload)
        copied_digest = inventory_digest(copied_inventory)
        if copied_digest != manifest["payload_sha256"]:
            raise FixtureError("fresh copy digest differs from sealed fixture")
        control = staging / CONTROL_DIR
        control.mkdir()
        provenance = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "run_id": run_id,
            "fixture": {
                "fixture_id": manifest["fixture_id"],
                "fixture_version": manifest["fixture_version"],
                "sha256": manifest["payload_sha256"],
                "fresh_copy": True,
                "copied_payload_sha256": copied_digest,
                "canonical_snapshot_sha256": manifest["canonical_snapshot_sha256"],
            },
            "environment": {
                "os": platform.platform(),
                "architecture": platform.machine(),
                "java": _java_provenance(java_executable),
                **manifest["versions"],
            },
            "effective_config_sha256": config_digest(payload),
            "dependency_manifest_sha256": manifest["dependency_manifest_sha256"],
            "dependency_artifacts": [
                {
                    "name": artifact["name"],
                    "bytes": artifact["bytes"],
                    "sha256": artifact["sha256"],
                }
                for artifact in dependencies["artifacts"]
            ],
            "network_policy": "loopback_only",
            "secret_policy": "forbidden_and_environment_allowlisted",
            "created_at": utc_now(),
        }
        atomic_write_json(control / "provenance.json", provenance)
        atomic_write_json(
            control / "lifecycle.json",
            {"schema_version": "gate-a-lifecycle-v1.0", "state": "prepared", "run_id": run_id},
        )
        os.replace(staging, run_dir)
        return run_dir
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def sanitized_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key.upper() in SAFE_ENV_NAMES}
    for key, value in (extra or {}).items():
        if SECRET_NAME_RE.search(key):
            raise FixtureError(f"secret-like environment variable is forbidden: {key}")
        environment[key] = value
    return environment


@dataclass
class ManagedProcess:
    """Own exactly one process handle; never discovers or kills by name."""

    run_dir: Path
    command: Sequence[str]
    extra_environment: Mapping[str, str] | None = None
    process: subprocess.Popen[bytes] | None = None
    _log_handle: Any = None

    @property
    def state_path(self) -> Path:
        return self.run_dir / CONTROL_DIR / "process.json"

    def start(self) -> int:
        if self.process is not None:
            raise FixtureError("process owner is single-use")
        if not self.command:
            raise FixtureError("server command must not be empty")
        control = self.run_dir / CONTROL_DIR
        payload = self.run_dir / PAYLOAD_NAME
        if not control.is_dir() or not payload.is_dir():
            raise FixtureError("run directory is not prepared")
        for argument in self.command:
            if "\n" in argument or "\r" in argument:
                raise FixtureError("command arguments must be single-line")
        log_path = control / "server-process.log"
        self._log_handle = log_path.open("ab", buffering=0)
        try:
            self.process = subprocess.Popen(
                list(self.command),
                cwd=payload,
                env=sanitized_environment(self.extra_environment),
                stdin=subprocess.DEVNULL,
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                shell=False,
            )
        except BaseException:
            self._log_handle.close()
            self._log_handle = None
            raise
        try:
            atomic_write_json(
                self.state_path,
                {
                    "schema_version": "gate-a-process-v1.0",
                    "state": "running",
                    "pid": self.process.pid,
                    "started_at": utc_now(),
                },
            )
        except BaseException:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self._log_handle.close()
            self._log_handle = None
            raise
        return self.process.pid

    def stop(self, timeout_seconds: float = 10.0) -> int:
        if self.process is None:
            raise FixtureError("process was not started by this owner")
        process = self.process
        forced = False
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                forced = True
                process.kill()
                process.wait(timeout=timeout_seconds)
        exit_code = process.returncode
        try:
            atomic_write_json(
                self.state_path,
                {
                    "schema_version": "gate-a-process-v1.0",
                    "state": "stopped",
                    "pid": process.pid,
                    "exit_code": exit_code,
                    "forced": forced,
                    "stopped_at": utc_now(),
                },
            )
        finally:
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
        return exit_code

    def __enter__(self) -> "ManagedProcess":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.stop()


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        # On Windows, signal 0 is CTRL_C_EVENT.  Using os.kill(pid, 0) as a
        # liveness probe can therefore interrupt every process attached to the
        # same console, including the Codex app-server running this harness.
        # Query the process handle without sending any signal instead.
        import ctypes
        from ctypes import wintypes

        synchronize = 0x00100000
        wait_object_0 = 0x00000000
        wait_timeout = 0x00000102
        error_access_denied = 5
        error_invalid_parameter = 87

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        if pid > 0xFFFFFFFF:
            return False
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == error_access_denied:
                return True
            if error == error_invalid_parameter:
                return False
            raise ctypes.WinError(error)
        try:
            wait_result = kernel32.WaitForSingleObject(handle, 0)
            if wait_result == wait_timeout:
                return True
            if wait_result == wait_object_0:
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_run(runs_root: Path, run_id: str) -> None:
    """Delete one validated run directory, never a computed broad target."""
    _validate_identifier(run_id, "run_id")
    root = runs_root.resolve()
    target = (root / run_id).resolve()
    if target.parent != root or target == root:
        raise FixtureError("cleanup target escapes runs root")
    if not target.is_dir():
        raise FixtureError(f"run directory does not exist: {run_id}")
    provenance_path = target / CONTROL_DIR / "provenance.json"
    if not provenance_path.is_file():
        raise FixtureError("refusing to remove a directory without Gate A provenance")
    provenance = load_json(provenance_path)
    if not isinstance(provenance, dict) or (
        provenance.get("schema_version") != PROVENANCE_SCHEMA_VERSION
        or provenance.get("run_id") != run_id
        or provenance.get("fixture", {}).get("fresh_copy") is not True
    ):
        raise FixtureError("refusing to remove a directory with invalid Gate A provenance")
    process_path = target / CONTROL_DIR / "process.json"
    if process_path.exists():
        state = load_json(process_path)
        if isinstance(state, dict) and state.get("state") == "running":
            pid = state.get("pid")
            if isinstance(pid, int) and _pid_exists(pid):
                raise FixtureError(f"refusing to remove live run process PID {pid}")
    shutil.rmtree(target)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate A hermetic fixture manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seal = subparsers.add_parser("seal", help="seal a source template into a new fixture")
    seal.add_argument("--source", type=Path, required=True)
    seal.add_argument("--fixture", type=Path, required=True)
    seal.add_argument("--dependency-lock", type=Path, required=True)
    seal.add_argument("--fixture-id", required=True)
    seal.add_argument("--fixture-version", required=True)

    verify = subparsers.add_parser("verify", help="verify fixture content and policy")
    verify.add_argument("--fixture", type=Path, required=True)

    prepare = subparsers.add_parser("prepare", help="create a fresh isolated run copy")
    prepare.add_argument("--fixture", type=Path, required=True)
    prepare.add_argument("--runs-root", type=Path, required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--java", default="java")

    cleanup = subparsers.add_parser("cleanup", help="remove one stopped, provenanced run")
    cleanup.add_argument("--runs-root", type=Path, required=True)
    cleanup.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "seal":
            manifest = seal_fixture(
                args.source,
                args.fixture,
                args.dependency_lock,
                args.fixture_id,
                args.fixture_version,
            )
            print(f"SEALED {args.fixture} {manifest['payload_sha256']}")
        elif args.command == "verify":
            manifest = verify_fixture(args.fixture)
            print(f"VERIFIED {args.fixture} {manifest['payload_sha256']}")
        elif args.command == "prepare":
            run_dir = prepare_run(args.fixture, args.runs_root, args.run_id, args.java)
            print(f"PREPARED {run_dir}")
        else:
            cleanup_run(args.runs_root, args.run_id)
            print(f"CLEANED {args.run_id}")
        return 0
    except FixtureError as error:
        print(f"FIXTURE_ERROR {error}", file=sys.stderr)
        return 5
    except OSError as error:
        print(f"HARNESS_ERROR {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
