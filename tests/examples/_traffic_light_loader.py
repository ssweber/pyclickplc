from __future__ import annotations

import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_example_module(example_filename: str, module_name: str):
    module_path = Path(__file__).resolve().parents[2] / "examples" / example_filename
    spec = spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load example module from {module_path}")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_traffic_light_example():
    return _load_example_module("traffic_light.py", "traffic_light_example")


def load_sync_clickplc_datetime_example():
    return _load_example_module("sync_clickplc_datetime.py", "sync_clickplc_datetime_example")
