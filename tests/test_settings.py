import unittest

from test_runner import tests_state

# XXX(guillermooo): Somehow ViewSettings seems to be a better name for this.
from vintage import SublimeSettings


class TestSublimeSettings(unittest.TestCase):
    def setUp(self):
        self.settings = SublimeSettings(tests_state.test_view)
        self.OPTION_FOO = 'foo'
        self.NON_EXISTENT_OPTION = 'fizz'
        tests_state.test_view.settings().erase(self.NON_EXISTENT_OPTION)

    def tearDown(self):
        tests_state.test_view.settings().erase(self.OPTION_FOO)

    def testCanSetSettings(self):
        self.settings[self.OPTION_FOO] = "bar"
        self.assertEqual(tests_state.test_view.settings().get(self.OPTION_FOO), "bar")

    def testCanGetSettings(self):
        self.settings[self.OPTION_FOO] = "bar"
        self.assertEqual(self.settings[self.OPTION_FOO], "bar")

    # XXX(guillermooo): Is this what we want?
    def testGettingNonExistentSettingReturnsNone(self):
        self.assertEqual(self.settings[self.NON_EXISTENT_OPTION], None)
