from app.geocooling.operating_mode_tracker import OperatingModeTracker


def test_first_observation_is_immediately_effective():
    tracker = OperatingModeTracker()

    result = tracker.observe("BUILDING_ONLY")

    assert result.effective_mode == "BUILDING_ONLY"
    assert result.changed is True
    assert result.previous_mode is None


def test_single_missing_cycle_does_not_degrade_mode():
    tracker = OperatingModeTracker(degradation_cycles=2)
    tracker.observe("FULL")

    result = tracker.observe("LIMITED")

    assert result.effective_mode == "FULL"
    assert result.changed is False
    assert result.pending_cycles == 1
    assert result.required_cycles == 2


def test_degradation_requires_consecutive_confirmations():
    tracker = OperatingModeTracker(degradation_cycles=2)
    tracker.observe("FULL")
    tracker.observe("LIMITED")

    result = tracker.observe("LIMITED")

    assert result.previous_mode == "FULL"
    assert result.effective_mode == "LIMITED"
    assert result.changed is True


def test_recovery_is_more_conservative_than_degradation():
    tracker = OperatingModeTracker(recovery_cycles=3)
    tracker.observe("LIMITED")

    assert tracker.observe("BUILDING_ONLY").effective_mode == "LIMITED"
    assert tracker.observe("BUILDING_ONLY").effective_mode == "LIMITED"

    result = tracker.observe("BUILDING_ONLY")

    assert result.effective_mode == "BUILDING_ONLY"
    assert result.changed is True


def test_return_to_effective_mode_cancels_pending_transition():
    tracker = OperatingModeTracker(degradation_cycles=2)
    tracker.observe("FULL")
    tracker.observe("INSUFFICIENT_DATA")

    result = tracker.observe("FULL")

    assert result.effective_mode == "FULL"
    assert result.pending_cycles == 0
    assert "annulée" in result.reason


def test_candidate_change_restarts_confirmation_counter():
    tracker = OperatingModeTracker(degradation_cycles=2)
    tracker.observe("FULL")
    tracker.observe("LIMITED")

    result = tracker.observe("BUILDING_ONLY")

    assert result.effective_mode == "FULL"
    assert result.pending_cycles == 1
