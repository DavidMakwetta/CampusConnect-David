"""Tool registry. Each tool lives in its own module; add a new tool by importing its SPEC here."""

from app.tools import (
    create_support_request_draft,
    get_support_request_status,
    lookup_lecture_venue,
    submit_support_request,
)
from app.tools.common import CATEGORIES, STATUSES, ToolSpec  # noqa: F401  (re-exported)

TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        lookup_lecture_venue.SPEC,
        get_support_request_status.SPEC,
        create_support_request_draft.SPEC,
        submit_support_request.SPEC,
    )
}
