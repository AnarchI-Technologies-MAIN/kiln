import unittest

from engine.injector_authorization import split_terms


class InjectorAuthorizationTests(unittest.TestCase):
    def test_terms_are_deterministic(self):
        observed = split_terms("token;owner;token")
        self.assertEqual(observed, ("owner", "token"))

    def test_empty_terms_remain_empty(self):
        self.assertEqual(split_terms(""), tuple())


if __name__ == "__main__":
    unittest.main()
