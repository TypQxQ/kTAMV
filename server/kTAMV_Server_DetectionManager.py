import logging, copy, io, datetime, time, os, requests, cv2, numpy as np
from requests.exceptions import InvalidURL, HTTPError, RequestException, ConnectionError
from PIL import Image, ImageDraw, ImageFont, ImageFile

import kTAMV_Server_io, kTAMV_Server


class kTAMV_DetectionManager:
    uv = [None, None]
    __nozzleAutoDetectionActive = False
    __uv = None
    __algorithm = None
    __io = None
    
    ##### Setup functions
    # init function
    def __init__(self, camera_url, *args, **kwargs):
        # send calling to log
        
        logging.debug('*** calling DetectionManager.__init__')

        # This are the variables that will be used to store the calibration points.
        self.uv = [None, None]
        
        # The already initialized io object.
        self.__io = kTAMV_Server_io.kTAMV_io(camera_url=camera_url, save_image=False)
        
        # This is the last successful algorithm used by the nozzle detection. Should be reset at tool change. Will have to change.
        self.__algorithm = None

        # TAMV has 2 detectors, one for standard and one for relaxed
        self.createDetectors()

        # send exiting to log
        logging.debug('*** exiting DetectionManager.__init__')

    # timeout = 20: If no nozzle found in this time, timeout the function
    # min_matches = 3: Minimum amount of matches to confirm toolhead position after a move
    # xy_tolerance = 1: If the nozzle position is within this tolerance, it's considered a match. 1.0 would be 1 pixel. Only whole numbers are supported.
    # put_frame_func: Function to put the frame into the main program
    def recursively_find_nozzle_position(self, put_frame_func, request_id, min_matches=3, timeout=20, xy_tolerance=1):
        start_time = time.time()  # Get the current time
        last_pos = (0,0)
        pos_matches = 0
        pos = None

        while time.time() - start_time < timeout:
            positions = self._burstNozzleDetection(put_frame_func)

            # positions = self._find_nozzle_positions()
            if positions is None or len(positions) == 0:
                continue

            pos = positions
            # Only compare XY position, not radius...
            if abs(pos[0] - last_pos[0]) <= xy_tolerance and abs(pos[1] - last_pos[1]) <= xy_tolerance:
                pos_matches += 1
                if pos_matches >= min_matches:
                    logging.debug("recursively_find_nozzle_position found %i matches and returning" % pos_matches) 
                    return pos
            else:
                logging.debug("Position found does not match last position. Last position: %s, current position: %s" % (str(last_pos), str(pos)))   
                logging.debug("Difference: X%.3f Y%.3f" % (abs(pos[0] - last_pos[0]), abs(pos[1] - last_pos[1])))
                pos_matches = 0

            last_pos = pos
        logging.debug("recursively_find_nozzle_position found: %s" % str(last_pos))
        return pos

    # This gets the nozzle position from the camera, taking the average position of a couple of images.
    def _burstNozzleDetection(self, put_frame_func, min_matches=3):
        detectionCount = 0
        uv = [None, None]
        average_location=[0,0]
        retries = 0

        # Open the stream
        self.__io.open_stream()
        while(detectionCount < min_matches):
            frame = self.__io.get_single_frame()
            uv, processed_frame = self.nozzleDetection(frame)
            if frame is not None:
                put_frame_func(processed_frame)
            if(uv is not None):
                if(uv[0] is not None and uv[1] is not None):
                    average_location[0] += uv[0]
                    average_location[1] += uv[1]
                    detectionCount += 1
                else:
                    retries += 1
            else:
                retries += 1
            if(retries > 5):
                average_location[0] = None
                average_location[1] = None
                break

        # Close the stream
        self.__io.close_stream()

        if(average_location[0] is not None):
            # calculate average X Y position from detection
            average_location[0] = average_location[0] / detectionCount
            average_location[1] = average_location[1] / detectionCount
            # round to 0 decimal places
            average_location = np.around(average_location,0)
            uv = average_location
            logging.debug("_burstNozzleDetection at: %s" % str(uv))
        else:
            uv = None
            logging.debug("Nozzle detection failed.")
        return(uv)

