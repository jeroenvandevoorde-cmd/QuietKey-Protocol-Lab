from __future__ import annotations

import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


RIG_DIRECTORY = Path(__file__).resolve().parents[1]
if str(RIG_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(RIG_DIRECTORY))

import rig_capture  # noqa: E402


SOURCE_COMMIT = "0" * 40


def public_payload(capture_id: str, page_id: str, attempt: int, sequence: int) -> bytes:
    return (
        "QUIETKEY PUBLIC MOCK CAPTURE\n"
        f"capture_id={capture_id}\n"
        f"page_id={page_id}\n"
        f"attempt={attempt}\n"
        f"sequence={sequence}\n"
    ).encode("ascii")


def base_config(behavior: str = "WRITE-PUBLIC-MOCK") -> dict:
    return {
        "contract_version": "QK-RIG-CAPTURE-G0-V1",
        "purpose": "MOCK",
        "corpus": False,
        "session_id": "MOCK-SESSION-ONE",
        "source_commit": SOURCE_COMMIT,
        "camera_class": "MOCK-CAMERA",
        "authorization": {
            "scope": "PUBLIC-MOCK-ONLY",
            "state": "NOT-CORPUS",
        },
        "software": {
            "adapter": "PUBLIC-MOCK-PRODUCER",
            "python": "TEST-RUNTIME",
        },
        "settings": {
            "output_extension": "mock",
            "producer_behavior": behavior,
        },
        "geometry": {
            "jig_revision": "PUBLIC-MOCK-JIG",
            "camera_to_page_distance_mm": 123.5,
            "page_fill_percent": 77,
            "page_orientation": "PUBLIC-MOCK-PORTRAIT",
            "camera_mount_definition": "PUBLIC-MOCK-MOUNT",
            "page_plane_definition": "PUBLIC-MOCK-PLANE",
            "fiducial_specification": "PUBLIC-MOCK-FIDUCIALS",
            "scale_bar_length_mm": 12.5,
            "scale_bar_placement": "PUBLIC-MOCK-BESIDE-PAGE",
            "lighting_geometry": "PUBLIC-MOCK-LIGHT",
        },
        "adapter": {
            "interface": "PUBLIC-MOCK-CAPTURE-V1",
            "working_directory": str(RIG_DIRECTORY),
        },
        "controls": {
            "timeout_seconds": 5,
            "max_output_bytes": 4096,
        },
        "captures": [
            {
                "capture_id": "MOCK-CAPTURE-ONE",
                "page_id": "MOCK-PAGE-ONE",
                "attempt": 1,
                "sequence": 0,
            },
            {
                "capture_id": "MOCK-CAPTURE-TWO",
                "page_id": "MOCK-PAGE-TWO",
                "attempt": 2,
                "sequence": 1,
            },
        ],
    }


def preflight_config(directory: Path, camera_class: str = "ZEROCAM") -> dict:
    executable = directory / "rpicam-still"
    executable.write_bytes(b"PUBLIC NONEXECUTING RPICAM PLACEHOLDER\n")
    executable.chmod(0o755)
    return {
        "contract_version": "QK-RIG-CAPTURE-G0-V1",
        "purpose": "PREFLIGHT",
        "corpus": False,
        "session_id": "PREFLIGHT-SESSION-ONE",
        "source_commit": SOURCE_COMMIT,
        "camera_class": camera_class,
        "authorization": {"scope": "NON-CORPUS-PREFLIGHT", "state": "NOT-ACTIVE"},
        "software": {"camera_stack": "OWNER-INPUT-REQUIRED"},
        "settings": {
            "output_extension": "jpg",
            "camera_index": 0,
            "width_px": 4608,
            "height_px": 2592,
            "jpeg_quality": 95,
            "capture_timeout_ms": 750,
            "shutter_us": 10000,
            "analogue_gain": 1.25,
            "awb_gain_red": 1.5,
            "awb_gain_blue": 1.75,
            "lens_position": 0,
            "rotation_degrees": 180,
            "horizontal_flip": True,
            "vertical_flip": False,
            "denoise_mode": "cdn_hq",
        },
        "geometry": base_config()["geometry"],
        "adapter": {
            "interface": "RPICAM-STILL-CAPTURE-V1",
            "working_directory": str(directory),
            "executable_path": str(executable),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        },
        "controls": {"timeout_seconds": 5, "max_output_bytes": 30_000_000},
        "captures": [
            {
                "capture_id": "PREFLIGHT-CAPTURE-ONE",
                "page_id": "PREFLIGHT-PAGE-ONE",
                "attempt": 1,
                "sequence": 0,
            }
        ],
    }


