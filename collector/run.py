"""Started by the widget every 60 s. Checks the Python version first: the collector needs 3.10."""

import json
import os
import sys

if sys.version_info < (3, 10):
    print(json.dumps({"envelope": 1, "error": "python-too-old",
                      "version": "%d.%d.%d" % tuple(sys.version_info[:3])}))
    sys.exit(3)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from limit_rings import widget  # noqa: E402

sys.exit(widget.main())
