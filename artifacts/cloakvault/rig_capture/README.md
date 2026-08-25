# Camera-rig capture scaffold

Status: `HOST BENCH SCAFFOLD - NON-CORPUS ONLY - NO DECODER`

This subtree is the capture-only groundwork for the ZeroCam bring-up and the
later Camera Module 3 standard rig. It chooses no distance, exposure, focus,
geometry, fiducial, scale-bar, lighting or software value. Its only physical
adapter is the closed `RPICAM-STILL-CAPTURE-V1` command shape. The intended
ZeroCam and Camera Module 3 paths use that same interface; actual compatibility
remains a preflight fact. The sensor class and all preflight settings are
configuration data, so the later sensor swap is designed not to add a new
runner or caller-controlled command surface.

The runner accepts only `MOCK` and `PREFLIGHT` purposes and requires
`corpus=false`. It cannot authorize a scheduled M19-R capture. Enabling corpus
capture requires the owed rig-amendment row and a later source change. No
decode, OCR, image transformation, scoring, calibration fit or Reader import
exists here. Capture output is treated as opaque bytes. The runner accepts no
input-image path, caller argument array, plug-in/support script or child
environment. It constructs the complete `rpicam-still` invocation itself from
a closed scalar settings object and the one output path; this is the structural
basis for `decode_performed=false` in the manifest.

## Files

- `CONFIG-CONTRACT.md` defines the complete, no-default configuration and
  invocation contract.
- `rig_capture.py` validates a hash-pinned configuration, verifies the exact
  `rpicam-still` executable for preflight, constructs deterministic names and
  the closed camera command, captures one opaque output at a time, hashes it
  and writes one canonical JSON manifest. Its second adapter is an in-process
  deterministic public mock with no executable hook.
- `tests/test_rig_capture.py` exercises only the in-process public mock and
  command construction in temporary directories. It performs no camera,
  network, corpus or decoder operation.

## Non-corpus invocation shape

The operator first computes the SHA-256 of the exact configuration bytes with
the separately registered procedure. Validation is non-executing:

```text
python3 rig_capture.py validate CONFIG.json EXPECTED_CONFIG_SHA256
```

A later authorized non-corpus preflight can use:

```text
python3 rig_capture.py run CONFIG.json EXPECTED_CONFIG_SHA256 ABSOLUTE_OUTPUT_DIRECTORY
```

`run` requires an absolute, new output-directory path and refuses an existing
directory, a changed executable,
a missing/empty/symlink output, a second page in flight, and any configuration
marked as corpus. The fixed physical command never receives a shell, caller
arguments, support scripts or inherited environment variables. Its exact
working directory is mandatory and hash-bound with the rest of the
configuration.

This scaffold does not claim Camera Module 3 results, O01/O02 evidence, sealed
O01-stack equivalence, Gate A closure or any product retry/font/geometry
value. It also does not touch the frozen M19-R or Reader v0.2 subtrees.
