import logging
import datetime

class NonRepetitiveLogger(logging.Logger):
    # https://stackoverflow.com/questions/57472091/how-to-build-a-python-logging-function-that-doesnt-repeat-the-exact-same-messag
    # define the cache as class attribute if all logger instances of _this_ class
    # shall share the same cache
    # _message_cache = []

    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name=name, level=level)
        # define the cache as instance variable if you want each logger instance
        # to use its own cache
        self._message_cache = {}
        self.wait_time = datetime.timedelta(seconds=5)

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False):
        msg_hash = hash(msg) # using hash() builtin; see remark below
        dt_now = datetime.datetime.now()

        # See if we've already received this one
        if msg_hash in self._message_cache:
            # See when the last time was
            last_time = self._message_cache[msg_hash]
            
            # See how long it's been
            if dt_now < last_time + self.wait_time:
                # It hasn't been long enough, just return without logging
                return
            else:
                # Update the last warn time to now
                self._message_cache[msg_hash] = dt_now

        else:
            # It wasn't in the cache, add it
            self._message_cache[msg_hash] = dt_now

        # In any other case, do log
        super()._log(level, msg, args, exc_info, extra, stack_info)