import time

class ExecutionTimer:
    """
    A context manager to time the execution of code blocks.
    Only prints the duration if verbose is set to True.
    """
    def __init__(self, name="Execution", verbose=False):
        self.name = name
        self.verbose = verbose
        self.start_time = None
        self.duration = 0.0

    def __enter__(self):
        self.start_time = time.time()
        if self.verbose:
            print(f"\n⏱️  [{self.name}] Timer started...")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.time() - self.start_time
        if self.verbose:
            print(f"⏱️  [{self.name}] Completed in {self.duration:.2f} seconds.\n")

class RepetitionDetector:
    """
    A generic detector to identify when an agent repeats the exact same state or output.
    This can be used to prevent infinite loops when an LLM repeats the same error.
    """
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.last_item = None
        self.count = 0

    def check(self, item: str) -> bool:
        """
        Returns True if the item has been repeated `threshold` times consecutively.
        """
        if not item:
            self.reset()
            return False

        if item == self.last_item:
            self.count += 1
        else:
            self.count = 1
            self.last_item = item
            
        return self.count >= self.threshold

    def reset(self):
        """Resets the tracker."""
        self.count = 0
        self.last_item = None
