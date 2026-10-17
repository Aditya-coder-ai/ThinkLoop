"""Unit tests for read-side concept knowledge graph service."""

import pytest


def test_graph_transitive_prerequisites() -> None:
    from app.content.service import GraphService

    # Graph DAG: a -> b -> c -> d
    # (d requires c, c requires b, b requires a)
    edges = [
        ("a", "b"),
        ("b", "c"),
        ("c", "d"),
        ("a", "e"),
    ]
    concepts = {
        "a": {"id": "a", "title": "A", "difficulty": 1, "topic": "mechanics"},
        "b": {"id": "b", "title": "B", "difficulty": 2, "topic": "mechanics"},
        "c": {"id": "c", "title": "C", "difficulty": 3, "topic": "mechanics"},
        "d": {"id": "d", "title": "D", "difficulty": 4, "topic": "mechanics"},
        "e": {"id": "e", "title": "E", "difficulty": 2, "topic": "mechanics"},
    }

    graph = GraphService(concepts=concepts, edges=edges)

    # Direct prerequisites for d
    direct_prereqs = graph.get_prerequisites("d", depth=1)
    assert direct_prereqs == ["c"]

    # Transitive prerequisites for d (depth=None)
    all_prereqs = graph.get_prerequisites("d")
    assert set(all_prereqs) == {"c", "b", "a"}


def test_graph_dependents() -> None:
    from app.content.service import GraphService

    edges = [
        ("a", "b"),
        ("b", "c"),
        ("a", "d"),
    ]
    concepts = {
        "a": {"id": "a", "title": "A", "difficulty": 1, "topic": "mechanics"},
        "b": {"id": "b", "title": "B", "difficulty": 2, "topic": "mechanics"},
        "c": {"id": "c", "title": "C", "difficulty": 3, "topic": "mechanics"},
        "d": {"id": "d", "title": "D", "difficulty": 2, "topic": "mechanics"},
    }
    graph = GraphService(concepts=concepts, edges=edges)

    dependents_of_a = graph.get_dependents("a")
    assert set(dependents_of_a) == {"b", "d"}


def test_graph_learning_path_topological_sort() -> None:
    from app.content.service import GraphService

    # d requires c, c requires b, b requires a
    # Valid learning path to master d: a -> b -> c -> d
    edges = [
        ("a", "b"),
        ("b", "c"),
        ("c", "d"),
    ]
    concepts = {
        "a": {"id": "a", "title": "A", "difficulty": 1, "topic": "mechanics"},
        "b": {"id": "b", "title": "B", "difficulty": 2, "topic": "mechanics"},
        "c": {"id": "c", "title": "C", "difficulty": 3, "topic": "mechanics"},
        "d": {"id": "d", "title": "D", "difficulty": 4, "topic": "mechanics"},
    }
    graph = GraphService(concepts=concepts, edges=edges)

    path = graph.learning_path("d")
    assert path == ["a", "b", "c", "d"]


def test_graph_cycle_guard() -> None:
    from app.content.service import GraphCycleError, GraphService

    # Manually inject a cycle in database edges: a -> b -> c -> a
    edges = [
        ("b", "a"),
        ("c", "b"),
        ("a", "c"),
    ]
    concepts = {
        "a": {"id": "a", "title": "A", "difficulty": 1, "topic": "mechanics"},
        "b": {"id": "b", "title": "B", "difficulty": 2, "topic": "mechanics"},
        "c": {"id": "c", "title": "C", "difficulty": 3, "topic": "mechanics"},
    }
    graph = GraphService(concepts=concepts, edges=edges)

    with pytest.raises(GraphCycleError):
        graph.learning_path("a")
