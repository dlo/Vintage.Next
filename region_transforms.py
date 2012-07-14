import sublime

def place_cursor_at_beginning(region):
    if region.b < region.a:
        return sublime.Region(region.a, region.b)
    else:
        return sublime.Region(region.b, region.a)

def place_cursor_at_end(region):
    if region.b > region.a:
        return sublime.Region(region.a, region.b)
    else:
        return sublime.Region(region.b, region.a)

def expand_to_full_lines(region, include_whitespace=False):
    if include_whitespace:
        fun = 
    pass

