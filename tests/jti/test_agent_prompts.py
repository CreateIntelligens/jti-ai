import unittest

from app.services.jti.agent_prompts import PERSONA, build_system_instruction


class TestJtiAgentPrompts(unittest.TestCase):
    def test_system_instruction_does_not_include_core_rules(self):
        zh_instruction = build_system_instruction(PERSONA["zh"], "zh")
        en_instruction = build_system_instruction(PERSONA["en"], "en")

        self.assertNotIn("CORE", zh_instruction)
        self.assertNotIn("CORE", en_instruction)


if __name__ == "__main__":
    unittest.main()
