"""External benchmark harness (Track B).

This package hosts reusable external benchmark logic that is intentionally kept
separate from the Track A (in-project synthetic) evaluation harness under
``src/evaluation``. Track B benchmarks run against publicly published datasets
(e.g. the UCI "Condition monitoring of hydraulic systems" dataset) and never
touch the Track A modules, docs, or evidence contracts.
"""
