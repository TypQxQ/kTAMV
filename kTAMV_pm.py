# kTAMV Printer Manager module
import math, copy
import numpy as np
import logging

class kTAMV_pm:
    __defaultSpeed = 3000

    def __init__(self, config):
        # Load used objects. Mainly to log stuff.
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.log = self.printer.load_object(config, 'ktcc_log')

        self.toolhead = self.printer.lookup_object("toolhead")
        
    # Ensure that the printer is homed before continuing
    def ensureHomed(self):
        curtime = self.printer.get_reactor().monotonic()
        kin_status = self.toolhead.get_kinematics().get_status(curtime)

        for axis in enumerate('XYZ'):
            if axis in kin_status['homed_axes']:
                return

        # If we get here, we're not homed
        raise Exception("Must home X, Y and Z axes first")

        # Old code
        # if ('x' not in kin_status['homed_axes'] or
        #     'y' not in kin_status['homed_axes'] or
        #     'z' not in kin_status['homed_axes']):


    def moveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed, protected=False):
        # send calling to log
        logging.debug('*** calling kTAMV_pm.moveRelative')
        logging.debug('Requesting a move to position: X: ' + str(X) + ' Y: ' + str(Y) + ' Z: ' + str(Z) + ' at speed: ' + str(moveSpeed) + ' protected: ' + str(protected))

        self.ensureHomed()

        try:
            if(protected):
                # self.complexMoveRelative(moveSpeed=moveSpeed, position={'X':X, 'Y': Y, 'Z': Z})
                pass
            else:
                self.toolhead.move([X, Y, Z], moveSpeed)
                self.toolhead.wait_moves()

        except Exception as e:
            logging.exception('Error: kTAMV_pm.moveRelative cannot run: ' + str(e))
            raise e
            
        # send exiting to log
        logging.debug('*** exiting kTAMV_pm.moveRelative')

