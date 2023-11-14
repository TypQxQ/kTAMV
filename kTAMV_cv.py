import math, copy
import cv2
import numpy as np
from requests.exceptions import InvalidURL, HTTPError, RequestException, ConnectionError
# from PIL import Image, ImageDraw, ImageFont, ImageFile
from . import kTAMV_io

class kTAMV_cv:
    def __init__(self, config, io : kTAMV_io):
        # Load used objects. Mainly to log stuff.
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.log = self.printer.load_object(config, 'ktcc_log')
        
        self.io : kTAMV_io.kTAMV_io = io
 
        # This is the last successful algorithm used by the nozzle detection. Should be reset at tool change. Will have to change.
        self.__algorithm = None
        # TAMV has 2 detectors, one for standard and one for relaxed
        self.createDetectors()

    def get_average_positions(self, positions):
        avg_positions = {}
        for position in positions:
            mm_positions = positions[position]
            transposed = zip(*mm_positions)
            averages = [np.mean(col) for col in transposed]
            avg_positions[position] = averages
        return avg_positions

    def calculate_px_to_mm(self, positions, center_point):
        mm_center_point = (center_point[0], center_point[1])
        px_center_point = (positions[mm_center_point][0], positions[mm_center_point][1])

        px_mm_calibs = []
        for key in positions:
            if key == mm_center_point:
                continue
            position = positions[key]

            px_distance = self.get_distance((position[0], position[1]), px_center_point)
            mm_distance = self.get_distance((key[0], key[1]), mm_center_point)

            px_mm_calibs.append((px_distance / mm_distance))

        avg = (sum(px_mm_calibs)/len(px_mm_calibs))
        return avg

    def get_distance(self, p1, p2):
        return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

    def get_center_point_deviation(self, positions):
        center_min = np.min(positions, axis=0)
        center_max = np.max(positions, axis=0)
        return (center_max[0]-center_min[0], center_max[1]-center_min[1])

    def positions_dict_to_string(self, dictionary):
        string = ""
        for key, value in dictionary.items():
            string += f"X{key[0]} Y{key[1]}:\n"
            for val in value:
                string += f"  X{val[0]} Y{val[1]} r{val[2]}\n"
        return string

    def get_edge_point(self, positions, edge):
        points_np = np.array(list(positions.keys()))

        x_median = np.median(points_np[:,0])
        y_median = np.median(points_np[:,1])
        if edge == 'left':
            min_x = np.min(points_np[:,0])
            return (min_x, y_median)
        if edge == 'right':
            max_x = np.max(points_np[:,0])
            return (max_x, y_median)
        if edge == 'top':
            min_y = np.min(points_np[:,1])
            return (x_median, min_y)
        if edge == 'bottom':
            max_y = np.max(points_np[:,1])
            return (x_median, max_y)
        if edge == 'center':
            return (x_median, y_median)
        return None

    def rotate_around_origin(self, origin, point, angle):
            """
            Rotate a point around a given origin by a given angle.

            Args:
                origin (tuple): The origin point as a tuple of (x, y) coordinates.
                point (tuple): The point to be rotated as a tuple of (x, y) coordinates.
                angle (float): The angle of rotation in radians.

            Returns:
                tuple: The rotated point as a tuple of (x, y) coordinates.
            """
            ox, oy = (int(origin[0]), int(origin[1]))
            px, py = (int(point[0]), int(point[1]))

            qx = ox + math.cos(angle) * (px - ox) - math.sin(angle) * (py - oy)
            qy = oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)
            return qx, qy
    
    def detect_nozzles(self, image):
        
        keypoints, nozzleDetectFrame = self.nozzleDetection(image)

        if (keypoints is None):
            return None

        if len(keypoints) < 1:
            return None

        data = []
        for point in keypoints:
            pos = np.around(point.pt)
            r = np.around(point.size/2) # Radius of the detected nozzle
            data.append((pos[0], pos[1], r))

        # self.save_image(nozzleDetectFrame, keypoints)
        self.io.output_image(nozzleDetectFrame, keypoints)
        
        return data

    def slope(self, p1, p2):
        a1 = p2[1]-p1[1]
        a2 = p2[0]-p1[0]
        if a1 == 0:
            return a2
        if a2 == 0:
            return a1
        return a1/a2

    def angle(self,  s1, s2):
        return math.degrees(math.atan((s2-s1)/(1+(s2*s1))))

# ----------------- TAMV Nozzle Detection -----------------

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
            self.log.trace("Nozzle detected %i circles with algorithm: %s" % (len(keypoints), str(self.__algorithm)))
        else:
            self.log.trace("Nozzle detection failed.")
            
            
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
        # elif(self.__nozzleAutoDetectionActive is True):
        #     # no keypoints, draw a 3 outline circle in the middle of the frame
        #     keypointRadius = 17
        #     nozzleDetectFrame = cv2.circle(img=nozzleDetectFrame, center=(320,240), radius=keypointRadius, color=(0,0,0), thickness=3,lineType=cv2.LINE_AA)
        #     nozzleDetectFrame = cv2.circle(img=nozzleDetectFrame, center=(320,240), radius=keypointRadius+1, color=(0,0,255), thickness=1,lineType=cv2.LINE_AA)
        #     center = (None, None)
        # if(self.__nozzleAutoDetectionActive is True):
            # draw crosshair
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (320,0), (320,480), (0,0,0), 2)
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (0,240), (640,240), (0,0,0), 2)
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (320,0), (320,480), (255,255,255), 1)
            nozzleDetectFrame = cv2.line(nozzleDetectFrame, (0,240), (640,240), (255,255,255), 1)
        # return(center, nozzleDetectFrame)
        return(keypoints, nozzleDetectFrame)


    ##### TAMV Utilities
    # adjust image gamma
    def adjust_gamma(self, image, gamma=1.2):
        # build a lookup table mapping the pixel values [0, 255] to
        # their adjusted gamma values
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype( 'uint8' )
        # apply gamma correction using the lookup table
        return cv2.LUT(image, table)

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



#  Stuff to use from TAMV


    def normalize_coords(self, coords):
            """
            Normalizes the given coordinates to be between -0.5 and 0.5, based on the camera dimensions.

            Args:
                coords (tuple): A tuple of (x, y) coordinates.

            Returns:
                tuple: A tuple of normalized (x, y) coordinates.
            """
            xdim, ydim = self._cameraWidth, self._cameraHeight
            returnValue = (coords[0] / xdim - 0.5, coords[1] / ydim - 0.5)
            return returnValue
        
