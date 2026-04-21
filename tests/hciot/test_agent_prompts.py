"""Tests for HCIoT agent_prompts — safety modularization."""

import unittest

from app.services.hciot.agent_prompts import PERSONA, build_system_instruction


class TestHciotAgentPrompts(unittest.TestCase):
    def test_persona_does_not_contain_priority_zero(self):
        """PERSONA should be clean — safety is injected by build_system_instruction."""
        for lang in ("zh", "en"):
            self.assertNotIn("PRIORITY 0", PERSONA[lang])
            self.assertNotIn("最高優先級", PERSONA[lang])

    def test_system_instruction_contains_safety_blocks(self):
        for lang in ("zh", "en"):
            instruction = build_system_instruction(PERSONA[lang], lang)
            self.assertIn("PRIORITY 0" if lang == "en" else "最高優先級", instruction)
            self.assertIn("1925", instruction)
            self.assertIn("1995", instruction)

    def test_system_instruction_contains_persona(self):
        for lang in ("zh", "en"):
            instruction = build_system_instruction(PERSONA[lang], lang)
            if lang == "zh":
                self.assertIn("小元", instruction)
            else:
                self.assertIn("Xiaoyuan", instruction)


if __name__ == "__main__":
    unittest.main()
