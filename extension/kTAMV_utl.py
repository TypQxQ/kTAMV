# kTAMV Utility Functions
import math, copy, statistics, requests, json, time
import numpy as np
import logging

def get_nozzle_position(server_url, reactor):
    ##############################
    # Get nozzle position
    ##############################
    logging.debug("*** calling kTAMV_utl.get_nozzle_position")
    _request_id = None

    _response = json.loads(requests.get(server_url + "/burstNozzleDetection", timeout=2).text)
    if not (_response['statuscode'] == 202 or _response['statuscode'] == 200):
        raise Exception("When starting to look for nozzle, server sent statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))
    
    # Success, got response
    _request_id = _response['request_id']
    
    start_time = time.time()
    while True:
        #  Check if the request is done
        _response = json.loads(requests.get(f"{server_url}/getReqest?request_id={_request_id}", timeout=2).text)
        if _response['statuscode'] == 202:
            # Check if one minute has elapsed
            elapsed_time = time.time() - start_time
            if elapsed_time >= 60:
                raise Exception("Nozzle detection timed out after 60 seconds, Server still looking for nozzle.")

            # Pause for 100ms to avoid busy loop
            _ = reactor.pause(reactor.monotonic() + 0.100)
            continue
        # If nozzles were found, return the position
        elif _response['statuscode'] == 200:
            logging.debug("*** exiting kTAMV_utl.get_nozzle_position")
            return _response
        # If nozzles were not found, raise exception
        elif _response['statuscode'] == 404:
            raise Exception("Server did not find nozzle, found, got statuscode %s: %s. Try Cleaning the nozzle or adjust Z height. Verify with the KTAMV_SIMPLE_NOZZLE_POSITION command." % ( str(_response['statuscode']), str(_response['statusmessage'])))
        else:
            raise Exception("Server nozzle detection failed, got statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))



def get_average_mpp(mpps : list, space_coordinates : list, camera_coordinates : list, gcmd):
    # send calling to log
    logging.debug('*** calling kTAMV_utl.get_average_mpp')

    try:
        # Calculate the average mm per pixel and the standard deviation
        mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)
        
        __mpp_msg = ("Standard deviation of mm/pixel is %s for a calculated mm/pixel of %s. \nPossible deviation of %s" % (str(mpps_std_dev), str(mpp), str(np.around((mpps_std_dev / mpp)*100,2)))) + " %."

        # If standard deviation is higher than 10% of the average mm per pixel, try to exclude deviant values and recalculate to get a better average
        if mpps_std_dev / mpp > 0.1:
            gcmd.respond_info(__mpp_msg + "\nTrying to exclude deviant values and recalculate")
            
            # ----------------- 1st recalculation -----------------
            # Exclude the highest value if it deviates more than 20% from the mean value and recalculate. This is the most likely to be a deviant value
            if max(mpps) > mpp + (mpp * 0.20):
                __max_index = mpps.index(max(mpps))
                mpps.remove(mpps[__max_index])
                space_coordinates.remove(space_coordinates[__max_index])
                camera_coordinates.remove(camera_coordinates[__max_index])
            
            # Calculate the average mm per pixel and the standard deviation
            mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

            # ----------------- 2nd recalculation -----------------
            # Exclude the lowest value if it deviates more than 20% from the mean value and recalculate
            if min(mpps) < mpp - (mpp * 0.20):
                __min_index = mpps.index(min(mpps))
                mpps.remove(mpps[__min_index])
                space_coordinates.remove(space_coordinates[__min_index])
                camera_coordinates.remove(camera_coordinates[__min_index])
                
            # Calculate the average mm per pixel and the standard deviation
            mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

            gcmd.respond.info("Recalculated std. dev. of mm/pixel is %s for a calculated mm/pixel of %s. \nPossible deviation of %s" % (str(mpps_std_dev), str(mpp), str(np.around((mpps_std_dev / mpp)*100,2)))) + " %."

            # ----------------- 3rd recalculation -----------------
            # Exclude the values that are more than 2 standard deviations from the mean and recalculate
            for i in reversed(range(len(list(mpps)))):
                if mpps[i] > mpp + (mpps_std_dev * 2) or mpps[i] < mpp - (mpps_std_dev * 2):
                    mpps.remove(mpps[i])
                    space_coordinates.remove(space_coordinates[i])
                    camera_coordinates.remove(camera_coordinates[i])

            # Calculate the average mm per pixel and the standard deviation
            mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

            # ----------------- 4th recalculation -----------------
            # Exclude any other value that deviates more than 25% from mean value and recalculate
            for i in reversed(range(len(mpps))):
                if mpps[i] > mpp + (mpp * 0.5) or mpps[i] < mpp - (mpp * 0.5):
                    logging.log("Removing value %s from list" % str(mpps[i]))
                    mpps.remove(mpps[i])
                
            # Calculate the average mm per pixel and the standard deviation
            mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

            # Final check if standard deviation is still too high
            gcmd.respond_info("Final recalculated standard deviation of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpps_std_dev), str(mpp), str(np.around((mpps_std_dev / mpp)*100,2))) + " %.")
            gcmd.respond_info("Final recalculated mm per pixel is calculated from %s values" % str(len(mpps)))

            if mpps_std_dev / mpp > 0.2 or len(mpps) < 5:
                gcmd.respond_info("Standard deviation is still too high. Calibration failed.")
                return None
            else:
                gcmd.respond_info("Standard deviation is now within acceptable range. Calibration succeeded.")
                logging.debug("Average mm per pixel: %s with a standard deviation of %s" % (str(mpp), str(mpps_std_dev)))
        else:
            gcmd.respond_info(__mpp_msg)

        # send exiting to log
        logging.debug('*** exiting kTAMV_utl.get_average_mpp')

        return mpp, mpps, space_coordinates, camera_coordinates
    except Exception as e:
        raise e.with_traceback(e.__traceback__)

def _get_std_dev_and_mean(mpps : list):
    # Calculate the average mm per pixel and the standard deviation
    mpps_std_dev = statistics.stdev(mpps)
    mpp = np.around(np.mean(mpps),3)
    return mpps_std_dev, mpp

def normalize_coords(coords, frame_width, frame_height):
    xdim, ydim = frame_width, frame_height
    returnValue = (coords[0] / xdim - 0.5, coords[1] / ydim - 0.5)
    return(returnValue)

def least_square_mapping(calibration_points):
    # Compute a 2x2 map from displacement vectors in screen space to real space.
    n = len(calibration_points)
    real_coords, pixel_coords = np.empty((n,2)),np.empty((n,2))
    for i, (r,p) in enumerate(calibration_points):
        real_coords[i] = r
        pixel_coords[i] = p
    x,y = pixel_coords[:,0],pixel_coords[:,1]
    A = np.vstack([x**2,y**2,x * y, x,y,np.ones(n)]).T
    transform = np.linalg.lstsq(A, real_coords, rcond = None)
    return transform[0], transform[1].mean()


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
        logging.debug('Current absolute position: ' + str(_current_position))
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
            raise e.with_traceback(e.__traceback__)
            
        # send exiting to log
        logging.debug('*** exiting kTAMV_pm.moveRelative')

    def moveRelativeToArray(self, pos_array, moveSpeed=__defaultSpeed, protected=False):
        self.moveRelative(pos_array[0], pos_array[1], pos_array[2], moveSpeed, protected)

    # Move one axis at a time to the position.
    def complexMoveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed):
        self.moveRelative(X, Y, Z, moveSpeed, True)

    # Using G1 command to move the toolhead to the position instead of using the toolhead.move() function because G1 will use the tool's offset.
    def moveAbsoluteToArray(self, pos_array, moveSpeed=__defaultSpeed):
        gcode = "G1 "
        for i in range(len(pos_array)):
            debug = "moveAbsoluteToArray pos_array[%s] = %s" % (i, pos_array[i])
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
        self.moveAbsoluteToArray([X, Y, Z], moveSpeed)
        
    def get_gcode_position(self):
        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_position = gcode_move.get_status()['gcode_position']
        
        return [gcode_position.x, gcode_position.y, gcode_position.z]

    def get_raw_position(self):
        gcode_move = self.printer.lookup_object('gcode_move')
        raw_position = gcode_move.get_status()['position']
        
        return [raw_position.x, raw_position.y, raw_position.z]
