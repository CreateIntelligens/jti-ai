import unittest
from tempfile import TemporaryDirectory

from app.services.logging.conversation_logger import ConversationLogger


class TestConversationLogger(unittest.TestCase):
    def test_log_conversation_requires_mode(self):
        with TemporaryDirectory() as tmp_dir:
            logger = ConversationLogger(log_dir=tmp_dir)

            with self.assertRaises(TypeError):
                logger.log_conversation(
                    session_id="test-123",
                    user_message="開始測驗",
                    agent_response="好的，開始測驗",
                )
            with self.assertRaises(ValueError):
                logger.log_conversation(
                    session_id="test-123",
                    user_message="開始測驗",
                    agent_response="好的，開始測驗",
                    mode="",
                )


if __name__ == "__main__":
    unittest.main()
