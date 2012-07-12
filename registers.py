import sublime
import os


REG_DEFAULT = '"'
REG_SMALL_DELETE = '-'
REG_NULL = '_'
REG_LAST_INSERTED_TEXT = '.'
REG_FILE_NAME = '%'
REG_ALT_FILE_NAME = '#'
REG_SYS_CLIPBOARD_1 = '*'
REG_SYS_CLIPBOARD_2 = '+'
REG_SYS_CLIPBOARD_ALL = (REG_SYS_CLIPBOARD_1, REG_SYS_CLIPBOARD_2)
REG_ALL = (REG_DEFAULT, REG_SMALL_DELETE, REG_NULL, REG_LAST_INSERTED_TEXT,
           REG_FILE_NAME, REG_ALT_FILE_NAME, REG_SYS_CLIPBOARD_1,
           REG_SYS_CLIPBOARD_2)
# todo(guillermo): there are more


class Registers(dict):
    """
    Registers hold global data mainly used by yank, delete and paste.

    This class is meant to be used a descriptor.

        class VintageState(object):
            ...
            self.registers = Registers()

        vstate = VintageState()
        vstate.registers["%"] # now vstate has access to the current view.
    """


    def __init__(self, view, settings):
        self.view = view
        self.settings = settings

    def __get__(self, obj, type):
        # This ensures that we can easiy access the active view.
        return Registers(obj.view, obj.settings)

    def _set_default_register(self, value):
        # todo(guillermo): could be made a decorator.
        self.__dict__[REG_DEFAULT] = value

    def _maybe_set_sys_clipboard(self, value):
        # We actually need to check whether the option is set to a bool; could
        # be any JSON type.
        if self.settings.vintage_use_sys_clipboard == True:
            sublime.set_clipboard(value)

    def set(self, name, value):
        """
        Sets an a-z or 0-9 register.
        """
        assert len(str(name)) == 1, "Register names must be 1 char long."

        if name == REG_NULL:
            return

        if isinstance(name, int):
            name = unicode(name)
        # Special registers and invalid registers won't be set.
        if (not (name.isalpha() or name.isdigit())) or name.isupper():
            # Vim fails silently.
            # raise Exception("Can only set a-z and 0-9 registers.")
            return None
        self.__dict__[name] = value
        self._set_default_register(value)
        self._maybe_set_sys_clipboard(value)

    def append_to(self, name, value):
        """
        Appends to an a-z register. `name` must be a capital in A-Z.
        """
        assert len(name) == 1, "Register names must be 1 char long."
        assert ord(name) in xrange(ord('A'), ord('Z') + 1), "Can only append to A-Z registers."

        existing = self.__dict__.get(name.lower(), '')
        new_value = existing + value
        self.__dict__[name.lower()] = new_value
        self._set_default_register(new_value)
        self._maybe_set_sys_clipboard(new_value)

    def get(self, name=REG_DEFAULT):
        assert len(str(name)) == 1, "Register names must be 1 char long."

        # Did we request a special register?
        if name == REG_NULL:
            return
        elif name == REG_FILE_NAME:
            try:
                return os.path.basename(self.view.file_name())
            except AttributeError:
                return ''
        elif name in REG_SYS_CLIPBOARD_ALL:
            return sublime.get_clipboard()
        elif name != REG_DEFAULT and name in REG_ALL:
            return
        # Special case lumped among these --user always wants the sys
        # clipboard.
        elif self.settings.vintage_use_sys_clipboard == True:
            return sublime.get_clipboard()

        # We requested an [a-z0-9"] register.
        if isinstance(name, int):
            name = unicode(name)
        try:
            # In Vim, "A and "a seem to be synonyms, so accept either.
            return self.__dict__[name.lower()]
        except KeyError:
            # sublime.status_message("Vintage.Next: E353 Nothing in register %s", name)
            pass

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        try:
            if key.isupper():
                self.append_to(key, value)
            else:
                self.set(key, value)
        except AttributeError:
            self.set(key, value)
