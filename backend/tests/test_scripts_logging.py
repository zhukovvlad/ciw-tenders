from __future__ import annotations

import app.scripts.create_admin as ca
import app.scripts.smoke_import as si


def test_create_admin_uses_logger_not_print() -> None:
    src = ca.__loader__.get_source(ca.__name__)
    assert "print(" not in src  # статусные строки переведены на logger
    assert "logger" in src


def test_smoke_import_keeps_print_report() -> None:
    src = si.__loader__.get_source(si.__name__)
    assert "print(report)" in src  # фактический вывод скрипта остаётся print
    assert "setup_logging" in src  # но логирование инициализируется
