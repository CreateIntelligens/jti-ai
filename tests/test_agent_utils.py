import unittest

from app.services.agent_utils import strip_citations, strip_core_markup


class TestAgentUtils(unittest.TestCase):
    def test_strip_core_markup_removes_wrapper_but_keeps_content(self):
        self.assertEqual(
            strip_core_markup("before [CORE: important fact] after"),
            "before important fact after",
        )

    def test_strip_citations_removes_core_wrapper_but_keeps_content(self):
        text = (
            "What is heated tobacco "
            "[CORE: 加熱菸跟紙菸一樣皆含有菸草。]"
            "[cite: knowledge-base]"
        )

        self.assertEqual(
            strip_citations(text),
            "What is heated tobacco 加熱菸跟紙菸一樣皆含有菸草。",
        )


if __name__ == "__main__":
    unittest.main()
