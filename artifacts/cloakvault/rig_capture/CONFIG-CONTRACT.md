# QK rig-capture configuration contract v1

Status: `HOST BENCH SCAFFOLD - NON-CORPUS ONLY - NO DEFAULT RIG CONSTANTS`

The input is one UTF-8 JSON object. Its exact file bytes are SHA-256 hashed
before parsing and must equal the lowercase 64-hex digest supplied separately
on the command line. The runner also records a canonical hash of each
settings, geometry and software object plus the fixed empty child environment.
These subhashes aid comparison; the raw configuration hash remains the
complete binding.

No field below has a default. Unknown schema fields at the root, adapter,
controls, geometry, settings and capture-record levels reject so a future
widening is visible. `authorization` and `software` are caller-defined
nonempty records whose complete content is bound by the raw configuration
hash. Settings and adapters have the closed schemas below.

## Root object

| Field | Required value |
|---|---|
| `contract_version` | Exact scaffold schema label `QK-RIG-CAPTURE-G0-V1` |
| `purpose` | `MOCK` or `PREFLIGHT`; neither is scheduled corpus evidence |
| `corpus` | Boolean `false`; `true` rejects |
| `session_id` | Caller-supplied filename-safe identity |
| `source_commit` | Exact lowercase 40-hex Protocol-Lab source commit |
| `camera_class` | Caller-supplied observed/planned class label; never inferred |
| `authorization` | Nonempty record of the exact non-corpus execution authority |
| `software` | Nonempty object of exact program/OS/stack versions and identities |
| `settings` | Exact purpose-specific object described below |
| `geometry` | Exact object described below |
| `adapter` | Exact executable contract described below |
| `controls` | Positive caller-supplied `timeout_seconds` and `max_output_bytes` |
| `captures` | Nonempty ordered list of exact capture records |

`timeout_seconds` and `max_output_bytes` are per-invocation HOST safety
controls. They are supplied every time, have no repository default and imply
no camera, product, retry, APDU or QK-LIM value.

## Settings object

For `MOCK`, the exact keys are `output_extension` (exact `mock`) and
`producer_behavior`; the latter is one of the public fake outcomes exercised
by the tests. For `PREFLIGHT`, `output_extension` is exact `jpg` and all of
these caller-supplied values are mandatory:

- `camera_index`, `width_px`, `height_px`, `jpeg_quality`;
- `capture_timeout_ms`, `shutter_us`, `analogue_gain`;
- `awb_gain_red`, `awb_gain_blue`, `lens_position`;
- `rotation_degrees`, `horizontal_flip`, `vertical_flip`; and
- `denoise_mode`.

Counts are positive except the camera index and lens position, which may be
zero. JPEG quality is 1 through 100; rotation is 0 or 180; flips are Boolean;
denoise is one of `auto`, `off`, `cdn_off`, `cdn_fast`, or `cdn_hq`; and every
decimal is finite. Time values are rendered with explicit `ms` and `us`
suffixes in the command. These are validation domains, not selected rig values. Every
preflight configuration supplies the values expressly, and the owed
rig-amendment row later pins the scheduled-corpus settings.

## Geometry object

All of these keys are mandatory and their values are supplied by rig
preflight. The scaffold chooses none of them:

- `jig_revision`
- `camera_to_page_distance_mm`
- `page_fill_percent`
- `page_orientation`
- `camera_mount_definition`
- `page_plane_definition`
- `fiducial_specification`
- `scale_bar_length_mm`
- `scale_bar_placement`
- `lighting_geometry`

Each value must be a nonempty string or a finite JSON number. Requiring these
names does not ratify their values. The owed rig-amendment row later records
the corpus constants.

## Adapter object

The adapter is purpose-bound. `MOCK` requires exactly:

| Field | Required value |
|---|---|
| `interface` | Exact `PUBLIC-MOCK-CAPTURE-V1` |
| `working_directory` | Absolute existing nonsymlink directory; no process is launched |

`PREFLIGHT` requires exactly:

| Field | Required value |
|---|---|
| `interface` | Exact `RPICAM-STILL-CAPTURE-V1` |
| `working_directory` | Absolute existing nonsymlink directory used as the fixed child working directory |
| `executable_path` | Absolute existing executable regular nonsymlink file whose basename is exact `rpicam-still` |
| `executable_sha256` | Lowercase SHA-256 of that exact file, checked before and after each output |

The runner supplies the full argument list: fixed capture-only flags, every
closed settings value and one final output path. It accepts no caller argument
array, input path, plug-in, post-process file, support script or environment.
It uses no shell and gives the child an empty environment. The only physical
interface is therefore the registered `rpicam-still` binary and a scalar
camera configuration; changing the sensor class from the Owner's ZeroCam to
Camera Module 3 does not widen the program interface.

## Capture record

Every record has exactly `capture_id`, `page_id`, `attempt`, and `sequence`.
Identifiers use uppercase ASCII letters, digits and hyphens. `attempt` is a
positive integer; `sequence` is a nonnegative integer. Capture IDs, sequences
and resulting names must be unique. The output extension is the required
`settings.output_extension` lowercase alphanumeric value.

The deterministic name is:

```text
qk-rig-g0-v1__<session_id>__s<sequence>__<capture_id>__<page_id>__a<attempt>.<extension>
```

No content-derived page identity is permitted. The runner processes the
listed order serially and never has more than one expected output path active.

## Manifest

The runner writes
`qk-rig-g0-v1__<session_id>__manifest.json` only after every capture succeeds.
The CLI output-directory argument must be absolute and must not exist before
the run; this keeps the child working directory from changing output-path
resolution.
It is canonical compact JSON (sorted keys, UTF-8, one final LF) and contains:

- contract/purpose/non-corpus/source/session/camera labels;
- adapter interface plus raw configuration, executable, software, settings,
  geometry and fixed-empty-environment SHA-256 values;
- for every capture, its registered identifiers, deterministic filename,
  start/end UTC timestamps, byte count and SHA-256; and
- fixed statements `decode_performed=false` and
  `payload_bytes_recorded_in_manifest=false`.

The manifest never contains capture payload bytes or command stdout/stderr.
An invocation failure emits a category to stderr, leaves no success manifest
and never retries. `decode_performed=false` is structural: neither adapter has
an input-image or decoder hook, and the physical command admits only camera
capture settings and its output path. The scaffold makes no acceptance
judgment about images.
