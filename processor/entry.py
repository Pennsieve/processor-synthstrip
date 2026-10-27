"""Container entrypoint: runs main() once and exits with its code."""
import sys

from processor.main import main

sys.exit(main())
