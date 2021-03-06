import sublime
import sublime_plugin

import os.path

from registers import Registers
from transformer import Transformer

from vintage_next import logging


log = logging.Logger(level=logging.DEBUG, prefix="Vintage.Next: ")


print "XXX" * 30
print "XXX" * 30


# Normal: Motions apply to all the characters they select
MOTION_MODE_NORMAL = 0
# Used in visual line mode: Motions are extended to BOL and EOL.
MOTION_MODE_LINE = 2

MODE_NORMAL = 1 << 0
MODE_VISUAL = 1 << 1
MODE_SELECT = 1 << 2
MODE_INSERT = 1 << 3
MODE_COMMAND_LINE = 1 << 4
MODE_EX = 1 << 5
MODE_REPLACE = 1 << 7
MODE_VIRTUAL_REPLACE = 1 << 8
MODE_INSERT_NORMAL = 1 << 9
MODE_INSERT_VISUAL = 1 << 10
MODE_VISUAL_LINE = 1 << 11

ACTION_DELETE = 1 << 0
ACTION_COPY = 1 << 1
ACTION_PASTE = 1 << 2

SELECTION_CHARACTER = 1 << 0
SELECTION_LINE = 1 << 1

DIRECTION_UP = 1 << 0
DIRECTION_RIGHT = 1 << 1
DIRECTION_DOWN = 1 << 2
DIRECTION_LEFT = 1 << 3

MODE_MAPPING = {
    'vi_mode_normal': MODE_NORMAL,
    'vi_mode_insert': MODE_INSERT,
    'vi_mode_visual_line': MODE_VISUAL_LINE,
    'vi_mode_visual': MODE_VISUAL,
    'vi_mode_visual_all': MODE_VISUAL | MODE_VISUAL_LINE,
    'vi_mode_motion': MODE_NORMAL | MODE_VISUAL | MODE_VISUAL_LINE,
}


def mode_to_str(mode):
    for k, v in MODE_MAPPING.iteritems():
        if mode == v:
            return k
    return "Unknown mode: %s" % mode

ACTION_FOLLOWUP_MODES = {
    'd': MODE_NORMAL,
    'D': MODE_NORMAL,
    's': MODE_INSERT,
    'S': MODE_INSERT,
    'x': MODE_NORMAL,
    'X': MODE_NORMAL,
    'c': MODE_INSERT,
    'C': MODE_INSERT,
    'y': MODE_NORMAL,
    'Y': MODE_NORMAL
}

ACTION_DIRECTIONS = {
    'd': DIRECTION_DOWN,
    'D': DIRECTION_DOWN,
    's': DIRECTION_RIGHT,
    'S': DIRECTION_DOWN,
    'x': DIRECTION_RIGHT,
    'X': DIRECTION_LEFT,
    'c': DIRECTION_DOWN,
    'C': DIRECTION_DOWN,
    'y': DIRECTION_DOWN,
    'Y': DIRECTION_DOWN
}

ACTIONS_REQUIRING_SELECTIONS = ('c', 'd')

VISUAL_ACTIONS = ('s', 'D', 'c', 'C', 'x', 'X')
LINEWISE_ACTIONS = ('o', 'O', 'd', 'D', 'c', 'C', 'S')
REPEATABLE_ACTIONS = ('R', 'o', 'O', 'a', 'A', 'd', 'D', 'x', 'X', 'c', 'C')

# Registers are used for clipboards and macro storage
g_registers = {}

class ViAction(object):
    def __init__(self, motion=None, line=True, count=1, delete=False,
            insert=False):
        """
        Commands are the foundation of all Vim actions. Every action is an
        instance of a ViCommand and can fit into the following construct (in
        the same order).

        1. Initial view motion command. Defaults to identity.
        2. Enter one of visual mode or visual line mode.
        3. Perform movement [count] times.
        4. [optional] Delete selection.
        5. [optional] Save contents of selection to register.
        6. Exit visual mode.
        7. [optional] Enter insert mode.
        """
        self.line = line
        self.count = count
        self.delete = delete
        self.insert = insert

    def run(self):
        if self.delete:
            self.view.run_command("vi_x")

        if self.insert:
            self.view.run_command("vi_enter_insert_mode")


class SublimeSettings(object):
    """ Helper class for accessing settings values from views """

    def __init__(self, view):
        self.view = view

    def __getitem__(self, key):
        return self.view.settings().get(key)

    def __setitem__(self, key, value):
        self.view.settings().set(key, value)


class VintageSettings(object):
    """ Helper class for accessing settings related to Vintage. """

    def __init__(self, view):
        self.view = view
        self.log = log
        if not isinstance(self.view.settings().get('vintage'), dict):
            self.view.settings().set('vintage', dict())

    def __getitem__(self, key):
        try:
            value = self.view.settings().get('vintage').get(key)
            self.log.debug("VintageSettings - Getting %s (%s)" % (key, value))
        except (KeyError, AttributeError):
            value = None
        return value

    def __setitem__(self, key, value):
        self.log.debug("VintageSettings - Setting %s to %s" % (key, value))
        setts = self.view.settings().get('vintage')
        setts[key] = value
        self.view.settings().set('vintage', setts)


class Direction:
    @staticmethod
    def from_motion(motion):
        if motion['forward']:
            if motion['by'] == 'lines':
                return DIRECTION_DOWN
            else:
                return DIRECTION_RIGHT
        else:
            if motion['by'] == 'lines':
                return DIRECTION_UP
            else:
                return DIRECTION_LEFT


