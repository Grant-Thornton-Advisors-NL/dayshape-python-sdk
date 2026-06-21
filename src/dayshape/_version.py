"""Single source of truth for the package version.

``SPEC_VERSION`` records the three authoritative source artefacts the SDK was
generated against, per plan.md §9.
"""

from __future__ import annotations

__version__ = "0.3.0"

#: The spec artefacts this build was generated/validated against.
SPEC_VERSION = {
    "workbook": "26.3.0",  # Dayshape Reporting Service Detail
    "api_doc": "R2",  # Reporting Service API Documentation (March 2025)
    "openapi": "v2",  # Reporting Service Payloads (v2)
}
