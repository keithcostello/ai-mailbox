"""Test Suite 2: Data Layer — 8 tests."""

import pytest

from ai_mailbox.db.queries import (
    insert_message,
    get_inbox,
    mark_read,
    get_thread,
    get_unread_counts,
)


def test_insert_message_returns_uuid(db):
    """Message stored, gets unique ID."""
    msg_id = insert_message(db, from_user="keith", to_user="amy", body="Hello", project="general")
    assert msg_id is not None
    assert len(msg_id) > 0


def test_get_inbox_returns_only_recipient_messages(db):
    """Keith's inbox has no messages TO Amy."""
    insert_message(db, from_user="keith", to_user="amy", body="For Amy")
    insert_message(db, from_user="amy", to_user="keith", body="For Keith")

    keith_inbox = get_inbox(db, user_id="keith")
    assert len(keith_inbox) == 1
    assert keith_inbox[0]["body"] == "For Keith"

    amy_inbox = get_inbox(db, user_id="amy")
    assert len(amy_inbox) == 1
    assert amy_inbox[0]["body"] == "For Amy"


def test_get_inbox_filters_by_project(db):
    """project='steertrue' only returns steertrue messages."""
    insert_message(db, from_user="keith", to_user="amy", body="General msg", project="general")
    insert_message(db, from_user="keith", to_user="amy", body="ST msg", project="steertrue")

    filtered = get_inbox(db, user_id="amy", project="steertrue")
    assert len(filtered) == 1
    assert filtered[0]["body"] == "ST msg"

    all_msgs = get_inbox(db, user_id="amy", project=None)
    assert len(all_msgs) == 2


def test_mark_read_flips_flag(db):
    """After mark_read, message.read == True."""
    msg_id = insert_message(db, from_user="keith", to_user="amy", body="Read me")

    inbox_before = get_inbox(db, user_id="amy", unread_only=True)
    assert len(inbox_before) == 1

    mark_read(db, msg_id)

    inbox_after = get_inbox(db, user_id="amy", unread_only=True)
    assert len(inbox_after) == 0


def test_mark_read_idempotent(db):
    """Marking already-read message doesn't error."""
    msg_id = insert_message(db, from_user="keith", to_user="amy", body="Read me twice")
    mark_read(db, msg_id)
    mark_read(db, msg_id)  # Should not raise


def test_get_thread_walks_full_chain(db):
    """5-message thread returns all 5 in chronological order."""
    m1 = insert_message(db, from_user="keith", to_user="amy", body="msg 1", project="test")
    m2 = insert_message(db, from_user="amy", to_user="keith", body="msg 2", project="test", reply_to=m1)
    m3 = insert_message(db, from_user="keith", to_user="amy", body="msg 3", project="test", reply_to=m2)
    m4 = insert_message(db, from_user="amy", to_user="keith", body="msg 4", project="test", reply_to=m3)
    m5 = insert_message(db, from_user="keith", to_user="amy", body="msg 5", project="test", reply_to=m4)

    thread = get_thread(db, m1)
    assert len(thread) == 5
    assert [m["body"] for m in thread] == ["msg 1", "msg 2", "msg 3", "msg 4", "msg 5"]


def test_get_thread_from_middle_message(db):
    """Starting from reply #3 still returns the full thread."""
    m1 = insert_message(db, from_user="keith", to_user="amy", body="msg 1", project="test")
    m2 = insert_message(db, from_user="amy", to_user="keith", body="msg 2", project="test", reply_to=m1)
    m3 = insert_message(db, from_user="keith", to_user="amy", body="msg 3", project="test", reply_to=m2)

    thread = get_thread(db, m3)  # Start from middle
    assert len(thread) == 3
    assert thread[0]["body"] == "msg 1"  # Still starts from root


def test_unread_count_by_project(db):
    """Correct counts: general=2, steertrue=1, wedding=0."""
    insert_message(db, from_user="keith", to_user="amy", body="g1", project="general")
    insert_message(db, from_user="keith", to_user="amy", body="g2", project="general")
    insert_message(db, from_user="keith", to_user="amy", body="s1", project="steertrue")

    counts = get_unread_counts(db, user_id="amy")
    assert counts["general"] == 2
    assert counts["steertrue"] == 1
    assert counts.get("wedding", 0) == 0