class VintageState(object):
    registers = Registers()
    transformer = Transformer()

    def __init__(self, view):
        self.log = log
        self.log.debug("=" * 80)
        self.log.debug("Initializing VintageState...")
        self.view = view
        self.settings = SublimeSettings(self.view)
        self.vintage_settings = VintageSettings(self.view)
        self.log.debug("VintageState - Mode is currently %s" % mode_to_str(self.mode))

    @property
    def reset_count(self):
        # This flag is set whenever we should reset the count modifier when
        # accepting digit input.
        value = self.vintage_settings['reset_count']
        if value is None:
            return True
        self.log.debug("VintageState - Getting reset_count (%s)" % (value))
        return value

    @reset_count.setter
    def reset_count(self, value):
        self.vintage_settings['reset_count'] = value

    @property
    def digits(self):
        value = self.vintage_settings['digits']
        if not value:
            value = []
        self.log.debug("VintageState - Getting digits (%s)." % value)
        return value

    @digits.setter
    def digits(self, value):
        self.vintage_settings['digits'] = value

    @property
    def direction(self):
        value = None
        if self.motion is not None:
            value = Direction.from_motion(self.motion)
        elif self.action is not None:
            pass

        self.log.debug("VintageState - Getting direction (%s)." % value)
        return value

    @property
    def default_selection(self):
        value = self.vintage_settings['default_selection']
        if not value:
            value = SELECTION_LINE

        self.log.debug("VintageState - Getting default_selection (%s)." % value)
        return value

    @default_selection.setter
    def default_selection(self, value):
        self.vintage_settings['default_selection'] = value

    @property
    def default_direction(self):
        value = self.vintage_settings['default_direction']
        if not value:
            value = DIRECTION_DOWN

        self.log.debug("VintageState - Getting default_selection (%s)." % value)
        return value

    @default_direction.setter
    def default_direction(self, value):
        self.vintage_settings['default_direction'] = value

    @property
    def motion(self):
        return self.vintage_settings['motion']

    @motion.setter
    def motion(self, value):
        # Encapsulates ST2 motion args
        self.vintage_settings['motion'] = value

    def mode_matches_context(self, key):
        return MODE_MAPPING[key] & self.mode == self.mode

    def select_native_move_command(self):
        cmd = 'move'
        if 'to' in self.motion:
            cmd = 'move_to'
        self.log.debug("VintageState - Selecting native motion command (%s)" % cmd)
        return cmd

    def run_motion(self):
        self.log.debug("VintageState - Running motion...")

        # Extend the selections if we're in visual mode.
        if self.mode_matches_context("vi_mode_visual_all"):
            self.log.debug("VintageState - Running as visual...")
            motion = self.motion
            motion['extend'] = True
            self.motion = motion

        # Store the repeat count in a copy
        repeat_count = self.count
        motion = self.motion
        move_cmd_name = self.select_native_move_command()

        # This is the number of times the action has actually been executed
        count = 0
        while True:
            count += 1

            if count > repeat_count:
                self.log.debug("Repeat count reached, exiting motion...")
                break

            # Store the number of selections that haven't changed because
            # of the action
            unchanged_selections = 0

            sels = self.view.sel()
            old_coords = [(r.begin(), r.end()) for r in sels]
            self.log.debug("Old selections: %s" % sels)

            self.log.debug("VintageState - About to run move command...")
            # Run the motion
            self.view.run_command(move_cmd_name, motion)

            sels = self.view.sel()
            new_coords = [(r.begin(), r.end()) for r in sels]
            self.log.debug("New selections: %s" % sels)

            # If none of the selections have changed position, end the
            # motion.
            if old_coords == new_coords:
                break

        # Reset the repeat count.
        del self.count
        self.update_status_line()


    def run(self):
        """
        * If action exists, enter visual mode.
        * Perform movement if necessary.
        * Transform selections based on action, if action exists.
        * Depending on action, exit visual mode and optionally enter insert.
        """

        self.log.debug("VintageState - Running action...")

        # All actions are basically verbs performed on selections, so we enter
        # visual mode if required.
        if self.action is not None:
            self.log.debug("VintageState - Action found... Entering visual mode...")
            self.view.run_command("vi_enter_visual_mode")

        if self.action == 'x':
            self.log.debug("VintageState - Action is 'x'. Aborting...")
            pass

        self.log.debug("VintageState - Mode before running motion was %s" % mode_to_str(self.mode))
        self.run_motion()
        self.log.debug("VintageState - Mode after running motion was %s" % mode_to_str(self.mode))

        if self.mode == MODE_VISUAL_LINE:
            self.transformer.place_cursor_at_beginning()
            self.transformer.expand_to_full_lines(include_whitespace=True)
        elif self.mode == MODE_VISUAL:
            if self.direction == DIRECTION_LEFT:
                self.transformer.expand_region_to_minimal_size_from_right()
            elif self.direction == DIRECTION_RIGHT:
                self.transformer.expand_region_to_minimal_size_from_left()

        if self.action is not None:
            fup_mode = ACTION_FOLLOWUP_MODES[self.action]
            self.log.debug("VintageState - Follow up mode is %s" % mode_to_str(fup_mode))
            self.mode = fup_mode

            if self.action == 'd':
                if self.direction == DIRECTION_RIGHT:
                    self.view.run_command('right_delete')
                elif self.direction == DIRECTION_LEFT:
                    self.view.run_command('left_delete')

        self.action = None

    @property
    def action(self):
        return self.vintage_settings['action']

    @action.setter
    def action(self, new_action):
        old_action = self.action
        if new_action is None:
            self.vintage_settings['action'] = new_action
        elif old_action is None:
            self.vintage_settings['action'] = new_action
        elif old_action != new_action:
            self.mode = MODE_NORMAL
            self.action = None
        else:
            self.run()

    @property
    def count(self):
        # XXX (dlo): memoize properties like this
        digits = self.digits
        if len(digits) == 0:
            value = 1
        else:
            value = int("".join(digits))
        self.log.debug("VintageState - Getting count (%s)" % value)

        # XXX: This is ugly. Fix it.
        # Vintage may modify the selections after the user has issued his command. This will
        # happen mainly to enter visual mode. Ensure that we don't run the motion too many
        # times in this case. This affects only motions by characters.
        if (self.motion and self.motion.get('by') == 'characters'
                        and self.motion.get('extend')):
            self.log.debug("VintageState - Decreasing motion count...")
            value -= self.count_offset

        return value

    @count.deleter
    def count(self):
        self.digits = []
        self.count_offset = 0
        self.update_status_line()

    @property
    def count_offset(self):
        return self.vintage_settings['count_offset'] or 0

    @count_offset.setter
    def count_offset(self, value):
        self.vintage_settings['count_offset'] = value

    def push_digit(self, digit):
        if self.reset_count:
            self.vintage_settings['reset_count'] = False
            self.reset_count = False
            del self.count

        digits = self.vintage_settings['digits']
        digits.append(str(digit))
        self.digits = digits
        self.update_status_line()

    @property
    def mode(self):
        mode = self.vintage_settings['mode']
        if mode is None:
            self.vintage_settings['mode'] = MODE_NORMAL
        value = mode or MODE_NORMAL
        self.log.debug("VintageState - Getting mode (%s)." % mode_to_str(value))
        return mode

    @mode.setter
    def mode(self, new_mode):
        self.vintage_settings['mode'] = new_mode
        self.log.debug("VintageState - Setting mode to '%s'." % mode_to_str(new_mode))
        if new_mode == MODE_NORMAL:
            del self.count

        inverse_caret_state = new_mode in (MODE_NORMAL, MODE_VISUAL, MODE_VISUAL_LINE)
        self.settings['inverse_caret_state'] = inverse_caret_state
        self.update_status_line()

    def update_status_line(self):
        self.log.debug("VintageState - Updating status line...")
        desc = []
        if self.mode == MODE_NORMAL:
            if self.action and not self.motion:
                desc = ["NORMAL MODE - OP PENDING"]
            else:
                desc = ["NORMAL MODE"]
        elif self.mode == MODE_VISUAL:
            desc = ["VISUAL MODE"]
        elif self.mode == MODE_VISUAL_LINE:
            desc = ["VISUAL LINE MODE"]
        elif self.mode == MODE_INSERT:
            desc = ["INSERT MODE"]
        elif self.mode == MODE_REPLACE:
            pass
        elif self.mode == MODE_EX:
            pass
        elif self.mode == MODE_SELECT:
            pass
        elif self.mode == MODE_INSERT_VISUAL:
            pass
        elif self.mode == MODE_INSERT_NORMAL:
            pass
        elif self.mode == MODE_COMMAND_LINE:
            pass
        # elif self.mode == MODE_OP_PENDING:
        #     desc = ["NORMAL MODE - OP PENDING"]

        if self.count is not None:
            desc.append(str(self.count))

        self.view.set_status('mode', ' - '.join(desc))

