'''
Helper "pointers" for components.
These are typically tied to a component.
Will deprecate eventually when there's better ways to fix this?
(M3 interrupts, TIMERLS debug start/stops)
'''

class ComponentFastLookup:
    def __init__(self):
        self.timels = None
        self.m3 = None
        self.uart0 = None

        # PINMUX and GPIO not necessary, only increases setup time, not runtime.