            # If standard deviation is higher than 5% of the average, try to exclude the highest and lowest values and recalculate
            __mpp_msg = ("Standard deviation of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2)))) + " %."
            if mpss_std_dev / self.mpp > 0.05:
                gcmd.respond_info("Too high " + __mpp_msg)
                # Exclude the highest and lowest values and recalculate
                mpps_a = mpps.copy()
                mpps_a.remove(max(mpps))
                mpps_a.remove(min(mpps))
                mpss_std_dev_a = statistics.stdev(mpps_a)
                mpp_a = np.around(np.mean(mpps_a),3)
                
                __mpp_msg = ("Recalculated Standard deviation without max and min of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpss_std_dev_a), str(mpp_a), str(np.around((mpss_std_dev_a / mpp_a)*100,2)))) + " %."
                gcmd.respond_info(__mpp_msg)

                # Exclude the values that are more than deviate with more than 50% of mean value and recalculate
                __mpps_std_dev_removed = 0
                for i in reversed(range(len(mpps))):
                    if mpps[i] > self.mpp + (self.mpp * 0.5) or mpps[i] < self.mpp - (self.mpp * 0.5):
                        gcmd.respond_info("1. Removing value %s from list" % str(mpps[i]))
                        mpps.remove(mpps[i])
                        __mpps_std_dev_removed += 1
                    
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                __mpp_msg = ("Standard deviation of mm per pixel after removing %i deviant values is %s for a mm per pixel of %s. This gives an error margin of %s" % (__mpps_std_dev_removed,  str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2)))) + " %."
                gcmd.respond_info(__mpp_msg)

                # Exclude the values that are more than deviate with more than 25% of mean value and recalculate
                __mpps_std_dev_removed = 0
                for i in reversed(range(len(list(mpps)))):
                    gcmd.respond_info(str(mpps[i]) + " >" + str(self.mpp + (self.mpp * 0.15)) + " or " + str(mpps[i]) + " < " + str(self.mpp - (self.mpp * 0.15)))
                    if mpps[i] > self.mpp + (self.mpp * 0.15) or mpps[i] < self.mpp - (self.mpp * 0.15):
                        gcmd.respond_info("2. Removing value %s from list" % str(mpps[i]))
                        mpps.remove(mpps[i])
                        __mpps_std_dev_removed += 1
                    
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                __mpp_msg = ("Standard deviation of mm per pixel after removing %i deviant values is %s for a mm per pixel of %s. This gives an error margin of %s" % (__mpps_std_dev_removed,  str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2)))) + " %."
                gcmd.respond_info(__mpp_msg)

                # Exclude the values that are more than 2 standard deviations from the mean and recalculate
                __mpps_std_dev_removed = 0
                for i in range(len(list(mpps))):
                    if mpps[i] > self.mpp + (mpss_std_dev * 2) or mpps[i] < self.mpp - (mpss_std_dev * 2):
                        gcmd.respond_info("3. Removing value %s from list" % str(mpps[i]))
                        mpps.remove(mpps[i])
                        __mpps_std_dev_removed += 1
                    
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                __mpp_msg = ("Standard deviation of mm per pixel after removing %i deviant values is %s for a mm per pixel of %s. This gives an error margin of %s" % (__mpps_std_dev_removed,  str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2)))) + " %."
                    
                
                gcmd.respond_info("Too high " + __mpp_msg)
                return
            else:
                gcmd.respond_info(__mpp_msg)
            
            logging.debug("Average mm per pixel: %s with a standard deviation of %s" % (str(self.mpp), str(mpss_std_dev)))
            gcmd.respond_info("Average mm per pixel: %s with a standard deviation of %s" % (str(self.mpp), str(mpss_std_dev)))
            logging.debug('*** exiting kTAMV.getDistance')