def write_config(directory: Path, config: dict) -> tuple[Path, str]:
    path = directory / "config.json"
    raw = (json.dumps(config, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class RigCaptureTests(unittest.TestCase):
    def expect_category(self, category: str, operation) -> None:
        with self.assertRaises(rig_capture.RigCaptureError) as raised:
            operation()
        self.assertEqual(raised.exception.category, category)

    def test_valid_configuration_has_deterministic_names(self) -> None:
        validated = rig_capture.validate_config(base_config())
        self.assertEqual(
            [record["filename"] for record in validated["captures"]],
            [
                "qk-rig-g0-v1__MOCK-SESSION-ONE__s0__MOCK-CAPTURE-ONE__MOCK-PAGE-ONE__a1.mock",
                "qk-rig-g0-v1__MOCK-SESSION-ONE__s1__MOCK-CAPTURE-TWO__MOCK-PAGE-TWO__a2.mock",
            ],
        )
        self.assertEqual(
            rig_capture.manifest_filename("MOCK-SESSION-ONE"),
            "qk-rig-g0-v1__MOCK-SESSION-ONE__manifest.json",
        )

    def test_validate_cli_is_nonexecuting_and_reports_only_plan_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, digest = write_config(directory, base_config())
            output = io.StringIO()
            with redirect_stdout(output):
                status = rig_capture.main(["validate", str(config_path), digest])
            self.assertEqual(status, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["planned_capture_count"], 2)
            self.assertFalse(result["corpus"])
            self.assertFalse(any(directory.glob("*.mock")))

    def test_mock_run_hashes_opaque_outputs_and_writes_canonical_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, digest = write_config(directory, base_config())
            config, observed = rig_capture.load_config(config_path, digest)
            timestamps = iter(
                [
                    "2030-01-01T00:00:00.000001Z",
                    "2030-01-01T00:00:00.000002Z",
                    "2030-01-01T00:00:00.000003Z",
                    "2030-01-01T00:00:00.000004Z",
                ]
            )
            output_directory = directory / "outputs"
            manifest_path = rig_capture.run_capture_session(
                config, observed, output_directory, clock=lambda: next(timestamps)
            )
            raw_manifest = manifest_path.read_bytes()
            manifest = json.loads(raw_manifest)
            self.assertEqual(raw_manifest, rig_capture.canonical_json_bytes(manifest))
            self.assertEqual(manifest["configuration_sha256"], digest)
            self.assertEqual(manifest["adapter_interface"], "PUBLIC-MOCK-CAPTURE-V1")
            self.assertIsNone(manifest["executable_path"])
            self.assertIsNone(manifest["executable_sha256"])
            self.assertFalse(manifest["corpus"])
            self.assertFalse(manifest["decode_performed"])
            self.assertFalse(manifest["payload_bytes_recorded_in_manifest"])
            for record, expected in zip(
                manifest["captures"],
                [
                    public_payload("MOCK-CAPTURE-ONE", "MOCK-PAGE-ONE", 1, 0),
                    public_payload("MOCK-CAPTURE-TWO", "MOCK-PAGE-TWO", 2, 1),
                ],
            ):
                self.assertEqual(record["byte_count"], len(expected))
                self.assertEqual(record["sha256"], hashlib.sha256(expected).hexdigest())
                self.assertNotIn("payload", record)

    def test_configuration_hash_mismatch_stops_before_parse_or_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, _ = write_config(directory, base_config())
            self.expect_category(
                "ConfigHashMismatch",
                lambda: rig_capture.load_config(config_path, "f" * 64),
            )

    def test_duplicate_configuration_field_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_path, _ = write_config(directory, base_config())
            raw = config_path.read_bytes().replace(
                b'"corpus":false,', b'"corpus":false,"corpus":false,', 1
            )
            config_path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.expect_category(
                "MalformedConfig",
                lambda: rig_capture.load_config(config_path, digest),
            )

    def test_executable_hash_mismatch_rejects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = preflight_config(Path(temporary))
            config["adapter"]["executable_sha256"] = "f" * 64
            self.expect_category(
                "BoundFileHashMismatch", lambda: rig_capture.validate_config(config)
            )

    def test_preflight_executable_identity_is_closed_to_rpicam_still(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = preflight_config(directory)
            other = directory / "caller-program"
            other.write_bytes((directory / "rpicam-still").read_bytes())
            other.chmod(0o755)
            config["adapter"]["executable_path"] = str(other)
            self.expect_category(
                "UnsupportedCaptureExecutable",
                lambda: rig_capture.validate_config(config),
            )

    def test_adapter_rejects_caller_commands_plugins_and_environment(self) -> None:
        config = base_config()
        config["adapter"]["arguments"] = ["--post-process-file", "/tmp/plugin.json"]
        self.expect_category(
            "MalformedConfig", lambda: rig_capture.validate_config(config)
        )
        config = base_config()
        config["adapter"]["environment"] = {"LD_PRELOAD": "/tmp/plugin.so"}
        self.expect_category("MalformedConfig", lambda: rig_capture.validate_config(config))

    def test_corpus_and_unregistered_purpose_are_closed(self) -> None:
        config = base_config()
        config["corpus"] = True
        self.expect_category("CorpusClosed", lambda: rig_capture.validate_config(config))
        config = base_config()
        config["purpose"] = "CORPUS"
        self.expect_category(
            "UnauthorizedPurpose", lambda: rig_capture.validate_config(config)
        )

    def test_geometry_has_no_omission_or_extension_path(self) -> None:
        config = base_config()
        del config["geometry"]["scale_bar_placement"]
        self.expect_category("MalformedConfig", lambda: rig_capture.validate_config(config))
        config = base_config()
        config["geometry"]["silent_default"] = 1
        self.expect_category("MalformedConfig", lambda: rig_capture.validate_config(config))

    def test_identifiers_sequences_and_capture_ids_are_unique(self) -> None:
        config = base_config()
        config["captures"][0]["page_id"] = "../PAGE"
        self.expect_category("UnsafeIdentifier", lambda: rig_capture.validate_config(config))
        config = base_config()
        config["captures"][1]["sequence"] = 0
        self.expect_category("DuplicateCapture", lambda: rig_capture.validate_config(config))
        config = base_config()
        config["captures"][1]["capture_id"] = "MOCK-CAPTURE-ONE"
        self.expect_category("DuplicateCapture", lambda: rig_capture.validate_config(config))

    def test_adapter_interface_and_working_directory_are_mandatory(self) -> None:
        config = base_config()
        config["adapter"]["interface"] = "CALLER-EXECUTABLE-V1"
        self.expect_category("UnsupportedAdapter", lambda: rig_capture.validate_config(config))
        config = base_config()
        del config["adapter"]["working_directory"]
        self.expect_category("MalformedConfig", lambda: rig_capture.validate_config(config))

    def test_rpicam_command_is_closed_and_sensor_class_is_data_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            zero = rig_capture.validate_config(preflight_config(directory, "ZEROCAM"))
            module_three_input = preflight_config(directory, "CAMERA-MODULE-3")
            module_three = rig_capture.validate_config(module_three_input)
            output = directory / "opaque.jpg"
            zero_command = rig_capture.build_rpicam_command(zero, output)
            module_three_command = rig_capture.build_rpicam_command(module_three, output)
            self.assertEqual(zero_command, module_three_command)
            self.assertEqual(zero_command[0], str(directory / "rpicam-still"))
            self.assertEqual(zero_command[-2:], ["--output", str(output)])
            self.assertEqual(zero_command.count(str(output)), 1)
            self.assertNotIn("--post-process-file", zero_command)
            self.assertNotIn("--metadata", zero_command)
            self.assertNotIn("--input", zero_command)

    def test_existing_output_directory_is_never_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = rig_capture.validate_config(base_config())
            output = directory / "already-there"
            output.mkdir()
            self.expect_category(
                "OutputDirectoryExists",
                lambda: rig_capture.run_capture_session(config, "0" * 64, output),
            )

    def test_output_directory_must_be_absolute_before_creation(self) -> None:
        config = rig_capture.validate_config(base_config())
        self.expect_category(
            "UnsafeOutputPath",
            lambda: rig_capture.run_capture_session(
                config, "0" * 64, Path("relative-output")
            ),
        )
        self.assertFalse(Path("relative-output").exists())

    def test_empty_and_missing_capture_outputs_fail_without_manifest(self) -> None:
        for behavior, category in [
            ("EMPTY", "EmptyCaptureOutput"),
            ("MISSING", "MissingBoundFile"),
        ]:
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                config = base_config(behavior)
                config["captures"] = config["captures"][:1]
                validated = rig_capture.validate_config(config)
                output = directory / "outputs"
                self.expect_category(
                    category,
                    lambda: rig_capture.run_capture_session(validated, "0" * 64, output),
                )
                self.assertFalse(any(output.glob("*manifest.json")))

    def test_failed_capture_command_is_not_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config = base_config("FAIL")
            config["captures"] = config["captures"][:1]
            validated = rig_capture.validate_config(config)
            output = directory / "outputs"
            self.expect_category(
                "CaptureCommandFailed",
                lambda: rig_capture.run_capture_session(validated, "0" * 64, output),
            )
            self.assertEqual(list(output.iterdir()), [])

    def test_capture_module_imports_only_standard_capture_scaffold_modules(self) -> None:
        source_path = RIG_DIRECTORY / "rig_capture.py"
        parsed = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(
            imported,
            {
                "__future__",
                "argparse",
                "datetime",
                "hashlib",
                "json",
                "math",
                "os",
                "pathlib",
                "re",
                "stat",
                "subprocess",
                "sys",
                "typing",
            },
        )


if __name__ == "__main__":
    unittest.main()