# Represents the current input state. The primary commands that interact with
# this are:
# * set_action
# * set_motion
# * push_repeat_digit
class Vintage(object):
    def __init__(self):
        self.prefix_repeat_digits = []
        self.action_command = None
        self.action_command_args = None
        self.action_description = None
        self.motion_repeat_digits = []
        self.motion_command = None
        self.motion_command_args = None
        self.motion_mode = MOTION_MODE_NORMAL
        self.motion_mode_overridden = False
        self.motion_inclusive = False
        self.motion_clip_to_line = False
        self.register = None
        self.states = {}
        self.mode = MODE_NORMAL

    def __getitem__(self, key):
        return self.states.setdefault(key, VintageState())

    def set_motion_mode(self, view, mode):
        self.states[view] = mode
        self.motion_mode = mode

    def reset_all(self):
        for window in sublime.windows():
            for view in window.views():
                view.settings().set('command_mode', False)
                view.settings().set('inverse_caret_state', False)
                view.erase_status('mode')

    def reset(self, view, reset_motion_mode=True):
        self.prefix_repeat_digits = []
        self.action_command = None
        self.action_command_args = None
        self.action_description = None
        self.motion_repeat_digits = []
        self.motion_command = None
        self.motion_mode_overridden = False
        self.motion_command_args = None
        self.motion_inclusive = False
        self.motion_clip_to_line = False
        self.register = None
        self.states = {}
        if reset_motion_mode:
            self.set_motion_mode(view, MOTION_MODE_NORMAL)

vintage = Vintage()

def string_to_motion_mode(mode):
    if mode == 'normal':
        return MOTION_MODE_NORMAL
    elif mode == 'line':
        return MOTION_MODE_LINE
    else:
        return -1


class ViEnterInsertMode(sublime_plugin.TextCommand):
    def is_visible(self):
        vintage_state = VintageState(self.view)
        return vintage_state.mode != MODE_INSERT

    def run(self, edit, **kwargs):
        vintage_state = VintageState(self.view)
        vintage_state.mode = MODE_INSERT
        if 'action' in kwargs:
            if 'action_args' in kwargs:
                self.view.run_command(kwargs['action'], kwargs['action_args'])
            else:
                self.view.run_command(kwargs['action'])


