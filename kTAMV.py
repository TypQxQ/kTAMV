import numpy as np
from . import kTAMV_io, kTAMV_pm, kTAMV_utl as utl
import logging

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
 
        # Initialize variables
        self.mpp = None                 # Average mm per pixel
        self.transformMatrix = None     # Transformation matrix for converting from camera coordinates to space coordinates
        self.space_coordinates = []     # List of space coordinates for each calibration point
        self.camera_coordinates = []    # List of camera coordinates for each calibration point
        self.mm_per_pixels = []         # List of mm per pixel for each calibration point
        self.cp = None                  # Center position used for offset calculations

        # TODO: Change from using the ktcc_log to using the klippy logger
        if not config.has_section('ktcc_log'):
            raise self.printer.config_error("Klipper Toolchanger KTCC addon section not found in config, CVNozzleCalib wont work")

        # Load used objects.
        self.config = config 
        self.printer  = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        # self.gcode_macro : gcode_macro.GCodeMacro = self.printer.load_object(config, 'gcode_macro')
        # self.toollock : ktcc_toolchanger.ktcc_toolchanger = self.printer.lookup_object('ktcc_toolchanger')

        # Register backwords compatibility commands
        self.__currentPosition = {'X': None, 'Y': None, 'Z': None}

        self.printer.register_event_handler("klippy:ready", self.handle_ready)

    def handle_ready(self):
        self.reactor = self.printer.get_reactor()

        self.log = self.printer.lookup_object('ktcc_log')
        self.io = kTAMV_io.kTAMV_io(self.log, self.camera_address, self.server_url, self.save_image)
        self.pm = kTAMV_pm.kTAMV_pm(self.config)

        self.gcode.register_command('KTAMV_TEST', self.cmd_SIMPLE_TEST, desc=self.cmd_SIMPLE_TEST_help)
        self.gcode.register_command('KTAMV_SIMPLE_NOZZLE_POSITION', self.cmd_SIMPLE_NOZZLE_POSITION, desc=self.cmd_SIMPLE_NOZZLE_POSITION_help)
        self.gcode.register_command('KTAMV_CALIB_NOZZLE_PX_MM', self.cmd_CALIB_NOZZLE_PX_MM, desc=self.cmd_CALIB_NOZZLE_PX_MM_help)
        # self.gcode.register_command('KTAMV_CALIB_NOZZLE_OFFSET', self.cmd_CALIB_NOZZLE_OFFSET, desc=self.cmd_CALIB_NOZZLE_OFFSET_help)
        self.gcode.register_command('KTAMV_FIND_NOZZLE_CENTER', self.cmd_FIND_NOZZLE_CENTER, desc=self.cmd_FIND_NOZZLE_CENTER_help)
        self.gcode.register_command('KTAMV_SET_CENTER', self.cmd_SET_CENTER, desc=self.cmd_SET_CENTER_help)
        self.gcode.register_command('KTAMV_GET_OFFSET', self.cmd_GET_OFFSET, desc=self.cmd_GET_OFFSET_help)

    cmd_SET_CENTER_help = "Set current toolhead position as the center position to get offset from"
    def cmd_SET_CENTER(self, gcmd):
        self.cp = self.pm.get_raw_position()
        self.cp = (float(self.cp[0]), float(self.cp[1]))
        gcmd.respond_info("Center position set to X:%3f Y:%3f" % self.cp[0], self.cp[1])
        
    cmd_GET_OFFSET_help = "Get offset from the current position to the configured center position"
    def cmd_GET_OFFSET(self, gcmd):
        if self.cp is None:
            gcmd.respond_info("No center position set, use KTAMV_SET_CENTER to set it to the position you want to get offset from")
            return
        _pos = self.pm.get_raw_position()
        _offset = (float(_pos[0]) - self.cp[0], float(_pos[1]) - self.cp[1])
        gcmd.respond_info("Offset from center is X:%3f Y:%3f" % _offset[0], _offset[1])

    cmd_FIND_NOZZLE_CENTER_help = "Finds the center of the nozzle and moves it to the center of the camera, offset can be set from here"
    def cmd_FIND_NOZZLE_CENTER(self, gcmd):
        self._calibrate_nozzle(gcmd)

    cmd_SIMPLE_TEST_help = "Gets all requests from the server and prints them to the console"
    def cmd_SIMPLE_TEST(self, gcmd):
        self._calibrate_px_mm(gcmd)
        self._calibrate_nozzle(gcmd)
        # response = json.loads(requests.get(self.server_url + "/getAllReqests").text)
        # logging.debug("Response: %s" % str(response))
        # gcmd.respond_info("Response: %s" % str(response))

    def _set_camera_center_to_current_position(self):
        gcode_position = self._get_gcode_position()
        self.camera_position = (float(gcode_position.x), float(gcode_position.y))
        self.log.trace("Set camera position to: %s" % str(self.camera_position))

    cmd_center_toolhead_help = "Positions the current toolhead at the camera nozzle position"
    def cmd_center_toolhead(self, gcmd):
        self._center_toolhead()

    cmd_SIMPLE_NOZZLE_POSITION_help = "Detects if a nozzle is found in the current image"
    def cmd_SIMPLE_NOZZLE_POSITION(self, gcmd):
        try:
            canread = self.io.can_read_stream(self.printer)
            logging.debug("Can read stream: %s" % str(canread))
            gcmd.respond_info("Can read stream: %s" % str(canread))
            if not canread:
                return None

            _response = utl.get_nozzle_position(self.server_url, gcmd, self.reactor)
            if _response is None:
                return
            else:
                gcmd.respond_info("Found nozzle at position: %s after %.2f seconds" % (str(_response['position']), float(_response['runtime'])))
        except Exception as e:
            gcmd.respond_info("Failed to run burstNozzleDetection, got error: %s" % str(e))
            return


    cmd_CALIB_NOZZLE_PX_MM_help = "Calibrates the movement of the active nozzle around the point it started at"
    def cmd_CALIB_NOZZLE_PX_MM(self, gcmd):
        gcmd.respond_info("Starting mm/px calibration")
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
            _rr = utl.get_nozzle_position(self.server_url, gcmd, self.reactor)
            
            # If we did not get a response at first querry, abort
            if _rr is None:
                gcmd.respond_info("Did not find nozzle, aborting")
                return

            # Save the 2D coordinates of where the nozzle is on the camera
            _uv = _rr['position']
            
            # Save size of the image for use in Matrix calculations
            _frame_width = _rr['frame_width']
            _frame_height = _rr['frame_height']

            # Save the position of the nozzle in the center
            _olduv = _uv

            # Save the 3D coordinates of where the nozzle is on the printer in relation to the endstop
            _xy = self.pm.get_gcode_position()

            for i in range(len(self.calibrationCoordinates)):
                gcmd.respond_info("Calibrating camera step %s of %s" % (str(i+1), str(len(self.calibrationCoordinates))))

                # # Move to calibration location and get the nozzle position
                _rr, _xy = self.moveRelative_getNozzlePosition(self.calibrationCoordinates[i][0], self.calibrationCoordinates[i][1], gcmd)

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
                gcmd.respond_info("MM per pixel for step %s is %s" % (str(i+1), str(mpp)))

                # If this is not the last item
                if i != (len(self.calibrationCoordinates)-1):
                    # Move back to center but do not save the calibration point because it would be the same as the first and double the errors if it is wrong
                    self.pm.moveRelative(X = -self.calibrationCoordinates[i][0], Y = -self.calibrationCoordinates[i][1])
                # If this is the last calibration point, move to the new center and get the nozzle position to update the camera
                else:
                    _olduv = _uv    # Last position to get center from inverted move
                    # # Move to calibration location and get the nozzle position
                    _rr, _xy = self.moveRelative_getNozzlePosition(self.calibrationCoordinates[i][0], self.calibrationCoordinates[i][1], gcmd)
                    # If we did not get a response, skip this calibration point
                    if _rr is  None:
                        break   # This was the last thing to do, so just break out of the loop
                    
                    # If we did get a response, do the calibration point
                    _uv = _rr['position']  # Save the new nozzle position as UV 2D coordinates
                    
                    # Calculate mm per pixel and save it to a list
                    mpp = self.getMMperPixel(self.calibrationCoordinates[i], _olduv, _uv)
                    # Save the 3D space coordinates, 2D camera coordinates and mm per pixel to lists for later use
                    self._save_coordinates_for_matrix(_xy, _uv, mpp)
                    gcmd.respond_info("MM per pixel for step %s is %s" % (str(i+1), str(mpp)))

            # Check that we have at least 75% of the calibration points
            if (len(self.mm_per_pixels) < (len(self.calibrationCoordinates) * 0.75)):
                gcmd.respond_info("More than 25% of the calibration points failed, aborting")
                return

            # Calculate the average mm per pixel
            mpp = self._get_average_mpp_from_lists(gcmd)                
            # mpp = utl.get_average_mpp(self.mm_per_pixels, gcmd)
            if mpp is None:
                gcmd.respond_info("Failed to get average mm per pixel")
                return

            # Calculate transformation matrix
            self.transform_input = [(self.space_coordinates[i], 
                                     utl.normalize_coords(camera, _frame_width, _frame_height)
                                     ) for i, camera in enumerate(self.camera_coordinates)]
            self.transformMatrix, _ = utl.least_square_mapping(self.transform_input)
            
            # define camera center in machine coordinate space
            self.newCenter = self.transformMatrix.T @ np.array([0, 0, 0, 0, 0, 1])
            guessPosition[0]= np.around(self.newCenter[0],3)
            guessPosition[1]= np.around(self.newCenter[1],3)
            logging.info('Calibration positional guess: ' + str(guessPosition))
            gcmd.respond_info("Calibration positional guess: " + str(guessPosition))

            # Move to the new center and get the nozzle position to update the camera
            self.pm.moveAbsolute(X = guessPosition[0], Y = guessPosition[1])
            _rr = utl.get_nozzle_position(self.server_url, gcmd, self.reactor)

            logging.debug('*** exiting kTAMV.getDistance')

        except Exception as e:
            logging.exception('Error: kTAMV.getDistance cannot run: ' + str(e))
            gcmd.respond_info("_calibrate_px_mm failed %s" % str(e))
            # raise e
            return None

    def _calibrate_nozzle(self, gcmd, retries = 30):
        ##############################
        # Calibration of the tool
        ##############################
        logging.debug('*** calling kTAMV._calibrate_Tool')
        _not_found_retries = 0
        _olduv = None

        try:
            self.pm.ensureHomed()
            
            # Loop max 30 times to get the nozzle position
            for _retries in range(retries):
                # _Request_Result
                _rr = utl.get_nozzle_position(self.server_url, gcmd, self.reactor)
                
                # If we did not get a response, try to wiggle the toolhead to find the nozzle 4 times
                if _rr is None:
                    if _not_found_retries > 3:
                        gcmd.respond_info("Did not find nozzle, aborting")
                        return
                    gcmd.respond_info("Did not find nozzle, Will try to wiggle the toolhead to find it")
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
                _offsets[0] = np.around(_offsets[0],3)
                _offsets[1] = np.around(_offsets[1],3)

                gcmd.respond_info('*** Nozzle calibration take: ' + str(_retries) + '.\n X' + str(_xy[0]) + ' Y' + str(_xy[1]) + ' \nUV: ' + str(_uv) + ' old UV: ' + str(_olduv) + ' \nOffsets: ' + str(_offsets))

                # Check if we're not aligned to the center
                if(_offsets[0] != 0.0 or _offsets[1] != 0.0):
                    _olduv = _uv
                    logging.debug('Calibration move X{0:-1.3f} Y{1:-1.3f} F1000 '.format(_offsets[0],_offsets[1]))
                    # gcmd.respond_info('Calibration move X{0:-1.3f} Y{1:-1.3f} F1000 '.format(_offsets[0],_offsets[1]))
                    self.pm.moveRelative(X = _offsets[0], Y = _offsets[1], moveSpeed=1000)
                    continue
                # finally, we're aligned to the center
                elif(_offsets[0] == 0.0 and _offsets[1] == 0.0):
                    gcmd.respond_info("Calibration to nozzle center complete")
                    return

        except Exception as e:
            gcmd.respond_info("_calibrate_nozzle failed %s" % str(e))
            return None

    def getMMperPixel(self, distance_traveled = [], from_camera_point = [], to_camera_point = []):
        logging.debug('*** calling kTAMV.getMMperPixel')
        logging.debug("distance_traveled: %s" % str(distance_traveled))
        logging.debug("from_camera_point: %s" % str(from_camera_point))
        logging.debug("to_camera_point: %s" % str(to_camera_point))
        total_distance_traveled = abs(distance_traveled[0]) + abs(distance_traveled[1])
        logging.debug("total_distance_traveled: %s" % str(total_distance_traveled))
        mpp = np.around(total_distance_traveled /self.getDistance(from_camera_point[0],from_camera_point[1],to_camera_point[0],to_camera_point[1]),3)
        logging.debug("mm per pixel: %s" % str(mpp))
        logging.debug('*** exiting kTAMV.getMMperPixel')
        return mpp

    def moveRelative_getNozzlePosition(self, X, Y, gcmd):    
        # Move to calibration location
        self.pm.moveRelative(X = X, Y = Y)

        # Get the nozzle position
        _request_result = utl.get_nozzle_position(self.server_url, gcmd, self.reactor)
        
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
            if (len(new_mm_per_pixels) < (len(self.mm_per_pixels) * 0.75)):
                gcmd.respond_info("More than 25% of the calibration points failed, aborting")
                return None
            
            self.mm_per_pixels = new_mm_per_pixels
            self.space_coordinates = new_space_coordinates
            self.camera_coordinates = new_camera_coordinates
            
            logging.debug('*** exiting kTAMV._get_average_mpp_from_lists')
            return mpp
        except Exception as e:
            gcmd.respond_info("_get_average_mpp_from_lists failed %s" % str(e))
            return None
        
    def getDistance(self, x1, y1, x0, y0):
        logging.debug('*** calling kTAMV.getDistance')
        x1_float = float(x1)
        x0_float = float(x0)
        y1_float = float(y1)
        y0_float = float(y0)
        x_dist = (x1_float - x0_float) ** 2
        y_dist = (y1_float - y0_float) ** 2
        retVal = np.sqrt((x_dist + y_dist))
        returnVal = np.around(retVal,3)
        logging.debug('*** exiting kTAMV.getDistance')
        return(returnVal)

def load_config(config):
    return kTAMV(config)
