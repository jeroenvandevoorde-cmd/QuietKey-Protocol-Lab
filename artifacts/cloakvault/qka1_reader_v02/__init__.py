"""Isolated QKA1 Reader v0.2 contract scaffold.

This package stops at a fixed-position symbol/erasure transcript.  Protocol
decoding and authentication belong to a separately authored adapter.
"""

from .constants import ALPHABET, ERASURE, PROFILE_LAYOUTS, ProfileName
from .image import GrayImage, decode_png
from .interfaces import LocationFailure
from .model import ReadOutcome, ReaderResult, Transcript
from .pipeline import ReaderV02
from .policy import CorpusDescriptor, CorpusPurpose, FrameInput
from .profile import ReaderProfile
from .templates import TemplateClassifier
from .vision import DeterministicLocator

__all__ = [
    "ALPHABET",
    "ERASURE",
    "PROFILE_LAYOUTS",
    "CorpusDescriptor",
    "CorpusPurpose",
    "FrameInput",
    "GrayImage",
    "LocationFailure",
    "ProfileName",
    "ReadOutcome",
    "ReaderProfile",
    "ReaderResult",
    "ReaderV02",
    "TemplateClassifier",
    "Transcript",
    "DeterministicLocator",
    "decode_png",
]
