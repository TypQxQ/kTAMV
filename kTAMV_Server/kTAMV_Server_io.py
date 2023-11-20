import cv2
import numpy as np
import requests
from requests.exceptions import InvalidURL, HTTPError, RequestException, ConnectionError

from PIL import Image, ImageDraw, ImageFont, ImageFile
import time, os, copy, io, datetime

import logging

class kTAMV_io:
    def __init__(self, camera_url, server_url = None, save_image = False):
        self.camera_url = camera_url
        self.server_url = server_url
        self.save_image = save_image
        self.session = requests.Session()
        

    def can_read_stream(self, printer):
        # TODO: Clean this up and return actual errors instead of this...stuff...
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
        # TODO: Raise error, stream already running 
        self.session = requests.Session()

    def get_single_frame(self):
        if self.session is None: 
            # TODO: Raise error: stream is not running
            return None, None

        try:
            with self.session.get(self.camera_url, stream=True) as stream:
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
                            # Save the image dimensions as class variables. TODO Not sure which one is the best way to do it.
                            # self._cameraHeight, self._cameraWidth, _ = image.shape
                            # self.cvtools._cameraHeight, self.cvtools._cameraWidth, _ = image.shape
                            # Return the image
                            return image, image.shape
            return None, None
        except Exception as e:
            logging.error("Failed to get single frame from stream %s" % str(e))
            # raise Exception("Failed to get single frame from stream %s" % str(e))

    def close_stream(self):
        if self.session is not None:
            self.session.close()
            self.session = None


    def output_image(self, image, keypoints):
        if self.server_url is None and not self.save_image:
            return "No server URL or save image flag set, not sending image"
        
        status = ""
        image_with_keypoints : cv2.typing.MatLike = cv2.drawKeypoints(image, keypoints, np.array([]), (0,0,255), cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
        # date_now = datetime.datetime.strftime(datetime.datetime.now(), "%a %b %d %H:%M:%S %Y")        
        # self.textOnFrame(image_with_keypoints, date_now)

        if self.save_image:    
            home_dir = os.path.expanduser('~')
            _ = cv2.imwrite(home_dir + "/frame.jpg", image_with_keypoints)
            status = "Image saved to %s/frame.jpg. " % home_dir
        
        if self.server_url is not None:
            # Convert image to JPEG format
            _, jpeg_image = cv2.imencode('.jpg', image)
            
            try:
                # Send image to server
                _, jpeg_image = cv2.imencode('.jpg', image)
                files = {'image.jpeg': jpeg_image.tobytes()}
                response = requests.post(self.server_url, files=files)
                if response.status_code == 200:
                    return('Image sent successfully')
                else:
                    return('Error sending image: %s' % response.text)
            except Exception as e:
                return("Failed to send image to server: %s" % str(e))  
        return status

    def textOnFrame(image, text : str):
        usedFrame = copy.deepcopy(image)
        
        # Create a draw object
        draw = ImageDraw.Draw(usedFrame)

        # Choose a font
        font = ImageFont.truetype("arial.ttf", 32)
        
        # Draw the date on the image
        draw.text((10, 10), text, font=font, fill=(255, 255, 255))

        return usedFrame
