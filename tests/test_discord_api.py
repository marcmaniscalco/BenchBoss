from datetime import UTC, date, datetime, timedelta, timezone

from bench_boss.discord_api import (
    _EVENT_MODAL_ERROR_LABELS,
    BLURPLE,
    _build_gcal_url,
    build_add_rsvp_modal,
    build_event_embed,
    build_event_modal,
    build_help_embed,
    build_no_events_embed,
    build_remove_rsvp_modal,
    build_retry_button,
    build_rsvp_components,
)

START = datetime(2026, 4, 5, 19, 0, tzinfo=UTC)
END = START + timedelta(hours=1)


# ---------------------------------------------------------------------------
# build_event_embed
# ---------------------------------------------------------------------------


class TestBuildEventEmbed:
    def test_title_is_event_name(self):
        embed = build_event_embed("Team Standup", START, None, None, None, [], [], [])
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

    def test_plain_text_description_renders_as_plain_text(self):
        embed = build_event_embed(
            "Event", START, None, None, "Bring your own gear", [], [], []
        )
        details_field = next(f for f in embed["fields"] if "📋" in f["name"])
        assert details_field["value"] == "Bring your own gear"

    def test_http_description_still_renders_as_link(self):
        embed = build_event_embed(
            "Event", START, None, None, "http://example.com/game", [], [], []
        )
        details_field = next(f for f in embed["fields"] if "📋" in f["name"])
        assert details_field["value"] == "[Game Details](http://example.com/game)"

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

    def test_rsvp_field_falls_back_to_mention_without_names(self):
        embed = build_event_embed("Event", START, None, None, None, ["user1"], [], [])
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "<@user1>" in accepted_field["value"]

    def test_rsvp_field_shows_display_name_without_at_symbol(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            ["user1"],
            [],
            [],
            names={"user1": "Alice"},
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "Alice" in accepted_field["value"]
        assert "<@user1>" not in accepted_field["value"]
        assert "@" not in accepted_field["value"]

    def test_rsvp_field_mixes_names_and_mentions(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            ["user1", "user2"],
            [],
            [],
            names={"user1": "Alice"},
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "Alice" in accepted_field["value"]
        assert "<@user2>" in accepted_field["value"]

    def test_rsvp_fulltime_players_listed_before_non_fulltime(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            ["sub1", "full1", "sub2"],
            [],
            [],
            names={"sub1": "Bob*", "full1": "Alice", "sub2": "Carol*"},
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        lines = accepted_field["value"].split("\n")
        assert lines[0] == "Alice"
        assert set(lines[1:]) == {"Bob*", "Carol*"}

    def test_rsvp_all_fulltime_order_preserved(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            ["u1", "u2"],
            [],
            [],
            names={"u1": "Alice", "u2": "Bob"},
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "Alice" in accepted_field["value"]
        assert "Bob" in accepted_field["value"]
        assert "*" not in accepted_field["value"]

    def test_rsvp_all_non_fulltime_order_preserved(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            ["u1", "u2"],
            [],
            [],
            names={"u1": "Alice*", "u2": "Bob*"},
        )
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert "Alice*" in accepted_field["value"]
        assert "Bob*" in accepted_field["value"]

    def test_rsvp_field_shows_dash_when_empty(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        accepted_field = next(f for f in embed["fields"] if "Accepted" in f["name"])
        assert accepted_field["value"] == "-"

    def test_goalie_field_shows_dash_when_empty(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        goalie_field = next(f for f in embed["fields"] if "Goalie" in f["name"])
        assert goalie_field["value"] == "-"

    def test_goalie_field_shows_mention_when_set(self):
        embed = build_event_embed(
            "Event", START, None, None, None, [], [], [], goalie=["user1"]
        )
        goalie_field = next(f for f in embed["fields"] if "Goalie" in f["name"])
        assert "<@user1>" in goalie_field["value"]

    def test_goalie_field_shows_display_name_when_in_names(self):
        embed = build_event_embed(
            "Event",
            START,
            None,
            None,
            None,
            [],
            [],
            [],
            names={"user1": "Alice"},
            goalie=["user1"],
        )
        goalie_field = next(f for f in embed["fields"] if "Goalie" in f["name"])
        assert "Alice" in goalie_field["value"]
        assert "<@user1>" not in goalie_field["value"]

    def test_goalie_field_appears_before_rsvp_fields(self):
        embed = build_event_embed(
            "Event", START, None, None, None, [], [], [], goalie=["user1"]
        )
        field_names = [f["name"] for f in embed["fields"]]
        goalie_idx = next(i for i, n in enumerate(field_names) if "Goalie" in n)
        accepted_idx = next(i for i, n in enumerate(field_names) if "Accepted" in n)
        assert goalie_idx < accepted_idx

    def test_goalie_field_appears_directly_before_accepted_field(self):
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        field_names = [f["name"] for f in embed["fields"]]
        goalie_idx = next(i for i, n in enumerate(field_names) if "Goalie" in n)
        accepted_idx = next(i for i, n in enumerate(field_names) if "Accepted" in n)
        assert goalie_idx == accepted_idx - 1

    def test_naive_datetime_is_handled_without_error(self):
        naive_start = datetime(2026, 4, 5, 19, 0)
        embed = build_event_embed("Event", naive_start, None, None, None, [], [], [])
        assert embed["title"] == "Event"

    def test_when_field_converts_utc_to_team_timezone_label(self):
        # START is 2026-04-05 19:00 UTC — daylight saving is in effect for
        # America/New_York by then, so it should render in Eastern as EDT,
        # not the literal "UTC" the input was tagged with.
        embed = build_event_embed("Event", START, None, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "EDT" in when_field["value"]
        assert "UTC" not in when_field["value"]

    def test_when_field_shows_est_in_winter(self):
        winter_start = datetime(2026, 1, 15, 0, 0, tzinfo=UTC)
        embed = build_event_embed("Event", winter_start, None, None, None, [], [], [])
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "EST" in when_field["value"]

    def test_when_field_ignores_a_bare_fixed_offset_and_uses_team_zone(self):
        # A datetime round-tripped through storage (fromisoformat on a
        # stored ISO string) carries a bare fixed-offset tzinfo with no
        # zone name — e.g. UTC-04:00 — which is exactly the bug this
        # guards against: strftime("%Z") on that would print "UTC-04:00"
        # instead of resolving to a real zone abbreviation.
        bare_offset_start = datetime(
            2026, 4, 5, 15, 0, tzinfo=timezone(timedelta(hours=-4))
        )
        embed = build_event_embed(
            "Event", bare_offset_start, None, None, None, [], [], []
        )
        when_field = next(f for f in embed["fields"] if "📅" in f["name"])
        assert "EDT" in when_field["value"]
        assert "UTC-04:00" not in when_field["value"]


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

    def test_row2_has_four_buttons(self):
        components = build_rsvp_components("key1")
        assert len(components[1]["components"]) == 4

    def test_row1_custom_ids(self):
        components = build_rsvp_components("key1")
        custom_ids = {btn["custom_id"] for btn in components[0]["components"]}
        assert custom_ids == {
            "rsvp:accepted:key1",
            "rsvp:declined:key1",
            "rsvp:tentative:key1",
            "goalie_rsvp:key1",
        }

    def test_row2_custom_ids(self):
        components = build_rsvp_components("key1")
        custom_ids = {btn["custom_id"] for btn in components[1]["components"]}
        assert custom_ids == {
            "add_rsvp:key1",
            "remove_rsvp:key1",
            "edit_event:key1",
            "delete:key1",
        }

    def test_edit_button_has_primary_style(self):
        components = build_rsvp_components("key1")
        edit_btn = next(
            b
            for b in components[1]["components"]
            if b["custom_id"] == "edit_event:key1"
        )
        assert edit_btn["style"] == 1

    def test_delete_button_has_danger_style(self):
        components = build_rsvp_components("key1")
        delete_btn = next(
            b for b in components[1]["components"] if b["custom_id"] == "delete:key1"
        )
        assert delete_btn["style"] == 4

    def test_delete_button_label_is_delete(self):
        components = build_rsvp_components("key1")
        delete_btn = next(
            b for b in components[1]["components"] if b["custom_id"] == "delete:key1"
        )
        assert delete_btn["label"] == "Delete"

    def test_rsvp_buttons_use_emoji_field(self):
        components = build_rsvp_components("key1")
        rsvp_btns = [
            b for b in components[0]["components"] if b["custom_id"].startswith("rsvp:")
        ]
        for btn in rsvp_btns:
            assert "emoji" in btn
            assert btn["emoji"]["name"] in {"✅", "❌", "❔"}
            assert "label" not in btn

    def test_accept_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "accepted" in b["custom_id"]
        )
        assert btn["style"] == 2

    def test_decline_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "declined" in b["custom_id"]
        )
        assert btn["style"] == 2

    def test_tentative_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "tentative" in b["custom_id"]
        )
        assert btn["style"] == 2

    def test_add_response_button_is_primary(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[1]["components"] if b["custom_id"] == "add_rsvp:key1"
        )
        assert btn["style"] == 1

    def test_add_response_button_has_plus_emoji(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[1]["components"] if b["custom_id"] == "add_rsvp:key1"
        )
        assert btn["emoji"]["name"] == "➕"
        assert "label" not in btn

    def test_remove_response_button_is_danger(self):
        components = build_rsvp_components("key1")
        btn = next(
            b
            for b in components[1]["components"]
            if b["custom_id"] == "remove_rsvp:key1"
        )
        assert btn["style"] == 4

    def test_remove_response_button_has_minus_emoji(self):
        components = build_rsvp_components("key1")
        btn = next(
            b
            for b in components[1]["components"]
            if b["custom_id"] == "remove_rsvp:key1"
        )
        assert btn["emoji"]["name"] == "➖"
        assert "label" not in btn

    def test_goalie_button_has_mask_emoji(self):
        components = build_rsvp_components("key1")
        btn = next(
            b
            for b in components[0]["components"]
            if b["custom_id"] == "goalie_rsvp:key1"
        )
        assert btn["emoji"]["name"] == "🇬"
        assert "label" not in btn

    def test_goalie_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b
            for b in components[0]["components"]
            if b["custom_id"] == "goalie_rsvp:key1"
        )
        assert btn["style"] == 2


# ---------------------------------------------------------------------------
# build_add_rsvp_modal / build_remove_rsvp_modal
# ---------------------------------------------------------------------------


class TestBuildNoEventsEmbed:
    def test_has_title(self):
        assert build_no_events_embed()["title"] == "No More Events"

    def test_has_description(self):
        assert "description" in build_no_events_embed()

    def test_color_is_blurple(self):
        assert build_no_events_embed()["color"] == BLURPLE


class TestBuildHelpEmbed:
    def test_has_title(self):
        assert build_help_embed()["title"] == "BenchBoss Help"

    def test_color_is_blurple(self):
        assert build_help_embed()["color"] == BLURPLE

    def test_lists_all_four_slash_commands(self):
        embed = build_help_embed()
        commands_field = next(
            f for f in embed["fields"] if f["name"] == "Slash Commands"
        )
        for cmd in ("/bb-help", "/schedule", "/events", "/create-event"):
            assert cmd in commands_field["value"]

    def test_describes_event_message_controls(self):
        embed = build_help_embed()
        controls_field = next(
            f for f in embed["fields"] if f["name"] == "On an Event Message"
        )
        assert "goalie" in controls_field["value"].lower()
        assert "Edit" in controls_field["value"]
        assert "Delete" in controls_field["value"]

    def test_goalie_emoji_matches_the_goalie_button(self):
        # Same character used on the actual goalie button/field elsewhere
        # (discord_api.py's build_rsvp_components / build_event_embed) —
        # keep it consistent rather than picking a different "goalie" icon.
        embed = build_help_embed()
        controls_field = next(
            f for f in embed["fields"] if f["name"] == "On an Event Message"
        )
        assert "🇬" in controls_field["value"]

    def test_takes_no_arguments(self):
        # Static for v1 — no per-invoker variation.
        embed = build_help_embed()
        assert isinstance(embed, dict)


class TestBuildAddRsvpModal:
    def test_custom_id_contains_event_key(self):
        assert "key1" in build_add_rsvp_modal("key1")["custom_id"]

    def test_has_title(self):
        assert "title" in build_add_rsvp_modal("key1")

    def test_has_user_and_action_inputs(self):
        modal = build_add_rsvp_modal("key1")
        input_ids = {
            comp["custom_id"]
            for row in modal["components"]
            for comp in row["components"]
        }
        assert "user" in input_ids
        assert "action" in input_ids


class TestBuildRemoveRsvpModal:
    def test_custom_id_contains_event_key(self):
        assert "key1" in build_remove_rsvp_modal("key1")["custom_id"]

    def test_has_title(self):
        assert "title" in build_remove_rsvp_modal("key1")

    def test_has_user_input_only(self):
        modal = build_remove_rsvp_modal("key1")
        input_ids = {
            comp["custom_id"]
            for row in modal["components"]
            for comp in row["components"]
        }
        assert "user" in input_ids
        assert "action" not in input_ids


class TestBuildEventModal:
    def _input_ids(self, modal):
        return {
            comp["custom_id"]
            for row in modal["components"]
            for comp in row["components"]
        }

    def test_create_custom_id_has_no_event_key(self):
        modal = build_event_modal()
        assert modal["custom_id"] == "create_event_modal"

    def test_create_title(self):
        modal = build_event_modal()
        assert modal["title"] == "Create Event"

    def test_edit_custom_id_contains_event_key(self):
        modal = build_event_modal("key1")
        assert modal["custom_id"] == "edit_event_modal:key1"

    def test_edit_title(self):
        modal = build_event_modal("key1")
        assert modal["title"] == "Edit Event"

    def test_has_all_five_fields(self):
        modal = build_event_modal()
        assert self._input_ids(modal) == {
            "name",
            "datetime",
            "duration",
            "location",
            "description",
        }

    def test_at_most_five_action_rows(self):
        modal = build_event_modal()
        assert len(modal["components"]) == 5

    def test_name_datetime_duration_required(self):
        modal = build_event_modal()
        required = {
            comp["custom_id"]: comp["required"]
            for row in modal["components"]
            for comp in row["components"]
        }
        assert required["name"] is True
        assert required["datetime"] is True
        assert required["duration"] is True
        assert required["location"] is False
        assert required["description"] is False

    def test_no_prefill_has_no_values(self):
        modal = build_event_modal()
        for row in modal["components"]:
            for comp in row["components"]:
                assert "value" not in comp

    def test_prefill_populates_matching_fields(self):
        prefill = {
            "name": "Scrimmage",
            "datetime": "2026-08-30 07:00 PM",
            "duration": "90",
            "location": "Rink 1",
            "description": "Bring pads",
        }
        modal = build_event_modal("key1", prefill=prefill)
        values = {
            comp["custom_id"]: comp["value"]
            for row in modal["components"]
            for comp in row["components"]
        }
        assert values == prefill

    def test_prefill_skips_empty_values(self):
        prefill = {"name": "Scrimmage", "location": "", "description": ""}
        modal = build_event_modal("key1", prefill=prefill)
        components = {
            comp["custom_id"]: comp
            for row in modal["components"]
            for comp in row["components"]
        }
        assert components["name"]["value"] == "Scrimmage"
        assert "value" not in components["location"]
        assert "value" not in components["description"]

    def test_error_field_gets_red_asterisk_label(self):
        modal = build_event_modal(error_field="datetime", error_message="Bad date.")
        components = {
            comp["custom_id"]: comp
            for row in modal["components"]
            for comp in row["components"]
        }
        assert components["datetime"]["label"].startswith("🔴*")
        assert components["datetime"]["placeholder"] == "Bad date."

    def test_error_field_does_not_affect_other_labels(self):
        modal = build_event_modal(error_field="datetime", error_message="Bad date.")
        components = {
            comp["custom_id"]: comp
            for row in modal["components"]
            for comp in row["components"]
        }
        assert not components["name"]["label"].startswith("🔴*")
        assert not components["duration"]["label"].startswith("🔴*")

    def test_error_message_is_truncated_to_placeholder_limit(self):
        long_message = "x" * 150
        modal = build_event_modal(error_field="name", error_message=long_message)
        components = {
            comp["custom_id"]: comp
            for row in modal["components"]
            for comp in row["components"]
        }
        assert len(components["name"]["placeholder"]) == 100

    def test_no_error_field_leaves_labels_untouched(self):
        modal = build_event_modal()
        for row in modal["components"]:
            for comp in row["components"]:
                assert not comp["label"].startswith("🔴*")

    def test_error_field_combines_with_prefill(self):
        prefill = {"name": "Scrimmage", "datetime": "not a date"}
        modal = build_event_modal(
            "key1",
            prefill=prefill,
            error_field="datetime",
            error_message="Could not parse date/time.",
        )
        components = {
            comp["custom_id"]: comp
            for row in modal["components"]
            for comp in row["components"]
        }
        assert components["datetime"]["value"] == "not a date"
        assert components["datetime"]["label"].startswith("🔴*")
        assert components["name"]["value"] == "Scrimmage"

    def test_error_label_carries_fix_it_advice_even_with_a_value_set(self):
        # The placeholder is invisible once a field has a value (which it
        # always will here, since we prefill with what the user typed), so
        # the format guidance has to be readable straight off the label.
        modal = build_event_modal(
            prefill={"datetime": "not a date"},
            error_field="datetime",
            error_message="Could not parse date/time.",
        )
        datetime_field = next(
            comp
            for row in modal["components"]
            for comp in row["components"]
            if comp["custom_id"] == "datetime"
        )
        assert "YYYY-MM-DD" in datetime_field["label"]
        assert "value" in datetime_field

    def test_all_error_labels_fit_discord_limit(self):
        for field, label in _EVENT_MODAL_ERROR_LABELS.items():
            assert len(label) <= 45, f"{field} error label exceeds 45 chars: {label}"

    def test_custom_id_is_stable_regardless_of_error_field(self):
        # build_event_modal is only ever called from a fresh
        # APPLICATION_COMMAND or MESSAGE_COMPONENT interaction (never as a
        # direct response to the MODAL_SUBMIT that failed — Discord
        # disallows that), so there's no need to vary the custom_id here.
        modal = build_event_modal(error_field="name", error_message="Required.")
        assert modal["custom_id"] == "create_event_modal"
        modal = build_event_modal("key1", error_field="name", error_message="Required.")
        assert modal["custom_id"] == "edit_event_modal:key1"


class TestBuildRetryButton:
    def test_single_button_with_draft_key_in_custom_id(self):
        rows = build_retry_button("abc123")
        assert len(rows) == 1
        button = rows[0]["components"][0]
        assert button["type"] == 2
        assert button["custom_id"] == "retry_event_modal:abc123"

    def test_button_has_a_label(self):
        rows = build_retry_button("abc123")
        button = rows[0]["components"][0]
        assert button["label"]
