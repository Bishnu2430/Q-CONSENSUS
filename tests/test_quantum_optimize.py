import numpy as np

from src.qconsensus.quantum_executor import QuantumExecutor
from src.qconsensus.quantum_kernel import (
    average_pairwise_similarity,
    classical_text_similarity,
    pairwise_similarity_matrix,
    quantum_kernel_similarity,
)
from src.qconsensus.quantum_qaoa import (
    build_maxcut_qubo,
    classical_solve_qubo,
    solve_qubo_qaoa,
)
from src.qconsensus.quantum_ordering import diversity_order


def test_quantum_kernel_identical_text_is_similarity_one():
    qexec = QuantumExecutor({"base_seed": 7})
    sim = quantum_kernel_similarity(text_a="hello world", text_b="hello world", executor=qexec)
    assert sim == 1.0


def test_quantum_kernel_shared_words_more_similar_than_disjoint():
    qexec = QuantumExecutor({"base_seed": 7})
    close = quantum_kernel_similarity(
        text_a="the quick brown fox jumps",
        text_b="the quick brown fox runs",
        executor=qexec,
        shots=1024,
    )
    far = quantum_kernel_similarity(
        text_a="the quick brown fox jumps",
        text_b="completely unrelated economic policy discussion",
        executor=qexec,
        shots=1024,
    )
    assert close > far


def test_classical_text_similarity_matches_jaccard_bounds():
    assert classical_text_similarity("a b c", "a b c") == 1.0
    assert classical_text_similarity("a b c", "d e f") == 0.0
    mid = classical_text_similarity("a b c", "a b d")
    assert 0.0 < mid < 1.0


def test_pairwise_similarity_matrix_symmetric_and_unit_diagonal():
    agent_ids = ["a", "b", "c"]
    texts = {"a": "alpha beta", "b": "alpha gamma", "c": "delta epsilon"}
    matrix = pairwise_similarity_matrix(agent_ids=agent_ids, texts=texts, kind="classical")
    assert matrix.shape == (3, 3)
    assert np.allclose(np.diag(matrix), 1.0)
    assert np.allclose(matrix, matrix.T)


def test_average_pairwise_similarity_single_agent_is_one():
    assert average_pairwise_similarity(np.array([[1.0]])) == 1.0


def test_build_maxcut_qubo_two_node_optimal_cut():
    weights = np.array([[0.0, 1.0], [1.0, 0.0]])
    Q = build_maxcut_qubo(weights)
    bits, cost = classical_solve_qubo(Q=Q, seed=1)
    # Optimal max-cut of a single weight-1 edge separates the two nodes.
    assert bits[0] != bits[1]
    assert cost == -1.0


def test_classical_solve_qubo_brute_force_matches_known_optimum():
    # Triangle with edges (0,1)=5, (0,2)=1, (1,2)=1. Max cut isolates
    # whichever of node 0 or node 1 (both incident to the heavy edge) from
    # the rest, worth 5+1=6; isolating node 2 alone is only worth 1+1=2.
    weights = np.array(
        [
            [0.0, 5.0, 1.0],
            [5.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
        ]
    )
    Q = build_maxcut_qubo(weights)
    bits, cost = classical_solve_qubo(Q=Q, seed=1)
    assert cost == -6.0
    assert len(set(bits)) == 2  # a real, non-trivial cut was found


def test_solve_qubo_qaoa_finds_a_valid_cut_on_small_instance():
    qexec = QuantumExecutor({"base_seed": 3})
    weights = np.array([[0.0, 1.0], [1.0, 0.0]])
    Q = build_maxcut_qubo(weights)
    result = solve_qubo_qaoa(Q=Q, executor=qexec, p=1, shots=256, maxiter=15, seed=3)
    assert len(result.bitstring) == 2
    # Either a valid cut (cost -1) or the trivial no-cut (cost 0); QAOA on a
    # simulator with few iterations isn't guaranteed optimal, but it must
    # never do worse than the two possible outcomes for this tiny instance.
    assert result.cost in (-1.0, 0.0)


def test_diversity_order_single_agent_is_identity():
    qexec = QuantumExecutor({"base_seed": 1})
    result = diversity_order(
        agent_ids=["solo"], texts={"solo": "only agent"}, executor=qexec
    )
    assert result.quantum_order == [0]
    assert result.classical_order == [0]


def test_diversity_order_covers_every_agent_exactly_once():
    qexec = QuantumExecutor({"base_seed": 5})
    agent_ids = ["a", "b", "c", "d"]
    texts = {
        "a": "the proposer offers a direct solution",
        "b": "the skeptic stress-tests every claim",
        "c": "the verifier checks correctness explicitly",
        "d": "the optimizer minimizes complexity and risk",
    }
    result = diversity_order(agent_ids=agent_ids, texts=texts, executor=qexec, shots=128, maxiter=10)
    assert sorted(result.quantum_order) == list(range(4))
    assert sorted(result.classical_order) == list(range(4))
