import sublime

import unittest

from test_runner import g_test_view

import registers

class TestRegisters(unittest.TestCase):
    def setUp(self):
        self.registers = registers.Registers(g_test_view)

    def testCanSetUnnamedRegister(self):
        self.registers._set_default_register("foo")
        actual = self.registers.__dict__[registers.REG_DEFAULT]
        self.assertEquals("foo", actual)
