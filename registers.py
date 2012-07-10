import sublime
import os

# todo(guillermo): some operations will require a view. fix that.
class Registers(dict):
    """
    Registers hold global data mainly used by yank, delete and paste.
    Create only one instance of this class.
    """
    REG_DEFAULT = '"'
    REG_SMALL_DELETE = '-'
    REG_NULL = '_'
    REG_LAST_INSERTED_TEXT = '.'
    REG_FILE_NAME = '%'
    REG_ALT_FILE_NAME = '#'
    # todo(guillermo): implement vintage_use_sys_clipboard option to always
    # propagate registers to the system clipboard.
    REG_SYS_CLIPBOARD = '*'
    REG_ALL = (REG_DEFAULT, REG_SMALL_DELETE, REG_NULL, REG_LAST_INSERTED_TEXT,
               REG_FILE_NAME, REG_ALT_FILE_NAME, REG_SYS_CLIPBOARD)
    # todo(guillermo): there are more

    def _set_default_register(self, value):
        # todo(guillermo): could be made a decorator.
        self.__dict__[Registers.REG_DEFAULT] = value

    def set(self, name, value):
        """
        Sets an a-z or 0-9 register.
        """
        assert len(name) == 1, "Register names must be 1 char long."

        if name == Registers.REG_NULL:
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

    def append_to(self, name, value):
        """
        Appends to an a-z register. `name` must be a capital in A-Z.
        """
        assert len(name) == 1, "Register names must be 1 char long."
        assert ord(name) in xrange(ord('A'), ord('Z') + 1), "Can only append to A-Z registers."

        existing = self.__dict__.get(name.lower(), '')
        self.__dict__[name.lower()] = existing + value
        self._set_default_register(self[name.lower()])

    def get(self, name):
        assert len(name) == 1, "Register names must be 1 char long."

        # Did we request a special register?
        if name == Registers.REG_NULL:
            return
        elif name == Registers.REG_FILE_NAME:
            try:
                # todo(guillermo): there must be a better way of doing this.
                v = sublime.active_window().active_view().file_name()
                return os.path.basename(v)
            except AttributeError:
                return ''
        elif name == Registers.REG_SYS_CLIPBOARD:
            return sublime.get_clipboard()
        elif name != Registers.REG_DEFAULT and name in Registers.REG_ALL:
            return None

        # We requestested an a-z register.
        # In Vim, "A and "a seem to be synonyms.
        try:
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
        except AttributeError:
            self.set(key, value)
        else:
            self.set(key, value)
