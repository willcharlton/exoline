# -*- coding: utf-8 -*-
# pylint: disable=W0604,W0312,W0102,W0232,C1001
'''Open a persistent websocket and make asynchronous,
requests using the RPC API.

The <json_object> is a JSON dictionary with keys as
CIKs and values as either {'rid': <rid>} or 
{'alias': <alias>}. 

Example:
  exo wswait {"ec371e51158dd2034e633835a416a2f08c22a642": {"rid": "75b4f0eb5925610c14ba0205078ce4b3b5711c61"}}
Usage:
    exo [options] wswait <pcik> <json_object> [options]

Command Options:
    <pcik>                 The Parent CIK for all future requests.
    <json_object>          A JSON dictionary. { <pcik>: {'rid':<rid>}|{'cik':<cik>} }
    --verbose              Adjust stuff.
    --limit=<limit>        Get shit done.
    --timeout=<timeout>    A timeout
    --jq=<jq>              'jq'-style cli parsing.

{{ helpoption }}
'''

import websocket, threading, json, queue
from time import time
from datetime import datetime

# class ExoTimer(threading._Timer):
#     """ Normal threading.Timer signature:
#             threading.Timer(interval, function, args=[], kwargs={})
#         This extension class is the same, but with the added function knowing 
#         how much time is left in the timer.
#     """
#     def __init__(self, interval, function, args=[], kwargs={}):
#         threading._Timer.__init__(self, interval, function, args=args, kwargs=kwargs)
#         self._start_time = time()
#         self._callback = function.__name__
#     def __repr__(self):
#         return '{0} :: {1}s - {2}'.format(
#             self.name,
#             # self._callback,
#             self.seconds_left(),
#             datetime.fromtimestamp(time() + self.seconds_left()).strftime('%m/%d/%Y %H:%M:%S'))
#     def seconds_left(self):
#         """ Return a float of the number of seconds remaining in the Timer. """
#         now = time()
#         return self.interval - (now - self._start_time)

class MethodThread(threading.Thread):
    """
        Class for running functions and/or methods as threads.

        Example usage:
            t1 = MethodThread(set_report_mode, TNodeModes.REPORT)
            t1.start()
            t1.join()
    """
    def __init__(self, target, *args):
        threading.Thread.__init__(self)
        self._target = target
        self._args = args

    def run(self):
        self._target(*self._args)

class OPWSS():
    def __init__(self, cik, kill_event):
        """

        """
        self.ws_uri = 'wss://m2.exosite.com/ws'
        self.auth = { 'auth': {'cik': cik} }
        self.wss = websocket.WebSocketApp(
            self.ws_uri,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.wss.on_open = self.on_open
        self.Q_in = queue.Queue()
        self.Q_out = queue.Queue()
        self.kill_event = kill_event
        # print("on_open function set")

    def on_message(self, ws, message):
        self.Q_out.put(message)

    def on_error(self, ws, error):
        print(error)

    def on_close(self, ws):
        self.closed = True
        print("### closed ###")

    def on_open(self, ws):
        """ Called when run_forever is called. """
        # print("Starting... sending auth")
        def __run(*args):
            self.wss.send(json.dumps(self.auth))
            while not self.kill_event.is_set():
                try:
                    # block for 1 second. if nothing's there, 
                    # then go do something else.
                    new_call = self.Q_in.get(True,1)
                    self.wss.send(json.dumps(new_call))
                except queue.Empty:
                    # If we timed out it's not an error, we just go check other things
                    # print("ping...")
                    # this is just a guess at how to do a ping to maintain the websocket
                    # self.wss.send( json.dumps({}) ) 
                    pass
        t = MethodThread(__run, ())
        t.start()


    def run_forever(self, ws):
        if self.kill_event.is_set():
            pass
        else:
            self.wss.run_forever()

class Plugin():
    def command(self):
        return 'wss'

    def run(self, cmd, args, options): # pylint: disable=R0201
        print("this shouldn't be the run")
        pass


