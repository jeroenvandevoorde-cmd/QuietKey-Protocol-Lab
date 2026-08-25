from __future__ import annotations

import hashlib
import json
import struct
import unittest
import zlib
from pathlib import Path

from qka1_reader_v02.constants import ALPHABET, ERASURE, ProfileName, layout_for
from qka1_reader_v02.image import GrayImage, decode_png
from qka1_reader_v02.model import ReadOutcome
from qka1_reader_v02.pipeline import ReaderV02
from qka1_reader_v02.policy import CorpusDescriptor, CorpusPurpose, FrameInput
from qka1_reader_v02.profile import ReaderProfile
from qka1_reader_v02.templates import (
    TemplateClassifier,
    build_synthetic_partition,
    train_template_model,
)
from qka1_reader_v02.vision import DeterministicLocator

REPOSITORY = Path(__file__).resolve().parents[4]
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "substance-v1.json"


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def corpus_manifest(corpus_id, purpose, source_commit, members):
    return canonical_json(
        {
            "format": "qka1-reader-corpus-v1",
            "corpus_id": corpus_id,
            "purpose": purpose.value,
            "source_commit": source_commit,
            "members": [
                {
                    "member_id": member_id,
                    "byte_length": len(member_bytes),
                    "sha256": hashlib.sha256(member_bytes).hexdigest(),
                }
                for member_id, member_bytes in members
            ],
        }
    )


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(data, zlib.crc32(kind)) & 0xFFFFFFFF)
    )


def stored_zlib(data):
    """Emit a byte-stable zlib stream made only of stored DEFLATE blocks."""

    blocks = bytearray(b"\x78\x01")
    for offset in range(0, len(data), 65535):
        block = data[offset : offset + 65535]
        final = offset + len(block) == len(data)
        blocks.append(1 if final else 0)
        blocks.extend(struct.pack("<H", len(block)))
        blocks.extend(struct.pack("<H", len(block) ^ 0xFFFF))
        blocks.extend(block)
    blocks.extend(struct.pack(">I", zlib.adler32(data) & 0xFFFFFFFF))
    return bytes(blocks)


def encode_gray_png(image):
    scanlines = b"".join(
        b"\x00" + image.pixels[y * image.width : (y + 1) * image.width]
        for y in range(image.height)
    )
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", stored_zlib(scanlines))
        + png_chunk(b"IEND", b"")
    )


def solve_linear(matrix, vector):
    """Solve one small dense system for fixture generation only."""

    rows = [list(row) + [value] for row, value in zip(matrix, vector)]
    size = len(rows)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-12:
            raise ValueError("singular fixture transform")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            rows[row] = [
                value - factor * source
                for value, source in zip(rows[row], rows[column])
            ]
    return [rows[index][-1] for index in range(size)]


def projective_matrix(corners):
    matrix = []
    vector = []
    for (u, v), (x, y) in zip(
        ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), corners
    ):
        matrix.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        vector.append(float(x))
        matrix.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        vector.append(float(y))
    return solve_linear(matrix, vector) + [1.0]


def invert_three(matrix):
    a, b, c, d, e, f, g, h, i = matrix
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(determinant) < 1e-12:
        raise ValueError("singular fixture matrix")
    return [
        (e * i - f * h) / determinant,
        (c * h - b * i) / determinant,
        (b * f - c * e) / determinant,
        (f * g - d * i) / determinant,
        (a * i - c * g) / determinant,
        (c * d - a * f) / determinant,
        (d * h - e * g) / determinant,
        (b * g - a * h) / determinant,
        (a * e - b * d) / determinant,
    ]


