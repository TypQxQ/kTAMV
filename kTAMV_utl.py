# kTAMV Utility Functions
import math, copy, statistics, requests, json, time
import numpy as np
import logging

def get_nozzle_position(server_url, gcmd, reactor):
    _request_id = None
    try:
        _response = json.loads(requests.get(server_url + "/burstNozzleDetection", timeout=2).text)
        if not (_response['statuscode'] == 202 or _response['statuscode'] == 200):
            gcmd.respond_info("Failed to run burstNozzleDetection, got statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))
            raise Exception("Failed to run burstNozzleDetection, got statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))
        
        # Success, got request id
        _request_id = _response['request_id']
        
        start_time = time.time()
        while True:
            #  Check if the request is done
            _response = json.loads(requests.get(f"{server_url}/getReqest?request_id={_request_id}", timeout=2).text)
            if _response['statuscode'] == 202:
                # Check if one minute has elapsed
                elapsed_time = time.time() - start_time
                if elapsed_time >= 60:
                    raise Exception("Nozzle detection kTAMV_SIMPLE_NOZZLE_POSITION timed out after 60 seconds")

                # Pause for 100ms to avoid busy loop
                _ = reactor.pause(reactor.monotonic() + 0.100)
                continue
            # If nozzles were found, return the position
            elif _response['statuscode'] == 200:
                return _response
            # If nozzles were not found, raise exception
            elif _response['statuscode'] == 404:
                raise Exception("Nozzle detection kTAMV_SIMPLE_NOZZLE_POSITION failed, got statuscode %s: %s. Try Cleaning the nozzle or adjust Z height. Verify with the KTAMV_SIMPLE_NOZZLE_POSITION command." % ( str(_response['statuscode']), str(_response['statusmessage'])))
            else:
                raise Exception("Nozzle detection kTAMV_SIMPLE_NOZZLE_POSITION failed, got statuscode %s: %s" % ( str(_response['statuscode']), str(_response['statusmessage'])))

    except Exception as e:
        gcmd.respond_info("_get_nozzle_position failed %s" % str(e))
        # raise e
        return None


def get_average_mpp(mpps : list, space_coordinates : list, camera_coordinates : list, gcmd):
    # send calling to log
    logging.debug('*** calling kTAMV_utl.get_average_mpp')

    # Calculate the average mm per pixel and the standard deviation
    mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)
    
    __mpp_msg = ("Standard deviation of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpps_std_dev), str(mpp), str(np.around((mpps_std_dev / mpp)*100,2)))) + " %."

    # If standard deviation is higher than 10% of the average mm per pixel, try to exclude deviant values and recalculate to get a better average
    if mpps_std_dev / mpp > 0.1:
        gcmd.respond_info("Too high " + __mpp_msg + " Trying to exclude deviant values and recalculate")
        
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

        gcmd.respond_info("Recalculated Standard deviation without deviant max and min of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpps_std_dev), str(mpp), str(np.around((mpps_std_dev / mpp)*100,2))) + " %.")

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

