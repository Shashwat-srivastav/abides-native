"""Build-time rewrite: guard every `logger.debug(...)` statement with `if logger.isEnabledFor(10): `.

Debug logging is disabled at runtime, but ABIDES builds the f-string arguments eagerly
(fmt_ts, Order.__str__), which is ~16% of simulation time. Guarding skips only the string
construction; the arguments are pure formatting, so no simulator state or RNG is touched.
The guard is inserted on the statement's first line, so line numbers are preserved."""
import ast, pathlib, sys

def rewrite(path: pathlib.Path) -> int:
    with open(path, newline="") as fh:
        src = fh.read()
    tree = ast.parse(src)
    targets = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody", "handlers"):
            seq = getattr(node, field, None)
            for stmt in (seq if isinstance(seq, list) else []):
                if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Attribute)
                        and stmt.value.func.attr == "debug"
                        and isinstance(stmt.value.func.value, ast.Name)
                        and stmt.value.func.value.id == "logger"):
                    targets.append((stmt.lineno, stmt.col_offset))
    if not targets:
        return 0
    lines = src.splitlines(keepends=True)
    for lineno, col in sorted(set(targets), reverse=True):
        l = lines[lineno - 1]
        lines[lineno - 1] = l[:col] + "if logger.isEnabledFor(10): " + l[col:]
    out = "".join(lines)
    ast.parse(out)  # must still compile
    with open(path, "w", newline="") as fh:
        fh.write(out)
    return len(set(targets))

if __name__ == "__main__":
    total = 0
    for root in sys.argv[1:]:
        for p in sorted(pathlib.Path(root).rglob("*.py")):
            total += rewrite(p)
    print(f"lazy_debug: guarded {total} logger.debug statements")
