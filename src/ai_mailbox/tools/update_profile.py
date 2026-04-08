"""update_profile tool -- update user profile metadata for AI-to-AI routing."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from ai_mailbox.config import MAX_EXPERTISE_TAGS, MAX_PROFILE_METADATA_SIZE
from ai_mailbox.db.queries import get_user_profile_metadata, update_user_profile_metadata
from ai_mailbox.errors import make_error

if TYPE_CHECKING:
    from ai_mailbox.db.connection import DBConnection

_VALID_KEYS = {"team", "department", "expertise_tags", "projects", "jira_tickets", "observed_topics", "bio"}
_LIST_KEYS = {"expertise_tags", "projects", "jira_tickets", "observed_topics"}
_STRING_KEYS = {"team", "department", "bio"}


def tool_update_profile(
    db: DBConnection,
    *,
    user_id: str,
    metadata: dict,
    merge: bool = True,
) -> dict:
    """Update user profile metadata. Merge mode unions lists, replaces strings."""
    if user_id == "system":
        return make_error("SYSTEM_USER_DENIED", "The 'system' user cannot have a profile")

    # Validate keys
    unknown = set(metadata.keys()) - _VALID_KEYS
    if unknown:
        return make_error(
            "INVALID_PARAMETER",
            f"Unknown profile keys: {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_VALID_KEYS))}",
            param="metadata",
        )

    # Validate types
    for key in _LIST_KEYS:
        if key in metadata:
            val = metadata[key]
            if not isinstance(val, list):
                return make_error(
                    "INVALID_PARAMETER",
                    f"'{key}' must be a list of strings",
                    param=key,
                )
            if not all(isinstance(item, str) for item in val):
                return make_error(
                    "INVALID_PARAMETER",
                    f"'{key}' items must all be strings",
                    param=key,
                )

    for key in _STRING_KEYS:
        if key in metadata and not isinstance(metadata[key], str):
            return make_error(
                "INVALID_PARAMETER",
                f"'{key}' must be a string",
                param=key,
            )

    # Validate expertise_tags count
    if "expertise_tags" in metadata and len(metadata["expertise_tags"]) > MAX_EXPERTISE_TAGS:
        return make_error(
            "INVALID_PARAMETER",
            f"expertise_tags exceeds maximum of {MAX_EXPERTISE_TAGS}",
            param="expertise_tags",
        )

    # Merge or replace
    if merge and metadata:
        existing = get_user_profile_metadata(db, user_id)
        for key, val in metadata.items():
            if key in _LIST_KEYS and key in existing:
                # Union lists, deduplicate, preserve order
                combined = list(dict.fromkeys(existing[key] + val))
                existing[key] = combined
            else:
                existing[key] = val
        final = existing
    else:
        final = dict(metadata)

    # Validate total size
    serialized = json.dumps(final)
    if len(serialized) > MAX_PROFILE_METADATA_SIZE:
        return make_error(
            "PROFILE_TOO_LARGE",
            f"Profile metadata exceeds {MAX_PROFILE_METADATA_SIZE} characters ({len(serialized)} given)",
        )

    # Re-check expertise_tags after merge
    if "expertise_tags" in final and len(final["expertise_tags"]) > MAX_EXPERTISE_TAGS:
        return make_error(
            "INVALID_PARAMETER",
            f"expertise_tags exceeds maximum of {MAX_EXPERTISE_TAGS} after merge",
            param="expertise_tags",
        )

    update_user_profile_metadata(db, user_id, final)

    return {
        "user_id": user_id,
        "profile_metadata": final,
    }
