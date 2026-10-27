"""
Unit tests for the parts that don't need mri_synthstrip: input discovery in
both layouts, output naming, the command line, parameters, and the mask volume
(needs nibabel; skipped without it). `make test` runs them inside the image.
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from processor import main as app


def touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


class DiscoveryTest(unittest.TestCase):
    def test_root_layout_finds_t1w_by_suffix_recursively(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            touch(root / "sub-01_T1w.nii.gz")
            touch(root / "sub-02" / "anat" / "sub-02_T1w.nii")
            touch(root / "sub-01_FLAIR.nii.gz")      # other suffix: ignored
            touch(root / "sub-01_T1w.json")          # sidecar: ignored
            found = app.discover(root)
            self.assertEqual(sorted(found), ["sub-01", "sub-02"])
            self.assertEqual(found["sub-01"], root / "sub-01_T1w.nii.gz")
            self.assertEqual(found["sub-02"], root / "sub-02" / "anat" / "sub-02_T1w.nii")

    def test_linked_layout_takes_precedence_over_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            touch(root / "t1w" / "sub-03_T1w.nii.gz")
            touch(root / "t1w" / "nested" / "sub-04_T1w.nii.gz")
            touch(root / "sub-01_T1w.nii.gz")        # stray file at the root: not used
            found = app.discover(root)
            self.assertEqual(sorted(found), ["sub-03", "sub-04"])

    def test_nothing_found(self):
        with tempfile.TemporaryDirectory() as d:
            touch(Path(d) / "notes.txt")
            self.assertEqual(app.discover(d), {})


class NamingTest(unittest.TestCase):
    def test_output_names(self):
        self.assertEqual(app.output_names("sub-01_T1w.nii.gz"),
                         ("sub-01_desc-brain_T1w.nii.gz", "sub-01_desc-brain_mask.nii.gz"))
        self.assertEqual(app.output_names("/in/sub-010200_acq-mprage_T1w.nii"),
                         ("sub-010200_desc-brain_T1w.nii.gz", "sub-010200_desc-brain_mask.nii.gz"))

    def test_command_flags(self):
        params = {"NO_CSF": False, "BORDER_MM": 1, "THREADS": 4}
        cmd = app.synthstrip_command(Path("/in/a_T1w.nii.gz"), Path("/out/b.nii.gz"), Path("/out/m.nii.gz"), params)
        self.assertEqual(cmd, ["mri_synthstrip", "-i", "/in/a_T1w.nii.gz", "-o", "/out/b.nii.gz",
                               "-m", "/out/m.nii.gz", "-b", "1", "-t", "4"])
        params["NO_CSF"] = True
        self.assertEqual(app.synthstrip_command(Path("x"), Path("y"), Path("z"), params)[-1], "--no-csf")


class ParameterTest(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(app.parameters(), {"NO_CSF": False, "BORDER_MM": 1, "THREADS": 4})

    def test_values(self):
        with mock.patch.dict(os.environ, {"NO_CSF": "True", "BORDER_MM": "3", "THREADS": "2"}):
            self.assertEqual(app.parameters(), {"NO_CSF": True, "BORDER_MM": 3, "THREADS": 2})

    def test_bad_value(self):
        with mock.patch.dict(os.environ, {"BORDER_MM": "wide"}):
            self.assertRaises(ValueError, app.parameters)
        with mock.patch.dict(os.environ, {"THREADS": "0"}):
            self.assertRaises(ValueError, app.parameters)


class MainTest(unittest.TestCase):
    def test_no_input_exits_1_and_creates_output_folders(self):
        with tempfile.TemporaryDirectory() as d:
            inp, out = Path(d) / "in", Path(d) / "out"
            touch(inp / "readme.txt")
            with mock.patch.dict(os.environ, {"INPUT_DIR": str(inp), "OUTPUT_DIR": str(out)}):
                self.assertEqual(app.main(), 1)
            self.assertTrue((out / "brain").is_dir())
            self.assertTrue((out / "mask").is_dir())


class MaskVolumeTest(unittest.TestCase):
    def test_volume_from_mask(self):
        try:
            import nibabel as nib
            import numpy as np
        except ImportError:
            self.skipTest("nibabel not installed")
        data = np.zeros((10, 10, 10), dtype=np.uint8)
        data[2:7, 2:7, 2:6] = 1                       # 5*5*4 = 100 voxels
        affine = np.diag([2.0, 2.0, 2.0, 1.0])        # 8 mm3 per voxel
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub-01_desc-brain_mask.nii.gz"
            nib.save(nib.Nifti1Image(data, affine), str(path))
            stats = app.mask_volume(path)
        self.assertEqual(stats["maskVoxels"], 100)
        self.assertAlmostEqual(stats["voxelVolumeMm3"], 8.0)
        self.assertAlmostEqual(stats["brainVolumeMl"], 0.8)
        self.assertEqual(stats["shape"], [10, 10, 10])


if __name__ == "__main__":
    unittest.main()
