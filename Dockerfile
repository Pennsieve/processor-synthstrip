# SynthStrip 1.8 (FreeSurfer): CPU build, amd64 only, model weights bundled at
# /freesurfer/models. The image ships Python 3.10 with torch, surfa and nibabel,
# so the processor runs in that interpreter and installs nothing.
FROM freesurfer/synthstrip:1.8

ENV SYNTHSTRIP_VERSION=1.8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/processor

WORKDIR /processor
COPY VERSION /processor/VERSION
COPY processor/ /processor/processor/

# The base image's entrypoint is mri_synthstrip itself; ours runs the processor
# (which calls mri_synthstrip from PATH) once over INPUT_DIR.
ENTRYPOINT ["python3", "-m", "processor.entry"]