def projective_canvas(source, specification):
    """Render a page into a rotated projective quadrilateral deterministically."""

    width = specification["canvas_width"]
    height = specification["canvas_height"]
    inverse = invert_three(projective_matrix(specification["corners"]))
    pixels = bytearray([specification["background"]] * (width * height))
    for y in range(height):
        for x in range(width):
            denominator = inverse[6] * x + inverse[7] * y + inverse[8]
            if abs(denominator) < 1e-12:
                continue
            u = (inverse[0] * x + inverse[1] * y + inverse[2]) / denominator
            v = (inverse[3] * x + inverse[4] * y + inverse[5]) / denominator
            if not 0.0 <= u <= 1.0 or not 0.0 <= v <= 1.0:
                continue
            sx = min(source.width - 1, int(u * (source.width - 1) + 0.5))
            sy = min(source.height - 1, int(v * (source.height - 1) + 0.5))
            pixels[y * width + x] = source.pixels[sy * source.width + sx]
    return GrayImage(width, height, bytes(pixels))


class SubstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()
        cls.fixture = json.loads(cls.fixture_bytes)
        cls.source_commit = cls.fixture["source_commit"]
        implementation = cls.fixture["implementation"]
        for entry in implementation["inputs"]:
            actual = hashlib.sha256((REPOSITORY / entry["path"]).read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                raise AssertionError("reader implementation input differs from binding")
        cls.implementation_manifest_bytes = canonical_json(
            {
                "format": "qka1-reader-implementation-inputs-v1",
                "state": implementation["state"],
                "inputs": implementation["inputs"],
            }
        )
        cls.implementation_sha256 = hashlib.sha256(
            cls.implementation_manifest_bytes
        ).hexdigest()
        if cls.implementation_sha256 != implementation["manifest_sha256"]:
            raise AssertionError("reader implementation manifest differs from binding")
        cls.locator_bytes = canonical_json(cls.fixture["locator"])
        cls.locator = DeterministicLocator(cls.locator_bytes)

        labels = []
        patches = []
        cls.source_hashes = {}
        for source in cls.fixture["synthetic_training"]["sources"]:
            image_bytes = (REPOSITORY / source["image"]).read_bytes()
            label_bytes = (REPOSITORY / source["labels"]).read_bytes()
            cls.source_hashes[source["image"]] = hashlib.sha256(image_bytes).hexdigest()
            cls.source_hashes[source["labels"]] = hashlib.sha256(label_bytes).hexdigest()
            if cls.source_hashes[source["image"]] != source["image_sha256"]:
                raise AssertionError("training image differs from preregistration")
            if cls.source_hashes[source["labels"]] != source["labels_sha256"]:
                raise AssertionError("training labels differ from preregistration")
            text = label_bytes.decode("ascii")
            layout = layout_for(source["profile"])
            if len(text) != layout.symbol_count or any(c not in ALPHABET for c in text):
                raise AssertionError("training labels violate frozen geometry or alphabet")
            located = cls.locator.locate(image_bytes)
            if (
                not hasattr(located, "cells")
                or located.profile is not layout.profile
                or len(located.cells) != layout.symbol_count
            ):
                raise AssertionError("training footer was not located exactly")
            labels.extend(text)
            patches.extend(located.cells)

        synthetic = cls.fixture["synthetic_training"]
        cls.partition_bytes = build_synthetic_partition(
            synthetic["member_id"], "".join(labels), tuple(patches)
        )

        rectify = synthetic["rectification_fixture"]
        rectify_source_bytes = (REPOSITORY / rectify["source_image"]).read_bytes()
        rectify_label_bytes = (REPOSITORY / rectify["labels"]).read_bytes()
        if hashlib.sha256(rectify_source_bytes).hexdigest() != rectify["source_image_sha256"]:
            raise AssertionError("rectification source differs from preregistration")
        if hashlib.sha256(rectify_label_bytes).hexdigest() != rectify["labels_sha256"]:
            raise AssertionError("rectification labels differ from preregistration")
        cls.rectify_labels = rectify_label_bytes.decode("ascii")
        cls.rectify_bytes = encode_gray_png(
            projective_canvas(decode_png(rectify_source_bytes), rectify)
        )

        cls.synthetic_manifest_bytes = corpus_manifest(
            synthetic["corpus_id"],
            CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING,
            cls.source_commit,
            (
                (synthetic["member_id"], cls.partition_bytes),
                (rectify["member_id"], cls.rectify_bytes),
            ),
        )
        cls.synthetic_corpus = CorpusDescriptor(cls.synthetic_manifest_bytes)
        cls.model_bytes = train_template_model(
            cls.fixture["classifier"]["artifact_id"],
            cls.partition_bytes,
            cls.synthetic_corpus.manifest_sha256,
        )
        cls.classifier = TemplateClassifier(cls.model_bytes)

        clean = cls.fixture["clean_render_holdout"]
        clean_members = []
        cls.clean_cases = []
        for member in clean["members"]:
            image_bytes = (REPOSITORY / member["image"]).read_bytes()
            label_bytes = (REPOSITORY / member["labels"]).read_bytes()
            if hashlib.sha256(image_bytes).hexdigest() != member["image_sha256"]:
                raise AssertionError("clean-render image differs from preregistration")
            if hashlib.sha256(label_bytes).hexdigest() != member["labels_sha256"]:
                raise AssertionError("clean-render labels differ from preregistration")
            labels_text = label_bytes.decode("ascii")
            if len(labels_text) != layout_for(member["profile"]).symbol_count:
                raise AssertionError("clean-render labels violate frozen geometry")
            clean_members.append((member["member_id"], image_bytes))
            cls.clean_cases.append((member, image_bytes, labels_text))
        cls.clean_manifest_bytes = corpus_manifest(
            clean["corpus_id"],
            CorpusPurpose.FROZEN_CLEAN_RENDER,
            cls.source_commit,
            tuple(clean_members),
        )
        cls.clean_corpus = CorpusDescriptor(cls.clean_manifest_bytes)

        profile_data = {
            "profile_format_version": 1,
            "reader_version": "0.2",
            "status": "DEVELOPMENT / NOT FOR SCORING",
            "confidence_floor": cls.fixture["classifier"]["confidence_floor"],
            "margin_floor": cls.fixture["classifier"]["margin_floor"],
            "locator_id": cls.locator.artifact_id,
            "locator_sha256": cls.locator.artifact_sha256,
            "classifier_id": cls.classifier.artifact_id,
            "classifier_sha256": cls.classifier.artifact_sha256,
            "clean_render_corpus_id": cls.clean_corpus.corpus_id,
            "clean_render_source_commit": cls.clean_corpus.source_commit,
            "clean_render_manifest_sha256": cls.clean_corpus.manifest_sha256,
            "training_corpus_id": cls.synthetic_corpus.corpus_id,
            "training_corpus_source_commit": cls.synthetic_corpus.source_commit,
            "training_corpus_manifest_sha256": cls.synthetic_corpus.manifest_sha256,
            "training_partition_id": synthetic["member_id"],
            "training_partition_sha256": hashlib.sha256(cls.partition_bytes).hexdigest(),
            "reader_implementation_state": implementation["state"],
            "reader_implementation_sha256": cls.implementation_sha256,
            "alphabet": ALPHABET,
        }
        cls.profile_bytes = canonical_json(profile_data)
        cls.profile = ReaderProfile.from_json_bytes(cls.profile_bytes)
        cls.reader = ReaderV02(cls.profile, cls.locator, cls.classifier)

    def test_preregistered_partition_and_artifact_bindings_are_exact(self):
        fixture = self.fixture
        expected_hashes = fixture["expected_hashes"]
        self.assertEqual(
            fixture["status"],
            "DEVELOPMENT / NOT FOR SCORING / NOT A PRODUCT DEFAULT",
        )
        self.assertEqual(
            fixture["synthetic_training"]["transforms"],
            ["contrast-7of8", "shift-left-1", "shift-right-1"],
        )
        partition = json.loads(self.partition_bytes)
        self.assertEqual(len(partition["records"]), (116 + 128) * 3)
        self.assertEqual(set(record["symbol"] for record in partition["records"]), set(ALPHABET))
        self.assertEqual(
            self.locator.artifact_sha256,
            expected_hashes["locator_config_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(self.partition_bytes).hexdigest(),
            expected_hashes["synthetic_partition_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(self.rectify_bytes).hexdigest(),
            expected_hashes["projective_canvas_sha256"],
        )
        self.assertEqual(
            self.synthetic_corpus.manifest_sha256,
            expected_hashes["synthetic_corpus_manifest_sha256"],
        )
        self.assertEqual(
            self.classifier.artifact_sha256,
            expected_hashes["classifier_model_sha256"],
        )
        self.assertEqual(
            self.clean_corpus.manifest_sha256,
            expected_hashes["clean_render_manifest_sha256"],
        )
        self.assertEqual(self.classifier.training_partition_id, partition["partition_id"])
        self.assertEqual(
            self.classifier.training_partition_sha256,
            hashlib.sha256(self.partition_bytes).hexdigest(),
        )
        self.assertEqual(
            self.classifier.training_corpus_manifest_sha256,
            self.synthetic_corpus.manifest_sha256,
        )
        self.assertEqual(
            self.profile.raw_sha256,
            expected_hashes["reader_profile_sha256"],
        )
        self.assertEqual(
            self.profile.reader_implementation_state,
            "PENDING_BEFORE_SCORING",
        )
        self.assertEqual(
            self.profile.reader_implementation_sha256,
            fixture["implementation"]["manifest_sha256"],
        )

    def test_frozen_clean_renders_recover_all_three_exact_profiles(self):
        for member, image_bytes, expected in self.clean_cases:
            with self.subTest(profile=member["profile"]):
                result = self.reader.read(
                    FrameInput(member["member_id"], image_bytes),
                    self.clean_corpus,
                )
                self.assertEqual(result.outcome, ReadOutcome.TRANSCRIPT_READY)
                self.assertEqual(result.profile, ProfileName(member["profile"]))
                self.assertEqual(result.transcript.text, expected)
                self.assertEqual(result.transcript.text.count(ERASURE), 0)
                self.assertFalse(result.authenticated)

    def test_projective_full_page_is_located_rectified_and_profiled_automatically(self):
        fixture = self.fixture["synthetic_training"]["rectification_fixture"]
        result = self.reader.read(
            FrameInput(fixture["member_id"], self.rectify_bytes),
            self.synthetic_corpus,
        )
        self.assertEqual(result.outcome, ReadOutcome.TRANSCRIPT_READY)
        self.assertEqual(result.profile, ProfileName(fixture["profile"]))
        self.assertEqual(result.transcript.text, self.rectify_labels)
        self.assertEqual(result.transcript.erasure_count, 0)
        self.assertFalse(result.authenticated)

    def test_concrete_profile_inference_rejects_an_ambiguous_boundary(self):
        white = GrayImage(12, 20, b"\xff" * 240)
        ink = GrayImage(12, 20, b"\x00" * 240)
        boundary = GrayImage(12, 20, b"\xf5" * 240)
        cells = [white] * 128
        cells[64 + 46 : 64 + 52] = [ink] * 6
        cells[64 + 52 : 64 + 58] = [boundary] * 6
        self.assertIsNone(self.locator._infer_profile(tuple(cells)))

    def test_png_transport_rejects_corruption(self):
        corrupt = bytearray(self.rectify_bytes)
        corrupt[-20] ^= 1
        with self.assertRaises(ValueError):
            decode_png(bytes(corrupt))

    def test_generation_is_byte_deterministic(self):
        partition = json.loads(self.partition_bytes)
        records = partition["records"]
        self.assertEqual(canonical_json(partition), self.partition_bytes)
        self.assertTrue(all(record["pixels"] == record["pixels"].lower() for record in records))
        rebuilt = train_template_model(
            self.fixture["classifier"]["artifact_id"],
            self.partition_bytes,
            self.synthetic_corpus.manifest_sha256,
        )
        self.assertEqual(rebuilt, self.model_bytes)


if __name__ == "__main__":
    unittest.main()
