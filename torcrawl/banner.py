"""
TORCrawl banner module.

The banner is a hand-tuned ASCII totem of an arachnid (the "crawler")
woven from the tor onion geometry. It uses a fixed-width font and
chained block characters so it renders identically across terminals.
"""

from __future__ import annotations

import sys


# 64 cols, 11 rows. Pure ASCII; no Unicode box-drawing.
BANNER = r"""
        .   .        .          .          .        .   .
          \  |  /        \    |    /        \  |  /
       .---\ | /---.   .---\   |   /---.   .---\ | /---.
        ====>@<====    ====>@<====    ====>@<====
       '---/ | \---'   '---/ | \---'   '---/ | \---'
          /  |  \        /    |    \        /  |  \
        '   '        '          '        '   '

     T O R C R A W L  ·  E t e r n a l  ·  V i g i l a n c e
       v2.0   persistent   stateful   adaptive
"""


def print_banner(stream=sys.stdout) -> None:
    """Write the banner to the given stream, colour-free, with a trailing newline.

    Stays readable on 80-col terminals and on 132-col terminals. The banner
    is intentionally NOT styled with ANSI colour so it survives a `tee` to
    a log file without leaking escape codes.
    """
    stream.write(BANNER)
    stream.write("\n")
    stream.flush()