# ----------------- TAMV Nozzle Detection as tested in kTAMV_cv -----------------

    def createDetectors(self):
        # Standard Parameters
        if(True):
            self.standardParams = cv2.SimpleBlobDetector_Params()
            # Thresholds
            self.standardParams.minThreshold = 1
            self.standardParams.maxThreshold = 50
            self.standardParams.thresholdStep = 1
            # Area
            self.standardParams.filterByArea = True
            self.standardParams.minArea = 400
            self.standardParams.maxArea = 900
            # Circularity
            self.standardParams.filterByCircularity = True
            self.standardParams.minCircularity = 0.8
            self.standardParams.maxCircularity= 1
            # Convexity
            self.standardParams.filterByConvexity = True
            self.standardParams.minConvexity = 0.3
            self.standardParams.maxConvexity = 1
            # Inertia
            self.standardParams.filterByInertia = True
            self.standardParams.minInertiaRatio = 0.3

        # Relaxed Parameters
        if(True):
            self.relaxedParams = cv2.SimpleBlobDetector_Params()
            # Thresholds
            self.relaxedParams.minThreshold = 1
            self.relaxedParams.maxThreshold = 50
            self.relaxedParams.thresholdStep = 1
            # Area
            self.relaxedParams.filterByArea = True
            self.relaxedParams.minArea = 600
            self.relaxedParams.maxArea = 15000
            # Circularity
            self.relaxedParams.filterByCircularity = True
            self.relaxedParams.minCircularity = 0.6
            self.relaxedParams.maxCircularity= 1
            # Convexity
            self.relaxedParams.filterByConvexity = True
            self.relaxedParams.minConvexity = 0.1
            self.relaxedParams.maxConvexity = 1
            # Inertia
            self.relaxedParams.filterByInertia = True
            self.relaxedParams.minInertiaRatio = 0.3

        # Super Relaxed Parameters
            t1=20
            t2=200
            all=0.5
            area=200
            
            self.superRelaxedParams = cv2.SimpleBlobDetector_Params()
        
            self.superRelaxedParams.minThreshold = t1
            self.superRelaxedParams.maxThreshold = t2
            
            self.superRelaxedParams.filterByArea = True
            self.superRelaxedParams.minArea = area
            
            self.superRelaxedParams.filterByCircularity = True
            self.superRelaxedParams.minCircularity = all
            
            self.superRelaxedParams.filterByConvexity = True
            self.superRelaxedParams.minConvexity = all
            
            self.superRelaxedParams.filterByInertia = True
            self.superRelaxedParams.minInertiaRatio = all
            
            self.superRelaxedParams.filterByColor = False

            self.superRelaxedParams.minDistBetweenBlobs = 2
            
        # Create 3 detectors
        self.detector = cv2.SimpleBlobDetector_create(self.standardParams)
        self.relaxedDetector = cv2.SimpleBlobDetector_create(self.relaxedParams)
        self.superRelaxedDetector = cv2.SimpleBlobDetector_create(self.superRelaxedParams)

    def nozzleDetection(self, image):
        # working frame object
        nozzleDetectFrame = copy.deepcopy(image)
        # return value for keypoints
        keypoints = None
        center = (None, None)
        # check which algorithm worked previously
        if 1==1: #(self.__algorithm is None):
            preprocessorImage0 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=0)
            preprocessorImage1 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=1)
            preprocessorImage2 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=2)

            # apply combo 1 (standard detector, preprocessor 0)
            keypoints = self.detector.detect(preprocessorImage0)
            keypointColor = (0,0,255)
            if(len(keypoints) != 1):
                # apply combo 2 (standard detector, preprocessor 1)
                keypoints = self.detector.detect(preprocessorImage1)
                keypointColor = (0,255,0)
                if(len(keypoints) != 1):
                    # apply combo 3 (relaxed detector, preprocessor 0)
                    keypoints = self.relaxedDetector.detect(preprocessorImage0)
                    keypointColor = (255,0,0)
                    if(len(keypoints) != 1):
                        # apply combo 4 (relaxed detector, preprocessor 1)
                        keypoints = self.relaxedDetector.detect(preprocessorImage1)
                        keypointColor = (39,127,255)

                        if(len(keypoints) != 1):
                            # apply combo 5 (superrelaxed detector, preprocessor 2)
                            keypoints = self.superRelaxedDetector.detect(preprocessorImage2)
                            keypointColor = (39,255,127)
                            if(len(keypoints) != 1):
                                # failed to detect a nozzle, correct return value object
                                keypoints = None
                            else:
                                self.__algorithm = 5
                        else:
                            self.__algorithm = 4
                    else:
                        self.__algorithm = 3
                else:
                    self.__algorithm = 2
            else:
                self.__algorithm = 1
        elif(self.__algorithm == 1):
            preprocessorImage0 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=0)
            keypoints = self.detector.detect(preprocessorImage0)
            keypointColor = (0,0,255)
        elif(self.__algorithm == 2):
            preprocessorImage1 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=1)
            keypoints = self.detector.detect(preprocessorImage1)
            keypointColor = (0,255,0)
        elif(self.__algorithm == 3):
            preprocessorImage0 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=0)
            keypoints = self.relaxedDetector.detect(preprocessorImage0)
            keypointColor = (255,0,0)
        else:
            preprocessorImage1 = self.preprocessImage(frameInput=nozzleDetectFrame, algorithm=1)
            keypoints = self.relaxedDetector.detect(preprocessorImage1)
            keypointColor = (39,127,255)
            
        if keypoints is not None:
            logging.debug("Nozzle detected %i circles with algorithm: %s" % (len(keypoints), str(self.__algorithm)))
        else:
            logging.debug("Nozzle detection failed.")
            
            
        # process keypoint
        if(keypoints is not None and len(keypoints) >= 1):
            # create center object
            (x,y) = np.around(keypoints[0].pt)
            x,y = int(x), int(y)
            center = (x,y)
            # create radius object
            keypointRadius = np.around(keypoints[0].size/2)
            keypointRadius = int(keypointRadius)
            circleFrame = cv2.circle(img=nozzleDetectFrame, center=center, radius=keypointRadius,color=keypointColor,thickness=-1,lineType=cv2.LINE_AA)
            nozzleDetectFrame = cv2.addWeighted(circleFrame, 0.4, nozzleDetectFrame, 0.6, 0)
            nozzleDetectFrame = cv2.circle(img=nozzleDetectFrame, center=center, radius=keypointRadius, color=(0,0,0), thickness=1,lineType=cv2.LINE_AA)
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (x-5,y), (x+5, y), (255,255,255), 2)
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (x,y-5), (x, y+5), (255,255,255), 2)
        elif(self.__nozzleAutoDetectionActive is True):
            # no keypoints, draw a 3 outline circle in the middle of the frame
            keypointRadius = 17
            nozzleDetectFrame = cv2.circle(img=nozzleDetectFrame, center=(320,240), radius=keypointRadius, color=(0,0,0), thickness=3,lineType=cv2.LINE_AA)
            nozzleDetectFrame = cv2.circle(img=nozzleDetectFrame, center=(320,240), radius=keypointRadius+1, color=(0,0,255), thickness=1,lineType=cv2.LINE_AA)
            center = (None, None)
        # draw crosshair
        nozzleDetectFrame = cv2.line(nozzleDetectFrame, (320,0), (320,480), (0,0,0), 2)
        nozzleDetectFrame = cv2.line(nozzleDetectFrame, (0,240), (640,240), (0,0,0), 2)
        nozzleDetectFrame = cv2.line(nozzleDetectFrame, (320,0), (320,480), (255,255,255), 1)
        nozzleDetectFrame = cv2.line(nozzleDetectFrame, (0,240), (640,240), (255,255,255), 1)

        # return(center, nozzleDetectFrame)
        return(center, nozzleDetectFrame)

    # Image detection preprocessors
    def preprocessImage(self, frameInput, algorithm=0):
        try:
            outputFrame = self.adjust_gamma(image=frameInput, gamma=1.2)
            height, width, channels = outputFrame.shape
        except: outputFrame = copy.deepcopy(frameInput)
        if(algorithm == 0):
            yuv = cv2.cvtColor(outputFrame, cv2.COLOR_BGR2YUV)
            yuvPlanes = cv2.split(yuv)
            yuvPlanes_0 = cv2.GaussianBlur(yuvPlanes[0],(7,7),6)
            yuvPlanes_0 = cv2.adaptiveThreshold(yuvPlanes_0,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY,35,1)
            outputFrame = cv2.cvtColor(yuvPlanes_0,cv2.COLOR_GRAY2BGR)
        elif(algorithm == 1):
            outputFrame = cv2.cvtColor(outputFrame, cv2.COLOR_BGR2GRAY )
            thr_val, outputFrame = cv2.threshold(outputFrame, 127, 255, cv2.THRESH_BINARY|cv2.THRESH_TRIANGLE )
            outputFrame = cv2.GaussianBlur( outputFrame, (7,7), 6 )
            outputFrame = cv2.cvtColor( outputFrame, cv2.COLOR_GRAY2BGR )
        elif(algorithm == 2):
            gray = cv2.cvtColor(frameInput, cv2.COLOR_BGR2GRAY)
            outputFrame = cv2.medianBlur(gray, 5)

        return(outputFrame)

    def adjust_gamma(self, image, gamma=1.2):
        # build a lookup table mapping the pixel values [0, 255] to
        # their adjusted gamma values
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype( 'uint8' )
        # apply gamma correction using the lookup table
        return cv2.LUT(image, table)















# -----------------------------------------------------------
# From the TAMV main program
# -----------------------------------------------------------

    def getDistance(self, x1, y1, x0, y0):
        logging.debug('*** calling CalibrateNozzles.getDistance')
        x1_float = float(x1)
        x0_float = float(x0)
        y1_float = float(y1)
        y0_float = float(y0)
        x_dist = (x1_float - x0_float) ** 2
        y_dist = (y1_float - y0_float) ** 2
        retVal = np.sqrt((x_dist + y_dist))
        returnVal = np.around(retVal,3)
        logging.debug('*** exiting CalibrateNozzles.getDistance')
        return(returnVal)

    def normalize_coords(self,coords):
        xdim, ydim = self._cameraWidth, self._cameraHeight
        returnValue = (coords[0] / xdim - 0.5, coords[1] / ydim - 0.5)
        return(returnValue)

    def least_square_mapping(self,calibration_points):
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

