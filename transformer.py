import sublime

def iterate_over_regions(fun):
    def inner(self, *args, **kwargs):
        transformer = fun(self, *args, **kwargs)
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


class Transformer(object):
    def __init__(self, view=None, settings=None):
        self.view = view
        self.settings = settings

    def __get__(self, instance, owner):
        if instance is not None:
            return Transformer(instance.view, instance.settings)
        return Transformer()

    @iterate_over_regions
    def move_cursor_to_first_non_whitespace_character(self):
        def transformer(region):
            self.place_cursor_at_beginning()(region)

            first_line_region = self.view.line(region.a)
            first_line_string = self.view.substr(first_point_in_expanded_region)
            offset = 0

            for character in string_containing_first_point:
                if c == ' ' or c == '\t':
                    offset += 1
                else:
                    break

            return first_line_region.a + offset
        return transformer

    @iterate_over_regions
    def place_cursor_at_beginning(self):
        def transformer(region):
            if region.b < region.a:
                return sublime.Region(region.a, region.b)
            else:
                return sublime.Region(region.b, region.a)
        return transformer

    @iterate_over_regions
    def place_cursor_at_end(self):
        def transformer(region):
            if region.b > region.a:
                return sublime.Region(region.a, region.b)
            else:
                return sublime.Region(region.b, region.a)
        return transformer

    @iterate_over_regions
    def expand_to_full_lines(self, include_whitespace=False):
        def transformer(region):
            if include_whitespace:
                line_fun = self.view.full_line
            else:
                line_fun = self.view.line

            return line_fun(region)
        return transformer
