"""Registry of available CampusConnect tools."""

from app.tools import (
    create_support_request_draft,
    get_support_request_status,
    lookup_lecture_venue,
    submit_support_request,
)

from app.tools.common import ToolSpec

TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        lookup_lecture_venue.SPEC,
        get_support_request_status.SPEC,
        create_support_request_draft.SPEC,
        submit_support_request.SPEC,
    )
}