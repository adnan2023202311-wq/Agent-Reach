"""Unit tests for PromptLibrary (M6.6)."""

from __future__ import annotations

import pytest

from prompts.library import (
    PromptEvaluationMetadata,
    PromptLibrary,
    PromptTemplate,
)


@pytest.fixture
def library() -> PromptLibrary:
    return PromptLibrary()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_returns_template(self, library: PromptLibrary) -> None:
        t = library.register("greet", "Hello, {{ name }}!")
        assert t.name == "greet"
        assert t.template == "Hello, {{ name }}!"
        assert t.variables == ["name"]
        assert t.version == 1

    def test_register_extracts_multiple_variables(self, library: PromptLibrary) -> None:
        t = library.register(
            "summarize",
            "Summarize this {{ document }} in {{ style }}.",
        )
        assert t.variables == ["document", "style"]

    def test_register_extracts_unique_variables(self, library: PromptLibrary) -> None:
        t = library.register("repeat", "{{ x }} and {{ x }} again")
        assert t.variables == ["x"]

    def test_register_no_variables(self, library: PromptLibrary) -> None:
        t = library.register("simple", "No variables here.")
        assert t.variables == []

    def test_register_with_metadata(self, library: PromptLibrary) -> None:
        t = library.register(
            "greet",
            "Hello, {{ name }}!",
            description="Greets a person",
            tags=["greeting", "basic"],
            owner="alice",
            metadata={"locale": "en"},
        )
        assert t.description == "Greets a person"
        assert t.tags == ["greeting", "basic"]
        assert t.owner == "alice"
        assert t.metadata == {"locale": "en"}

    def test_register_bumps_version(self, library: PromptLibrary) -> None:
        t1 = library.register("greet", "v1")
        assert t1.version == 1
        t2 = library.register("greet", "v2")
        assert t2.version == 2
        assert t2.prompt_id == t1.prompt_id  # same ID

    def test_register_preserves_id(self, library: PromptLibrary) -> None:
        t1 = library.register("greet", "v1")
        prompt_id = t1.prompt_id
        t2 = library.register("greet", "v2")
        assert t2.prompt_id == prompt_id

    def test_unregister(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello")
        assert library.unregister("greet") is True
        assert library.get("greet") is None

    def test_unregister_missing(self, library: PromptLibrary) -> None:
        assert library.unregister("ghost") is False


# ---------------------------------------------------------------------------
# Evaluation metadata
# ---------------------------------------------------------------------------


class TestEvaluationMetadata:
    def test_set_evaluation(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{ name }}!")
        ev = library.set_evaluation(
            "greet",
            expected_output="Hello, World!",
            criteria=["exact_match"],
            threshold=0.9,
        )
        assert ev is not None
        assert ev.expected_output == "Hello, World!"
        assert ev.criteria == ["exact_match"]
        assert ev.threshold == 0.9

    def test_set_evaluation_missing_prompt(self, library: PromptLibrary) -> None:
        assert library.set_evaluation("ghost") is None

    def test_get_evaluation(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello")
        library.set_evaluation("greet", expected_output="Hi")
        ev = library.get_evaluation("greet")
        assert ev is not None
        assert ev.expected_output == "Hi"

    def test_get_evaluation_missing(self, library: PromptLibrary) -> None:
        assert library.get_evaluation("ghost") is None

    def test_evaluation_metadata_to_dict(self) -> None:
        ev = PromptEvaluationMetadata(
            expected_output="Hi",
            criteria=["exact"],
            threshold=0.95,
            notes="test",
        )
        d = ev.to_dict()
        assert d == {
            "expected_output": "Hi",
            "criteria": ["exact"],
            "threshold": 0.95,
            "notes": "test",
        }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def test_render_substitutes_variables(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{ name }}!")
        result = library.render("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_render_multiple_variables(self, library: PromptLibrary) -> None:
        library.register("full", "{{ greeting }}, {{ name }}!")
        result = library.render("full", {"greeting": "Hi", "name": "Alice"})
        assert result == "Hi, Alice!"

    def test_render_missing_variable_left_as_is(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{ name }}!")
        result = library.render("greet", {})
        assert result == "Hello, {{ name }}!"

    def test_render_strict_raises_on_missing(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{ name }}!")
        with pytest.raises(KeyError, match="Missing variables"):
            library.render_strict("greet", {})

    def test_render_strict_succeeds_when_all_present(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{ name }}!")
        result = library.render_strict("greet", {"name": "World"})
        assert result == "Hello, World!"

    def test_render_missing_prompt_raises(self, library: PromptLibrary) -> None:
        with pytest.raises(KeyError, match="not registered"):
            library.render("ghost", {})

    def test_render_with_whitespace_in_placeholder(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello, {{name}} and {{ name }}!")
        result = library.render("greet", {"name": "X"})
        assert result == "Hello, X and X!"


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


class TestAccess:
    def test_get(self, library: PromptLibrary) -> None:
        library.register("greet", "Hello")
        t = library.get("greet")
        assert t is not None
        assert t.name == "greet"

    def test_get_missing(self, library: PromptLibrary) -> None:
        assert library.get("ghost") is None

    def test_get_by_id(self, library: PromptLibrary) -> None:
        t = library.register("greet", "Hello")
        assert library.get_by_id(t.prompt_id) is t

    def test_get_by_id_missing(self, library: PromptLibrary) -> None:
        assert library.get_by_id("ghost") is None

    def test_get_version(self, library: PromptLibrary) -> None:
        library.register("greet", "v1")
        library.register("greet", "v2")
        assert library.get_version("greet") == 2

    def test_get_version_missing(self, library: PromptLibrary) -> None:
        assert library.get_version("ghost") == 0


# ---------------------------------------------------------------------------
# Listing and discovery
# ---------------------------------------------------------------------------


class TestListing:
    def test_list_names(self, library: PromptLibrary) -> None:
        library.register("beta", "b")
        library.register("alpha", "a")
        assert library.list_names() == ["alpha", "beta"]

    def test_list_prompts(self, library: PromptLibrary) -> None:
        library.register("a", "x")
        library.register("b", "y")
        prompts = library.list_prompts()
        assert [p.name for p in prompts] == ["a", "b"]

    def test_list_prompts_by_tag(self, library: PromptLibrary) -> None:
        library.register("a", "x", tags=["greeting"])
        library.register("b", "y", tags=["farewell"])
        results = library.list_prompts(tag="greeting")
        assert [p.name for p in results] == ["a"]

    def test_list_prompts_by_owner(self, library: PromptLibrary) -> None:
        library.register("a", "x", owner="alice")
        library.register("b", "y", owner="bob")
        results = library.list_prompts(owner="alice")
        assert [p.name for p in results] == ["a"]

    def test_list_tags(self, library: PromptLibrary) -> None:
        library.register("a", "x", tags=["t1", "t2"])
        library.register("b", "y", tags=["t2", "t3"])
        assert library.list_tags() == ["t1", "t2", "t3"]

    def test_search_by_name(self, library: PromptLibrary) -> None:
        library.register("greeting", "Hello")
        library.register("farewell", "Bye")
        results = library.search("greet")
        assert [p.name for p in results] == ["greeting"]

    def test_search_by_description(self, library: PromptLibrary) -> None:
        library.register("a", "x", description="Says hello")
        library.register("b", "y", description="Says bye")
        results = library.search("hello")
        assert [p.name for p in results] == ["a"]

    def test_search_by_tag(self, library: PromptLibrary) -> None:
        library.register("a", "x", tags=["greeting"])
        library.register("b", "y", tags=["farewell"])
        results = library.search("greeting")
        assert [p.name for p in results] == ["a"]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_get_stats_empty(self, library: PromptLibrary) -> None:
        stats = library.get_stats()
        assert stats == {"total": 0, "with_evaluation": 0, "tags": 0}

    def test_get_stats_populated(self, library: PromptLibrary) -> None:
        library.register("a", "x", tags=["t1"])
        library.register("b", "y", tags=["t2"])
        library.set_evaluation("a")
        stats = library.get_stats()
        assert stats["total"] == 2
        assert stats["with_evaluation"] == 1
        assert stats["tags"] == 2


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_template_to_dict(self, library: PromptLibrary) -> None:
        t = library.register(
            "greet",
            "Hello, {{ name }}!",
            description="Greets",
            tags=["greeting"],
        )
        d = t.to_dict()
        assert d["name"] == "greet"
        assert d["template"] == "Hello, {{ name }}!"
        assert d["variables"] == ["name"]
        assert d["tags"] == ["greeting"]


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear(self, library: PromptLibrary) -> None:
        library.register("a", "x")
        library.register("b", "y")
        library.clear()
        assert library.list_names() == []
        assert library.get("a") is None
