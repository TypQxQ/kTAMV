# kTAMV Utility Functions
import json, time
from statistics import mean, stdev
import logging

# For server_request
import typing
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message  # For headers in server_request

__SERVER_REQUEST_TIMEOUT = 2
__FRAME_WIDTH = 640
__FRAME_HEIGHT = 480

class NozzleNotFoundException(Exception):
    pass

####################################################################################################
# Set the server's camera path
####################################################################################################
def send_srv_command(server_url : str, command : str,  **data):
    rr = server_request(server_url + command, data=data, method="POST")
    if not rr.status == 200:
        raise Exception("Server responded with statuscode %s: %s" % (str(rr.status), str(rr.body)))
    return rr.body


####################################################################################################
# Calculate the matrix for maping the camera coordinates to the space coordinates
####################################################################################################
def calculate_camera_to_space_matrix(server_url, calibration_points):
    rr = server_request(
        server_url + "/calculate_camera_to_space_matrix",
        {"calibration_points": calibration_points},
        method="POST",
    )
    if rr.status == 200:
        return True
    else:
        return False

####################################################################################################
# Calculate the offset from a point and the matrix for maping the camera coordinates to the space coordinates
####################################################################################################
def calculate_offset_from_matrix(server_url, _v):
    rr = server_request(
        server_url + "/calculate_offset_from_matrix",
        {"_v": _v},
        method="POST",
    )
    # TODO: Check if the request was successful
    return rr.body


def get_nozzle_position(server_url, reactor):
    ##############################
    # Get nozzle position
    ##############################
    logging.debug("*** calling ktamv_utl.get_nozzle_position")
    _request_id = None

    # First load the server response and check that it is working
    _response = server_request(server_url + "/getNozzlePosition", timeout=__SERVER_REQUEST_TIMEOUT)
    if _response.status != 200:
        raise Exception(
            "When getting nozzle position, server sent statuscode %s: %s"
            % (str(_response.status), str(_response.body))
        )
    # Then load the response content as JSON and check that the statuscode is Accepted (202) or OK (200)
    _response = json.loads(_response.body)
    if not (_response["statuscode"] == 202 or _response["statuscode"] == 200):
        raise Exception(
            "When starting to look for nozzle, server sent statuscode %s: %s"
            % (str(_response["statuscode"]), str(_response["statusmessage"]))
        )
    else:
        logging.warning("_response: %s" % str(_response))
        logging.warning("_response[\"request_id\"]: %s" % str(_response["request_id"])) 

    # Success, got response
    _request_id = _response["request_id"]

    start_time = time.time()
    while True:
        #
        # Check if the request is done
        #

        # First load the server response and check that it is working
        _response = server_request(
            f"{server_url}/getReqest?request_id={_request_id}", timeout=2
        )
        if _response.status != 200:
            raise Exception(
                "When getting nozzle position, server sent statuscode %s: %s"
                % (str(_response.status), str(_response.body))
            )
        # Then load the response content as JSON and check that the statuscode is Accepted (202) or OK (200)
        _response = json.loads(_response.body)
        if _response["statuscode"] == 202:
            # Check if one minute has elapsed
            elapsed_time = time.time() - start_time
            if elapsed_time >= 60:
                raise NozzleNotFoundException(
                    "Nozzle detection timed out after 60 seconds, Server still looking for nozzle."
                )

            # Pause for 200ms to avoid busy loop, this equals checking 5 times per second
            _ = reactor.pause(reactor.monotonic() + 0.200)
            continue
        # If nozzles were found, return the position
        elif _response["statuscode"] == 200:
            logging.debug("*** exiting ktamv_utl.get_nozzle_position")
            return _response
        # If nozzles were not found, raise exception
        elif _response["statuscode"] == 404:
            raise NozzleNotFoundException(
                "Server did not find nozzle, found, got statuscode %s: %s. Try Cleaning the nozzle or adjust Z height. Verify with the KTAMV_SIMPLE_NOZZLE_POSITION command."
                % (str(_response["statuscode"]), str(_response["statusmessage"]))
            )
        else:
            raise Exception(
                "Server nozzle detection failed, got statuscode %s: %s"
                % (str(_response["statuscode"]), str(_response["statusmessage"]))
            )


