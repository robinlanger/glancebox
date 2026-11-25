"""3D printer page (printer): state, progress and times of one printer, selected with `source:`.

Only the hook load_page_types needs so far; the page logic follows.
"""


def fetch(options, ctx):
    raise NotImplementedError
