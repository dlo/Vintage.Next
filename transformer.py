import sublime

def region_transformer(fun):
    def inner(self, iterate=True, *args, **kwargs):
        transformer = fun(self, *args, **kwargs)

        if not iterate:
            return transformer

        new_region_set = []
        region_set = self.view.sel()

        for region in region_set:
            new_region = transformer(region)
            if new_region is not None:
                new_region_set.append(new_region)

        region_set.clear()
        for region in new_region_set:
            region_set.add(region)

    return inner

sublime.Region.is_reversed = lambda self: self.b < self.a

class Transformer(object):
    def __init__(self, view=None, settings=None):
        self.view = view
        self.settings = settings

    def __get__(self, instance, owner):
        if instance is not None:
            return Transformer(instance.view, instance.settings)
        return Transformer()

    def get_position_of_first_non_whitespace_character(self, pos):
        first_line_region = self.view.line(pos)
        first_line_string = self.view.substr(first_line_region)
        offset = 0

        for character in first_line_string:
            # TODO: Find what other characters also count as whitespace, if
            # any.
            if character in (' ', '\t'):
                offset += 1
            else:
                break

        return first_line_region.a + offset

    def get_position_of_first_character(self, pos):
        row, col = self.view.rowcol(pos)
        return pos - col

    @region_transformer
    def expand_region_to_minimal_size(self, iterate=True):
        def transformer(region):
            if region.empty():
                return sublime.Region(region.b, region.b+1)
            return region
        return transformer

    @region_transformer
    def expand_region_to_minimal_size_from_left(self, iterate=True):
        def transformer(region):
            if region.empty():
                fun = self.place_cursor_at_end(iterate=False)
                return fun(sublime.Region(region.b-1, region.b+1))
            return region
        return transformer

    @region_transformer
    def expand_region_to_minimal_size_from_right(self, iterate=True):
        def transformer(region):
            if region.empty():
                fun = self.place_cursor_at_beginning(iterate=False)
                return fun(sublime.Region(region.a+1, region.a-1))
            return region
        return transformer

    @region_transformer
    def expand_region_to_first_non_whitespace_character(self, iterate=True):
        def transformer(region):
            new_beginning = self.get_position_of_first_non_whitespace_character(region.begin())
            return sublime.Region(region.a, new_beginning)
        return transformer

    @region_transformer
    def expand_region_to_first_character(self, iterate=True):
        def transformer(region):
            if region.b == region.begin():
                new_beginning = self.get_position_of_first_character(region.begin())
                return sublime.Region(region.a, new_beginning)
            return region
        return transformer

    @region_transformer
    def place_cursor_at_beginning(self, iterate=True):
        def transformer(region):
            if region.is_reversed():
                return sublime.Region(region.a, region.b)
            else:
                return region
        return transformer

    @region_transformer
    def place_cursor_at_end(self, iterate=True):
        def transformer(region):
            if not region.is_reversed():
                return region
            else:
                return sublime.Region(region.b, region.a)
        return transformer

    @region_transformer
    def expand_to_full_lines(self, iterate=True, include_whitespace=False):
        def transformer(region):
            if include_whitespace:
                # full_line includes trailing newline characters, if they exist
                line_fun = self.view.full_line
            else:
                line_fun = self.view.line

            region = self.place_cursor_at_beginning(iterate=False)(region)
            return line_fun(region)
        return transformer

