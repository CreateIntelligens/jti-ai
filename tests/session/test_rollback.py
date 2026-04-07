import unittest
from unittest.mock import patch, MagicMock
from app.services.logging.mongo_conversation_logger import MongoConversationLogger

class TestRollback(unittest.TestCase):
    @patch("app.services.logging.mongo_conversation_logger.get_mongo_db")
    def setUp(self, mock_get_db):
        self.mock_db = MagicMock()
        mock_get_db.return_value = self.mock_db
        self.mock_conversations = MagicMock()
        self.mock_db.__getitem__.return_value = self.mock_conversations
        self.logger = MongoConversationLogger()

    def test_delete_turns_from(self):
        # Setup
        session_id = "test-session"
        turn_number = 3
        
        # Action
        self.logger.delete_turns_from(session_id, turn_number)
        
        # Verify
        self.mock_conversations.delete_many.assert_called_once()
        call_args = self.mock_conversations.delete_many.call_args
        query = call_args[0][0]
        
        # Ensure the query correctly targets the session and turn number >= 3
        self.assertEqual(query["session_id"], session_id)
        self.assertEqual(query["turn_number"], {"$gte": turn_number})
        
    def test_delete_turns_from_first_turn(self):
        # Setup
        session_id = "test-session"
        turn_number = 1
        
        # Action
        self.logger.delete_turns_from(session_id, turn_number)
        
        # Verify
        self.mock_conversations.delete_many.assert_called_once()
        call_args = self.mock_conversations.delete_many.call_args
        query = call_args[0][0]
        
        self.assertEqual(query["session_id"], session_id)
        self.assertEqual(query["turn_number"], {"$gte": turn_number})

if __name__ == "__main__":
    unittest.main()
