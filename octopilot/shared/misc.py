import time
import threading
import logging

class RepeatedTimer(object):
    """Helper object used to call an event at regular intervals
    
    https://stackoverflow.com/questions/474528/how-to-repeatedly-execute-a-function-every-x-seconds
    """
    def __init__(self, interval, function, *args, **kwargs):
        """Init a new RepatedTimer that will call `function` every `interval`
        
        The timer starts immediately upon initialization.
        
        TODO: do not start immediately
        TODO: better handle the case where someone calls `start` and it's
        already running
        Right now, it's a common issue that it starts automatically and then
        gets started again.
        
        Arguments
        ---------
        interval : numeric, time in seconds
        function : method
            This method will be called every `interval` seconds
        args, kwargs : passed to function
        """
        # Store aguments
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs

        # Instance variables
        self._timer = None
        self.is_running = False
        self.next_call = time.time()
        
        # Start immediately
        self.start()

    def _run(self):
        """The function that is called when _timer completes"""
        # Start again
        self.is_running = False
        self.start()
        
        # Call the function
        self.function(*self.args, **self.kwargs)

    def start(self):
        """Start the Repeated Timer"""
        # Define next_call
        if not self.is_running:
            self.next_call += self.interval
        
        # Define the timer to use
        self._timer = threading.Timer(self.next_call - time.time(), self._run)
        
        # Start the _timer
        self._timer.start()
        self.is_running = True

    def stop(self):
        """Cancel _timer and stop"""
        self._timer.cancel()
        self.is_running = False
        
class PersistentRepeatedTimer(object):
    """
    Run a periodic callback on one persistent thread.

    Unlike RepeatedTimer, this does not create a new
    threading.Timer thread for every invocation.
    """

    def __init__(self, interval, function, *args, **kwargs):
        self.interval = float(interval)
        self.function = function
        self.args = args
        self.kwargs = kwargs

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="surface-report-timer",
            daemon=True,
        )
        self._thread.start()

    def _run(self):
        next_call = time.monotonic() + self.interval

        while not self._stop_event.is_set():
            remaining = next_call - time.monotonic()

            if self._stop_event.wait(max(0.0, remaining)):
                break

            if self._stop_event.is_set():
                break

            try:
                self.function(*self.args, **self.kwargs)
            except Exception:
                logging.exception(
                    "PersistentRepeatedTimer callback failed"
                )

            next_call += self.interval

            # Skip missed intervals rather than accumulating
            # overlapping or back-to-back callbacks.
            now = time.monotonic()
            if next_call <= now:
                next_call = now + self.interval

    def stop(self):
        self._stop_event.set()

        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)