# --------------------------------------------------------------------
        try:
            self.pm.ensureHomed()
            _current_position = self.pm.get_gcode_position()
            gcmd.respond_info("Current position: %s" % str(_current_position))
            _request_result = self._get_nozzle_position(gcmd)

            # _nozzle_possition = _request_result['position'] 
            # self.uv = [_nozzle_possition[0], _nozzle_possition[1]]
            # Save the position of the nozzle in the center
            self.uv = _request_result['position'] 
            self.olduv = self.uv # Save the camera position of the nozzle in the center
            camera_center_coordinates = self.uv
            self.space_coordinates.append((_current_position[0], _current_position[1]))
            self.camera_coordinates.append((self.uv[0], self.uv[1]))
            
            # self.pm.moveRelative(X =self.calibrationCoordinates[0][0], Y = self.calibrationCoordinates[0][1])

            for i in range(len(self.calibrationCoordinates)):
                gcmd.respond_info("Calibrating camera step %s of %s" % (str(i+1), str(len(self.calibrationCoordinates))))
                logging.debug("Calibrating camera step %s of %s at location: %s" % (str(i), str(len(self.calibrationCoordinates)), str(self.calibrationCoordinates[i])))

                # Move to calibration location
                self.pm.moveRelative(X =self.calibrationCoordinates[i][0], Y = self.calibrationCoordinates[i][1])
                # Get the nozzle position
                _request_result = self._get_nozzle_position(gcmd)
                self.uv = _request_result['position'] 

                # Save the position of the nozzle on camera at the current location
                self.space_coordinates.append((_current_position[0], _current_position[1]))
                self.camera_coordinates.append((self.uv[0], self.uv[1]))

                # Calculate mm per pixel and save it to a list
                mpp = self.getMMperPixel(self.calibrationCoordinates[i], camera_center_coordinates, self.uv)
                mpps.append(mpp)
                gcmd.respond_info("MM per pixel for step %s is %s" % (str(i+1), str(mpp)))

                # Move back to center
                self.pm.moveRelative(X = -self.calibrationCoordinates[i][0], Y = -self.calibrationCoordinates[i][1])
                

            # Calculate the average mm per pixel and the standard deviation
            mpss_std_dev = statistics.stdev(mpps)
            self.mpp = np.around(np.mean(mpps),3)
            
            # If standard deviation is higher than 05% of the average, try to exclude the highest and lowest values and recalculate
            __mpp_msg = ("Standard deviation of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2)))) + " %."
            if mpss_std_dev / self.mpp > 0.05:
                gcmd.respond_info("Too high " + __mpp_msg + " Trying to exclude deviant values and recalculate")

                # Exclude the highest value if it deviates more than 20% from the mean value and recalculate. This is the most likely to be a deviant value
                if max(mpps) > self.mpp + (self.mpp * 0.20):
                    mpps.remove(max(mpps))
                
                # Calculate the average mm per pixel and the standard deviation
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                # Exclude the lowest value if it deviates more than 20% from the mean value and recalculate
                if min(mpps) < self.mpp - (self.mpp * 0.20):
                    mpps.remove(min(mpps))
                    
                # Calculate the average mm per pixel and the standard deviation
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                gcmd.respond_info("Recalculated Standard deviation without deviant max and min of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2))) + " %.")

                # Exclude the values that are more than 2 standard deviations from the mean and recalculate
                for i in reversed(range(len(list(mpps)))):
                    if mpps[i] > self.mpp + (mpss_std_dev * 2) or mpps[i] < self.mpp - (mpss_std_dev * 2):
                        mpps.remove(mpps[i])

                # Calculate the average mm per pixel and the standard deviation
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                # Exclude any other value that deviates more than 25% from mean value and recalculate
                for i in reversed(range(len(mpps))):
                    if mpps[i] > self.mpp + (self.mpp * 0.5) or mpps[i] < self.mpp - (self.mpp * 0.5):
                        logging.log("Removing value %s from list" % str(mpps[i]))
                        mpps.remove(mpps[i])
                    
                # Calculate the average mm per pixel and the standard deviation
                mpss_std_dev = statistics.stdev(mpps)
                self.mpp = np.around(np.mean(mpps),3)

                gcmd.respond_info("Final recalculated standard deviation of mm per pixel is %s for a mm per pixel of %s. This gives an error margin of %s" % (str(mpss_std_dev), str(self.mpp), str(np.around((mpss_std_dev / self.mpp)*100,2))) + " %.")
                gcmd.respond_info("Final recalculated mm per pixel is calculated from %s values" % str(len(mpps)))

                if mpss_std_dev / self.mpp > 0.2 or len(mpps) < 5:
                    gcmd.respond_info("Standard deviation is still too high. Calibration failed.")
                    return
                else:
                    gcmd.respond_info("Standard deviation is now within acceptable range. Calibration succeeded.")
                    logging.debug("Average mm per pixel: %s with a standard deviation of %s" % (str(self.mpp), str(mpss_std_dev)))
                    return
            else:
                gcmd.respond_info(__mpp_msg)
            
            logging.debug("Average mm per pixel: %s with a standard deviation of %s" % (str(self.mpp), str(mpss_std_dev)))
            gcmd.respond_info("Average mm per pixel: %s with a standard deviation of %s" % (str(self.mpp), str(mpss_std_dev)))
            logging.debug('*** exiting kTAMV.getDistance')

        except Exception as e:
            logging.exception('Error: kTAMV.getDistance cannot run: ' + str(e))
            gcmd.respond_info("_calibrate_px_mm failed %s" % str(e))
            raise e
            return None

