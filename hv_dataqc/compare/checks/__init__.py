"""Check implementations for the compare pipeline.

One file per check family. Each check function takes some combination of
source/harmonized summaries plus a match dict from the crosswalk, and
returns a list of CheckResult.

The check-function entry points are imported by hv_dataqc.compare's main
orchestrator. Helpers internal to a single check family stay private to
their family module.
"""
