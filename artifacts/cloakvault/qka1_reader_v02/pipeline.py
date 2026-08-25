"""Deterministic one-frame Reader v0.2 transcript pipeline."""

from __future__ import annotations

from .constants import ALPHABET, ERASURE, layout_for
from .interfaces import CellClassifier, FooterLocator, LocatedFooter, LocationFailure
from .model import ReadOutcome, ReaderResult, Transcript
from .policy import CorpusDescriptor, CorpusPolicyError, CorpusPurpose, FrameInput
from .profile import ReaderProfile


class ArtifactBindingError(ValueError):
    pass


def _bound(actual_id: str, actual_sha256: str, expected_id: str, expected_sha256: str) -> bool:
    return actual_id == expected_id and actual_sha256 == expected_sha256


class ReaderV02:
    """One automatic frame-to-transcript pass with injected image algorithms."""

    def __init__(
        self,
        profile: ReaderProfile,
        locator: FooterLocator,
        classifier: CellClassifier,
    ) -> None:
        if not _bound(
            locator.artifact_id,
            locator.artifact_sha256,
            profile.locator_id,
            profile.locator_sha256,
        ):
            raise ArtifactBindingError("locator does not match the frozen profile")
        if not _bound(
            classifier.artifact_id,
            classifier.artifact_sha256,
            profile.classifier_id,
            profile.classifier_sha256,
        ):
            raise ArtifactBindingError("classifier does not match the frozen profile")
        if (
            classifier.training_corpus_manifest_sha256
            != profile.training_corpus_manifest_sha256
            or classifier.training_partition_id != profile.training_partition_id
            or classifier.training_partition_sha256
            != profile.training_partition_sha256
        ):
            raise ArtifactBindingError(
                "classifier training partition does not match the frozen profile"
            )
        self._profile = profile
        self._locator = locator
        self._classifier = classifier

    def read(
        self,
        frame: FrameInput,
        corpus: CorpusDescriptor,
    ) -> ReaderResult:
        if type(corpus) is not CorpusDescriptor:
            raise CorpusPolicyError("reader corpus must be an exact CorpusDescriptor")
        corpus.require_reader_use()
        self._require_bound_corpus(corpus)
        input_sha256 = corpus.require_member(frame)
        located = self._locator.locate(frame.data)
        reason = self._location_rejection(located)
        if reason is not None:
            return ReaderResult(
                outcome=ReadOutcome.RECAPTURE_REQUIRED,
                profile=None,
                profile_sha256=self._profile.raw_sha256,
                corpus_id=corpus.corpus_id,
                corpus_source_commit=corpus.source_commit,
                corpus_manifest_sha256=corpus.manifest_sha256,
                input_member_id=frame.member_id,
                input_sha256=input_sha256,
                reason=reason,
            )

        assert isinstance(located, LocatedFooter)
        layout = layout_for(located.profile)
        positions = []
        for position, cell in enumerate(located.cells):
            candidate = self._classifier.classify(cell, position)
            known = (
                candidate.symbol is not None
                and candidate.symbol in ALPHABET
                and candidate.confidence >= self._profile.confidence_floor
                and candidate.margin >= self._profile.margin_floor
            )
            positions.append(candidate.symbol if known else ERASURE)
        transcript = Transcript(layout.profile, tuple(positions))
        return ReaderResult(
            outcome=ReadOutcome.TRANSCRIPT_READY,
            profile=layout.profile,
            profile_sha256=self._profile.raw_sha256,
            corpus_id=corpus.corpus_id,
            corpus_source_commit=corpus.source_commit,
            corpus_manifest_sha256=corpus.manifest_sha256,
            input_member_id=frame.member_id,
            input_sha256=input_sha256,
            transcript=transcript,
        )

    def _require_bound_corpus(self, corpus: CorpusDescriptor) -> None:
        if corpus.purpose is CorpusPurpose.FROZEN_CLEAN_RENDER:
            expected = (
                self._profile.clean_render_corpus_id,
                self._profile.clean_render_source_commit,
                self._profile.clean_render_manifest_sha256,
            )
        else:
            expected = (
                self._profile.training_corpus_id,
                self._profile.training_corpus_source_commit,
                self._profile.training_corpus_manifest_sha256,
            )
        actual = (corpus.corpus_id, corpus.source_commit, corpus.manifest_sha256)
        if actual != expected:
            raise CorpusPolicyError("corpus does not match the frozen profile binding")

    @staticmethod
    def _location_rejection(
        located: LocatedFooter | LocationFailure | None,
    ) -> str | None:
        if located is None:
            return "FOOTER_NOT_LOCATED"
        if isinstance(located, LocationFailure):
            return located.reason
        if not located.automatic:
            return "MANUAL_INTERVENTION_FORBIDDEN"
        if located.used_decoy_text:
            return "DECOY_TEXT_INPUT_FORBIDDEN"
        if located.used_rig_marks:
            return "RIG_MARK_INPUT_FORBIDDEN"
        if located.candidate_count != 1:
            return "CANDIDATE_SELECTION_FORBIDDEN"
        if len(located.cells) != layout_for(located.profile).symbol_count:
            return "GRID_POSITION_COUNT_MISMATCH"
        return None
