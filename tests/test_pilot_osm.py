from unittest.mock import patch

from scripts.run_pilot_osm import search_radii, wait_for_request_slot


def test_default_search_is_bounded_to_500_m_for_every_habitat():
    for habitat in ("lake", "stream", "marine", "transition", "unknown"):
        assert search_radii(habitat) == (100.0, 500.0)


def test_expanded_search_restores_habitat_specific_larger_retries():
    assert search_radii("lake", allow_expanded_search=True) == (100.0, 500.0, 1500.0)
    assert search_radii("stream", allow_expanded_search=True) == (100.0, 500.0, 1000.0)
    assert search_radii("marine", allow_expanded_search=True) == (100.0, 500.0, 3000.0, 10000.0)
    assert search_radii("transition", allow_expanded_search=True) == (100.0, 500.0, 1000.0, 5000.0)
    assert search_radii("unknown", allow_expanded_search=True) == (100.0, 500.0, 2000.0)


def test_expanded_search_respects_configured_ceilings_without_duplicates():
    assert search_radii("lake", general_ceiling=500.0, allow_expanded_search=True) == (100.0, 500.0)
    assert search_radii("marine", coast_ceiling=500.0, allow_expanded_search=True) == (100.0, 500.0)


def test_request_slot_sleeps_between_calls_but_not_before_first():
    state = {}
    with patch("scripts.run_pilot_osm.time.sleep") as sleep:
        wait_for_request_slot(state, 1.0)
        sleep.assert_not_called()
        wait_for_request_slot(state, 1.0)
    sleep.assert_called_once_with(1.0)
    assert state["request_count"] == 2
