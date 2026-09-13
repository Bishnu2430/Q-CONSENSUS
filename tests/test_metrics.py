"""Tests for ChainVerifier.verify_run, in particular the leading-zero
commitment comparison bug: .lstrip("0x") strips the *characters* '0' and
'x' from the left rather than the literal "0x" prefix, so a commitment
whose hex digest starts with '0' could fail to match its own on-chain copy
even when they're identical.
"""

from dataclasses import dataclass

from src.qconsensus.metrics import ChainVerifier

_TEST_ADDRESS = "0x" + "11" * 20


@dataclass(frozen=True)
class _FakeEvent:
    event_type: str
    payload: dict


class _FakeEventStore:
    def __init__(self, events):
        self._events = events

    def iter_events(self, _run_id):
        return list(self._events)


class _FakeAnchorClient:
    def __init__(self, commitment, error=None):
        self._commitment = commitment
        self._error = error

    def verify_commitment(self, *, run_id, contract_address):
        return {"commitment": self._commitment, "error": self._error}


def test_verify_run_matches_when_commitment_has_no_leading_zeros():
    commitment = "ab" * 32
    store = _FakeEventStore([_FakeEvent("run_committed", {"commitment": commitment})])
    verifier = ChainVerifier(anchor_client=_FakeAnchorClient(commitment), event_store=store)
    result = verifier.verify_run(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["verified"] is True


def test_verify_run_matches_when_commitment_has_leading_zeros():
    # This is the regression case: both sides start with "00", and the old
    # .lstrip("0x") would strip those (and any other leading 0/x chars)
    # from both -- usually still comparing equal by coincidence, but the
    # point is this must work correctly and predictably, not by accident.
    commitment = "00" + "cd" * 31
    store = _FakeEventStore([_FakeEvent("run_committed", {"commitment": commitment})])
    verifier = ChainVerifier(anchor_client=_FakeAnchorClient(commitment), event_store=store)
    result = verifier.verify_run(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["verified"] is True


def test_verify_run_detects_genuine_mismatch_with_leading_zeros():
    event_commitment = "00" + "cd" * 31
    onchain_commitment = "00" + "ef" * 31
    store = _FakeEventStore([_FakeEvent("run_committed", {"commitment": event_commitment})])
    verifier = ChainVerifier(anchor_client=_FakeAnchorClient(onchain_commitment), event_store=store)
    result = verifier.verify_run(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["verified"] is False
    assert result["reason"] == "On-chain commitment mismatch"


def test_verify_run_no_commitment_in_event_log():
    store = _FakeEventStore([_FakeEvent("input_received", {})])
    verifier = ChainVerifier(anchor_client=_FakeAnchorClient("ab" * 32), event_store=store)
    result = verifier.verify_run(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["verified"] is False
    assert result["reason"] == "No commitment found in event log"


def test_verify_run_surfaces_lookup_error_distinctly():
    commitment = "ab" * 32
    store = _FakeEventStore([_FakeEvent("run_committed", {"commitment": commitment})])
    verifier = ChainVerifier(
        anchor_client=_FakeAnchorClient(None, error="no_contract_at_address"), event_store=store
    )
    result = verifier.verify_run(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["verified"] is False
    assert "no_contract_at_address" in result["reason"]
