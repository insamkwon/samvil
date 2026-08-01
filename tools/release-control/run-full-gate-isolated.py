#!/usr/bin/env python3
"""Run the one pinned SAMVIL full gate inside its trusted control boundary.

This is deliberately not a generic launcher.  The only target command is
``bash scripts/pre-commit-check.sh`` and neither callers nor target bytes can
select a root, command, profile, or policy.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import pwd
import re
import resource
import signal
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Mapping, NoReturn, Sequence
import unicodedata


HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
PROFILE_CLASS = "pinned-full-gate-loopback-only"
COMMAND = ("bash", "scripts/pre-commit-check.sh")
PROMOTION_LIMITATION = "LOOPBACK_PORT_OWNERSHIP_NOT_OS_ISOLATED"
DETACHED_DESCENDANT_LIMITATION = "DETACHED_DESCENDANT_NOT_OS_ISOLATED"
PROMOTION_LIMITATIONS = (
    PROMOTION_LIMITATION,
    DETACHED_DESCENDANT_LIMITATION,
)
APPLE_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
APPLE_CODESIGN = Path("/usr/bin/codesign")
APPLE_CODESIGN_REQUIREMENT = 'anchor apple and identifier "com.apple.sandbox-exec"'
APPLE_CODESIGN_VERIFY_ARGV = (
    str(APPLE_CODESIGN),
    "--verify",
    "--strict",
    "--verbose=2",
    f"-R={APPLE_CODESIGN_REQUIREMENT}",
    str(APPLE_SANDBOX_EXEC),
)
APPLE_CODESIGN_DISPLAY_ARGV = (
    str(APPLE_CODESIGN),
    "-d",
    "--verbose=4",
    "-r-",
    str(APPLE_SANDBOX_EXEC),
)
APPLE_SANDBOX_BEHAVIOR_PROFILE = "(version 1)\n(allow default)\n"
APPLE_SANDBOX_BEHAVIOR_ARGV = (
    str(APPLE_SANDBOX_EXEC),
    "-p",
    APPLE_SANDBOX_BEHAVIOR_PROFILE,
    "/usr/bin/true",
)
APPLE_TOOL_MAX_BYTES = 8 * 1024 * 1024
APPLE_COMMAND_OUTPUT_MAX_BYTES = 64 * 1024
HOST_TOOL_IDENTITY_PARSER_TIMEOUT_SECONDS = 15.0
_APPLE_PLATFORM_BINDING_CACHE: bytes | None = None
AUTHORITY_PHASES = (
    "runtime_identity",
    "pytest",
    "server_import",
    "candidate",
    "complete",
)
DEFAULT_RESOURCE_LIMITS: dict[str, int] = {
    "cpu_seconds": 900,
    "wall_seconds": 1200,
    "rss_bytes": 2 * 1024 * 1024 * 1024,
    "address_space_bytes": 2 * 1024 * 1024 * 1024 * 1024,
    "file_size_bytes": 64 * 1024 * 1024,
    "nofile": 256,
    "descendants": 256,
    "per_file_bytes": 64 * 1024 * 1024,
    "aggregate_bytes": 2 * 1024 * 1024 * 1024,
    "stdout_bytes": 4 * 1024 * 1024,
    "stderr_bytes": 4 * 1024 * 1024,
    "authority_frame_count": len(AUTHORITY_PHASES),
    "authority_frame_bytes": 256 * 1024,
    "authority_aggregate_bytes": 1024 * 1024,
}
CONTROL_PATHS = (
    "tools/release-control/inherited_context.py",
    "tools/release-control/run-isolated.py",
    "tools/release-control/run-full-gate-isolated.py",
    "tools/release-control/verify-quarantine-candidate.py",
    "tools/release-control/tests/test_release_control.py",
)
MANIFEST_FIXED_LOG_PATHS = (
    "/tmp/samvil-pretest.log",
    "/tmp/samvil-mdrefs.log",
    "/tmp/samvil-hostparity.log",
    "/tmp/samvil-forward.log",
    "/tmp/samvil-agent-inventory.log",
)
FIXED_LOG_PATHS = MANIFEST_FIXED_LOG_PATHS
FULL_GATE_LOCK_PATH = Path("/tmp/samvil-full-gate.lock")
SEMANTIC_COUNTER_FIELDS = (
    "pytest_passed",
    "mcp_tools",
    "markdown_references",
    "host_untested",
    "forward_registered_tools",
    "forward_cited_tools",
    "agent_inventory_entries",
)
RECEIPT_FIELDS = (
    "schema",
    "status",
    "verdict",
    "nonce",
    "control_commit",
    "control_tree",
    "target_kind",
    "source_commit",
    "candidate_tree",
    "final_commit",
    "expected_parent",
    "authorization_sha256",
    "manifest_sha256",
    "prior_receipt_sha256",
    "command_sha256",
    "content_sha256",
    "profile_class",
    "profile_sha256",
    "import_manifest_sha256",
    "identity_sha256",
    "tree_sha256",
    "runtime_sha256",
    "semantic_counters",
    "promotion_limitations",
)
MANIFEST_FIELDS = frozenset(
    {
        "schema",
        "nonce",
        "control",
        "target",
        "object_pack",
        "inventory",
        "trusted_wrapper",
        "probes",
        "apple_platform_tcb",
        "command",
        "gate_inventory",
        "phase6_inventory",
        "collected_mcp_tests",
        "import_manifest",
        "runtime",
        "fixed_logs",
        "semantic_counters",
        "resource_limits",
        "receipt_fields",
    }
)
APPROVED_MANIFEST_FIELDS = frozenset(
    (MANIFEST_FIELDS - {"apple_platform_tcb"})
    | {
        "host_tool_identity_parser",
        "copied_application_runtime",
        "canonical_host_tools",
    }
)
APPROVED_COMMAND = ("/bin/bash", "scripts/pre-commit-check.sh")
RUNTIME_ARTIFACT_FIELDS = (
    "python_archive",
    "python_manifest",
    "dependency_archive",
    "dependency_manifest",
    "tool_archive",
    "tool_manifest",
    "facade_manifest",
)
REQUIRED_TOOL_NAMES = (
    "env",
    "git",
    "bash",
    "sh",
    "mktemp",
    "mkdir",
    "chmod",
    "grep",
    "xargs",
    "sed",
    "tail",
    "head",
    "find",
    "cat",
)
FACADE_PYTHON_WRAPPER = b'''#!/bin/sh
exec "${0%/*}/../../../../runtime/bin/python3.12" "$@"
'''
RUNTIME_PYTHON_FACADE_SOURCE = b'''#!/bin/sh
exec "${0%/*}/../../runtime/bin/python3.12" "$@"
'''
RUNTIME_DIRNAME_FACADE_SOURCE = b'''#!/bin/sh
exec "${0%/*}/../../runtime/bin/python3.12" -c '
import sys

if len(sys.argv) != 2:
    raise SystemExit(1)
value = sys.argv[1]
if not value:
    print(".")
else:
    value = value.rstrip("/")
    if not value:
        print("/")
    else:
        parent = value.rsplit("/", 1)[0]
        print(parent or ".")
' "$@"
'''
FACADE_PYVENV_CONFIG = (
    b"include-system-site-packages = false\nversion = 3.12\n"
)
FACADE_PATHS = (
    "mcp/.venv/bin/python",
    "mcp/.venv/bin/python3",
    "mcp/.venv/bin/python3.12",
    "mcp/.venv/pyvenv.cfg",
)
HERMETIC_ENVIRONMENT_KEYS = tuple(
    sorted(
        {
            "PATH",
            "LANG",
            "LC_ALL",
            "HOME",
            "CODEX_HOME",
            "CLAUDE_CONFIG_DIR",
            "GNUPGHOME",
            "TMPDIR",
            "XDG_CACHE_HOME",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "PYTHONNOUSERSITE",
            "PYTHONDONTWRITEBYTECODE",
            "PIP_CONFIG_FILE",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "__CF_USER_TEXT_ENCODING",
        }
    )
)
GIT_CONFIG_BYTES = (
    b"[credential]\n\thelper =\n"
    b"[protocol]\n\tallow = never\n"
    b"[protocol \"file\"]\n\tallow = never\n"
    b"[core]\n\tfsmonitor = false\n"
)
PIP_CONFIG_BYTES = b"[global]\nno-index = true\ndisable-pip-version-check = true\n"
TRUSTED_WRAPPER_SOURCE = r'''#!/usr/bin/env python3
"""Derived SAMVIL full-gate wrapper; source is pinned by the outer runner."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import subprocess
import sys

PHASES = ("runtime_identity", "pytest", "server_import", "candidate", "complete")
CANDIDATES = {
    ("bash", "scripts/pre-commit-check.sh"),
    ("/bin/bash", "scripts/pre-commit-check.sh"),
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def contained(path, roots):
    resolved = Path(path).resolve(strict=False)
    return any(resolved == root or root in resolved.parents for root in roots)


def load_contract(path, expected_digest):
    raw = Path(path).read_bytes()
    if digest(raw) != expected_digest:
        raise RuntimeError("contract digest")
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) != raw or value.get("schema") != "samvil.full-gate-wrapper-contract.v1":
        raise RuntimeError("contract canonical")
    return value


def set_child_limits(limits):
    def lower(which, requested):
        soft, hard = resource.getrlimit(which)
        bounded = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
        resource.setrlimit(which, (bounded, bounded))
    lower(resource.RLIMIT_CPU, limits["cpu_seconds"])
    lower(resource.RLIMIT_FSIZE, limits["file_size_bytes"])
    lower(resource.RLIMIT_NOFILE, limits["nofile"])
    if hasattr(resource, "RLIMIT_AS") and sys.platform != "darwin":
        lower(resource.RLIMIT_AS, limits["address_space_bytes"])


def run_child(name, argv, cwd, environment, scratch, limits):
    phase_scratch = scratch / name
    stdout_path = phase_scratch / "stdout"
    stderr_path = phase_scratch / "stderr"
    with stdout_path.open("xb", buffering=0) as stdout, stderr_path.open("xb", buffering=0) as stderr:
        try:
            completed = subprocess.run(
                argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, close_fds=True, pass_fds=(),
                preexec_fn=lambda: set_child_limits(limits),
                timeout=limits["wall_seconds"], check=False,
            )
        except subprocess.TimeoutExpired:
            return 124, stdout_path, stderr_path
    if stdout_path.stat().st_size > limits["stdout_bytes"]:
        return 122, stdout_path, stderr_path
    if stderr_path.stat().st_size > limits["stderr_bytes"]:
        return 123, stdout_path, stderr_path
    return completed.returncode, stdout_path, stderr_path


def tree_digest(root):
    observed=[]
    stack=[root]
    while stack:
        directory=stack.pop()
        for child in sorted(directory.iterdir(), key=lambda item: item.name, reverse=True):
            metadata=child.lstat()
            relative=str(child.relative_to(root))
            if child.is_symlink():
                raise RuntimeError("inventory symlink")
            if child.is_dir():
                stack.append(child)
                continue
            if not child.is_file() or metadata.st_nlink != 1:
                raise RuntimeError("inventory type")
            data=child.read_bytes()
            observed.append({"path":relative,"mode":format((metadata.st_mode & 0o777)|0o100000,"06o"),
                             "size":len(data),"sha256":digest(data)})
    observed.sort(key=lambda item:item["path"])
    return digest(canonical(observed))


def verify_inventory(contract):
    roots = {name: Path(value).resolve(strict=True) for name, value in contract["roots"].items()}
    observed = []
    for entry in contract["identity_inventory"]:
        root = roots[entry["root"]]
        path = (root / entry["path"]).resolve(strict=True)
        if path != root and root not in path.parents:
            raise RuntimeError("inventory escape")
        metadata = path.stat()
        if not path.is_file() or metadata.st_nlink != 1:
            raise RuntimeError("inventory type")
        data = path.read_bytes()
        mode = format((metadata.st_mode & 0o777) | 0o100000, "06o")
        item = {"root": entry["root"], "path": entry["path"], "mode": mode,
                "sha256": digest(data)}
        if item != entry:
            raise RuntimeError("inventory drift")
        observed.append(item)
    root_digests={name:tree_digest(roots[name]) for name in sorted(contract["root_digests"])}
    for name,value in root_digests.items():
        if value != contract["root_digests"].get(name):
            raise RuntimeError("root inventory drift:"+name)
    return digest(canonical({"critical":observed,"roots":root_digests}))


def emit(fd, nonce, sequence, phase, status, evidence, limits):
    payload = canonical({"schema": "samvil.full-gate-authority-frame.v1",
                         "nonce": nonce, "sequence": sequence, "phase": phase,
                         "status": status, "evidence": evidence})
    if len(payload) > limits["authority_frame_bytes"]:
        raise RuntimeError("authority frame size")
    frame = struct.pack(">I", len(payload)) + payload
    view = memoryview(frame)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise RuntimeError("authority write")
        view = view[written:]


def parse_json_capture(path, limit):
    raw = path.read_bytes()
    if len(raw) > limit:
        raise RuntimeError("capture size")
    return json.loads(raw.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--authority-fd", required=True, type=int)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--dependencies", required=True)
    parser.add_argument("--tools", required=True)
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--scratch", required=True)
    args = parser.parse_args()
    flags = fcntl.fcntl(args.authority_fd, fcntl.F_GETFD)
    fcntl.fcntl(args.authority_fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)
    contract = load_contract(args.contract, args.contract_sha256)
    candidate = tuple(contract["candidate_command"])
    if contract["nonce"] != args.nonce or candidate not in CANDIDATES:
        raise RuntimeError("contract authority")
    limits = contract["resource_limits"]
    snapshot = Path(args.snapshot).resolve(strict=True)
    runtime = Path(args.runtime).resolve(strict=True)
    dependencies = Path(args.dependencies).resolve(strict=True)
    tools = Path(args.tools).resolve(strict=True)
    wrapper = Path(args.wrapper).resolve(strict=True)
    scratch = Path(args.scratch).resolve(strict=True)
    roots = (snapshot, runtime, dependencies, tools, wrapper.parent)
    for value in contract["roots"].values():
        if not contained(value, roots):
            raise RuntimeError("contract root")
    python = runtime / "bin/python3.12"
    environment = dict(os.environ)
    environment.pop("SAMVIL_FULL_GATE_OBSERVATION_LOG", None)
    environment.pop("SAMVIL_AUTHORITY_FD", None)
    environment["PATH"] = str(tools / "bin") + ":" + str(runtime / "bin") + ":/usr/bin:/bin:/usr/sbin:/sbin"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

    sequence = 0
    pre_identity = verify_inventory(contract)
    runtime_source = contract["runtime_probe_source"]
    code, stdout, _stderr = run_child("runtime", [str(python), "-I", "-B", "-c", runtime_source],
                                      runtime, environment, scratch, limits)
    runtime_evidence = parse_json_capture(stdout, limits["stdout_bytes"]) if code == 0 else {}
    runtime_roots = (runtime,)
    runtime_paths = [runtime_evidence.get("executable"), runtime_evidence.get("prefix"),
                     runtime_evidence.get("base_prefix"), *runtime_evidence.get("sys_path", []),
                     *runtime_evidence.get("modules", {}).values()]
    runtime_ok = code == 0 and all(isinstance(value, str) and contained(value, runtime_roots)
                                   for value in runtime_paths)
    emit(args.authority_fd, args.nonce, sequence, "runtime_identity",
         "PASS" if runtime_ok else "FAIL",
         {"inventory_sha256": pre_identity, "probe_sha256": digest(canonical(runtime_evidence))}, limits)
    if not runtime_ok:
        return 125
    sequence += 1

    verify_inventory(contract)
    test_paths = [str(Path(path).relative_to("mcp")) for path in contract["test_paths"]]
    code, stdout, _stderr = run_child("pytest", [str(python), "-I", "-B", "-m", "pytest", *test_paths,
                                      "-p", "no:cacheprovider", "-q", "--tb=no"],
                                      snapshot / "mcp", environment, scratch, limits)
    pytest_bytes=stdout.read_bytes()
    import re
    matches=re.findall(rb"(?:^|\n)([0-9]+) passed(?:[ ,\n]|$)",pytest_bytes)
    pytest_passed=int(matches[-1]) if len(matches)==1 else -1
    emit(args.authority_fd, args.nonce, sequence, "pytest", "PASS" if code == 0 else "FAIL",
         {"command_sha256": contract["probe_digests"]["pytest"],
          "stdout_sha256": digest(pytest_bytes),"pytest_passed":pytest_passed}, limits)
    if code != 0 or pytest_passed < 0:
        return 125
    sequence += 1

    verify_inventory(contract)
    server_source = contract["server_probe_source"]
    code, stdout, _stderr = run_child(
        "server", [str(python), "-I", "-B", "-c", server_source, str(snapshot), str(dependencies),
                   canonical(contract["import_allowlist"]).decode("utf-8")],
        snapshot, environment, scratch, limits)
    server_evidence = parse_json_capture(stdout, limits["stdout_bytes"]) if code == 0 else {}
    allowed_roots = (snapshot, runtime, dependencies)
    module_paths = server_evidence.get("modules", {}).values()
    server_ok = code == 0 and all(isinstance(value, str) and contained(value, allowed_roots)
                                  for value in module_paths)
    emit(args.authority_fd, args.nonce, sequence, "server_import",
         "PASS" if server_ok else "FAIL",
         {"command_sha256": contract["probe_digests"]["server_import"],
          "probe_sha256": digest(canonical(server_evidence)),
          "tool_count":server_evidence.get("tool_count",-1)}, limits)
    if not server_ok:
        return 125
    sequence += 1

    verify_inventory(contract)
    candidate_environment = dict(environment)
    candidate_environment["TMPDIR"] = str(scratch / "candidate")
    code, stdout, stderr = run_child("candidate", list(candidate), snapshot,
                                     candidate_environment, scratch, limits)
    try:
        post_identity = verify_inventory(contract)
    except Exception as inventory_error:
        emit(args.authority_fd, args.nonce, sequence, "candidate", "FAIL",
             {"exit_code": code, "stdout_sha256": digest(stdout.read_bytes()),
              "stderr_sha256": digest(stderr.read_bytes()),
              "inventory_error_sha256": digest(
                  (type(inventory_error).__name__ + ":" + str(inventory_error)).encode("utf-8")
              )}, limits)
        return 125
    emit(args.authority_fd, args.nonce, sequence, "candidate", "PASS" if code == 0 else "FAIL",
         {"exit_code": code, "stdout_sha256": digest(stdout.read_bytes()),
          "stderr_sha256": digest(stderr.read_bytes()), "inventory_sha256": post_identity}, limits)
    if code != 0:
        return code
    sequence += 1
    emit(args.authority_fd, args.nonce, sequence, "complete", "PASS",
         {"pre_identity_sha256": pre_identity, "post_identity_sha256": post_identity}, limits)
    os.close(args.authority_fd)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        try:
            os.close(int(sys.argv[sys.argv.index("--authority-fd") + 1]))
        except BaseException:
            pass
        raise
'''.encode("utf-8")
TRUSTED_PROBE_COMMANDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "runtime_identity",
        (
            "<PINNED_PYTHON>",
            "-I",
            "-B",
            "-c",
            "<RUNTIME_IDENTITY_PROBE>",
        ),
    ),
    (
        "pytest",
        (
            "<PINNED_PYTHON>",
            "-I",
            "-B",
            "-m",
            "pytest",
            "<VERIFIED_TEST_INVENTORY>",
            "-p",
            "no:cacheprovider",
            "-q",
            "--tb=no",
        ),
    ),
    (
        "server_import",
        (
            "<PINNED_PYTHON>",
            "-I",
            "-B",
            "-c",
            "<SERVER_IMPORT_CONTAINMENT_PROBE>",
        ),
    ),
)
RUNTIME_IDENTITY_PROBE_SOURCE = r'''import hashlib,json,os,platform,sys
modules={}
module_hashes={}
for name,module in sorted(sys.modules.items()):
    value=getattr(module,"__file__",None)
    if value:
        path=os.path.realpath(value)
        modules[name]=path
        try:
            module_hashes[name]=hashlib.sha256(open(path,"rb").read()).hexdigest()
        except OSError:
            raise SystemExit(91)
paths=[os.path.realpath(value or os.getcwd()) for value in sys.path]
print(json.dumps({"version":platform.python_version(),"architecture":platform.machine(),
"executable":os.path.realpath(sys.executable),"prefix":os.path.realpath(sys.prefix),
"base_prefix":os.path.realpath(sys.base_prefix),"sys_path":paths,"modules":modules,
"module_hashes":module_hashes},sort_keys=True,separators=(",",":")))
'''
SERVER_IMPORT_PROBE_SOURCE = r'''import hashlib,json,os,sys
snapshot=os.path.realpath(sys.argv[1])
dependencies=os.path.realpath(sys.argv[2])
allowlist=json.loads(sys.argv[3])
sys.path[:0]=[os.path.join(snapshot,"mcp"),os.path.join(dependencies,"lib/python3.12/site-packages")]
for name in allowlist:
    __import__(name)
from samvil_mcp import server
modules={}
module_hashes={}
for name,module in sorted(sys.modules.items()):
    value=getattr(module,"__file__",None)
    if value:
        path=os.path.realpath(value)
        modules[name]=path
        try:
            module_hashes[name]=hashlib.sha256(open(path,"rb").read()).hexdigest()
        except OSError:
            raise SystemExit(92)
