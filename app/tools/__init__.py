"""
Importing this package registers every tool module's decorated
functions into app.enforcement.registry. Nothing else in the codebase
should import an individual tools submodule directly; import
app.tools once, at startup, and use the registry from there.

Adding a new tool: write the function in the relevant module (or a
new one) with the @tool decorator from app.enforcement, then add the
module to the imports below. Forgetting this step means the tool
exists in Python but Claude never sees it and the harness never calls
it, a silent failure worth checking for in code review.
"""

from app.tools import audit  # noqa: F401
from app.tools import consistency  # noqa: F401
from app.tools import cover_letter  # noqa: F401
from app.tools import delivery  # noqa: F401
from app.tools import docx_checks  # noqa: F401
from app.tools import docx_render  # noqa: F401
from app.tools import final_review  # noqa: F401
from app.tools import formatting  # noqa: F401
from app.tools import harness_meta  # noqa: F401
from app.tools import intake  # noqa: F401
from app.tools import foundational_build  # noqa: F401
from app.tools import page_estimate  # noqa: F401
from app.tools import profile  # noqa: F401
from app.tools import redaction  # noqa: F401
from app.tools import registry_tools  # noqa: F401
from app.tools import security  # noqa: F401
from app.tools import slop  # noqa: F401
from app.tools import slop_advanced  # noqa: F401
from app.tools import tailoring  # noqa: F401
from app.tools import verification  # noqa: F401

__all__ = [
    "audit",
    "consistency",
    "cover_letter",
    "delivery",
    "docx_checks",
    "docx_render",
    "final_review",
    "formatting",
    "harness_meta",
    "intake",
    "foundational_build",
    "page_estimate",
    "profile",
    "redaction",
    "registry_tools",
    "security",
    "slop",
    "slop_advanced",
    "tailoring",
    "verification",
]
