# processor-synthstrip

Skull stripping for T1-weighted brain MRI with **SynthStrip 1.8** (FreeSurfer):
step 2 of the *Clinical Brain MRI Volumetrics* workflow on Pennsieve.

SynthStrip is a learning-based brain extractor that works on images of any
contrast and resolution ([Hoopes et al. 2022](https://doi.org/10.1016/j.neuroimage.2022.119474),
<https://surfer.nmr.mgh.harvard.edu/docs/synthstrip/>). For every T1w image
the app runs `mri_synthstrip` and writes the brain-extracted image and the
binary brain mask, named so the next steps (N4, registration, volumetrics)
find them by subject. It also checks each mask with nibabel and records the
brain volume in mL.

The image is `FROM freesurfer/synthstrip:1.8` (amd64, CPU, model weights
bundled), so it needs no network at run time. See `THIRD_PARTY.md` for the
FreeSurfer licence: SynthStrip is **for research purposes only**.

## Ports

| Port | Name | Takes / gives | Where |
|---|---|---|---|
| input | `t1w` | `<sub>_T1w.nii.gz` or `.nii`, one per subject (`application/x-nifti-gz`, `application/x-nifti`), required | `INPUT_DIR/t1w/` when a workflow links it; otherwise anywhere under `INPUT_DIR` (found recursively by the BIDS suffix `T1w`) |
| output | `brain` | `<sub>_desc-brain_T1w.nii.gz`, the skull-stripped image, plus `provenance.json` | `OUTPUT_DIR/brain/` |
| output | `mask` | `<sub>_desc-brain_mask.nii.gz`, the binary brain mask | `OUTPUT_DIR/mask/` |

The subject label is everything before the first `_` of the input file name
(`sub-01_T1w.nii.gz` → `sub-01`); files named differently are skipped with a
message. Files with the same name in several folders are taken once.

## Parameters

| Parameter | Type | Default | `mri_synthstrip` flag | |
|---|---|---|---|---|
| `NO_CSF` | boolean | `false` | `--no-csf` | Exclude CSF from the brain boundary (uses the no-CSF model) |
| `BORDER_MM` | integer | `1` | `-b` | Mask border threshold in mm; larger keeps more tissue |
| `THREADS` | integer | `4` | `-t` | PyTorch CPU threads |

Per subject the app runs

```
mri_synthstrip -i <in>_T1w.nii.gz -o brain/<sub>_desc-brain_T1w.nii.gz -m mask/<sub>_desc-brain_mask.nii.gz -b <BORDER_MM> -t <THREADS> [--no-csf]
```

## Behaviour

- Subjects are processed one after another and independently: a subject whose
  run fails (or whose mask comes out empty) is logged, its partial outputs are
  removed, and the others continue. The run exits 1 only when **every**
  subject failed, or when no T1w image was found at all (the log then lists
  what was in `INPUT_DIR`).
- `OUTPUT_DIR/brain/provenance.json` records `app`, `appVersion`, `tool`,
  `toolVersion`, `startedAt`/`finishedAt`, the `parameters` used, and per
  subject: `inputs`, `outputs`, `command`, `seconds`, `status`, and from the
  mask `shape`, `voxelSizeMm`, `voxelVolumeMm3`, `maskVoxels` and
  `brainVolumeMl` (mask voxels × voxel volume).
- One log line per subject reports the brain volume and runtime.

## Runtime

`computeTypes: [standard]` only (container, no Lambda): 2 vCPU, 8 GiB,
30 min timeout. One 1 mm T1w takes under a minute on an x86 machine and
roughly 1 GB of RAM; see the measured numbers at the end of this file.

## Running it locally

The base image is amd64 only; on Apple silicon the Makefile and compose file
set `--platform linux/amd64`, and a run takes several minutes under emulation.

```sh
./sample-input/fetch-sample.sh   # one T1w from OpenNeuro (CC0) into data/input/
make test                        # unit tests (discovery, naming, volume) inside the image
make run                         # skull-strip data/input/ into data/output/
```

or by hand:

```sh
docker build --platform linux/amd64 -t processor-synthstrip .
docker run --rm --platform linux/amd64 --user 1000:1000 \
  -e INPUT_DIR=/data/input -e OUTPUT_DIR=/data/output \
  -e NO_CSF=false -e BORDER_MM=1 -e THREADS=4 \
  -v "$PWD/data/input:/data/input:ro" -v "$PWD/data/output:/data/output" \
  processor-synthstrip
```

To try the linked layout, put the file under `data/input/t1w/` instead.

## Citation

If you use the outputs of this app, cite SynthStrip:

> Hoopes A, Mora JS, Dalca AV, Fischl B, Hoffmann M. SynthStrip: skull-stripping for any
> brain image. *NeuroImage* 2022; 260:119474. https://doi.org/10.1016/j.neuroimage.2022.119474

## Licence

The wrapper code in this repository is Apache-2.0 (`LICENSE`). SynthStrip and
FreeSurfer are distributed under the FreeSurfer Software License (research use
only); the model weights are MIT / CC BY 4.0. See `THIRD_PARTY.md`.