print(json.dumps({"modules":modules,"module_hashes":module_hashes,
"tool_count":len(list(server.mcp._tool_manager._tools))},sort_keys=True,separators=(",",":")))
'''


class FullGateError(ValueError):
    """A typed, path-free full-gate blocker."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


@dataclass(frozen=True)
class FullGateArguments:
    manifest: str
    prior_receipt: str | None
    nonce: str
    timeout: float
    receipt: str
    denial_log: str


@dataclass(frozen=True)
class ValidatedManifest:
    raw: Mapping[str, object]
    manifest_sha256: str
    nonce: str
    control_commit: str
    control_tree: str
    target_kind: str
    source_commit: str | None
    candidate_tree: str
    final_commit: str | None
    expected_parent: str | None
    authorization_sha256: str | None
    precommit_tree: str | None
    expected_precommit_nonce: str | None
    expected_precommit_control_commit: str | None
    expected_precommit_control_tree: str | None
    expected_precommit_manifest_sha256: str | None
    prior_receipt_sha256: str | None


@dataclass(frozen=True)
class GitObject:
    kind: str
    content: bytes


@dataclass(frozen=True)
class VerifiedGitObjectPack:
    tree: str
    files: Mapping[str, bytes]
    modes: Mapping[str, str]
    blobs: Mapping[str, str]
    closure_sha256: str


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    nlink: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def from_stat(cls, metadata: os.stat_result) -> "FileIdentity":
        return cls(
            device=metadata.st_dev,
            inode=metadata.st_ino,
            mode=metadata.st_mode,
            nlink=metadata.st_nlink,
            size=metadata.st_size,
            mtime_ns=getattr(
                metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)
            ),
            ctime_ns=getattr(
                metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)
            ),
        )


@dataclass
class HeldArtifact:
    path: Path
    descriptor: int
    data: bytes
    identity: FileIdentity
    status: str
    closed: bool = False

    def assert_stable(self) -> None:
        if self.closed:
            _raise("EXTERNAL_ARTIFACT_DESCRIPTOR_CLOSED")
        try:
            descriptor_state = FileIdentity.from_stat(os.fstat(self.descriptor))
            path_state = FileIdentity.from_stat(os.lstat(self.path))
        except OSError:
            _raise("EXTERNAL_ARTIFACT_REPLACED")
        if descriptor_state != self.identity or path_state != self.identity:
            _raise("EXTERNAL_ARTIFACT_REPLACED")

    def close(self) -> None:
        if self.closed:
            return
        try:
            os.close(self.descriptor)
        except OSError:
            self.closed = True
            _raise("EXTERNAL_ARTIFACT_CLOSE_FAILED")
        self.closed = True


@dataclass
class HeldApplePlatformTool:
    path: Path
    descriptor: int
    identity: FileIdentity
    binding: Mapping[str, object]
    closed: bool = False

    def assert_stable(self) -> None:
        if self.closed:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        try:
            descriptor_state = os.fstat(self.descriptor)
            path_state = os.lstat(self.path)
            resolved = self.path.resolve(strict=True)
        except (OSError, RuntimeError):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        if (
            resolved != self.path
            or FileIdentity.from_stat(descriptor_state) != self.identity
            or FileIdentity.from_stat(path_state) != self.identity
            or descriptor_state.st_uid != self.binding["uid"]
            or descriptor_state.st_gid != self.binding["gid"]
            or path_state.st_uid != self.binding["uid"]
            or path_state.st_gid != self.binding["gid"]
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")

    def close(self) -> None:
        if self.closed:
            return
        try:
            os.close(self.descriptor)
        except OSError:
            self.closed = True
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        self.closed = True


@dataclass
class HeldApplePlatformTCB:
    sandbox_exec: HeldApplePlatformTool
    codesign: HeldApplePlatformTool
    codesign_result: Mapping[str, object]
    behavior: Mapping[str, object]
    closed: bool = False

    def assert_stable(self) -> None:
        if self.closed:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        self.sandbox_exec.assert_stable()
        self.codesign.assert_stable()

    def complete(self) -> dict[str, object]:
        self.assert_stable()
        payload = {
            "schema": "samvil.apple-platform-evidence.v1",
            "sandbox_exec": dict(self.sandbox_exec.binding),
            "codesign": dict(self.codesign.binding),
            "codesign_result": dict(self.codesign_result),
            "behavior": dict(self.behavior),
            "pre_post_identity": "stable",
        }
        return {
            **payload,
            "result_sha256": sha256_bytes(canonical_json_bytes(payload)),
        }

    def close(self) -> None:
        if self.closed:
            return
        failed = False
        for held in (self.codesign, self.sandbox_exec):
            try:
                held.close()
            except FullGateError:
                failed = True
        self.closed = True
        if failed:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")


@dataclass
class HeldOutput:
    path: Path
    descriptor: int
    identity: FileIdentity
    closed: bool = False

    def assert_stable(self) -> None:
        if self.closed:
            _raise("OUTPUT_DESCRIPTOR_CLOSED")
        try:
            descriptor_state = FileIdentity.from_stat(os.fstat(self.descriptor))
            path_state = FileIdentity.from_stat(os.lstat(self.path))
        except OSError:
            _raise("OUTPUT_IDENTITY_MISMATCH")
        if descriptor_state != self.identity or path_state != self.identity:
            _raise("OUTPUT_IDENTITY_MISMATCH")

    def close(self) -> None:
        if self.closed:
            return
        try:
            os.close(self.descriptor)
        except OSError:
            self.closed = True
            _raise("OUTPUT_CLOSE_FAILED")
        self.closed = True


@dataclass
class OutputFiles:
    receipt: HeldOutput
    denial_log: HeldOutput
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        failed = False
        for output in (self.denial_log, self.receipt):
            try:
                output.close()
            except FullGateError:
                failed = True
        self.closed = True
        if failed:
            _raise("OUTPUT_CLOSE_FAILED")


@dataclass(frozen=True)
class CapturedLog:
    name: str
    sha256: str
    size: int


@dataclass
class FixedLogProtocol:
    lock_path: Path
    descriptor: int
    identity: tuple[int, int, int, int, int]
    log_paths: tuple[Path, ...]
    closed: bool = False

    def assert_stable(self) -> None:
        if self.closed:
            _raise("FULL_GATE_LOCK_CLOSED")
        try:
            descriptor = os.fstat(self.descriptor)
            path = os.lstat(self.lock_path)
        except OSError:
            _raise("FULL_GATE_LOCK_IDENTITY_MISMATCH")
        if _core_identity(descriptor) != self.identity or _core_identity(path) != self.identity:
            _raise("FULL_GATE_LOCK_IDENTITY_MISMATCH")

    def close(self) -> None:
        if self.closed:
            return
        failed = False
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        except OSError:
            failed = True
        try:
            os.close(self.descriptor)
        except OSError:
            failed = True
        self.closed = True
        if failed:
            _raise("FULL_GATE_LOCK_RELEASE_FAILED")


@dataclass(frozen=True)
class GateOutcome:
    returncode: int
    timed_out: bool
    cleanup_performed: bool
    resource_status: str | None
    stdout: bytes
    stderr: bytes
    authority_frames: tuple[dict[str, object], ...] = ()
    wrapper_pid: int | None = None
    wrapper_start_identity: str | None = None
    observed_descendants: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ReceiptDigests:
    command: str
    content: str
    profile: str
    imports: str
    identity: str
    tree: str
    runtime: str


@dataclass(frozen=True)
class ExecutionEvidence:
    digest: str
    import_manifest_sha256: str
    facade_roles: tuple[str, ...]
    pytest_passed: int
    mcp_tools: int


def _raise(status: str) -> NoReturn:
    raise FullGateError(status)


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError, MemoryError):
        _raise("FULL_GATE_JSON_INVALID")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validated_resource_limits(value: Mapping[str, object]) -> dict[str, int]:
    if set(value) != set(DEFAULT_RESOURCE_LIMITS):
        _raise("RESOURCE_LIMIT_MANIFEST_INVALID")
    limits: dict[str, int] = {}
    for key, default in DEFAULT_RESOURCE_LIMITS.items():
        raw = value[key]
        if type(raw) is not int or raw <= 0 or raw > max(default * 1024, 2**47):
            _raise("RESOURCE_LIMIT_MANIFEST_INVALID")
        limits[key] = raw
    if limits["authority_frame_bytes"] > limits["authority_aggregate_bytes"]:
        _raise("RESOURCE_LIMIT_MANIFEST_INVALID")
    return limits


def encode_authority_frame(
    value: Mapping[str, object], *, limits: Mapping[str, object]
) -> bytes:
    bounded = _validated_resource_limits(limits)
    payload = canonical_json_bytes(dict(value))
    if len(payload) > bounded["authority_frame_bytes"]:
        _raise("AUTHORITY_FRAME_BYTES_EXCEEDED")
    return struct.pack(">I", len(payload)) + payload


def decode_authority_frames(
    raw: bytes,
    *,
    nonce: str,
    limits: Mapping[str, object],
    wrapper_exited: bool,
    post_exit_bytes: bytes = b"",
) -> tuple[dict[str, object], ...]:
    bounded = _validated_resource_limits(limits)
    expected_nonce = _hex64(nonce, "AUTHORITY_FRAME_INVALID")
    if not isinstance(raw, bytes) or not isinstance(post_exit_bytes, bytes):
        _raise("AUTHORITY_FRAME_INVALID")
    if post_exit_bytes:
        _raise("AUTHORITY_POST_EXIT_BYTES")
    if not wrapper_exited:
        _raise("AUTHORITY_FRAME_INVALID")
    if len(raw) > bounded["authority_aggregate_bytes"]:
        _raise("AUTHORITY_FRAME_AGGREGATE_EXCEEDED")
    frames: list[dict[str, object]] = []
    offset = 0
    while offset < len(raw):
        if len(raw) - offset < 4:
            _raise("AUTHORITY_FRAME_INVALID")
        size = struct.unpack(">I", raw[offset : offset + 4])[0]
        offset += 4
        if size <= 0 or size > bounded["authority_frame_bytes"]:
            _raise("AUTHORITY_FRAME_BYTES_EXCEEDED")
        if len(raw) - offset < size:
            _raise("AUTHORITY_FRAME_INVALID")
        payload = raw[offset : offset + size]
        offset += size
        decoded = decode_canonical_json_bytes(
            payload,
            status="AUTHORITY_FRAME_INVALID",
            max_bytes=bounded["authority_frame_bytes"],
        )
        frame = _exact_object(
            decoded,
            frozenset({"schema", "nonce", "sequence", "phase", "status", "evidence"}),
            "AUTHORITY_FRAME_INVALID",
        )
        sequence = frame["sequence"]
        phase = frame["phase"]
        if (
            frame["schema"] != "samvil.full-gate-authority-frame.v1"
            or frame["nonce"] != expected_nonce
            or type(sequence) is not int
            or sequence != len(frames)
            or not isinstance(phase, str)
            or len(frames) >= len(AUTHORITY_PHASES)
            or phase != AUTHORITY_PHASES[len(frames)]
            or frame["status"] not in {"PASS", "FAIL"}
            or not isinstance(frame["evidence"], dict)
        ):
            _raise("AUTHORITY_FRAME_ORDER_INVALID")
        frames.append(frame)
        if len(frames) > bounded["authority_frame_count"]:
            _raise("AUTHORITY_FRAME_COUNT_EXCEEDED")
    if len(frames) > bounded["authority_frame_count"]:
        _raise("AUTHORITY_FRAME_COUNT_EXCEEDED")
    phases = tuple(frame["phase"] for frame in frames)
    statuses = tuple(frame["status"] for frame in frames)
    if phases == AUTHORITY_PHASES:
        if statuses != ("PASS",) * len(AUTHORITY_PHASES):
            _raise("AUTHORITY_FRAME_ORDER_INVALID")
    elif (
        not frames
        or phases != AUTHORITY_PHASES[: len(frames)]
        or statuses[-1] != "FAIL"
        or any(status != "PASS" for status in statuses[:-1])
    ):
        _raise("AUTHORITY_FRAME_ORDER_INVALID")
    return tuple(frames)


def create_cloexec_pipe() -> tuple[int, int]:
    try:
        read_fd, write_fd = os.pipe()
        os.set_inheritable(read_fd, False)
        os.set_inheritable(write_fd, False)
    except OSError:
        _raise("AUTHORITY_PIPE_CREATE_FAILED")
    if os.get_inheritable(read_fd) or os.get_inheritable(write_fd):
        try:
            os.close(read_fd)
            os.close(write_fd)
        finally:
            _raise("AUTHORITY_PIPE_CREATE_FAILED")
    return read_fd, write_fd


def _walk_json_bounds(value: object, *, depth: int = 0) -> None:
    if depth > 48:
        _raise("FULL_GATE_JSON_DEPTH_EXCEEDED")
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _raise("FULL_GATE_JSON_UNICODE_INVALID")
        if unicodedata.normalize("NFC", value) != value:
            _raise("FULL_GATE_JSON_UNICODE_INVALID")
        return
    if value is None or type(value) in {bool, int}:
        return
    if isinstance(value, list):
        if len(value) > 100_000:
            _raise("FULL_GATE_JSON_BOUNDS_EXCEEDED")
        for item in value:
            _walk_json_bounds(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 100_000:
            _raise("FULL_GATE_JSON_BOUNDS_EXCEEDED")
        for key, item in value.items():
            _walk_json_bounds(key, depth=depth + 1)
            _walk_json_bounds(item, depth=depth + 1)
        return
    _raise("FULL_GATE_JSON_INVALID")


def decode_canonical_json_bytes(
    raw: bytes, *, status: str, max_bytes: int
) -> object:
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        _raise(status)

    def reject_constant(_value: str) -> NoReturn:
        _raise(status)

    def reject_float(_value: str) -> NoReturn:
        _raise(status)

    def bounded_int(value: str) -> int:
        if len(value.lstrip("-")) > 16:
            _raise(status)
        parsed = int(value)
        if abs(parsed) > 9_007_199_254_740_991:
            _raise(status)
        return parsed

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                _raise(status)
            result[key] = item
        return result

    try:
        decoded = raw.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=bounded_int,
        )
    except FullGateError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
    ):
        _raise(status)
    try:
        _walk_json_bounds(value)
        canonical = canonical_json_bytes(value)
    except FullGateError:
        _raise(status)
    if canonical != raw:
        _raise(status)
    return value


def _exact_object(
    value: object, fields: frozenset[str], status: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        _raise(status)
    if any(not isinstance(key, str) for key in value):
        _raise(status)
    return value


def _hex40(value: object, status: str) -> str:
    if not isinstance(value, str) or HEX40.fullmatch(value) is None:
        _raise(status)
    return value


def _hex64(value: object, status: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        _raise(status)
    return value


def _identity_uint(value: object, status: str) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,19}", value):
        parsed = int(value)
    else:
        _raise(status)
    if parsed < 0 or parsed > 0xFFFFFFFFFFFFFFFF:
        _raise(status)
    return parsed


def _safe_repo_path(value: object, status: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
    ):
        _raise(status)
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        _raise(status)
    return value


def _validate_artifact_reference(value: object, status: str) -> dict[str, str]:
    artifact = _exact_object(value, frozenset({"path", "sha256"}), status)
    raw_path = artifact["path"]
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        _raise(status)
    return {"path": raw_path, "sha256": _hex64(artifact["sha256"], status)}


def _canonical_external_path(raw: str, status: str) -> Path:
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        _raise(status)
    path = Path(raw)
    if path.name in {"", ".", ".."}:
        _raise(status)
    try:
        parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    canonical = parent / path.name
    if str(canonical) != raw:
        _raise(status)
    return canonical


def open_external_artifact(
    raw_path: str,
    expected_sha256: str,
    *,
    max_bytes: int,
    status: str,
) -> HeldArtifact:
    held = open_external_control_artifact(
        raw_path, max_bytes=max_bytes, status=status
    )
    expected = _hex64(expected_sha256, status)
    if sha256_bytes(held.data) != expected:
        try:
            held.close()
        finally:
            _raise(status)
    return held


def open_external_control_artifact(
    raw_path: str,
    *,
    max_bytes: int,
    status: str,
) -> HeldArtifact:
    path = _canonical_external_path(raw_path, status)
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        _raise(status)
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise(status)
    held: HeldArtifact | None = None
    try:
        metadata = os.fstat(descriptor)
        identity = FileIdentity.from_stat(metadata)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > max_bytes
        ):
            _raise(status)
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != metadata.st_size or len(data) > max_bytes:
            _raise(status)
        held = HeldArtifact(path, descriptor, data, identity, status)
        held.assert_stable()
        return held
    except BaseException:
        if held is None or not held.closed:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _output_collision_key(path: Path) -> str:
    return unicodedata.normalize("NFC", str(path)).casefold()


def _preflight_absent_output(raw: str, status: str) -> Path:
    path = _canonical_external_path(raw, status)
    try:
        os.lstat(path)
    except FileNotFoundError:
        return path
    except OSError:
        _raise(status)
    _raise("OUTPUT_PREEXISTS")


def _open_output(path: Path) -> HeldOutput:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        _raise("OUTPUT_PREEXISTS")
    except OSError:
        _raise("OUTPUT_CREATE_FAILED")
    try:
        metadata = os.fstat(descriptor)
        identity = FileIdentity.from_stat(metadata)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            _raise("OUTPUT_IDENTITY_MISMATCH")
        output = HeldOutput(path, descriptor, identity)
        output.assert_stable()
        return output
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def create_output_files(
    receipt_raw: str,
    denial_raw: str,
    *,
    reserved_paths: Sequence[Path | str],
) -> OutputFiles:
    receipt = _preflight_absent_output(receipt_raw, "OUTPUT_PATH_INVALID")
    denial = _preflight_absent_output(denial_raw, "OUTPUT_PATH_INVALID")
    paths = (receipt, denial)
    reserved = tuple(Path(path) for path in reserved_paths) + tuple(
        Path(path) for path in FIXED_LOG_PATHS
    ) + (FULL_GATE_LOCK_PATH,)
    keys = [_output_collision_key(path) for path in paths]
    reserved_keys = {_output_collision_key(path) for path in reserved}
    if len(set(keys)) != len(keys) or any(key in reserved_keys for key in keys):
        _raise("OUTPUT_PATH_COLLISION")
    receipt_output = _open_output(receipt)
    try:
        denial_output = _open_output(denial)
    except BaseException:
        try:
            receipt_output.close()
        finally:
            try:
                os.unlink(receipt)
            except OSError:
                pass
        raise
    return OutputFiles(receipt_output, denial_output)


def write_output(output: HeldOutput, data: bytes) -> None:
    if not isinstance(data, bytes) or len(data) > 8 * 1024 * 1024:
        _raise("OUTPUT_WRITE_FAILED")
    output.assert_stable()
    try:
        os.lseek(output.descriptor, 0, os.SEEK_SET)
        os.ftruncate(output.descriptor, 0)
        view = memoryview(data)
        while view:
            written = os.write(output.descriptor, view)
            if written <= 0:
                _raise("OUTPUT_WRITE_FAILED")
            view = view[written:]
        os.fsync(output.descriptor)
    except FullGateError:
        raise
    except OSError:
        _raise("OUTPUT_WRITE_FAILED")
    try:
        metadata = os.fstat(output.descriptor)
    except OSError:
        _raise("OUTPUT_WRITE_FAILED")
    output.identity = FileIdentity.from_stat(metadata)
    output.assert_stable()


def _invalidate_output(output: HeldOutput, blocker: bytes) -> None:
    if not output.closed:
        try:
            write_output(output, blocker)
            return
        except FullGateError:
            pass
    flags = os.O_WRONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(output.path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_dev != output.identity.device
            or metadata.st_ino != output.identity.inode
        ):
            raise OSError("output identity changed")
        os.ftruncate(descriptor, 0)
        view = memoryview(blocker)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short blocker write")
            view = view[written:]
        os.fsync(descriptor)
        final_descriptor = os.fstat(descriptor)
        final_path = os.lstat(output.path)
        if _core_identity(final_descriptor) != _core_identity(final_path):
            raise OSError("output identity changed")
        os.close(descriptor)
        descriptor = None
        return
    except OSError:
        if descriptor is not None:
            try:
                os.ftruncate(descriptor, 0)
                os.fsync(descriptor)
            except OSError:
                pass
            try:
                os.close(descriptor)
            except OSError:
                pass
    try:
        os.unlink(output.path)
    except FileNotFoundError:
        return
    except OSError:
        _raise("OUTPUT_INVALIDATION_FAILED")


def finalize_outputs(
    outputs: OutputFiles,
    *,
    denial_bytes: bytes,
    receipt_bytes: bytes,
    nonce: str,
) -> None:
    if outputs.closed:
        _raise("OUTPUT_FINALIZATION_FAILED")
    incomplete = _failure_receipt("OUTPUT_FINALIZATION_INCOMPLETE", nonce)
    failed = _failure_receipt("OUTPUT_FINALIZATION_FAILED", nonce)
    try:
        write_output(outputs.receipt, incomplete)
        write_output(outputs.denial_log, denial_bytes)
        write_output(outputs.receipt, receipt_bytes)
        outputs.denial_log.close()
        outputs.receipt.close()
        outputs.closed = True
        return
    except FullGateError:
        try:
            _invalidate_output(outputs.receipt, failed)
        except FullGateError:
            pass
        for output in (outputs.denial_log, outputs.receipt):
            try:
                output.close()
            except FullGateError:
                pass
        outputs.closed = True
        _raise("OUTPUT_FINALIZATION_FAILED")


def _core_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
    )


def acquire_fixed_log_protocol() -> FixedLogProtocol:
    lock_path = Path(FULL_GATE_LOCK_PATH)
    if not lock_path.is_absolute():
        _raise("FULL_GATE_LOCK_INVALID")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        _raise("FULL_GATE_LOCK_INVALID")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            _raise("FULL_GATE_LOCK_INVALID")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _raise("FULL_GATE_LOCK_CONTENDED")
        except OSError:
            _raise("FULL_GATE_LOCK_INVALID")
        protocol = FixedLogProtocol(
            lock_path=lock_path,
            descriptor=descriptor,
            identity=_core_identity(metadata),
            log_paths=tuple(Path(path) for path in FIXED_LOG_PATHS),
        )
        protocol.assert_stable()
        for path in protocol.log_paths:
            try:
                os.lstat(path)
            except FileNotFoundError:
                continue
            except OSError:
                _raise("FIXED_LOG_PREFLIGHT_FAILED")
            _raise("FIXED_LOG_PREEXISTS")
        return protocol
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _read_fixed_log(path: Path) -> tuple[int, bytes, tuple[int, int, int, int, int]]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        _raise("FIXED_LOG_MISSING")
    except OSError:
        _raise("FIXED_LOG_INVALID")
    try:
        metadata = os.fstat(descriptor)
        identity = _core_identity(metadata)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > 32 * 1024 * 1024
        ):
            _raise("FIXED_LOG_INVALID")
        chunks: list[bytes] = []
        remaining = 32 * 1024 * 1024 + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) != metadata.st_size or len(data) > 32 * 1024 * 1024:
            _raise("FIXED_LOG_INVALID")
        path_state = os.lstat(path)
        if _core_identity(path_state) != identity:
            _raise("FIXED_LOG_IDENTITY_MISMATCH")
        return descriptor, data, identity
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def capture_fixed_logs(
    protocol: FixedLogProtocol, destination: Path
) -> tuple[CapturedLog, ...]:
    protocol.assert_stable()
    root = _canonical_destination(
        destination, "FIXED_LOG_DESTINATION_INVALID", must_exist=False
    )
    opened: list[tuple[Path, int, bytes, tuple[int, int, int, int, int]]] = []
    try:
        for path in protocol.log_paths:
            descriptor, data, identity = _read_fixed_log(path)
            opened.append((path, descriptor, data, identity))
        os.mkdir(root, 0o700)
        captured: list[CapturedLog] = []
        for path, descriptor, data, identity in opened:
            target = root / path.name
            try:
                os.rename(path, target)
                target_state = os.lstat(target)
                descriptor_state = os.fstat(descriptor)
            except OSError:
                _raise("FIXED_LOG_MOVE_FAILED")
            if (
                _core_identity(target_state) != _core_identity(descriptor_state)
                or _core_identity(descriptor_state) != identity
            ):
                _raise("FIXED_LOG_IDENTITY_MISMATCH")
            try:
                os.lstat(path)
            except FileNotFoundError:
                pass
            except OSError:
                _raise("FIXED_LOG_MOVE_FAILED")
            else:
                _raise("FIXED_LOG_MOVE_FAILED")
            captured.append(CapturedLog(path.name, sha256_bytes(data), len(data)))
        protocol.assert_stable()
        return tuple(captured)
    finally:
        close_failed = False
        for _path, descriptor, _data, _identity in opened:
            try:
                os.close(descriptor)
            except OSError:
                close_failed = True
        if close_failed:
            _raise("FIXED_LOG_CLOSE_FAILED")


def trusted_wrapper_binding() -> dict[str, object]:
    digest = sha256_bytes(TRUSTED_WRAPPER_SOURCE)
    return {
        "schema": "samvil.full-gate-wrapper.v1",
        "source_sha256": digest,
        "content_sha256": digest,
        "mode": "100555",
        "interpreter": "runtime/bin/python3.12",
    }


def trusted_probe_manifest() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for name, command in TRUSTED_PROBE_COMMANDS:
        vector = list(command)
        result.append(
            {
                "name": name,
                "command": vector,
                "sha256": sha256_bytes(canonical_json_bytes(vector)),
            }
        )
    return result


def mktemp_facade_source(runtime_python: str) -> bytes:
    status = "TRUSTED_MKTEMP_FACADE_INVALID"
    if (
        not isinstance(runtime_python, str)
        or not runtime_python.startswith("/")
        or runtime_python.startswith("//")
        or "\x00" in runtime_python
        or "\\" in runtime_python
        or str(Path(runtime_python)) != runtime_python
        or any(part in {"", ".", ".."} for part in runtime_python.split("/")[1:])
        or not runtime_python.endswith("/runtime/bin/python3.12")
    ):
        _raise(status)
    source = f'''#!{runtime_python}
import os
import posixpath
import re
import secrets
import sys

ATTEMPTS = 16
TEMPLATE = "samvil-dogfood-smoke-XXXXXX"
PREFIX = "samvil-dogfood-smoke-"


def _default_token_source():
    return secrets.token_hex(6)


def main(argv, environment, mkdir=os.mkdir, token_source=_default_token_source):
    if argv != ["-d", "-t", TEMPLATE] or not isinstance(environment, dict):
        return 2
    tmpdir = environment.get("TMPDIR")
    if (
        not isinstance(tmpdir, str)
        or not tmpdir.startswith("/")
        or tmpdir.startswith("//")
        or tmpdir == "/"
        or "\\x00" in tmpdir
        or "\\\\" in tmpdir
        or posixpath.normpath(tmpdir) != tmpdir
    ):
        return 2
    for _attempt in range(ATTEMPTS):
        try:
            token = token_source()
        except Exception:
            return 2
        if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{{12}}", token) is None:
            return 2
        candidate = tmpdir + "/" + PREFIX + token
        if posixpath.dirname(candidate) != tmpdir or not candidate.startswith(tmpdir + "/"):
            return 2
        try:
            mkdir(candidate, 0o700)
        except FileExistsError:
            continue
        except OSError:
            return 1
        print(candidate)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], dict(os.environ)))
