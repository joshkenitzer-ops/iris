import unittest

from app.enforcement import (
    DuplicateToolError,
    EnforcementKind,
    ToolNotFoundError,
    ToolRegistry,
    ToolResult,
    tool,
)


class TestToolRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()

    def test_register_and_get(self) -> None:
        def handler(text: str) -> ToolResult:
            return ToolResult(passed=True)

        from app.enforcement import ToolSpec

        self.registry.register(
            ToolSpec(
                id="T-99.1",
                name="dummy_check",
                description="A dummy check.",
                kind=EnforcementKind.TOOL,
                input_schema={"type": "object", "properties": {}},
                handler=handler,
            )
        )
        spec = self.registry.get("T-99.1")
        self.assertEqual(spec.name, "dummy_check")

    def test_duplicate_id_rejected(self) -> None:
        from app.enforcement import ToolSpec

        def handler(**kwargs) -> ToolResult:
            return ToolResult(passed=True)

        spec = ToolSpec(
            id="T-99.1",
            name="a",
            description="d",
            kind=EnforcementKind.TOOL,
            input_schema={},
            handler=handler,
        )
        self.registry.register(spec)
        with self.assertRaises(DuplicateToolError):
            self.registry.register(
                ToolSpec(
                    id="T-99.1",
                    name="b",
                    description="d",
                    kind=EnforcementKind.TOOL,
                    input_schema={},
                    handler=handler,
                )
            )

    def test_missing_tool_raises(self) -> None:
        with self.assertRaises(ToolNotFoundError):
            self.registry.get("T-does-not-exist")

    def test_claude_schema_uses_input_schema_key(self) -> None:
        """Anthropic's tool schema field is `input_schema`, not
        `parameters`. A regression here would silently fail against
        the real API rather than raising locally, so it's worth
        pinning as a test."""
        from app.enforcement import ToolSpec

        def handler(**kwargs) -> ToolResult:
            return ToolResult(passed=True)

        self.registry.register(
            ToolSpec(
                id="T-99.2",
                name="schema_check",
                description="d",
                kind=EnforcementKind.TOOL,
                input_schema={"type": "object", "properties": {"x": {"type": "string"}}},
                handler=handler,
            )
        )
        schemas = self.registry.claude_schemas()
        self.assertEqual(len(schemas), 1)
        self.assertIn("input_schema", schemas[0])
        self.assertNotIn("parameters", schemas[0])
        self.assertTrue(schemas[0]["description"].startswith("[T-99.2]"))

    def test_needs_session_tool_requires_session_arg(self) -> None:
        from app.enforcement import ToolSpec

        def handler(session, **kwargs) -> ToolResult:
            return ToolResult(passed=True, data={"saw_session": session})

        self.registry.register(
            ToolSpec(
                id="T-99.3",
                name="session_dependent",
                description="d",
                kind=EnforcementKind.TOOL,
                input_schema={},
                handler=handler,
                needs_session=True,
            )
        )
        with self.assertRaises(ValueError):
            self.registry.dispatch("session_dependent", {})

        result = self.registry.dispatch("session_dependent", {}, session="fake-session")
        self.assertEqual(result.data["saw_session"], "fake-session")


if __name__ == "__main__":
    unittest.main()
