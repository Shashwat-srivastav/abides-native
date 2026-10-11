"""Build-time rewrite: replace the kernel's queue.PriorityQueue with a lock-free heapq queue.

queue.PriorityQueue is heapq.heappush/heappop on a list behind a mutex + condition variables.
The kernel is single-threaded, so the lock is pure overhead (~8% of simulation time). This class
performs the identical heap operations on the identical (time, (sender, recipient, msg)) tuples,
so pop order -- including ties -- is unchanged."""
import pathlib, sys

HEAPQ_CLASS = '''

class _HeapQueue:
    """Lock-free drop-in for queue.PriorityQueue (single-threaded kernel)."""

    __slots__ = ("queue",)

    def __init__(self):
        self.queue = []

    def put(self, item):
        heapq.heappush(self.queue, item)

    def get(self):
        return heapq.heappop(self.queue)

    def empty(self):
        return not self.queue

    def qsize(self):
        return len(self.queue)
'''

def main(kernel_path: str) -> None:
    p = pathlib.Path(kernel_path)
    with open(p, newline="") as fh:
        src = fh.read()
    old = "= queue.PriorityQueue()"
    assert src.count(old) == 1, "kernel PriorityQueue construction not found exactly once"
    src = src.replace(old, "= _HeapQueue()")
    anchor = "\nlogger = logging.getLogger(__name__)\n"
    assert src.count(anchor) == 1, "logger anchor not found"
    src = src.replace(anchor, "\nimport heapq\n" + anchor.rstrip("\n") + HEAPQ_CLASS + "\n", 1)
    compile(src, str(p), "exec")
    with open(p, "w", newline="") as fh:
        fh.write(src)
    print("heap_queue: kernel queue replaced")

if __name__ == "__main__":
    main(sys.argv[1])
