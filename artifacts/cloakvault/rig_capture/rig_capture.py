#!/usr/bin/env python3
"""Hash-bound, capture-only HOST bench scaffold.

This module deliberately has no image, OCR, decode, network or corpus-specific
dependency.  It exposes two closed adapters: an in-process public mock and one
fixed rpicam-still command shape shared by ZeroCam bring-up and Camera Module 3
preflight.  Callers cannot supply command arguments, input paths or plug-ins.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable


CONTRACT_VERSION = "QK-RIG-CAPTURE-G0-V1"
MANIFEST_VERSION = "QK-RIG-CAPTURE-MANIFEST-G0-V1"
SAFE_IDENTIFIER = re.compile(r"[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\Z")
SAFE_EXTENSION = re.compile(r"[a-z0-9]+\Z")
LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
MOCK_ADAPTER = "PUBLIC-MOCK-CAPTURE-V1"
RPICAM_ADAPTER = "RPICAM-STILL-CAPTURE-V1"
MOCK_ADAPTER_KEYS = frozenset({"interface", "working_directory"})
RPICAM_ADAPTER_KEYS = frozenset(
    {"interface", "working_directory", "executable_path", "executable_sha256"}
)
RPICAM_SETTINGS_KEYS = frozenset(
    {
        "output_extension",
        "camera_index",
        "width_px",
        "height_px",
        "jpeg_quality",
        "capture_timeout_ms",
        "shutter_us",
        "analogue_gain",
        "awb_gain_red",
        "awb_gain_blue",
        "lens_position",
        "rotation_degrees",
        "horizontal_flip",
        "vertical_flip",
        "denoise_mode",
    }
)
MOCK_SETTINGS_KEYS = frozenset({"output_extension", "producer_behavior"})
RPICAM_DENOISE_MODES = frozenset({"auto", "off", "cdn_off", "cdn_fast", "cdn_hq"})
GEOMETRY_KEYS = frozenset(
    {
        "jig_revision",
        "camera_to_page_distance_mm",
        "page_fill_percent",
        "page_orientation",
        "camera_mount_definition",
        "page_plane_definition",
        "fiducial_specification",
        "scale_bar_length_mm",
        "scale_bar_placement",
        "lighting_geometry",
    }
)
ROOT_KEYS = frozenset(
    {
        "contract_version",
        "purpose",
        "corpus",
        "session_id",
        "source_commit",
        "camera_class",
        "authorization",
        "software",
        "settings",
        "geometry",
        "adapter",
        "controls",
        "captures",
    }
)


class RigCaptureError(Exception):
    """A stable fail-closed category with a non-payload diagnostic."""

    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def _reject(category: str, message: str) -> None:
    raise RigCaptureError(category, message)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _reject("MalformedConfig", f"duplicate configuration field: {key}")
        value[key] = item
    return value


def _exact_keys(value: dict[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        _reject("MalformedConfig", f"{label} keys differ; missing={missing}, extra={extra}")


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _reject("MalformedConfig", f"{label} must be a nonempty string")
    return value


def _safe_identifier(value: Any, label: str) -> str:
    text = _nonempty_string(value, label)
    if SAFE_IDENTIFIER.fullmatch(text) is None:
        _reject("UnsafeIdentifier", f"{label} is not filename-safe uppercase ASCII")
    return text


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        _reject("MalformedConfig", f"{label} must be a positive integer")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject("MalformedConfig", f"{label} must be a nonnegative integer")
    return value


def _positive_number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject("MalformedConfig", f"{label} must be a positive finite number")
    if not math.isfinite(value) or value <= 0:
        _reject("MalformedConfig", f"{label} must be a positive finite number")
    return value


def _nonnegative_number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject("MalformedConfig", f"{label} must be a nonnegative finite number")
    if not math.isfinite(value) or value < 0:
        _reject("MalformedConfig", f"{label} must be a nonnegative finite number")
    return value


def _lower_sha256(value: Any, label: str) -> str:
    text = _nonempty_string(value, label)
    if LOWER_HEX_64.fullmatch(text) is None:
        _reject("MalformedDigest", f"{label} must be canonical lowercase SHA-256 hex")
    return text


def _regular_nonsymlink(path: Path, label: str, executable: bool = False) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        _reject("MissingBoundFile", f"{label} is unavailable: {error.strerror}")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _reject("UnsafeBoundFile", f"{label} must be a regular nonsymlink file")
    if executable and not os.access(path, os.X_OK):
        _reject("UnsafeBoundFile", f"{label} is not executable")


def _directory_nonsymlink(path: Path, label: str) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        _reject("MissingBoundDirectory", f"{label} is unavailable: {error.strerror}")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _reject("UnsafeBoundDirectory", f"{label} must be a directory and not a symlink")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(65536), b""):
                digest.update(block)
    except OSError as error:
        _reject("BoundFileReadFailed", f"cannot hash bound file: {error.strerror}")
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        _reject("MalformedConfig", f"value is not canonical JSON: {error}")
    return (encoded + "\n").encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _nonempty_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        _reject("MalformedConfig", f"{label} must be a nonempty object")
    for key in value:
        _nonempty_string(key, f"{label} key")
    canonical_json_bytes(value)
    return value


def _validate_geometry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        _reject("MalformedConfig", "geometry must be an object")
    _exact_keys(value, GEOMETRY_KEYS, "geometry")
    for key, item in value.items():
        if isinstance(item, bool):
            _reject("MalformedConfig", f"geometry.{key} must be a string or finite number")
        if isinstance(item, str):
            if not item:
                _reject("MalformedConfig", f"geometry.{key} must not be empty")
        elif isinstance(item, (int, float)):
            if not math.isfinite(item):
                _reject("MalformedConfig", f"geometry.{key} must be finite")
        else:
            _reject("MalformedConfig", f"geometry.{key} must be a string or finite number")
    return value


def _absolute_path(value: Any, label: str) -> Path:
    text = _nonempty_string(value, label)
    path = Path(text)
    if not path.is_absolute():
        _reject("UnsafeBoundPath", f"{label} must be absolute")
    return path


def _verify_hash(path: Path, expected: str, label: str, executable: bool = False) -> str:
    _regular_nonsymlink(path, label, executable=executable)
    observed = sha256_file(path)
    if observed != expected:
        _reject("BoundFileHashMismatch", f"{label} SHA-256 does not match configuration")
    return observed


def _validate_adapter(value: Any, purpose: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _reject("MalformedConfig", "adapter must be an object")
    interface = value.get("interface")
    expected_interface = MOCK_ADAPTER if purpose == "MOCK" else RPICAM_ADAPTER
    if interface != expected_interface:
        _reject(
            "UnsupportedAdapter",
            f"{purpose} requires the exact {expected_interface} interface",
        )
    expected_keys = MOCK_ADAPTER_KEYS if purpose == "MOCK" else RPICAM_ADAPTER_KEYS
    _exact_keys(value, expected_keys, "adapter")

    working_directory = _absolute_path(
        value["working_directory"], "adapter.working_directory"
    )
    _directory_nonsymlink(working_directory, "adapter.working_directory")
    if purpose == "PREFLIGHT":
        executable = _absolute_path(value["executable_path"], "adapter.executable_path")
        if executable.name != "rpicam-still":
            _reject(
                "UnsupportedCaptureExecutable",
                "RPICAM adapter executable basename must be exact rpicam-still",
            )
        executable_hash = _lower_sha256(
            value["executable_sha256"], "adapter.executable_sha256"
        )
        _verify_hash(
            executable,
            executable_hash,
            "adapter.executable_path",
            executable=True,
        )
    return value


def _validate_settings(value: Any, purpose: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _reject("MalformedConfig", "settings must be an object")
    expected = MOCK_SETTINGS_KEYS if purpose == "MOCK" else RPICAM_SETTINGS_KEYS
    _exact_keys(value, expected, "settings")

    if purpose == "MOCK":
        if value["output_extension"] != "mock":
            _reject("MalformedConfig", "MOCK output_extension must be exact mock")
        if value["producer_behavior"] not in {
            "WRITE-PUBLIC-MOCK",
            "EMPTY",
            "MISSING",
            "FAIL",
        }:
            _reject("MalformedConfig", "unknown public mock producer behavior")
        return value

    if value["output_extension"] != "jpg":
        _reject("MalformedConfig", "PREFLIGHT output_extension must be exact jpg")
    _nonnegative_integer(value["camera_index"], "settings.camera_index")
    _positive_integer(value["width_px"], "settings.width_px")
    _positive_integer(value["height_px"], "settings.height_px")
    quality = _positive_integer(value["jpeg_quality"], "settings.jpeg_quality")
    if quality > 100:
        _reject("MalformedConfig", "settings.jpeg_quality must be at most 100")
    _positive_integer(value["capture_timeout_ms"], "settings.capture_timeout_ms")
    _positive_integer(value["shutter_us"], "settings.shutter_us")
    for key in ("analogue_gain", "awb_gain_red", "awb_gain_blue"):
        _positive_number(value[key], f"settings.{key}")
    _nonnegative_number(value["lens_position"], "settings.lens_position")
    if value["rotation_degrees"] not in (0, 180):
        _reject("MalformedConfig", "settings.rotation_degrees must be 0 or 180")
    for key in ("horizontal_flip", "vertical_flip"):
        if not isinstance(value[key], bool):
            _reject("MalformedConfig", f"settings.{key} must be boolean")
    if value["denoise_mode"] not in RPICAM_DENOISE_MODES:
        _reject("MalformedConfig", "settings.denoise_mode is unsupported")
    return value


def _validate_captures(value: Any, session_id: str, extension: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _reject("MalformedConfig", "captures must be a nonempty array")
    seen_ids: set[str] = set()
    seen_sequences: set[int] = set()
    seen_names: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, record in enumerate(value):
        if not isinstance(record, dict):
            _reject("MalformedConfig", f"captures[{index}] must be an object")
        _exact_keys(
            record,
            frozenset({"capture_id", "page_id", "attempt", "sequence"}),
            f"captures[{index}]",
        )
        capture_id = _safe_identifier(record["capture_id"], f"captures[{index}].capture_id")
        page_id = _safe_identifier(record["page_id"], f"captures[{index}].page_id")
        attempt = _positive_integer(record["attempt"], f"captures[{index}].attempt")
        sequence = _nonnegative_integer(record["sequence"], f"captures[{index}].sequence")
        if capture_id in seen_ids:
            _reject("DuplicateCapture", "capture_id values must be unique")
        if sequence in seen_sequences:
            _reject("DuplicateCapture", "sequence values must be unique")
        filename = output_filename(
            session_id, sequence, capture_id, page_id, attempt, extension
        )
        if filename in seen_names:
            _reject("DuplicateCapture", "deterministic output names must be unique")
        seen_ids.add(capture_id)
        seen_sequences.add(sequence)
        seen_names.add(filename)
        validated.append(
            {
                "capture_id": capture_id,
                "page_id": page_id,
                "attempt": attempt,
                "sequence": sequence,
                "filename": filename,
            }
        )
    return validated


def output_filename(
    session_id: str,
    sequence: int,
    capture_id: str,
    page_id: str,
    attempt: int,
    extension: str,
) -> str:
    return (
        f"qk-rig-g0-v1__{session_id}__s{sequence}__{capture_id}__"
        f"{page_id}__a{attempt}.{extension}"
    )


def manifest_filename(session_id: str) -> str:
    return f"qk-rig-g0-v1__{session_id}__manifest.json"


def load_config(config_path: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    expected = _lower_sha256(expected_sha256, "expected configuration SHA-256")
    _regular_nonsymlink(config_path, "configuration")
    try:
        raw = config_path.read_bytes()
    except OSError as error:
        _reject("ConfigReadFailed", f"cannot read configuration: {error.strerror}")
    observed = hashlib.sha256(raw).hexdigest()
    if observed != expected:
        _reject("ConfigHashMismatch", "configuration SHA-256 does not match")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _reject("MalformedConfig", f"configuration is not UTF-8 JSON: {error}")
    if not isinstance(value, dict):
        _reject("MalformedConfig", "configuration root must be an object")
    validated = validate_config(value)
    return validated, observed


def validate_config(value: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(value, ROOT_KEYS, "root")
    if value["contract_version"] != CONTRACT_VERSION:
        _reject("UnsupportedContract", "contract_version is not supported")
    if value["purpose"] not in ("MOCK", "PREFLIGHT"):
        _reject("UnauthorizedPurpose", "purpose must be MOCK or PREFLIGHT")
    if value["corpus"] is not False:
        _reject("CorpusClosed", "this scaffold requires corpus=false")

    session_id = _safe_identifier(value["session_id"], "session_id")
    if value["purpose"] == "MOCK" and not session_id.startswith("MOCK-"):
        _reject("MockIdentity", "MOCK session_id must begin MOCK-")
    source_commit = _nonempty_string(value["source_commit"], "source_commit")
    if LOWER_HEX_40.fullmatch(source_commit) is None:
        _reject("MalformedConfig", "source_commit must be lowercase 40-hex")
    _safe_identifier(value["camera_class"], "camera_class")
    _nonempty_object(value["authorization"], "authorization")
    _nonempty_object(value["software"], "software")
    settings = _validate_settings(value["settings"], value["purpose"])
    extension = settings["output_extension"]
    if SAFE_EXTENSION.fullmatch(extension) is None:
        _reject("MalformedConfig", "settings.output_extension is not filename-safe")
    _validate_geometry(value["geometry"])
    _validate_adapter(value["adapter"], value["purpose"])

    controls = value["controls"]
    if not isinstance(controls, dict):
        _reject("MalformedConfig", "controls must be an object")
    _exact_keys(
        controls, frozenset({"timeout_seconds", "max_output_bytes"}), "controls"
    )
    _positive_integer(controls["timeout_seconds"], "controls.timeout_seconds")
    _positive_integer(controls["max_output_bytes"], "controls.max_output_bytes")
    captures = _validate_captures(value["captures"], session_id, extension)

    result = dict(value)
    result["captures"] = captures
    return result


def verify_capture_executable(config: dict[str, Any]) -> str | None:
    adapter = config["adapter"]
    if adapter["interface"] == MOCK_ADAPTER:
        return None
    executable = Path(adapter["executable_path"])
    if executable.name != "rpicam-still":
        _reject(
            "UnsupportedCaptureExecutable",
            "RPICAM adapter executable basename must be exact rpicam-still",
        )
    return _verify_hash(
        executable,
        adapter["executable_sha256"],
        "adapter.executable_path",
        executable=True,
    )


def _number_argument(value: int | float) -> str:
    return str(value)


def build_rpicam_command(config: dict[str, Any], output: Path) -> list[str]:
    """Construct the one closed, output-only camera invocation."""

    if config["adapter"]["interface"] != RPICAM_ADAPTER:
        _reject("UnsupportedAdapter", "rpicam command requested for another interface")
    settings = config["settings"]
    command = [
        config["adapter"]["executable_path"],
        "--nopreview",
        "--camera",
        str(settings["camera_index"]),
        "--width",
        str(settings["width_px"]),
        "--height",
        str(settings["height_px"]),
        "--quality",
        str(settings["jpeg_quality"]),
        "--timeout",
        f"{settings['capture_timeout_ms']}ms",
        "--shutter",
        f"{settings['shutter_us']}us",
        "--gain",
        _number_argument(settings["analogue_gain"]),
        "--awbgains",
        f"{_number_argument(settings['awb_gain_red'])},"
        f"{_number_argument(settings['awb_gain_blue'])}",
        "--lens-position",
        _number_argument(settings["lens_position"]),
        "--rotation",
        str(settings["rotation_degrees"]),
        "--denoise",
        settings["denoise_mode"],
        "--encoding",
        "jpg",
    ]
    if settings["horizontal_flip"]:
        command.append("--hflip")
    if settings["vertical_flip"]:
        command.append("--vflip")
    command.extend(["--output", str(output)])
    return command


def _write_public_mock(
    settings: dict[str, Any], capture: dict[str, Any], output: Path
) -> None:
    behavior = settings["producer_behavior"]
    if behavior == "FAIL":
        _reject("CaptureCommandFailed", "public mock producer returned 7")
    if behavior == "MISSING":
        return
    if behavior == "EMPTY":
        output.write_bytes(b"")
        return
    payload = (
        "QUIETKEY PUBLIC MOCK CAPTURE\n"
        f"capture_id={capture['capture_id']}\n"
        f"page_id={capture['page_id']}\n"
        f"attempt={capture['attempt']}\n"
        f"sequence={capture['sequence']}\n"
    ).encode("ascii")
    output.write_bytes(payload)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def run_capture_session(
    config: dict[str, Any],
    config_sha256: str,
    output_directory: Path,
    clock: Callable[[], str] = utc_now,
) -> Path:
    if not output_directory.is_absolute():
        _reject("UnsafeOutputPath", "output directory must be absolute")
    if output_directory.exists() or output_directory.is_symlink():
        _reject("OutputDirectoryExists", "output directory must not already exist")
    parent = output_directory.parent
    _directory_nonsymlink(parent, "output directory parent")
    try:
        output_directory.mkdir()
    except OSError as error:
        _reject("OutputDirectoryCreateFailed", f"cannot create output directory: {error.strerror}")

    adapter = config["adapter"]
    controls = config["controls"]
    executable_hash = verify_capture_executable(config)
    records: list[dict[str, Any]] = []
    for capture in config["captures"]:
        output = output_directory / capture["filename"]
        if output.exists() or output.is_symlink():
            _reject("OutputExists", "deterministic capture output already exists")
        started = clock()
        if adapter["interface"] == MOCK_ADAPTER:
            try:
                _write_public_mock(config["settings"], capture, output)
            except OSError as error:
                _reject("CaptureOutputWriteFailed", f"public mock write failed: {error.strerror}")
        else:
            command = build_rpicam_command(config, output)
            try:
                completed = subprocess.run(
                    command,
                    cwd=adapter["working_directory"],
                    env={},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    timeout=controls["timeout_seconds"],
                    check=False,
                )
            except subprocess.TimeoutExpired:
                _reject("CaptureTimeout", "rpicam-still exceeded supplied HOST timeout")
            except OSError as error:
                _reject("CaptureLaunchFailed", f"rpicam-still could not start: {error.strerror}")
            if completed.returncode != 0:
                _reject(
                    "CaptureCommandFailed",
                    f"rpicam-still returned {completed.returncode}",
                )
        completed_at = clock()
        _regular_nonsymlink(output, "capture output")
        try:
            byte_count = output.stat().st_size
        except OSError as error:
            _reject("CaptureOutputReadFailed", f"cannot stat capture output: {error.strerror}")
        if byte_count == 0:
            _reject("EmptyCaptureOutput", "capture output is empty")
        if byte_count > controls["max_output_bytes"]:
            _reject("CaptureOutputOverBound", "capture exceeds supplied HOST byte bound")
        output_hash = sha256_file(output)
        executable_hash = verify_capture_executable(config)
        records.append(
            {
                "attempt": capture["attempt"],
                "byte_count": byte_count,
                "capture_id": capture["capture_id"],
                "completed_utc": completed_at,
                "filename": capture["filename"],
                "page_id": capture["page_id"],
                "sequence": capture["sequence"],
                "sha256": output_hash,
                "started_utc": started,
            }
        )

    manifest = {
        "camera_class": config["camera_class"],
        "captures": records,
        "configuration_sha256": config_sha256,
        "contract_version": config["contract_version"],
        "corpus": False,
        "decode_performed": False,
        "adapter_interface": adapter["interface"],
        "environment_sha256": canonical_hash({}),
        "executable_path": adapter.get("executable_path"),
        "executable_sha256": executable_hash,
        "geometry_sha256": canonical_hash(config["geometry"]),
        "manifest_version": MANIFEST_VERSION,
        "payload_bytes_recorded_in_manifest": False,
        "purpose": config["purpose"],
        "session_id": config["session_id"],
        "settings_sha256": canonical_hash(config["settings"]),
        "software_sha256": canonical_hash(config["software"]),
        "source_commit": config["source_commit"],
    }
    manifest_path = output_directory / manifest_filename(config["session_id"])
    try:
        with manifest_path.open("xb") as destination:
            destination.write(canonical_json_bytes(manifest))
    except FileExistsError:
        _reject("ManifestExists", "success manifest already exists")
    except OSError as error:
        _reject("ManifestWriteFailed", f"cannot write success manifest: {error.strerror}")
    return manifest_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("config", type=Path)
        command.add_argument("expected_config_sha256")
        if name == "run":
            command.add_argument("output_directory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        config, config_hash = load_config(arguments.config, arguments.expected_config_sha256)
        if arguments.command == "validate":
            names = [capture["filename"] for capture in config["captures"]]
            print(
                json.dumps(
                    {
                        "configuration_sha256": config_hash,
                        "corpus": False,
                        "planned_capture_count": len(names),
                        "planned_filenames": names,
                        "purpose": config["purpose"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            return 0
        manifest = run_capture_session(config, config_hash, arguments.output_directory)
        print(
            json.dumps(
                {
                    "capture_count": len(config["captures"]),
                    "manifest": str(manifest),
                    "status": "PASS",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except RigCaptureError as error:
        print(f"{error.category}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