def get_average_mpp(
    mpps: list, space_coordinates: list, camera_coordinates: list, gcmd
):
    # send calling to log
    logging.debug("*** calling ktamv_utl.get_average_mpp")

    try:
        # Save initial mpps for later comparison
        initial_mpps = mpps.copy()

        # Calculate the average mm per pixel and the standard deviation
        mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)
        # Try to exclude deviant values and recalculate to get a better average and standard deviation

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
        # Exclude the lowest value if it deviates more than 20% from the mean value
        if min(mpps) < mpp - (mpp * 0.20):
            __min_index = mpps.index(min(mpps))
            mpps.remove(mpps[__min_index])
            space_coordinates.remove(space_coordinates[__min_index])
            camera_coordinates.remove(camera_coordinates[__min_index])

        # Calculate the average mm per pixel and the standard deviation
        mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

        # ----------------- 3rd recalculation -----------------
        # Exclude the values that are more than 2 standard deviations from mean
        for i in reversed(range(len(list(mpps)))):
            if mpps[i] > mpp + (mpps_std_dev * 2) or mpps[i] < mpp - (mpps_std_dev * 2):
                mpps.remove(mpps[i])
                space_coordinates.remove(space_coordinates[i])
                camera_coordinates.remove(camera_coordinates[i])

        # Calculate the average mm per pixel and the standard deviation
        mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

        # ----------------- 4th recalculation -----------------
        # Exclude any other value that deviates more than 25% from mean value
        for i in reversed(range(len(mpps))):
            if mpps[i] > mpp + (mpp * 0.25) or mpps[i] < mpp - (mpp * 0.25):
                # logging.debug("Removing value %s from list" % str(mpps[i]))
                mpps.remove(mpps[i])

        # Calculate the average mm per pixel and the standard deviation
        mpps_std_dev, mpp = _get_std_dev_and_mean(mpps)

        # Final check if standard deviation is still too high
        gcmd.respond_info(
            (
                "Final mm/pixel is %.4f with a std. dev. of %.1f"
                % (mpp, (mpps_std_dev / mpp) * 100)
            )
            + "%" + (
                ".\n Final mm/px is calculated from %d of %d values"
                % (len(mpps), len(initial_mpps))
            )
        )

        if mpps_std_dev / mpp > 0.2:
            gcmd.respond_info(
                "Standard deviation is still too high. Calibration failed."
            )
            return None

        # send exiting to log
        logging.debug("*** exiting ktamv_utl.get_average_mpp")

        return mpp, mpps, space_coordinates, camera_coordinates
    except Exception as e:
        raise e.with_traceback(e.__traceback__)


def _get_std_dev_and_mean(mpps: list):
    # Calculate the average mm per pixel and the standard deviation
    mpps_std_dev = stdev(mpps)
    mpp = round(mean(mpps), 3)
    return mpps_std_dev, mpp


def normalize_coords(coords, frame_width=__FRAME_WIDTH, frame_height=__FRAME_HEIGHT):
    xdim, ydim = frame_width, frame_height
    returnValue = (coords[0] / xdim - 0.5, coords[1] / ydim - 0.5)
    return returnValue

