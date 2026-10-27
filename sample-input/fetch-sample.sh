#!/usr/bin/env sh
# Fetch one T1w image (OpenNeuro ds000117, sub-01, CC0) into data/input/.
set -eu
cd "$(dirname "$0")/.."
mkdir -p data/input
aws s3 cp --no-sign-request \
  s3://openneuro.org/ds000117/sub-01/ses-mri/anat/sub-01_ses-mri_T1w.nii.gz \
  data/input/sub-01_T1w.nii.gz
ls -l data/input
