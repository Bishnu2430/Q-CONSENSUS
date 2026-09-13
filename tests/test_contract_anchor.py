"""Unit tests for the anchoring bug fix: verify_commitment must distinguish
"no contract at this address" / "call reverted" / "genuinely not anchored"
instead of collapsing every failure into a bare None (the root cause of the
"stores fine, fails on retrieval" symptom).

These use a fake w3.eth so they run without a live chain -- exercising the
real ContractAnchoringClient methods against controlled fake RPC responses.
"""

from web3 import Web3
from web3.exceptions import ContractLogicError

from src.qconsensus.contract_anchor import AnchorContractConfig, ContractAnchoringClient

_ABI = [
    {
        "name": "commit",
        "type": "function",
        "inputs": [{"name": "run_id", "type": "bytes32"}, {"name": "commitment", "type": "bytes32"}],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "getCommitment",
        "type": "function",
        "inputs": [{"name": "run_id", "type": "bytes32"}],
        "outputs": [
            {"name": "", "type": "bytes32"},
            {"name": "", "type": "uint256"},
            {"name": "", "type": "address"},
        ],
        "stateMutability": "view",
    },
]

_TEST_ADDRESS = Web3.to_checksum_address("0x" + "11" * 20)


class _FakeCallable:
    def __init__(self, result=None, exception=None):
        self._result = result
        self._exception = exception

    def call(self):
        if self._exception is not None:
            raise self._exception
        return self._result


class _FakeFunctions:
    def __init__(self, result=None, exception=None):
        self._result = result
        self._exception = exception

    def getCommitment(self, _run_id_bytes):
        return _FakeCallable(self._result, self._exception)


class _FakeContract:
    def __init__(self, result=None, exception=None):
        self.functions = _FakeFunctions(result, exception)


class _FakeEth:
    def __init__(self, *, has_code: bool, result=None, exception=None):
        self._has_code = has_code
        self._result = result
        self._exception = exception

    def get_code(self, _address):
        return b"\x60\x80" if self._has_code else b""

    def contract(self, address, abi):
        return _FakeContract(self._result, self._exception)


class _FakeW3:
    def __init__(self, eth: _FakeEth):
        self.eth = eth


def _make_client(eth: _FakeEth) -> ContractAnchoringClient:
    client = ContractAnchoringClient.__new__(ContractAnchoringClient)
    client.config = AnchorContractConfig(
        rpc_url="http://fake",
        chain_id=1337,
        from_address="0x" + "22" * 20,
        private_key="0x" + "33" * 32,
    )
    client.w3 = _FakeW3(eth)
    client.contract_abi = _ABI
    return client


def test_has_code_true_and_false():
    client_with_code = _make_client(_FakeEth(has_code=True))
    client_without_code = _make_client(_FakeEth(has_code=False))
    assert client_with_code.has_code(_TEST_ADDRESS) is True
    assert client_without_code.has_code(_TEST_ADDRESS) is False


def test_verify_commitment_no_contract_at_address():
    client = _make_client(_FakeEth(has_code=False))
    result = client.verify_commitment(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["commitment"] is None
    assert result["error"] == "no_contract_at_address"


def test_verify_commitment_call_reverted_is_distinguishable_from_not_found():
    client = _make_client(
        _FakeEth(has_code=True, exception=ContractLogicError("execution reverted"))
    )
    result = client.verify_commitment(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["commitment"] is None
    assert result["error"] is not None
    assert "call_reverted" in result["error"]


def test_verify_commitment_genuinely_not_anchored_yet():
    client = _make_client(
        _FakeEth(has_code=True, result=(b"\x00" * 32, 0, "0x" + "00" * 20))
    )
    result = client.verify_commitment(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["commitment"] is None
    assert result["error"] is None  # a clean "not found", not a lookup failure


def test_verify_commitment_found():
    commitment_bytes = b"\xab" * 32
    client = _make_client(
        _FakeEth(has_code=True, result=(commitment_bytes, 5, "0x" + "22" * 20))
    )
    result = client.verify_commitment(run_id="run-1", contract_address=_TEST_ADDRESS)
    assert result["error"] is None
    assert result["commitment"] == commitment_bytes.hex()


def test_verify_commitment_invalid_address():
    client = _make_client(_FakeEth(has_code=True))
    result = client.verify_commitment(run_id="run-1", contract_address="not-an-address")
    assert result["commitment"] is None
    assert "invalid_contract_address" in result["error"]


def test_anchor_commitment_refuses_when_no_code_at_address():
    client = _make_client(_FakeEth(has_code=False))
    try:
        client.anchor_commitment(
            run_id="run-1",
            commitment="ab" * 32,
            contract_address=_TEST_ADDRESS,
        )
        assert False, "expected RuntimeError for missing contract code"
    except RuntimeError as exc:
        assert "No contract deployed" in str(exc)


def test_anchor_commitment_parses_commitments_with_leading_zeros():
    # Regression test: .lstrip("0x") strips the *characters* '0'/'x' from
    # the left, not the literal "0x" prefix, so any commitment whose hex
    # digest happens to start with '0' (about 1 in 16 of them) used to get
    # corrupted into an odd-length string that bytes.fromhex() rejected
    # with "non-hexadecimal number found in fromhex() arg". has_code=False
    # so this raises for an unrelated, later reason (no contract deployed)
    # -- reaching that error at all proves the hex parsing above it succeeded.
    client = _make_client(_FakeEth(has_code=False))
    leading_zero_commitment = "00" + "ab" * 31  # 64 hex chars, starts with "00"
    try:
        client.anchor_commitment(
            run_id="run-1",
            commitment=leading_zero_commitment,
            contract_address=_TEST_ADDRESS,
        )
        assert False, "expected RuntimeError for missing contract code"
    except ValueError:
        raise AssertionError("commitment hex parsing was corrupted by leading zeros")
    except RuntimeError as exc:
        assert "No contract deployed" in str(exc)


def test_anchor_commitment_strips_0x_prefix_but_not_leading_zero_digits():
    client = _make_client(_FakeEth(has_code=False))
    prefixed_commitment = "0x" + "00" + "cd" * 31
    try:
        client.anchor_commitment(
            run_id="run-1",
            commitment=prefixed_commitment,
            contract_address=_TEST_ADDRESS,
        )
        assert False, "expected RuntimeError for missing contract code"
    except ValueError:
        raise AssertionError("0x-prefixed commitment hex parsing was corrupted")
    except RuntimeError as exc:
        assert "No contract deployed" in str(exc)
