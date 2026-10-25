"""Finite in-process source for protocol fixtures, never used by the application."""
def inline_capture(stream_type):
    class Inline:
        def __init__(self,request,callback):
            self.stream=stream_type(callback=callback);self.info={'device_name':'Synthetic input'};self.health={};self.process=None
        def __enter__(self):self.stream.__enter__();return self
        def check(self):pass
        def __exit__(self,*args):self.stream.__exit__(*args)
    return Inline
