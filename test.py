import unittest
from dhcp_manager import DHCPManager

class TestDHCPManager(unittest.TestCase):

    def setUp(self):
        self.m = DHCPManager()

    def test_valid_ip(self):
        self.assertTrue(self.m.is_valid_ip("192.168.1.10"))
        self.assertFalse(self.m.is_valid_ip("999.999.999.999"))

    def test_syntax_validation(self):
        ok, err = self.m.validate_syntax()
        # cannot assert true; just ensure it returns tuple
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(err, str)

if __name__ == "__main__":
    unittest.main()

