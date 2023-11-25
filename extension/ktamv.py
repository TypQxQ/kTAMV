import numpy as np
from math import sqrt
from . import kTAMV_utl as utl
import logging
 
class ktamv:
    def __init__(self, config):
        # Load config values
        self.camera_url = config.get('nozzle_cam_url')
        self.server_url = config.get('server_url')
        self.speed = config.getfloat('move_speed', 50., above=10.)
        self.calib_iterations = config.getint('calib_iterations', 1, minval=1, maxval=25)
        self.calib_value = config.getfloat('calib_value', 1.0, above=0.25)
 
        # Initialize variables
        self.mpp = None                 # Average mm per pixel
        self.transformMatrix = None     # Transformation matrix for converting from camera coordinates to space coordinates
        self.space_coordinates = []     # List of space coordinates for each calibration point
        self.camera_coordinates = []    # List of camera coordinates for each calibration point
        self.mm_per_pixels = []         # List of mm per pixel for each calibration point
        self.cp = None                  # Center position used for offset calculations

        # Load used objects.
        self.config = config 
        self.printer  = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')

        self.printer.register_event_handler("klippy:ready", self.handle_ready)

    def handle_ready(self):
        self.reactor = self.printer.get_reactor()
        self.pm = utl.kTAMV_pm(self.config) # Printer Manager
        self.gcode.register_command('KTAMV_CALIB_CAMERA', self.cmd_KTAMV_CALIB_CAMERA, desc=self.cmd_KTAMV_CALIB_CAMERA_help)
        self.gcode.register_command('KTAMV_FIND_NOZZLE_CENTER', self.cmd_FIND_NOZZLE_CENTER, desc=self.cmd_FIND_NOZZLE_CENTER_help)
        self.gcode.register_command('KTAMV_SET_ORIGIN', self.cmd_SET_CENTER, desc=self.cmd_SET_CENTER_help)
        self.gcode.register_command('KTAMV_GET_OFFSET', self.cmd_GET_OFFSET, desc=self.cmd_GET_OFFSET_help)
        self.gcode.register_command('KTAMV_MOVE_TO_ORIGIN', self.cmd_MOVE_TO_ORIGIN, desc=self.cmd_MOVE_TO_ORIGIN_help)
        self.gcode.register_command('KTAMV_SIMPLE_NOZZLE_POSITION', self.cmd_SIMPLE_NOZZLE_POSITION, desc=self.cmd_SIMPLE_NOZZLE_POSITION_help)
        self.gcode.register_command('KTAMV_TEST', self.cmd_SIMPLE_TEST, desc=self.cmd_SIMPLE_TEST_help)
        self.gcode.register_command('KTAMV_SEND_SERVER_CFG', self.cmd_SEND_SERVER_CFG, desc=self.cmd_SEND_SERVER_CFG_help)

    
    cmd_SEND_SERVER_CFG_help = "Send the server configuration to the server, i.e. the nozzle camera url"
    def cmd_SEND_SERVER_CFG(self, gcmd):
        try:
            _camera_url = gcmd.get('CAMERA_URL', self.camera_url)
            rr = utl.send_server_cfg(self.server_url, camera_url = _camera_url)
            gcmd.respond_info("Sent server configuration to server")
            gcmd.respond_info("Server response: %s" % str(rr))
        except Exception as e:
            raise self.gcode.error("Failed to send server configuration to server, got error: %s" % str(e))
        
    cmd_SET_CENTER_help = "Saves the center position for offset calculations based on the current toolhead position."
    def cmd_SET_CENTER(self, gcmd):
        self.cp = self.pm.get_raw_position()
        self.cp = (float(self.cp[0]), float(self.cp[1]))
        self.gcode.respond_info("Center position set to X:%3f Y:%3f" % self.cp[0], self.cp[1])
        
    cmd_MOVE_TO_ORIGIN_help = "Sets the center position for offset calculations based on the current toolhead position"
    def cmd_MOVE_TO_ORIGIN(self, gcmd):
        self.cp = self.pm.get_raw_position()
        self.cp = (float(self.cp[0]), float(self.cp[1]))
        self.gcode.respond_info("Center position set to X:%3f Y:%3f" % self.cp[0], self.cp[1])

    cmd_GET_OFFSET_help = "Get offset from the current position to the configured center position"
    def cmd_GET_OFFSET(self, gcmd):
        if self.cp is None:
            raise self.gcode.error("No center position set, use KTAMV_SET_CENTER to set it to the position you want to get offset from")
            return
        _pos = self.pm.get_raw_position()
        _offset = (float(_pos[0]) - self.cp[0], float(_pos[1]) - self.cp[1])
        self.gcode.respond_info("Offset from center is X:%3f Y:%3f" % _offset[0], _offset[1])

    cmd_FIND_NOZZLE_CENTER_help = "Finds the center of the nozzle and moves it to the center of the camera, offset can be set from here"
    def cmd_FIND_NOZZLE_CENTER(self, gcmd):
        self._calibrate_nozzle(gcmd)

    cmd_SIMPLE_TEST_help = "Gets all requests from the server and prints them to the console"
    def cmd_SIMPLE_TEST(self, gcmd):
        self._calibrate_px_mm(gcmd)
        self._calibrate_nozzle(gcmd)

    cmd_SIMPLE_NOZZLE_POSITION_help = "Detects if a nozzle is found in the current image"
    def cmd_SIMPLE_NOZZLE_POSITION(self, gcmd):
        ##############################
        # Get nozzle position
        ##############################
        logging.debug('*** calling kTAMV_SIMPLE_NOZZLE_POSITION')
        try:
            _response = utl.get_nozzle_position(self.server_url, self.reactor)
            if _response is None:
                raise self.gcode.error("Did not find nozzle, aborting")
            else:
                self.gcode.respond_info("Found nozzle at position: %s after %.2f seconds" % (str(_response['position']), float(_response['runtime'])))
        except Exception as e:
            raise self.gcode.error("Failed to run burstNozzleDetection, got error: %s" % str(e))


    cmd_KTAMV_CALIB_CAMERA_help = "Calibrates the movement of the active nozzle around the point it started at"
    def cmd_KTAMV_CALIB_CAMERA(self, gcmd):
        self.gcode.respond_info("Starting mm/px calibration")
        self._calibrate_px_mm(gcmd)

    def _calibrate_px_mm(self, gcmd):
        ##############################
        # Calibration of the camera
        ##############################
        logging.debug('*** calling kTAMV.getDistance')
        self.space_coordinates = []
        self.camera_coordinates = []
        self.mm_per_pixels = []

        # Setup camera calibration move coordinates
        self.calibrationCoordinates = [ [0,-0.5], [0.294,-0.405], [0.476,-0.155], [0.476,0.155], [0.294,0.405], [0,0.5], [-0.294,0.405], [-0.476,0.155], [-0.476,-0.155], [-0.294,-0.405] ]
        guessPosition  = [1,1]

        try:
            self.pm.ensureHomed()
            # _Request_Result
            _rr = utl.get_nozzle_position(self.server_url, self.reactor)
            
            # If we did not get a response at first querry, abort
            if _rr is None:
                self.gcode.respond_info("Did not find nozzle, aborting")
                return

            # Save the 2D coordinates of where the nozzle is on the camera
            _uv = _rr['position']
            
            # Save size of the image for use in Matrix calculations
            _frame_width = _rr['frame_width']
            _frame_height = _rr['frame_height']

            # Save the position of the nozzle in the as old (move from) value
            _olduv = _uv

            # Save the 3D coordinates of where the nozzle is on the printer in relation to the endstop
            _xy = self.pm.get_gcode_position()

            for i in range(len(self.calibrationCoordinates)):
                # self.gcode.respond_info("Calibrating camera step %s of %s" % (str(i+1), str(len(self.calibrationCoordinates))))

                # # Move to calibration location and get the nozzle position
                _rr, _xy = self.moveRelative_and_getNozzlePosition(self.calibrationCoordinates[i][0], self.calibrationCoordinates[i][1], gcmd)

                # If we did not get a response, skip this calibration point
                if _rr is  None:
                    # Move back to center but do not save the calibration point because it would be the same as the first and double the errors if it is wrong
                    self.pm.moveRelative(X = -self.calibrationCoordinates[i][0], Y = -self.calibrationCoordinates[i][1])
                    continue
                
                # If we did get a response, do the calibration point
                _uv = _rr['position']  # Save the new nozzle position as UV 2D coordinates
                
                # Calculate mm per pixel and save it to a list
                mpp = self.getMMperPixel(self.calibrationCoordinates[i], _olduv, _uv)
                # Save the 3D space coordinates, 2D camera coordinates and mm per pixel to lists for later use
                self._save_coordinates_for_matrix(_xy, _uv, mpp)
                self.gcode.respond_info("MM per pixel for step %s is %s" % (str(i+1), str(mpp)))

                # If this is not the last item
                if i < (len(self.calibrationCoordinates)-1):
                    # gcmd.respond_info("Moving back to starting position= X: %s Y: %s" % (str(-self.calibrationCoordinates[i][0]), str(-self.calibrationCoordinates[i][1])))
                    # Move back to center but do not save the calibration point because it would be the same as the first and double the errors if it is wrong
                    self.pm.moveRelative(X = -self.calibrationCoordinates[i][0], Y = -self.calibrationCoordinates[i][1])

            # 
            # Finish the calibration loop
            # 
            
            # Move back to the center and get coordinates for the center
            gcmd.respond_info("Moving back to starting position")
            _olduv = _uv    # Last position to get center from inverted move
            _rr, _xy = self.moveRelative_and_getNozzlePosition(-self.calibrationCoordinates[i][0], -self.calibrationCoordinates[i][1], gcmd)

            # If we did not get a response, indicate it by setting _uv to None
            if _rr is None:
                _uv = None
            else:
                _uv = _rr['position']  # Save the new nozzle position as UV 2D coordinates

                # Calculate mm per pixel and save it to a list
                mpp = self.getMMperPixel(self.calibrationCoordinates[i], _olduv, _uv)
                # Save the 3D space coordinates, 2D camera coordinates and mm per pixel to lists for later use
                self._save_coordinates_for_matrix(_xy, _uv, mpp)
                self.gcode.respond_info("Calibrated camera center: mm/pixel found: %.4f" % (mpp))

            # 
            # All calibration points are done, calculate the average mm per pixel
            # 
            
            # Check that we have at least 75% of the calibration points
            if (len(self.mm_per_pixels) < (len(self.calibrationCoordinates) * 0.75)):
                raise self.gcode.error("More than 25% of the calibration points failed, aborting")

            # Calculate the average mm per pixel
            gcmd.respond_info("Calculating average mm per pixel")
            self.mpp = self._get_average_mpp_from_lists(gcmd)                

            # Calculate transformation matrix
            self.transform_input = [(self.space_coordinates[i], 
                                     utl.normalize_coords(camera, _frame_width, _frame_height)
                                     ) for i, camera in enumerate(self.camera_coordinates)]

            # TODO: Write a function to call the server in utl.py
            self.transformMatrix, _ = utl.least_square_mapping(self.transform_input)
            
            _current_position = self.pm.get_gcode_position()

            _cx,_cy = utl.normalize_coords(_uv, _frame_width, _frame_height)
            _v = [_cx**2, _cy**2, _cx*_cy, _cx, _cy, 0]
            _offsets = -1*(0.55*self.transformMatrix.T @ _v)
            guessPosition[0] = round(_offsets[0],3) + round(_current_position[0],3)
            guessPosition[1] = round(_offsets[1],3) + round(_current_position[1],3)

            # Move to the new center and get the nozzle position to update the camera
            self.pm.moveAbsolute(X = guessPosition[0], Y = guessPosition[1])
            _rr = utl.get_nozzle_position(self.server_url, self.reactor)

            logging.debug('*** exiting kTAMV.getDistance')

        except Exception as e:
            raise self.gcode.error("_calibrate_px_mm failed %s" % str(e)).with_traceback(e.__traceback__)

    def _calibrate_nozzle(self, gcmd, retries = 30):
        ##############################
        # Calibration of the tool
        ##############################
        logging.debug('*** calling kTAMV._calibrate_Tool')
        _retries = 0
        _not_found_retries = 0
        _uv = [None,None]               # 2D coordinates of where the nozzle is on the camera image
        _xy = [None,None]               # 3D coordinates of where the nozzle is on the printer in relation to the endstop
        _cx = 0                         # Normalized X
        _cy = 0                         # Normalized Y
        _olduv = None                   # 2D coordinates of where the nozzle was last on the camera image
        _pixel_offsets = [None,None]    # Offsets from the center of the camera image to where the nozzle is in pixels
        _frame_width = 0                # Width of the camera image
        _frame_height = 0               # Height of the camera image
        _offsets = [None,None]          # Offsets from the center of the camera image
        _rr = None                      # _Request_Result

        try:
            self.pm.ensureHomed()

            if self.transformMatrix is None:
                raise self.gcode.error("Camera is not calibrated, aborting")
            
            # Loop max 30 times to get the nozzle position
            for _retries in range(retries):
                
                # _Request_Result
                _rr = utl.get_nozzle_position(self.server_url, self.reactor)
                
                # If we did not get a response, try to wiggle the toolhead to find the nozzle 4 times
                if _rr is None:
                    if _not_found_retries > 3:
                        raise self.gcode.error("Did not find nozzle, aborting")
                    self.gcode.respond_info("Did not find nozzle, Will try to wiggle the toolhead to find it")
                    if _not_found_retries == 0:
                        # Wiggle the toolhead to try and find the nozzle
                        self.pm.moveRelative(X = 0.1)
                    elif _not_found_retries == 1:
                        self.pm.moveRelative(X = -0.2)
                    elif _not_found_retries == 2:
                        self.pm.moveRelative(X = 0.1, Y = 0.1)
                    elif _not_found_retries == 3:
                        self.pm.moveRelative(Y = -0.2)
                    _not_found_retries += 1
                    continue
                else:
                    _not_found_retries = 0

                # Save the 2D coordinates of where the nozzle is on the camera
                _uv = _rr['position']
                
                # Save size of the image for use in Matrix calculations
                _frame_width = _rr['frame_width']
                _frame_height = _rr['frame_height']

                # Save the position of the nozzle in the center
                if _olduv is None:
                    _olduv = _uv

                # Save the 3D coordinates of where the nozzle is on the printer in relation to the endstop
                _xy = self.pm.get_gcode_position()

                # Calculate the offset from the center of the camera
                _cx,_cy = utl.normalize_coords(_uv, _frame_width, _frame_height)
                _v = [_cx**2, _cy**2, _cx*_cy, _cx, _cy, 0]
                _offsets = -1*(0.55*self.transformMatrix.T @ _v)
                _offsets[0] = round(_offsets[0],3)
                _offsets[1] = round(_offsets[1],3)

                self.gcode.respond_info('*** Nozzle calibration take: ' + str(_retries) + '.\n X' + str(_xy[0]) + ' Y' + str(_xy[1]) + ' \nUV: ' + str(_uv) + ' old UV: ' + str(_olduv) + ' \nOffsets: ' + str(_offsets))

                # Check if we're not aligned to the center
                if(_offsets[0] != 0.0 or _offsets[1] != 0.0):
                    ##############################
                    # Ensure the next move is within the frame
                    ##############################
                    # Convert the offsets to pixels
                    _pixel_offsets[0] = _offsets[0] / self.mpp
                    _pixel_offsets[1] = _offsets[1] / self.mpp
                    
                    # If the offset added to the current position is outside the frame size, abort
                    if(_pixel_offsets[0] + _uv[0] > _frame_width or _pixel_offsets[1] + _uv[1] > _frame_height or _pixel_offsets[0] + _uv[0] < 0 or _pixel_offsets[1] + _uv[1] < 0):
                        raise self.gcode.error("Calibration failed, offset would move the nozzle outside the frame. This is most likely caused by a bad mm per pixel calibration")
                    
                    ##############################
                    # Move the toolhead to the new position
                    ##############################
                    _olduv = _uv
                    logging.debug('Calibration move X{0:-1.3f} Y{1:-1.3f} F1000 '.format(_offsets[0],_offsets[1]))
                    self.pm.moveRelative(X = _offsets[0], Y = _offsets[1], moveSpeed=1000)
                    continue
                # finally, we're aligned to the center
                elif(_offsets[0] == 0.0 and _offsets[1] == 0.0):
                    self.gcode.respond_info("Calibration to nozzle center complete")
                    return

        except Exception as e:
            logging.exception('_calibrate_nozzle(): self.mpp: ' + str(self.mpp) 
                              +' _pixel_offsets: ' + str(_pixel_offsets) 
                              + ' _uv: ' + str(_uv) 
                              + ' _frame_width: ' + str(_frame_width) 
                              + ' _frame_height: ' + str(_frame_height)
                              + ' _offsets: ' + str(_offsets)
                              + ' _olduv: ' + str(_olduv)
                              + ' _xy: ' + str(_xy)
                              + ' _retries: ' + str(_retries)
                              + ' _not_found_retries: ' + str(_not_found_retries)
                              + ' _rr: ' + str(_rr))
            
            raise self.gcode.error(e).with_traceback(e.__traceback__)

    def getMMperPixel(self, distance_traveled = [], from_camera_point = [], to_camera_point = []):
        logging.debug('*** calling kTAMV.getMMperPixel')
        logging.debug("distance_traveled: %s" % str(distance_traveled))
        logging.debug("from_camera_point: %s" % str(from_camera_point))
        logging.debug("to_camera_point: %s" % str(to_camera_point))
        total_distance_traveled = abs(distance_traveled[0]) + abs(distance_traveled[1])
        logging.debug("total_distance_traveled: %s" % str(total_distance_traveled))
        mpp = round(total_distance_traveled /self.getDistance(from_camera_point[0],from_camera_point[1],to_camera_point[0],to_camera_point[1]),3)
        logging.debug("mm per pixel: %s" % str(mpp))
        logging.debug('*** exiting kTAMV.getMMperPixel')
        return mpp

    def moveRelative_and_getNozzlePosition(self, X, Y, gcmd):    
        # Move to calibration location
        self.pm.moveRelative(X = X, Y = Y)

        # Get the nozzle position
        _request_result = utl.get_nozzle_position(self.server_url, self.reactor)
        
        # If we did not get a response, return None
        if _request_result is None:
            return None, None

        # Save the position of the nozzle on camera at the current location
        _current_position = self.pm.get_gcode_position()
        
        return _request_result, [_current_position[0], _current_position[1]]

    def _save_coordinates_for_matrix(self, space_coordinates, camera_coordinates, mpp):
        # Save the 3D space coordinates and 2D camera coordinates to lists for later use
        self.space_coordinates.append(space_coordinates) # (_xy[0], _xy[1]))
        self.camera_coordinates.append(camera_coordinates) #(_uv[0], _uv[1]))
        self.mm_per_pixels.append(mpp)

    def _get_average_mpp_from_lists(self, gcmd):
        logging.debug('*** calling kTAMV._get_average_mpp_from_lists')
        try:
            mpp, new_mm_per_pixels, new_space_coordinates, new_camera_coordinates = utl.get_average_mpp(self.mm_per_pixels, self.space_coordinates, self.camera_coordinates, gcmd)
            
            # Ensure we got a result and that we have at least 75% of the calibration points
            if mpp is None:
                raise self.gcode.error("Failed to get average mm per pixel")
            elif (len(new_mm_per_pixels) < (len(self.mm_per_pixels) * 0.75)):
                raise self.gcode.error("More than 25% of the calibration points failed, aborting")
            
            self.mm_per_pixels = new_mm_per_pixels
            self.space_coordinates = new_space_coordinates
            self.camera_coordinates = new_camera_coordinates
            
            logging.debug('*** exiting kTAMV._get_average_mpp_from_lists')
            return mpp
        except Exception as e:
            raise self.gcode.error("_get_average_mpp_from_lists failed %s" % str(e)).with_traceback(e.__traceback__)
        
    def getDistance(self, x1, y1, x0, y0):
        logging.debug('*** calling kTAMV.getDistance')
        x1_float = float(x1)
        x0_float = float(x0)
        y1_float = float(y1)
        y0_float = float(y0)
        x_dist = (x1_float - x0_float) ** 2
        y_dist = (y1_float - y0_float) ** 2
        retVal = sqrt((x_dist + y_dist))
        returnVal = round(retVal,3)
        logging.debug('*** exiting kTAMV.getDistance')
        return(returnVal)

def load_config(config):
    return ktamv(config)
