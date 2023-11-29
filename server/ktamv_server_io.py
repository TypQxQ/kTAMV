import cv2, numpy as np
import requests
from requests.exceptions import InvalidURL, ConnectionError # , HTTPError, RequestException

import base64

# Size of frame to use
_FRAME_WIDTH = 640
_FRAME_HEIGHT = 480
 
class Ktamv_Server_Io:
    def __init__(self, log, camera_url, cloud_url, save_image = False):
        self.log = log
        self.log(' *** initializing Ktamv_Server_Io **** ')
        self.camera_url = camera_url
        self.save_image = save_image
        self.cloud_url = cloud_url
        self.session = requests.Session()
        self.log(' *** initialized Ktamv_Server_Io with camera_url = %s, save_image = %s **** ' % (str(camera_url), str(save_image)))
        

    def can_read_stream(self, printer):
        try:
            with self.session.get(self.camera_url) as _:
                return True
        except InvalidURL as _:
            raise printer.config_error("Could not read nozzle camera address, got InvalidURL error %s" % (self.camera_url))
        except ConnectionError as _:
            raise printer.config_error("Failed to establish connection with nozzle camera %s" % (self.camera_url))
        except Exception as e:
            raise printer.config_error("Nozzle camera request failed %s" % str(e))

    def open_stream(self):
        self.session = requests.Session()

    def get_single_frame(self):
        self.log(' *** calling get_single_frame **** ')
        
        if self.session is None: 
            self.log("HTTP stream for reading jpeg is not running")
            raise Exception("HTTP stream for reading jpeg is not running")

        try:
            with self.session.get(self.camera_url, stream=True) as stream:
                self.log(' stream.ok = %s ' % stream.ok)
                if stream.ok:
                    chunk_size = 1024
                    bytes_ = b''
                    for chunk in stream.iter_content(chunk_size=chunk_size):
                        bytes_ += chunk
                        a = bytes_.find(b'\xff\xd8')
                        b = bytes_.find(b'\xff\xd9')
                        if a != -1 and b != -1:
                            jpg = bytes_[a:b+2]
                            # Read the image from the byte array with OpenCV
                            image = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            image = cv2.resize(image, (_FRAME_WIDTH, _FRAME_HEIGHT), interpolation=cv2.INTER_AREA)
                            # Return the image
                            return image
            return None
        except Exception as e:
            self.log("Failed to get single frame from stream %s" % str(e))
            # raise Exception("Failed to get single frame from stream %s" % str(e))

    def close_stream(self):
        if self.session is not None:
            self.session.close()
            self.session = None
            
    def send_frame_to_cloud(self, frame, points, algorithm):
        try:
            self.log(' *** calling send_frame_to_cloud **** ')
            _, img_encoded = cv2.imencode('.jpg', frame)
            data = {'photo': base64.b64encode(img_encoded), 'algorithm': algorithm, 'points': str(points)}
            
            response = requests.post(self.cloud_url, data=data)
            if response.status_code != 200:
                self.log("Failed to send frame to cloud, got status code %d" % response.status_code)
                return False
            self.log(' *** sent frame to cloud **** ')
            self.log(' *** response = %s **** :' % response.text)
            return True
        except Exception as e:
            self.log("Failed to send frame to cloud %s" % str(e))
            return False    
