import time, os
import numpy as np
import math
from requests.exceptions import InvalidURL, HTTPError, RequestException, ConnectionError
from . import kTAMV_io, kTAMV_pm
from . import kTAMV_cv, kTAMV_DetectionManager
from PIL import Image, ImageDraw, ImageFont, ImageFile
import requests, json

import logging

# from ..toolhead import ToolHead

class kTAMV:
    def __init__(self, config):
        # Load config values
        self.camera_address = config.get('nozzle_cam_url')
        self.server_url = config.get('server_url')
        self.save_image = config.getboolean('save_image', False)
        self.camera_position = config.getlist('camera_position', ('x','y'), count=2)
        self.camera_position = (float(self.camera_position[0]), float(self.camera_position[1]))
        self.speed = config.getfloat('speed', 50., above=10.)
        self.calib_iterations = config.getint('calib_iterations', 1, minval=1, maxval=25)
        self.calib_value = config.getfloat('calib_value', 1.0, above=0.25)
 
        # TODO: Change from using the ktcc_log to using the klippy logger
        if not config.has_section('ktcc_log'):
            raise self.printer.config_error("Klipper Toolchanger KTCC addon section not found in config, CVNozzleCalib wont work")

        # Load used objects.
        self.printer  = config.get_printer()
        self.config = config 
        self.gcode = self.printer.lookup_object('gcode')
        self.log = self.printer.lookup_object('ktcc_log')
        self.reactor = self.printer.get_reactor()
        # self.gcode_macro : gcode_macro.GCodeMacro = self.printer.load_object(config, 'gcode_macro')
        # self.toollock : ktcc_toolchanger.ktcc_toolchanger = self.printer.lookup_object('ktcc_toolchanger')

        # Register backwords compatibility commands
        self.__currentPosition = {'X': None, 'Y': None, 'Z': None}

        self.io = kTAMV_io.kTAMV_io(self.log, self.camera_address, self.server_url, self.save_image)
        self.cv_tools = kTAMV_cv.kTAMV_cv(config, self.io)
        self.DetectionManager = kTAMV_DetectionManager.kTAMV_DetectionManager(config, self.io)
        self.pm = kTAMV_pm.kTAMV_pm(config)

        self.gcode.register_command('KTAMV_TEST', self.cmd_SIMPLE_TEST, desc=self.cmd_SIMPLE_TEST_help)
        self.gcode.register_command('KTAMV_SIMPLE_NOZZLE_POSITION', self.cmd_SIMPLE_NOZZLE_POSITION, desc=self.cmd_SIMPLE_NOZZLE_POSITION_help)
        self.gcode.register_command('CV_CENTER_TOOLHEAD', self.cmd_center_toolhead, desc=self.cmd_center_toolhead_help)
        self.gcode.register_command('CV_CALIB_NOZZLE_PX_MM', self.cmd_CALIB_NOZZLE_PX_MM, desc=self.cmd_CALIB_NOZZLE_PX_MM_help)
        self.gcode.register_command('CV_CALIB_OFFSET', self.cmd_CALIB_OFFSET, desc=self.cmd_CALIB_OFFSET_help)
        self.gcode.register_command('CV_SET_CENTER', self.cmd_SET_CENTER, desc=self.cmd_SET_CENTER_help)
        
    cmd_SIMPLE_TEST_help = "Gets all requests from the server and prints them to the console"
    def cmd_SIMPLE_TEST(self, gcmd):
        response = json.loads(requests.get(self.server_url + "/getAllReqests").text)
        logging.debug("Response: %s" % str(response))
        gcmd.respond_info("Response: %s" % str(response))

    cmd_SET_CENTER_help = "Centers the camera to the current toolhead position"
    def cmd_SET_CENTER(self, gcmd):
        self._set_camera_center_to_current_position()
        
    def _set_camera_center_to_current_position(self):
        gcode_position = self._get_gcode_position()
        self.camera_position = (float(gcode_position.x), float(gcode_position.y))
        self.log.trace("Set camera position to: %s" % str(self.camera_position))

    cmd_center_toolhead_help = "Positions the current toolhead at the camera nozzle position"
    def cmd_center_toolhead(self, gcmd):
        self._center_toolhead()

    cmd_SIMPLE_NOZZLE_POSITION_help = "Detects if a nozzle is found in the current image"
    def cmd_SIMPLE_NOZZLE_POSITION(self, gcmd):
        self._get_nozzle_position(gcmd)

    def _get_nozzle_position(self, gcmd):
        _request_id = None
        try:
            _response = json.loads(requests.get(self.server_url + "/burstNozzleDetection").text)
            if not (_response['statuscode'] == 202 or _response['statuscode'] == 200):
                gcmd.respond_info("Failed to run burstNozzleDetection, got statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))
                return
            
            # Success, got request id
            _request_id = _response['request_id']
            
            start_time = time.time()
            while True:
                #  Check if the request is done
                _response = json.loads(requests.get(f"{self.server_url}/getReqest?request_id={_request_id}").text)
                if _response['statuscode'] == 200:
                    gcmd.respond_info("Found nozzle at position: %s after %2f seconds" % (str(_response['position']), float(_response['runtime'])))
                    return _response
                
                # Check if one minute has elapsed
                elapsed_time = time.time() - start_time
                if elapsed_time >= 60:
                    gcmd.respond_info("Nozzle detection kTAMV_SIMPLE_NOZZLE_POSITION timed out after 60 seconds")
                    return None

                # Pause for 100ms to avoid busy loop
                _ = self.reactor.pause(self.reactor.monotonic() + 0.200)
            
        except Exception as e:
            raise Exception("SIMPLE_NOZZLE_POSITION failed %s" % str(e))

            

    # def _calibrate_tool(self, toolindex):
    #     # Switch to T1 and move to center above camera
    #     self.changeTool(toolindex)
    #     self._center_toolhead()

    #     # Find initial tool position to caluclate offset from
    #     tool_nozzle_pos = self._recursively_find_nozzle_position()
    #     if tool_nozzle_pos is None:
    #         self.log.trace("Did not find nozzle after initial T%s move to center, aborting" % str(toolindex))   
    #         self.io.close_stream()
    #         return

    #     pos = (int(tool_nozzle_pos[0]), int(tool_nozzle_pos[1]))
    #     rotated_position = self.cv_tools.rotate_around_origin(self.calibrated_center_point, pos, self.calibrated_angle)

    #     # TODO: If t1_nozzle_pos nozzle radius differs a lot from T0 nozzle radius there will be issues

    #     # Calculate the X and Y offsets
    #     x_offset_px = t0_nozzle_pos[0]-rotated_position[0]
    #     y_offset_px = t0_nozzle_pos[1]-rotated_position[1]

    #     # Convert the px offset values to real world mm
    #     x_offset_mm = x_offset_px/px_mm
    #     y_offset_mm = y_offset_px/px_mm

    #     # TODO: Add early return if movement is bigger then some we can assume is outside of the cameras vision
    #     new_pos_t1 = toolhead.get_position()
    #     new_pos_t1[0] = center_point[0]+x_offset_mm
    #     new_pos_t1[1] = center_point[1]+y_offset_mm

    #     # Move T1 to "center" + offsets
    #     toolhead.move(new_pos_t1, self.speed)
    #     toolhead.wait_moves()

    #     second_t1_pos = self._recursively_find_nozzle_position()
    #     if second_t1_pos is None:
    #         gcmd.respond_info("Tried to use MM offsets X%.4f Y%.4f, but did not find T1 nozzle after move..." % (x_offset_mm, y_offset_mm))
    #         self.io.close_stream()
    #         return

    #     # TODO: Add early return if resulting virtual offset is not within spec

    #     gcmd.respond_info("""
    #         Done calibrating! 
    #         Using MM offsets X%.4f Y%.4f got:
    #         Initial virtual offset: X%d Y%d
    #         Resulting virtual offset: X%d Y%d
    #     """ % (
    #         x_offset_mm, 
    #         y_offset_mm, 
    #         (t0_nozzle_pos[0]-t1_nozzle_pos[0]), # Initial virtual offset between t0 and t1
    #         (t0_nozzle_pos[1]-t1_nozzle_pos[1]), # Initial virtual offset between t0 and t1
    #         (t0_nozzle_pos[0]-second_t1_pos[0]), # Calibrated virtual offset between t0 and t1
    #         (t0_nozzle_pos[1]-second_t1_pos[1]) # Calibrated virtual offset between t0 and t1
    #     ))

    #     self.io.close_stream()

    #     self._x_home_current_toolhead()
    #     # Restore state to t0
    #     self.changeTool(0)





    cmd_CALIB_OFFSET_help = "Calibraties T0 and T1 XY offsets based on the configured center point"
    def cmd_CALIB_OFFSET(self, gcmd):
        self.io.open_stream()
        # Ensure we are using T10 for testing
        self.changeTool(10)

        skip_center = gcmd.get('SKIP_CENTER', False)
        calib_value = gcmd.get_float('CALIB_VALUE', self.calib_value)
        calib_iterations = gcmd.get_int('CALIB_ITERATIONS', self.calib_iterations)

        # Get positions from the calibration function
        positions = self.calibrate_toolhead_movement(skip_center, calib_value, calib_iterations)

        # avg_positions would be {(klipper_x_in_mm, klipper_y_in_mm): (cv_pixel_x_in_px, cv_pixel_y_in_px), {...}, ...}
        avg_points = self.cv_tools.get_average_positions(positions)

        # Get px/mm from averages
        px_mm = self.cv_tools.calculate_px_to_mm(avg_points, self.camera_position)

        top_point = self.cv_tools.get_edge_point(positions, 'top')
        center_point = self.cv_tools.get_edge_point(positions, 'center')

        point_ideal_top = (
            int(avg_points[center_point][0]), 
            0
        )
        point_center = (
            int(avg_points[center_point][0]), 
            int(avg_points[center_point][1])
        )
        point_top = (
            int(avg_points[top_point][0]), 
            int(avg_points[top_point][1])
        )

        slope1 = self.cv_tools.slope(point_center, point_ideal_top)
        slope2 = self.cv_tools.slope(point_center, point_top)

        ang = self.cv_tools.angle(slope1, slope2)

        if point_center[1] < point_top[1]: 
            ang += 180

        rads = math.radians(ang)

        center_deviation = self.cv_tools.get_center_point_deviation(positions[center_point])
        gcmd.respond_info("""
            T0 calibration
            Center point: (%.2f,%.2f)
            Calibration accuracy: X%dpx Y%dpx
            px/mm: %.4f
            Camera rotation %.2f
        """ % (
            avg_points[center_point][0],
            avg_points[center_point][1],
            center_deviation[0],
            center_deviation[1],
            px_mm,
            ang
        ))

        toolhead = self.printer.lookup_object('toolhead')

        # Get a new T0 center position after running the calibration function
        # TODO: If this position deviates too much from calibration function center point, abort
        t0_nozzle_pos = self._recursively_find_nozzle_position()
        if t0_nozzle_pos is None:
            gcmd.respond_info("Did not find nozzle after initial T0 move to center, aborting")
            self.io.close_stream()
            return

        # X home T0
        self._x_home_current_toolhead()

        # Switch to T1 and center above camera
        self.changeTool(1)
        self._center_toolhead()

        # Find initial T1 position to caluclate offset from
        t1_nozzle_pos = self._recursively_find_nozzle_position()
        if t1_nozzle_pos is None:
            gcmd.respond_info("Did not find nozzle after initial T1 move to center, aborting")
            self.io.close_stream()
            return

        t1_pos = (int(t1_nozzle_pos[0]), int(t1_nozzle_pos[1]))
        t1_rotated = self.cv_tools.rotate_around_origin(avg_points[center_point], t1_pos, -rads)

        # TODO: If t1_nozzle_pos nozzle radius differs a lot from T0 nozzle radius there will be issues

        # Calculate the X and Y offsets
        x_offset_px = t0_nozzle_pos[0]-t1_rotated[0]
        y_offset_px = t0_nozzle_pos[1]-t1_rotated[1]

        # Convert the px offset values to real world mm
        x_offset_mm = x_offset_px/px_mm
        y_offset_mm = y_offset_px/px_mm

        # TODO: Add early return if movement is bigger then some we can assume is outside of the cameras vision
        new_pos_t1 = toolhead.get_position()
        new_pos_t1[0] = center_point[0]+x_offset_mm
        new_pos_t1[1] = center_point[1]+y_offset_mm

        # Move T1 to "center" + offsets
        toolhead.move(new_pos_t1, self.speed)
        toolhead.wait_moves()

        second_t1_pos = self._recursively_find_nozzle_position()
        if second_t1_pos is None:
            gcmd.respond_info("Tried to use MM offsets X%.4f Y%.4f, but did not find T1 nozzle after move..." % (x_offset_mm, y_offset_mm))
            self.io.close_stream()
            return

        # TODO: Add early return if resulting virtual offset is not within spec

        gcmd.respond_info("""
            Done calibrating! 
            Using MM offsets X%.4f Y%.4f got:
            Initial virtual offset: X%d Y%d
            Resulting virtual offset: X%d Y%d
        """ % (
            x_offset_mm, 
            y_offset_mm, 
            (t0_nozzle_pos[0]-t1_nozzle_pos[0]), # Initial virtual offset between t0 and t1
            (t0_nozzle_pos[1]-t1_nozzle_pos[1]), # Initial virtual offset between t0 and t1
            (t0_nozzle_pos[0]-second_t1_pos[0]), # Calibrated virtual offset between t0 and t1
            (t0_nozzle_pos[1]-second_t1_pos[1]) # Calibrated virtual offset between t0 and t1
        ))

        self.io.close_stream()

        self._x_home_current_toolhead()
        # Restore state to t0
        self.changeTool(0)

    cmd_CALIB_NOZZLE_PX_MM_help = "Calibrates the movement of the active nozzle around the point it started at"
    def cmd_CALIB_NOZZLE_PX_MM(self, gcmd):
        self.io.open_stream()
        skip_center = gcmd.get('SKIP_CENTER', False)
        calib_value = gcmd.get_float('CALIB_VALUE', self.calib_value)
        calib_iterations = gcmd.get_int('CALIB_ITERATIONS', self.calib_iterations)

        # Get positions from the calibration function
        positions = self.calibrate_toolhead_movement(skip_center, calib_value, calib_iterations)

        # avg_positions would be {(klipper_x_in_mm, klipper_y_in_mm): (cv_pixel_x_in_px, cv_pixel_y_in_px), {...}, ...}
        avg_points = self.cv_tools.get_average_positions(positions)

        # Get px/mm from averages
        px_mm = self.cv_tools.calculate_px_to_mm(avg_points, self.camera_position)

        top_point = self.cv_tools.get_edge_point(positions, 'top')
        center_point = self.cv_tools.get_edge_point(positions, 'center')

        point_ideal_top = (
            int(avg_points[center_point][0]), 
            0
        )
        point_center = (
            int(avg_points[center_point][0]), 
            int(avg_points[center_point][1])
        )
        point_top = (
            int(avg_points[top_point][0]), 
            int(avg_points[top_point][1])
        )

        slope1 = self.cv_tools.slope(point_center, point_ideal_top)
        slope2 = self.cv_tools.slope(point_center, point_top)

        ang = self.cv_tools.angle(slope1, slope2)

        if point_center[1] < point_top[1]: 
            ang += 180

        print_positions = gcmd.get('PRINT_POSITIONS', False)
        if print_positions != False:
            debug_string = self.cv_tools.positions_dict_to_string(positions)
            gcmd.respond_info(debug_string)

        center_deviation = self.cv_tools.get_center_point_deviation(positions[self.camera_position])
            
        gcmd.respond_info("""
            Calibration results:
            Center point: (%.2f,%.2f)
            Deviation: X%dpx Y%dpx
            px/mm: %.4f
            Camera rotation %.4f
        """ % (avg_points[self.camera_position][0], avg_points[self.camera_position][1], center_deviation[0], center_deviation[1], px_mm, ang))

        self.io.close_stream()
        self.calibrated_center_point = point_center
        self.calibrated_angle = ang

    def calibrate_toolhead_movement(self, skip_move_toolhead_to_center=False, calib_value=1.0, iterations=1):
        if not skip_move_toolhead_to_center:
            self._center_toolhead()

        # toolhead = self.printer.lookup_object('toolhead')
        # starting_pos = toolhead.get_position()
        self._set_camera_center_to_current_position()
        starting_pos = self._get_gcode_position()
        start_x = starting_pos[0]
        start_y = starting_pos[1]

        # These points most likely don't need to be this extensive
        calib_points = [ 
            (start_x-calib_value, start_y), # Most left
            # (start_x-(calib_value/2), start_y-(calib_value/2)), # Top left corner
            (start_x, start_y-calib_value), # Most top
            # (start_x+(calib_value/2), start_y-(calib_value/2)), # Top right corner
            (start_x+calib_value, start_y), # Most right
            # (start_x+(calib_value/2), start_y+(calib_value/2)), # Bottom right corner
            (start_x, start_y+calib_value), # Most bottom
            # (start_x-(calib_value/2), start_y+(calib_value/2)) # Bottom left corner
        ]

        # Would have data like {(klipper_x_in_mm, klipper_y_in_mm): [(cv_pixel_x_in_px, cv_pixel_y_in_px), ...], ...}
        positions = {}

        # Itterations is most likely not needed for the same reason as mentioned for calib_points
        for iteration in range(iterations):
            for i, calib_point in enumerate(calib_points):
                # Move the toolhead to the calibration point but using the tool's offset.
                # self.log.trace("Moving to calib point no.%i: %s" % ( iteration, str(calib_point)))
                self._move_tool(calib_point)

                nozzle_pos = self._recursively_find_nozzle_position()
                if nozzle_pos:
                    positions.setdefault(calib_point,[]).append(nozzle_pos)
                else:
                    raise self.gcode.error("No nozzle detected for position %i: (%.3f, %.3f). Iteration: %i" % (i ,calib_point[0],calib_point[1], iteration))

                self._move_tool((start_x, start_y))

                nozzle_pos = self._recursively_find_nozzle_position()
                if nozzle_pos:
                    positions.setdefault((start_x, start_y),[]).append(nozzle_pos)

        return positions

    def changeTool(self, toolindex):
        self.gcode.run_script_from_command("T%s" % str(toolindex))

    def _x_home_current_toolhead(self):
        toolhead = self.printer.lookup_object('toolhead')
        dc = self.printer.lookup_object('dual_carriage')
        status = dc.get_status()
        pos = toolhead.get_position()

        if status['active_carriage'] == 'CARRIAGE_0':
            stepper_x = self.config.getsection('stepper_x')
            x_endstop = stepper_x.getfloat('position_endstop')
            pos[0] = x_endstop
        elif status['active_carriage'] == 'CARRIAGE_1':
            dual_carriage = self.config.getsection('dual_carriage')
            x_endstop = dual_carriage.getfloat('position_endstop')
            pos[0] = x_endstop

        toolhead.move(pos, self.speed)
        toolhead.wait_moves()

    def _center_toolhead(self):
        self._move_tool(self.camera_position)
        # toolhead = self.printer.lookup_object('toolhead')
        # starting_pos = toolhead.get_position()
        # if starting_pos[0] != self.camera_position[0] or starting_pos[1] != self.camera_position[1]:
        #     center_pos = starting_pos
        #     center_pos[0] = self.camera_position[0]
        #     center_pos[1] = self.camera_position[1]
        #     toolhead.move(center_pos, self.speed)
        # toolhead.wait_moves()

    def _find_nozzle_positions(self):
        self.log.always("Finding nozzle positions")
        image, size = self.io.get_single_frame()
        if image is None:
            self.log.always("No image found")
            return None

        return self.cv_tools.detect_nozzles(image)

    def _recursively_find_nozzle_position(self):
        start_time = time.time()  # Get the current time

        CV_TIME_OUT = 20 #5 # If no nozzle found in this time, timeout the function
        CV_MIN_MATCHES = 3 # Minimum amount of matches to confirm toolhead position after a move
        CV_XY_TOLERANCE = 1 # If the nozzle position is within this tolerance, it's considered a match. 1.0 would be 1 pixel. Only whole numbers are supported.

        last_pos = (0,0)
        pos_matches = 0
        while time.time() - start_time < CV_TIME_OUT:
            positions = self._find_nozzle_positions()
            if not positions:
                continue

            pos = positions[0]
            # Only compare XY position, not radius...
            if abs(pos[0] - last_pos[0]) <= CV_XY_TOLERANCE and abs(pos[1] - last_pos[1]) <= CV_XY_TOLERANCE:
                pos_matches += 1
                if pos_matches >= CV_MIN_MATCHES:
                    return pos
            else:
                self.log.trace("Position found does not match last position. Last position: %s, current position: %s" % (str(last_pos), str(pos)))
                self.log.trace("Difference: X%.3f Y%.3f" % (abs(pos[0] - last_pos[0]), abs(pos[1] - last_pos[1])))
                pos_matches = 0

            last_pos = pos
        return None
    
    # Using G1 command to move the toolhead to the position instead of using the toolhead.move() function because G1 will use the tool's offset.
    def _move_tool(self, pos_array, speed = None):
        if speed is None:
            speed = self.speed
            
        gcode = "G1 "
        for i in range(len(pos_array)):
            if i == 0:
                gcode += "X%s " % (pos_array[i])
            elif i == 1:
                gcode += "Y%s " % (pos_array[i])
            elif i == 2:
                gcode += "Z%s " % (pos_array[i])
        gcode += "F%s " % (speed)
        
        # self.log.trace("G1 command: %s" % gcode)
        self.gcode.run_script_from_command(gcode)
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()

    def _get_gcode_position(self):
        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_position = gcode_move.get_status()['gcode_position']
        # self.log.trace("Gcode position: %s" % str(gcode_position))
        return gcode_position

    def _set_calibrate_px_mm(self):
        self.olduv = self.uv
        self.space_coordinates = []
        self.camera_coordinates = []

        # Setup camera calibration move coordinates
        self.calibrationCoordinates = [ [0,-0.5], [0.294,-0.405], [0.476,-0.155], [0.476,0.155], [0.294,0.405], [0,0.5], [-0.294,0.405], [-0.476,0.155], [-0.476,-0.155], [-0.294,-0.405] ]
        self.guessPosition  = [1,1]

        _current_position = self._get_gcode_position()
        _nozzle_possition = self._recursively_find_nozzle_position()

        self.__currentPosition['X'] = _current_position[0]
        self.__currentPosition['Y'] = _current_position[1]
        self.__currentPosition['Z'] = _current_position[2]
        
        self.uv = [_nozzle_possition[0], _nozzle_possition[1]]
        
        self.space_coordinates.append((self.__currentPosition['X'], self.__currentPosition['Y']))
        self.camera_coordinates.append((self.uv[0], self.uv[1]))
        
        params = {'position':{'X': self.offsetX, 'Y': self.offsetY}}
        self.pm.moveRelative(params)
        self.moveRelativeSignal.emit(params)



def load_config(config):
    return kTAMV(config)
