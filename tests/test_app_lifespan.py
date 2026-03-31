import unittest
from tests.app_main_test_support import get_test_app


app = get_test_app()


class TestAppLifespan(unittest.TestCase):
    def test_app_uses_lifespan_instead_of_on_startup_handlers(self):
        self.assertEqual(app.router.on_startup, [])


if __name__ == "__main__":
    unittest.main()