'''
    try:
        rendered = source.encode("utf-8")
    except UnicodeEncodeError:
        _raise(status)
    if not rendered.startswith(f"#!{runtime_python}\n".encode("utf-8")):
        _raise(status)
    return rendered


def materialize_trusted_wrapper(
    invocation_root: Path, expected_binding: Mapping[str, object]
) -> tuple[Path, dict[str, object]]:
    expected = trusted_wrapper_binding()
    if dict(expected_binding) != expected:
        _raise("TRUSTED_WRAPPER_MANIFEST_INVALID")
    try:
        invocation = invocation_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
    if invocation != invocation_root:
        _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
    wrapper_root = _safe_directory(
        invocation, Path("control"), "TRUSTED_WRAPPER_MATERIALIZATION_FAILED"
    )
    wrapper = wrapper_root / "trusted-full-gate-wrapper.py"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(wrapper, flags, 0o500)
        view = memoryview(TRUSTED_WRAPPER_SOURCE)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
            view = view[written:]
        os.fchmod(descriptor, 0o555)
        os.fsync(descriptor)
        descriptor_state = os.fstat(descriptor)
        path_state = os.lstat(wrapper)
    except FullGateError:
        raise
    except OSError:
        _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
    finally:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
    if (
        FileIdentity.from_stat(descriptor_state) != FileIdentity.from_stat(path_state)
        or not stat.S_ISREG(descriptor_state.st_mode)
        or descriptor_state.st_nlink != 1
        or stat.S_IMODE(descriptor_state.st_mode) != 0o555
        or descriptor_state.st_size != len(TRUSTED_WRAPPER_SOURCE)
    ):
        _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
    observed = {
        **expected,
        "content_sha256": sha256_bytes(wrapper.read_bytes()),
    }
    if observed != expected:
        _raise("TRUSTED_WRAPPER_MATERIALIZATION_FAILED")
    return wrapper, observed


def capture_readonly_tree_identity(root: Path) -> dict[str, object]:
    try:
        canonical = root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("MATERIALIZED_IDENTITY_INVALID")
    if canonical != root:
        _raise("MATERIALIZED_IDENTITY_INVALID")
    stack = [canonical]
    observed: list[dict[str, object]] = []
    total_bytes = 0
    while stack:
        directory = stack.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name, reverse=True)
        except OSError:
            _raise("MATERIALIZED_IDENTITY_INVALID")
        for child in children:
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                _raise("MATERIALIZED_IDENTITY_INVALID")
            path = Path(child.path)
            if stat.S_ISLNK(metadata.st_mode):
                _raise("MATERIALIZED_IDENTITY_INVALID")
            if stat.S_ISDIR(metadata.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                _raise("MATERIALIZED_IDENTITY_INVALID")
            try:
                data = path.read_bytes()
            except OSError:
                _raise("MATERIALIZED_IDENTITY_INVALID")
            total_bytes += len(data)
            observed.append(
                {
                    "path": str(path.relative_to(canonical)),
                    "mode": f"{stat.S_IFREG | stat.S_IMODE(metadata.st_mode):06o}",
                    "size": len(data),
                    "sha256": sha256_bytes(data),
                }
            )
    observed.sort(key=lambda item: item["path"])
    return {
        "sha256": sha256_bytes(canonical_json_bytes(observed)),
        "entries": len(observed),
        "bytes": total_bytes,
    }


def scan_invocation_usage(
    root: Path, limits: Mapping[str, object]
) -> dict[str, int]:
    bounded = _validated_resource_limits(limits)
    try:
        canonical = root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("GATE_INVOCATION_ENTRY_INVALID")
    if canonical != root:
        _raise("GATE_INVOCATION_ENTRY_INVALID")
    stack = [canonical]
    entries = 0
    total = 0
    while stack:
        directory = stack.pop()
        try:
            children = list(os.scandir(directory))
        except OSError:
            _raise("GATE_INVOCATION_ENTRY_INVALID")
        for child in children:
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                _raise("GATE_INVOCATION_ENTRY_INVALID")
            path = Path(child.path)
            if stat.S_ISLNK(metadata.st_mode):
                _raise("GATE_INVOCATION_ENTRY_INVALID")
            if stat.S_ISDIR(metadata.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                _raise("GATE_INVOCATION_ENTRY_INVALID")
            entries += 1
            if metadata.st_size > bounded["per_file_bytes"]:
                _raise("GATE_PER_FILE_BYTES_EXCEEDED")
            total += metadata.st_size
            if total > bounded["aggregate_bytes"]:
                _raise("GATE_AGGREGATE_BYTES_EXCEEDED")
    return {"entries": entries, "bytes": total}


def make_tree_readonly(root: Path) -> None:
    try:
        canonical = root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("MATERIALIZED_READONLY_FAILED")
    if canonical != root:
        _raise("MATERIALIZED_READONLY_FAILED")
    directories: list[Path] = []
    stack = [canonical]
    while stack:
        directory = stack.pop()
        directories.append(directory)
        try:
            children = list(os.scandir(directory))
        except OSError:
            _raise("MATERIALIZED_READONLY_FAILED")
        for child in children:
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                _raise("MATERIALIZED_READONLY_FAILED")
            path = Path(child.path)
            if stat.S_ISLNK(metadata.st_mode):
                _raise("MATERIALIZED_READONLY_FAILED")
            if stat.S_ISDIR(metadata.st_mode):
                stack.append(path)
            elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                mode = 0o555 if metadata.st_mode & 0o111 else 0o444
                try:
                    os.chmod(path, mode, follow_symlinks=False)
                except OSError:
                    _raise("MATERIALIZED_READONLY_FAILED")
            else:
                _raise("MATERIALIZED_READONLY_FAILED")
    for directory in reversed(directories):
        try:
            os.chmod(directory, 0o555, follow_symlinks=False)
        except OSError:
            _raise("MATERIALIZED_READONLY_FAILED")


def _critical_identity(root_name: str, root: Path, relative: str) -> dict[str, object]:
    path = root / relative
    try:
        metadata = os.lstat(path)
        data = path.read_bytes()
    except OSError:
        _raise("MATERIALIZED_IDENTITY_INVALID")
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        _raise("MATERIALIZED_IDENTITY_INVALID")
    return {
        "root": root_name,
        "path": relative,
        "mode": f"{stat.S_IFREG | stat.S_IMODE(metadata.st_mode):06o}",
        "sha256": sha256_bytes(data),
    }


def materialize_wrapper_contract(
    invocation_root: Path,
    manifest: ValidatedManifest,
    *,
    snapshot: Path,
    runtime: Path,
    dependencies: Path,
    tools: Path,
    wrapper: Path,
    scratch: Path,
) -> tuple[Path, str]:
    roots = {
        "snapshot": snapshot,
        "runtime": runtime,
        "dependencies": dependencies,
        "tools": tools,
        "wrapper": wrapper.parent,
    }
    for root in roots.values():
        try:
            root.resolve(strict=True).relative_to(invocation_root)
        except (OSError, RuntimeError, ValueError):
            _raise("TRUSTED_WRAPPER_CONTRACT_INVALID")
    test_paths = [entry["path"] for entry in manifest.raw["collected_mcp_tests"]]
    import_manifest = manifest.raw["import_manifest"]
    if not isinstance(import_manifest, dict):
        _raise("TRUSTED_WRAPPER_CONTRACT_INVALID")
    probe_digests = {
        item["name"]: item["sha256"] for item in trusted_probe_manifest()
    }
    critical = [
        _critical_identity("wrapper", wrapper.parent, wrapper.name),
        _critical_identity("runtime", runtime, "bin/python3.12"),
        _critical_identity("snapshot", snapshot, "scripts/pre-commit-check.sh"),
    ]
    critical.extend(
        _critical_identity("snapshot", snapshot, path) for path in test_paths
    )
    contract = {
        "schema": "samvil.full-gate-wrapper-contract.v1",
        "nonce": manifest.nonce,
        "candidate_command": list(manifest.raw["command"]),
        "test_paths": test_paths,
        "import_allowlist": import_manifest["allowlist"],
        "probe_digests": probe_digests,
        "resource_limits": _validated_resource_limits(manifest.raw["resource_limits"]),
        "runtime_probe_source": RUNTIME_IDENTITY_PROBE_SOURCE,
        "server_probe_source": SERVER_IMPORT_PROBE_SOURCE,
        "roots": {name: str(path) for name, path in sorted(roots.items())},
        "root_digests": {
            name: capture_readonly_tree_identity(path)["sha256"]
            for name, path in sorted(roots.items())
            if name != "wrapper"
        },
        "identity_inventory": critical,
    }
    raw = canonical_json_bytes(contract)
    control = _safe_directory(
        invocation_root, Path("control"), "TRUSTED_WRAPPER_CONTRACT_INVALID"
    )
    relative = str((control / "wrapper-contract.json").relative_to(invocation_root))
    _write_materialized_file(
        invocation_root,
        relative,
        raw,
        "100644",
        "TRUSTED_WRAPPER_CONTRACT_INVALID",
    )
    contract_path = control / "wrapper-contract.json"
    try:
        os.chmod(contract_path, 0o444, follow_symlinks=False)
    except OSError:
        _raise("TRUSTED_WRAPPER_CONTRACT_INVALID")
    return contract_path, sha256_bytes(raw)


def build_sandbox_argv(
    profile: bytes,
    snapshot: Path,
    runtime: Path,
    dependencies: Path,
    tools: Path,
    wrapper: Path,
    contract: Path,
    contract_sha256: str,
    scratch: Path,
    environment: Mapping[str, str],
    *,
    sandbox_executable: Path,
    authority_fd: int,
    nonce: str,
) -> tuple[str, ...]:
    try:
        profile_text = profile.decode("utf-8")
        snapshot_root = snapshot.resolve(strict=True)
        runtime_root = runtime.resolve(strict=True)
        dependencies_root = dependencies.resolve(strict=True)
        tools_root = tools.resolve(strict=True)
        wrapper_path = wrapper.resolve(strict=True)
        contract_path = contract.resolve(strict=True)
        scratch_root = scratch.resolve(strict=True)
        sandbox_path = sandbox_executable.resolve(strict=True)
    except (UnicodeDecodeError, OSError, RuntimeError):
        _raise("SANDBOX_COMMAND_INVALID")
    if (
        snapshot_root != snapshot
        or runtime_root != runtime
        or dependencies_root != dependencies
        or tools_root != tools
        or wrapper_path != wrapper
        or contract_path != contract
        or scratch_root != scratch
        or sandbox_path != sandbox_executable
        or _hex64(contract_sha256, "SANDBOX_COMMAND_INVALID") != contract_sha256
        or not isinstance(authority_fd, int)
        or authority_fd < 3
        or not isinstance(nonce, str)
        or HEX64.fullmatch(nonce) is None
        or "\x00" in profile_text
        or not environment
        or any(
            not isinstance(key, str)
            or not key
            or "=" in key
            or "\x00" in key
            or not isinstance(value, str)
            or "\x00" in value
            for key, value in environment.items()
        )
    ):
        _raise("SANDBOX_COMMAND_INVALID")
    return (
        str(sandbox_path),
        "-p",
        profile_text,
        str(runtime_root / "bin/python3.12"),
        str(wrapper_path),
        "--authority-fd",
        str(authority_fd),
        "--nonce",
        nonce,
        "--snapshot",
        str(snapshot_root),
        "--runtime",
        str(runtime_root),
        "--dependencies",
        str(dependencies_root),
        "--tools",
        str(tools_root),
        "--wrapper",
        str(wrapper_path),
        "--contract",
        str(contract_path),
        "--contract-sha256",
        contract_sha256,
        "--scratch",
        str(scratch_root),
    )


def _terminate_process_group(pgid: int) -> bool:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except PermissionError:
        _raise("CHILD_CLEANUP_FAILED")
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return True
        time.sleep(0.01)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        _raise("CHILD_CLEANUP_FAILED")
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return True
        time.sleep(0.01)
    _raise("CHILD_CLEANUP_FAILED")


def _read_capture(handle: object, status: str) -> bytes:
    try:
        handle.flush()
        handle.seek(0)
        data = handle.read(4 * 1024 * 1024 + 1)
    except (AttributeError, OSError):
        _raise(status)
    if not isinstance(data, bytes) or len(data) > 4 * 1024 * 1024:
        _raise(status)
    return data


def _bounded_internal_file(path: Path, max_bytes: object, status: str) -> bytes:
    if type(max_bytes) is not int or max_bytes <= 0:
        _raise(status)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > max_bytes
        ):
            _raise(status)
        data = os.read(descriptor, max_bytes + 1)
        path_state = os.lstat(path)
    except FullGateError:
        raise
    except OSError:
        _raise(status)
    finally:
        try:
            os.close(descriptor)
        except (OSError, UnboundLocalError):
            pass
    if len(data) != metadata.st_size or len(data) > max_bytes:
        _raise(status)
    if _core_identity(metadata) != _core_identity(path_state):
        _raise(status)
    return data


def _process_snapshot() -> dict[int, tuple[int, int, int, str]]:
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid=,rss=,vsz=,lstart="],
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _raise("PROCESS_INVENTORY_FAILED")
    if result.returncode != 0 or len(result.stdout) > 16 * 1024 * 1024:
        _raise("PROCESS_INVENTORY_FAILED")
    table: dict[int, tuple[int, int, int, str]] = {}
    for raw in result.stdout.decode("utf-8", "strict").splitlines():
        parts = raw.split(None, 4)
        if len(parts) != 5:
            continue
        try:
            pid, ppid, rss_kib, vsz_kib = map(int, parts[:4])
        except ValueError:
            continue
        table[pid] = (ppid, rss_kib * 1024, vsz_kib * 1024, parts[4])
    return table


def _descendant_identities(
    table: Mapping[int, tuple[int, int, int, str]], root_pid: int
) -> tuple[tuple[int, str], ...]:
    descendants: set[int] = set()
    frontier = {root_pid}
    while frontier:
        next_frontier = {
            pid
            for pid, (ppid, _rss, _vsz, _start) in table.items()
            if ppid in frontier and pid not in descendants
        }
        descendants.update(next_frontier)
        frontier = next_frontier
    return tuple(sorted((pid, table[pid][3]) for pid in descendants))


def _kill_tracked_descendants(identities: Sequence[tuple[int, str]]) -> bool:
    cleanup = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, start_identity in identities:
            table = _process_snapshot()
            current = table.get(pid)
            if current is None or current[3] != start_identity:
                continue
            try:
                os.kill(pid, sig)
                cleanup = True
            except ProcessLookupError:
                continue
            except PermissionError:
                _raise("CHILD_CLEANUP_FAILED")
        deadline = time.monotonic() + (0.25 if sig == signal.SIGTERM else 1.0)
        while time.monotonic() < deadline:
            table = _process_snapshot()
            if not any(
                pid in table and table[pid][3] == start_identity
                for pid, start_identity in identities
            ):
                return cleanup
            time.sleep(0.01)
    table = _process_snapshot()
    if any(
        pid in table and table[pid][3] == start_identity
        for pid, start_identity in identities
    ):
        _raise("CHILD_CLEANUP_FAILED")
    return cleanup


def supervise_process(
    process: subprocess.Popen[bytes],
    *,
    timeout: float,
    stdout_handle: object,
    stderr_handle: object,
    authority_read_fd: int | None = None,
    nonce: str | None = None,
    limits: Mapping[str, object] | None = None,
) -> GateOutcome:
    if not math.isfinite(timeout) or timeout <= 0:
        _raise("INVALID_TIMEOUT")
    deadline = time.monotonic() + timeout
    timed_out = False
    cleanup = False
    resource_status: str | None = None
    bounded = _validated_resource_limits(limits or DEFAULT_RESOURCE_LIMITS)
    authority = bytearray()
    observed_descendants: dict[int, str] = {}
    wrapper_start_identity: str | None = None
    if authority_read_fd is not None:
        try:
            flags = fcntl.fcntl(authority_read_fd, fcntl.F_GETFL)
            fcntl.fcntl(authority_read_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        except OSError:
            _raise("AUTHORITY_PIPE_INVALID")

    def process_snapshot() -> dict[int, tuple[int, int, int, str]]:
        try:
            return _process_snapshot()
        except BaseException as inventory_error:
            try:
                _terminate_process_group(process.pid)
                process.wait(timeout=2)
            except BaseException as cleanup_error:
                raise cleanup_error from inventory_error
            raise

    while process.poll() is None:
        try:
            stdout_size = os.fstat(stdout_handle.fileno()).st_size
            stderr_size = os.fstat(stderr_handle.fileno()).st_size
        except (AttributeError, OSError):
            resource_status = "capture_identity"
            cleanup = _terminate_process_group(process.pid) or cleanup
            break
        if stdout_size > bounded["stdout_bytes"]:
            resource_status = "GATE_STDOUT_BYTES_EXCEEDED"
            cleanup = _terminate_process_group(process.pid) or cleanup
            break
        if stderr_size > bounded["stderr_bytes"]:
            resource_status = "GATE_STDERR_BYTES_EXCEEDED"
            cleanup = _terminate_process_group(process.pid) or cleanup
            break
        if authority_read_fd is not None:
            try:
                while True:
                    chunk = os.read(authority_read_fd, 64 * 1024)
                    if not chunk:
                        break
                    authority.extend(chunk)
                    if len(authority) > bounded["authority_aggregate_bytes"]:
                        resource_status = "AUTHORITY_FRAME_AGGREGATE_EXCEEDED"
                        cleanup = _terminate_process_group(process.pid) or cleanup
                        break
            except BlockingIOError:
                pass
            except OSError:
                resource_status = "AUTHORITY_PIPE_INVALID"
                cleanup = _terminate_process_group(process.pid) or cleanup
                break
        table = process_snapshot()
        root = table.get(process.pid)
        if root is not None:
            if wrapper_start_identity is None:
                wrapper_start_identity = root[3]
            elif wrapper_start_identity != root[3]:
                resource_status = "WRAPPER_IDENTITY_DRIFT"
                cleanup = _terminate_process_group(process.pid) or cleanup
                break
            descendants = _descendant_identities(table, process.pid)
            for pid, start_identity in descendants:
                observed_descendants[pid] = start_identity
            if len(descendants) > bounded["descendants"]:
                resource_status = "GATE_DESCENDANT_LIMIT_EXCEEDED"
                cleanup = _terminate_process_group(process.pid) or cleanup
                break
            rss = root[1] + sum(table[pid][1] for pid, _start in descendants if pid in table)
            address_space = root[2] + sum(
                table[pid][2] for pid, _start in descendants if pid in table
            )
            if rss > bounded["rss_bytes"]:
                resource_status = "GATE_RSS_BYTES_EXCEEDED"
                cleanup = _terminate_process_group(process.pid) or cleanup
                break
            if address_space > bounded["address_space_bytes"]:
                resource_status = "GATE_ADDRESS_SPACE_BYTES_EXCEEDED"
                cleanup = _terminate_process_group(process.pid) or cleanup
                break
        if time.monotonic() >= deadline:
            timed_out = True
            cleanup = _terminate_process_group(process.pid) or cleanup
            break
        time.sleep(0.01)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        cleanup = _terminate_process_group(process.pid) or cleanup
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _raise("CHILD_WAIT_FAILED")
    if not timed_out and resource_status is None:
        cleanup = _terminate_process_group(process.pid) or cleanup
    if authority_read_fd is not None:
        try:
            while True:
                chunk = os.read(authority_read_fd, 64 * 1024)
                if not chunk:
                    break
                authority.extend(chunk)
        except BlockingIOError:
            pass
        except OSError:
            _raise("AUTHORITY_PIPE_INVALID")
    table = process_snapshot()
    survivors = tuple(
        (pid, start_identity)
        for pid, start_identity in sorted(observed_descendants.items())
        if pid in table and table[pid][3] == start_identity
    )
    if survivors:
        try:
            cleanup = _kill_tracked_descendants(survivors) or cleanup
        except BaseException as cleanup_error:
            try:
                _terminate_process_group(process.pid)
            except BaseException as group_error:
                raise group_error from cleanup_error
            raise
    stdout = _read_capture(stdout_handle, "STDOUT_CAPTURE_INVALID")
    stderr = _read_capture(stderr_handle, "STDERR_CAPTURE_INVALID")
    frames: tuple[dict[str, object], ...] = ()
    if authority_read_fd is not None and resource_status is None and not timed_out:
        if nonce is None:
            _raise("AUTHORITY_FRAME_INVALID")
        frames = decode_authority_frames(
            bytes(authority),
            nonce=nonce,
            limits=bounded,
            wrapper_exited=True,
        )
    return GateOutcome(
        returncode=process.returncode,
        timed_out=timed_out,
        cleanup_performed=cleanup,
        resource_status=resource_status,
        stdout=stdout,
        stderr=stderr,
        authority_frames=frames,
        wrapper_pid=process.pid,
        wrapper_start_identity=wrapper_start_identity,
        observed_descendants=tuple(sorted(observed_descendants.items())),
    )


def run_gate_once(
    profile: bytes,
    snapshot: Path,
    runtime: Path,
    dependencies: Path,
    tools: Path,
    wrapper: Path,
    contract: Path,
    contract_sha256: str,
    scratch: Path,
    environment: Mapping[str, str],
    *,
    sandbox_executable: Path,
    timeout: float,
    limits: Mapping[str, object],
    nonce: str,
) -> GateOutcome:
    bounded = _validated_resource_limits(limits)
    argv = build_sandbox_argv(
        profile,
        snapshot,
        runtime,
        dependencies,
        tools,
        wrapper,
        contract,
        contract_sha256,
        scratch,
        environment,
        sandbox_executable=sandbox_executable,
        authority_fd=3,
        nonce=nonce,
    )
    raw_tmpdir = environment.get("TMPDIR")
    if raw_tmpdir is None:
        _raise("HERMETIC_ENVIRONMENT_INVALID")
    tmpdir = _canonical_destination(
        Path(raw_tmpdir), "HERMETIC_ENVIRONMENT_INVALID", must_exist=True
    )

    def apply_limits() -> None:
        def lower(which: int, requested: int) -> None:
            _soft, hard = resource.getrlimit(which)
            value = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
            resource.setrlimit(which, (value, value))

        lower(resource.RLIMIT_FSIZE, bounded["file_size_bytes"])
        lower(
            resource.RLIMIT_CPU,
            min(bounded["cpu_seconds"], max(1, math.ceil(timeout) + 5)),
        )
        lower(resource.RLIMIT_NOFILE, bounded["nofile"])

    read_fd, write_fd = create_cloexec_pipe()
    actual_argv = argv
    authority_index = actual_argv.index("--authority-fd") + 1
    actual_argv = (*actual_argv[:authority_index], str(write_fd), *actual_argv[authority_index + 1 :])
    with tempfile.TemporaryFile(mode="w+b", dir=tmpdir) as stdout_handle, tempfile.TemporaryFile(
        mode="w+b", dir=tmpdir
    ) as stderr_handle:
        try:
            process = subprocess.Popen(
                actual_argv,
                cwd=snapshot,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                preexec_fn=apply_limits,
                close_fds=True,
                pass_fds=(write_fd,),
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            os.close(read_fd)
            os.close(write_fd)
            _raise("GATE_SPAWN_FAILED")
        os.close(write_fd)
        try:
            return supervise_process(
                process,
                timeout=timeout,
                stdout_handle=stdout_handle,
                stderr_handle=stderr_handle,
                authority_read_fd=read_fd,
                nonce=nonce,
                limits=bounded,
            )
        finally:
            os.close(read_fd)


def _one_counter(pattern: bytes, value: bytes, status: str) -> int:
    matches = re.findall(pattern, value, flags=re.MULTILINE)
    if len(matches) != 1:
        _raise(status)
    try:
        parsed = int(matches[0])
    except (TypeError, ValueError, OverflowError):
        _raise(status)
    if parsed < 0 or parsed > 10_000_000:
        _raise(status)
    return parsed


def validate_gate_process_outcome(outcome: GateOutcome) -> None:
    if outcome.timed_out:
        _raise("GATE_TIMEOUT")
    if outcome.resource_status is not None:
        _raise(outcome.resource_status)
    if outcome.cleanup_performed:
        _raise("GATE_DESCENDANT_CLEANUP_REQUIRED")
    if outcome.returncode != 0:
        _raise("GATE_EXIT_NONZERO")


def validate_gate_outcome(
    outcome: GateOutcome,
    logs: Mapping[str, bytes],
    expected_counters: Mapping[str, int],
    *,
    execution_evidence: ExecutionEvidence | None,
) -> dict[str, int]:
    validate_gate_process_outcome(outcome)
    if execution_evidence is None:
        _raise("EXECUTION_EVIDENCE_MISSING")
    if execution_evidence.facade_roles != ("pytest", "server_import"):
        _raise("EXECUTION_EVIDENCE_INVALID")
    if (
        type(execution_evidence.pytest_passed) is not int
        or execution_evidence.pytest_passed < 0
        or type(execution_evidence.mcp_tools) is not int
        or execution_evidence.mcp_tools < 0
    ):
        _raise("EXECUTION_EVIDENCE_INVALID")
    _hex64(execution_evidence.digest, "EXECUTION_EVIDENCE_INVALID")
    _hex64(
        execution_evidence.import_manifest_sha256,
        "EXECUTION_EVIDENCE_INVALID",
    )
    expected_log_names = {Path(path).name for path in FIXED_LOG_PATHS}
    if set(logs) != expected_log_names or any(
        not isinstance(value, bytes) or len(value) > 32 * 1024 * 1024
        for value in logs.values()
    ):
        _raise("FIXED_LOG_SET_INVALID")
    pass_lines = re.findall(
        rb"^\xe2\x95\x90\xe2\x95\x90\xe2\x95\x90 pre-commit check: PASS \xe2\x95\x90\xe2\x95\x90\xe2\x95\x90$",
        outcome.stdout,
        flags=re.MULTILINE,
    )
    if len(pass_lines) != 1 or b"pre-commit check:" not in outcome.stdout:
        _raise("GATE_PASS_MARKER_INVALID")
    pretest = logs["samvil-pretest.log"]
    markdown = logs["samvil-mdrefs.log"]
    host = logs["samvil-hostparity.log"]
    forward = logs["samvil-forward.log"]
    agents = logs["samvil-agent-inventory.log"]
    host_pairs = _one_counter(rb"^UNTESTED: ([0-9]+) pairs?", host, "HOST_COUNTER_INVALID")
    host_native = len(re.findall(rb"^UNTESTED: .*native", host, flags=re.MULTILINE))
    persona = _one_counter(
        rb"Agent inventory consistent: ([0-9]+) persona files,",
        agents,
        "AGENT_COUNTER_INVALID",
    )
    inline = _one_counter(
        rb"Agent inventory consistent: [0-9]+ persona files, ([0-9]+) inline identities",
        agents,
        "AGENT_COUNTER_INVALID",
    )
    counters = {
        "pytest_passed": execution_evidence.pytest_passed,
        "mcp_tools": execution_evidence.mcp_tools,
        "markdown_references": _one_counter(
            rb"all markdown references resolve \(([0-9]+) files scanned\)",
            markdown,
            "MARKDOWN_COUNTER_INVALID",
        ),
        "host_untested": host_pairs + host_native,
        "forward_registered_tools": _one_counter(
            rb"^  Registered @mcp\.tool\(\) functions: ([0-9]+)$",
            forward,
            "FORWARD_COUNTER_INVALID",
        ),
        "forward_cited_tools": _one_counter(
            rb"^  Distinct tool refs in skill files: ([0-9]+)$",
            forward,
            "FORWARD_COUNTER_INVALID",
        ),
        "agent_inventory_entries": persona + inline,
    }
    trusted_expected = _validate_semantic_counters(
        dict(expected_counters), "SEMANTIC_COUNTER_SCHEMA_INVALID"
    )
    if counters != trusted_expected:
        _raise("SEMANTIC_COUNTER_MISMATCH")
    return counters


def verify_target_manifests(
    manifest: ValidatedManifest, verified: VerifiedGitObjectPack
) -> str:
    inventory = [
        {
            "path": path,
            "mode": verified.modes[path],
            "blob": verified.blobs[path],
            "sha256": sha256_bytes(verified.files[path]),
        }
        for path in sorted(verified.files)
    ]
    inventory_map = {entry["path"]: entry for entry in inventory}
    if manifest.raw["inventory"] != inventory:
        _raise("TARGET_INVENTORY_MISMATCH")
    expected_gate = [inventory_map.get("scripts/pre-commit-check.sh")]
    expected_phase6 = [
        inventory_map.get("scripts/phase6-real-runtime-dogfood.py"),
        inventory_map.get("mcp/tests/test_phase6_real_runtime_dogfood.py"),
    ]
    expected_collected = [
        inventory_map[path]
        for path in sorted(inventory_map)
        if path.startswith("mcp/tests/")
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
    ]
    if manifest.raw["gate_inventory"] != expected_gate:
        _raise("GATE_INVENTORY_INVALID")
    if manifest.raw["phase6_inventory"] != expected_phase6:
        _raise("PHASE6_INVENTORY_INVALID")
    if manifest.raw["collected_mcp_tests"] != expected_collected:
        _raise("COLLECTED_TESTS_INCOMPLETE")
    imports = manifest.raw["import_manifest"]
    if not isinstance(imports, dict) or not isinstance(imports.get("allowlist"), list):
        _raise("IMPORT_MANIFEST_INVALID")
    for module in imports["allowlist"]:
        prefix = f"mcp/{module.replace('.', '/')}"
        if not any(
            path == f"{prefix}.py" or path.startswith(f"{prefix}/")
            for path in inventory_map
        ):
            _raise("IMPORT_MANIFEST_INCOMPLETE")
    derived = sha256_bytes(
        canonical_json_bytes(
            {
                "allowlist": imports["allowlist"],
                "collected_mcp_tests": expected_collected,
            }
        )
    )
    if imports.get("sha256") != derived:
        _raise("IMPORT_MANIFEST_INVALID")
    return derived


def _observe_regular_file(path: Path, expected_mode: str) -> dict[str, object]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _raise("EXECUTION_EVIDENCE_INVALID")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or f"{stat.S_IMODE(metadata.st_mode) | stat.S_IFREG:06o}" != expected_mode
            or metadata.st_size > 16 * 1024 * 1024
        ):
            _raise("EXECUTION_EVIDENCE_INVALID")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                _raise("EXECUTION_EVIDENCE_INVALID")
            chunks.append(chunk)
            remaining -= len(chunk)
        path_state = os.lstat(path)
        if _core_identity(metadata) != _core_identity(path_state):
            _raise("EXECUTION_EVIDENCE_INVALID")
        data = b"".join(chunks)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    try:
        os.close(descriptor)
    except OSError:
        _raise("EXECUTION_EVIDENCE_INVALID")
    return {"mode": expected_mode, "sha256": sha256_bytes(data)}


def measure_materialized_execution(
    snapshot: Path,
    runtime: Path,
    facade_digest: str,
) -> str:
    runtime_executable = _observe_regular_file(
        runtime / "bin/python3.12", "100555"
    )
    facade_entries = [
        {
            "path": path,
            **_observe_regular_file(
                snapshot / path,
                "100444" if path == FACADE_PATHS[3] else "100555",
            ),
        }
        for path in FACADE_PATHS
    ]
    observed_facade_digest = sha256_bytes(canonical_json_bytes(facade_entries))
    logical_facade_digest = sha256_bytes(
        canonical_json_bytes(
            [
                {
                    "path": entry["path"],
                    "mode": "100644" if entry["path"] == FACADE_PATHS[3] else "100755",
                    "sha256": entry["sha256"],
                }
                for entry in facade_entries
            ]
        )
    )
    if logical_facade_digest != facade_digest:
        _raise("EXECUTION_EVIDENCE_INVALID")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "runtime_executable": runtime_executable,
                "facade_sha256": observed_facade_digest,
                "logical_facade_sha256": logical_facade_digest,
            }
        )
    )


def observe_execution_evidence(
    manifest: ValidatedManifest,
    verified: VerifiedGitObjectPack,
    snapshot: Path,
    runtime: Path,
    facade_digest: str,
    authority_frames: Sequence[Mapping[str, object]],
    *,
    expected_execution_digest: str,
) -> ExecutionEvidence:
    import_digest = verify_target_manifests(manifest, verified)
    if tuple(frame.get("phase") for frame in authority_frames) != AUTHORITY_PHASES:
        _raise("EXECUTION_EVIDENCE_INVALID")
    if any(frame.get("status") != "PASS" for frame in authority_frames):
        _raise("EXECUTION_EVIDENCE_INVALID")
    pytest_evidence = authority_frames[1].get("evidence")
    server_evidence = authority_frames[2].get("evidence")
    if not isinstance(pytest_evidence, dict) or not isinstance(server_evidence, dict):
        _raise("EXECUTION_EVIDENCE_INVALID")
    pytest_passed = pytest_evidence.get("pytest_passed")
    mcp_tools = server_evidence.get("tool_count")
    if (
        type(pytest_passed) is not int
        or pytest_passed < 0
        or type(mcp_tools) is not int
        or mcp_tools < 0
    ):
        _raise("EXECUTION_EVIDENCE_INVALID")
    roles = ("pytest", "server_import")
    measured_execution_digest = measure_materialized_execution(
        snapshot, runtime, facade_digest
    )
    if measured_execution_digest != _hex64(
        expected_execution_digest, "EXECUTION_EVIDENCE_INVALID"
    ):
        _raise("EXECUTION_EVIDENCE_CHANGED")
    payload = {
        "schema": "samvil.full-gate-execution-evidence.v1",
        "facade_roles": list(roles),
        "import_manifest_sha256": import_digest,
        "materialized_execution_sha256": measured_execution_digest,
        "authority_frames": list(authority_frames),
    }
    return ExecutionEvidence(
        digest=sha256_bytes(canonical_json_bytes(payload)),
        import_manifest_sha256=import_digest,
        facade_roles=roles,
        pytest_passed=pytest_passed,
        mcp_tools=mcp_tools,
    )


def build_pass_receipt(
    manifest: ValidatedManifest,
    counters: Mapping[str, int],
    digests: ReceiptDigests,
    *,
    prior_receipt_sha256: str | None = None,
) -> bytes:
    semantic = _validate_semantic_counters(
        dict(counters), "SEMANTIC_COUNTER_SCHEMA_INVALID"
    )
    for value in (
        digests.command,
        digests.content,
        digests.profile,
        digests.imports,
        digests.identity,
        digests.tree,
        digests.runtime,
    ):
        _hex64(value, "RECEIPT_DIGEST_INVALID")
    import_manifest = manifest.raw["import_manifest"]
    if (
        not isinstance(import_manifest, dict)
        or digests.imports != import_manifest.get("sha256")
    ):
        _raise("RECEIPT_DIGEST_INVALID")
    expected_prior = (
        manifest.prior_receipt_sha256
        if manifest.target_kind == "candidate_postcommit"
        else None
    )
    if prior_receipt_sha256 != expected_prior:
        _raise("RECEIPT_PRIOR_BINDING_INVALID")
    payload = {
        "schema": "samvil.full-gate-receipt.v1",
        "status": "PASS",
        "verdict": "PASS",
        "nonce": manifest.nonce,
        "control_commit": manifest.control_commit,
        "control_tree": manifest.control_tree,
        "target_kind": manifest.target_kind,
        "source_commit": manifest.source_commit,
        "candidate_tree": manifest.candidate_tree,
        "final_commit": manifest.final_commit,
        "expected_parent": manifest.expected_parent,
        "authorization_sha256": manifest.authorization_sha256,
        "manifest_sha256": manifest.manifest_sha256,
        "prior_receipt_sha256": prior_receipt_sha256,
        "command_sha256": digests.command,
        "content_sha256": digests.content,
        "profile_class": PROFILE_CLASS,
        "profile_sha256": digests.profile,
        "import_manifest_sha256": digests.imports,
        "identity_sha256": digests.identity,
        "tree_sha256": digests.tree,
        "runtime_sha256": digests.runtime,
        "semantic_counters": semantic,
        "promotion_limitations": list(PROMOTION_LIMITATIONS),
    }
    if tuple(payload) != RECEIPT_FIELDS:
        _raise("RECEIPT_SCHEMA_INVALID")
    return canonical_json_bytes(payload)


def _reject_environment_authority(environment: Mapping[str, str]) -> None:
    forbidden = {
        "PROFILE_CLASS",
        "SAMVIL_PROFILE_CLASS",
        "SAMVIL_FULL_GATE_ROOT",
        "SAMVIL_FULL_GATE_PROFILE_CLASS",
        "SAMVIL_TARGET_ROOT",
        "SAMVIL_CONTROL_ROOT",
    }
    if any(key in environment for key in forbidden) or any(
        key.startswith("SAMVIL_FULL_GATE_") for key in environment
    ):
        _raise("FULL_GATE_ENV_AUTHORITY_REJECTED")


def _validated_temp_parent(
    environment: Mapping[str, str], control_root: Path
) -> Path:
    raw = environment.get("TMPDIR")
    if not isinstance(raw, str) or not Path(raw).is_absolute():
        _raise("TMPDIR_INVALID")
    path = Path(raw)
    try:
        resolved = path.resolve(strict=True)
        metadata = os.lstat(path)
    except (OSError, RuntimeError):
        _raise("TMPDIR_INVALID")
    if (
        str(resolved) != raw
        or resolved != path
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
    ):
        _raise("TMPDIR_INVALID")
    try:
        resolved.relative_to(control_root)
    except ValueError:
        pass
    else:
        _raise("TMPDIR_INVALID")
    return resolved


def _external_references(manifest: ValidatedManifest) -> tuple[tuple[str, dict[str, str]], ...]:
    object_pack = manifest.raw["object_pack"]
    runtime = manifest.raw["runtime"]
    if not isinstance(object_pack, dict) or not isinstance(runtime, dict):
        _raise("MANIFEST_FIELDS_INVALID")
    references: list[tuple[str, dict[str, str]]] = [
        ("object_pack", object_pack),
    ]
    for role in RUNTIME_ARTIFACT_FIELDS:
        value = runtime.get(role)
        if not isinstance(value, dict):
            _raise("RUNTIME_MANIFEST_INVALID")
        references.append((role, value))
    parser = manifest.raw.get("host_tool_identity_parser")
    if parser is not None:
        if not isinstance(parser, Mapping):
            _raise("HOST_TOOL_IDENTITY_PARSER_INVALID")
        source_artifact = parser.get("source_artifact")
        inputs = parser.get("inputs")
        if not isinstance(source_artifact, dict) or not isinstance(inputs, list):
            _raise("HOST_TOOL_IDENTITY_PARSER_INVALID")
        references.append(
            ("host_tool_identity_parser_source", source_artifact)
        )
        for entry in inputs:
            if not isinstance(entry, Mapping):
                _raise("HOST_TOOL_IDENTITY_PARSER_INVALID")
            role = entry.get("role")
            path = entry.get("path")
            sha256 = entry.get("sha256")
            if (
                not isinstance(role, str)
                or not isinstance(path, str)
                or not isinstance(sha256, str)
            ):
                _raise("HOST_TOOL_IDENTITY_PARSER_INVALID")
            references.append(
                (
                    f"host_tool_identity_parser_input:{role}",
                    {"path": path, "sha256": sha256},
                )
            )
    return tuple(references)


def _cleanup_owned_fixed_logs(protocol: FixedLogProtocol) -> None:
    failed = False
    for path in protocol.log_paths:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError:
            failed = True
            continue
        try:
            if stat.S_ISDIR(metadata.st_mode):
                failed = True
            else:
                os.unlink(path)
        except OSError:
            failed = True
    if failed:
        _raise("FIXED_LOG_CLEANUP_FAILED")


def _failure_receipt(status: str, nonce: str) -> bytes:
    return canonical_json_bytes(
        {
            "schema": "samvil.full-gate-failure.v1",
            "status": status,
            "verdict": "BLOCKED",
            "nonce": nonce,
        }
    )


def execute_full_gate(
    arguments: FullGateArguments,
    *,
    source_environment: Mapping[str, str],
    control_root: Path,
) -> int:
    _reject_environment_authority(source_environment)
    manifest_artifact: HeldArtifact | None = None
    held_inputs: list[HeldArtifact] = []
    outputs: OutputFiles | None = None
    protocol: FixedLogProtocol | None = None
    invocation_root: Path | None = None
    platform_authority: HeldApplePlatformTCB | HeldCanonicalHostAuthority | None = None
    outcome: GateOutcome | None = None
    primary: FullGateError | None = None
    receipt_bytes: bytes | None = None
    denial_bytes = b""
    try:
        manifest_artifact = open_external_control_artifact(
            arguments.manifest,
            max_bytes=16 * 1024 * 1024,
            status="MANIFEST_ARTIFACT_INVALID",
        )
        held_inputs.append(manifest_artifact)
        manifest_object = decode_canonical_json_bytes(
            manifest_artifact.data,
            status="MANIFEST_JSON_INVALID",
            max_bytes=16 * 1024 * 1024,
        )
        manifest = validate_manifest_object(manifest_object)
        validate_cli_target_binding(arguments, manifest)
        approved_host_tools = "canonical_host_tools" in manifest.raw

        accepted_prior_sha256: str | None = None
        if arguments.prior_receipt is not None:
            if manifest.prior_receipt_sha256 is None:
                _raise("PRIOR_RECEIPT_FORBIDDEN")
            prior = open_external_artifact(
                arguments.prior_receipt,
                manifest.prior_receipt_sha256,
                max_bytes=8 * 1024 * 1024,
                status="PRIOR_RECEIPT_ARTIFACT_INVALID",
            )
            held_inputs.append(prior)
            prior_object = decode_canonical_json_bytes(
                prior.data,
                status="PRIOR_RECEIPT_JSON_INVALID",
                max_bytes=8 * 1024 * 1024,
            )
            accepted_prior_sha256 = validate_prior_receipt_object(
                manifest, prior_object, prior.data
            )

        artifacts: dict[str, HeldArtifact] = {}
        for role, reference in _external_references(manifest):
            held = open_external_artifact(
                reference["path"],
                reference["sha256"],
                max_bytes=(
                    256 * 1024 * 1024
                    if role.endswith("archive") or role == "object_pack"
                    else 16 * 1024 * 1024
                ),
                status=(
                    "OBJECT_PACK_INVALID"
                    if role == "object_pack"
                    else "RUNTIME_ARTIFACT_INVALID"
                ),
            )
            artifacts[role] = held
            held_inputs.append(held)
        identities = {
            (held.identity.device, held.identity.inode) for held in held_inputs
        }
        if len(identities) != len(held_inputs):
            _raise("EXTERNAL_ARTIFACT_ALIAS_INVALID")

        try:
            canonical_control = control_root.resolve(strict=True)
        except (OSError, RuntimeError):
            _raise("CONTROL_IDENTITY_MISMATCH")
        if canonical_control != control_root:
            _raise("CONTROL_IDENTITY_MISMATCH")
        for held in held_inputs:
            try:
                held.path.relative_to(canonical_control)
            except ValueError:
                continue
            _raise("EXTERNAL_ARTIFACT_LOCATION_INVALID")

        reserved = tuple(held.path for held in held_inputs)
        receipt_target = _preflight_absent_output(
            arguments.receipt, "OUTPUT_PATH_INVALID"
        )
        denial_target = _preflight_absent_output(
            arguments.denial_log, "OUTPUT_PATH_INVALID"
        )
        output_keys = {
            _output_collision_key(receipt_target),
            _output_collision_key(denial_target),
        }
        if len(output_keys) != 2 or output_keys.intersection(
            {_output_collision_key(path) for path in reserved}
        ):
            _raise("OUTPUT_PATH_COLLISION")

        temp_parent = _validated_temp_parent(source_environment, canonical_control)
        try:
            invocation_root = Path(
                tempfile.mkdtemp(prefix="samvil-full-gate-", dir=temp_parent)
            ).resolve(strict=True)
        except (OSError, RuntimeError):
            _raise("INVOCATION_CREATE_FAILED")
        if invocation_root.parent != temp_parent:
            _raise("INVOCATION_CREATE_FAILED")

        platform_scratch = _safe_directory(
            invocation_root, Path("host-platform"), "UNSUPPORTED_HERMETIC_RUNTIME"
        )
        sandbox_executable = APPLE_SANDBOX_EXEC
        if not approved_host_tools:
            platform_authority = acquire_apple_platform_tcb(
                manifest.raw["apple_platform_tcb"], platform_scratch
            )

        runtime_root = invocation_root / "runtime"
        dependency_root = invocation_root / "dependencies"
        tools_root = invocation_root / "tools"
        runtime_materialized = materialize_closure_archive(
            artifacts["python_archive"].data,
            artifacts["python_manifest"].data,
            runtime_root,
            expected_role="python",
        )
        dependency_materialized = materialize_closure_archive(
            artifacts["dependency_archive"].data,
            artifacts["dependency_manifest"].data,
            dependency_root,
            expected_role="dependencies",
        )
        tools_materialized = materialize_closure_archive(
            artifacts["tool_archive"].data,
            artifacts["tool_manifest"].data,
            tools_root,
            expected_role="tools",
        )
        tool_probe_root = _safe_directory(
            invocation_root, Path("tool-probe"), "UNSUPPORTED_HERMETIC_RUNTIME"
        )
        tool_evidence = validate_tool_closure(tools_root, tool_probe_root)
        _remove_invocation_tree(tool_probe_root, "TOOL_PROBE_CLEANUP_FAILED")
        materialize_runtime_python_facade(
            invocation_root, runtime_root, tools_root
        )
        materialize_runtime_dirname_facade(
            invocation_root, runtime_root, tools_root
        )
        hermetic_environment = build_hermetic_environment(
            invocation_root,
            runtime_root,
            tools_root,
            source_environment=source_environment,
        )
        control_digest = validate_control_identity(
            canonical_control, manifest, hermetic_environment
        )
        verified_pack = verify_git_object_pack(
            manifest, artifacts["object_pack"].data
        )
        snapshot = invocation_root / "snapshot"
        snapshot_digest = materialize_verified_snapshot(verified_pack, snapshot)
        facade_digest = materialize_facade(
            artifacts["facade_manifest"].data, snapshot, invocation_root
        )
        wrapper, wrapper_binding = materialize_trusted_wrapper(
            invocation_root, manifest.raw["trusted_wrapper"]
        )
        scratch = _safe_directory(
            invocation_root, Path("scratch"), "TRUSTED_WRAPPER_CONTRACT_INVALID"
        )
        for relative in ("candidate", "runtime", "pytest", "server"):
            _safe_directory(
                scratch, Path(relative), "TRUSTED_WRAPPER_CONTRACT_INVALID"
            )
        for root in (snapshot, runtime_root, dependency_root, tools_root):
            make_tree_readonly(root)
        runtime_identity = validate_hermetic_runtime(
            runtime_root, manifest.raw["runtime"]["python_identity"]
        )
        if approved_host_tools:
            parser_scratch = _safe_directory(
                invocation_root,
                Path("host-tool-parser"),
                "HOST_TOOL_IDENTITY_PARSER_INVALID",
            )
            parser_evidence = prepare_approved_host_tool_parser(
                manifest.raw["host_tool_identity_parser"],
                artifacts,
                runtime_root=runtime_root,
                scratch_root=parser_scratch,
            )
            platform_authority = acquire_runtime_manifest_host_tool_authority(
                manifest,
                platform_scratch,
                parser_evidence=parser_evidence,
            )
            sandbox_executable = platform_authority.executable_path(
                "sandbox-exec"
            )
        contract, contract_sha256 = materialize_wrapper_contract(
            invocation_root,
            manifest,
            snapshot=snapshot,
            runtime=runtime_root,
            dependencies=dependency_root,
            tools=tools_root,
            wrapper=wrapper,
            scratch=scratch,
        )
        expected_execution_digest = measure_materialized_execution(
            snapshot, runtime_root, facade_digest
        )

        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        protected_roots = (home, home / ".codex")
        profile, profile_source_sha256, _rendered_profile_sha256 = render_loopback_profile(
            invocation_root,
            snapshot,
            runtime_root,
            tools_root,
            protected_roots=protected_roots,
            executable_allowlist=build_gate_executable_allowlist(
                snapshot=snapshot,
                runtime=runtime_root,
                tools=tools_root,
                wrapper=wrapper,
            ),
            writable_roots=(
                scratch,
                *(Path(hermetic_environment[key]) for key in (
                    "HOME",
                    "CODEX_HOME",
                    "CLAUDE_CONFIG_DIR",
                    "GNUPGHOME",
                    "TMPDIR",
                    "XDG_CACHE_HOME",
                    "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME",
                    "XDG_STATE_HOME",
                )),
            ),
        )
        protocol = acquire_fixed_log_protocol()
        outputs = create_output_files(
            arguments.receipt,
            arguments.denial_log,
            reserved_paths=reserved,
        )
        outcome = run_gate_once(
            profile,
            snapshot,
            runtime_root,
            dependency_root,
            tools_root,
            wrapper,
            contract,
            contract_sha256,
            scratch,
            hermetic_environment,
            sandbox_executable=sandbox_executable,
            timeout=arguments.timeout,
            limits=manifest.raw["resource_limits"],
            nonce=manifest.nonce,
        )
        if platform_authority is None:
            _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
        platform_evidence = platform_authority.complete()
        platform_authority.close()
        platform_authority = None
        candidate_stdout = _bounded_internal_file(
            scratch / "candidate/stdout",
            manifest.raw["resource_limits"]["stdout_bytes"],
            "GATE_STDOUT_BYTES_EXCEEDED",
        )
        candidate_stderr = _bounded_internal_file(
            scratch / "candidate/stderr",
            manifest.raw["resource_limits"]["stderr_bytes"],
            "GATE_STDERR_BYTES_EXCEEDED",
        )
        outcome = replace(
            outcome,
            stdout=candidate_stdout,
            stderr=candidate_stderr + outcome.stderr,
        )
        denial_bytes = outcome.stderr
        captured = capture_fixed_logs(protocol, invocation_root / "captured-logs")
        protocol.close()
        protocol = None
        logs = {
            item.name: (invocation_root / "captured-logs" / item.name).read_bytes()
            for item in captured
        }
        validate_gate_process_outcome(outcome)
        execution_evidence = observe_execution_evidence(
            manifest,
            verified_pack,
            snapshot,
            runtime_root,
            facade_digest,
            outcome.authority_frames,
            expected_execution_digest=expected_execution_digest,
        )
        counters = validate_gate_outcome(
            outcome,
            logs,
            manifest.raw["semantic_counters"],
            execution_evidence=execution_evidence,
        )
        invocation_usage = scan_invocation_usage(
            invocation_root, manifest.raw["resource_limits"]
        )
        for held in held_inputs:
            held.assert_stable()
        import_manifest = manifest.raw["import_manifest"]
        if not isinstance(import_manifest, dict) or not isinstance(
            import_manifest.get("sha256"), str
        ):
            _raise("IMPORT_MANIFEST_INVALID")
        runtime_digest = sha256_bytes(
            canonical_json_bytes(
                {
                    "python": runtime_materialized,
                    "dependencies": dependency_materialized,
                    "tools": tools_materialized,
                    "tool_evidence": tool_evidence,
                    "facade": facade_digest,
                    "wrapper": wrapper_binding,
                    "runtime_identity": runtime_identity,
                    **(
                        {"canonical_host_tools": platform_evidence}
                        if approved_host_tools
                        else {"apple_platform": platform_evidence}
                    ),
                    "artifacts": {
                        role: sha256_bytes(artifact.data)
                        for role, artifact in sorted(artifacts.items())
                        if role != "object_pack"
                    },
                }
            )
        )
        identity_digest = sha256_bytes(
            canonical_json_bytes(
                {
                    "control": control_digest,
                    "target_kind": manifest.target_kind,
                    "source_commit": manifest.source_commit,
                    "tree": manifest.candidate_tree,
                    "final_commit": manifest.final_commit,
                    "expected_parent": manifest.expected_parent,
                    "authorization_sha256": manifest.authorization_sha256,
                }
            )
        )
        receipt_bytes = build_pass_receipt(
            manifest,
            counters,
            ReceiptDigests(
                command=sha256_bytes(
                    canonical_json_bytes(
                        {
                            "trusted_wrapper": wrapper_binding,
                            "trusted_probes": trusted_probe_manifest(),
                            "candidate_command": list(manifest.raw["command"]),
                        }
                    )
                ),
                content=sha256_bytes(
                    canonical_json_bytes(
                        {
                            "object_closure": verified_pack.closure_sha256,
                            "control": control_digest,
                            "semantic_counters": counters,
                            "execution_evidence": execution_evidence.digest,
                            "invocation_usage": invocation_usage,
                        }
                    )
                ),
                profile=profile_source_sha256,
                imports=execution_evidence.import_manifest_sha256,
                identity=identity_digest,
                tree=sha256_bytes(canonical_json_bytes(manifest.raw["inventory"])),
                runtime=sha256_bytes(
                    canonical_json_bytes(
                        {
                            "materialized": runtime_digest,
                            "execution_evidence": execution_evidence.digest,
                        }
                    )
                ),
            ),
            prior_receipt_sha256=accepted_prior_sha256,
        )
    except FullGateError as exc:
        primary = exc
    except (OSError, RuntimeError, ValueError, TypeError, MemoryError):
        primary = FullGateError("FULL_GATE_INTERNAL_BLOCKER")

    if protocol is not None:
        try:
            _cleanup_owned_fixed_logs(protocol)
        except FullGateError as exc:
            primary = exc
        try:
            protocol.close()
        except FullGateError as exc:
            primary = exc
        protocol = None
    if platform_authority is not None:
        try:
            platform_authority.close()
        except FullGateError as exc:
            primary = exc
        platform_authority = None
    if invocation_root is not None:
        try:
            _remove_invocation_tree(invocation_root, "INVOCATION_CLEANUP_FAILED")
        except FullGateError as exc:
            primary = exc
    for held in reversed(held_inputs):
        try:
            held.close()
        except FullGateError as exc:
            primary = exc

    if outputs is not None:
        try:
            status = primary.status if primary is not None else None
            final_receipt = (
                receipt_bytes
                if status is None and receipt_bytes is not None
                else _failure_receipt(
                    status or "FULL_GATE_INTERNAL_BLOCKER", arguments.nonce
                )
            )
            finalize_outputs(
                outputs,
                denial_bytes=denial_bytes,
                receipt_bytes=final_receipt,
                nonce=arguments.nonce,
            )
        except FullGateError as exc:
            primary = exc
        outputs = None

    if primary is not None:
        raise primary
    if receipt_bytes is None:
        _raise("FULL_GATE_INTERNAL_BLOCKER")
    return 0


def _validate_inventory(
    value: object,
    status: str,
    *,
    exact_paths: tuple[str, ...] | None = None,
    require_nonempty: bool = True,
) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list) or (require_nonempty and not value):
        _raise(status)
    entries: list[dict[str, str]] = []
    collision_keys: set[str] = set()
    for raw in value:
        entry = _exact_object(
            raw, frozenset({"path", "mode", "blob", "sha256"}), status
        )
        path = _safe_repo_path(entry["path"], status)
        mode = entry["mode"]
        if mode not in {"100644", "100755"}:
            _raise(status)
        collision = unicodedata.normalize("NFC", path).casefold()
        if collision in collision_keys:
            _raise(status)
        collision_keys.add(collision)
        entries.append(
            {
                "path": path,
                "mode": mode,
                "blob": _hex40(entry["blob"], status),
                "sha256": _hex64(entry["sha256"], status),
            }
        )
    if exact_paths is not None and tuple(entry["path"] for entry in entries) != exact_paths:
        _raise(status)
    return tuple(entries)


def _validate_semantic_counters(value: object, status: str) -> dict[str, int]:
    counters = _exact_object(value, frozenset(SEMANTIC_COUNTER_FIELDS), status)
    result: dict[str, int] = {}
    for field in SEMANTIC_COUNTER_FIELDS:
        item = counters[field]
        if type(item) is not int or item < 0 or item > 10_000_000:
            _raise(status)
        result[field] = item
    return result


def _validate_runtime_identity_manifest(value: object) -> dict[str, object]:
    status = "RUNTIME_MANIFEST_INVALID"
    identity = _exact_object(
        value,
        frozenset(
            {
                "schema",
                "major_minor",
                "version",
                "architecture",
                "slices",
                "executable_sha256",
                "file_description",
                "load_commands",
                "rpaths",
                "load_closure",
                "runtime_probe",
            }
        ),
        status,
    )
    version = identity["version"]
    slices = identity["slices"]
    if (
        identity["schema"] != "samvil.full-gate-python-identity.v1"
        or identity["major_minor"] != "3.12"
        or not isinstance(version, str)
        or re.fullmatch(r"3\.12\.[0-9]+", version) is None
        or identity["architecture"] != "arm64"
        or not isinstance(slices, list)
        or "arm64" not in slices
        or any(item not in {"arm64", "x86_64"} for item in slices)
        or not isinstance(identity["file_description"], str)
        or "Mach-O" not in identity["file_description"]
        or not isinstance(identity["load_commands"], list)
        or not identity["load_commands"]
        or any(not isinstance(item, str) or not item for item in identity["load_commands"])
        or not isinstance(identity["rpaths"], list)
        or any(not isinstance(item, str) for item in identity["rpaths"])
        or not isinstance(identity["load_closure"], list)
        or not isinstance(identity["runtime_probe"], dict)
    ):
        _raise(status)
    _hex64(identity["executable_sha256"], status)
    return identity


def _validate_target(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not isinstance(value.get("kind"), str):
        _raise("TARGET_IDENTITY_INVALID")
    kind = value["kind"]
    if kind == "original":
        target = _exact_object(
            value,
            frozenset({"kind", "source_commit", "tree"}),
            "TARGET_IDENTITY_INVALID",
        )
        return {
            "kind": kind,
            "source_commit": _hex40(
                target["source_commit"], "TARGET_IDENTITY_INVALID"
            ),
            "tree": _hex40(target["tree"], "TARGET_IDENTITY_INVALID"),
        }
    if kind == "candidate_precommit":
        target = _exact_object(
            value,
            frozenset(
                {
                    "kind",
                    "tree",
                    "expected_parent",
                    "authorization_sha256",
                    "final_commit",
                }
            ),
            "TARGET_IDENTITY_INVALID",
        )
        if target["final_commit"] is not None:
            _raise("TARGET_IDENTITY_INVALID")
        return {
            "kind": kind,
            "tree": _hex40(target["tree"], "TARGET_IDENTITY_INVALID"),
            "expected_parent": _hex40(
                target["expected_parent"], "TARGET_IDENTITY_INVALID"
            ),
            "authorization_sha256": _hex64(
                target["authorization_sha256"], "TARGET_IDENTITY_INVALID"
            ),
            "final_commit": None,
        }
    if kind == "candidate_postcommit":
        fields = frozenset(
            {
                "kind",
                "final_commit",
                "tree",
                "expected_parent",
                "precommit_tree",
                "authorization_sha256",
                "expected_precommit_nonce",
                "expected_precommit_control_commit",
                "expected_precommit_control_tree",
                "expected_precommit_manifest_sha256",
                "prior_receipt_sha256",
            }
        )
        target = _exact_object(value, fields, "TARGET_IDENTITY_INVALID")
        tree = _hex40(target["tree"], "TARGET_IDENTITY_INVALID")
        precommit_tree = _hex40(
            target["precommit_tree"], "TARGET_IDENTITY_INVALID"
        )
        if tree != precommit_tree:
            _raise("TARGET_IDENTITY_INVALID")
        return {
            "kind": kind,
            "final_commit": _hex40(
                target["final_commit"], "TARGET_IDENTITY_INVALID"
            ),
            "tree": tree,
            "expected_parent": _hex40(
                target["expected_parent"], "TARGET_IDENTITY_INVALID"
            ),
            "precommit_tree": precommit_tree,
            "authorization_sha256": _hex64(
                target["authorization_sha256"], "TARGET_IDENTITY_INVALID"
            ),
            "expected_precommit_nonce": _hex64(
                target["expected_precommit_nonce"], "TARGET_IDENTITY_INVALID"
            ),
            "expected_precommit_control_commit": _hex40(
                target["expected_precommit_control_commit"],
                "TARGET_IDENTITY_INVALID",
            ),
            "expected_precommit_control_tree": _hex40(
                target["expected_precommit_control_tree"],
                "TARGET_IDENTITY_INVALID",
            ),
            "expected_precommit_manifest_sha256": _hex64(
                target["expected_precommit_manifest_sha256"],
                "TARGET_IDENTITY_INVALID",
            ),
            "prior_receipt_sha256": _hex64(
                target["prior_receipt_sha256"], "TARGET_IDENTITY_INVALID"
            ),
        }
    _raise("TARGET_KIND_INVALID")


def _validate_host_tool_identity_parser_manifest(value: object) -> None:
    status = "HOST_TOOL_IDENTITY_PARSER_INVALID"
    parser = _exact_object(
        value,
        frozenset(
            {
                "schema",
                "authority",
                "staged_runner_authority",
                "source_sha256",
                "source_artifact",
                "materialized",
                "supported_schemas",
                "limits",
                "inputs",
                "result_sha256",
                "staged_runner_comparison",
            }
        ),
        status,
    )
    if (
        parser["schema"] != "host-tool-identity-parser.v1"
        or parser["authority"] != "task-2-external-controller"
        or parser["staged_runner_authority"] is not False
    ):
        _raise(status)
    source_sha256 = _hex64(parser["source_sha256"], status)
    result_sha256 = _hex64(parser["result_sha256"], status)
    source_artifact = _validate_artifact_reference(
        parser["source_artifact"], status
    )
    if source_artifact["sha256"] != source_sha256:
        _raise(status)

    materialized = _exact_object(
        parser["materialized"],
        frozenset({"content_sha256", "mode", "interpreter"}),
        status,
    )
    interpreter = _exact_object(
        materialized["interpreter"],
        frozenset({"classification", "relative_path", "sha256"}),
        status,
    )
    relative_path = interpreter["relative_path"]
    if (
        _hex64(materialized["content_sha256"], status) != source_sha256
        or materialized["mode"] != "100500"
        or interpreter["classification"] != "copied_application_runtime"
        or not isinstance(relative_path, str)
        or not relative_path
        or relative_path.startswith("/")
        or "\\" in relative_path
        or "\x00" in relative_path
        or any(part in {"", ".", ".."} for part in relative_path.split("/"))
    ):
        _raise(status)
    _hex64(interpreter["sha256"], status)

    if parser["supported_schemas"] != ["code-directory.v1", "mach-o.v1"]:
        _raise(status)

    limits = _exact_object(
        parser["limits"],
        frozenset({"file_bytes", "aggregate_bytes", "depth", "load_commands"}),
        status,
    )
    maxima = {
        "file_bytes": 64 * 1024 * 1024,
        "aggregate_bytes": 256 * 1024 * 1024,
        "depth": 64,
        "load_commands": 16_384,
    }
    if any(
        type(limits[key]) is not int
        or limits[key] <= 0
        or limits[key] > maximum
        for key, maximum in maxima.items()
    ) or limits["aggregate_bytes"] < limits["file_bytes"]:
        _raise(status)

    inputs = parser["inputs"]
    if not isinstance(inputs, list) or not inputs:
        _raise(status)
    roles: list[str] = []
    identities: set[tuple[int, int]] = set()
    for raw_input in inputs:
        entry = _exact_object(
            raw_input,
            frozenset({"role", "path", "device", "inode", "size", "sha256"}),
            status,
        )
        role = entry["role"]
        path = entry["path"]
        device = _identity_uint(entry["device"], status)
        inode = _identity_uint(entry["inode"], status)
        size = entry["size"]
        if (
            not isinstance(role, str)
            or not role
            or not isinstance(path, str)
            or not Path(path).is_absolute()
            or "\x00" in path
            or "\\" in path
            or str(Path(path)) != path
            or any(part in {"", ".", ".."} for part in path.split("/")[1:])
            or type(size) is not int
            or size <= 0
            or size > limits["file_bytes"]
            or (device, inode) in identities
        ):
            _raise(status)
        _hex64(entry["sha256"], status)
        roles.append(role)
        identities.add((device, inode))
    if roles != sorted(roles) or len(set(roles)) != len(roles):
        _raise(status)

    comparison = _exact_object(
        parser["staged_runner_comparison"],
        frozenset({"source_sha256", "result_sha256", "byte_identical", "authority"}),
        status,
    )
    _hex64(comparison["source_sha256"], status)
    if (
        _hex64(comparison["result_sha256"], status) != result_sha256
        or comparison["byte_identical"] is not True
        or comparison["authority"] is not False
    ):
        _raise(status)


def build_staged_host_tool_identity_corpus_result(
    parser_manifest: object,
    corpus_artifacts: Mapping[str, HeldArtifact],
) -> bytes:
    status = "HOST_TOOL_IDENTITY_PARSER_INVALID"
    _validate_host_tool_identity_parser_manifest(parser_manifest)
    if not isinstance(parser_manifest, Mapping) or not isinstance(
        corpus_artifacts, Mapping
    ):
        _raise(status)
    expected_inputs = parser_manifest["inputs"]
    if not isinstance(expected_inputs, list):
        _raise(status)
    expected_roles = [entry["role"] for entry in expected_inputs]
    if list(corpus_artifacts) != expected_roles:
        _raise(status)
    items: list[dict[str, object]] = []
    for entry in expected_inputs:
        role = entry["role"]
        held = corpus_artifacts.get(role)
        if not isinstance(held, HeldArtifact):
            _raise(status)
        held.assert_stable()
        digest = sha256_bytes(held.data)
        if (
            held.identity.device != _identity_uint(entry["device"], status)
            or held.identity.inode != _identity_uint(entry["inode"], status)
            or held.identity.size != entry["size"]
            or digest != entry["sha256"]
        ):
            _raise(status)
        items.append(
            {
                "role": role,
                "sha256": digest,
                "size": len(held.data),
            }
        )
    return canonical_json_bytes(
        {
            "schema": "host-tool-identity-corpus-result.v1",
            "items": items,
        }
    )


def verify_external_host_tool_identity_parser(
    parser_manifest: object,
    parser_artifact: HeldArtifact,
    corpus_artifacts: Mapping[str, HeldArtifact],
    *,
    runtime_root: Path,
    scratch_root: Path,
    staged_result: bytes,
) -> dict[str, object]:
    status = "HOST_TOOL_IDENTITY_PARSER_INVALID"
    execution_status = "HOST_TOOL_IDENTITY_PARSER_EXECUTION_FAILED"
    comparison_status = "HOST_TOOL_IDENTITY_PARSER_COMPARISON_FAILED"
    _validate_host_tool_identity_parser_manifest(parser_manifest)
    if (
        not isinstance(parser_manifest, Mapping)
        or not isinstance(parser_artifact, HeldArtifact)
        or not isinstance(corpus_artifacts, Mapping)
        or not isinstance(staged_result, bytes)
    ):
        _raise(status)
    try:
        runtime = runtime_root.resolve(strict=True)
        scratch = scratch_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if runtime != runtime_root or scratch != scratch_root or not scratch.is_dir():
        _raise(status)

    materialized = parser_manifest["materialized"]
    interpreter_manifest = materialized["interpreter"]
    interpreter_relative = interpreter_manifest["relative_path"]
    try:
        interpreter = (runtime / interpreter_relative).resolve(strict=True)
        interpreter.relative_to(runtime)
        interpreter_bytes = interpreter.read_bytes()
    except (OSError, RuntimeError, ValueError):
        _raise(status)
    if (
        interpreter != runtime / interpreter_relative
        or sha256_bytes(interpreter_bytes) != interpreter_manifest["sha256"]
    ):
        _raise(status)

    parser_artifact.assert_stable()
    if (
        sha256_bytes(parser_artifact.data) != parser_manifest["source_sha256"]
        or parser_manifest["materialized"]["content_sha256"]
        != parser_manifest["source_sha256"]
    ):
        _raise(status)

    expected_inputs = parser_manifest["inputs"]
    if not isinstance(expected_inputs, list):
        _raise(status)
    expected_roles = [entry["role"] for entry in expected_inputs]
    if list(corpus_artifacts) != expected_roles:
        _raise(status)
    held_inputs: list[tuple[str, HeldArtifact]] = []
    for entry in expected_inputs:
        role = entry["role"]
        held = corpus_artifacts.get(role)
        if not isinstance(held, HeldArtifact):
            _raise(status)
        held.assert_stable()
        if (
            held.identity.device != _identity_uint(entry["device"], status)
            or held.identity.inode != _identity_uint(entry["inode"], status)
            or held.identity.size != entry["size"]
            or sha256_bytes(held.data) != entry["sha256"]
        ):
            _raise(status)
        held_inputs.append((role, held))

    external_root = _safe_directory(scratch, Path("external-parser"), status)
    corpus_root = _safe_directory(external_root, Path("corpus"), status)

    def write_exact(path: Path, content: bytes, mode: int) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(path, flags, 0o600)
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    _raise(status)
                view = view[written:]
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
            descriptor_state = os.fstat(descriptor)
            path_state = os.lstat(path)
            if (
                FileIdentity.from_stat(descriptor_state)
                != FileIdentity.from_stat(path_state)
                or not stat.S_ISREG(descriptor_state.st_mode)
                or descriptor_state.st_nlink != 1
                or descriptor_state.st_size != len(content)
                or stat.S_IMODE(descriptor_state.st_mode) != mode
            ):
                _raise(status)
        except FullGateError:
            raise
        except OSError:
            _raise(status)
        finally:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    _raise(status)

    parser_path = external_root / "host-tool-identity-parser.py"
    write_exact(parser_path, parser_artifact.data, 0o500)
    request_inputs: list[dict[str, object]] = []
    for index, (role, held) in enumerate(held_inputs):
        materialized_input = corpus_root / f"{index:04d}.bin"
        write_exact(materialized_input, held.data, 0o400)
        request_inputs.append(
            {
                "role": role,
                "path": str(materialized_input),
                "sha256": sha256_bytes(held.data),
                "size": len(held.data),
            }
        )
    request = canonical_json_bytes(
        {
            "schema": "host-tool-identity-parser-request.v1",
            "supported_schemas": parser_manifest["supported_schemas"],
            "limits": parser_manifest["limits"],
            "inputs": request_inputs,
        }
    )
    request_path = external_root / "request.json"
    write_exact(request_path, request, 0o400)

    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(external_root / "home-unavailable"),
        "CODEX_HOME": str(external_root / "codex-home-unavailable"),
        "TMPDIR": str(external_root),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    argv = [str(interpreter), "-I", str(parser_path), str(request_path)]
    try:
        process = subprocess.Popen(
            argv,
            cwd=external_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
        )
        try:
            stdout, stderr = process.communicate(
                timeout=HOST_TOOL_IDENTITY_PARSER_TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                _raise(execution_status)
            try:
                process.communicate(timeout=2)
            except subprocess.SubprocessError:
                _raise(execution_status)
            _raise(execution_status)
        completed = subprocess.CompletedProcess(
            argv,
            process.returncode,
            stdout,
            stderr,
        )
    except FullGateError:
        raise
    except (OSError, subprocess.SubprocessError):
        _raise(execution_status)
    if (
        completed.returncode != 0
        or completed.stderr != b""
        or len(completed.stdout) > 4 * 1024 * 1024
    ):
        _raise(execution_status)

    try:
        decoded = decode_canonical_json_bytes(
            completed.stdout,
            status=comparison_status,
            max_bytes=4 * 1024 * 1024,
        )
        if canonical_json_bytes(decoded) != completed.stdout:
            _raise(comparison_status)
    except FullGateError:
        raise
    except (TypeError, ValueError):
        _raise(comparison_status)
    result_sha256 = sha256_bytes(completed.stdout)
    if (
        completed.stdout != staged_result
        or result_sha256 != parser_manifest["result_sha256"]
        or result_sha256
        != parser_manifest["staged_runner_comparison"]["result_sha256"]
    ):
        _raise(comparison_status)

    parser_artifact.assert_stable()
    for _role, held in held_inputs:
        held.assert_stable()
    payload = {
        "schema": "samvil.host-tool-identity-parser-evidence.v1",
        "source_sha256": sha256_bytes(parser_artifact.data),
        "interpreter_sha256": sha256_bytes(interpreter_bytes),
        "input_count": len(held_inputs),
        "result_sha256": result_sha256,
        "byte_identical": True,
        "staged_runner_authority": False,
    }
    return {
        **payload,
        "evidence_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def prepare_approved_host_tool_parser(
    parser_manifest: object,
    artifacts: Mapping[str, HeldArtifact],
    *,
    runtime_root: Path,
    scratch_root: Path,
) -> dict[str, object]:
    status = "HOST_TOOL_IDENTITY_PARSER_INVALID"
    _validate_host_tool_identity_parser_manifest(parser_manifest)
    if not isinstance(parser_manifest, Mapping) or not isinstance(
        artifacts, Mapping
    ):
        _raise(status)
    parser_artifact = artifacts.get("host_tool_identity_parser_source")
    if not isinstance(parser_artifact, HeldArtifact):
        _raise(status)
    inputs = parser_manifest["inputs"]
    if not isinstance(inputs, list):
        _raise(status)
    corpus: dict[str, HeldArtifact] = {}
    for entry in inputs:
        role = entry["role"]
        held = artifacts.get(f"host_tool_identity_parser_input:{role}")
        if not isinstance(held, HeldArtifact):
            _raise(status)
        corpus[role] = held
    staged_result = build_staged_host_tool_identity_corpus_result(
        parser_manifest, corpus
    )
    return verify_external_host_tool_identity_parser(
        parser_manifest,
        parser_artifact,
        corpus,
        runtime_root=runtime_root,
        scratch_root=scratch_root,
        staged_result=staged_result,
    )


def _validated_string_list(value: object, status: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        _raise(status)
    return value


def _validated_unique_string_list(value: object, status: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        _raise(status)
    return value


def _validate_copied_application_runtime_manifest(value: object) -> None:
    status = "COPIED_APPLICATION_RUNTIME_INVALID"
    runtime = _exact_object(
        value,
        frozenset({"schema", "portable_tools", "exec_allowlist", "path_order"}),
        status,
    )
    if (
        runtime["schema"] != "samvil.copied-application-runtime.v1"
        or not isinstance(runtime["portable_tools"], list)
    ):
        _raise(status)
    expected_paths = {
        "git": (
            "/Library/Developer/CommandLineTools/usr/bin/git",
            "tools/usr/bin/git",
        ),
        "git-shell": (
            "/Library/Developer/CommandLineTools/usr/bin/git-shell",
            "tools/usr/bin/git-shell",
        ),
        "lipo": (
            "/Library/Developer/CommandLineTools/usr/bin/lipo",
            "tools/usr/bin/lipo",
        ),
        "otool": (
            "/Library/Developer/CommandLineTools/usr/bin/otool",
            "tools/usr/bin/otool",
        ),
        "scalar": (
            "/Library/Developer/CommandLineTools/usr/bin/scalar",
            "tools/usr/bin/scalar",
        ),
    }
    rows = runtime["portable_tools"]
    if len(rows) != len(expected_paths):
        _raise(status)
    observed_roles: list[str] = []
    observed_execs: set[str] = set()
    for raw_row in runtime["portable_tools"]:
        row = _exact_object(
            raw_row,
            frozenset(
                {
                    "role",
                    "source_path",
                    "destination_path",
                    "platform_identifier",
                    "filesystem_flags",
                    "mode",
                    "nlink",
                    "size",
                    "sha256",
                    "slices",
                    "load_closure",
                    "exec_closure",
                    "behavior_probe",
                    "admission_state",
                }
            ),
            status,
        )
        role = row["role"]
        source_path = row["source_path"]
        destination_path = row["destination_path"]
        platform_identifier = row["platform_identifier"]
        flags = _validated_string_list(row["filesystem_flags"], status)
        if (
            type(platform_identifier) is not int
            or platform_identifier < 0
            or platform_identifier > 0xFFFFFFFF
        ):
            _raise(status)
        normalized_flags = {flag.casefold() for flag in flags}
        if (
            platform_identifier != 0
            or "restricted" in normalized_flags
            or "cs_platform_path" in normalized_flags
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        if (
            not isinstance(role, str)
            or role not in expected_paths
            or not isinstance(source_path, str)
            or not isinstance(destination_path, str)
            or (source_path, destination_path) != expected_paths[role]
            or row["mode"] != "100755"
            or type(row["nlink"]) is not int
            or row["nlink"] < 1
            or type(row["size"]) is not int
            or row["size"] <= 0
            or row["size"] > 64 * 1024 * 1024
            or row["admission_state"] != "STATIC_ADMITTED"
        ):
            _raise(status)
        _safe_repo_path(destination_path, status)
        _hex64(row["sha256"], status)
        slices = _validated_unique_string_list(row["slices"], status)
        if (
            not slices
            or any(item not in {"arm64", "arm64e", "x86_64"} for item in slices)
        ):
            _raise(status)
        loads = _validated_string_list(row["load_closure"], status)
        if not loads or any(
            not (
                load.startswith("/usr/lib/")
                or load.startswith("/System/Library/")
            )
            for load in loads
        ):
            _raise(status)

        exec_closure = _exact_object(
            row["exec_closure"],
            frozenset(
                {
                    "executables",
                    "git_core_root",
                    "topology_sha256",
                    "internal_symlink_count",
                }
            ),
            status,
        )
        executables = _validated_string_list(exec_closure["executables"], status)
        if not executables:
            _raise(status)
        for executable in executables:
            _safe_repo_path(executable, status)
            if any(token in executable for token in ("*", "?", "[", "]")):
                _raise(status)
        if role == "git":
            git_core_root = exec_closure["git_core_root"]
            if (
                git_core_root != "tools/usr/libexec/git-core"
                or destination_path not in executables
                or not any(
                    executable.startswith(f"{git_core_root}/")
                    for executable in executables
                )
                or type(exec_closure["internal_symlink_count"]) is not int
                or exec_closure["internal_symlink_count"] <= 0
            ):
                _raise(status)
            _hex64(exec_closure["topology_sha256"], status)
        elif (
            executables != [destination_path]
            or exec_closure["git_core_root"] is not None
            or exec_closure["topology_sha256"] is not None
            or exec_closure["internal_symlink_count"] != 0
        ):
            _raise(status)
        observed_execs.update(executables)

        probe = _exact_object(
            row["behavior_probe"], frozenset({"argv", "stdout_sha256"}), status
        )
        argv = probe["argv"]
        if (
            not isinstance(argv, list)
            or not argv
            or argv[0] != destination_path
            or any(not isinstance(item, str) or not item for item in argv)
        ):
            _raise(status)
        _hex64(probe["stdout_sha256"], status)
        observed_roles.append(role)

    if observed_roles != sorted(expected_paths) or len(set(observed_roles)) != len(
        observed_roles
    ):
        _raise(status)

    expected_path_order = [
        "tools/facade/bin",
        "tools/usr/bin",
        "node/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    if runtime["path_order"] != expected_path_order:
        _raise(status)

    required_execs = {
        "tools/facade/bin/mktemp",
        "tools/facade/bin/python",
        "tools/facade/bin/python3",
        "tools/facade/bin/python3.12",
        "node/bin/node",
        "node/bin/npm",
        "node/bin/pnpm",
    }
    allowlist = _validated_string_list(runtime["exec_allowlist"], status)
    if set(allowlist) != observed_execs | required_execs:
        _raise(status)
    for executable in allowlist:
        _safe_repo_path(executable, status)
        if any(token in executable for token in ("*", "?", "[", "]")):
            _raise(status)


def _validate_canonical_host_tools_manifest(value: object) -> None:
    status = "CANONICAL_HOST_TOOLS_INVALID"
    closure = _exact_object(
        value,
        frozenset({"schema", "rows"}),
        status,
    )
    if (
        closure["schema"] != "samvil.canonical-host-tools.v1"
        or not isinstance(closure["rows"], list)
    ):
        _raise(status)
    row_fields = frozenset(
        {
            "role",
            "path",
            "uid",
            "mode",
            "nlink",
            "size",
            "filesystem_flags",
            "read_only_filesystem",
            "device",
            "inode",
            "sha256",
            "slices",
            "load_closure",
            "apple_anchor",
            "signing_identifier",
            "platform_identifier",
            "designated_requirement",
            "cdhash",
            "behavior_probe",
            "admission_state",
        }
    )
    seen_roles: set[str] = set()
    seen_paths: set[str] = set()
    for raw_row in closure["rows"]:
        row = _exact_object(raw_row, row_fields, status)
        role = row["role"]
        path = row["path"]
        flags = _validated_string_list(row["filesystem_flags"], status)
        slices = _validated_unique_string_list(row["slices"], status)
        if (
            not isinstance(role, str)
            or not role
            or not isinstance(path, str)
            or not path.startswith("/")
            or "\x00" in path
            or row["uid"] != 0
            or not isinstance(row["mode"], str)
            or re.fullmatch(r"100[0-7]{3}", row["mode"]) is None
            or type(row["nlink"]) is not int
            or row["nlink"] < 1
            or type(row["size"]) is not int
            or row["size"] < 1
            or row["read_only_filesystem"] is not True
            or _identity_uint(row["device"], status) < 0
            or _identity_uint(row["inode"], status) < 0
            or not flags
            or "restricted" not in {flag.casefold() for flag in flags}
            or not slices
            or not isinstance(row["load_closure"], list)
            or row["apple_anchor"] is not True
            or not isinstance(row["signing_identifier"], str)
            or not row["signing_identifier"]
            or type(row["platform_identifier"]) is not int
            or row["platform_identifier"] == 0
            or not isinstance(row["designated_requirement"], str)
            or not row["designated_requirement"]
            or not isinstance(row["behavior_probe"], dict)
            or row["admission_state"]
            not in {"PLATFORM_VERIFIER_PINNED", "STATIC_ADMITTED", "ACCEPTED_ROW"}
        ):
            _raise(status)
        _hex64(row["sha256"], status)
        _hex40(row["cdhash"], status)
        if role != "codesign":
            probe = _exact_object(
                row["behavior_probe"],
                frozenset(
                    {
                        "schema",
                        "argv",
                        "returncode",
                        "stdout_sha256",
                        "stderr_sha256",
                        "result_sha256",
                    }
                ),
                "UNSUPPORTED_CANONICAL_TOOLCHAIN",
            )
            argv = probe["argv"]
            if (
                probe["schema"] != "samvil.host-tool-behavior.v1"
                or not isinstance(argv, list)
                or not argv
                or argv[0] != path
                or any(
                    not isinstance(argument, str)
                    or not argument
                    or "\x00" in argument
                    for argument in argv
                )
                or type(probe["returncode"]) is not int
                or probe["returncode"] < 0
                or probe["returncode"] > 255
            ):
                _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
            stdout_sha256 = _hex64(
                probe["stdout_sha256"], "UNSUPPORTED_CANONICAL_TOOLCHAIN"
            )
            stderr_sha256 = _hex64(
                probe["stderr_sha256"], "UNSUPPORTED_CANONICAL_TOOLCHAIN"
            )
            result_payload = {
                "schema": "samvil.host-tool-behavior-result.v1",
                "target_path": path,
                "argv": argv,
                "returncode": probe["returncode"],
                "stdout_sha256": stdout_sha256,
                "stderr_sha256": stderr_sha256,
                "status": "GREEN",
            }
            if _hex64(
                probe["result_sha256"], "UNSUPPORTED_CANONICAL_TOOLCHAIN"
            ) != sha256_bytes(canonical_json_bytes(result_payload)):
                _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
        seen_roles.add(role)
        seen_paths.add(path)
    rows = closure["rows"]
    roles = [row["role"] for row in rows]
    paths = [row["path"] for row in rows]
    if (
        len(rows) < 2
        or len(set(roles)) != len(roles)
        or len(set(paths)) != len(paths)
        or rows[0]["role"] != "codesign"
        or rows[0]["path"] != "/usr/bin/codesign"
        or rows[0]["admission_state"] != "PLATFORM_VERIFIER_PINNED"
        or not any(
            row["role"] == "sandbox-exec"
            and row["path"] == "/usr/bin/sandbox-exec"
            for row in rows[1:]
        )
        or any(
            row["role"] == "codesign"
            or row["path"] == "/usr/bin/codesign"
            or row["admission_state"] != "STATIC_ADMITTED"
            for row in rows[1:]
        )
    ):
        _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
    verifier_behavior = _exact_object(
        rows[0]["behavior_probe"],
        frozenset({"schema", "first_non_self_role", "result_sha256"}),
        "UNSUPPORTED_CANONICAL_TOOLCHAIN",
    )
    if (
        verifier_behavior["schema"]
        != "samvil.codesign-verifier-behavior.v1"
        or verifier_behavior["first_non_self_role"] != rows[1]["role"]
    ):
        _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
    _hex64(
        verifier_behavior["result_sha256"],
        "UNSUPPORTED_CANONICAL_TOOLCHAIN",
    )


@dataclass
class HeldCanonicalHostTool:
    path: Path
    descriptor: int
    identity: FileIdentity
    binding: Mapping[str, object]
    closed: bool = False

    def assert_stable(self) -> None:
        status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
        if self.closed:
            _raise(status)
        try:
            descriptor_state = os.fstat(self.descriptor)
            path_state = os.lstat(self.path)
            resolved = self.path.resolve(strict=True)
            filesystem_state = os.statvfs(self.path)
        except (OSError, RuntimeError):
            _raise(status)
        raw_flags = getattr(descriptor_state, "st_flags", 0)
        observed_flags = sorted(
            name
            for name, bit in (
                ("immutable", getattr(stat, "SF_IMMUTABLE", 0)),
                ("restricted", 0x00080000),
                ("user_immutable", getattr(stat, "UF_IMMUTABLE", 0)),
            )
            if bit and raw_flags & bit
        )
        observed_read_only = bool(
            filesystem_state.f_flag & getattr(os, "ST_RDONLY", 1)
        )
        if (
            resolved != self.path
            or FileIdentity.from_stat(descriptor_state) != self.identity
            or FileIdentity.from_stat(path_state) != self.identity
            or not stat.S_ISREG(descriptor_state.st_mode)
            or self.binding.get("path") != str(self.path)
            or self.binding.get("uid") != descriptor_state.st_uid
            or self.binding.get("mode") != f"{descriptor_state.st_mode:o}"
            or self.binding.get("nlink") != descriptor_state.st_nlink
            or self.binding.get("size") != descriptor_state.st_size
            or _identity_uint(self.binding.get("device"), status)
            != descriptor_state.st_dev
            or _identity_uint(self.binding.get("inode"), status)
            != descriptor_state.st_ino
            or self.binding.get("filesystem_flags") != observed_flags
            or self.binding.get("read_only_filesystem") is not observed_read_only
        ):
            _raise(status)

    def close(self) -> None:
        if self.closed:
            return
        try:
            os.close(self.descriptor)
        except OSError:
            self.closed = True
            _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
        self.closed = True


def open_canonical_host_tool(row: Mapping[str, object]) -> HeldCanonicalHostTool:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if not isinstance(row, Mapping):
        _raise(status)
    raw_path = row.get("path")
    expected_size = row.get("size")
    expected_sha256 = row.get("sha256")
    if (
        not isinstance(raw_path, str)
        or not Path(raw_path).is_absolute()
        or "\x00" in raw_path
        or "\\" in raw_path
        or str(Path(raw_path)) != raw_path
        or type(expected_size) is not int
        or expected_size < 1
        or expected_size > 64 * 1024 * 1024
        or not isinstance(expected_sha256, str)
        or HEX64.fullmatch(expected_sha256) is None
    ):
        _raise(status)
    path = Path(raw_path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    held: HeldCanonicalHostTool | None = None
    try:
        if path.resolve(strict=True) != path:
            _raise(status)
        descriptor = os.open(path, flags)
        descriptor_state = os.fstat(descriptor)
        path_state = os.lstat(path)
        identity = FileIdentity.from_stat(descriptor_state)
        if (
            not stat.S_ISREG(descriptor_state.st_mode)
            or identity != FileIdentity.from_stat(path_state)
            or descriptor_state.st_size != expected_size
        ):
            _raise(status)
        chunks: list[bytes] = []
        remaining = expected_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                _raise(status)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _raise(status)
        if sha256_bytes(b"".join(chunks)) != expected_sha256:
            _raise(status)
        held = HeldCanonicalHostTool(
            path=path,
            descriptor=descriptor,
            identity=identity,
            binding=dict(row),
        )
        held.assert_stable()
        return held
    except FullGateError:
        raise
    except (OSError, RuntimeError):
        _raise(status)
    finally:
        if held is None and descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def run_canonical_host_behavior(
    row: Mapping[str, object],
    held: HeldCanonicalHostTool,
    *,
    scratch_root: Path,
) -> dict[str, object]:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if not isinstance(row, Mapping) or not isinstance(
        held, HeldCanonicalHostTool
    ):
        _raise(status)
    try:
        scratch = scratch_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if scratch != scratch_root or not scratch.is_dir():
        _raise(status)
    probe = _exact_object(
        row.get("behavior_probe"),
        frozenset(
            {
                "schema",
                "argv",
                "returncode",
                "stdout_sha256",
                "stderr_sha256",
                "result_sha256",
            }
        ),
        status,
    )
    argv = probe["argv"]
    if (
        probe["schema"] != "samvil.host-tool-behavior.v1"
        or not isinstance(argv, list)
        or not argv
        or argv[0] != row.get("path")
        or any(not isinstance(argument, str) or not argument for argument in argv)
        or type(probe["returncode"]) is not int
    ):
        _raise(status)
    held.assert_stable()
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home-unavailable"),
        "CODEX_HOME": str(scratch / "codex-home-unavailable"),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        completed = subprocess.run(
            argv,
            cwd=scratch,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _raise(status)
    held.assert_stable()
    if (
        len(completed.stdout) > 64 * 1024
        or len(completed.stderr) > 64 * 1024
    ):
        _raise(status)
    stdout_sha256 = sha256_bytes(completed.stdout)
    stderr_sha256 = sha256_bytes(completed.stderr)
    result_payload = {
        "schema": "samvil.host-tool-behavior-result.v1",
        "target_path": row["path"],
        "argv": argv,
        "returncode": completed.returncode,
        "stdout_sha256": stdout_sha256,
        "stderr_sha256": stderr_sha256,
        "status": "GREEN",
    }
    result_sha256 = sha256_bytes(canonical_json_bytes(result_payload))
    if (
        completed.returncode != probe["returncode"]
        or stdout_sha256 != probe["stdout_sha256"]
        or stderr_sha256 != probe["stderr_sha256"]
        or result_sha256 != probe["result_sha256"]
    ):
        _raise(status)
    return {
        "schema": "samvil.host-tool-behavior-result.v1",
        "target_path": row["path"],
        "status": "GREEN",
        "result_sha256": result_sha256,
    }


def run_canonical_codesign(
    row: Mapping[str, object],
    held: object,
    verifier: object,
    *,
    scratch_root: Path,
) -> dict[str, object]:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if not isinstance(row, Mapping):
        _raise(status)
    target_path = row.get("path")
    identifier = row.get("signing_identifier")
    slices = row.get("slices")
    verifier_binding = getattr(verifier, "binding", None)
    if (
        not isinstance(target_path, str)
        or not Path(target_path).is_absolute()
        or not isinstance(identifier, str)
        or not identifier
        or not isinstance(slices, list)
        or not slices
        or not isinstance(verifier_binding, Mapping)
        or verifier_binding.get("role") != "codesign"
        or verifier_binding.get("path") != str(APPLE_CODESIGN)
        or not callable(getattr(held, "assert_stable", None))
        or not callable(getattr(verifier, "assert_stable", None))
    ):
        _raise(status)
    try:
        scratch = scratch_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if scratch != scratch_root or not scratch.is_dir():
        _raise(status)
    requirement = f'anchor apple and identifier "{identifier}"'
    verify_argv = [
        str(APPLE_CODESIGN),
        "--verify",
        "--strict",
        "--verbose=2",
        f"-R={requirement}",
        target_path,
    ]
    display_argv = [
        str(APPLE_CODESIGN),
        "-d",
        "--verbose=4",
        "-r-",
        target_path,
    ]
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home-unavailable"),
        "CODEX_HOME": str(scratch / "codex-home-unavailable"),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
    }

    def run(argv: list[str]) -> subprocess.CompletedProcess[bytes]:
        held.assert_stable()
        verifier.assert_stable()
        try:
            completed = subprocess.run(
                argv,
                cwd=scratch,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            _raise(status)
        held.assert_stable()
        verifier.assert_stable()
        if (
            not isinstance(completed.stdout, bytes)
            or not isinstance(completed.stderr, bytes)
            or len(completed.stdout) > APPLE_COMMAND_OUTPUT_MAX_BYTES
            or len(completed.stderr) > APPLE_COMMAND_OUTPUT_MAX_BYTES
        ):
            _raise(status)
        return completed

    verify = run(verify_argv)
    display = run(display_argv)
    return {
        "target_path": target_path,
        "signing_identifier": identifier,
        "expected_slices": list(slices),
        "verify_argv": verify_argv,
        "verify_returncode": verify.returncode,
        "verify_stdout": verify.stdout,
        "verify_stderr": verify.stderr,
        "display_argv": display_argv,
        "display_returncode": display.returncode,
        "display_stdout": display.stdout,
        "display_stderr": display.stderr,
    }


@dataclass
class HeldCanonicalHostAuthority:
    row_bytes: tuple[bytes, ...]
    opened: tuple[object, ...]
    evidence_payload: Mapping[str, object]
    closed: bool = False

    def _assert_stable(self) -> None:
        status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
        if self.closed or len(self.row_bytes) != len(self.opened):
            _raise(status)
        try:
            for expected, held in zip(self.row_bytes, self.opened):
                binding = getattr(held, "binding")
                if (
                    not isinstance(binding, Mapping)
                    or canonical_json_bytes(dict(binding)) != expected
                ):
                    _raise(status)
                held.assert_stable()
        except Exception:
            _raise(status)

    def complete(self) -> dict[str, object]:
        self._assert_stable()
        payload = dict(self.evidence_payload)
        return {
            **payload,
            "result_sha256": sha256_bytes(canonical_json_bytes(payload)),
        }

    def executable_path(self, role: str) -> Path:
        if not isinstance(role, str) or not role:
            _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
        self._assert_stable()
        matches: list[Path] = []
        for held in self.opened:
            binding = getattr(held, "binding", None)
            if not isinstance(binding, Mapping) or binding.get("role") != role:
                continue
            raw_path = binding.get("path")
            if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
                _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
            matches.append(Path(raw_path))
        if len(matches) != 1:
            _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")
        return matches[0]

    def close(self) -> None:
        if self.closed:
            return
        failed = False
        for held in reversed(self.opened):
            try:
                held.close()
            except Exception:
                failed = True
        self.closed = True
        if failed:
            _raise("UNSUPPORTED_CANONICAL_TOOLCHAIN")


def acquire_canonical_host_tools(
    rows: object,
    *,
    open_tool: object,
    run_codesign: object,
    run_behavior: object,
) -> HeldCanonicalHostAuthority:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if (
        not isinstance(rows, list)
        or not callable(open_tool)
        or not callable(run_codesign)
        or not callable(run_behavior)
    ):
        _raise(status)
    _validate_canonical_host_tools_manifest(
        {"schema": "samvil.canonical-host-tools.v1", "rows": rows}
    )

    opened: list[object] = []
    opened_ids: set[int] = set()
    row_bytes = tuple(canonical_json_bytes(row) for row in rows)

    def assert_held_binding(held: object, expected: bytes) -> None:
        try:
            binding = getattr(held, "binding")
            if (
                not isinstance(binding, Mapping)
                or canonical_json_bytes(dict(binding)) != expected
            ):
                _raise(status)
            held.assert_stable()
        except Exception:
            _raise(status)

    try:
        for row, expected in zip(rows, row_bytes):
            try:
                held = open_tool(row)
            except Exception:
                _raise(status)
            if (
                held is None
                or id(held) in opened_ids
                or not callable(getattr(held, "assert_stable", None))
                or not callable(getattr(held, "close", None))
                or not isinstance(getattr(held, "binding", None), Mapping)
            ):
                _raise(status)
            opened.append(held)
            opened_ids.add(id(held))
            assert_held_binding(held, expected)

        verifier_behavior = _exact_object(
            rows[0]["behavior_probe"],
            frozenset({"schema", "first_non_self_role", "result_sha256"}),
            status,
        )
        verifier_behavior_digest = _hex64(
            verifier_behavior["result_sha256"], status
        )

        admitted_rows: list[dict[str, object]] = [
            {
                "role": "codesign",
                "path": "/usr/bin/codesign",
                "admission_state": "PLATFORM_VERIFIER_PINNED",
                "self_verified": False,
                "first_non_self_target": rows[1]["path"],
                "verifier_behavior_result_sha256": verifier_behavior_digest,
                "identity_pre_post": "stable",
            }
        ]
        for index, (row, expected, held) in enumerate(
            zip(rows[1:], row_bytes[1:], opened[1:])
        ):
            try:
                raw_codesign = run_codesign(row, held)
            except Exception:
                _raise(status)
            assert_held_binding(held, expected)
            if not isinstance(raw_codesign, dict):
                _raise(status)
            try:
                parsed_codesign = parse_canonical_codesign_result(**raw_codesign)
            except Exception:
                _raise(status)
            if (
                parsed_codesign.get("target_path") != row["path"]
                or parsed_codesign.get("signing_identifier")
                != row["signing_identifier"]
                or parsed_codesign.get("slices") != row["slices"]
            ):
                _raise(status)
            if index == 0 and (
                verifier_behavior["first_non_self_role"] != row["role"]
                or parsed_codesign["result_sha256"] != verifier_behavior_digest
            ):
                _raise(status)

            expected_behavior = _exact_object(
                row["behavior_probe"],
                frozenset(
                    {
                        "schema",
                        "argv",
                        "returncode",
                        "stdout_sha256",
                        "stderr_sha256",
                        "result_sha256",
                    }
                ),
                status,
            )
            if expected_behavior["schema"] != "samvil.host-tool-behavior.v1":
                _raise(status)
            expected_behavior_digest = _hex64(
                expected_behavior["result_sha256"], status
            )
            try:
                behavior = run_behavior(row, held)
            except Exception:
                _raise(status)
            assert_held_binding(held, expected)
            behavior_result = _exact_object(
                behavior,
                frozenset({"schema", "target_path", "status", "result_sha256"}),
                status,
            )
            if (
                behavior_result["schema"]
                != "samvil.host-tool-behavior-result.v1"
                or behavior_result["target_path"] != row["path"]
                or behavior_result["status"] != "GREEN"
                or _hex64(behavior_result["result_sha256"], status)
                != expected_behavior_digest
            ):
                _raise(status)
            admitted_rows.append(
                {
                    "role": row["role"],
                    "path": row["path"],
                    "admission_state": "ACCEPTED_ROW",
                    "codesign_result_sha256": parsed_codesign["result_sha256"],
                    "behavior_result_sha256": expected_behavior_digest,
                    "identity_pre_post": "stable",
                }
            )

        payload = {
            "schema": "samvil.canonical-host-admission.v1",
            "rows": admitted_rows,
        }
        return HeldCanonicalHostAuthority(
            row_bytes=row_bytes,
            opened=tuple(opened),
            evidence_payload=payload,
        )
    except Exception:
        for held in reversed(opened):
            try:
                held.close()
            except Exception:
                pass
        _raise(status)


def admit_canonical_host_tools(
    rows: object,
    *,
    open_tool: object,
    run_codesign: object,
    run_behavior: object,
) -> dict[str, object]:
    authority = acquire_canonical_host_tools(
        rows,
        open_tool=open_tool,
        run_codesign=run_codesign,
        run_behavior=run_behavior,
    )
    try:
        return authority.complete()
    finally:
        authority.close()


def acquire_manifest_host_tool_authority(
    manifest: object,
    scratch_root: object,
    *,
    open_tool: object,
    run_codesign: object,
    run_behavior: object,
) -> HeldCanonicalHostAuthority:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if (
        not isinstance(manifest, ValidatedManifest)
        or not isinstance(scratch_root, Path)
        or not scratch_root.is_absolute()
        or "canonical_host_tools" not in manifest.raw
        or "apple_platform_tcb" in manifest.raw
    ):
        _raise(status)
    canonical = _exact_object(
        manifest.raw["canonical_host_tools"],
        frozenset({"schema", "rows"}),
        status,
    )
    if canonical["schema"] != "samvil.canonical-host-tools.v1":
        _raise(status)
    return acquire_canonical_host_tools(
        canonical["rows"],
        open_tool=open_tool,
        run_codesign=run_codesign,
        run_behavior=run_behavior,
    )


def acquire_runtime_manifest_host_tool_authority(
    manifest: ValidatedManifest,
    scratch_root: Path,
    *,
    parser_evidence: Mapping[str, object],
) -> HeldCanonicalHostAuthority:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if not isinstance(manifest, ValidatedManifest) or not isinstance(
        parser_evidence, Mapping
    ):
        _raise(status)
    parser_manifest = manifest.raw.get("host_tool_identity_parser")
    if not isinstance(parser_manifest, Mapping):
        _raise(status)
    evidence = _exact_object(
        parser_evidence,
        frozenset(
            {
                "schema",
                "source_sha256",
                "interpreter_sha256",
                "input_count",
                "result_sha256",
                "byte_identical",
                "staged_runner_authority",
                "evidence_sha256",
            }
        ),
        status,
    )
    payload = {
        key: value for key, value in evidence.items() if key != "evidence_sha256"
    }
    materialized = parser_manifest.get("materialized")
    inputs = parser_manifest.get("inputs")
    if (
        evidence["schema"]
        != "samvil.host-tool-identity-parser-evidence.v1"
        or evidence["source_sha256"] != parser_manifest.get("source_sha256")
        or not isinstance(materialized, Mapping)
        or not isinstance(materialized.get("interpreter"), Mapping)
        or evidence["interpreter_sha256"]
        != materialized["interpreter"].get("sha256")
        or not isinstance(inputs, list)
        or evidence["input_count"] != len(inputs)
        or evidence["result_sha256"] != parser_manifest.get("result_sha256")
        or evidence["byte_identical"] is not True
        or evidence["staged_runner_authority"] is not False
        or _hex64(evidence["evidence_sha256"], status)
        != sha256_bytes(canonical_json_bytes(payload))
    ):
        _raise(status)

    registry: dict[str, HeldCanonicalHostTool] = {}

    def open_tool(row: Mapping[str, object]) -> HeldCanonicalHostTool:
        role = row.get("role")
        if not isinstance(role, str) or role in registry:
            _raise(status)
        held = open_canonical_host_tool(row)
        registry[role] = held
        return held

    def run_codesign(
        row: Mapping[str, object], held: HeldCanonicalHostTool
    ) -> dict[str, object]:
        verifier = registry.get("codesign")
        if verifier is None or held is verifier:
            _raise(status)
        return run_canonical_codesign(
            row,
            held,
            verifier,
            scratch_root=scratch_root,
        )

    def run_behavior(
        row: Mapping[str, object], held: HeldCanonicalHostTool
    ) -> dict[str, object]:
        return run_canonical_host_behavior(
            row,
            held,
            scratch_root=scratch_root,
        )

    return acquire_manifest_host_tool_authority(
        manifest,
        scratch_root,
        open_tool=open_tool,
        run_codesign=run_codesign,
        run_behavior=run_behavior,
    )


def _validate_approved_host_tool_manifests(manifest: Mapping[str, object]) -> None:
    _validate_host_tool_identity_parser_manifest(manifest["host_tool_identity_parser"])
    canonical = _exact_object(
        manifest["canonical_host_tools"],
        frozenset({"schema", "rows"}),
        "CANONICAL_HOST_TOOLS_INVALID",
    )
    if (
        canonical["schema"] != "samvil.canonical-host-tools.v1"
        or not isinstance(canonical["rows"], list)
    ):
        _raise("CANONICAL_HOST_TOOLS_INVALID")
    _validate_copied_application_runtime_manifest(
        manifest["copied_application_runtime"]
    )
    _validate_canonical_host_tools_manifest(canonical)


def validate_manifest_object(value: object) -> ValidatedManifest:
    if not isinstance(value, dict):
        _raise("MANIFEST_FIELDS_INVALID")
    fields = frozenset(value)
    approved_host_tool_protocol = fields == APPROVED_MANIFEST_FIELDS
    if fields == MANIFEST_FIELDS:
        manifest = _exact_object(value, MANIFEST_FIELDS, "MANIFEST_FIELDS_INVALID")
    elif approved_host_tool_protocol:
        manifest = _exact_object(
            value, APPROVED_MANIFEST_FIELDS, "MANIFEST_FIELDS_INVALID"
        )
        _validate_approved_host_tool_manifests(manifest)
    else:
        _raise("MANIFEST_FIELDS_INVALID")
    if manifest["schema"] != "samvil.full-gate-manifest.v1":
        _raise("MANIFEST_SCHEMA_INVALID")
    nonce = _hex64(manifest["nonce"], "MANIFEST_NONCE_INVALID")
    control = _exact_object(
        manifest["control"],
        frozenset({"commit", "tree", "files"}),
        "CONTROL_IDENTITY_INVALID",
    )
    control_commit = _hex40(control["commit"], "CONTROL_IDENTITY_INVALID")
    control_tree = _hex40(control["tree"], "CONTROL_IDENTITY_INVALID")
    _validate_inventory(
        control["files"],
        "CONTROL_IDENTITY_INVALID",
        exact_paths=CONTROL_PATHS,
    )
    target = _validate_target(manifest["target"])
    _validate_artifact_reference(manifest["object_pack"], "OBJECT_PACK_INVALID")
    inventory = _validate_inventory(manifest["inventory"], "TARGET_INVENTORY_INVALID")
    wrapper = _exact_object(
        manifest["trusted_wrapper"],
        frozenset(trusted_wrapper_binding()),
        "TRUSTED_WRAPPER_MANIFEST_INVALID",
    )
    if wrapper != trusted_wrapper_binding():
        _raise("TRUSTED_WRAPPER_MANIFEST_INVALID")
    probes = manifest["probes"]
    if probes != trusted_probe_manifest():
        _raise("TRUSTED_PROBE_MANIFEST_INVALID")
    if approved_host_tool_protocol:
        expected_command = APPROVED_COMMAND
    else:
        _validate_apple_platform_tcb_manifest(manifest["apple_platform_tcb"])
        expected_command = COMMAND
    if manifest["command"] != list(expected_command):
        _raise("GATE_COMMAND_INVALID")
    gate_inventory = _validate_inventory(
        manifest["gate_inventory"],
        "GATE_INVENTORY_INVALID",
        exact_paths=("scripts/pre-commit-check.sh",),
    )
    phase6_inventory = _validate_inventory(
        manifest["phase6_inventory"],
        "PHASE6_INVENTORY_INVALID",
        exact_paths=(
            "scripts/phase6-real-runtime-dogfood.py",
            "mcp/tests/test_phase6_real_runtime_dogfood.py",
        ),
    )
    collected_tests = _validate_inventory(
        manifest["collected_mcp_tests"], "COLLECTED_TESTS_INVALID"
    )
    inventory_map = {entry["path"]: entry for entry in inventory}
    for entry in (*gate_inventory, *phase6_inventory, *collected_tests):
        if inventory_map.get(entry["path"]) != entry:
            _raise("TARGET_INVENTORY_INVALID")
    if any(
        not entry["path"].startswith("mcp/tests/")
        or not entry["path"].endswith(".py")
        for entry in collected_tests
    ):
        _raise("COLLECTED_TESTS_INVALID")
    derived_collected_tests = tuple(
        inventory_map[path]
        for path in sorted(inventory_map)
        if path.startswith("mcp/tests/")
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
    )
    if collected_tests != derived_collected_tests:
        _raise("COLLECTED_TESTS_INCOMPLETE")
    imports = _exact_object(
        manifest["import_manifest"],
        frozenset({"allowlist", "sha256"}),
        "IMPORT_MANIFEST_INVALID",
    )
    allowlist = imports["allowlist"]
    if (
        not isinstance(allowlist, list)
        or not allowlist
        or any(not isinstance(name, str) or not name for name in allowlist)
        or allowlist != sorted(set(allowlist))
        or any("release-control" in name or "release_control" in name for name in allowlist)
    ):
        _raise("IMPORT_MANIFEST_INVALID")
    import_sha256 = _hex64(imports["sha256"], "IMPORT_MANIFEST_INVALID")
    derived_import_sha256 = sha256_bytes(
        canonical_json_bytes(
            {
                "allowlist": allowlist,
                "collected_mcp_tests": manifest["collected_mcp_tests"],
            }
        )
    )
    if import_sha256 != derived_import_sha256:
        _raise("IMPORT_MANIFEST_INVALID")
    runtime = _exact_object(
        manifest["runtime"],
        frozenset({"python_version", "python_identity", *RUNTIME_ARTIFACT_FIELDS}),
        "RUNTIME_MANIFEST_INVALID",
    )
    runtime_identity = _validate_runtime_identity_manifest(runtime["python_identity"])
    if runtime["python_version"] != runtime_identity["version"]:
        _raise("RUNTIME_MANIFEST_INVALID")
    for role in RUNTIME_ARTIFACT_FIELDS:
        _validate_artifact_reference(runtime[role], "RUNTIME_MANIFEST_INVALID")
    if manifest["fixed_logs"] != list(MANIFEST_FIXED_LOG_PATHS):
        _raise("FIXED_LOG_MANIFEST_INVALID")
    _validate_semantic_counters(
        manifest["semantic_counters"], "SEMANTIC_COUNTER_SCHEMA_INVALID"
    )
    if not isinstance(manifest["resource_limits"], dict):
        _raise("RESOURCE_LIMIT_MANIFEST_INVALID")
    _validated_resource_limits(manifest["resource_limits"])
    if manifest["receipt_fields"] != list(RECEIPT_FIELDS):
        _raise("RECEIPT_SCHEMA_INVALID")

    kind = target["kind"]
    return ValidatedManifest(
        raw=manifest,
        manifest_sha256=sha256_bytes(canonical_json_bytes(manifest)),
        nonce=nonce,
        control_commit=control_commit,
        control_tree=control_tree,
        target_kind=kind,
        source_commit=target.get("source_commit"),
        candidate_tree=target["tree"],
        final_commit=target.get("final_commit"),
        expected_parent=target.get("expected_parent"),
        authorization_sha256=target.get("authorization_sha256"),
        precommit_tree=target.get("precommit_tree"),
        expected_precommit_nonce=target.get("expected_precommit_nonce"),
        expected_precommit_control_commit=target.get(
            "expected_precommit_control_commit"
        ),
        expected_precommit_control_tree=target.get("expected_precommit_control_tree"),
        expected_precommit_manifest_sha256=target.get(
            "expected_precommit_manifest_sha256"
        ),
        prior_receipt_sha256=target.get("prior_receipt_sha256"),
    )


def validate_cli_target_binding(
    arguments: FullGateArguments, manifest: ValidatedManifest
) -> None:
    if manifest.nonce != arguments.nonce:
        _raise("NONCE_MISMATCH")
    if manifest.target_kind == "candidate_postcommit":
        if arguments.prior_receipt is None:
            _raise("PRIOR_RECEIPT_REQUIRED")
    elif arguments.prior_receipt is not None:
        _raise("PRIOR_RECEIPT_FORBIDDEN")


def validate_prior_receipt_object(
    manifest: ValidatedManifest, value: object, raw: bytes
) -> str:
    if manifest.target_kind != "candidate_postcommit":
        _raise("PRIOR_RECEIPT_FORBIDDEN")
    receipt = _exact_object(value, frozenset(RECEIPT_FIELDS), "PRIOR_RECEIPT_INVALID")
    if raw != canonical_json_bytes(receipt):
        _raise("PRIOR_RECEIPT_CANONICAL_INVALID")
    receipt_sha256 = sha256_bytes(raw)
    if receipt_sha256 != manifest.prior_receipt_sha256:
        _raise("PRIOR_RECEIPT_DIGEST_MISMATCH")
    if receipt["schema"] != "samvil.full-gate-receipt.v1":
        _raise("PRIOR_RECEIPT_INVALID")
    if receipt["status"] != "PASS" or receipt["verdict"] != "PASS":
        _raise("PRIOR_RECEIPT_NOT_PASS")
    expected = {
        "nonce": manifest.expected_precommit_nonce,
        "control_commit": manifest.expected_precommit_control_commit,
        "control_tree": manifest.expected_precommit_control_tree,
        "target_kind": "candidate_precommit",
        "source_commit": None,
        "candidate_tree": manifest.precommit_tree,
        "final_commit": None,
        "expected_parent": manifest.expected_parent,
        "authorization_sha256": manifest.authorization_sha256,
        "manifest_sha256": manifest.expected_precommit_manifest_sha256,
        "prior_receipt_sha256": None,
        "profile_class": PROFILE_CLASS,
        "import_manifest_sha256": manifest.raw["import_manifest"]["sha256"],
        "promotion_limitations": list(PROMOTION_LIMITATIONS),
    }
    if any(receipt[field] != expected_value for field, expected_value in expected.items()):
        _raise("PRIOR_RECEIPT_MISMATCH")
    for field in (
        "command_sha256",
        "content_sha256",
        "profile_sha256",
        "import_manifest_sha256",
        "identity_sha256",
        "tree_sha256",
        "runtime_sha256",
    ):
        _hex64(receipt[field], "PRIOR_RECEIPT_INVALID")
    _validate_semantic_counters(
        receipt["semantic_counters"], "PRIOR_RECEIPT_INVALID"
    )
    return receipt_sha256


def _git_oid(kind: str, content: bytes) -> str:
    header = f"{kind} {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _decode_git_object_pack(raw: bytes) -> dict[str, GitObject]:
    decoded = decode_canonical_json_bytes(
        raw, status="GIT_OBJECT_PACK_INVALID", max_bytes=256 * 1024 * 1024
    )
    pack = _exact_object(
        decoded,
        frozenset({"schema", "objects"}),
        "GIT_OBJECT_PACK_INVALID",
    )
    if pack["schema"] != "samvil.git-object-pack.v1":
        _raise("GIT_OBJECT_PACK_INVALID")
    rows = pack["objects"]
    if not isinstance(rows, list) or not rows or len(rows) > 100_000:
        _raise("GIT_OBJECT_PACK_INVALID")
    objects: dict[str, GitObject] = {}
    total_bytes = 0
    for raw_entry in rows:
        entry = _exact_object(
            raw_entry,
            frozenset({"oid", "type", "size", "sha256", "content_base64"}),
            "GIT_OBJECT_PACK_INVALID",
        )
        oid = _hex40(entry["oid"], "GIT_OBJECT_PACK_INVALID")
        kind = entry["type"]
        size = entry["size"]
        encoded = entry["content_base64"]
        if (
            kind not in {"blob", "tree", "commit"}
            or type(size) is not int
            or size < 0
            or size > 64 * 1024 * 1024
            or not isinstance(encoded, str)
            or oid in objects
        ):
            _raise("GIT_OBJECT_PACK_INVALID")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            _raise("GIT_OBJECT_PACK_INVALID")
        if base64.b64encode(content).decode("ascii") != encoded or len(content) != size:
            _raise("GIT_OBJECT_PACK_INVALID")
        total_bytes += len(content)
        if total_bytes > 192 * 1024 * 1024:
            _raise("GIT_OBJECT_PACK_INVALID")
        if (
            sha256_bytes(content)
            != _hex64(entry["sha256"], "GIT_OBJECT_PACK_INVALID")
            or _git_oid(kind, content) != oid
        ):
            _raise("GIT_OBJECT_HASH_MISMATCH")
        objects[oid] = GitObject(kind, content)
    return objects


def _parse_commit(value: GitObject) -> tuple[str, tuple[str, ...]]:
    if value.kind != "commit" or b"\0" in value.content:
        _raise("GIT_COMMIT_INVALID")
    header, separator, _message = value.content.partition(b"\n\n")
    if not separator:
        _raise("GIT_COMMIT_INVALID")
    try:
        lines = header.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        _raise("GIT_COMMIT_INVALID")
    if not lines or not lines[0].startswith("tree "):
        _raise("GIT_COMMIT_INVALID")
    tree = _hex40(lines[0][5:], "GIT_COMMIT_INVALID")
    parents: list[str] = []
    for line in lines[1:]:
        if line.startswith("parent "):
            parents.append(_hex40(line[7:], "GIT_COMMIT_INVALID"))
        elif line.startswith(" "):
            continue
        elif " " not in line:
            _raise("GIT_COMMIT_INVALID")
    return tree, tuple(parents)


def _parse_tree(value: GitObject) -> tuple[tuple[str, str, str], ...]:
    if value.kind != "tree":
        _raise("GIT_TREE_INVALID")
    rows: list[tuple[str, str, str]] = []
    offset = 0
    previous: bytes | None = None
    collisions: set[str] = set()
    while offset < len(value.content):
        space = value.content.find(b" ", offset)
        nul = value.content.find(b"\0", space + 1)
        if space <= offset or nul < 0 or nul + 21 > len(value.content):
            _raise("GIT_TREE_INVALID")
        mode_bytes = value.content[offset:space]
        name_bytes = value.content[space + 1 : nul]
        oid = value.content[nul + 1 : nul + 21].hex()
        offset = nul + 21
        try:
            mode = mode_bytes.decode("ascii")
            name = name_bytes.decode("utf-8")
        except UnicodeDecodeError:
            _raise("GIT_TREE_INVALID")
        if (
            mode not in {"100644", "100755", "40000"}
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or unicodedata.normalize("NFC", name) != name
            or (previous is not None and name_bytes <= previous)
        ):
            _raise("GIT_TREE_INVALID")
        collision = name.casefold()
        if collision in collisions:
            _raise("GIT_TREE_INVALID")
        collisions.add(collision)
        previous = name_bytes
        rows.append((mode, name, oid))
    if offset != len(value.content):
        _raise("GIT_TREE_INVALID")
    return tuple(rows)


def verify_git_object_pack(
    manifest: ValidatedManifest, raw: bytes
) -> VerifiedGitObjectPack:
    objects = _decode_git_object_pack(raw)
    reachable: set[str] = set()
    files: dict[str, bytes] = {}
    modes: dict[str, str] = {}
    blobs: dict[str, str] = {}
    path_collisions: set[str] = set()

    target_trees: set[str] = set()

    def walk_target_tree(oid: str, prefix: str = "") -> None:
        if oid in target_trees:
            if prefix:
                _raise("GIT_OBJECT_ALIAS_INVALID")
            return
        value = objects.get(oid)
        if value is None or value.kind != "tree":
            _raise("GIT_OBJECT_CLOSURE_INVALID")
        target_trees.add(oid)
        reachable.add(oid)
        for mode, name, child_oid in _parse_tree(value):
            path = f"{prefix}/{name}" if prefix else name
            _safe_repo_path(path, "GIT_TREE_INVALID")
            collision = path.casefold()
            if collision in path_collisions:
                _raise("GIT_OBJECT_ALIAS_INVALID")
            path_collisions.add(collision)
            child = objects.get(child_oid)
            if child is None:
                _raise("GIT_OBJECT_CLOSURE_INVALID")
            if mode == "40000":
                if child.kind != "tree":
                    _raise("GIT_TREE_INVALID")
                walk_target_tree(child_oid, path)
            else:
                if child.kind != "blob":
                    _raise("GIT_TREE_INVALID")
                reachable.add(child_oid)
                files[path] = child.content
                modes[path] = mode
                blobs[path] = child_oid

    closure_trees: set[str] = set()

    def walk_closure_tree(oid: str) -> None:
        if oid in closure_trees:
            return
        value = objects.get(oid)
        if value is None or value.kind != "tree":
            _raise("GIT_OBJECT_CLOSURE_INVALID")
        closure_trees.add(oid)
        reachable.add(oid)
        for mode, _name, child_oid in _parse_tree(value):
            child = objects.get(child_oid)
            if child is None:
                _raise("GIT_OBJECT_CLOSURE_INVALID")
            if mode == "40000":
                if child.kind != "tree":
                    _raise("GIT_TREE_INVALID")
                walk_closure_tree(child_oid)
            else:
                if child.kind != "blob":
                    _raise("GIT_TREE_INVALID")
                reachable.add(child_oid)

    walked_commits: set[str] = set()

    def walk_commit(oid: str) -> tuple[str, tuple[str, ...]]:
        if oid in walked_commits:
            value = objects.get(oid)
            if value is None:
                _raise("GIT_OBJECT_CLOSURE_INVALID")
            return _parse_commit(value)
        value = objects.get(oid)
        if value is None or value.kind != "commit":
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")
        walked_commits.add(oid)
        reachable.add(oid)
        tree, parents = _parse_commit(value)
        walk_closure_tree(tree)
        for parent in parents:
            walk_commit(parent)
        return tree, parents

    if manifest.target_kind == "original":
        if manifest.source_commit is None:
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")
        commit_tree, _parents = walk_commit(manifest.source_commit)
        if commit_tree != manifest.candidate_tree:
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")
    elif manifest.target_kind == "candidate_precommit":
        if manifest.expected_parent is None:
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")
        walk_commit(manifest.expected_parent)
        walk_closure_tree(manifest.candidate_tree)
    else:
        if manifest.final_commit is None or manifest.expected_parent is None:
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")
        commit_tree, parents = walk_commit(manifest.final_commit)
        if commit_tree != manifest.candidate_tree or parents != (
            manifest.expected_parent,
        ):
            _raise("TARGET_COMMIT_IDENTITY_MISMATCH")

    walk_target_tree(manifest.candidate_tree)

    if set(objects) != reachable:
        _raise("GIT_OBJECT_CLOSURE_INVALID")
    inventory = manifest.raw["inventory"]
    if not isinstance(inventory, list):
        _raise("TARGET_INVENTORY_MISMATCH")
    flattened = [
        {
            "path": path,
            "mode": modes[path],
            "blob": blobs[path],
            "sha256": sha256_bytes(files[path]),
        }
        for path in sorted(files)
    ]
    if inventory != flattened:
        _raise("TARGET_INVENTORY_MISMATCH")
    closure_manifest = [
        {
            "oid": oid,
            "type": objects[oid].kind,
            "size": len(objects[oid].content),
            "sha256": sha256_bytes(objects[oid].content),
        }
        for oid in sorted(objects)
    ]
    return VerifiedGitObjectPack(
        tree=manifest.candidate_tree,
        files=dict(sorted(files.items())),
        modes=dict(sorted(modes.items())),
        blobs=dict(sorted(blobs.items())),
        closure_sha256=sha256_bytes(canonical_json_bytes(closure_manifest)),
    )


def _control_git(
    root: Path, environment: Mapping[str, str], *arguments: str
) -> bytes:
    safe_environment = {
        "PATH": environment.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": environment.get("HOME", "/var/empty"),
        "TMPDIR": environment.get("TMPDIR", "/var/empty"),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": environment.get("GIT_CONFIG_GLOBAL", "/dev/null"),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    try:
        completed = subprocess.run(
            [
                "/usr/bin/git",
                "-c",
                "credential.helper=",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "protocol.file.allow=never",
                "-C",
                str(root),
                *arguments,
            ],
            env=safe_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        _raise("CONTROL_GIT_FAILED")
    if completed.returncode != 0 or len(completed.stdout) > 4 * 1024 * 1024:
        _raise("CONTROL_GIT_FAILED")
    return completed.stdout


def validate_control_identity(
    control_root: Path,
    manifest: ValidatedManifest,
    environment: Mapping[str, str],
) -> str:
    try:
        root = control_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("CONTROL_IDENTITY_MISMATCH")
    if root != control_root or not root.is_dir():
        _raise("CONTROL_IDENTITY_MISMATCH")
    commit = _control_git(root, environment, "rev-parse", "--verify", "HEAD^{commit}")
    tree = _control_git(root, environment, "rev-parse", "--verify", "HEAD^{tree}")
    try:
        actual_commit = commit.decode("ascii").strip()
        actual_tree = tree.decode("ascii").strip()
    except UnicodeDecodeError:
        _raise("CONTROL_IDENTITY_MISMATCH")
    if (
        actual_commit != manifest.control_commit
        or actual_tree != manifest.control_tree
        or HEX40.fullmatch(actual_commit) is None
        or HEX40.fullmatch(actual_tree) is None
    ):
        _raise("CONTROL_IDENTITY_MISMATCH")
    control = manifest.raw["control"]
    if not isinstance(control, dict) or not isinstance(control.get("files"), list):
        _raise("CONTROL_IDENTITY_MISMATCH")
    observed: list[dict[str, object]] = []
    held: list[HeldArtifact] = []
    try:
        if len(control["files"]) != len(CONTROL_PATHS):
            _raise("CONTROL_IDENTITY_MISMATCH")
        for expected, path in zip(control["files"], CONTROL_PATHS):
            if not isinstance(expected, dict):
                _raise("CONTROL_IDENTITY_MISMATCH")
            raw = _control_git(root, environment, "ls-tree", "HEAD", "--", path)
            try:
                metadata, actual_path = raw.rstrip(b"\n").split(b"\t", 1)
                mode, kind, blob = metadata.decode("ascii").split(" ")
                decoded_path = actual_path.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                _raise("CONTROL_IDENTITY_MISMATCH")
            if (
                decoded_path != path
                or kind != "blob"
                or mode != expected["mode"]
                or blob != expected["blob"]
            ):
                _raise("CONTROL_IDENTITY_MISMATCH")
            artifact_path = root / path
            artifact = open_external_artifact(
                str(artifact_path),
                expected["sha256"],
                max_bytes=16 * 1024 * 1024,
                status="CONTROL_FILE_DRIFT",
            )
            held.append(artifact)
            expected_mode = "100755" if artifact.identity.mode & 0o111 else "100644"
            if expected_mode != mode or _git_oid("blob", artifact.data) != blob:
                _raise("CONTROL_FILE_DRIFT")
            observed.append(
                {
                    "path": path,
                    "mode": mode,
                    "blob": blob,
                    "sha256": sha256_bytes(artifact.data),
                }
            )
        for artifact in held:
            artifact.assert_stable()
    finally:
        close_failed = False
        for artifact in reversed(held):
            try:
                artifact.close()
            except FullGateError:
                close_failed = True
        if close_failed:
            _raise("CONTROL_FILE_CLOSE_FAILED")
    return sha256_bytes(
        canonical_json_bytes(
            {
                "commit": actual_commit,
                "tree": actual_tree,
                "files": observed,
            }
        )
    )


def _canonical_destination(path: Path, status: str, *, must_exist: bool) -> Path:
    if not path.is_absolute():
        _raise(status)
    try:
        parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    canonical = parent / path.name
    if canonical != path:
        _raise(status)
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        if must_exist:
            _raise(status)
        return canonical
    except OSError:
        _raise(status)
    if not must_exist or not stat.S_ISDIR(metadata.st_mode):
        _raise(status)
    try:
        if path.resolve(strict=True) != path:
            _raise(status)
    except (OSError, RuntimeError):
        _raise(status)
    return canonical


def _safe_directory(root: Path, relative_parent: Path, status: str) -> Path:
    current = root
    for part in relative_parent.parts:
        if part in {"", ".", ".."}:
            _raise(status)
        child = current / part
        try:
            metadata = os.lstat(child)
        except FileNotFoundError:
            try:
                os.mkdir(child, 0o700)
                metadata = os.lstat(child)
            except OSError:
                _raise(status)
        except OSError:
            _raise(status)
        if not stat.S_ISDIR(metadata.st_mode):
            _raise(status)
        current = child
    return current


def _write_materialized_file(
    root: Path, path: str, content: bytes, mode: str, status: str
) -> None:
    relative = Path(_safe_repo_path(path, status))
    parent = _safe_directory(root, relative.parent, status)
    target = parent / relative.name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError:
        _raise(status)
    primary: FullGateError | None = None
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _raise(status)
            view = view[written:]
        os.fchmod(descriptor, 0o755 if mode == "100755" else 0o644)
        os.fsync(descriptor)
        descriptor_state = os.fstat(descriptor)
        path_state = os.lstat(target)
        if (
            FileIdentity.from_stat(descriptor_state)
            != FileIdentity.from_stat(path_state)
            or not stat.S_ISREG(descriptor_state.st_mode)
            or descriptor_state.st_nlink != 1
            or descriptor_state.st_size != len(content)
        ):
            _raise(status)
    except FullGateError as exc:
        primary = exc
    except OSError:
        primary = FullGateError(status)
    try:
        os.close(descriptor)
    except OSError:
        _raise(f"{status}_CLOSE_FAILED")
    if primary is not None:
        raise primary


def materialize_verified_snapshot(
    verified: VerifiedGitObjectPack, destination: Path
) -> str:
    root = _canonical_destination(
        destination, "SNAPSHOT_MATERIALIZATION_INVALID", must_exist=False
    )
    try:
        os.mkdir(root, 0o700)
    except OSError:
        _raise("SNAPSHOT_MATERIALIZATION_INVALID")
    observed: list[dict[str, object]] = []
    try:
        for path in sorted(verified.files):
            _write_materialized_file(
                root,
                path,
                verified.files[path],
                verified.modes[path],
                "SNAPSHOT_MATERIALIZATION_FAILED",
            )
            observed.append(
                {
                    "path": path,
                    "mode": verified.modes[path],
                    "blob": verified.blobs[path],
                    "sha256": sha256_bytes(verified.files[path]),
                }
            )
    except BaseException:
        _remove_invocation_tree(root, "SNAPSHOT_CLEANUP_FAILED")
        raise
    return sha256_bytes(canonical_json_bytes(observed))


def _decode_closure_manifest(
    raw: bytes, expected_role: str
) -> tuple[dict[str, object], ...]:
    decoded = decode_canonical_json_bytes(
        raw, status="CLOSURE_MANIFEST_INVALID", max_bytes=16 * 1024 * 1024
    )
    manifest = _exact_object(
        decoded,
        frozenset({"schema", "role", "files"}),
        "CLOSURE_MANIFEST_INVALID",
    )
    if (
        manifest["schema"] != "samvil.full-gate-closure-manifest.v1"
        or manifest["role"] != expected_role
        or not isinstance(manifest["files"], list)
        or not manifest["files"]
    ):
        _raise("CLOSURE_MANIFEST_INVALID")
    entries: list[dict[str, object]] = []
    collisions: set[str] = set()
    for raw_entry in manifest["files"]:
        entry = _exact_object(
            raw_entry,
            frozenset({"path", "mode", "size", "sha256"}),
            "CLOSURE_MANIFEST_INVALID",
        )
        path = _safe_repo_path(entry["path"], "CLOSURE_MANIFEST_INVALID")
        collision = path.casefold()
        size = entry["size"]
        if (
            collision in collisions
            or entry["mode"] not in {"100644", "100755"}
            or type(size) is not int
            or size < 0
            or size > 64 * 1024 * 1024
        ):
            _raise("CLOSURE_MANIFEST_INVALID")
        collisions.add(collision)
        entries.append(
            {
                "path": path,
                "mode": entry["mode"],
                "size": size,
                "sha256": _hex64(entry["sha256"], "CLOSURE_MANIFEST_INVALID"),
            }
        )
    if entries != sorted(entries, key=lambda item: item["path"]):
        _raise("CLOSURE_MANIFEST_INVALID")
    return tuple(entries)


def _dependency_path_forbidden(path: str) -> bool:
    name = Path(path).name.casefold()
    return (
        name.endswith(".pth")
        or name in {"sitecustomize.py", "usercustomize.py", "direct_url.json"}
    )


def _looks_like_trivial_exit_zero(content: bytes) -> bool:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    meaningful = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return meaningful in (["exit 0"], ["true"], [":"])


def _is_macho(content: bytes) -> bool:
    return content[:4] in {
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
        b"\xca\xfe\xba\xbf",
        b"\xbf\xba\xfe\xca",
    }


def _macho_slices(content: bytes) -> tuple[str, ...]:
    if len(content) < 12 or not _is_macho(content):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    magic = content[:4]
    architectures: list[tuple[int, int]] = []
    if magic in {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca"}:
        endian = ">" if magic[:1] == b"\xca" else "<"
        is_64 = magic in {b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
        try:
            count = struct.unpack_from(f"{endian}I", content, 4)[0]
        except struct.error:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        entry_size = 32 if is_64 else 20
        if count < 1 or count > 8 or len(content) < 8 + count * entry_size:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        for index in range(count):
            try:
                cpu_type, cpu_subtype = struct.unpack_from(
                    f"{endian}ii", content, 8 + index * entry_size
                )
            except struct.error:
                _raise("UNSUPPORTED_HERMETIC_RUNTIME")
            architectures.append((cpu_type, cpu_subtype))
    else:
        endian = ">" if magic == b"\xfe\xed\xfa\xcf" else "<"
        try:
            architectures.append(struct.unpack_from(f"{endian}ii", content, 4))
        except struct.error:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")

    slices: list[str] = []
    for cpu_type, raw_subtype in architectures:
        subtype = raw_subtype & 0x00FFFFFF
        if cpu_type == 0x01000007:
            name = "x86_64"
        elif cpu_type == 0x0100000C and subtype == 2:
            name = "arm64e"
        elif cpu_type == 0x0100000C:
            name = "arm64"
        else:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        if name in slices:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        slices.append(name)
    return tuple(slices)


def _apple_identity_object(metadata: os.stat_result) -> dict[str, object]:
    return {
        "device": str(metadata.st_dev),
        "inode": str(metadata.st_ino),
        "mode": metadata.st_mode,
        "nlink": metadata.st_nlink,
        "size": metadata.st_size,
        "mtime_ns": str(
            getattr(
                metadata, "st_mtime_ns", int(metadata.st_mtime * 1_000_000_000)
            )
        ),
        "ctime_ns": str(
            getattr(
                metadata, "st_ctime_ns", int(metadata.st_ctime * 1_000_000_000)
            )
        ),
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
    }


def _open_apple_platform_tool(
    path: Path, classification: str
) -> HeldApplePlatformTool:
    expected = {
        APPLE_SANDBOX_EXEC: "apple_platform_tool",
        APPLE_CODESIGN: "apple_platform_identity_verifier",
    }
    if expected.get(path) != classification or not path.is_absolute():
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        if path.resolve(strict=True) != path:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        descriptor = os.open(path, flags)
    except FullGateError:
        raise
    except (OSError, RuntimeError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    held: HeldApplePlatformTool | None = None
    try:
        descriptor_state = os.fstat(descriptor)
        path_state = os.lstat(path)
        identity = FileIdentity.from_stat(descriptor_state)
        if (
            not stat.S_ISREG(descriptor_state.st_mode)
            or identity != FileIdentity.from_stat(path_state)
            or descriptor_state.st_uid != 0
            or path_state.st_uid != 0
            or stat.S_IMODE(descriptor_state.st_mode) != 0o755
            or descriptor_state.st_nlink != 1
            or descriptor_state.st_size < 1
            or descriptor_state.st_size > APPLE_TOOL_MAX_BYTES
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        chunks: list[bytes] = []
        remaining = descriptor_state.st_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                _raise("UNSUPPORTED_HERMETIC_RUNTIME")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        content = b"".join(chunks)
        slices = _macho_slices(content)
        binding = {
            "schema": "samvil.apple-platform-tool.v1",
            "classification": classification,
            "path": str(path),
            "uid": descriptor_state.st_uid,
            "gid": descriptor_state.st_gid,
            "mode": "100755",
            "nlink": descriptor_state.st_nlink,
            "size": descriptor_state.st_size,
            "sha256": sha256_bytes(content),
            "slices": list(slices),
            "path_identity": _apple_identity_object(descriptor_state),
        }
        held = HeldApplePlatformTool(path, descriptor, identity, binding)
        held.assert_stable()
        return held
    except BaseException:
        if held is None or not held.closed:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _apple_output_bytes(value: bytes | str) -> bytes:
    if isinstance(value, bytes):
        result = value
    elif isinstance(value, str):
        try:
            result = value.encode("utf-8")
        except UnicodeEncodeError:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    else:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if len(result) > APPLE_COMMAND_OUTPUT_MAX_BYTES:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return result


def parse_canonical_codesign_result(
    *,
    target_path: object,
    signing_identifier: object,
    expected_slices: object,
    verify_argv: object,
    verify_returncode: object,
    verify_stdout: object,
    verify_stderr: object,
    display_argv: object,
    display_returncode: object,
    display_stdout: object,
    display_stderr: object,
) -> dict[str, object]:
    status = "UNSUPPORTED_CANONICAL_TOOLCHAIN"
    if (
        not isinstance(target_path, str)
        or not target_path.startswith("/")
        or target_path == str(APPLE_CODESIGN)
        or "\x00" in target_path
        or "\\" in target_path
        or str(Path(target_path)) != target_path
        or any(part in {"", ".", ".."} for part in target_path.split("/")[1:])
        or not isinstance(signing_identifier, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,255}", signing_identifier)
        is None
        or not isinstance(expected_slices, list)
        or not expected_slices
        or len(set(expected_slices)) != len(expected_slices)
        or any(
            not isinstance(slice_name, str)
            or slice_name not in {"arm64", "arm64e", "x86_64"}
            for slice_name in expected_slices
        )
    ):
        _raise(status)

    requirement = f'anchor apple and identifier "{signing_identifier}"'
    expected_verify_argv = [
        str(APPLE_CODESIGN),
        "--verify",
        "--strict",
        "--verbose=2",
        f"-R={requirement}",
        target_path,
    ]
    expected_display_argv = [
        str(APPLE_CODESIGN),
        "-d",
        "--verbose=4",
        "-r-",
        target_path,
    ]
    if (
        type(verify_returncode) is not int
        or verify_returncode != 0
        or type(display_returncode) is not int
        or display_returncode != 0
        or not isinstance(verify_argv, list)
        or verify_argv != expected_verify_argv
        or any(not isinstance(item, str) for item in verify_argv)
        or not isinstance(display_argv, list)
        or display_argv != expected_display_argv
        or any(not isinstance(item, str) for item in display_argv)
    ):
        _raise(status)

    channels = (verify_stdout, verify_stderr, display_stdout, display_stderr)
    if any(
        not isinstance(channel, bytes)
        or len(channel) > APPLE_COMMAND_OUTPUT_MAX_BYTES
        for channel in channels
    ):
        _raise(status)
    try:
        verify_out = verify_stdout.decode("utf-8", "strict")
        verify_err = verify_stderr.decode("utf-8", "strict")
        display_out = display_stdout.decode("utf-8", "strict")
        display_err = display_stderr.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _raise(status)

    verify_statements = [
        f"{target_path}: valid on disk",
        f"{target_path}: satisfies its Designated Requirement",
        f"{target_path}: explicit requirement satisfied",
    ]
    designated_requirement = (
        f'designated => identifier "{signing_identifier}" and anchor apple'
    )
    if (
        verify_out != ""
        or verify_err != "\n".join(verify_statements) + "\n"
        or display_out != designated_requirement + "\n"
    ):
        _raise(status)

    metadata_lines = display_err.splitlines()
    expected_keys = (
        "Executable",
        "Identifier",
        "Format",
        "CodeDirectory",
        "Platform identifier",
        "VersionPlatform",
        "VersionMin",
        "VersionSDK",
        "Hash type",
        "CandidateCDHash sha256",
        "CandidateCDHashFull sha256",
        "Hash choices",
        "CMSDigest",
        "CMSDigestType",
        "Executable Segment base",
        "Executable Segment limit",
        "Executable Segment flags",
        "Page size",
        "CDHash",
        "Signature size",
        "Authority",
        "Authority",
        "Authority",
        "Signed Time",
        "Info.plist",
        "TeamIdentifier",
        "Sealed Resources",
    )
    parsed: list[tuple[str, str]] = []
    for line in metadata_lines:
        if line.startswith("CodeDirectory "):
            key = "CodeDirectory"
            field_value = line.removeprefix("CodeDirectory ")
        else:
            matches = [
                key
                for key in dict.fromkeys(expected_keys)
                if line.startswith(f"{key}=")
            ]
            if len(matches) != 1:
                _raise(status)
            key = matches[0]
            field_value = line[len(key) + 1 :]
        if not field_value:
            _raise(status)
        parsed.append((key, field_value))
    if tuple(key for key, _field_value in parsed) != expected_keys:
        _raise(status)
    values: dict[str, list[str]] = {}
    for key, field_value in parsed:
        values.setdefault(key, []).append(field_value)

    cdhash = values["CDHash"][0]
    candidate_cdhash = values["CandidateCDHash sha256"][0]
    cdhash_full = values["CandidateCDHashFull sha256"][0]
    if (
        values["Executable"] != [target_path]
        or values["Identifier"] != [signing_identifier]
        or values["Format"]
        != [f"Mach-O universal ({' '.join(expected_slices)})"]
        or values["Platform identifier"] != ["16"]
        or values["Hash type"] != ["sha256 size=32"]
        or values["Hash choices"] != ["sha256"]
        or values["CMSDigestType"] != ["2"]
        or values["Authority"]
        != [
            "Software Signing",
            "Apple Code Signing Certification Authority",
            "Apple Root CA",
        ]
        or values["Info.plist"] != ["not bound"]
        or values["TeamIdentifier"] != ["not set"]
        or values["Sealed Resources"] != ["none"]
        or HEX40.fullmatch(cdhash) is None
        or candidate_cdhash != cdhash
        or HEX64.fullmatch(cdhash_full) is None
        or not cdhash_full.startswith(cdhash)
        or values["CMSDigest"] != [cdhash_full]
    ):
        _raise(status)

    payload = {
        "schema": "samvil.canonical-codesign-result.v1",
        "target_path": target_path,
        "signing_identifier": signing_identifier,
        "requirement": requirement,
        "designated_requirement": designated_requirement,
        "slices": list(expected_slices),
        "platform_identifier": 16,
        "cdhash": cdhash,
        "cdhash_full": cdhash_full,
        "authorities": values["Authority"],
        "verify_statements": verify_statements,
        "metadata_lines": metadata_lines,
    }
    return {
        **payload,
        "result_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def parse_apple_codesign_results(
    *,
    verify_stdout: bytes | str,
    verify_stderr: bytes | str,
    display_stdout: bytes | str,
    display_stderr: bytes | str,
    sandbox_slices: Sequence[str],
) -> dict[str, object]:
    verify_out = _apple_output_bytes(verify_stdout)
    verify_err = _apple_output_bytes(verify_stderr)
    display_out = _apple_output_bytes(display_stdout)
    display_err = _apple_output_bytes(display_stderr)
    expected_verify = (
        b"/usr/bin/sandbox-exec: valid on disk\n"
        b"/usr/bin/sandbox-exec: satisfies its Designated Requirement\n"
        b"/usr/bin/sandbox-exec: explicit requirement satisfied\n"
    )
    expected_designated = (
        b'designated => identifier "com.apple.sandbox-exec" and anchor apple\n'
    )
    slices = tuple(sandbox_slices)
    if (
        verify_out != b""
        or verify_err != expected_verify
        or display_out != expected_designated
        or not slices
        or any(slice_name not in {"x86_64", "arm64", "arm64e"} for slice_name in slices)
        or len(set(slices)) != len(slices)
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    try:
        lines = display_err.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    expected_keys = (
        "Executable",
        "Identifier",
        "Format",
        "CodeDirectory",
        "Platform identifier",
        "VersionPlatform",
        "VersionMin",
        "VersionSDK",
        "Hash type",
        "CandidateCDHash sha256",
        "CandidateCDHashFull sha256",
        "Hash choices",
        "CMSDigest",
        "CMSDigestType",
        "Executable Segment base",
        "Executable Segment limit",
        "Executable Segment flags",
        "Page size",
        "CDHash",
        "Signature size",
        "Authority",
        "Authority",
        "Authority",
        "Signed Time",
        "Info.plist",
        "TeamIdentifier",
        "Sealed Resources",
    )
    parsed: list[tuple[str, str]] = []
    for line in lines:
        if line.startswith("CodeDirectory "):
            key, value = "CodeDirectory", line.removeprefix("CodeDirectory ")
        else:
            matches = [
                key for key in dict.fromkeys(expected_keys) if line.startswith(f"{key}=")
            ]
            if len(matches) != 1:
                _raise("UNSUPPORTED_HERMETIC_RUNTIME")
            key = matches[0]
            value = line[len(key) + 1 :]
        if not value:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        parsed.append((key, value))
    if tuple(key for key, _value in parsed) != expected_keys:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    values: dict[str, list[str]] = {}
    for key, value in parsed:
        values.setdefault(key, []).append(value)
    cdhash = values["CDHash"][0]
    candidate = values["CandidateCDHash sha256"][0]
    full = values["CandidateCDHashFull sha256"][0]
    if (
        values["Executable"] != [str(APPLE_SANDBOX_EXEC)]
        or values["Identifier"] != ["com.apple.sandbox-exec"]
        or values["Format"] != [f"Mach-O universal ({' '.join(slices)})"]
        or values["Platform identifier"] != ["16"]
        or values["Hash type"] != ["sha256 size=32"]
        or values["Hash choices"] != ["sha256"]
        or values["Authority"]
        != [
            "Software Signing",
            "Apple Code Signing Certification Authority",
            "Apple Root CA",
        ]
        or values["Info.plist"] != ["not bound"]
        or values["TeamIdentifier"] != ["not set"]
        or values["Sealed Resources"] != ["none"]
        or HEX40.fullmatch(cdhash) is None
        or candidate != cdhash
        or HEX64.fullmatch(full) is None
        or not full.startswith(cdhash)
        or values["CMSDigest"] != [full]
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    result = {
        "requirement": APPLE_CODESIGN_REQUIREMENT,
        "designated_requirement": expected_designated.decode("utf-8").rstrip("\n"),
        "identifier": "com.apple.sandbox-exec",
        "format": values["Format"][0],
        "platform_identifier": 16,
        "slices": list(slices),
        "cdhash": cdhash,
        "cdhash_full": full,
        "authorities": values["Authority"],
        "metadata_lines": lines,
        "verify_statements": expected_verify.decode("utf-8").splitlines(),
    }
    return {
        **result,
        "result_sha256": sha256_bytes(canonical_json_bytes(result)),
    }


def _run_apple_command(
    argv: Sequence[str], scratch_root: Path
) -> subprocess.CompletedProcess[bytes]:
    command = tuple(argv)
    if command not in {
        APPLE_CODESIGN_VERIFY_ARGV,
        APPLE_CODESIGN_DISPLAY_ARGV,
        APPLE_SANDBOX_BEHAVIOR_ARGV,
    }:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    try:
        scratch = scratch_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if scratch != scratch_root or not scratch.is_dir():
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home-unavailable"),
        "CODEX_HOME": str(scratch / "codex-home-unavailable"),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        result = subprocess.run(
            list(command),
            cwd=scratch,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if (
        len(result.stdout) > APPLE_COMMAND_OUTPUT_MAX_BYTES
        or len(result.stderr) > APPLE_COMMAND_OUTPUT_MAX_BYTES
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return result


def _capture_apple_codesign_result(
    sandbox_exec: HeldApplePlatformTool,
    codesign: HeldApplePlatformTool,
    scratch: Path,
) -> dict[str, object]:
    sandbox_exec.assert_stable()
    codesign.assert_stable()
    verify = _run_apple_command(APPLE_CODESIGN_VERIFY_ARGV, scratch)
    sandbox_exec.assert_stable()
    codesign.assert_stable()
    display = _run_apple_command(APPLE_CODESIGN_DISPLAY_ARGV, scratch)
    sandbox_exec.assert_stable()
    codesign.assert_stable()
    if verify.returncode != 0 or display.returncode != 0:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    parsed = parse_apple_codesign_results(
        verify_stdout=verify.stdout,
        verify_stderr=verify.stderr,
        display_stdout=display.stdout,
        display_stderr=display.stderr,
        sandbox_slices=sandbox_exec.binding["slices"],
    )
    payload = {
        "verify": {
            "argv": list(APPLE_CODESIGN_VERIFY_ARGV),
            "returncode": verify.returncode,
            "stdout": verify.stdout.decode("utf-8", "strict"),
            "stderr": verify.stderr.decode("utf-8", "strict"),
        },
        "display": {
            "argv": list(APPLE_CODESIGN_DISPLAY_ARGV),
            "returncode": display.returncode,
            "stdout": display.stdout.decode("utf-8", "strict"),
            "stderr": display.stderr.decode("utf-8", "strict"),
        },
        "parsed": parsed,
        "verifier_identity_sha256": sha256_bytes(
            canonical_json_bytes(codesign.binding)
        ),
    }
    return {
        **payload,
        "result_sha256": sha256_bytes(canonical_json_bytes(payload)),
    }


def _validate_apple_tool_manifest(
    raw: object, *, path: Path, classification: str
) -> dict[str, object]:
    value = _exact_object(
        raw,
        frozenset(
            {
                "schema",
                "classification",
                "path",
                "uid",
                "gid",
                "mode",
                "nlink",
                "size",
                "sha256",
                "slices",
                "path_identity",
            }
        ),
        "UNSUPPORTED_HERMETIC_RUNTIME",
    )
    if (
        value["schema"] != "samvil.apple-platform-tool.v1"
        or value["classification"] != classification
        or value["path"] != str(path)
        or value["uid"] != 0
        or type(value["gid"]) is not int
        or value["gid"] < 0
        or value["mode"] != "100755"
        or value["nlink"] != 1
        or type(value["size"]) is not int
        or value["size"] < 1
        or value["size"] > APPLE_TOOL_MAX_BYTES
        or HEX64.fullmatch(value["sha256"]) is None
        or not isinstance(value["slices"], list)
        or not value["slices"]
        or any(item not in {"x86_64", "arm64", "arm64e"} for item in value["slices"])
        or len(set(value["slices"])) != len(value["slices"])
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    identity = _exact_object(
        value["path_identity"],
        frozenset(
            {
                "device",
                "inode",
                "mode",
                "nlink",
                "size",
                "mtime_ns",
                "ctime_ns",
                "uid",
                "gid",
            }
        ),
        "UNSUPPORTED_HERMETIC_RUNTIME",
    )
    if (
        _identity_uint(identity["device"], "UNSUPPORTED_HERMETIC_RUNTIME") < 0
        or _identity_uint(identity["inode"], "UNSUPPORTED_HERMETIC_RUNTIME") < 0
        or _identity_uint(identity["mtime_ns"], "UNSUPPORTED_HERMETIC_RUNTIME") < 0
        or _identity_uint(identity["ctime_ns"], "UNSUPPORTED_HERMETIC_RUNTIME") < 0
        or any(
            type(identity[key]) is not int or identity[key] < 0
            for key in ("mode", "nlink", "size", "uid", "gid")
        )
        or identity["uid"] != 0
        or identity["gid"] != value["gid"]
        or identity["nlink"] != 1
        or identity["size"] != value["size"]
        or stat.S_IMODE(identity["mode"]) != 0o755
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return value


def _validate_apple_platform_tcb_manifest(raw: object) -> dict[str, object]:
    value = _exact_object(
        raw,
        frozenset({"schema", "sandbox_exec", "codesign", "codesign_result"}),
        "UNSUPPORTED_HERMETIC_RUNTIME",
    )
    if value["schema"] != "samvil.apple-platform-tcb.v1":
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    sandbox = _validate_apple_tool_manifest(
        value["sandbox_exec"],
        path=APPLE_SANDBOX_EXEC,
        classification="apple_platform_tool",
    )
    codesign = _validate_apple_tool_manifest(
        value["codesign"],
        path=APPLE_CODESIGN,
        classification="apple_platform_identity_verifier",
    )
    result = _exact_object(
        value["codesign_result"],
        frozenset(
            {
                "verify",
                "display",
                "parsed",
                "verifier_identity_sha256",
                "result_sha256",
            }
        ),
        "UNSUPPORTED_HERMETIC_RUNTIME",
    )
    for key, expected_argv in (
        ("verify", APPLE_CODESIGN_VERIFY_ARGV),
        ("display", APPLE_CODESIGN_DISPLAY_ARGV),
    ):
        invocation = _exact_object(
            result[key],
            frozenset({"argv", "returncode", "stdout", "stderr"}),
            "UNSUPPORTED_HERMETIC_RUNTIME",
        )
        if (
            invocation["argv"] != list(expected_argv)
            or invocation["returncode"] != 0
            or not isinstance(invocation["stdout"], str)
            or not isinstance(invocation["stderr"], str)
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    parsed = parse_apple_codesign_results(
        verify_stdout=result["verify"]["stdout"],
        verify_stderr=result["verify"]["stderr"],
        display_stdout=result["display"]["stdout"],
        display_stderr=result["display"]["stderr"],
        sandbox_slices=sandbox["slices"],
    )
    payload = {
        "verify": result["verify"],
        "display": result["display"],
        "parsed": parsed,
        "verifier_identity_sha256": sha256_bytes(canonical_json_bytes(codesign)),
    }
    if (
        result["parsed"] != parsed
        or result["verifier_identity_sha256"] != payload["verifier_identity_sha256"]
        or result["result_sha256"] != sha256_bytes(canonical_json_bytes(payload))
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return value


def apple_platform_tcb_binding() -> dict[str, object]:
    global _APPLE_PLATFORM_BINDING_CACHE
    if _APPLE_PLATFORM_BINDING_CACHE is not None:
        cached = json.loads(_APPLE_PLATFORM_BINDING_CACHE.decode("utf-8"))
        if not isinstance(cached, dict):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        return cached
    sandbox = _open_apple_platform_tool(
        APPLE_SANDBOX_EXEC, "apple_platform_tool"
    )
    codesign: HeldApplePlatformTool | None = None
    try:
        codesign = _open_apple_platform_tool(
            APPLE_CODESIGN, "apple_platform_identity_verifier"
        )
        with tempfile.TemporaryDirectory(prefix="samvil-apple-platform-binding-") as raw:
            scratch = Path(raw).resolve(strict=True)
            result = _capture_apple_codesign_result(sandbox, codesign, scratch)
        sandbox.assert_stable()
        codesign.assert_stable()
        binding = {
            "schema": "samvil.apple-platform-tcb.v1",
            "sandbox_exec": dict(sandbox.binding),
            "codesign": dict(codesign.binding),
            "codesign_result": result,
        }
        _validate_apple_platform_tcb_manifest(binding)
        _APPLE_PLATFORM_BINDING_CACHE = canonical_json_bytes(binding)
        return json.loads(_APPLE_PLATFORM_BINDING_CACHE.decode("utf-8"))
    finally:
        if codesign is not None:
            codesign.close()
        sandbox.close()


def acquire_apple_platform_tcb(
    expected_binding: Mapping[str, object], scratch_root: Path
) -> HeldApplePlatformTCB:
    expected = _validate_apple_platform_tcb_manifest(expected_binding)
    sandbox = _open_apple_platform_tool(
        APPLE_SANDBOX_EXEC, "apple_platform_tool"
    )
    codesign: HeldApplePlatformTool | None = None
    try:
        codesign = _open_apple_platform_tool(
            APPLE_CODESIGN, "apple_platform_identity_verifier"
        )
        if (
            dict(sandbox.binding) != expected["sandbox_exec"]
            or dict(codesign.binding) != expected["codesign"]
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        codesign_result = _capture_apple_codesign_result(
            sandbox, codesign, scratch_root
        )
        if codesign_result != expected["codesign_result"]:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        behavior_result = _run_apple_command(
            APPLE_SANDBOX_BEHAVIOR_ARGV, scratch_root
        )
        sandbox.assert_stable()
        codesign.assert_stable()
        if (
            behavior_result.returncode != 0
            or behavior_result.stdout != b""
            or behavior_result.stderr != b""
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        behavior_payload = {
            "argv": list(APPLE_SANDBOX_BEHAVIOR_ARGV),
            "returncode": behavior_result.returncode,
            "stdout": "",
            "stderr": "",
        }
        behavior = {
            **behavior_payload,
            "result_sha256": sha256_bytes(canonical_json_bytes(behavior_payload)),
        }
        held = HeldApplePlatformTCB(sandbox, codesign, codesign_result, behavior)
        held.assert_stable()
        return held
    except BaseException:
        if codesign is not None:
            codesign.close()
        sandbox.close()
        raise


def validate_apple_platform_tcb(
    expected_binding: Mapping[str, object], scratch_root: Path
) -> dict[str, object]:
    held = acquire_apple_platform_tcb(expected_binding, scratch_root)
    try:
        return held.complete()
    finally:
        held.close()


def materialize_closure_archive(
    archive_raw: bytes,
    manifest_raw: bytes,
    destination: Path,
    *,
    expected_role: str,
) -> str:
    if expected_role not in {"python", "dependencies", "tools"}:
        _raise("CLOSURE_MANIFEST_INVALID")
    entries = _decode_closure_manifest(manifest_raw, expected_role)
    expected = {entry["path"]: entry for entry in entries}
    if expected_role == "dependencies" and any(
        _dependency_path_forbidden(path) for path in expected
    ):
        _raise("DEPENDENCY_CLOSURE_INVALID")
    if expected_role == "python" and (
        "bin/python3.12" not in expected
        or expected["bin/python3.12"]["mode"] != "100755"
    ):
        _raise("PYTHON_CLOSURE_INVALID")
    if expected_role == "tools":
        required = {f"bin/{name}" for name in REQUIRED_TOOL_NAMES}
        if (
            {"bin/sandbox-exec", "bin/codesign"}.intersection(expected)
            or not required.issubset(expected)
            or any(
            expected[path]["mode"] != "100755" for path in required
            )
        ):
            _raise("TOOL_CLOSURE_INVALID")
    if len(archive_raw) > 256 * 1024 * 1024:
        _raise("CLOSURE_ARCHIVE_INVALID")
    extracted: dict[str, tuple[str, bytes]] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_raw), mode="r:*") as archive:
            for member in archive:
                if not member.isfile():
                    _raise("CLOSURE_ARCHIVE_INVALID")
                path = _safe_repo_path(member.name, "CLOSURE_ARCHIVE_INVALID")
                if path in extracted or path.casefold() in {
                    existing.casefold() for existing in extracted
                }:
                    _raise("CLOSURE_ARCHIVE_INVALID")
                handle = archive.extractfile(member)
                if handle is None:
                    _raise("CLOSURE_ARCHIVE_INVALID")
                content = handle.read(64 * 1024 * 1024 + 1)
                if len(content) > 64 * 1024 * 1024:
                    _raise("CLOSURE_ARCHIVE_INVALID")
                mode = "100755" if member.mode & 0o111 else "100644"
                extracted[path] = (mode, content)
    except FullGateError:
        raise
    except (tarfile.TarError, OSError, EOFError, MemoryError):
        _raise("CLOSURE_ARCHIVE_INVALID")
    if set(extracted) != set(expected):
        _raise("CLOSURE_ARCHIVE_INVALID")
    for path, (mode, content) in extracted.items():
        entry = expected[path]
        if (
            mode != entry["mode"]
            or len(content) != entry["size"]
            or sha256_bytes(content) != entry["sha256"]
        ):
            _raise("CLOSURE_ARCHIVE_INVALID")
    if expected_role == "python" and not _is_macho(
        extracted["bin/python3.12"][1]
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if expected_role == "tools" and any(
        _looks_like_trivial_exit_zero(extracted[path][1])
        for path in required
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    root = _canonical_destination(
        destination, "CLOSURE_MATERIALIZATION_INVALID", must_exist=False
    )
    try:
        os.mkdir(root, 0o700)
    except OSError:
        _raise("CLOSURE_MATERIALIZATION_INVALID")
    try:
        for path in sorted(extracted):
            mode, content = extracted[path]
            _write_materialized_file(
                root, path, content, mode, "CLOSURE_MATERIALIZATION_FAILED"
            )
    except BaseException:
        _remove_invocation_tree(root, "CLOSURE_CLEANUP_FAILED")
        raise
    return sha256_bytes(canonical_json_bytes(list(entries)))


def materialize_runtime_python_facade(
    invocation_root: Path, runtime_root: Path, tools_root: Path
) -> Path:
    status = "RUNTIME_PYTHON_FACADE_INVALID"
    try:
        invocation = invocation_root.resolve(strict=True)
        runtime = runtime_root.resolve(strict=True)
        tools = tools_root.resolve(strict=True)
        python = (runtime / "bin/python3.12").resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if invocation != invocation_root or runtime != runtime_root or tools != tools_root:
        _raise(status)
    for root in (runtime, tools):
        try:
            root.relative_to(invocation)
        except ValueError:
            _raise(status)
    if python != runtime / "bin/python3.12":
        _raise(status)
    target = tools / "bin/python3"
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    except OSError:
        _raise(status)
    else:
        _raise(status)
    _write_materialized_file(
        tools,
        "bin/python3",
        RUNTIME_PYTHON_FACADE_SOURCE,
        "100755",
        status,
    )
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if resolved != target:
        _raise(status)
    return resolved


def materialize_runtime_dirname_facade(
    invocation_root: Path, runtime_root: Path, tools_root: Path
) -> Path:
    status = "RUNTIME_DIRNAME_FACADE_INVALID"
    try:
        invocation = invocation_root.resolve(strict=True)
        runtime = runtime_root.resolve(strict=True)
        tools = tools_root.resolve(strict=True)
        python = (runtime / "bin/python3.12").resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if invocation != invocation_root or runtime != runtime_root or tools != tools_root:
        _raise(status)
    for root in (runtime, tools):
        try:
            root.relative_to(invocation)
        except ValueError:
            _raise(status)
    if python != runtime / "bin/python3.12":
        _raise(status)
    target = tools / "bin/dirname"
    try:
        os.lstat(target)
    except FileNotFoundError:
        pass
    except OSError:
        _raise(status)
    else:
        _raise(status)
    _write_materialized_file(
        tools,
        "bin/dirname",
        RUNTIME_DIRNAME_FACADE_SOURCE,
        "100755",
        status,
    )
    try:
        resolved = target.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise(status)
    if resolved != target:
        _raise(status)
    return resolved


def build_gate_executable_allowlist(
    *, snapshot: Path, runtime: Path, tools: Path, wrapper: Path
) -> list[str]:
    values = {
        "/bin/bash",
        "/bin/sh",
        str(runtime / "bin/python3.12"),
        str(wrapper),
        str(snapshot / "scripts/pre-commit-check.sh"),
        *(str(snapshot / path) for path in FACADE_PATHS if path.endswith(("/python", "/python3", "/python3.12"))),
        *(str(tools / "bin" / name) for name in REQUIRED_TOOL_NAMES),
        str(tools / "bin/python3"),
        str(tools / "bin/dirname"),
    }
    return sorted(values)


def _runtime_command(
    argv: Sequence[str], *, runtime: Path, status: str
) -> bytes:
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(runtime.parent / "hermetic-home-unavailable"),
        "CODEX_HOME": str(runtime.parent / "hermetic-codex-home-unavailable"),
        "TMPDIR": str(runtime.parent),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    try:
        result = subprocess.run(
            list(argv),
            cwd=runtime,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        _raise(status)
    if result.returncode != 0 or len(result.stdout) > 4 * 1024 * 1024:
        _raise(status)
    return result.stdout


def _resolve_runtime_load(
    load: str, *, executable: Path, runtime: Path, rpaths: Sequence[str]
) -> Path | None:
    if load.startswith("/System/Library/") or load.startswith("/usr/lib/"):
        return None

    def expand(value: str) -> Path:
        expanded = value.replace("@loader_path", str(executable.parent)).replace(
            "@executable_path", str(executable.parent)
        )
        return Path(expanded)

    candidates: list[Path] = []
    if load.startswith("@rpath/"):
        suffix = load.removeprefix("@rpath/")
        candidates.extend(expand(rpath) / suffix for rpath in rpaths)
    elif load.startswith("@loader_path/") or load.startswith("@executable_path/"):
        candidates.append(expand(load))
    else:
        candidates.append(Path(load))
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(runtime)
        except (OSError, RuntimeError, ValueError):
            continue
        return resolved
    _raise("UNSUPPORTED_HERMETIC_RUNTIME")


def capture_hermetic_runtime_identity(runtime_root: Path) -> dict[str, object]:
    try:
        runtime = runtime_root.resolve(strict=True)
        executable = (runtime / "bin/python3.12").resolve(strict=True)
        metadata = os.lstat(executable)
    except (OSError, RuntimeError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if (
        runtime != runtime_root
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    try:
        executable_bytes = executable.read_bytes()
    except OSError:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if not _is_macho(executable_bytes):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")

    file_output = _runtime_command(
        ("/usr/bin/file", "-b", str(executable)),
        runtime=runtime,
        status="UNSUPPORTED_HERMETIC_RUNTIME",
    ).decode("utf-8", "strict").strip()
    if "Mach-O" not in file_output:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    slices_output = _runtime_command(
        ("/usr/bin/lipo", "-archs", str(executable)),
        runtime=runtime,
        status="UNSUPPORTED_HERMETIC_RUNTIME",
    ).decode("ascii", "strict").strip()
    slices = tuple(part for part in slices_output.split() if part)
    if not slices or any(part not in {"arm64", "x86_64"} for part in slices):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")

    loads_output = _runtime_command(
        ("/usr/bin/otool", "-L", str(executable)),
        runtime=runtime,
        status="UNSUPPORTED_HERMETIC_RUNTIME",
    ).decode("utf-8", "strict")
    loads = tuple(
        line.strip().split(" (", 1)[0]
        for line in loads_output.splitlines()[1:]
        if line.strip()
    )
    if not loads:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    load_commands_output = _runtime_command(
        ("/usr/bin/otool", "-l", str(executable)),
        runtime=runtime,
        status="UNSUPPORTED_HERMETIC_RUNTIME",
    ).decode("utf-8", "strict")
    rpaths: list[str] = []
    lines = load_commands_output.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_RPATH":
            continue
        for candidate in lines[index + 1 : index + 5]:
            stripped = candidate.strip()
            if stripped.startswith("path "):
                rpaths.append(stripped[5:].split(" (offset", 1)[0])
                break
    closure: list[dict[str, object]] = []
    for load in loads:
        resolved = _resolve_runtime_load(
            load, executable=executable, runtime=runtime, rpaths=rpaths
        )
        if resolved is None:
            closure.append({"load": load, "kind": "system"})
            continue
        try:
            content = resolved.read_bytes()
        except OSError:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        closure.append(
            {
                "load": load,
                "kind": "runtime",
                "path": str(resolved.relative_to(runtime)),
                "sha256": sha256_bytes(content),
            }
        )

    probe_source = (
        "import json,os,platform,sys\n"
        "paths=[]\n"
        "for value in sys.path:\n"
        " p=os.path.realpath(value or os.getcwd())\n"
        " paths.append(p)\n"
        "modules={}\n"
        "for name,module in sorted(sys.modules.items()):\n"
        " value=getattr(module,'__file__',None)\n"
        " if value: modules[name]=os.path.realpath(value)\n"
        "print(json.dumps({'version':platform.python_version(),"
        "'architecture':platform.machine(),'executable':os.path.realpath(sys.executable),"
        "'prefix':os.path.realpath(sys.prefix),'base_prefix':os.path.realpath(sys.base_prefix),"
        "'sys_path':paths,'modules':modules},sort_keys=True,separators=(',',':')))\n"
    )
    probe_raw = _runtime_command(
        (str(executable), "-I", "-c", probe_source),
        runtime=runtime,
        status="UNSUPPORTED_HERMETIC_RUNTIME",
    )
    probe = decode_canonical_json_bytes(
        probe_raw.rstrip(b"\n"),
        status="UNSUPPORTED_HERMETIC_RUNTIME",
        max_bytes=4 * 1024 * 1024,
    )
    if not isinstance(probe, dict):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    version = probe.get("version")
    architecture = probe.get("architecture")
    if (
        not isinstance(version, str)
        or not version.startswith("3.12.")
        or architecture not in slices
        or architecture != "arm64"
        or probe.get("executable") != str(executable)
    ):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    contained_values = [probe.get("prefix"), probe.get("base_prefix")]
    sys_path = probe.get("sys_path")
    modules = probe.get("modules")
    if not isinstance(sys_path, list) or not isinstance(modules, dict):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    contained_values.extend(sys_path)
    contained_values.extend(modules.values())
    for value in contained_values:
        if not isinstance(value, str):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        try:
            Path(value).resolve(strict=False).relative_to(runtime)
        except (OSError, RuntimeError, ValueError):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    normalized_probe = dict(probe)
    for field in ("executable", "prefix", "base_prefix"):
        normalized_probe[field] = str(Path(probe[field]).relative_to(runtime)) or "."
    normalized_probe["sys_path"] = [
        str(Path(value).relative_to(runtime)) or "." for value in sys_path
    ]
    normalized_probe["modules"] = {
        name: str(Path(value).relative_to(runtime))
        for name, value in modules.items()
    }
    return {
        "schema": "samvil.full-gate-python-identity.v1",
        "major_minor": "3.12",
        "version": version,
        "architecture": architecture,
        "slices": list(slices),
        "executable_sha256": sha256_bytes(executable_bytes),
        "file_description": file_output,
        "load_commands": list(loads),
        "rpaths": rpaths,
        "load_closure": closure,
        "runtime_probe": normalized_probe,
    }


def validate_hermetic_runtime(
    runtime: Path, expected_identity: Mapping[str, object]
) -> dict[str, object]:
    observed = capture_hermetic_runtime_identity(runtime)
    if canonical_json_bytes(observed) != canonical_json_bytes(dict(expected_identity)):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return observed


def validate_tool_closure(tools_root: Path, scratch_root: Path) -> dict[str, object]:
    try:
        tools = tools_root.resolve(strict=True)
        scratch = scratch_root.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if tools != tools_root or scratch != scratch_root:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    for forbidden in (tools / "bin/sandbox-exec", tools / "bin/codesign"):
        try:
            os.lstat(forbidden)
        except FileNotFoundError:
            continue
        except OSError:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    evidence: dict[str, dict[str, object]] = {}
    environment = {
        "PATH": f"{tools / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": str(scratch / "home-unavailable"),
        "CODEX_HOME": str(scratch / "codex-home-unavailable"),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }

    def run(argv: Sequence[str], *, stdin: bytes = b"") -> bytes:
        try:
            result = subprocess.run(
                list(argv),
                cwd=scratch,
                env=environment,
                input=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        return result.stdout

    for name in REQUIRED_TOOL_NAMES:
        path = tools / "bin" / name
        try:
            metadata = os.lstat(path)
            content = path.read_bytes()
        except OSError:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o111 == 0
            or not _is_macho(content)
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        loads = _runtime_command(
            ("/usr/bin/otool", "-L", str(path)),
            runtime=tools,
            status="UNSUPPORTED_HERMETIC_RUNTIME",
        ).decode("utf-8", "strict")
        load_paths = tuple(
            line.strip().split(" (", 1)[0]
            for line in loads.splitlines()[1:]
            if line.strip()
        )
        if not load_paths or any(
            not (load.startswith("/System/Library/") or load.startswith("/usr/lib/"))
            for load in load_paths
        ):
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
        evidence[name] = {
            "classification": "mach-o",
            "sha256": sha256_bytes(content),
            "loads": list(load_paths),
        }

    token = b"samvil-tool-probe\n"
    sample = scratch / "sample.txt"
    sample.write_bytes(token)
    run((str(tools / "bin/env"), "-i", "/usr/bin/true"))
    if b"git version" not in run((str(tools / "bin/git"), "--version")):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if b"bash" not in run((str(tools / "bin/bash"), "--version")).lower():
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if run((str(tools / "bin/sh"), "-c", "printf samvil")) != b"samvil":
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    created = run((str(tools / "bin/mktemp"), "-d", str(scratch / "mktemp.XXXXXX"))).strip()
    try:
        os.rmdir(created.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    directory = scratch / "mkdir-probe"
    run((str(tools / "bin/mkdir"), str(directory)))
    run((str(tools / "bin/chmod"), "700", str(directory)))
    if run((str(tools / "bin/grep"), "samvil", str(sample))) != token:
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if b"samvil" not in run((str(tools / "bin/xargs"), "/bin/echo"), stdin=b"samvil\n"):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    for name, argv in (
        ("sed", ("-n", "1p", str(sample))),
        ("tail", ("-n", "1", str(sample))),
        ("head", ("-n", "1", str(sample))),
        ("cat", (str(sample),)),
    ):
        if run((str(tools / f"bin/{name}"), *argv)) != token:
            _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    if b"sample.txt" not in run((str(tools / "bin/find"), str(scratch), "-name", "sample.txt")):
        _raise("UNSUPPORTED_HERMETIC_RUNTIME")
    return {
        "schema": "samvil.full-gate-tool-evidence.v1",
        "tools": evidence,
    }


def materialize_facade(raw: bytes, snapshot: Path, invocation_root: Path) -> str:
    try:
        invocation = invocation_root.resolve(strict=True)
        snapshot_root = snapshot.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("FACADE_MANIFEST_INVALID")
    if invocation != invocation_root or snapshot_root != snapshot:
        _raise("FACADE_MANIFEST_INVALID")
    try:
        snapshot_root.relative_to(invocation)
    except ValueError:
        _raise("FACADE_MANIFEST_INVALID")
    decoded = decode_canonical_json_bytes(
        raw, status="FACADE_MANIFEST_INVALID", max_bytes=1024 * 1024
    )
    manifest = _exact_object(
        decoded,
        frozenset({"schema", "entries"}),
        "FACADE_MANIFEST_INVALID",
    )
    if (
        manifest["schema"] != "samvil.full-gate-facade.v1"
        or not isinstance(manifest["entries"], list)
        or len(manifest["entries"]) != len(FACADE_PATHS)
    ):
        _raise("FACADE_MANIFEST_INVALID")
    expected_content = {
        path: FACADE_PYTHON_WRAPPER for path in FACADE_PATHS[:3]
    }
    expected_content[FACADE_PATHS[3]] = FACADE_PYVENV_CONFIG
    observed: list[dict[str, object]] = []
    for raw_entry, expected_path in zip(manifest["entries"], FACADE_PATHS):
        entry = _exact_object(
            raw_entry,
            frozenset({"path", "mode", "content_base64", "sha256"}),
            "FACADE_MANIFEST_INVALID",
        )
        if entry["path"] != expected_path:
            _raise("FACADE_MANIFEST_INVALID")
        mode = "100755" if expected_path != FACADE_PATHS[3] else "100644"
        if entry["mode"] != mode or not isinstance(entry["content_base64"], str):
            _raise("FACADE_MANIFEST_INVALID")
        try:
            content = base64.b64decode(entry["content_base64"], validate=True)
        except (TypeError, ValueError):
            _raise("FACADE_MANIFEST_INVALID")
        if (
            content != expected_content[expected_path]
            or base64.b64encode(content).decode("ascii") != entry["content_base64"]
            or sha256_bytes(content)
            != _hex64(entry["sha256"], "FACADE_MANIFEST_INVALID")
        ):
            _raise("FACADE_MANIFEST_INVALID")
        _write_materialized_file(
            snapshot_root, expected_path, content, mode, "FACADE_MATERIALIZATION_FAILED"
        )
        observed.append(
            {
                "path": expected_path,
                "mode": mode,
                "sha256": sha256_bytes(content),
            }
        )
    return sha256_bytes(canonical_json_bytes(observed))


def _remove_invocation_tree(root: Path, status: str) -> None:
    """Remove one invocation-owned tree without following directory symlinks."""

    try:
        metadata = os.lstat(root)
    except FileNotFoundError:
        return
    except OSError:
        _raise(status)
    if not stat.S_ISDIR(metadata.st_mode):
        try:
            os.unlink(root)
        except OSError:
            _raise(status)
        return
    try:
        with os.scandir(root) as entries:
            children = list(entries)
        for entry in children:
            child = Path(entry.path)
            child_metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(child_metadata.st_mode):
                try:
                    os.chmod(child, 0o700, follow_symlinks=False)
                except OSError:
                    pass
                _remove_invocation_tree(child, status)
            else:
                os.unlink(child)
        os.chmod(root, 0o700)
        os.rmdir(root)
    except FullGateError:
        raise
    except OSError:
        _raise(status)


def _profile_literal(path: Path | str) -> bytes:
    value = str(path)
    if "\x00" in value or "\n" in value or "\r" in value:
        _raise("PROFILE_RENDER_INVALID")
    return json.dumps(value, ensure_ascii=True).encode("ascii")


def render_loopback_profile(
    invocation_root: Path,
    snapshot: Path,
    runtime: Path,
    tools: Path,
    *,
    protected_roots: tuple[Path, Path],
    executable_allowlist: Sequence[Path | str],
    writable_roots: Sequence[Path] | None = None,
) -> tuple[bytes, str, str]:
    status = "PROFILE_EXEC_ALLOWLIST_INVALID"
    if isinstance(executable_allowlist, (str, bytes)) or not isinstance(
        executable_allowlist, Sequence
    ):
        _raise(status)
    executable_values: list[str] = []
    for raw in executable_allowlist:
        if isinstance(raw, Path):
            value = str(raw)
        elif type(raw) is str:
            value = raw
        else:
            _raise(status)
        parts = value.split("/")
        if (
            not value.startswith("/")
            or value.startswith("//")
            or value.endswith("/")
            or any(part in {"", ".", ".."} for part in parts[1:])
            or any(character in value for character in ("\x00", "\n", "\r", "\\"))
            or any(character in value for character in ("*", "?", "[", "]"))
        ):
            _raise(status)
        executable_values.append(value)
    if (
        not executable_values
        or executable_values != sorted(executable_values)
        or len(set(executable_values)) != len(executable_values)
    ):
        _raise(status)
    executables = tuple(executable_values)

    try:
        invocation = invocation_root.resolve(strict=True)
        snapshot_root = snapshot.resolve(strict=True)
        runtime_root = runtime.resolve(strict=True)
        tools_root = tools.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("PROFILE_RENDER_INVALID")
    if any(
        path != original
        for path, original in (
            (invocation, invocation_root),
            (snapshot_root, snapshot),
            (runtime_root, runtime),
            (tools_root, tools),
        )
    ):
        _raise("PROFILE_RENDER_INVALID")
    for child in (snapshot_root, runtime_root, tools_root):
        try:
            child.relative_to(invocation)
        except ValueError:
            _raise("PROFILE_RENDER_INVALID")
    if len(protected_roots) != 2:
        _raise("PROFILE_RENDER_INVALID")
    for protected in protected_roots:
        if not protected.is_absolute() or any(part in {".", ".."} for part in protected.parts):
            _raise("PROFILE_RENDER_INVALID")
    if writable_roots is None:
        writable = (invocation,)
    else:
        writable_list: list[Path] = []
        for raw in writable_roots:
            try:
                resolved = raw.resolve(strict=True)
                resolved.relative_to(invocation)
            except (OSError, RuntimeError, ValueError):
                _raise("PROFILE_RENDER_INVALID")
            if resolved != raw:
                _raise("PROFILE_RENDER_INVALID")
            writable_list.append(resolved)
        writable = tuple(sorted(set(writable_list), key=str))
    if not writable:
        _raise("PROFILE_RENDER_INVALID")

    def render(
        values: Mapping[str, Path | str],
        executable_paths: Sequence[Path | str],
    ) -> bytes:
        protected_one = _profile_literal(values["protected_one"])
        protected_two = _profile_literal(values["protected_two"])
        invocation_value = _profile_literal(values["invocation"])
        snapshot_value = _profile_literal(values["snapshot"])
        runtime_value = _profile_literal(values["runtime"])
        tools_value = _profile_literal(values["tools"])
        process_exec = (
            b"(allow process-exec (require-any "
            + b" ".join(
                b"(literal " + _profile_literal(path) + b")"
                for path in executable_paths
            )
            + b"))"
        )
        lines = (
            b"(version 1)",
            b'(import "system.sb")',
            b"(deny default)",
            b"(deny network*)",
            b"(deny system-socket)",
            b"(deny file-read-metadata file-test-existence (require-any (literal "
            + protected_one
            + b") (subpath "
            + protected_one
            + b") (literal "
            + protected_two
            + b") (subpath "
            + protected_two
            + b")))",
            b"(deny file-read* (require-any (literal "
            + protected_one
            + b") (subpath "
            + protected_one
            + b") (literal "
            + protected_two
            + b") (subpath "
            + protected_two
            + b")))",
            b"(deny file-write* (require-any (literal "
            + protected_one
            + b") (subpath "
            + protected_one
            + b") (literal "
            + protected_two
            + b") (subpath "
            + protected_two
            + b")))",
            b"(allow file-read-metadata file-test-existence)",
            b"(allow process-fork)",
            process_exec,
            b"(allow signal (target children))",
            b'(allow file-read* (literal "/dev/null") (subpath "/System") '
            b'(subpath "/usr") (subpath "/bin") (subpath "/sbin") '
            b'(subpath "/Library/Apple") '
            b'(subpath "/Library/Developer/CommandLineTools") '
            b'(subpath "/private/var/db/dyld") (subpath '
            + invocation_value
            + b") (subpath "
            + snapshot_value
            + b") (subpath "
            + runtime_value
            + b") (subpath "
            + tools_value
            + b"))",
            *(
                b"(allow file-write* (subpath " + _profile_literal(path) + b"))"
                for path in writable
            ),
            *(
                b"(allow file-write* (literal "
                + _profile_literal(log_path)
                + b"))"
                for log_path in FIXED_LOG_PATHS
            ),
            b'(allow network-inbound (local tcp "localhost:*"))',
            b'(allow network-outbound (remote tcp "localhost:*"))',
        )
        return b"\n".join(lines) + b"\n"

    rendered = render(
        {
            "protected_one": protected_roots[0],
            "protected_two": protected_roots[1],
            "invocation": invocation,
            "snapshot": snapshot_root,
            "runtime": runtime_root,
            "tools": tools_root,
        },
        executables,
    )
    source_writable = writable
    writable = tuple(f"<WRITABLE_ROOT_{index}>" for index, _path in enumerate(source_writable))
    source_roots = (
        (str(invocation), "<INVOCATION_ROOT>"),
        (str(snapshot_root), "<SNAPSHOT_ROOT>"),
        (str(runtime_root), "<RUNTIME_ROOT>"),
        (str(tools_root), "<TOOLS_ROOT>"),
    )
    source_executables: list[str] = []
    for executable in executables:
        source_value = executable
        for actual, placeholder in source_roots:
            if executable == actual or executable.startswith(actual + "/"):
                source_value = placeholder + executable[len(actual) :]
                break
        source_executables.append(source_value)
    source = render(
        {
            "protected_one": "<PROTECTED_HOME>",
            "protected_two": "<PROTECTED_CODEX_HOME>",
            "invocation": "<INVOCATION_ROOT>",
            "snapshot": "<SNAPSHOT_ROOT>",
            "runtime": "<RUNTIME_ROOT>",
            "tools": "<TOOLS_ROOT>",
        },
        source_executables,
    )
    writable = source_writable
    return rendered, sha256_bytes(source), sha256_bytes(rendered)


def build_hermetic_environment(
    invocation_root: Path,
    runtime: Path,
    tools: Path,
    *,
    source_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    del source_environment
    try:
        invocation = invocation_root.resolve(strict=True)
        runtime_root = runtime.resolve(strict=True)
        tools_root = tools.resolve(strict=True)
    except (OSError, RuntimeError):
        _raise("HERMETIC_ENVIRONMENT_INVALID")
    if (
        invocation != invocation_root
        or runtime_root != runtime
        or tools_root != tools
    ):
        _raise("HERMETIC_ENVIRONMENT_INVALID")
    for child in (runtime_root, tools_root):
        try:
            child.relative_to(invocation)
        except ValueError:
            _raise("HERMETIC_ENVIRONMENT_INVALID")
    directories = {
        "HOME": "home",
        "CODEX_HOME": "codex-home",
        "CLAUDE_CONFIG_DIR": "claude-config",
        "GNUPGHOME": "gnupg",
        "TMPDIR": "tmp",
        "XDG_CACHE_HOME": "xdg/cache",
        "XDG_CONFIG_HOME": "xdg/config",
        "XDG_DATA_HOME": "xdg/data",
        "XDG_STATE_HOME": "xdg/state",
    }
    environment: dict[str, str] = {}
    for key, relative in directories.items():
        directory = _safe_directory(invocation, Path(relative), "HERMETIC_ENVIRONMENT_INVALID")
        environment[key] = str(directory)
    _safe_directory(invocation, Path("config"), "HERMETIC_ENVIRONMENT_INVALID")
    git_config = invocation / "config/gitconfig"
    pip_config = invocation / "config/pip.conf"
    _write_materialized_file(
        invocation,
        "config/gitconfig",
        GIT_CONFIG_BYTES,
        "100644",
        "HERMETIC_ENVIRONMENT_INVALID",
    )
    _write_materialized_file(
        invocation,
        "config/pip.conf",
        PIP_CONFIG_BYTES,
        "100644",
        "HERMETIC_ENVIRONMENT_INVALID",
    )
    environment.update(
        {
            "PATH": ":".join(
                (
                    str(tools_root / "bin"),
                    str(runtime_root / "bin"),
                    "/usr/bin",
                    "/bin",
                    "/usr/sbin",
                    "/sbin",
                )
            ),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "GIT_CONFIG_GLOBAL": str(git_config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "/usr/bin/false",
            "SSH_ASKPASS": "/usr/bin/false",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PIP_CONFIG_FILE": str(pip_config),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "__CF_USER_TEXT_ENCODING": "0x1F5:0x0:0x0",
        }
    )
    if set(environment) != set(HERMETIC_ENVIRONMENT_KEYS):
        _raise("HERMETIC_ENVIRONMENT_INVALID")
    return dict(sorted(environment.items()))


def _positive_timeout(raw: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        _raise("INVALID_TIMEOUT")
    if not math.isfinite(value) or value <= 0:
        _raise("INVALID_TIMEOUT")
    return value


def parse_exact_argv(argv: Sequence[str]) -> FullGateArguments:
    """Accept only the two documented fixed-position grammars."""

    original_flags = (
        "--manifest",
        "--nonce",
        "--timeout",
        "--receipt",
        "--denial-log",
    )
    postcommit_flags = (
        "--manifest",
        "--prior-receipt",
        "--nonce",
        "--timeout",
        "--receipt",
        "--denial-log",
    )
    if len(argv) == 10 and tuple(argv[0::2]) == original_flags:
        values = tuple(argv[1::2])
        prior_receipt = None
    elif len(argv) == 12 and tuple(argv[0::2]) == postcommit_flags:
        values = tuple(argv[1::2])
        prior_receipt = values[1]
        values = (values[0], *values[2:])
    else:
        _raise("FULL_GATE_USAGE")

    manifest, nonce, timeout, receipt, denial_log = values
    if not HEX64.fullmatch(nonce):
        _raise("INVALID_NONCE")
    if any(not Path(raw).is_absolute() for raw in (manifest, receipt, denial_log)):
        _raise("FULL_GATE_USAGE")
    if prior_receipt is not None and not Path(prior_receipt).is_absolute():
        _raise("FULL_GATE_USAGE")
    return FullGateArguments(
        manifest=manifest,
        prior_receipt=prior_receipt,
        nonce=nonce,
        timeout=_positive_timeout(timeout),
        receipt=receipt,
        denial_log=denial_log,
    )


def _emit_terminal(status: str) -> None:
    payload = json.dumps(
        {"schema": "samvil.full-gate-terminal.v1", "status": status},
        sort_keys=True,
        separators=(",", ":"),
    )
    print(payload, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parse_exact_argv(tuple(sys.argv[1:] if argv is None else argv))
        _reject_environment_authority(os.environ)
        entrypoint = Path(__file__)
        try:
            canonical_entrypoint = entrypoint.resolve(strict=True)
        except (OSError, RuntimeError):
            _raise("CONTROL_ENTRYPOINT_INVALID")
        if str(entrypoint) != str(canonical_entrypoint):
            _raise("CONTROL_ENTRYPOINT_INVALID")
        control_root = canonical_entrypoint.parents[2]
        return execute_full_gate(
            arguments,
            source_environment=os.environ,
            control_root=control_root,
        )
    except FullGateError as exc:
        _emit_terminal(exc.status)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
