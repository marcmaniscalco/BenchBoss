from bench_boss.guest import GUEST_ID_PREFIX, generate_guest_id, is_guest_id

# ---------------------------------------------------------------------------
# is_guest_id
# ---------------------------------------------------------------------------


class TestIsGuestId:
    def test_true_for_guest_prefixed_id(self):
        assert is_guest_id("guest:abcd1234") is True

    def test_true_for_bare_prefix(self):
        assert is_guest_id(GUEST_ID_PREFIX) is True

    def test_false_for_discord_snowflake(self):
        assert is_guest_id("123456789012345678") is False

    def test_false_for_empty_string(self):
        assert is_guest_id("") is False

    def test_false_for_unrelated_string(self):
        assert is_guest_id("not-a-guest-id") is False


# ---------------------------------------------------------------------------
# generate_guest_id
# ---------------------------------------------------------------------------


class TestGenerateGuestId:
    def test_has_guest_prefix(self):
        assert generate_guest_id().startswith(GUEST_ID_PREFIX)

    def test_is_guest_id_round_trip(self):
        assert is_guest_id(generate_guest_id()) is True

    def test_suffix_is_8_hex_chars(self):
        suffix = generate_guest_id().removeprefix(GUEST_ID_PREFIX)
        assert len(suffix) == 8
        int(suffix, 16)  # raises ValueError if not valid hex

    def test_generates_unique_ids(self):
        ids = {generate_guest_id() for _ in range(100)}
        assert len(ids) == 100
