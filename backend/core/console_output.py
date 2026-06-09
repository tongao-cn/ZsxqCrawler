from __future__ import annotations

import builtins
import sys
from typing import Any


def safe_console_print(*values: Any, **kwargs: Any) -> None:
    try:
        builtins.print(*values, **kwargs)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_values = [
            str(value).encode(encoding, errors="replace").decode(encoding)
            for value in values
        ]
        builtins.print(*safe_values, **kwargs)
