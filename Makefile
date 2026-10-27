.PHONY: help build test run clean

SERVICE_NAME ?= processor-synthstrip
IMAGE ?= $(SERVICE_NAME):local
# The base image is amd64 only; on Apple silicon this runs under emulation.
export DOCKER_DEFAULT_PLATFORM ?= linux/amd64

.DEFAULT: help

help:
	@echo "Make Help for $(SERVICE_NAME)"
	@echo ""
	@echo "make build  - build the image ($(IMAGE))"
	@echo "make test   - run the unit tests (input discovery, naming, mask volume) inside the image"
	@echo "make run    - run the processor in Docker over data/input/, writing to data/output/"
	@echo "make clean  - remove data/output/"

build:
	docker build --platform linux/amd64 -t $(IMAGE) .

test: build
	docker run --rm --platform linux/amd64 -v "$(CURDIR)/tests:/tests:ro" \
		--entrypoint python3 $(IMAGE) -m unittest discover -s /tests -v

run: clean
	@test -n "$$(ls data/input 2>/dev/null)" || { echo "data/input/ is empty: see sample-input/README.md"; exit 1; }
	docker compose -f docker-compose.yml down --remove-orphans
	docker compose -f docker-compose.yml build
	docker compose -f docker-compose.yml up --exit-code-from processor
	@find data/output -type f | sort
	@cat data/output/brain/provenance.json

clean:
	rm -rf data/output
