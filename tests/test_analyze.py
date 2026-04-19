import pytest
from analyze import _floor_to_int, _floor_type, _room_key, _stats
from analyze import compute_prices, compute_trends, find_outliers, analyze
from tests.fixtures import SAMPLE_DEALS


class TestFloorParsing:
    def test_hebrew_ordinal(self):
        assert _floor_to_int("חמישית") == 5

    def test_ground_floor(self):
        assert _floor_to_int("קרקע") == 0

    def test_basement(self):
        assert _floor_to_int("מרתף") == -1

    def test_numeric_in_string(self):
        assert _floor_to_int("קומה 7") == 7

    def test_large_number(self):
        assert _floor_to_int("עשרים ושמונה") is None  # not in map, no digit → None

    def test_none_input(self):
        assert _floor_to_int(None) is None

    def test_floor_type_ground(self):
        assert _floor_type("קרקע") == "ground"

    def test_floor_type_basement_is_ground(self):
        assert _floor_type("מרתף") == "ground"

    def test_floor_type_low(self):
        assert _floor_type("שלישית") == "low"

    def test_floor_type_high(self):
        assert _floor_type("חמישית") == "high"

    def test_floor_type_unknown(self):
        assert _floor_type(None) is None


class TestRoomKey:
    def test_two_rooms(self):
        assert _room_key(2.0) == "2"

    def test_three_rooms(self):
        assert _room_key(3.0) == "3"

    def test_four_plus(self):
        assert _room_key(4.0) == "4+"

    def test_five_rooms_is_four_plus(self):
        assert _room_key(5.0) == "4+"

    def test_none(self):
        assert _room_key(None) is None


class TestStats:
    def test_empty(self):
        assert _stats([]) == {"count": 0}

    def test_single_value(self):
        r = _stats([1000000])
        assert r["count"] == 1
        assert r["mean"] == 1000000
        assert r["median"] == 1000000

    def test_mean_median(self):
        r = _stats([1000000, 2000000, 3000000])
        assert r["mean"] == 2000000
        assert r["median"] == 2000000

    def test_with_sqm(self):
        r = _stats([1000000], [10000])
        assert r["mean_per_sqm"] == 10000

    def test_sqm_none_values_ignored(self):
        r = _stats([1000000, 2000000], [None, 10000])
        assert r["mean_per_sqm"] == 10000


class TestComputePrices:
    def test_overall_count(self):
        # SAMPLE_DEALS has 1 deal with no dealAmount → should be excluded
        result = compute_prices(SAMPLE_DEALS)
        assert result["overall"]["count"] == 11  # 11 with amount (including מחסן with amount)

    def test_overall_mean_positive(self):
        result = compute_prices(SAMPLE_DEALS)
        assert result["overall"]["mean"] > 0

    def test_by_rooms_keys(self):
        result = compute_prices(SAMPLE_DEALS)
        assert "2" in result["by_rooms"] or "3" in result["by_rooms"]

    def test_by_floor_ground_exists(self):
        result = compute_prices(SAMPLE_DEALS)
        # מרתף and קרקע both map to ground
        assert "ground" in result["by_floor_type"]

    def test_no_sqm_deals_excluded_from_sqm_stats(self):
        # דיזנגוף 70 has priceSM=None — should not break mean_per_sqm
        result = compute_prices(SAMPLE_DEALS)
        assert "mean_per_sqm" in result["overall"]


class TestComputeTrends:
    def test_by_quarter_not_empty(self):
        result = compute_trends(SAMPLE_DEALS)
        assert len(result["by_quarter"]) > 0

    def test_direction_is_valid(self):
        result = compute_trends(SAMPLE_DEALS)
        assert result["direction"] in ("rising", "falling", "stable")

    def test_quarter_has_required_keys(self):
        result = compute_trends(SAMPLE_DEALS)
        q = result["by_quarter"][0]
        assert "label" in q and "count" in q and "mean_price" in q

    def test_deals_with_no_date_are_skipped(self):
        deals = [{"dealDate": None, "dealAmount": 1000000}]
        result = compute_trends(deals)
        assert result["by_quarter"] == []


class TestFindOutliers:
    def test_returns_list(self):
        result = find_outliers(SAMPLE_DEALS)
        assert isinstance(result, list)

    def test_outliers_have_direction(self):
        result = find_outliers(SAMPLE_DEALS)
        for o in result:
            assert o["_outlier_direction"] in ("high", "low")
            assert "_outlier_pct" in o

    def test_no_priceSM_deals_excluded(self):
        deals = [{"dealAmount": 1000000, "priceSM": None}]
        result = find_outliers(deals)
        assert result == []

    def test_high_threshold_returns_fewer(self):
        r_low  = find_outliers(SAMPLE_DEALS, threshold=0.1)
        r_high = find_outliers(SAMPLE_DEALS, threshold=0.9)
        assert len(r_low) >= len(r_high)


class TestAnalyze:
    def test_returns_all_keys(self):
        result = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        assert all(k in result for k in ("meta", "prices", "trends", "outliers", "recent"))

    def test_meta_values(self):
        result = analyze(SAMPLE_DEALS, street="דיזנגוף", settlement="תל אביב")
        assert result["meta"]["street"] == "דיזנגוף"
        assert result["meta"]["settlement"] == "תל אביב"
        assert result["meta"]["total_deals"] > 0

    def test_recent_at_most_20(self):
        result = analyze(SAMPLE_DEALS)
        assert len(result["recent"]) <= 20

    def test_recent_sorted_newest_first(self):
        result = analyze(SAMPLE_DEALS)
        dates = [d["dealDate"] for d in result["recent"] if d.get("dealDate")]
        assert dates == sorted(dates, reverse=True)

    def test_empty_deals(self):
        result = analyze([])
        assert result["meta"]["total_deals"] == 0
        assert result["prices"]["overall"]["count"] == 0
