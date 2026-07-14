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

    def test_hciot_safety_requires_explicit_risk_signal(self):
        instruction = build_system_instruction(PERSONA["zh"], "zh")

        self.assertIn("相關字眼", instruction)
        self.assertIn("諧音", instruction)
        self.assertIn("我是", instruction)
        self.assertIn("正常自我介紹", instruction)
        self.assertIn("不得觸發", instruction)
        self.assertIn("害怕、難過、焦慮、壓力大、疲憊或心情不好", instruction)
        self.assertNotIn("自我傷害 / 強烈負面情緒", instruction)

    def test_hciot_safety_uses_non_commanding_crisis_tone(self):
        instruction = build_system_instruction(PERSONA["zh"], "zh")

        self.assertIn("非命令式", instruction)
        self.assertIn("不要自動假設使用者正處於立即危險", instruction)
        self.assertIn("避免使用「請一定」「務必」", instruction)


if __name__ == "__main__":
    unittest.main()
