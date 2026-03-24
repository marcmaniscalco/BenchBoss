from datetime import UTC, datetime, timedelta

from bench_boss.discord_api import BLURPLE, build_event_embed, build_rsvp_components

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


# ---------------------------------------------------------------------------
# build_rsvp_components
# ---------------------------------------------------------------------------


class TestBuildRsvpComponents:
    def test_returns_two_action_rows(self):
        components = build_rsvp_components("key1")
        assert len(components) == 2
        assert all(row["type"] == 1 for row in components)

    def test_first_row_has_four_buttons(self):
        components = build_rsvp_components("key1")
        assert len(components[0]["components"]) == 4

    def test_all_buttons_are_type_2(self):
        components = build_rsvp_components("key1")
        for row in components:
            for btn in row["components"]:
                assert btn["type"] == 2

    def test_first_row_custom_ids_contain_event_key(self):
        components = build_rsvp_components("my-event-key")
        for btn in components[0]["components"]:
            assert "my-event-key" in btn["custom_id"]

    def test_custom_id_format_for_all_actions(self):
        components = build_rsvp_components("key1")
        custom_ids = {btn["custom_id"] for btn in components[0]["components"]}
        assert custom_ids == {
            "rsvp:accepted:key1",
            "rsvp:declined:key1",
            "rsvp:tentative:key1",
            "delete:key1",
        }

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

    def test_rsvp_buttons_have_icon_only_labels(self):
        components = build_rsvp_components("key1")
        rsvp_btns = [b for b in components[0]["components"] if b["custom_id"].startswith("rsvp:")]
        for btn in rsvp_btns:
            assert btn["label"] in {"✅", "❌", "❔", "🕐"}

    def test_accept_button_has_success_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "accepted" in b["custom_id"]
        )
        assert btn["style"] == 3

    def test_decline_button_has_danger_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "declined" in b["custom_id"]
        )
        assert btn["style"] == 4

    def test_tentative_has_secondary_style(self):
        components = build_rsvp_components("key1")
        btn = next(
            b for b in components[0]["components"] if "tentative" in b["custom_id"]
        )
        assert btn["style"] == 2

    def test_second_row_has_help_button(self):
        components = build_rsvp_components("key1")
        assert len(components[1]["components"]) == 1
        help_btn = components[1]["components"][0]
        assert help_btn["custom_id"] == "help"

    def test_help_button_has_secondary_style(self):
        components = build_rsvp_components("key1")
        help_btn = components[1]["components"][0]
        assert help_btn["style"] == 2

    def test_help_button_does_not_contain_event_key(self):
        components = build_rsvp_components("my-event-key")
        help_btn = components[1]["components"][0]
        assert "my-event-key" not in help_btn["custom_id"]
