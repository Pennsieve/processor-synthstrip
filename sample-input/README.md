# Sample input

No NIfTI files are committed (they are too large). Fetch one T1-weighted image
from OpenNeuro (CC0) into `data/input/` with:

```sh
./sample-input/fetch-sample.sh          # ds000117 sub-01, ~11 MB
```

This downloads `sub-01_T1w.nii.gz` with `aws s3 cp --no-sign-request` (no AWS
account needed) and renames it to the `<sub>_T1w.nii.gz` form the app expects.
Then `make run`.

To try the linked layout (what a workflow with a linked `t1w` input gives the
app), put the file in `data/input/t1w/` instead; the app looks there first.
