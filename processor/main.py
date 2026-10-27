"""
SynthStrip skull stripping: step 2 of the Clinical Brain MRI Volumetrics
workflow.

For every T1-weighted image (BIDS suffix T1w) of the `t1w` input, runs
FreeSurfer's mri_synthstrip and writes

  OUTPUT_DIR/brain/<sub>_desc-brain_T1w.nii.gz   the skull-stripped image
  OUTPUT_DIR/mask/<sub>_desc-brain_mask.nii.gz   the binary brain mask
  OUTPUT_DIR/brain/provenance.json               what ran, per subject

Each mask is checked with nibabel (non-empty) and the brain volume in mL
(mask voxels x voxel volume) is logged and recorded in provenance.json.

Subjects are independent: a failure is logged and the others continue. The
run fails (exit 1) only when every subject failed, or when no T1w image was
found at all.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from processor.bids_names import by_subject, derived_name, find_input_files, output_dir_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("processor-synthstrip")

APP = "processor-synthstrip"
INPUT = "t1w"
SUFFIXES = ("T1w",)
OUTPUTS = ["brain", "mask"]
VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def app_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return "0.0.0"


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(float(value))
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {parsed}")
    return parsed


def parameters() -> dict:
    return {
        "NO_CSF": env_bool("NO_CSF", False),
        "BORDER_MM": env_int("BORDER_MM", 1, minimum=0),
        "THREADS": env_int("THREADS", 4, minimum=1),
    }


def discover(input_dir: str | os.PathLike) -> dict[str, Path]:
    """Subject label -> T1w file: INPUT_DIR/t1w/ if present, else all of INPUT_DIR by suffix."""
    return by_subject(find_input_files(input_dir, INPUT, SUFFIXES))


def output_names(t1w: str | os.PathLike) -> tuple[str, str]:
    """('sub-01_desc-brain_T1w.nii.gz', 'sub-01_desc-brain_mask.nii.gz') for sub-01_T1w.nii.gz."""
    return derived_name(t1w, "T1w", desc="brain"), derived_name(t1w, "mask", desc="brain")


def synthstrip_command(t1w: Path, brain: Path, mask: Path, params: dict) -> list[str]:
    cmd = [
        "mri_synthstrip",
        "-i", str(t1w),
        "-o", str(brain),
        "-m", str(mask),
        "-b", str(params["BORDER_MM"]),
        "-t", str(params["THREADS"]),
    ]
    if params["NO_CSF"]:
        cmd.append("--no-csf")
    return cmd


def mask_volume(mask_path: str | os.PathLike) -> dict:
    """Voxel count, voxel volume (mm3) and brain volume (mL) of a binary mask."""
    import nibabel as nib
    import numpy as np

    img = nib.load(str(mask_path))
    data = np.asanyarray(img.dataobj)
    voxels = int(np.count_nonzero(data))
    zooms = [float(z) for z in img.header.get_zooms()[:3]]
    voxel_mm3 = float(np.prod(zooms))
    return {
        "shape": [int(s) for s in data.shape],
        "voxelSizeMm": zooms,
        "voxelVolumeMm3": voxel_mm3,
        "maskVoxels": voxels,
        "brainVolumeMl": round(voxels * voxel_mm3 / 1000.0, 3),
    }


def run_subject(subject: str, t1w: Path, brain_dir: Path, mask_dir: Path, params: dict,
                input_dir: Path, output_dir: Path) -> dict:
    brain_name, mask_name = output_names(t1w)
    brain, mask = brain_dir / brain_name, mask_dir / mask_name
    cmd = synthstrip_command(t1w, brain, mask, params)
    record = {
        "subject": subject,
        "inputs": [os.path.relpath(t1w, input_dir)],
        "outputs": [os.path.relpath(brain, output_dir), os.path.relpath(mask, output_dir)],
        "command": cmd,
    }
    started = time.monotonic()
    try:
        log.info("%s: running %s", subject, " ".join(cmd))
        sys.stdout.flush()
        subprocess.run(cmd, check=True)
        for out in (brain, mask):
            if not out.is_file():
                raise RuntimeError(f"mri_synthstrip finished but did not write {out.name}")
        stats = mask_volume(mask)
        if stats["maskVoxels"] == 0:
            raise RuntimeError("brain mask is empty")
        record.update(stats)
        record["status"] = "ok"
    except Exception as exc:  # one subject's failure must not stop the others
        record["status"] = "failed"
        record["error"] = str(exc)
        for out in (brain, mask):  # no half-written files for the next step to trip over
            try:
                out.unlink()
            except FileNotFoundError:
                pass
    record["seconds"] = round(time.monotonic() - started, 1)
    if record["status"] == "ok":
        log.info("%s: brain volume %.1f mL (%d voxels of %.3f mm3, shape %s) in %.0fs -> %s, %s",
                 subject, record["brainVolumeMl"], record["maskVoxels"], record["voxelVolumeMm3"],
                 "x".join(map(str, record["shape"])), record["seconds"], brain_name, mask_name)
    else:
        log.error("%s: FAILED after %.0fs: %s", subject, record["seconds"], record["error"])
    return record


def list_tree(root: Path, limit: int = 50) -> list[str]:
    files = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    if len(files) > limit:
        files = files[:limit] + [f"... and {len(files) - limit} more"]
    return files


def main() -> int:
    input_dir = os.environ.get("INPUT_DIR")
    output_dir = os.environ.get("OUTPUT_DIR")
    if not input_dir or not output_dir:
        log.error("INPUT_DIR and OUTPUT_DIR must be set")
        return 2
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    if not input_dir.is_dir():
        log.error("INPUT_DIR %s is not a folder", input_dir)
        return 2
    try:
        params = parameters()
    except ValueError as exc:
        log.error("bad parameter: %s", exc)
        return 2

    started_at = datetime.now(timezone.utc)
    brain_dir = output_dir_for(output_dir, OUTPUTS, "brain")
    mask_dir = output_dir_for(output_dir, OUTPUTS, "mask")

    subjects = discover(input_dir)
    where = f"{INPUT}/" if (input_dir / INPUT).is_dir() else "root"
    if not subjects:
        log.error("no T1w image (*_T1w.nii.gz or *_T1w.nii) found in %s (looked in %s). Files present: %s",
                  input_dir, where, ", ".join(list_tree(input_dir)) or "none")
        return 1
    log.info("%s v%s, SynthStrip %s; %d subject(s) found in %s; parameters %s",
             APP, app_version(), os.environ.get("SYNTHSTRIP_VERSION", "unknown"), len(subjects), where, params)

    records = [run_subject(sub, t1w, brain_dir, mask_dir, params, input_dir, output_dir)
               for sub, t1w in subjects.items()]
    ok = [r for r in records if r["status"] == "ok"]

    provenance = {
        "app": APP,
        "appVersion": app_version(),
        "tool": "SynthStrip (mri_synthstrip)",
        "toolVersion": os.environ.get("SYNTHSTRIP_VERSION", "unknown"),
        "modelVersion": "1",
        "startedAt": started_at.isoformat(),
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "parameters": params,
        "inputsFoundIn": where,
        "subjects": records,
    }
    with open(brain_dir / "provenance.json", "w") as fh:
        json.dump(provenance, fh, indent=2)

    log.info("%d of %d subject(s) succeeded; provenance at %s", len(ok), len(records), brain_dir / "provenance.json")
    if not ok:
        log.error("every subject failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
