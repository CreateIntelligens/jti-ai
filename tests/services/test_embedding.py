import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import os
import sys

# Ensure app is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.services.embedding.service import EmbeddingService
from app.services.embedding.errors import EmbeddingModelError, EmbeddingEncodingError

# Mock FlagEmbedding module before tests run
mock_flag_embedding = MagicMock()
mock_flag_model = MagicMock()
mock_flag_embedding.FlagModel = mock_flag_model
sys.modules['FlagEmbedding'] = mock_flag_embedding

class TestEmbeddingService(unittest.TestCase):

    def setUp(self):
        # Reset singleton instance for tests
        EmbeddingService._instance = None
        EmbeddingService._model = None
        mock_flag_model.reset_mock(side_effect=True)


    @patch('torch.cuda.is_available', return_value=False)
    def test_singleton_and_lazy_loading(self, mock_cuda):
        service1 = EmbeddingService.get_instance()
        service2 = EmbeddingService.get_instance()
        self.assertIs(service1, service2)
        
        # Model should not be loaded yet
        self.assertIsNone(EmbeddingService._model)
        
        # Trigger model loading
        mock_model_instance = MagicMock()
        mock_flag_model.reset_mock()
        mock_flag_model.return_value = mock_model_instance
        mock_model_instance.encode.return_value = np.random.rand(1, 1024)
        
        service1.encode("test")
        mock_flag_model.assert_called_once()
        self.assertIsNotNone(EmbeddingService._model)

    @patch('torch.cuda.is_available', return_value=False)
    def test_encode_single_string(self, mock_cuda):
        mock_model_instance = MagicMock()
        mock_flag_model.reset_mock()
        mock_flag_model.return_value = mock_model_instance
        mock_model_instance.encode.return_value = np.random.rand(1, 1024)
        
        service = EmbeddingService.get_instance()
        result = service.encode("hello world")
        
        self.assertEqual(result.shape, (1, 1024))
        mock_model_instance.encode.assert_called_once_with(
            ["hello world"],
            batch_size=32,
            max_length=8192
        )

    def test_encode_batch(self):
        mock_model_instance = MagicMock()
        mock_flag_model.reset_mock()
        mock_flag_model.return_value = mock_model_instance
        mock_model_instance.encode.return_value = np.random.rand(3, 1024)
        
        service = EmbeddingService.get_instance()
        texts = ["one", "two", "three"]
        result = service.encode(texts)
        
        self.assertEqual(result.shape, (3, 1024))
        mock_model_instance.encode.assert_called_once_with(
            texts,
            batch_size=32,
            max_length=8192
        )

    def test_model_loading_failure(self):
        mock_flag_model.reset_mock()
        mock_flag_model.side_effect = Exception("CUDA error")
        
        service = EmbeddingService.get_instance()
        with self.assertRaises(EmbeddingModelError):
            service.encode("test")

    def test_encoding_failure(self):
        mock_model_instance = MagicMock()
        mock_flag_model.reset_mock()
        mock_flag_model.return_value = mock_model_instance
        mock_model_instance.encode.side_effect = Exception("Runtime error")
        
        service = EmbeddingService.get_instance()
        with self.assertRaises(EmbeddingEncodingError):
            service.encode("test")

if __name__ == '__main__':
    unittest.main()
