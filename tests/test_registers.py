import sublime

import unittest

from test_runner import tests_state

import registers

# Temporary mock object for Settigs.
# FIXME: use mock instead?; import from vintage?
class Settings(object):
    def __init__(self, view):
        self.view = view

    def __getitem__(self, key):
        return self.view.settings().get(key)

    def __setitem__(self, key, value):
        self.view.settings().set(key, value)


class RegistersTest(unittest.TestCase):
    def setUp(self):
        self.clipboard_content = sublime.get_clipboard()
        sublime.set_clipboard('')
        self.settings = Settings(tests_state.test_view)
        self.registers = registers.Registers(tests_state.test_view, self.settings)

    def tearDown(self):
        sublime.set_clipboard(self.clipboard_content)
        tests_state.test_view.settings().erase('vintage_use_sys_clipboard')


class TestRegistersHelpers(RegistersTest):
    def testCanSetUnnamedRegister(self):
        self.registers._set_default_register("foo")
        actual = registers._REGISTER_DATA[registers.REG_UNNAMED]
        self.assertEqual("foo", actual)

    def testBlackHoleRegisterWontBeSetEver(self):
        self.registers.set(registers.REG_BLACK_HOLE, "foo")
        # todo(guillermooo): test this better
        self.assertEqual(self.registers.__dict__.get(registers.REG_BLACK_HOLE, None), None)


class TestSettingRegisters(RegistersTest):
    def testCanSetLetterRegisters(self):
        self.registers.set("a", "foo")
        self.assertEqual(registers._REGISTER_DATA["a"], "foo")

    def testCanSetNumberRegisters(self):
        self.registers.set("0", "foo")
        self.registers.set(1, "bar")
        self.assertEqual(registers._REGISTER_DATA["0"], "foo")
        self.assertEqual(registers._REGISTER_DATA["1"], "bar")

    def testCannotSetUppercaseRegister(self):
        self.registers.set("A", "foo")
        self.assertEqual(self.registers.__dict__.get("a", None), None)

    def testCannotSetNonAlphanumericRegister(self):
        self.registers.set("$", "foo")
        self.assertEqual(self.registers.__dict__.get("$", None), None)

    def testNewlySetRegisterValueIsAlwaysPropagatedToUnnamedRegister(self):
        self.registers.set("a", "foo")
        self.assertEqual(registers._REGISTER_DATA["a"],
                         registers._REGISTER_DATA[registers.REG_UNNAMED])
        self.registers.set("0", "foo")
        self.assertEqual(registers._REGISTER_DATA["0"],
                         registers._REGISTER_DATA[registers.REG_UNNAMED])

    def testSysClipboardIsSetWhenSettingRegisterIfRequired(self):
        self.settings['vintage_use_sys_clipboard'] = True
        self.registers.set("a", "foo")
        self.assertEqual(sublime.get_clipboard(),
                         registers._REGISTER_DATA["a"])

    def testSettingViaMethodEqualsSettingsViaAttributeAccess(self):
        self.registers["a"] = "foo"
        self.assertEqual(registers._REGISTER_DATA["a"],
                         "foo")
        self.registers.set("a", "bar")
        self.assertEqual(registers._REGISTER_DATA["a"],
                         "bar")


class TestAppendingToRegisters(RegistersTest):
    def testCannotAppendToLowerCaseRegister(self):
        self.assertRaises(AssertionError, self.registers.append_to, "a", "foo")

    def testCannotAppendToNonAsciiCapitalLetters(self):
        self.assertRaises(AssertionError, self.registers.append_to, "1", "foo")
        self.assertRaises(AssertionError, self.registers.append_to, "$", "foo")

    def testCanAppendToRegister(self):
        self.registers.set("a", "foo")
        self.registers.append_to("A", "bar")
        self.assertEqual(registers._REGISTER_DATA["a"],
                         "foobar")

    def testAppendingViaMethodEqualsAppendingViaAttributeAccess(self):
        registers._REGISTER_DATA["a"] = "foo"
        self.registers["A"] = "bar"
        self.assertEqual(registers._REGISTER_DATA["a"],
                         "foobar")
        registers._REGISTER_DATA["b"] = "foo"
        self.registers.append_to("B", "bar")
        self.assertEqual(registers._REGISTER_DATA["b"],
                         "foobar")

    def testNewlyAppendedValueToRegisterIsAlwaysPropagatedToUnnamedRegister(self):
        self.registers.append_to("A", "foo")
        self.assertEqual(registers._REGISTER_DATA["a"],
                         registers._REGISTER_DATA[registers.REG_UNNAMED])

    def testSysClipboardIsSetWhenAppendingToRegisterIfRequired(self):
        self.settings['vintage_use_sys_clipboard'] = True
        self.registers.append_to("A", "foo")
        self.assertEqual(sublime.get_clipboard(),
                         registers._REGISTER_DATA["a"])


class TestGettingRegisters(RegistersTest):
    def testSetClipboardIfSettingsRequireIt(self):
        self.settings['vintage_use_sys_clipboard'] = True
        sublime.set_clipboard("foo")
        self.assertEqual(sublime.get_clipboard(), self.registers[registers.REG_UNNAMED])
        self.assertEqual(sublime.get_clipboard(), self.registers.get(registers.REG_UNNAMED))
