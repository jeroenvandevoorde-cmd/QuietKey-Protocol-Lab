from __future__ import annotations

import ast
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from qka1_reader_v02.constants import (
    ALPHABET,
    ERASURE,
    PROFILE_LAYOUTS,
    ProfileName,
    layout_for,
)
from qka1_reader_v02.interfaces import ClassificationCandidate, LocatedFooter
from qka1_reader_v02.model import ReadOutcome, ReaderResult, Transcript
from qka1_reader_v02.pipeline import ArtifactBindingError, ReaderV02
from qka1_reader_v02.policy import (
    CorpusDescriptor,
    CorpusPolicyError,
    CorpusPurpose,
    FrameInput,
)
from qka1_reader_v02.profile import ReaderProfile

LOCATOR_HASH = "11" * 32
CLASSIFIER_HASH = "22" * 32
SOURCE_COMMIT = "44" * 20
CLEAN_SOURCE_COMMIT = "55" * 20
SYNTHETIC_MEMBER_ID = "synthetic-frame-001"
CLEAN_MEMBER_ID = "clean-render-001"
SYNTHETIC_BYTES = b"QKA1 synthetic in-memory frame member v1"
CLEAN_BYTES = b"QKA1 frozen clean-render frame member v1"
FRESH_ANCHOR_BYTES = b"QKA1 fresh anchor bytes must never reach locator"


