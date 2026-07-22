import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAAS = ROOT / "saas"
if str(SAAS) not in sys.path:
    sys.path.insert(0, str(SAAS))
