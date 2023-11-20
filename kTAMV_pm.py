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
            if(!protected):
                self.toolhead.move([X, Y, Z], moveSpeed)
                self.toolhead.wait_moves()
            else:
                self.toolhead.move([X, 0, 0], moveSpeed)
                self.toolhead.wait_moves()
                self.toolhead.move([0, Y, 0], moveSpeed)
                self.toolhead.wait_moves()
                self.toolhead.move([0, 0, Z], moveSpeed)
                self.toolhead.wait_moves()
        except Exception as e:
            logging.exception('Error: kTAMV_pm.moveRelative cannot run: ' + str(e))
            raise e
            
        # send exiting to log
        logging.debug('*** exiting kTAMV_pm.moveRelative')

    def complexMoveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed):
        moveRelative(X, Y, Z, moveSpeed, True)

    # Using G1 command to move the toolhead to the position instead of using the toolhead.move() function because G1 will use the tool's offset.
    def moveAbsolute(self, pos_array, moveSpeed=__defaultSpeed):
        gcode = "G1 "
        for i in range(len(pos_array)):
            if i == 0:
                gcode += "X%s " % (pos_array[i])
            elif i == 1:
                gcode += "Y%s " % (pos_array[i])
            elif i == 2:
                gcode += "Z%s " % (pos_array[i])
        gcode += "F%s " % (moveSpeed)
        
        # self.log.trace("G1 command: %s" % gcode)
        self.gcode.run_script_from_command(gcode)
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
