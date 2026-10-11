"""t3native — native fast path for the Track 3 ``simulate`` / ``simulate-batch`` verbs.

Kept separate from ``abides_fork`` so the fast path never imports ABIDES; the reference adapter is
imported lazily, only when a scenario falls back.
"""
