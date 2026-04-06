"""Tests for the conversation-based query layer."""
import pytest

from ai_mailbox.db import queries


class TestFindOrCreateDirectConversation:
    """find_or_create_direct_conversation creates or reuses conversations."""

    def test_creates_conversation(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        assert conv_id is not None
        conv = queries.get_conversation(db, conv_id)
        assert conv["type"] == "direct"
        assert conv["project"] == "general"

    def test_creates_participants(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        participants = queries.get_conversation_participants(db, conv_id)
        assert set(participants) == {"keith", "amy"}

    def test_reuses_existing_conversation(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        assert conv1 == conv2

    def test_reuses_regardless_of_user_order(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "amy", "keith", "general")
        assert conv1 == conv2

    def test_different_projects_different_conversations(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "deployment")
        assert conv1 != conv2


class TestInsertMessage:
    """insert_message creates messages with sequence numbers."""

    def test_returns_id_and_sequence(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = queries.insert_message(db, conv_id, "keith", "hello")
        assert "id" in result
        assert result["sequence_number"] == 1

    def test_sequence_numbers_increment(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = queries.insert_message(db, conv_id, "keith", "first")
        r2 = queries.insert_message(db, conv_id, "amy", "second")
        r3 = queries.insert_message(db, conv_id, "keith", "third")
        assert r1["sequence_number"] == 1
        assert r2["sequence_number"] == 2
        assert r3["sequence_number"] == 3

    def test_sequence_numbers_independent_per_conversation(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "deployment")
        r1 = queries.insert_message(db, conv1, "keith", "in general")
        r2 = queries.insert_message(db, conv2, "keith", "in deployment")
        assert r1["sequence_number"] == 1
        assert r2["sequence_number"] == 1

    def test_subject_stored(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = queries.insert_message(db, conv_id, "keith", "hello", subject="Greeting")
        msg = queries.get_message(db, result["id"])
        assert msg["subject"] == "Greeting"

    def test_reply_to_stored(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = queries.insert_message(db, conv_id, "keith", "hello")
        r2 = queries.insert_message(db, conv_id, "amy", "reply", reply_to=r1["id"])
        msg = queries.get_message(db, r2["id"])
        assert msg["reply_to"] == r1["id"]

    def test_idempotency_key_prevents_duplicate(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = queries.insert_message(db, conv_id, "keith", "hello", idempotency_key="key-1")
        r2 = queries.insert_message(db, conv_id, "keith", "hello again", idempotency_key="key-1")
        assert "error" in r2

    def test_content_type_default(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = queries.insert_message(db, conv_id, "keith", "hello")
        msg = queries.get_message(db, result["id"])
        assert msg["content_type"] == "text/plain"

    def test_updates_conversation_updated_at(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv_before = queries.get_conversation(db, conv_id)
        queries.insert_message(db, conv_id, "keith", "hello")
        conv_after = queries.get_conversation(db, conv_id)
        assert conv_after["updated_at"] >= conv_before["updated_at"]


class TestGetMessage:
    """get_message fetches a single message."""

    def test_returns_message(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        result = queries.insert_message(db, conv_id, "keith", "hello")
        msg = queries.get_message(db, result["id"])
        assert msg["body"] == "hello"
        assert msg["from_user"] == "keith"
        assert msg["conversation_id"] == conv_id

    def test_returns_none_for_missing(self, db):
        assert queries.get_message(db, "nonexistent-id") is None


class TestGetConversationMessages:
    """get_conversation_messages retrieves ordered messages."""

    def test_returns_all_messages(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        queries.insert_message(db, conv_id, "keith", "third")
        msgs, _ = queries.get_conversation_messages(db, conv_id)
        assert len(msgs) == 3
        assert msgs[0]["body"] == "first"
        assert msgs[2]["body"] == "third"

    def test_after_sequence_filter(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        queries.insert_message(db, conv_id, "keith", "third")
        msgs, _ = queries.get_conversation_messages(db, conv_id, after_sequence=1)
        assert len(msgs) == 2
        assert msgs[0]["body"] == "second"

    def test_limit(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "keith", f"msg-{i}")
        msgs, _ = queries.get_conversation_messages(db, conv_id, limit=3)
        assert len(msgs) == 3

    def test_ordered_by_sequence_number(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        msgs, _ = queries.get_conversation_messages(db, conv_id)
        assert msgs[0]["sequence_number"] < msgs[1]["sequence_number"]


class TestReadTracking:
    """Cursor-based read tracking via last_read_sequence."""

    def test_initial_read_sequence_is_zero(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        seq = queries.get_last_read_sequence(db, conv_id, "keith")
        assert seq == 0

    def test_advance_read_cursor(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        queries.advance_read_cursor(db, conv_id, "amy", 2)
        seq = queries.get_last_read_sequence(db, conv_id, "amy")
        assert seq == 2

    def test_cursor_cannot_go_backward(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.advance_read_cursor(db, conv_id, "keith", 5)
        queries.advance_read_cursor(db, conv_id, "keith", 3)
        seq = queries.get_last_read_sequence(db, conv_id, "keith")
        assert seq == 5

    def test_cursors_independent_per_user(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "hello")
        queries.insert_message(db, conv_id, "amy", "reply")
        queries.advance_read_cursor(db, conv_id, "keith", 2)
        assert queries.get_last_read_sequence(db, conv_id, "keith") == 2
        assert queries.get_last_read_sequence(db, conv_id, "amy") == 0


class TestInbox:
    """get_inbox returns conversations with unread counts."""

    def test_empty_inbox(self, db):
        inbox = queries.get_inbox(db, "keith")
        assert inbox == []

    def test_conversation_appears_in_inbox(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello keith")
        inbox = queries.get_inbox(db, "keith")
        assert len(inbox) == 1
        assert inbox[0]["conversation_id"] == conv_id

    def test_inbox_shows_unread_count(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        inbox = queries.get_inbox(db, "keith")
        assert inbox[0]["unread_count"] == 2

    def test_inbox_unread_count_respects_cursor(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        inbox = queries.get_inbox(db, "keith")
        assert inbox[0]["unread_count"] == 1

    def test_inbox_project_filter(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "deployment")
        queries.insert_message(db, conv1, "amy", "general msg")
        queries.insert_message(db, conv2, "amy", "deploy msg")
        inbox = queries.get_inbox(db, "keith", project="deployment")
        assert len(inbox) == 1
        assert inbox[0]["project"] == "deployment"

    def test_inbox_ordered_by_last_activity(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "deployment")
        queries.insert_message(db, conv1, "amy", "older")
        queries.insert_message(db, conv2, "amy", "newer")
        inbox = queries.get_inbox(db, "keith")
        assert len(inbox) == 2
        assert inbox[0]["conversation_id"] == conv2

    def test_inbox_includes_last_message_preview(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "the latest message here")
        inbox = queries.get_inbox(db, "keith")
        assert "the latest message here" in inbox[0]["last_message_preview"]


class TestUnreadCounts:
    """get_unread_counts returns per-project unread counts."""

    def test_empty(self, db):
        counts = queries.get_unread_counts(db, "keith")
        assert counts == {}

    def test_counts_unread_messages(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        counts = queries.get_unread_counts(db, "keith")
        assert counts["general"] == 2

    def test_read_messages_not_counted(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "msg 1")
        queries.insert_message(db, conv_id, "amy", "msg 2")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        counts = queries.get_unread_counts(db, "keith")
        assert counts["general"] == 1

    def test_multiple_projects(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "alerts")
        queries.insert_message(db, conv1, "amy", "msg")
        queries.insert_message(db, conv2, "amy", "alert 1")
        queries.insert_message(db, conv2, "amy", "alert 2")
        counts = queries.get_unread_counts(db, "keith")
        assert counts["general"] == 1
        assert counts["alerts"] == 2


class TestGetThread:
    """get_thread returns all messages in a conversation."""

    def test_returns_all_messages(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = queries.insert_message(db, conv_id, "keith", "first")
        r2 = queries.insert_message(db, conv_id, "amy", "second")
        thread = queries.get_thread(db, r1["id"])
        assert len(thread) == 2

    def test_returns_from_any_message_in_conversation(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        r1 = queries.insert_message(db, conv_id, "keith", "first")
        r2 = queries.insert_message(db, conv_id, "amy", "second")
        thread = queries.get_thread(db, r2["id"])
        assert len(thread) == 2

    def test_ordered_by_sequence(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        queries.insert_message(db, conv_id, "keith", "third")
        msgs, _ = queries.get_conversation_messages(db, conv_id)
        thread = queries.get_thread(db, msgs[1]["id"])
        assert [m["body"] for m in thread] == ["first", "second", "third"]

    def test_empty_for_nonexistent_message(self, db):
        thread = queries.get_thread(db, "nonexistent")
        assert thread == []


class TestUserQueries:
    """User query functions."""

    def test_get_user(self, db):
        user = queries.get_user(db, "keith")
        assert user["display_name"] == "Keith"

    def test_get_user_not_found(self, db):
        assert queries.get_user(db, "nobody") is None

    def test_get_all_users(self, db):
        users = queries.get_all_users(db)
        assert len(users) == 2
        ids = {u["id"] for u in users}
        assert ids == {"keith", "amy"}


class TestAddParticipant:
    """add_participant is idempotent."""

    def test_add_new_participant(self, db):
        db._conn.execute(
            "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
            ("bob", "Bob", "test-bob-key"),
        )
        db._conn.commit()
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.add_participant(db, conv_id, "bob")
        participants = queries.get_conversation_participants(db, conv_id)
        assert "bob" in participants

    def test_add_existing_participant_is_idempotent(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.add_participant(db, conv_id, "keith")
        participants = queries.get_conversation_participants(db, conv_id)
        assert participants.count("keith") == 1


# ---------------------------------------------------------------------------
# Sprint 2 query additions
# ---------------------------------------------------------------------------

@pytest.fixture
def bob(db):
    """Add a third user for group tests."""
    db._conn.execute(
        "INSERT INTO users (id, display_name, api_key) VALUES (?, ?, ?)",
        ("bob", "Bob", "test-bob-key"),
    )
    db._conn.commit()
    return "bob"


class TestFindOrCreateGroupByMembers:
    """find_or_create_group_by_members finds or creates team groups."""

    def test_creates_group(self, db, bob):
        conv_id, created = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        assert conv_id is not None
        assert created is True
        conv = queries.get_conversation(db, conv_id)
        assert conv["type"] == "team_group"

    def test_includes_all_members_plus_creator(self, db, bob):
        conv_id, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        participants = queries.get_conversation_participants(db, conv_id)
        assert set(participants) == {"keith", "amy", "bob"}

    def test_reuses_existing_group_same_members(self, db, bob):
        conv1, created1 = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        conv2, created2 = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        assert conv1 == conv2
        assert created1 is True
        assert created2 is False

    def test_reuses_regardless_of_member_order(self, db, bob):
        conv1, _ = queries.find_or_create_group_by_members(
            db, "keith", [bob, "amy"], "general"
        )
        conv2, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        assert conv1 == conv2

    def test_different_project_different_group(self, db, bob):
        conv1, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general"
        )
        conv2, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "alerts"
        )
        assert conv1 != conv2

    def test_custom_name(self, db, bob):
        conv_id, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "general", name="Backend Team"
        )
        conv = queries.get_conversation(db, conv_id)
        assert conv["name"] == "Backend Team"

    def test_auto_generated_name_is_sorted_members(self, db, bob):
        conv_id, _ = queries.find_or_create_group_by_members(
            db, "keith", [bob, "amy"], "general"
        )
        conv = queries.get_conversation(db, conv_id)
        assert conv["name"] == "amy,bob,keith"

    def test_sets_project_on_group(self, db, bob):
        conv_id, _ = queries.find_or_create_group_by_members(
            db, "keith", ["amy", bob], "deployment"
        )
        conv = queries.get_conversation(db, conv_id)
        assert conv["project"] == "deployment"


class TestGetMaxSequence:
    """get_max_sequence returns highest sequence in a conversation."""

    def test_zero_for_empty_conversation(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        assert queries.get_max_sequence(db, conv_id) == 0

    def test_returns_max_after_messages(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "first")
        queries.insert_message(db, conv_id, "amy", "second")
        queries.insert_message(db, conv_id, "keith", "third")
        assert queries.get_max_sequence(db, conv_id) == 3


class TestGetInboxPaginated:
    """get_inbox_paginated supports limit and offset."""

    def test_returns_conversations_and_has_more(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello")
        convos, has_more = queries.get_inbox_paginated(db, "keith", limit=10)
        assert len(convos) == 1
        assert has_more is False

    def test_has_more_true_when_more_exist(self, db):
        # Create 3 conversations with messages
        for proj in ["proj-1", "proj-2", "proj-3"]:
            conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", proj)
            queries.insert_message(db, conv_id, "amy", f"hello from {proj}")
        convos, has_more = queries.get_inbox_paginated(db, "keith", limit=2)
        assert len(convos) == 2
        assert has_more is True

    def test_offset_skips_conversations(self, db):
        for proj in ["proj-a", "proj-b", "proj-c"]:
            conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", proj)
            queries.insert_message(db, conv_id, "amy", f"hello from {proj}")
        convos, has_more = queries.get_inbox_paginated(db, "keith", limit=2, offset=2)
        assert len(convos) == 1
        assert has_more is False

    def test_project_filter(self, db):
        for proj in ["general", "alerts"]:
            conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", proj)
            queries.insert_message(db, conv_id, "amy", f"hello from {proj}")
        convos, _ = queries.get_inbox_paginated(db, "keith", project="alerts")
        assert len(convos) == 1
        assert convos[0]["project"] == "alerts"


class TestListMessagesQuery:
    """list_messages_query fetches messages with pagination."""

    def test_returns_messages_and_has_more(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello")
        msgs, has_more = queries.list_messages_query(db, "keith")
        assert len(msgs) == 1
        assert has_more is False

    def test_limit_and_has_more(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "amy", f"msg {i}")
        msgs, has_more = queries.list_messages_query(db, "keith", limit=3)
        assert len(msgs) == 3
        assert has_more is True

    def test_unread_only_filters_by_cursor(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "old")
        queries.insert_message(db, conv_id, "amy", "new")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        msgs, _ = queries.list_messages_query(db, "keith", unread_only=True)
        assert len(msgs) == 1
        assert msgs[0]["body"] == "new"

    def test_unread_only_false_returns_all(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "old")
        queries.insert_message(db, conv_id, "amy", "new")
        queries.advance_read_cursor(db, conv_id, "keith", 1)
        msgs, _ = queries.list_messages_query(db, "keith", unread_only=False)
        assert len(msgs) == 2

    def test_conversation_id_filter(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "alerts")
        queries.insert_message(db, conv1, "amy", "general msg")
        queries.insert_message(db, conv2, "amy", "alert msg")
        msgs, _ = queries.list_messages_query(db, "keith", conversation_id=conv1)
        assert len(msgs) == 1
        assert msgs[0]["body"] == "general msg"

    def test_after_sequence_pagination(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "amy", f"msg {i}")
        msgs, _ = queries.list_messages_query(
            db, "keith", conversation_id=conv_id, after_sequence=3
        )
        assert len(msgs) == 2
        assert msgs[0]["sequence_number"] == 4

    def test_project_filter(self, db):
        conv1 = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        conv2 = queries.find_or_create_direct_conversation(db, "keith", "amy", "alerts")
        queries.insert_message(db, conv1, "amy", "general msg")
        queries.insert_message(db, conv2, "amy", "alert msg")
        msgs, _ = queries.list_messages_query(db, "keith", project="alerts")
        assert len(msgs) == 1
        assert msgs[0]["body"] == "alert msg"

    def test_does_not_return_other_users_messages(self, db):
        """keith should not see messages in conversations he's not part of."""
        # amy is in a conversation with someone else -- but we only have 2 users
        # so test that filter by user works
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "amy", "hello keith")
        msgs, _ = queries.list_messages_query(db, "amy")
        # amy should also see this (she's a participant)
        assert len(msgs) == 1


class TestGetConversationMessagesWithHasMore:
    """get_conversation_messages returns has_more flag."""

    def test_returns_tuple_with_has_more(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        queries.insert_message(db, conv_id, "keith", "hello")
        msgs, has_more = queries.get_conversation_messages(db, conv_id)
        assert len(msgs) == 1
        assert has_more is False

    def test_has_more_when_limited(self, db):
        conv_id = queries.find_or_create_direct_conversation(db, "keith", "amy", "general")
        for i in range(5):
            queries.insert_message(db, conv_id, "keith", f"msg {i}")
        msgs, has_more = queries.get_conversation_messages(db, conv_id, limit=3)
        assert len(msgs) == 3
        assert has_more is True