def manifest_bytes(corpus_id, purpose, source_commit, members):
    data = {
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
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


SYNTHETIC_MANIFEST = manifest_bytes(
    "synthetic-training-v1",
    CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING,
    SOURCE_COMMIT,
    [(SYNTHETIC_MEMBER_ID, SYNTHETIC_BYTES)],
)
CLEAN_MANIFEST = manifest_bytes(
    "frozen-clean-renders-v1",
    CorpusPurpose.FROZEN_CLEAN_RENDER,
    CLEAN_SOURCE_COMMIT,
    [(CLEAN_MEMBER_ID, CLEAN_BYTES)],
)
PARTITION_HASH = hashlib.sha256(SYNTHETIC_MANIFEST).hexdigest()
CLEAN_MANIFEST_HASH = hashlib.sha256(CLEAN_MANIFEST).hexdigest()


def profile_bytes(**changes):
    data = {
        "profile_format_version": 1,
        "reader_version": "0.2",
        "status": "DEVELOPMENT / NOT FOR SCORING",
        "confidence_floor": 0.75,
        "margin_floor": 0.20,
        "locator_id": "synthetic-locator-v1",
        "locator_sha256": LOCATOR_HASH,
        "classifier_id": "synthetic-classifier-v1",
        "classifier_sha256": CLASSIFIER_HASH,
        "clean_render_corpus_id": "frozen-clean-renders-v1",
        "clean_render_source_commit": CLEAN_SOURCE_COMMIT,
        "clean_render_manifest_sha256": CLEAN_MANIFEST_HASH,
        "training_partition_id": "synthetic-training-v1",
        "training_partition_source_commit": SOURCE_COMMIT,
        "training_partition_sha256": PARTITION_HASH,
        "reader_code_commit": SOURCE_COMMIT,
        "alphabet": ALPHABET,
    }
    data.update(changes)
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def corpus(purpose=CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING):
    if purpose is CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING:
        return CorpusDescriptor(SYNTHETIC_MANIFEST)
    if purpose is CorpusPurpose.FROZEN_CLEAN_RENDER:
        return CorpusDescriptor(CLEAN_MANIFEST)
    raw = manifest_bytes(
        f"forbidden-{purpose.value.lower()}",
        purpose,
        SOURCE_COMMIT,
        [("forbidden-frame-001", FRESH_ANCHOR_BYTES)],
    )
    return CorpusDescriptor(raw)


def frame_input(purpose=CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING):
    if purpose is CorpusPurpose.FROZEN_CLEAN_RENDER:
        return FrameInput(CLEAN_MEMBER_ID, CLEAN_BYTES)
    if purpose is CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING:
        return FrameInput(SYNTHETIC_MEMBER_ID, SYNTHETIC_BYTES)
    return FrameInput("forbidden-frame-001", FRESH_ANCHOR_BYTES)


def located(cells, automatic=True, used_decoy_text=False, used_rig_marks=False, candidates=1):
    return LocatedFooter(
        tuple(cells),
        automatic=automatic,
        used_decoy_text=used_decoy_text,
        used_rig_marks=used_rig_marks,
        candidate_count=candidates,
    )


class Locator:
    artifact_id = "synthetic-locator-v1"
    artifact_sha256 = LOCATOR_HASH

    def __init__(self, factory=None):
        self.factory = factory or (
            lambda layout: located(("2",) * layout.symbol_count)
        )
        self.calls = 0
        self.last_bytes = None

    def locate(self, frame_bytes, layout):
        self.calls += 1
        self.last_bytes = frame_bytes
        return self.factory(layout)


class Classifier:
    artifact_id = "synthetic-classifier-v1"
    artifact_sha256 = CLASSIFIER_HASH

    def classify(self, cell, position):
        if isinstance(cell, ClassificationCandidate):
            return cell
        return ClassificationCandidate(cell, 1.0, 1.0)


def reader(locator=None):
    return ReaderV02(
        ReaderProfile.from_json_bytes(profile_bytes()),
        locator or Locator(),
        Classifier(),
    )


def read_cells(cells, profile=ProfileName.RS72_60, **location_policy):
    locator = Locator(lambda layout: located(cells, **location_policy))
    return reader(locator).read(frame_input(), profile, corpus())


class ConstantsTests(unittest.TestCase):
    def test_exact_alphabet(self):
        self.assertEqual(ALPHABET, "23456789abcdefghijkmnpqrstuvwxyz")
        self.assertEqual(len(ALPHABET), 32)

    def test_exact_profiles_and_line_lengths(self):
        actual = {
            name.value: (layout.symbol_count, layout.line_lengths)
            for name, layout in PROFILE_LAYOUTS.items()
        }
        self.assertEqual(
            actual,
            {
                "Rs72_60": (116, (64, 52)),
                "Rs76_60": (122, (64, 58)),
                "Rs80_60": (128, (64, 64)),
            },
        )

    def test_unknown_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            layout_for("Rs84_60")


class ProfileTests(unittest.TestCase):
    def test_profile_hashes_exact_input_bytes(self):
        raw = profile_bytes()
        loaded = ReaderProfile.from_json_bytes(raw)
        self.assertEqual(loaded.raw_sha256, hashlib.sha256(raw).hexdigest())

    def test_profile_requires_exact_schema(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            ReaderProfile.from_json_bytes(profile_bytes(extra="forbidden"))

    def test_profile_rejects_alphabet_substitution(self):
        with self.assertRaisesRegex(ValueError, "alphabet"):
            ReaderProfile.from_json_bytes(profile_bytes(alphabet=ALPHABET.upper()))

    def test_profile_rejects_scoring_or_production_status(self):
        with self.assertRaisesRegex(ValueError, "development"):
            ReaderProfile.from_json_bytes(profile_bytes(status="PRODUCTION"))

    def test_profile_rejects_unbound_hash(self):
        with self.assertRaisesRegex(ValueError, "locator_sha256"):
            ReaderProfile.from_json_bytes(profile_bytes(locator_sha256="AA" * 32))

    def test_reader_rejects_locator_binding_mismatch(self):
        loaded = ReaderProfile.from_json_bytes(profile_bytes(locator_sha256="66" * 32))
        with self.assertRaisesRegex(ArtifactBindingError, "locator"):
            ReaderV02(loaded, Locator(), Classifier())

    def test_reader_rejects_classifier_binding_mismatch(self):
        loaded = ReaderProfile.from_json_bytes(profile_bytes(classifier_id="other"))
        with self.assertRaisesRegex(ArtifactBindingError, "classifier"):
            ReaderV02(loaded, Locator(), Classifier())


class CorpusPolicyTests(unittest.TestCase):
    def test_clean_and_synthetic_inputs_are_allowed(self):
        for purpose in (
            CorpusPurpose.FROZEN_CLEAN_RENDER,
            CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING,
        ):
            corpus(purpose).require_reader_use()

    def test_old_format_material_is_morphology_only(self):
        with self.assertRaisesRegex(CorpusPolicyError, "unavailable"):
            corpus(CorpusPurpose.OLD_FORMAT_MORPHOLOGY_REFERENCE).require_reader_use()

    def test_fresh_anchors_are_hard_rejected(self):
        for purpose in (
            CorpusPurpose.FRESH_M19R_ANCHOR,
            CorpusPurpose.REAL_M19R_HOLDOUT,
        ):
            with self.assertRaisesRegex(CorpusPolicyError, "unavailable"):
                corpus(purpose).require_reader_use()

    def test_manifest_hash_is_over_exact_input_bytes(self):
        descriptor = CorpusDescriptor(SYNTHETIC_MANIFEST)
        self.assertEqual(descriptor.manifest_sha256, PARTITION_HASH)

    def test_manifest_descriptor_is_immutable(self):
        descriptor = CorpusDescriptor(SYNTHETIC_MANIFEST)
        with self.assertRaises(FrozenInstanceError):
            descriptor.corpus_id = "relabeled"

    def test_manifest_rejects_bad_source_commit(self):
        raw = manifest_bytes(
            "bad-source",
            CorpusPurpose.FROZEN_CLEAN_RENDER,
            "1" * 39,
            [("member", CLEAN_BYTES)],
        )
        with self.assertRaisesRegex(CorpusPolicyError, "source_commit"):
            CorpusDescriptor(raw)

    def test_manifest_rejects_duplicate_member_identity(self):
        raw = manifest_bytes(
            "duplicates",
            CorpusPurpose.FROZEN_CLEAN_RENDER,
            SOURCE_COMMIT,
            [("same", CLEAN_BYTES), ("same", SYNTHETIC_BYTES)],
        )
        with self.assertRaisesRegex(CorpusPolicyError, "duplicate manifest member"):
            CorpusDescriptor(raw)

    def test_located_footer_policy_attestations_have_no_defaults(self):
        with self.assertRaises(TypeError):
            LocatedFooter(("2",))

    def test_profile_bound_manifest_relabel_stops_before_locator(self):
        relabeled = CorpusDescriptor(
            manifest_bytes(
                "synthetic-training-v1",
                CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING,
                SOURCE_COMMIT,
                [("fresh-anchor-A02", FRESH_ANCHOR_BYTES)],
            )
        )
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        with self.assertRaisesRegex(CorpusPolicyError, "frozen profile"):
            instance.read(
                FrameInput("fresh-anchor-A02", FRESH_ANCHOR_BYTES),
                ProfileName.RS72_60,
                relabeled,
            )
        self.assertEqual(locator.calls, 0)

    def test_mismatched_frame_bytes_stop_before_locator(self):
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        changed = bytes([SYNTHETIC_BYTES[0] ^ 1]) + SYNTHETIC_BYTES[1:]
        with self.assertRaisesRegex(CorpusPolicyError, "SHA-256"):
            instance.read(
                FrameInput(SYNTHETIC_MEMBER_ID, changed),
                ProfileName.RS72_60,
                corpus(),
            )
        self.assertEqual(locator.calls, 0)

    def test_mismatched_member_identity_stops_before_locator(self):
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        with self.assertRaisesRegex(CorpusPolicyError, "member_id"):
            instance.read(
                FrameInput("fresh-anchor-A02", SYNTHETIC_BYTES),
                ProfileName.RS72_60,
                corpus(),
            )
        self.assertEqual(locator.calls, 0)

    def test_arbitrary_frame_object_stops_before_locator(self):
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        with self.assertRaisesRegex(CorpusPolicyError, "exact FrameInput"):
            instance.read(object(), ProfileName.RS72_60, corpus())
        self.assertEqual(locator.calls, 0)

    def test_arbitrary_corpus_object_stops_before_locator(self):
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        with self.assertRaisesRegex(CorpusPolicyError, "exact CorpusDescriptor"):
            instance.read(frame_input(), ProfileName.RS72_60, object())
        self.assertEqual(locator.calls, 0)


class PipelineTests(unittest.TestCase):
    def test_all_profiles_emit_exact_position_counts(self):
        for name, layout in PROFILE_LAYOUTS.items():
            cells = tuple(ALPHABET[i % len(ALPHABET)] for i in range(layout.symbol_count))
            result = read_cells(cells, name)
            self.assertEqual(result.outcome, ReadOutcome.TRANSCRIPT_READY)
            self.assertEqual(len(result.transcript.positions), layout.symbol_count)
            self.assertEqual(result.transcript.text, "".join(cells))

    def test_exact_member_binding_is_recorded_and_passed_to_locator(self):
        locator = Locator()
        result = reader(locator).read(frame_input(), ProfileName.RS72_60, corpus())
        report = result.to_dict()
        self.assertEqual(locator.last_bytes, SYNTHETIC_BYTES)
        self.assertEqual(report["input_member_id"], SYNTHETIC_MEMBER_ID)
        self.assertEqual(report["input_sha256"], hashlib.sha256(SYNTHETIC_BYTES).hexdigest())

    def test_clean_render_binding_is_recorded_in_result(self):
        result = reader().read(
            frame_input(CorpusPurpose.FROZEN_CLEAN_RENDER),
            ProfileName.RS72_60,
            corpus(CorpusPurpose.FROZEN_CLEAN_RENDER),
        )
        report = result.to_dict()
        self.assertEqual(report["corpus_id"], "frozen-clean-renders-v1")
        self.assertEqual(report["corpus_source_commit"], CLEAN_SOURCE_COMMIT)
        self.assertEqual(report["corpus_manifest_sha256"], CLEAN_MANIFEST_HASH)
        self.assertEqual(report["input_member_id"], CLEAN_MEMBER_ID)

    def test_uncertainty_becomes_erasure_never_guess(self):
        layout = layout_for(ProfileName.RS72_60)
        cells = ["2"] * layout.symbol_count
        cells[1] = ClassificationCandidate("a", 0.74, 1.0)
        cells[2] = ClassificationCandidate("b", 1.0, 0.19)
        cells[3] = ClassificationCandidate(None, 1.0, 1.0)
        cells[4] = ClassificationCandidate("A", 1.0, 1.0)
        cells[5] = ClassificationCandidate("0", 1.0, 1.0)
        result = read_cells(tuple(cells))
        self.assertEqual(result.transcript.positions[0], "2")
        self.assertEqual(result.transcript.positions[1:6], (ERASURE,) * 5)

    def test_threshold_equality_is_known(self):
        layout = layout_for(ProfileName.RS72_60)
        cells = ["2"] * layout.symbol_count
        cells[0] = ClassificationCandidate("a", 0.75, 0.20)
        result = read_cells(tuple(cells))
        self.assertEqual(result.transcript.positions[0], "a")

    def test_no_normalization_or_aliasing(self):
        layout = layout_for(ProfileName.RS72_60)
        cells = [ClassificationCandidate("A", 1.0, 1.0)] * layout.symbol_count
        result = read_cells(tuple(cells))
        self.assertEqual(result.transcript.text, ERASURE * layout.symbol_count)

    def test_missing_footer_requests_recapture(self):
        locator = Locator(lambda layout: None)
        result = reader(locator).read(frame_input(), ProfileName.RS72_60, corpus())
        self.assertEqual(result.outcome, ReadOutcome.RECAPTURE_REQUIRED)
        self.assertEqual(result.reason, "FOOTER_NOT_LOCATED")

    def test_wrong_grid_count_requests_recapture(self):
        result = read_cells(("2",))
        self.assertEqual(result.reason, "GRID_POSITION_COUNT_MISMATCH")

    def test_manual_or_candidate_selection_requests_recapture(self):
        layout = layout_for(ProfileName.RS72_60)
        cells = ("2",) * layout.symbol_count
        cases = (
            ({"automatic": False}, "MANUAL_INTERVENTION_FORBIDDEN"),
            ({"candidates": 2}, "CANDIDATE_SELECTION_FORBIDDEN"),
        )
        for policy, expected in cases:
            with self.subTest(expected):
                self.assertEqual(read_cells(cells, **policy).reason, expected)

    def test_decoy_text_and_rig_marks_cannot_be_inputs(self):
        layout = layout_for(ProfileName.RS72_60)
        cells = ("2",) * layout.symbol_count
        cases = (
            ({"used_decoy_text": True}, "DECOY_TEXT_INPUT_FORBIDDEN"),
            ({"used_rig_marks": True}, "RIG_MARK_INPUT_FORBIDDEN"),
        )
        for policy, expected in cases:
            with self.subTest(expected):
                self.assertEqual(read_cells(cells, **policy).reason, expected)

    def test_reader_result_never_claims_authentication(self):
        layout = layout_for(ProfileName.RS72_60)
        result = reader().read(frame_input(), ProfileName.RS72_60, corpus())
        self.assertFalse(result.authenticated)
        self.assertFalse(result.to_dict()["authenticated"])
        with self.assertRaisesRegex(ValueError, "authentication"):
            ReaderResult(
                ReadOutcome.TRANSCRIPT_READY,
                ProfileName.RS72_60,
                "00" * 32,
                "synthetic-training-v1",
                SOURCE_COMMIT,
                PARTITION_HASH,
                SYNTHETIC_MEMBER_ID,
                hashlib.sha256(SYNTHETIC_BYTES).hexdigest(),
                Transcript(ProfileName.RS72_60, ("2",) * layout.symbol_count),
                authenticated=True,
            )

    def test_repeated_read_is_byte_deterministic(self):
        instance = reader()
        first = json.dumps(
            instance.read(frame_input(), ProfileName.RS72_60, corpus()).to_dict(),
            sort_keys=True,
        )
        second = json.dumps(
            instance.read(frame_input(), ProfileName.RS72_60, corpus()).to_dict(),
            sort_keys=True,
        )
        self.assertEqual(first.encode(), second.encode())

    def test_disallowed_corpus_stops_before_locator(self):
        locator = Locator(lambda layout: (_ for _ in ()).throw(AssertionError()))
        instance = reader(locator)
        with self.assertRaises(CorpusPolicyError):
            instance.read(
                frame_input(CorpusPurpose.FRESH_M19R_ANCHOR),
                ProfileName.RS72_60,
                corpus(CorpusPurpose.FRESH_M19R_ANCHOR),
            )
        self.assertEqual(locator.calls, 0)


class IsolationTests(unittest.TestCase):
    def test_package_uses_standard_library_and_relative_imports_only(self):
        package = Path(__file__).resolve().parents[1]
        allowed = {
            "__future__",
            "dataclasses",
            "enum",
            "hashlib",
            "json",
            "typing",
        }
        for path in sorted(package.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], allowed, path.name)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn((node.module or "").split(".")[0], allowed, path.name)

    def test_package_has_no_old_reader_or_codec_constants(self):
        package = Path(__file__).resolve().parents[1]
        banned = (
            "cloakvault_v3",
            "interop.python",
            "from reader",
            "import reader",
            "cv0",
            "RS(83,49)",
            "qpzry9x8gf2tvdw0s3jn54khce6mua7l",
        )
        for path in sorted(package.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for value in banned:
                self.assertNotIn(value, text, f"{path.name} contains {value!r}")


if __name__ == "__main__":
    unittest.main()
