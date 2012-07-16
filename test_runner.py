import sublime
import sublime_plugin

import os
import sys
# todo(guillermooo): maybe allow other test frameworks?
import unittest
import StringIO

# /////////////////////////////////////////////////////////////////////////////
# ********** Remember to enable Vintage.Next or this will not work. ***********
# /////////////////////////////////////////////////////////////////////////////

TEST_DATA_FILE_BASENAME = 'vintageex_test_data.txt'
TEST_DATA_PATH = os.path.join(sublime.packages_path(),
                              'Vintage.Next/tests/data/%s' % TEST_DATA_FILE_BASENAME)

class TestsState(object):
    def __init__(self):
        self.test_suite_to_run = ''
        self.test_view = None
        self.test_suite_to_run = ''
        self._suites = []

    @property
    def must_run_tests(self):
        return len(self._suites) != 0

    def add_test_suite(self, name):
        # TODO(guillermooo): must enforce one type of test only (i.e. with test
        # data file or without.)
        self._suites.append(name)

    def iter_module_names(self):
        for name in self._suites:
            module_or_modules = test_suites[name][1]
            if isinstance(module_or_modules, list):
                for item in module_or_modules:
                    yield item
            else:
                yield module_or_modules

    def run_all(self):
        for name in self._suites:
            cmd, _ = test_suites[name]
            # XXX(guillermooo): this feels like cheating. improve this.
            sublime.active_window().run_command(cmd, dict(suite_name=name))

    def reset(self):
        self.test_suite_to_run = ''
        self.test_view = None
        self._suites = []

tests_state = TestsState()

# XXX(guillermooo): use named tuples perhaps?
test_suites = {
        'registers': ['vintage_next_run_data_file_based_tests', 'tests.test_registers'],
        'settings': ['vintage_next_run_data_file_based_tests', 'tests.test_settings'],
        'all with data file': ['vintage_next_run_data_file_based_tests', ['tests.test_settings', 'tests.test_registers']],
}


def print_to_view(view, obtain_content):
    edit = view.begin_edit()
    view.insert(edit, 0, obtain_content())
    view.end_edit(edit)
    view.set_scratch(True)

    return view


class DisplayVintageNextTests(sublime_plugin.WindowCommand):
    def run(self):
        tests_state.reset()
        self.window.show_quick_panel(sorted(test_suites.keys()), self.run_suite)

    def run_suite(self, idx):
        suite_name = sorted(test_suites.keys())[idx]
        tests_state.add_test_suite(suite_name)
        tests_state.run_all()


class VintageNextRunSimpleTestsCommand(sublime_plugin.WindowCommand):
    def run(self, suite_name):
        bucket = StringIO.StringIO()
        _, suite = test_suites[suite_name]
        suite = unittest.defaultTestLoader.loadTestsFromName(suite)
        unittest.TextTestRunner(stream=bucket, verbosity=1).run(suite)

        print_to_view(self.window.new_file(), bucket.getvalue)


class VintageNextRunDataFileBasedTests(sublime_plugin.WindowCommand):
    def run(self, suite_name):
        self.window.open_file(TEST_DATA_PATH)


class TestDataDispatcher(sublime_plugin.EventListener):
    def on_load(self, view):
        if not tests_state.must_run_tests:
            return

        if os.path.basename(view.file_name()) == TEST_DATA_FILE_BASENAME:
            tests_state.test_view = view
            suite = unittest.TestLoader().loadTestsFromNames(tests_state.iter_module_names())

            bucket = StringIO.StringIO()
            unittest.TextTestRunner(stream=bucket, verbosity=1).run(suite)

            v = print_to_view(view.window().new_file(), bucket.getvalue)
            # In this order, or Sublime Text will fail.
            v.window().focus_view(view)
            view.window().run_command('close')
