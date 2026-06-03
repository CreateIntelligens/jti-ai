"""Tests for JTI agent_prompts — safety modularization."""

import unittest

from app.services.jti.agent_prompts import PERSONA, build_system_instruction
from app.services.jti.main_agent import MainAgent


class TestJtiAgentPrompts(unittest.TestCase):
    def test_persona_does_not_contain_priority_zero(self):
        """PERSONA should be clean — safety is injected by build_system_instruction."""
        for lang in ("zh", "en"):
            self.assertNotIn("PRIORITY 0", PERSONA[lang])
            self.assertNotIn("最高優先級", PERSONA[lang])

    def test_system_instruction_contains_safety_blocks(self):
        for lang in ("zh", "en"):
            instruction = build_system_instruction(PERSONA[lang], lang)
            # Priority 0 should be prepended
            self.assertIn("PRIORITY 0" if lang == "en" else "最高優先級", instruction)
            # Sensitive handling should be in the rules section
            self.assertIn("1925", instruction)
            self.assertIn("1995", instruction)

    def test_system_instruction_does_not_include_core_rules(self):
        zh_instruction = build_system_instruction(PERSONA["zh"], "zh")
        en_instruction = build_system_instruction(PERSONA["en"], "en")
        self.assertNotIn("CORE", zh_instruction)
        self.assertNotIn("CORE", en_instruction)

    def test_system_instruction_contains_persona(self):
        for lang in ("zh", "en"):
            instruction = build_system_instruction(PERSONA[lang], lang)
            # The persona identity text should be present
            self.assertIn("Ploom X", instruction)

    def test_search_tool_preserves_english_query_language(self):
        agent = MainAgent()
        tool = agent._rag_tool_declaration
        declaration = tool.function_declarations[0]
        description = declaration.parameters.properties["queries"].description

        self.assertIn("English questions use English queries", description)


if __name__ == "__main__":
    unittest.main()