class ViEnterVisualMode(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        vintage_state = VintageState(self.view)

        # Only enter visual mode if not already in it.
        if not vintage_state.mode_matches_context("vi_mode_visual_all"):
            vintage_state.mode = MODE_VISUAL
            vintage_state.transformer.expand_region_to_minimal_size()


class ViEnterVisualLineMode(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        vintage_state = VintageState(self.view)
        vintage_state.mode = MODE_VISUAL_LINE
        vintage_state.transformer.expand_to_full_lines()
        vintage_state.transformer.place_cursor_at_beginning()


class ViEnterSelectMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass


class ViEnterNormalMode(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        vintage_state = VintageState(self.view)
        vintage_state.mode = MODE_NORMAL
        transform_region_set(self.view, shrink_selection_regions)


class ViEnterReplaceMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass


class ViEnterVirtualReplaceMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass

class ViEnterInsertNormalMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass

class ViEnterInsertVisualMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass

class ViEnterExMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass

class ViEnterOpPendingMode(sublime_plugin.TextCommand):
    """ Not implemented """
    pass


# Called when the plugin is unloaded (e.g., perhaps it just got added to
# ignored_packages). Ensure files aren't left in command mode.
def unload_handler():
    # FOR DEBUG ONLY ========================
    log.empty()
    print "ZZZ" * 30
    print "ZZZ" * 30
    sublime.log_commands(True)
    for w in sublime.windows():
        for v in w.views():
            v.settings().set('vintage', {})
    # =======================================
    # DON'T DELETE THE FOLLOWING -- LEGIT LINE
    vintage.reset_all()

# Ensures the input state is reset when the view changes, or the user selects
# with the mouse or non-vintage key bindings
class InputStateTracker(sublime_plugin.EventListener):
    def __init__(self):
        for w in sublime.windows():
            for v in w.views():
                if v.settings().get("vintage_start_in_command_mode"):
                    v.settings().set('command_mode', True)
                    v.settings().set('inverse_caret_state', True)

    def on_activated(self, view):
        vintage.reset(view)

    def on_deactivated(self, view):
        vintage.reset(view)

        # Ensure that insert mode actions will no longer be grouped, otherwise
        # it can lead to the impression that too much is undone at once
        view.run_command('unmark_undo_groups_for_gluing')

    def on_post_save(self, view):
        # Ensure that insert mode actions will no longer be grouped, so it's
        # always possible to undo back to the last saved state
        view.run_command('unmark_undo_groups_for_gluing')

    def on_selection_modified(self, view):
        vintage.reset(view, False)
        # Get out of visual line mode if the selection has changed, e.g., due
        # to clicking with the mouse
        if (vintage.motion_mode == MOTION_MODE_LINE and not view.has_non_empty_selection_region()):
            vintage.motion_mode = MOTION_MODE_NORMAL

    def on_load(self, view):
        if view.settings().get("vintage_start_in_command_mode"):
            view.run_command('exit_insert_mode')

    def on_new(self, view):
        self.on_load(view)

    def on_clone(self, view):
        self.on_load(view)

    def on_query_context(self, view, key, operator, operand, match_all):
        if key.startswith("vi_mode"):
            vintage_state = VintageState(view)
            return vintage_state.mode_matches_context(key)
        return False

        if key == "vi_action" and vintage.action_command:
            if operator == sublime.OP_EQUAL:
                return operand == vintage.action_command
            if operator == sublime.OP_NOT_EQUAL:
                return operand != vintage.action_command
        elif key == "vi_has_action":
            v = vintage.action_command is not None
            if operator == sublime.OP_EQUAL: return v == operand
            if operator == sublime.OP_NOT_EQUAL: return v != operand
        elif key == "vi_has_register":
            r = vintage.register is not None
            if operator == sublime.OP_EQUAL: return r == operand
            if operator == sublime.OP_NOT_EQUAL: return r != operand
        elif key == "vi_motion_mode":
            m = string_to_motion_mode(operand)
            if operator == sublime.OP_EQUAL:
                return m == vintage.motion_mode
            if operator == sublime.OP_NOT_EQUAL:
                return m != vintage.motion_mode
        elif key == "vi_has_repeat_digit":
            if vintage.action_command:
                v = len(vintage.motion_repeat_digits) > 0
            else:
                v = len(vintage.prefix_repeat_digits) > 0
            if operator == sublime.OP_EQUAL: return v == operand
            if operator == sublime.OP_NOT_EQUAL: return v != operand
        elif key == "vi_has_input_state":
            v = (len(vintage.motion_repeat_digits) > 0 or
                len(vintage.prefix_repeat_digits) > 0 or
                vintage.action_command is not None or
                vintage.register is not None)
            if operator == sublime.OP_EQUAL: return v == operand
            if operator == sublime.OP_NOT_EQUAL: return v != operand
        elif key == "vi_can_enter_text_object":
            v = (vintage.action_command is not None) or view.has_non_empty_selection_region()
            if operator == sublime.OP_EQUAL: return v == operand
            if operator == sublime.OP_NOT_EQUAL: return v != operand

        return None

# Called when vintage represents a fully formed command. Generates a
# call to vi_eval, which is what will be left on the undo/redo stack.
def eval_input(view):
    global vintage

    cmd_args = {
        'action_command': vintage.action_command,
        'action_args': vintage.action_command_args,
        'motion_command': vintage.motion_command,
        'motion_args': vintage.motion_command_args,
        'motion_mode': vintage.motion_mode,
        'motion_inclusive': vintage.motion_inclusive,
        'motion_clip_to_line': vintage.motion_clip_to_line }

    if len(vintage.prefix_repeat_digits) > 0:
        cmd_args['prefix_repeat'] = digits_to_number(vintage.prefix_repeat_digits)

    if len(vintage.motion_repeat_digits) > 0:
        cmd_args['motion_repeat'] = digits_to_number(vintage.motion_repeat_digits)

    if vintage.register is not None:
        if not cmd_args['action_args']:
            cmd_args['action_args'] = {}
        cmd_args['action_args']['register'] = vintage.register

    reset_motion_mode = (vintage.action_command is not None)

    vintage.reset(view, reset_motion_mode)

    view.run_command('vi_eval', cmd_args)

# Adds a repeat digit to the input state.
# Repeat digits may come before the action, after the action, or both. For
# example:
#   4dw
#   d4w
#   2d2w
# These commands will all delete 4 words.
class PushRepeatDigit(sublime_plugin.TextCommand):
    def run(self, edit, digit):
        global vintage
        if vintage.action_command:
            vintage.motion_repeat_digits.append(digit)
        else:
            vintage.prefix_repeat_digits.append(digit)

# Set the current action in the input state. Note that this won't create an
# entry on the undo stack: only eval_input does this.
class SetAction(sublime_plugin.TextCommand):
    # Custom version of run_, so an edit object isn't created. This allows
    # eval_input() to add the desired command to the undo stack
    def run_(self, args):
        if 'event' in args:
            del args['event']

        return self.run(**args)

    def run(self, action, action_args={}, description=None):
        global vintage
        vintage.action_command = action
        vintage.action_command_args = action_args
        vintage.action_description = description

        if self.view.has_non_empty_selection_region():
            # Currently in visual mode, so no following motion is expected:
            # eval the current input
            eval_input(self.view)

def digits_to_number(digits):
    if len(digits) == 0:
        return 1

    number = 0
    place = 1
    for d in reversed(digits):
        number += place * int(d)
        place *= 10
    return number


def parse_motion(**kwargs):
    args = {}

    if kwargs.get('to'):
        # ST move_to command
        # Some of this parameters are needed by VintageState, but ST doesn't require them
        # for this command.
        args['to'] = kwargs.get('to')
        args['forward'] = kwargs.get('forward', True)
        args['by'] = kwargs.get('by', 'characters')
        return args

    # ST move command
    args['by'] = kwargs.get('by', "characters")
    args['forward'] = kwargs.get('forward', True)
    if args['by'] == "WORDS":
        args['by'] = "stops"
        args['word_begin'] = True
        args['empty_line'] = True
        args['separators'] = ""
    elif args['by'] == "words":
        args['by'] = "stops"
        args['word_begin'] = True
        args['punct_begin'] = True
        args['empty_line'] = True
    elif args['by'] == "paragraphs":
        args['by'] = "stops"
        args['word_begin'] = False
        args['empty_line'] = True
        args['separators'] = ""

    if 'stop_at_end' in kwargs:
        if 'word_begin' in args:
            del args['word_begin']

        if 'punct_begin' in args:
            del args['punct_begin']

        args['word_end'] = True
        args['punct_end'] = True

    return args


class ViGotoLine(sublime_plugin.TextCommand):
    def run(self, action, **kwargs):
        vintage_state = VintageState(self.view)

        args = {}
        if len(vintage_state.digits) == 0:
            if vintage_state.mode_matches_context("vi_mode_visual_all"):
                args['extend'] = True

            args['to'] = "eof"
            self.view.run_command("move_to", args)
        else:
            args['line'] = vintage_state.count
            self.view.run_command("goto_line", args)
            del vintage_state.count


class ViPushDigit(sublime_plugin.TextCommand):
    def run(self, action, **kwargs):
        vintage_state = VintageState(self.view)
        vintage_state.push_digit(kwargs['digit'])
        if vintage_state.count == 0:
            print "HI"



class ViSetBeginningCursorLocation(sublime_plugin.TextCommand):
    pass

class ViSetEndingCursorLocation(sublime_plugin.TextCommand):
    pass


# Set the current motion in the input state. Note that this won't create an
# entry on the undo stack: only eval_input does this.
class SetMotion(sublime_plugin.TextCommand):
    # Custom version of run_, so an edit object isn't created. This allows
    # eval_input() to add the desired command to the undo stack
    def run_(self, args):
        return self.run(**args)

    def run(self, motion, motion_args={}, linewise=False, inclusive=False,
            clip_to_line=False, character=None, mode=None):

        global vintage

        # Pass the character, if any, onto the motion command.
        # This is required for 'f', 't', etc
        if character is not None:
            motion_args['character'] = character

        vintage.motion_command = motion
        vintage.motion_command_args = motion_args
        vintage.motion_inclusive = inclusive
        vintage.motion_clip_to_line = clip_to_line
        if not vintage.motion_mode_overridden \
                and vintage.action_command \
                and linewise:
            vintage.motion_mode = MOTION_MODE_LINE

        if mode is not None:
            m = string_to_motion_mode(mode)
            if m != -1:
                vintage.set_motion_mode(self.view, m)
            else:
                print "invalid motion mode:", mode

        eval_input(self.view)

# Run a single, combined action and motion. Examples are 'D' (delete to EOL)
# and 'C' (change to EOL).
class SetActionMotion(sublime_plugin.TextCommand):
    # Custom version of run_, so an edit object isn't created. This allows
    # eval_input() to add the desired command to the undo stack
    def run_(self, args):
        return self.run(**args)

    def run(self, motion, action, motion_args={}, motion_clip_to_line=False,
            motion_inclusive=False, motion_linewise=False, action_args={}):

        global vintage

        vintage.motion_command = motion
        vintage.motion_command_args = motion_args
        vintage.motion_inclusive = motion_inclusive
        vintage.motion_clip_to_line = motion_clip_to_line
        vintage.action_command = action
        vintage.action_command_args = action_args
        if motion_linewise:
            vintage.motion_mode = MOTION_MODE_LINE

        eval_input(self.view)

# Update the current motion mode. e.g., 'dvj'
class SetMotionMode(sublime_plugin.TextCommand):
    def run_(self, args):
        if 'event' in args:
            del args['event']

        return self.run(**args)

    def run(self, mode):
        global vintage
        m = string_to_motion_mode(mode)

        if m != -1:
            vintage.set_motion_mode(self.view, m)
            vintage.motion_mode_overridden = True
        else:
            print "invalid motion mode"

class SetRegister(sublime_plugin.TextCommand):
    def run_(self, args):
        return self.run(**args)

    def run(self, character):
        vintage.register = character

def clip_point_to_line(view, f, pt):
    l = view.line(pt)
    if l.a == l.b:
        return l.a

    new_pt = f(pt)
    if new_pt < l.a:
        return l.a
    elif new_pt >= l.b:
        return l.b
    else:
        return new_pt

def transform_selection(view, transformer, extend=False, clip_to_line=False):
    new_region_set = []
    region_set = view.sel()
    size = view.size()

    for r in region_set:
        if clip_to_line:
            new_pt = clip_point_to_line(view, transformer, r.b)
        else:
            new_pt = transformer(r.b)

        if new_pt < 0: new_pt = 0
        elif new_pt > size: new_pt = size

        if extend:
            new_region_set.append(sublime.Region(r.a, new_pt))
        else:
            new_region_set.append(sublime.Region(new_pt))

    region_set.clear()
    for region in new_region_set:
        region_set.add(r)

def transform_region_set(view, transformer):
    new_region_set = []
    region_set = view.sel()

    for region in region_set:
        new_region = transformer(region)
        if new_region is not None:
            new_region_set.append(new_region)

    region_set.clear()
    for region in new_region_set:
        region_set.add(region)

def expand_to_full_line(view, ignore_trailing_newline=True):
    new_sel = []
    for selection in view.sel():
        if selection.a == selection.b:
            new_sel.append(view.full_line(selection.a))
        else:
            la = view.full_line(selection.begin())
            lb = view.full_line(selection.end())

            a = la.a

            if ignore_trailing_newline and selection.end() == lb.a:
                # selection.end() is already at EOL, don't go down to the next line
                b = selection.end()
            else:
                b = lb.b

            if selection.a < selection.b:
                new_sel.append(sublime.Region(a, b, 0))
            else:
                new_sel.append(sublime.Region(b, a, 0))

    view.sel().clear()
    for selection in new_sel:
        view.sel().add(selection)

def orient_single_line_region(view, forward, r):
    l = view.full_line(r.begin())
    if l.a == r.begin() and l.end() == r.end():
        if forward:
            return l
        else:
            return sublime.Region(l.b, l.a)
    else:
        return r

def set_single_line_selection_direction(view, forward):
    transform_region_set(view,
        lambda r: orient_single_line_region(view, forward, r))

def orient_single_character_region(view, forward, r):
    if r.begin() + 1 == r.end():
        if forward:
            return sublime.Region(r.begin(), r.end())
        else:
            return sublime.Region(r.end(), r.begin())
    else:
        return r

def set_single_character_selection_direction(view, forward):
    transform_region_set(view,
        lambda r: orient_single_character_region(view, forward, r))

def clip_empty_selection_to_line_contents(view):
    new_sel = []
    for s in view.sel():
        if s.empty():
            l = view.line(s.b)
            if s.b == l.b and not l.empty():
                s = sublime.Region(l.b - 1, l.b - 1, s.xpos())

        new_sel.append(s)

    view.sel().clear()
    for s in new_sel:
        view.sel().add(s)

def shrink_inclusive(r):
    if r.a < r.b:
        return sublime.Region(r.b - 1, r.b - 1, r.xpos())
    else:
        return sublime.Region(r.b, r.b, r.xpos())

def shrink_exclusive(r):
    return sublime.Region(r.b, r.b, r.xpos())

def shrink_to_first_char(r):
    if r.b < r.a:
        # If the Region is reversed, the first char is the character *before*
        # the first bound.
        return sublime.Region(r.a - 1)
    else:
        return sublime.Region(r.a)

# This is the core: it takes a motion command, action command, and repeat
# counts, and runs them all.
#
# Note that this doesn't touch vintage, and doesn't maintain any state
# other than what's passed on its arguments. This allows it to operate correctly
# in macros, and when running via repeat.
class ViEval(sublime_plugin.TextCommand):
    def run_(self, args):
        was_visual = self.view.has_non_empty_selection_region()

        edit = self.view.begin_edit(self.name(), args)
        try:
            self.run(edit, **args)
        except:
            # TODO: Need to specify exception
            pass
        finally:
            self.view.end_edit(edit)

        # Glue the marked undo groups if visual mode was exited (e.g., by
        # running an action while in visual mode). This ensures that
        # v+motions+action can be repeated as a single unit.
        if self.view.settings().get('command_mode') == True:
            is_visual = self.view.has_non_empty_selection_region()
            if was_visual and not is_visual:
                self.view.run_command('glue_marked_undo_groups')
            elif not is_visual:
                self.view.run_command('unmark_undo_groups_for_gluing')

    def run(self, edit, action_command, action_args,
            motion_command, motion_args, motion_mode,
            motion_inclusive, motion_clip_to_line,
            prefix_repeat=None, motion_repeat=None):

        explicit_repeat = (prefix_repeat is not None or motion_repeat is not None)

        if prefix_repeat is None:
            prefix_repeat = 1
        if motion_repeat is None:
            motion_repeat = 1

        # Arguments are always passed as floats (thanks to JSON encoding),
        # convert them back to integers
        prefix_repeat = int(prefix_repeat)
        motion_repeat = int(motion_repeat)
        motion_mode = int(motion_mode)

        # Combine the prefix_repeat and motion_repeat into motion_repeat, to
        # allow commands like 2yy to work by first doing the motion twice,
        # then operating once
        if motion_command and prefix_repeat > 1:
            motion_repeat *= prefix_repeat
            prefix_repeat = 1

        # Check if the motion command would like to handle the repeat itself
        if motion_args and 'repeat' in motion_args:
            motion_args['repeat'] = motion_repeat * prefix_repeat
            motion_repeat = 1
            prefix_repeat = 1

        # Some commands behave differently if a repeat is given. e.g., 1G goes
        # to line one, but G without a repeat goes to EOF. Let the command
        # know if a repeat was specified.
        if motion_args and 'explicit_repeat' in motion_args:
            motion_args['explicit_repeat'] = explicit_repeat

        visual_mode = self.view.has_non_empty_selection_region()

        # Let the motion know if we're in visual mode, if it wants to know
        if motion_args and 'visual' in motion_args:
            motion_args['visual'] = visual_mode

        for i in xrange(prefix_repeat):
            # Run the motion command, extending the selection to the range of
            # characters covered by the motion
            if motion_command:
                direction = 0
                if motion_args and 'forward' in motion_args:
                    forward = motion_args['forward']
                    if forward:
                        direction = 1
                    else:
                        direction = -1

                for j in xrange(motion_repeat):
                    if direction != 0 and motion_mode == MOTION_MODE_LINE:
                        # Ensure selections encompassing a single line are
                        # oriented in the same way as the motion, so they'll
                        # remain selected. This is needed so that Vk will work
                        # as expected
                        set_single_line_selection_direction(self.view, direction == 1)
                    elif direction != 0:
                        set_single_character_selection_direction(self.view, direction == 1)

                    if motion_mode == MOTION_MODE_LINE:
                        # Don't do either of the below things: this is
                        # important so that Vk on an empty line would select
                        # the following line.
                        pass
                    elif direction == 1 and motion_inclusive:
                        # Expand empty selections include the character
                        # they're on, and to start from the RHS of the
                        # character
                        transform_region_set(self.view,
                            lambda r: sublime.Region(r.b, r.b + 1, r.xpos()) if r.empty() else r)

                    self.view.run_command(motion_command, motion_args)

            # If the motion needs to be clipped to the line, remove any
            # trailing newlines from the selection. For example, with the
            # caret at the start of the last word on the line, 'dw' should
            # delete the word, but not the newline, while 'w' should advance
            # the caret to the first character of the next line.
            if motion_mode != MOTION_MODE_LINE and action_command and motion_clip_to_line:
                transform_region_set(self.view, lambda r: self.view.split_by_newlines(r)[0])

            reindent = False

            if motion_mode == MOTION_MODE_LINE:
                expand_to_full_line(self.view, visual_mode)
                if action_command == "enter_insert_mode":
                    # When lines are deleted before entering insert mode, the
                    # cursor should be left on an empty line. Leave the trailing
                    # newline out of the selection to allow for this.
                    transform_region_set(self.view,
                        lambda r: (sublime.Region(r.begin(), r.end() - 1)
                                   if not r.empty() and self.view.substr(r.end() - 1) == "\n"
                                   else r))
                    reindent = True

            if action_command:
                # Apply the action to the selection
                self.view.run_command(action_command, action_args)
                if reindent and self.view.settings().get('auto_indent'):
                    self.view.run_command('reindent', {'force_indent': False})

        if not visual_mode:
            # Shrink the selection down to a point
            if motion_inclusive:
                transform_region_set(self.view, shrink_inclusive)
            else:
                transform_region_set(self.view, shrink_exclusive)

        # Clip the selections to the line contents
        if self.view.settings().get('command_mode'):
            clip_empty_selection_to_line_contents(self.view)

        # Ensure the selection is visible
        self.view.show(self.view.sel())



class EnterVisualLineMode(sublime_plugin.TextCommand):
    def run(self, edit):
        vintage.set_motion_mode(self.view, MOTION_MODE_LINE)
        expand_to_full_line(self.view)


def shrink_selection_regions(r):
    if r.empty():
        return r
    elif r.a < r.b:
        return sublime.Region(r.b - 1)
    else:
        return sublime.Region(r.b)


class ShrinkSelectionsToBeginning(sublime_plugin.TextCommand):
    def shrink(self, r):
        return sublime.Region(r.begin())

    def run(self, edit, register='"'):
        transform_region_set(self.view, self.shrink)


class ShrinkSelectionsToEnd(sublime_plugin.TextCommand):
    def shrink(self, r):
        end = r.end()
        if self.view.substr(end - 1) == u'\n':
            # For linewise selections put the cursor *before* the line break
            return sublime.Region(end - 1)
        else:
            return sublime.Region(end)

    def run(self, edit, register='"'):
        transform_region_set(self.view, self.shrink)


class ViUpperCase(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("upper_case")
        vintage_state = VintageState(self.view)
        vintage_state.mode = MODE_NORMAL


class ViLowerCase(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command("lower_case")
        vintage_state = VintageState(self.view)
        vintage_state.mode = MODE_NORMAL


class ViCompound(sublime_plugin.TextCommand):
    def run(self, edit, commands):
        for command in commands:
            self.view.run_command(command)

        vintage_state = VintageState(self.view)
        vintage_state.run()


class ViD(sublime_plugin.TextCommand):
    def run(self, edit):
        log.debug("Running ViD...")
        vintage_state = VintageState(self.view)
        vintage_state.action = 'd'


class ViX(sublime_plugin.TextCommand):
    def run(self, edit):
        vintage_state = VintageState(self.view)
        vintage_state.action = 'x'



class ViMove(sublime_plugin.TextCommand):
    def run(self, edit, **kwargs):
        vintage_state = VintageState(self.view)
        vintage_state.motion = parse_motion(**kwargs)
        vintage_state.run()


class ViUndo(sublime_plugin.TextCommand):
    """ XXX: Figure out why this doesn't work """
    def run(self, edit):
        self.view.run_command("undo")
        self.view.run_command("vi_enter_normal_mode")


class ViC(sublime_plugin.TextCommand):
    def run(self, edit):
        vintage_state = VintageState(self.view)
        vintage_state.action = 'c'


class ViSetAction(sublime_plugin.TextCommand):
    def run(self, edit, action):
        vintage_state = VintageState(self.view)
        vintage_state.action = action
        vintage_state.run()


class ViDelete(sublime_plugin.TextCommand):
    def run(self, edit, right=False, direction="right", followup_mode="normal"):
        vintage_state = VintageState(self.view)
        vintage_state.action = 'd'

        # TODO: move to Vintage State object
        if direction == "right":
            self.view.run_command('right_delete')
        else:
            self.view.run_command('left_delete')

        if followup_mode == "normal":
            vintage_state.mode = MODE_NORMAL
        elif followup_mode == "visual":
            vintage_state.mode = MODE_VISUAL


class ViCopy(sublime_plugin.TextCommand):
    def run(self, edit, register='"'):
        set_register(self.view, register, forward=True)
        set_register(self.view, '0', forward=True)
        transform_region_set(self.view, shrink_to_first_char)


class ViPrefixableCommand(sublime_plugin.TextCommand):
    # Ensure register and repeat are picked up from vintage, and that
    # it'll be recorded on the undo stack
    def run_(self, args):
        if not args:
            args = {}

        if vintage.register:
            args['register'] = vintage.register
            vintage.register = None

        if vintage.prefix_repeat_digits:
            args['repeat'] = digits_to_number(vintage.prefix_repeat_digits)
            vintage.prefix_repeat_digits = []

        if 'event' in args:
            del args['event']

        edit = self.view.begin_edit(self.name(), args)
        try:
            return self.run(edit, **args)
        finally:
            self.view.end_edit(edit)


class ViPasteRight(ViPrefixableCommand):
    def advance(self, pt):
        if self.view.substr(pt) == '\n' or pt >= self.view.size():
            return pt
        else:
            return pt + 1

    def run(self, edit, register='"', repeat=1):
        visual_mode = self.view.has_non_empty_selection_region()
        if not visual_mode:
            transform_selection(self.view, lambda pt: self.advance(pt))
        self.view.run_command('paste_from_register', {'forward': not visual_mode,
                                                      'repeat': repeat,
                                                      'register': register})

class ViPasteLeft(ViPrefixableCommand):
    def run(self, edit, register='"', repeat=1):
        self.view.run_command('paste_from_register', {'forward': False,
                                                      'repeat': repeat,
                                                      'register': register})

def has_register(register):
    if register in ['%', '*', '+']:
        return True
    else:
        return register in g_registers

class PasteFromRegisterCommand(sublime_plugin.TextCommand):
    def run(self, edit, register, repeat=1, forward=True):
        text = get_register(self.view, register)
        if not text:
            sublime.status_message("Undefined register" + register)
            return
        text = text * int(repeat)

        self.view.run_command('vi_delete')

        regions = [r for r in self.view.sel()]
        new_sel = []

        offset = 0

        for s in regions:
            s = sublime.Region(s.a + offset, s.b + offset)

            if len(text) > 0 and text[-1] == '\n':
                # paste line-wise
                if forward:
                    start = self.view.full_line(s.end()).b
                else:
                    start = self.view.line(s.begin()).a

                num = self.view.insert(edit, start, text)
                new_sel.append(start)
            else:
                # paste character-wise
                num = self.view.insert(edit, s.begin(), text)
                self.view.erase(edit, sublime.Region(s.begin() + num,
                    s.end() + num))
                num -= s.size()
                new_sel.append(s.begin())

            offset += num

        self.view.sel().clear()
        for s in new_sel:
            self.view.sel().add(s)

    def is_enabled(self, register, repeat=1, forward=True):
        return has_register(register)

class ReplaceCharacter(sublime_plugin.TextCommand):
    def run(self, edit, character):
        new_sel = []
        created_new_line = False
        for s in reversed(self.view.sel()):
            if s.empty():
                self.view.replace(edit, sublime.Region(s.b, s.b + 1), character)
                if character == "\n":
                    created_new_line = True
                    # selection should be in the first column of the newly
                    # created line
                    new_sel.append(sublime.Region(s.b + 1))
                else:
                    new_sel.append(s)
            else:
                # Vim replaces characters with unprintable ones when r<enter> is
                # pressed from visual mode.  Let's not make a replacement in
                # that case.
                if character != '\n':
                    # Process lines contained in the selection individually.
                    # This way we preserve newline characters.
                    lines = self.view.split_by_newlines(s)
                    for line in lines:
                        self.view.replace(edit, line, character * line.size())
                new_sel.append(sublime.Region(s.begin()))

        self.view.sel().clear()
        for s in new_sel:
            self.view.sel().add(s)

        if created_new_line and self.view.settings().get('auto_indent'):
            self.view.run_command('reindent', {'force_indent': False})

class CenterOnCursor(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.show_at_center(self.view.sel()[0])

class ScrollCursorLineToTop(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.set_viewport_position((self.view.viewport_position()[0], self.view.layout_extent()[1]))
        self.view.show(self.view.sel()[0], False)

class ScrollCursorLineToBottom(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.set_viewport_position((self.view.viewport_position()[0], 0.0))
        self.view.show(self.view.sel()[0], False)

class ViScrollLines(ViPrefixableCommand):
    def run(self, edit, forward=True, repeat=None):
        if repeat:
            line_delta = repeat * (1 if forward else -1)
        else:
            viewport_height = self.view.viewport_extent()[1]
            lines_per_page = viewport_height / self.view.line_height()
            line_delta = int(round(lines_per_page / (2 if forward else -2)))
        visual_mode = self.view.has_non_empty_selection_region()

        y_deltas = []
        def transform(pt):
            row = self.view.rowcol(pt)[0]
            new_pt = self.view.text_point(row + line_delta, 0)
            y_deltas.append(self.view.text_to_layout(new_pt)[1]
                            - self.view.text_to_layout(pt)[1])
            return new_pt

        transform_selection(self.view, transform, extend=visual_mode)

        self.view.run_command('vi_move_to_first_non_white_space_character',
                              {'extend': visual_mode})

        # Vim scrolls the viewport as far as it moves the cursor.  With multiple
        # selections the cursors could have moved different distances, due to
        # word wrapping.  Move the viewport by the average of those distances.
        avg_y_delta = sum(y_deltas) / len(y_deltas)
        vp = self.view.viewport_position()
        self.view.set_viewport_position((vp[0], vp[1] + avg_y_delta))


class ViIndent(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command('indent')
        transform_region_set(self.view, shrink_to_first_char)

class ViUnindent(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command('unindent')
        transform_region_set(self.view, shrink_to_first_char)

class ViSetBookmark(sublime_plugin.TextCommand):
    def run(self, edit, character):
        sublime.status_message("Set bookmark " + character)
        self.view.add_regions("bookmark_" + character, [s for s in self.view.sel()],
            "", "", sublime.PERSISTENT | sublime.HIDDEN)

class ViSelectBookmark(sublime_plugin.TextCommand):
    def run(self, edit, character, select_bol=False):
        self.view.run_command('select_all_bookmarks', {'name': "bookmark_" + character})
        if select_bol:
            sels = list(self.view.sel())
            self.view.sel().clear()
            for r in sels:
                start = self.view.line(r.a).begin()
                self.view.sel().add(sublime.Region(start, start))

g_macro_target = None

class ViBeginRecordMacro(sublime_plugin.TextCommand):
    def run(self, edit, character):
        global g_macro_target
        g_macro_target = character
        self.view.run_command('start_record_macro')

class ViEndRecordMacro(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command('stop_record_macro')
        if not g_macro_target:
            return

        m = sublime.get_macro()
        # TODO: Convert the macro to a string before trying to store it in a
        # register
        g_registers[g_macro_target] = m

class ViReplayMacro(sublime_plugin.TextCommand):
    def run(self, edit, character):
        if not character in g_registers:
            return
        m = g_registers[character]
        global vintage

        prefix_repeat_digits, motion_repeat_digits=None, None
        if len(vintage.prefix_repeat_digits) > 0:
            prefix_repeat_digits = digits_to_number(vintage.prefix_repeat_digits)

        if len(vintage.motion_repeat_digits) > 0:
            motion_repeat_digits = digits_to_number(vintage.motion_repeat_digits)

        repetitions = 1
        if prefix_repeat_digits:
            repetitions *= prefix_repeat_digits

        if motion_repeat_digits:
            repetitions *= motion_repeat_digits

        for i in range(repetitions):
            for d in m:
                cmd = d['command']
                args = d['args']
                self.view.run_command(cmd, args)

class ShowAsciiInfo(sublime_plugin.TextCommand):
    def run(self, edit):
        c = self.view.substr(self.view.sel()[0].end())
        sublime.status_message("<%s> %d, Hex %s, Octal %s" %
                        (c, ord(c), hex(ord(c))[2:], oct(ord(c))))

class ViReverseSelectionsDirection(sublime_plugin.TextCommand):
    def run(self, edit):
        new_sels = []
        for s in self.view.sel():
            new_sels.append(sublime.Region(s.b, s.a))
        self.view.sel().clear()
        for s in new_sels:
            self.view.sel().add(s)

class MoveGroupFocus(sublime_plugin.WindowCommand):
    def run(self, direction):
        cells = self.window.get_layout()['cells']
        active_group = self.window.active_group()
        x1, y1, x2, y2 = cells[active_group]

        idxs = range(len(cells))
        del idxs[active_group]

        # Matches are any group that shares a border with the active group in the
        # specified direction.
        if direction == "up":
            matches = (i for i in idxs if cells[i][3] == y1 and cells[i][0] < x2 and cells[i][2] > x1)
        elif direction == "down":
            matches = (i for i in idxs if cells[i][1] == y2 and cells[i][0] < x2 and cells[i][2] > x1)
        elif direction == "right":
            matches = (i for i in idxs if cells[i][0] == x2 and cells[i][1] < y2 and cells[i][3] > y1)
        elif direction == "left":
            matches = (i for i in idxs if cells[i][2] == x1 and cells[i][1] < y2 and cells[i][3] > y1)

        # Focus the first group found in the specified direction, if there is one.
        try:
            self.window.focus_group(matches.next())
        except StopIteration:
            return

class Test(sublime_plugin.TextCommand):
    def run(self, edit):
        state = VintageState(self.view)
        state.transformer.expand_region_to_first_non_whitespace_character()

