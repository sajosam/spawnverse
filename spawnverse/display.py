# spawnverse/display.py
from datetime import datetime

C = {
    "M": "\033[95m", "B": "\033[94m", "G": "\033[92m",
    "Y": "\033[93m", "C": "\033[96m", "R": "\033[91m",
    "W": "\033[37m", "X": "\033[90m", "P": "\033[35m",
}
RST  = "\033[0m"
BOLD = "\033[1m"


def _log(sender: str, receiver: str, kind: str, msg: str, c: str = "M") -> None:
    ts     = datetime.now().strftime("%H:%M:%S")
    color  = C.get(c, C["M"])
    first  = str(msg).splitlines()[0][:120] if msg else ""
    extras = f"  …+{len(str(msg).splitlines())-1} lines" if len(str(msg).splitlines()) > 1 else ""
    print(f"{color}[{ts}] {sender:<6} → {receiver:<30} {kind:<18} {first}{extras}{RST}")
