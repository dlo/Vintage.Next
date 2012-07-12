import sublime, sublime_plugin

from vintage import VintageState
from vintage import parse_motion

class ViD(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        args = parse_motion(**kwargs)
        vintage_state = VintageState(self.view)
        vintage_state.motion = {"forward": true, "by": "lines"}
        vintage_state.action = ACTION_DELETE
        vintage_state.run()

