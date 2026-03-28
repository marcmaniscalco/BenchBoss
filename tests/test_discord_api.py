from datetime import UTC, datetime, timedelta, timezone

from bench_boss.discord_api import (
    BLURPLE,
    _build_gcal_url,
    build_add_rsvp_modal,
    build_event_embed,
    build_remove_rsvp_modal,
    build_rsvp_components,
)

START = datetime(2026, 4, 5, 19, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


# ---------------------------------------------------------------------------
# build_event_embed
# ---------------------------------------------------------------------------


class TestBuildEventEmbed:
    def test_title_is_event_name(self):
        embed = build_event_embed(
            "Team Standup", START, None, None, None, [], [], []
        )
        assert embed["title"] == "Team Standup"

    def test_color_is_blurple(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        assert embed["color"] == BLURPLE

    def test_contains_when_field(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert any("📅" in n for n in field_names)

    def test_when_field_contains_date(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "2026" in when_field["value"]
        assert "April" in when_field["value"]

    def test_when_field_includes_end_time_when_provided(self):
        embed = build_event_embed("Event", START, END, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "–" in when_field["value"]

    def test_location_field_present_when_provided(self):
        embed = build_event_embed("Event", START, None, "Room 1", None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert any("📍" in n for n in field_names)

    def test_location_field_absent_when_none(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert not any("📍" in n for n in field_names)

    def test_location_value_is_shown(self):
        embed = build_event_embed("Event", START, None, "Room 1", None, [], [], [])
        location_field = next(f for f in embed["fields"] if "📍" in f["name"])
        assert location_field["value"] == "Room 1"

    def test_description_field_present_when_provided(self):
        embed = build_event_embed(
            "Event", START, None, None, "https://example.com/game", [], [], []
        )
        field_names = [f["name"] for f in embed["fields"]]
        assert any("📋" in n for n in field_names)

    def test_description_renders_as_game_details_link(self):
        embed = build_event_embed(
            "Event", START, None, None, "https://example.com/game", [], [], []
        )
        details_field = next(f for f in embed["fields"] if "📋" in f["name"])
        assert details_field["value"] == "[Game Details](https://example.com/game)"

    def test_description_field_absent_when_none(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert not any("📋" in n for n in field_names)

    def test_rsvp_fields_show_zero_counts_when_empty(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert any("Accepted (0)" in n for n in field_names)
        assert any("Declined (0)" in n for n in field_names)
        assert any("Tentative (0)" in n for n in field_names)

    def test_rsvp_field_shows_correct_count(self):
        embed = build_event_embed(
            "Event", START, None, None, None, ["u1", "u2"], [], []
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "Accepted (2)" in accepted_field["name"]

    def test_rsvp_field_shows_user_mentions(self):
        embed = build_event_embed(
            "Event", START, None, None, None, ["user1"], [], []
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "<@user1>" in accepted_field["value"]

    def test_rsvp_field_shows_dash_when_empty(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert accepted_field["value"] == "-"

    def test_naive_datetime_is_handled_without_error(self):
        naive_start = datetime(2026, 4, 5, 19, 0)
        embed = build_event_embed(
            "Event", naive_start, None, None, None, [], [], []
        )
        assert embed["title"] == "Event"

    def test_when_field_shows_utc_label_for_utc_datetimes(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "UTC" in when_field["value"]

    def test_when_field_shows_original_timezone_label(self):
        eastern = timezone(timedelta(hours=-5), name="EST")
        est_start = datetime(2026, 4, 5, 19, 0, tzinfo=eastern)
        embed = build_event_embed("Event", est_start, None, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "EST" in when_field["value"]
        assert "UTC" not in when_field["value"]


# ---------------------------------------------------------------------------
# _build_gcal_url
# ---------------------------------------------------------------------------


class TestBuildGcalUrl:
    def test_contains_base_url(self):
        url = _build_gcal_url("Game Night", START, END, None, None)
        assert url.startswith("https://calendar.google.com/calendar/render")

    def test_event_name_encoded_in_url(self):
        url = _build_gcal_url("Game Night", START, END, None, None)
        assert "Game+Night" in url or "Game%20Night" in url

    def test_dates_formatted_as_utc(self):
        url = _build_gcal_url("Event", START, END, None, None)
        assert "20260405T190000Z" in url
        assert "20260405T200000Z" in url

    def test_no_end_uses_start_for_end(self):
        url = _build_gcal_url("Event", START, None, None, None)
        assert url.count("20260405T190000Z") == 2

    def test_location_included_when_provided(self):
        url = _build_gcal_url("Event", START, END, "Ice Rink", None)
        assert "Ice+Rink" in url or "Ice%20Rink" in url

    def test_description_included_when_provided(self):
        url = _build_gcal_url("Event", START, END, None, "Bring skates")
        assert "Bring+skates" in url or "Bring%20skates" in url

    def test_location_omitted_when_none(self):
        url = _build_gcal_url("Event", START, END, None, None)
        assert "location" not in url

    def test_all_day_event_uses_date_only_format(self):
        from datetime import date
        all_day_start = date(2026, 4, 5)
        url = _build_gcal_url("Event", all_day_start, None, None, None)
        assert "20260405" in url
        assert "T" not in url.split("dates=")[1].split("&")[0]

    def test_embed_contains_add_to_calendar_field(self):
        embed = build_event_embed("Event", START, END, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        assert any("Calendar" in n for n in field_names)

    def test_embed_calendar_field_contains_google_link(self):
        embed = build_event_embed("Event", START, END, None, None, [], [], [])
        cal_field = next(f for f in embed["fields"] if "Calendar" in f["name"])
        assert "calendar.google.com" in cal_field["value"]
        assert "Google Calendar" in cal_field["value"]


# ---------------------------------------------------------------------------
# build_rsvp_components
# ---------------------------------------------------------------------------


class TestBuildRsvpComponents:
    def test_returns_two_action_rows(self):
        components = build_rsvp_components("key1")
        assert len(components) == 2
        assert components[0]["type"] == 1
        assert components[1]["type"] == 1

    def test_row1_has_four_buttons(self):
        components = build_rsvp_components("key1")
        assert len(components[0]["components"]) == 4

    def test_row2_has_two_buttons(self):
        components = build_rsvp_components("key1")
        assert len(components[1]["components"]) == 2

    def test_row1_custom_ids(self):
        components = build_rsvp_components("key1")
        custom_ids = {btn["custom_id"] for btn in components[0]["components"]}
        assert custom_ids == {
            "rsvp:accepted:key1",
            "rsvp:declined:key1",
            "rsvp:tentative:key1",
            "delete:key1",
        }

    def test_row2_custom_ids(self):
        components = build_rsvp_components("key1")
        custom_ids = {btn["custom_id"] for btn in components[1]["components"]}
        assert custom_ids == {"add_rsvp:key1", "remove_rsvp:key1"}

    def test_no_edit_button(self):
        components = build_rsvp_components("key1")
        all_ids = [
            btn["custom_id"]
            for row in components
            for btn in row["components"]
        ]
        assert not any("edit:" in cid for cid in all_ids)

    def test_delete_button_has_danger_style(self):
        components = build_rsvp_components("key1")
        delete_btn = next(
            b for b in components[0]["components"] if b["custom_id"] == "delete:key1"
        )
        assert delete_btn["style"] == 4

    def test_delete_button_label_is_delete(self):
        components = build_rsvp_components("key1")
        delete_btn = next(
            b for b in components[0]["components"] if b["custom_id"] == "delete:key1"
        )
        assert delete_btn["label"] == "Delete"

    def test_rsvp_buttons_use_emoji_field(self):
        components = build_rsvp_components("key1")
        rsvp_btns = [b for b in components[0]["components"] if b["custom_id"].startswith("rsvp:")]
        for btn in rsvp_btns:
            assert "emoji" in btn
            assert btn["emoji"]["name"] in {"✅", "❌", "❔"}
            assert "label" not in btn

    def test_accept_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[0]["components"] if "accepted" in b["custom_id"])
        assert btn["style"] == 2

    def test_decline_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[0]["components"] if "declined" in b["custom_id"])
        assert btn["style"] == 2

    def test_tentative_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[0]["components"] if "tentative" in b["custom_id"])
        assert btn["style"] == 2

    def test_add_response_button_is_primary(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[1]["components"] if b["custom_id"] == "add_rsvp:key1")
        assert btn["style"] == 1

    def test_add_response_button_has_plus_emoji(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[1]["components"] if b["custom_id"] == "add_rsvp:key1")
        assert btn["emoji"]["name"] == "➕"
        assert "label" not in btn

    def test_remove_response_button_is_danger(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[1]["components"] if b["custom_id"] == "remove_rsvp:key1")
        assert btn["style"] == 4

    def test_remove_response_button_has_minus_emoji(self):
        components = build_rsvp_components("key1")
        btn = next(b for b in components[1]["components"] if b["custom_id"] == "remove_rsvp:key1")
        assert btn["emoji"]["name"] == "➖"
        assert "label" not in btn


# ---------------------------------------------------------------------------
# build_add_rsvp_modal / build_remove_rsvp_modal
# ---------------------------------------------------------------------------


class TestBuildAddRsvpModal:
    def test_custom_id_contains_event_key(self):
        assert "key1" in build_add_rsvp_modal("key1")["custom_id"]

    def test_has_title(self):
        assert "title" in build_add_rsvp_modal("key1")

    def test_has_user_and_action_inputs(self):
        modal = build_add_rsvp_modal("key1")
        input_ids = {comp["custom_id"] for row in modal["components"] for comp in row["components"]}
        assert "user" in input_ids
        assert "action" in input_ids


class TestBuildRemoveRsvpModal:
    def test_custom_id_contains_event_key(self):
        assert "key1" in build_remove_rsvp_modal("key1")["custom_id"]

    def test_has_title(self):
        assert "title" in build_remove_rsvp_modal("key1")

    def test_has_user_input_only(self):
        modal = build_remove_rsvp_modal("key1")
        input_ids = {comp["custom_id"] for row in modal["components"] for comp in row["components"]}
        assert "user" in input_ids
        assert "action" not in input_ids
