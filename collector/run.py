"""Started by the widget every 60 s (with --status: the last collected limits for scripts, see status.py).

Checks the Python version first: the collector needs 3.10."""

import json
import os
import sys

if sys.version_info < (3, 10):
    print(json.dumps({"envelope": 1, "error": "python-too-old",
                      "version": "%d.%d.%d" % tuple(sys.version_info[:3])}))
    sys.exit(3)

sys.dont_write_bytecode = True  # package updates keep the zip mtimes: a stale .pyc could outlive its source
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if "--status" in sys.argv[1:]:  # the last collected limits for scripts and bars: reads stats.json only
    from limit_rings import status  # noqa: E402
    sys.exit(status.main(sys.argv[1:]))

from limit_rings import widget  # noqa: E402

sys.exit(widget.main())
