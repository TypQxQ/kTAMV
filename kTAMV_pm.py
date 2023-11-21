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

        if ('x' not in kin_status['homed_axes'] or
            'y' not in kin_status['homed_axes'] or
            'z' not in kin_status['homed_axes']):
            raise Exception("Must home X, Y and Z axes first.")



    def moveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed, protected=False):
        # send calling to log
        logging.debug('*** calling kTAMV_pm.moveRelative')
        logging.debug('Requesting a move by a position of: X: ' + str(X) + ' Y: ' + str(Y) + ' Z: ' + str(Z) + ' at speed: ' + str(moveSpeed) + ' protected: ' + str(protected))

        # Ensure that the printer is homed before continuing
        self.ensureHomed()
        
        _current_position = self.get_gcode_position()
        _new_position = [_current_position[0] + X, _current_position[1] + Y, _current_position[2] + Z]
        logging.debug('New absolute position to move to: ' + str(_new_position))
        
        try:
            if not (protected):
                self.moveAbsoluteToArray(_new_position, moveSpeed)
                self.toolhead.wait_moves()
            else:
                self.moveAbsolute(_new_position[0], _current_position[1], _current_position[2], moveSpeed)
                self.toolhead.wait_moves()
                self.moveAbsolute(_new_position[0], _new_position[1], _current_position[2], moveSpeed)
                self.toolhead.wait_moves()
                self.moveAbsolute(_new_position[0], _new_position[1], _new_position[2], moveSpeed)
                self.toolhead.wait_moves()
        except Exception as e:
            logging.exception('Error: kTAMV_pm.moveRelative cannot run: ' + str(e))
            raise e
            
        # send exiting to log
        logging.debug('*** exiting kTAMV_pm.moveRelative')

        # self.ensureHomed()
        # E = 0

        # try:
        #     if not (protected):
        #         self.toolhead.move([X, Y, Z, E], moveSpeed)
        #         self.toolhead.wait_moves()
        #     else:
        #         self.toolhead.move([X, 0, 0, E], moveSpeed)
        #         self.toolhead.wait_moves()
        #         self.toolhead.move([0, Y, 0, E], moveSpeed)
        #         self.toolhead.wait_moves()
        #         self.toolhead.move([0, 0, Z, E], moveSpeed)
        #         self.toolhead.wait_moves()
        # except Exception as e:
        #     logging.exception('Error: kTAMV_pm.moveRelative cannot run: ' + str(e))
        #     raise e
            
        # # send exiting to log
        # logging.debug('*** exiting kTAMV_pm.moveRelative')

    def moveRelativeToArray(self, pos_array, moveSpeed=__defaultSpeed, protected=False):
        self.moveRelative(pos_array[0], pos_array[1], pos_array[2], moveSpeed, protected)

    # Move one axis at a time to the position.
    def complexMoveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed):
        self.moveRelative(X, Y, Z, moveSpeed, True)

    # Using G1 command to move the toolhead to the position instead of using the toolhead.move() function because G1 will use the tool's offset.
    def moveAbsoluteToArray(self, pos_array, moveSpeed=__defaultSpeed):
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

    def moveAbsolute(self, X=None, Y=None, Z=None, moveSpeed=__defaultSpeed):
        self.moveAbsolute([X, Y, Z], moveSpeed)
        
    def get_gcode_position(self):
        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_position = gcode_move.get_status()['gcode_position']
        
        return [gcode_position.x, gcode_position.y, gcode_position.z]
