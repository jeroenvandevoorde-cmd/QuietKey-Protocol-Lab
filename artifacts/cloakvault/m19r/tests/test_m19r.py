from __future__ import annotations

import copy
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

import synthetic_model as synth


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class M19RTests(unittest.TestCase):
    def test_payload_registry_is_exact(self):
        with (ROOT / "inputs" / "PAYLOADS.tsv").open("r", encoding="ascii", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(len(rows), 18)
        self.assertEqual([int(row["q"]) for row in rows], list(range(18)))
        self.assertEqual({row["lineage"] for row in rows}, set(synth.LINEAGES))
        for row in rows:
            token = row["token_ascii"].encode("ascii")
            self.assertEqual(len(token), int(row["token_length"]))
            self.assertEqual(sha(token), row["token_sha256"])

    def test_clean_render_manifest_and_bytes(self):
        manifest_path = ROOT / "generated" / "CLEAN-RENDERS.json"
        manifest = json.loads(manifest_path.read_text("ascii"))
        self.assertEqual(manifest["clean_render_count"], 36)
        self.assertEqual(manifest["comparison_generation"], "DISABLED")
        self.assertEqual(manifest["fresh_anchor_inputs"], 0)
        self.assertEqual(
            manifest["payload_registry"]["source_repository"],
            "https://github.com/jeroenvandevoorde-cmd/QuietKey",
        )
        self.assertEqual(len(manifest["records"]), 36)
        for record in manifest["records"]:
            data = (REPO / record["path"]).read_bytes()
            self.assertEqual(len(data), record["bytes"])
            self.assertEqual(sha(data), record["sha256"])

    def test_twelve_prior_clean_renders_are_byte_equal(self):
        old = REPO / "artifacts" / "cloakvault" / "m19" / "phase1" / "preflight" / "renders"
        new = ROOT / "generated" / "clean"
        paths = sorted(old.glob("*.png"))
        self.assertEqual(len(paths), 12)
        for path in paths:
            self.assertEqual(path.read_bytes(), (new / path.name).read_bytes())

    def test_reference_registration_counts_and_totals(self):
        with (ROOT / "registrations" / "MORPHOLOGY-REFERENCES.tsv").open(
            "r", encoding="ascii", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        spike = [row for row in rows if row["set"] == "spike"]
        bridge = [row for row in rows if row["set"] == "bridge"]
        self.assertEqual((len(spike), len(bridge)), (29, 19))
        self.assertEqual(sum(int(row["bytes"]) for row in spike), 59_148_370)
        self.assertEqual(sum(int(row["bytes"]) for row in bridge), 58_847_212)
        self.assertNotIn("baseline-0-std-S01..jpeg", {Path(row["path"]).name for row in spike})

    def test_spike_reference_bytes(self):
        with (ROOT / "registrations" / "MORPHOLOGY-REFERENCES.tsv").open(
            "r", encoding="ascii", newline=""
        ) as handle:
            rows = [row for row in csv.DictReader(handle, delimiter="\t") if row["set"] == "spike"]
        registry = []
        for row in rows:
            data = (REPO / row["path"]).read_bytes()
            self.assertEqual(len(data), int(row["bytes"]))
            self.assertEqual(sha(data), row["sha256"])
            registry.append("{}\t{}\t{}".format(Path(row["path"]).name, row["bytes"], row["sha256"]))
        self.assertEqual(
            sha("\n".join(registry).encode("ascii")),
            "4785158088a9c8a2b07a027c9e40078afeb36c77afe410ea25e829ed67d6ba60",
        )

    def test_bridge_registration_matches_committed_manifest(self):
        source_path = REPO / "artifacts" / "cloakvault" / "bridge" / "captures" / "CAPTURE-MANIFEST.json"
        self.assertEqual(sha(source_path.read_bytes()), "227e3c0836f339b810d504751f21c45cf32fb277c31ddcf6d56be6efef4298f7")
        source = json.loads(source_path.read_text("ascii"))["images"]
        with (ROOT / "registrations" / "MORPHOLOGY-REFERENCES.tsv").open(
            "r", encoding="ascii", newline=""
        ) as handle:
            registered = [
                row for row in csv.DictReader(handle, delimiter="\t") if row["set"] == "bridge"
            ]
        self.assertEqual(len(registered), len(source))
        for row, expected in zip(registered, source):
            self.assertEqual(Path(row["path"]).name, expected["filename"])
            self.assertEqual(int(row["bytes"]), expected["size_bytes"])
            self.assertEqual(row["sha256"], expected["sha256"])
            self.assertEqual(row["bench_commit"], "60f98eb1633266bf58a36b5eb4a446baeb66974a")
        registry = "\n".join(
            "{}\t{}\t{}".format(row["filename"], row["size_bytes"], row["sha256"])
            for row in source
        )
        self.assertEqual(sha(registry.encode("ascii")), "8788fa92295f740c897e27051d904b31d7b0a28bf0d0ce037357b10132915eba")

    def test_model_draft_validates_and_is_inactive(self):
        config = synth.load_draft()
        self.assertEqual(config["status"], "DRAFT_NOT_ACTIVE")
        self.assertFalse(config["activation"]["comparison_generation_enabled"])
        self.assertFalse(synth.ACTIVE_PATH.exists())
        self.assertFalse((ROOT / "generated" / "comparison").exists())
        modified = copy.deepcopy(config)
        modified["status"] = "ACTIVE_OWNER_RATIFIED"
        with self.assertRaises(synth.ConfigurationError):
            synth.validate_draft(modified)

    def test_comparison_plan_count_and_hash(self):
        plan = synth.comparison_plan()
        self.assertEqual(len(plan), 1566)
        self.assertEqual(synth.plan_sha256(plan), "78fae2b81bd302b841f4ff620ff073efd79e2e17b98971fc7b7cbd70b09ce88a")

    def test_profile_pair_uses_same_parameters(self):
        config = synth.load_draft()
        paired = [
            row
            for row in synth.comparison_plan()
            if row["lineage"] == "T2" and row["cell"] == "c14" and row["realization"] == 1
        ]
        self.assertEqual({row["profile"] for row in paired}, set(synth.PROFILES))
        parameters = [
            synth.derive_parameters(config, row["lineage"], row["cell"], row["realization"])
            for row in paired
        ]
        self.assertEqual(parameters[0], parameters[1])
        self.assertEqual(parameters[1], parameters[2])

    def test_integer_model_is_repeatable(self):
        config = synth.load_draft()
        image = synth.GrayImage(16, 12, bytes((x * 17 + y * 11) % 256 for y in range(12) for x in range(16)))
        params = synth.derive_parameters(config, "T5", "c22", 2)
        self.assertEqual(synth.apply_model(image, params), synth.apply_model(image, params))

    def test_linear_box_blur_matches_exact_area_reference(self):
        image = synth.GrayImage(
            11,
            9,
            bytes((x * 31 + y * 47 + x * y * 3) % 256 for y in range(9) for x in range(11)),
        )
        for radius in range(5):
            expected = bytearray(image.width * image.height)
            for y in range(image.height):
                y0, y1 = max(0, y - radius), min(image.height - 1, y + radius)
                for x in range(image.width):
                    x0, x1 = max(0, x - radius), min(image.width - 1, x + radius)
                    values = [
                        image.pixels[yy * image.width + xx]
                        for yy in range(y0, y1 + 1)
                        for xx in range(x0, x1 + 1)
                    ]
                    expected[y * image.width + x] = (sum(values) + len(values) // 2) // len(values)
            self.assertEqual(synth._box_blur(image, radius).pixels, bytes(expected))

    def test_locate_one_has_perspective_and_keeps_every_corner_in_frame(self):
        width, height = 1241, 1754
        self.assertEqual(
            synth._locate_page_corners(width, height),
            (
                (22_943_981, 13_595_505),
                (77_875_202, 28_315_222),
                (55_533_888, 94_381_106),
                (9_256_999, 81_980_459),
            ),
        )
        corners = synth._locate_page_corners(width, height)
        for x, y in corners:
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x, (width - 1) * synth.Q16)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(y, (height - 1) * synth.Q16)

        # Perspective makes the nearer top edge longer than the far bottom
        # edge; a rotation-only transform would leave these lengths equal.
        def squared_length(first, second):
            return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2

        self.assertGreater(squared_length(corners[0], corners[1]), squared_length(corners[3], corners[2]))

        # The locate margin also contains the complete page under every corner
        # of the separately bounded common translate/shear envelope.
        center_y_q16 = (height - 1) * synth.Q16 // 2
        for dx in (-31, 31):
            for dy in (-31, 31):
                for shear_q16 in (-1311, 1311):
                    for x, y in corners:
                        output_y = y + dy * synth.Q16
                        output_x = (
                            x
                            + dx * synth.Q16
                            + (output_y - center_y_q16) * shear_q16 // synth.Q16
                        )
                        self.assertGreaterEqual(output_x, 0)
                        self.assertLessEqual(output_x, (width - 1) * synth.Q16)
                        self.assertGreaterEqual(output_y, 0)
                        self.assertLessEqual(output_y, (height - 1) * synth.Q16)

    def test_scuff_segments_are_complete_exact_40_mm_spans(self):
        config = synth.load_draft()
        image = synth.GrayImage(210, 297, bytes([255]) * (210 * 297))
        params = synth.derive_parameters(config, "T3", "c25", 2)
        segments = synth._scuff_segments(image, params)
        self.assertEqual(len(segments), 30)
        x0, x1, y0, y1 = synth._footer_bounds(image.width, image.height)
        for start, y, end in segments:
            self.assertEqual(end - start, 40)
            self.assertGreaterEqual(start, x0)
            self.assertLess(end, x1)
            self.assertGreaterEqual(y, y0)
            self.assertLess(y, y1)

    def test_every_class_has_a_distinct_deterministic_operator(self):
        config = synth.load_draft()
        image = synth.GrayImage(
            64,
            96,
            bytes(40 if y >= 88 and 5 <= x <= 40 else 235 for y in range(96) for x in range(64)),
        )
        cells = ("c02", "c04", "c07", "c09", "c12", "c15", "c19", "c20", "c23", "c26")
        outputs = {}
        for cell in cells:
            params = synth.derive_parameters(config, "T1", cell, 0)
            first = synth.apply_model(image, params)
            second = synth.apply_model(image, params)
            self.assertEqual(first, second)
            outputs[params.damage_class] = sha(first.pixels)
        self.assertEqual(len(outputs), 10)
        self.assertEqual(len(set(outputs.values())), 10)

    def test_baseline_dim_and_glare_are_distinct(self):
        config = synth.load_draft()
        image = synth.GrayImage(32, 48, bytes((x * 9 + y * 3) % 256 for y in range(48) for x in range(32)))
        hashes = {
            cell: sha(synth.apply_model(image, synth.derive_parameters(config, "T0", cell, 0)).pixels)
            for cell in ("c00", "c01", "c02")
        }
        self.assertEqual(len(set(hashes.values())), 3)

    def test_metric_algorithms_and_centers(self):
        config = synth.load_draft()
        clean_pixels = bytearray([100] * (32 * 48))
        observed_pixels = bytearray(clean_pixels)
        x0, x1, y0, y1 = synth._footer_bounds(32, 48)
        observed_pixels[y0 * 32 + x0] = 255
        clean = synth.GrayImage(32, 48, bytes(clean_pixels))
        observed = synth.GrayImage(32, 48, bytes(observed_pixels))
        metric = synth.compute_metrics(clean, observed, config=config)
        self.assertEqual(metric.geometry_corner_rms_q16, 0)
        self.assertEqual(metric.geometry_corner_max_q16, 0)
        self.assertEqual(metric.component_count, 1)
        self.assertEqual(metric.largest_component_fraction_q16, synth.Q16)
        self.assertEqual(metric.footer_overlap_q16, synth.Q16)
        self.assertGreaterEqual(metric.damage_centroid_x_q16, 0)
        self.assertGreater(metric.glare_coverage_q16, 0)
        center = synth.aggregate_synthetic_metrics(
            [replace(metric, component_count=7), metric, replace(metric, component_count=3)]
        )
        self.assertEqual(center.component_count, 3)
        self.assertEqual(synth.validate_cell_metrics("c01", metric, [metric, metric, metric], config), ())

    def test_metric_rejections_are_named(self):
        config = synth.load_draft()
        clean = synth.GrayImage(24, 36, bytes([100] * (24 * 36)))
        anchor = synth.compute_metrics(clean, clean, config=config)
        bad = replace(
            anchor,
            geometry_corner_rms_q16=10_000,
            geometry_corner_max_q16=10_000,
            damage_centroid_x_q16=10_000,
            damage_centroid_y_q16=10_000,
            footer_overlap_q16=10_000,
            component_count=10,
            largest_component_fraction_q16=10_000,
            luminance_median_u8=255,
            contrast_iqr_u8=255,
            luminance_p05_u8=255,
            edge_energy_q16=10_000,
            high_edge_fraction_q16=10_000,
            glare_coverage_q16=10_000,
            glare_centroid_x_q16=10_000,
            glare_centroid_y_q16=10_000,
        )
        for cell, *_ in synth.CELLS:
            self.assertEqual(synth.validate_cell_metrics(cell, anchor, [anchor] * 3, config), ())
        failures = set(synth.validate_cell_metrics("c02", anchor, [bad, bad, bad], config))
        self.assertTrue(
            {
                "GeometryCornerRms",
                "GeometryCornerMax",
                "DamageMaskPresenceMismatch",
                "FooterOverlap",
                "ConnectedComponentCount",
                "LargestComponentFraction",
                "LuminanceMedian",
                "ContrastIqr",
                "LuminanceTail",
                "EdgeEnergyZeroMismatch",
                "HighEdgeFraction",
                "GlarePresenceMismatch",
                "GlareCoverage",
            }
            <= failures
        )

    def test_comparison_gate_refuses_missing_activation(self):
        with self.assertRaises(synth.ModelFreezeRequired):
            synth.generate_comparison()

    def test_arbitrary_activation_json_cannot_pass(self):
        self.assertIsNone(synth.EXPECTED_ACTIVE_REGISTRATION_SHA256)
        self.assertIsNone(synth.EXPECTED_OWNER_DECISION_ID)
        self.assertIsNone(synth.EXPECTED_DECISION_LOG_COMMIT)
        value = {
            "schema": "QK-M19R-MODEL-FREEZE-ACTIVATION-V1",
            "status": "ACTIVE_OWNER_RATIFIED",
            "authority": {},
            "bindings": {},
            "scope": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "MODEL-FREEZE-ACTIVE.json"
            path.write_text(json.dumps(value), encoding="ascii")
            with self.assertRaises(synth.ModelFreezeRequired):
                synth.require_active_registration(path)

    def test_no_decode_or_score_imports(self):
        for name in ("generate_clean_renders.py", "synthetic_model.py"):
            source = (ROOT / name).read_text("ascii")
            self.assertNotIn("qka1_reader_v02", source)
            self.assertNotIn("reed_solomon", source)
            self.assertNotIn("chacha", source.lower())


if __name__ == "__main__":
    unittest.main()
