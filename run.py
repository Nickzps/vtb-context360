"""Запуск без установки пакета: python run.py [--transfers 100000] [--json]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from context360.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
