"""Fresh interpreter entry point; native thread limits precede NumPy import."""
import os
from .execution import THREAD_ENV, worker_main

if __name__ == '__main__':
    os.environ.update(THREAD_ENV)
    raise SystemExit(worker_main())