# kTAMV Printer Manager
class ktamv_pm:
    __defaultSpeed = 3000

    def __init__(self, config):
        # Load used objects. Mainly to log stuff.
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.toolhead = self.printer.lookup_object("toolhead")

    # Ensure that the printer is homed before continuing
    def ensureHomed(self):
        curtime = self.printer.get_reactor().monotonic()
        kin_status = self.toolhead.get_kinematics().get_status(curtime)

        if (
            "x" not in kin_status["homed_axes"]
            or "y" not in kin_status["homed_axes"]
            or "z" not in kin_status["homed_axes"]
        ):
            raise Exception("Must home X, Y and Z axes first.")

    def moveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed, protected=False):
        # send calling to log
        logging.debug("*** calling ktamv_pm.moveRelative")

        # Ensure that the printer is homed before continuing
        self.ensureHomed()

        _current_position = self.get_gcode_position()
        _new_position = [_current_position[0] + X, _current_position[1] + Y]

        logging.debug("Current absolute position: " + str(_current_position))
        logging.debug("New absolute position to move to: " + str(_new_position))

        try:
            if not (protected):
                self.moveAbsoluteToArray(_new_position, moveSpeed)
                self.toolhead.wait_moves()
            else:
                self.moveAbsolute(
                    _new_position[0],
                    _current_position[1],
                    _current_position[2],
                    moveSpeed,
                )
                self.toolhead.wait_moves()
                self.moveAbsolute(
                    _new_position[0], _new_position[1], _current_position[2], moveSpeed
                )
                self.toolhead.wait_moves()
                self.moveAbsolute(
                    _new_position[0], _new_position[1], _new_position[2], moveSpeed
                )
                self.toolhead.wait_moves()
        except Exception as e:
            raise e.with_traceback(e.__traceback__)

        # send exiting to log
        logging.debug("*** exiting ktamv_pm.moveRelative")

    def moveRelativeToArray(self, pos_array, moveSpeed=__defaultSpeed, protected=False):
        self.moveRelative(
            pos_array[0], pos_array[1], pos_array[2], moveSpeed, protected
        )

    # Move one axis at a time to the position.
    def complexMoveRelative(self, X=0, Y=0, Z=0, moveSpeed=__defaultSpeed):
        self.moveRelative(X, Y, Z, moveSpeed, True)

    # Using G1 command to move the toolhead to the position instead of using the toolhead.move() function because G1 will use the tool's offset.
    def moveAbsoluteToArray(self, pos_array, moveSpeed=__defaultSpeed):
        gcode = "G90\nG1 "
        for i in range(len(pos_array)):
            if i == 0:
                gcode += "X%s " % (pos_array[i])
            elif i == 1:
                gcode += "Y%s " % (pos_array[i])
            elif i == 2:
                gcode += "Z%s " % (pos_array[i])
        gcode += "F%s " % (moveSpeed)

        self.gcode.run_script_from_command(gcode)
        toolhead = self.printer.lookup_object("toolhead")
        toolhead.wait_moves()

    def moveAbsolute(self, X=None, Y=None, Z=None, moveSpeed=__defaultSpeed):
        self.moveAbsoluteToArray([X, Y, Z], moveSpeed)

    def get_gcode_position(self):
        gcode_move = self.printer.lookup_object("gcode_move")
        gcode_position = gcode_move.get_status()["gcode_position"]

        return [gcode_position.x, gcode_position.y, gcode_position.z]

    def get_raw_position(self):
        gcode_move = self.printer.lookup_object("gcode_move")
        raw_position = gcode_move.get_status()["position"]

        return [raw_position.x, raw_position.y, raw_position.z]


class Server_Response(typing.NamedTuple):
    body: str
    headers: Message
    status: int
    error_count: int = 0

    def json(self) -> typing.Any:
        try:
            output = json.loads(self.body)
        except json.JSONDecodeError:
            output = ""
        return output


def server_request(
    url: str,
    data: dict = None,
    params: dict = None,
    headers: dict = None,
    method: str = "GET",
    data_as_json: bool = True,
    error_count: int = 0,
    timeout: int = __SERVER_REQUEST_TIMEOUT,  # 2 seconds
) -> Server_Response:
    if not url.casefold().startswith("http"):
        raise urllib.error.URLError("Incorrect and possibly insecure protocol in url")
    method = method.upper()
    request_data = None
    headers = headers or {}
    data = data or {}
    params = params or {}
    headers = {"Accept": "application/json", **headers}

    if method == "GET":
        params = {**params, **data}
        data = None

    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True, safe="/")

    if data:
        if data_as_json:
            request_data = json.dumps(data).encode()
            headers["Content-Type"] = "application/json; charset=UTF-8"
        else:
            request_data = urllib.parse.urlencode(data).encode()

    httprequest = urllib.request.Request(
        url, data=request_data, headers=headers, method=method
    )

    try:
        with urllib.request.urlopen(httprequest, timeout=timeout) as httpresponse:
            response = Server_Response(
                headers=httpresponse.headers,
                status=httpresponse.status,
                body=httpresponse.read().decode(
                    httpresponse.headers.get_content_charset("utf-8")
                ),
            )
    except Exception as e:
        raise e.with_traceback(e.__traceback__)
    return response
