"""Spa Client integration."""
import asyncio
from contextlib import suppress
import homeassistant.util.dt as dt_util

# Import the device class from the component that you want to support
from .const import _LOGGER
from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

IO_TIMEOUT = 5
REQUEST_TIMEOUT = 15


class spaclient:
    def __init__(self, host_ip):
        """ Socket variables """
        self.socket_is_connected = False
        self.socket_l = asyncio.Lock()
        self.socket_s = None
        self._reader = None
        self.socket_host_ip = host_ip

        """ Status update variable """
        self.status_chunk_array = []

        """ Status update variables """
        self.hold_mode = 0
        self.priming = 0
        self.current_temp = None
        self.hour = 0
        self.minute = 0
        self.heat_mode = "Rest"
        self.hold_mode_remain_time = 0
        self.temp_scale = "Fahrenheit"
        self.filter_mode = False
        self.time_scale = "24 Hr"
        self.heating = False
        self.temp_range = "Low"
        self.pump1 = "Off"
        self.pump2 = "Off"
        self.pump3 = "Off"
        self.pump4 = "Off"
        self.pump5 = "Off"
        self.pump6 = "Off"
        self.circ_pump = False
        self.blower = "Off"
        self.light1 = False
        self.light2 = False
        self.mister = "Off"
        self.aux1 = "Off"
        self.aux2 = "Off"
        self.set_temp = 0
        self.standby_mode = 0

        """ Information variables """
        self.info_model_name = "Unknown"
        self.info_cfg_sig = "Unknown"
        self.info_sw_vers = "Unknown"
        self.info_setup = 0
        self.info_ssid = "Unknown"
        self.info_heater_voltage = "Unknown"
        self.info_heater_type = "Unknown"
        self.info_dip_switch = "0000000000000000"
        self.information_loaded = False

        """ Configuration variables """
        self.cfg_pump_array = [0, 0, 0, 0, 0, 0] #To switch to development mode, replace the 0 with 1
        self.cfg_light_array = [0, 0]            #To switch to development mode, replace the 0 with 1
        self.cfg_circ_pump_array = [0]           #To switch to development mode, replace the 0 with 1
        self.cfg_blower_array = [0]              #To switch to development mode, replace the 0 with 1
        self.cfg_mister_array = [0]              #To switch to development mode, replace the 0 with 1
        self.cfg_aux_array = [0, 0]              #To switch to development mode, replace the 0 with 1
        self.configuration_loaded = False

        """ Module identification variables """
        self.id_macaddr = "Unknown"
        self.id_mac_oui = "Unknown"
        self.id_mac_nic = "Unknown"
        self.module_identification_loaded = False

        """ Filter cycles variables """
        self.filter_1_begins_hour = 0
        self.filter_1_begins_minute = 0
        self.filter_1_runs_hour = 0
        self.filter_1_runs_minute = 0
        self.filter_2_enabled = 0
        self.filter_2_begins_hour = 0
        self.filter_2_begins_minute = 0
        self.filter_2_runs_hour = 0
        self.filter_2_runs_minute = 0
        self.filter_cycles_loaded = False

        """ Additional information variables """
        self.add_info_low_range_min = 0
        self.add_info_low_range_max = 0
        self.add_info_high_range_min = 0
        self.add_info_high_range_max = 0
        self.add_info_nb_of_pumps = 0
        self.additional_information_loaded = False

        """ Preferences variables """
        self.pref_reminder = "Off"
        self.pref_temp_scale = "Fahrenheit"
        self.pref_clock_mode = "24 Hr"
        self.pref_clean_up_cycle = 0
        self.pref_dolphin_address = 0
        self.pref_m8_ai = "Off"
        self.preferences_loaded = False

        """ Fault log variables """
        self.fault_log_total_entries = 0
        self.fault_log_entry_nb = 0
        self.fault_log_msg_code = 0
        self.fault_log_days_ago = 0
        self.fault_log_msg_hour = 0
        self.fault_log_msg_minute = 0
        self.fault_log_todo = 0
        self.fault_log_set_temp = 0
        self.fault_log_sensor_a_temp = 0
        self.fault_log_sensor_b_temp = 0
        self.fault_log_loaded = False

        """ GFCI test variables """
        self.gfci_test_result = 0
        self.gfci_test_loaded = False

    async def get_socket(self):
        if self.socket_s is not None:
            return True
        try:
            async with asyncio.timeout(IO_TIMEOUT):
                self._reader, self.socket_s = await asyncio.open_connection(
                    self.socket_host_ip, 4257
                )
        except (OSError, TimeoutError) as err:
            _LOGGER.debug("Spa connection failed: %s", err)
            self._disconnect()
            return False
        return True

    def _disconnect(self):
        """Close the transport without blocking the event loop."""
        self.socket_is_connected = False
        self.status_chunk_array = []
        if self.socket_s is not None:
            self.socket_s.close()
        self.socket_s = None
        self._reader = None

    async def close(self):
        """Release the connection after its background tasks have stopped."""
        writer = self.socket_s
        self._disconnect()
        if writer is not None:
            with suppress(OSError, TimeoutError):
                async with asyncio.timeout(IO_TIMEOUT):
                    await writer.wait_closed()

    async def validate_connection(self):
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                if not await self.get_socket():
                    return False
                while not self.socket_is_connected:
                    if not await self.read_msg():
                        return False
                    await asyncio.sleep(0)
        except TimeoutError:
            self._disconnect()
            return False
        return self.socket_is_connected

    async def keep_alive_call(self):
        while True:
            if self.socket_s is None:
                await self.get_socket()
            else:
                try:
                    await self.send_fault_log_request()
                except (ConnectionError, TimeoutError):
                    self._disconnect()
            await asyncio.sleep(30)

    def compute_checksum(self, length, payload):
        crc = 0xb5
        for cur in range(length):
            for i in range(8):
                bit = crc & 0x80
                crc = ((crc << 1) & 0xff) | ((payload[cur] >> (7 - i)) & 0x01)
                if bit:
                    crc = crc ^ 0x07
            crc &= 0xff
        for i in range(8):
            bit = crc & 0x80
            crc = (crc << 1) & 0xff
            if bit:
                crc ^= 0x07
        return crc ^ 0x02

    async def read_msg(self):
        """Read one complete frame, including when TCP fragments a message."""
        async with self.socket_l:
            reader = self._reader
            if reader is None:
                return False
            try:
                async with asyncio.timeout(IO_TIMEOUT):
                    while await reader.readexactly(1) != b'\x7e':
                        pass
                    length = (await reader.readexactly(1))[0]
                    if length < 5:
                        return True
                    chunk = await reader.readexactly(length)
            except (OSError, EOFError, TimeoutError) as err:
                _LOGGER.debug("Spa connection lost: %s", err)
                if self._reader is reader:
                    self._disconnect()
                return False
            except asyncio.CancelledError:
                # A cancelled partial read cannot safely resume framing.
                if self._reader is reader:
                    self._disconnect()
                raise

            if self._reader is not reader:
                return False
            if chunk[-1] != 0x7e or chunk[-2] != self.compute_checksum(
                length - 1, bytes([length]) + chunk[:-2]
            ):
                _LOGGER.debug("Ignoring invalid spa frame")
                return True
            try:
                return self._process_message(chunk)
            except (IndexError, ValueError):
                _LOGGER.debug("Ignoring malformed spa payload", exc_info=True)
                return True

    def _process_message(self, chunk):

        if chunk != self.status_chunk_array:
            if chunk[0:3] == b'\xff\xaf\x13' and ((self.information_loaded and self.additional_information_loaded and self.preferences_loaded and self.configuration_loaded and self.module_identification_loaded) or (self.socket_is_connected == False)):
                #_LOGGER.info("Status update = %s", chunk[3:]) #Validation point
                self.parse_status_update(chunk[3:])
                self.status_chunk_array = chunk
                self.socket_is_connected = True
                return True

            if chunk[0:3] == b'\x0a\xbf\x23':
                #_LOGGER.info("Filter cycles response = %s", chunk[3:]) #Validation point
                self.parse_filter_cycles_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x24' and self.information_loaded != True:
                #_LOGGER.info("Information response = %s", chunk[3:]) #Validation point
                self.parse_information_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x25' and self.additional_information_loaded != True:
                #_LOGGER.info("Additional information response = %s", chunk[3:]) #Validation point
                self.parse_additional_information_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x26' and self.preferences_loaded != True:
                #_LOGGER.info("Preferences response = %s", chunk[3:]) #Validation point
                self.parse_preferences_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x28':
                #_LOGGER.info("Fault log response = %s", chunk[3:]) #Validation point
                self.parse_fault_log_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x2b':
                #_LOGGER.info("GFCI test response = %s", chunk[3:]) #Validation point
                self.parse_gfci_test_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x2e' and self.configuration_loaded != True:
                #_LOGGER.info("Configuration response = %s", chunk[3:]) #Validation point
                self.parse_configuration_response(chunk[3:])
                return True

            if chunk[0:3] == b'\x0a\xbf\x94' and self.module_identification_loaded != True:
                #_LOGGER.info("Module identification response = %s", chunk[3:]) #Validation point
                self.parse_module_identification_response(chunk[3:])
                return True

        return True

    async def read_all_msg(self):
        while True:
            if self.socket_s is not None:
                await self.read_msg()
            await asyncio.sleep(.1)


    def parse_additional_information_response(self, byte_array):
        """ Parse additional information response.

            SSID       Length
        M100_210 V6.0    14
        M100_225 V36.0   14
        M100_201 V44.0   15

                         00 01 02 03 04 05 06 07 08
        MS ML MT MT MT   00 01 LL LH HL HH 06 07 08   CS ME
        7E 0E 0A BF 25                                   7E

        00: ?
        01: ?
        LL: Low Low - Low range temperature's minimum in Fahrenheit
        LH: Low High - Low range temperature's maximum in Fahrenheit
        HL: High Low - High range temperature's minimum in Fahrenheit
        HH: High High - High range temperature's maximum in Fahrenheit
        06: ?
        07: Number of pumps
        08: ?

        """

        self.add_info_low_range_min = byte_array[2]
        self.add_info_low_range_max = byte_array[3]
        self.add_info_high_range_min = byte_array[4]
        self.add_info_high_range_max = byte_array[5]

        self.add_info_nb_of_pumps = (
            (byte_array[7] & 0x01)
            + (byte_array[7] >> 1 & 0x01)
            + (byte_array[7] >> 2 & 0x01)
            + (byte_array[7] >> 3 & 0x01)
            + (byte_array[7] >> 4 & 0x01)
            + (byte_array[7] >> 5 & 0x01)
        )

        self.additional_information_loaded = True

    def parse_configuration_response(self, byte_array):
        """ Parse a panel config response.

                         00 01 02 03 04 05
        MS ML MT MT MT   00 01 02 03 04 05   CS ME
        7E 0B 0A BF 2E                          7E

        00: P4P3P2P1 - Pumps 1-4 (0 = None, 1 = 1-speed, 2 = 2-speed)
        01: P6xxxxP5 - Pumps 5-6 (0 = None, 1 = 1-speed, 2 = 2-speed)
        02: L2xxxxL1 - Lights (0 = None, 1 = Present)
        03: CxxxxxBL - Circulation pump, Blower (0 = None, 1 = Present)
        04: xxMIxxAA - Mister, Aux2, Aux1 (0 = None, 1 = Present)
        05: ?

        """

        self.cfg_pump_array[0] = int((byte_array[0] & 0x03))
        self.cfg_pump_array[1] = int((byte_array[0] & 0x0c) >> 2)
        self.cfg_pump_array[2] = int((byte_array[0] & 0x30) >> 4)
        self.cfg_pump_array[3] = int((byte_array[0] & 0xc0) >> 6)
        self.cfg_pump_array[4] = int((byte_array[1] & 0x03))
        self.cfg_pump_array[5] = int((byte_array[1] & 0xc0) >> 6)

        self.cfg_light_array[0] = int((byte_array[2] & 0x03) != 0)
        self.cfg_light_array[1] = int((byte_array[2] & 0xc0) != 0)

        self.cfg_circ_pump_array[0] = int((byte_array[3] & 0x80) != 0)
        self.cfg_blower_array[0] = int((byte_array[3] & 0x03) != 0)
        self.cfg_mister_array[0] = int((byte_array[4] & 0x30) != 0)

        self.cfg_aux_array[0] = int((byte_array[4] & 0x01) != 0)
        self.cfg_aux_array[1] = int((byte_array[4] & 0x02) != 0)

        self.configuration_loaded = True

    def parse_fault_log_response(self, byte_array):
        """ Parse fault log response.

                         00 01 02 03 04 05 06 07 08 09
        MS ML MT MT MT   00 01 02 03 04 05 06 07 08 09   CS ME
        7E 0F 0A BF 28                                      7E

        00: Total Entries (0-24)
        01: Entry Number (0-23 (0=Entry #1))
        02: Message Code
        03: Days Ago (0-255?)
        04: Time: Hour (0-23)
        05: Time: Minute (0-59)
        06: Flags TODO
        07: Set Temperature (Temperature scaled by Temperature Scale)
        08: Sensor A Temperature (Temperature scaled by Temperature Scale)
        09: Sensor B Temperature (Temperature scaled by Temperature Scale)

        """
        self.fault_log_total_entries = byte_array[0]
        self.fault_log_entry_nb = byte_array[1]
        self.fault_log_msg_code = byte_array[2]
        self.fault_log_days_ago = byte_array[3]
        self.fault_log_msg_hour = byte_array[4]
        self.fault_log_msg_minute = byte_array[5]
        self.fault_log_todo = byte_array[6]
        self.fault_log_set_temp = byte_array[7]
        self.fault_log_sensor_a_temp = byte_array[8]
        self.fault_log_sensor_b_temp = byte_array[9]

        self.fault_log_loaded = True

    def parse_filter_cycles_response(self, byte_array):
        """ Parse filter cycles response.

                         00 01 02 03 04 05 06 07
        MS ML MT MT MT   1H 1M 1D 1E 2H 2M 2D 2E   CS ME
        7E 0D 0A BF 23                                7E

        1H: Filter 1 begins hour (0-23)
        1M: Filter 1 begins minute (0-59)
        1D: Filter 1 runs hour (0-23)
        1E: Filter 1 runs minute (0-59)
        2H: Filter 2 begins hour (0-23), masking out the high order bit, which is used as an enable/disable flag
        2M: Filter 2 begins minute (0-59)
        2D: Filter 2 runs hour (0-23)
        2E: Filter 2 runs minute (0-59)

        """

        self.filter_1_begins_hour = byte_array[0]
        self.filter_1_begins_minute = byte_array[1]
        self.filter_1_runs_hour = byte_array[2]
        self.filter_1_runs_minute = byte_array[3]
        self.filter_2_enabled = byte_array[4] >> 7
        self.filter_2_begins_hour = byte_array[4] ^ (self.filter_2_enabled << 7)
        self.filter_2_begins_minute = byte_array[5]
        self.filter_2_runs_hour = byte_array[6]
        self.filter_2_runs_minute = byte_array[7]

        self.filter_cycles_loaded = True

    def parse_gfci_test_response(self, byte_array):
        """ Parse fault log response.

                         00
        MS ML MT MT MT   00   CS ME
        7E 06 0A BF 2B           7E

        00: 0x00 = N/A ? or FAIL?
            0x01 = PASS

        """

        self.gfci_test_result = byte_array[0]

        self.gfci_test_loaded = True

    def parse_information_response(self, byte_array):
        """ Parse information response.

                         00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20
        MS ML MT MT MT   I0 I1 V0 V1 M0 M1 M2 M3 M4 M5 M6 M7 SU S0 S1 S2 S3 HV HT D0 D1   CS ME
        7E 1A 0A BF 24                                                                       7E

        I0-I1: Software ID (SSID) (Displayed (in decimal) as "M<I0>_<I1> V<V0>[.<V1>]"
        V0-V1
        M0-M7: System Model Number (ASCII-encoded string)
        SU   : Current Configuration Setup Number
        S1-S3: Configuration Signature (Checksum of the system configuration file)
        HV   : Heat Voltage (0x01 = 240, other = Unknown)
        HT   : Heater Type (0x0A = Standard, other = Unknown)
        D0-D1: DIP Switch Settings (bit 0 of Byte 19 is position 1)

        """

        model = [byte_array[4], byte_array[5], byte_array[6], byte_array[7], byte_array[8], byte_array[9], byte_array[10], byte_array[11]]
        model_name = "".join(map(chr, model))
        self.info_model_name = model_name.strip()

        self.info_sw_vers = f"{str(byte_array[2])}.{str(byte_array[3])}"
        self.info_setup = byte_array[12]
        self.info_ssid = f"M{str(byte_array[0])}_{str(byte_array[1])} V{self.info_sw_vers}"
        self.info_cfg_sig = f"{byte_array[13]:x}{byte_array[14]:x}{byte_array[15]:x}{byte_array[16]:x}"
        self.info_heater_voltage = 240 if byte_array[17] == 0x01 else "Unknown"
        self.info_heater_type = "Standard" if byte_array[18] == 0x0A else "Unknown"
        self.info_dip_switch = f"{byte_array[19]:08b}{byte_array[20]:08b}"

        self.information_loaded = True

    def parse_module_identification_response(self, byte_array):
        """ Parse a module identification response.

                         00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
        MS ML MT MT MT   00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24   CS ME
        7E 1E 0A BF 94                                                                                   7E

        00-02: ?
        03-08: MAC Address
        09-16: ? (0)
        17-19: MAC Address Organizationally Unique Identifier (OUI) (Balboa Instruments = 00:15:27)
        20-21: ? (0xFF)
        22-24: MAC Address Network Interface Controller (NIC) (Specific)

        """

        self.id_macaddr = f"{byte_array[3]:02x}:{byte_array[4]:02x}:{byte_array[5]:02x}:{byte_array[6]:02x}:{byte_array[7]:02x}:{byte_array[8]:02x}"
        self.id_mac_oui = f"{byte_array[17]:02x}:{byte_array[18]:02x}:{byte_array[19]:02x}"
        self.id_mac_nic = f"{byte_array[22]:02x}:{byte_array[23]:02x}:{byte_array[24]:02x}"

        self.module_identification_loaded = True

    def parse_preferences_response(self, byte_array):
        """ Parse preferences response.

                         00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17
        MS ML MT MT MT   00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17   CS ME
        7E 17 0A BF 26                                                              7E

        00: ?
        01: Reminders (0 = OFF, 1 = ON)
        02: ?
        03: Temperature Scale (0 = Fahrenheit, 1 = Celsius)
        04: Clock Mode (0 = 12 hour time, 1 = 24 hour time)
        05: Clean-up Cycle (0 = OFF, 1-8 (30 minute increments))
        06: Dolphin Address (0 = None, 1-7 = Address)
        07: ?
        08: M8 Artificial Intelligence (0 = OFF, 1 = ON)
        09-17: ?

        """

        self.pref_reminder = ("Off", "On")[byte_array[1] & 0x01]
        self.pref_temp_scale = ("Fahrenheit", "Celsius")[byte_array[3] & 0x01]
        self.pref_clock_mode = ("12 Hr", "24 Hr")[byte_array[4] & 0x01]
        self.pref_clean_up_cycle = byte_array[5]
        self.pref_dolphin_address = byte_array[6]
        self.pref_m8_ai = ("Off", "On")[byte_array[8] & 0x01]

        self.preferences_loaded = True

    def parse_status_update(self, byte_array):
        """ Parse a status update from the spa.

            SSID       Length
        M100_210 V6.0    28
        M100_220 V20.0   29
        M100_225 V36.0   29
        M100_201 V44.0   32
        M100_201 V47.0   32
        M100_220 V50.0   32

        MS: Message Start (always 0x7e "~")
        ML: Message Length
        MT: Message Type
        CS: Checksum (CRC-8 with 0x02 initial value, and 0x02 final XOR)
        ME: Message End (always 0x7e "~")

                         00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24
        MS ML MT MT MT   F0 F1 CT HH MM F2 06 TA TB F3 F4 P1 P2 F5 LF F6 16 17 18 CU ST AB 22 23 M8   CS ME
        7E 20 FF AF 13                                                                                   7E

        F0: 0x00 = Running
            0x01 = Initializing
            0x05 = Hold Mode
            0x14 = A/B Temps ON?
            0x17 = Test Mode
        F1: 0x00 = Idle
            0x01 = Priming Mode
            0x02 = Fault?
            0x03 = Reminder
            0x04 = Stage 1?
            0x05 = Stage 3?
            0x42 = Stage 2?
        CT: Current Temperature (divide by two if in Celsius; 0xFF if unknown)
        HH: Hour (always 0-23, even in 12 hour mode; flag is used to control display)
        MM: Minute (0-59)
        F2: 0x03 = Heating Mode (0 = Ready, 1 = Rest, 3 = Ready in rest)
        06: Reminder Type (0x00 = None, 0x04 = Clean filter, 0x0A = Check the pH, 0x09 = Check the sanitizer, 0x1E = Fault?)
        TA: Sensor A Temperature / Hold Timer (Minutes if Hold Mode else Temperature (scaled by Temperature Scale) if A/B Temps else 0x00)
        TB: Sensor B Temperature (0x00 if A/B Temps if OFF else Temperature (scaled by Temperature Scale))
        F3: 0x01 = Temperature Scale (0 = Fahrenheit, 1 = Celsius)
            0x02 = 24 Hour Time (0 = 12 hour time, 1 = 24 hour time)
            0x0c = Filter Mode (0 = OFF, 1 = Cycle 1, 2 = Cycle 2, 3 = Cycle 1 and 2)
        F4: 0x30 = Heating (0 = OFF, 1 = Heating, 2 = Heat Waiting)
            0x04 = Temperature Range (0 = Low, 1 = High)
        P1: Pump status: 0x03 for pump 1 * Valid values for each pump are 0 = OFF, 1 = Low, 2 = High
                         0x0C for pump 2 (or, shift two bits right, and then mask to 0x03)
                         0x30 for pump 3 (or, shift 4 bits right, and then mask to 0x03)
                         0xC0 for pump 4 (or, shift 6 bits right, and then mask to 0x03)
        P2: Pump status: 0x03 for pump 5
                         0xC0 for pump 6 (or, shift 6 bits right, and then mask to 0x03)
        F5: 0x02 = Circulation pump (0 = OFF, 1 = ON)
            0x0C = Blower (0 = OFF, 3 = ON)
        LF: Light 1: 0x03 == 0x03 for ON
            Light 2: 0xC0 == 0x03 for ON (or, shift 6 bits right, and then mask to 0x03)
        F6: 0x01 = Mister
            0x08 = Aux1
            0x10 = Aux2
        16: ?
        17: ?
        18: 0x00 = Reminder
            0x04 = Warning ("The settings have been reset")?
        CU: 0x00 = Clean-up Cycle (0x00 = N/A?, 0x04 = OFF, 0x0C = ON?)
            0x20 = Notification	(0 = No, 1 = Yes)
        ST: Set Temperature
        AB: 0x02 = Sensor A/B Temperatures	(0 = No, 1 = Yes)
            0x04 = Timeouts	(0 = Normal, 1 = 8h)
            0x08 = Settings Locked / Test Mode: Temp Limits	(0 = No, 1 = Yes)
        22: Mode of operation (0x00 = Normal Mode, 0x01 = Pump Test Mode, 0x40 = Hold Mode)
        23: Saving states when switching between modes... For internal use in the BP controller
        M8: M8 Cycle Time (0 = OFF, 30, 60, 90, or 120 (in minutes))

        """

        self.hold_mode = 1 if byte_array[0] == 0x05 else 0
        self.priming = 1 if byte_array[1] == 0x01 else 0
        self.current_temp = byte_array[2] if (byte_array[2] != 255) else None
        self.hour = byte_array[3]
        self.minute = byte_array[4]
        self.heat_mode = ("Ready", "Rest", "Ready in Rest")[byte_array[5]]
        self.hold_mode_remain_time = byte_array[7] if self.hold_mode else 0
        self.temp_scale = "Fahrenheit" if (byte_array[9] & 0x01 == 0) else "Celsius"
        self.time_scale = "12 Hr" if (byte_array[9] & 0x02 == 0) else "24 Hr"
        self.filter_mode = (byte_array[9] & 0x0c) >> 2
        self.heating = (byte_array[10] & 0x30) >> 4
        self.temp_range = "Low" if (byte_array[10] & 0x04) >> 2 == 0 else "High"
        self.pump1 = ("Off", "Low", "High")[byte_array[11] & 0x03]
        self.pump2 = ("Off", "Low", "High")[byte_array[11] >> 2 & 0x03]
        self.pump3 = ("Off", "Low", "High")[byte_array[11] >> 4 & 0x03]
        self.pump4 = ("Off", "Low", "High")[byte_array[11] >> 6 & 0x03]
        self.pump5 = ("Off", "Low", "High")[byte_array[12] & 0x03]
        self.pump6 = ("Off", "Low", "High")[byte_array[12] >> 6 & 0x03]
        self.circ_pump = byte_array[13] & 0x02
        self.blower =  "Off" if (byte_array[13] & 0x0c) >> 2 == 0 else "On"
        self.light1 = byte_array[14] & 0x03 == 0x03
        self.light2 = byte_array[14] >> 6 & 0x03 == 0x03
        self.mister = "Off" if (byte_array[15] & 0x01) == 0 else "On"
        self.aux1 = byte_array[15] & 0x08
        self.aux2 = byte_array[15] & 0x10
        self.set_temp = byte_array[20]
        self.standby_mode = 1 if (byte_array[22] & 0x01) == 1 else 0


    def get_aux(self, aux_num):
        if aux_num == 1:
            return self.get_aux1()
        else:
            return self.get_aux2()

    def get_aux_list(self):
        return self.cfg_aux_array

    def get_aux1(self):
        return self.aux1

    def get_aux2(self):
        return self.aux2

    def get_blower(self):
        return self.blower

    def get_blower_list(self):
        return self.cfg_blower_array

    def get_circ_pump(self):
        return self.circ_pump

    def get_circ_pump_list(self):
        return self.cfg_circ_pump_array

    def get_current_temp(self):
        return self.current_temp

    def get_current_time(self):
        return "%d:%02d" % (self.hour, self.minute)

    def get_fault_log_msg_code(self):
        return self.fault_log_msg_code

    def get_filter_begins(self, filter_num):
        if filter_num == 1:
            return "%02d:%02d" % (self.filter_1_begins_hour, self.filter_1_begins_minute)
        else:
            return "%02d:%02d" % (self.filter_2_begins_hour, self.filter_2_begins_minute)

    def get_filter_begins_hour(self, filter_num):
        if filter_num == 1:
            return self.filter_1_begins_hour
        else:
            return self.filter_2_begins_hour

    def get_filter_begins_minute(self, filter_num):
        if filter_num == 1:
            return self.filter_1_begins_minute
        else:
            return self.filter_2_begins_minute

    def get_filter_ends(self, filter_num):
        if filter_num == 1:
            if self.filter_1_begins_hour + self.filter_1_runs_hour >= 24:
                return "%02d:%02d" % (self.filter_1_begins_hour + self.filter_1_runs_hour - 24, self.filter_1_begins_minute + self.filter_1_runs_minute)
            return "%02d:%02d" % (self.filter_1_begins_hour + self.filter_1_runs_hour, self.filter_1_begins_minute + self.filter_1_runs_minute)
        else:
            if self.filter_2_begins_hour + self.filter_2_runs_hour >= 24:
                return "%02d:%02d" % (self.filter_2_begins_hour + self.filter_2_runs_hour - 24, self.filter_2_begins_minute + self.filter_2_runs_minute)
            return "%02d:%02d" % (self.filter_2_begins_hour + self.filter_2_runs_hour, self.filter_2_begins_minute + self.filter_2_runs_minute)

    def get_filter_mode(self, filter_num):
        if filter_num == 1:
            if self.filter_mode == 1 or self.filter_mode == 3:
                return True
        else:
            if self.filter_mode == 2 or self.filter_mode == 3:
                return True
        return False

    def get_filter_runs(self, filter_num):
        if filter_num == 1:
            return f"{self.filter_1_runs_hour} hours | {self.filter_1_runs_minute} minutes"
        else:
            return f"{self.filter_2_runs_hour} hours | {self.filter_2_runs_minute} minutes"

    def get_filter_runs_hour(self, filter_num):
        if filter_num == 1:
            return self.filter_1_runs_hour
        else:
            return self.filter_2_runs_hour

    def get_filter_runs_minute(self, filter_num):
        if filter_num == 1:
            return self.filter_1_runs_minute
        else:
            return self.filter_2_runs_minute

    def get_filter2_enabled(self):
        return self.filter_2_enabled

    def get_gateway_status(self):
        return self.socket_is_connected

    def get_heat_mode(self):
        return self.heat_mode

    def get_heating(self):
        return self.heating

    def get_high_range_max(self):
        return self.add_info_high_range_max

    def get_high_range_min(self):
        return self.add_info_high_range_min

    def get_hold_mode(self):
        return self.hold_mode

    def get_hold_mode_remain_time(self):
        hours = self.hold_mode_remain_time // 60
        minutes = self.hold_mode_remain_time % 60
        return "%02d:%02d" % (hours, minutes)

    def get_light(self, light_num):
        if light_num == 1:
            return self.get_light1()
        else:
            return self.get_light2()

    def get_light_list(self):
        return self.cfg_light_array

    def get_light1(self):
        return self.light1

    def get_light2(self):
        return self.light2

    def get_low_range_max(self):
        return self.add_info_low_range_max

    def get_low_range_min(self):
        return self.add_info_low_range_min

    def get_macaddr(self):
        return self.id_macaddr

    def get_mister(self):
        return self.mister

    def get_mister_list(self):
        return self.cfg_mister_array

    def get_model_name(self):
        return self.info_model_name

    def get_pump(self, pump_num):
        if pump_num == 1:
            return self.get_pump1()
        elif pump_num == 2:
            return self.get_pump2()
        elif pump_num == 3:
            return self.get_pump3()
        elif pump_num == 4:
            return self.get_pump4()
        elif pump_num == 5:
            return self.get_pump5()
        else:
            return self.get_pump6()

    def get_pump_list(self):
        return self.cfg_pump_array

    def get_pump1(self):
        return self.pump1

    def get_pump2(self):
        return self.pump2

    def get_pump3(self):
        return self.pump3

    def get_pump4(self):
        return self.pump4

    def get_pump5(self):
        return self.pump5

    def get_pump6(self):
        return self.pump6

    def get_set_temp(self):
        return self.set_temp

    def get_ssid(self):
        return self.info_ssid

    def get_standby_mode(self):
        return self.standby_mode

    def get_temp_range(self):
        return self.temp_range


    async def send_additional_information_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x04\x00\x00', "additional_information_loaded")

    async def send_configuration_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x00\x00\x01', "configuration_loaded")

    async def send_fault_log_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x20\x00\x00', "fault_log_loaded")

    async def _request(self, message_type, payload, loaded_attribute):
        """Wait a bounded time for initialization replies, without blocking HA."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                self.send_message(message_type, payload)
                while not getattr(self, loaded_attribute):
                    if not await self.read_msg():
                        raise ConnectionError("Spa disconnected while waiting for a reply")
                    # Buffered status frames must not starve other tasks or the timeout.
                    await asyncio.sleep(0)
        except (ConnectionError, TimeoutError):
            self._disconnect()
            raise

    def send_filter_cycles_config(self):
        self.send_message(b'\x0a\xbf\x23',
            bytes([self.filter_1_begins_hour]) +
            bytes([self.filter_1_begins_minute]) +
            bytes([self.filter_1_runs_hour]) +
            bytes([self.filter_1_runs_minute]) +
            bytes([int(self.filter_2_enabled << 7) + self.filter_2_begins_hour]) +
            bytes([self.filter_2_begins_minute]) +
            bytes([self.filter_2_runs_hour]) +
            bytes([self.filter_2_runs_minute])
        )

    async def send_filter_cycles_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x01\x00\x00', "filter_cycles_loaded")

    async def send_gfci_test_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x80\x00\x00', "gfci_test_loaded")

    async def send_information_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x02\x00\x00', "information_loaded")

    def send_message(self, type, payload):
        if self.socket_s is None or self.socket_s.is_closing():
            raise ConnectionError("Spa is not connected")
        length = 5 + len(payload)
        checksum = self.compute_checksum(length - 1, bytes([length]) + type + payload)
        prefix = b'\x7e'
        message = prefix + bytes([length]) + type + payload + bytes([checksum]) + prefix

        try:
            # StreamWriter buffers the complete frame; it never waits for network I/O.
            self.socket_s.write(message)
            return True
        except OSError:
            self._disconnect()
            raise

    async def send_module_identification_request(self):
        await self._request(b'\x0a\xbf\x04', b'', "module_identification_loaded")

    async def send_preferences_request(self):
        await self._request(b'\x0a\xbf\x22', b'\x08\x00\x00', "preferences_loaded")

    def send_toggle_message(self, item):
        self.send_message(b'\x0a\xbf\x11', bytes([item]) + b'\x00')


    def set_aux(self, aux_num, value):
        aux_val = self.aux1
        aux_code = 0x16
        if aux_num == 2:
            aux_val = self.aux2
            aux_code = 0x17
        if aux_val == value:
            return
        self.send_toggle_message(aux_code)
        if aux_num == 1:
            self.aux1 = value
        if aux_num == 2:
            self.aux2 = value

    def set_blower(self, value):
        if self.blower == value:
            return
        self.send_toggle_message(0x0c)
        self.blower = value

    def set_clear_notification(self, value):
        if self.clear_notification == value:
            return
        self.send_toggle_message(0x03)
        self.clear_notification = value

    async def set_current_time(self):
        now = dt_util.utcnow()
        now = dt_util.as_local(now)
        if self.time_scale == "24 Hr":
            self.send_message(b'\x0a\xbf\x21', bytes([128 + now.hour]) + bytes([now.minute]))
        else:
            self.send_message(b'\x0a\xbf\x21', bytes([now.hour]) + bytes([now.minute]))

    def set_filter_cycle_begins_time(self, filter_num, value):
        if filter_num == 1:
            self.filter_1_begins_hour = value.hour
            self.filter_1_begins_minute = value.minute
        if filter_num == 2:
            self.filter_2_begins_hour = value.hour
            self.filter_2_begins_minute = value.minute
        self.send_filter_cycles_config()

    def set_filter_cycle_runs_time(self, filter_num, value):
        if filter_num == 1:
            self.filter_1_runs_hour = value.hour
            self.filter_1_runs_minute = value.minute
        if filter_num == 2:
            self.filter_2_runs_hour = value.hour
            self.filter_2_runs_minute = value.minute
        self.send_filter_cycles_config()

    def set_filter2_enabled(self, value):
        self.filter_2_enabled = value
        self.send_filter_cycles_config()

    def set_heat_mode(self, value):
        if self.heat_mode == value:
            return
        self.send_toggle_message(0x51)
        self.heat_mode = value

    def set_hold_mode(self, value):
        if self.hold_mode == value:
            return
        self.send_toggle_message(0x3c)
        self.hold_mode = value

    def set_light(self, light_num, value):
        light_val = self.light1
        light_code = 0x11
        if light_num == 2:
            light_val = self.light2
            light_code = 0x12
        if light_val == value:
            return
        self.send_toggle_message(light_code)
        if light_num == 1:
            self.light1 = value
        if light_num == 2:
            self.light2 = value

    def set_mister(self, value):
        if self.mister == value:
            return
        self.send_toggle_message(0x0e)
        self.mister = value

    def set_normal_operation(self, value):
        if self.normal_operation == value:
            return
        self.send_toggle_message(0x01)
        self.normal_operation = value

    def set_pump(self, pump_num, value):
        pump_val = self.pump1
        pump_code = 0x04
        if pump_num == 2:
            pump_val = self.pump2
            pump_code = 0x05
        if pump_num == 3:
            pump_val = self.pump3
            pump_code = 0x06
        if pump_num == 4:
            pump_val = self.pump4
            pump_code = 0x07
        if pump_num == 5:
            pump_val = self.pump5
            pump_code = 0x08
        if pump_num == 6:
            pump_val = self.pump6
            pump_code = 0x09
        if pump_val == value:
            return
        self.send_toggle_message(pump_code)
        if pump_num == 1:
            self.pump1 = value
        if pump_num == 2:
            self.pump2 = value
        if pump_num == 3:
            self.pump3 = value
        if pump_num == 4:
            self.pump4 = value
        if pump_num == 5:
            self.pump5 = value
        if pump_num == 6:
            self.pump6 = value

    def set_standby_mode(self):
        self.send_toggle_message(0x1d)

    def set_temp_range(self, value):
        if self.temp_range == value:
            return
        self.send_toggle_message(0x50)
        self.temp_range = value

    async def set_temperature(self, temp):
        self.send_message(b'\x0a\xbf\x20', bytes([int(temp)]))

    def set_temperature_scale(self, temperature_scale): #Not use yet!
        self.send_message(b'\x0a\xbf\x27', bytes([]) + bytes([]))


    def print_variables(self):
        _LOGGER.info("")
        _LOGGER.info("======================")
        _LOGGER.info("<< socket variables >>")
        _LOGGER.info("======================")
        _LOGGER.info("self.socket_is_connected = %s", self.socket_is_connected)
        _LOGGER.info("self.socket_l = %s", self.socket_l)
        _LOGGER.info("self.socket_s = %s", self.socket_s)
        _LOGGER.info("self.socket_host_ip = %s", self.socket_host_ip)

        _LOGGER.info("")
        _LOGGER.info("=============================")
        _LOGGER.info("<< Status update variables >>")
        _LOGGER.info("=============================")
        _LOGGER.info("self.hold_mode= %s", self.hold_mode)
        _LOGGER.info("self.priming = %s", self.priming)
        _LOGGER.info("self.current_temp = %s", self.current_temp)
        _LOGGER.info("self.hour = %s", self.hour)
        _LOGGER.info("self.minute = %s", self.minute)
        _LOGGER.info("self.heat_mode = %s", self.heat_mode)
        _LOGGER.info("self.hold_mode_remain_time = %s", self.hold_mode_remain_time)
        _LOGGER.info("self.temp_scale = %s", self.temp_scale)
        _LOGGER.info("self.filter_mode = %s", self.filter_mode)
        _LOGGER.info("self.time_scale = %s", self.time_scale)
        _LOGGER.info("self.heating = %s", self.heating)
        _LOGGER.info("self.temp_range = %s", self.temp_range)
        _LOGGER.info("self.pump1 = %s", self.pump1)
        _LOGGER.info("self.pump2 = %s", self.pump2)
        _LOGGER.info("self.pump3 = %s", self.pump3)
        _LOGGER.info("self.pump4 = %s", self.pump4)
        _LOGGER.info("self.pump5 = %s", self.pump5)
        _LOGGER.info("self.pump6 = %s", self.pump6)
        _LOGGER.info("self.circ_pump = %s", self.circ_pump)
        _LOGGER.info("self.blower = %s", self.blower)
        _LOGGER.info("self.light1 = %s", self.light1)
        _LOGGER.info("self.light2 = %s", self.light2)
        _LOGGER.info("self.mister = %s", self.mister)
        _LOGGER.info("self.aux1 = %s", self.aux1)
        _LOGGER.info("self.aux2 = %s", self.aux2)
        _LOGGER.info("self.set_temp = %s", self.set_temp)
        _LOGGER.info("self.standby_mode = %s", self.standby_mode)

        _LOGGER.info("")
        _LOGGER.info("===========================")
        _LOGGER.info("<< Information variables >>")
        _LOGGER.info("===========================")
        _LOGGER.info("self.information_loaded = %s", self.information_loaded)
        _LOGGER.info("self.info_model_name = %s", self.info_model_name)
        _LOGGER.info("self.info_cfg_sig = %s", self.info_cfg_sig)
        _LOGGER.info("self.info_sw_vers = %s", self.info_sw_vers)
        _LOGGER.info("self.info_setup = %s", self.info_setup)
        _LOGGER.info("self.info_ssid = %s", self.info_ssid)
        _LOGGER.info("self.info_heater_voltage = %s", self.info_heater_voltage)
        _LOGGER.info("self.info_heater_type = %s", self.info_heater_type)
        _LOGGER.info("self.info_dip_switch = %s", self.info_dip_switch)

        _LOGGER.info("")
        _LOGGER.info("=============================")
        _LOGGER.info("<< Configuration variables >>")
        _LOGGER.info("=============================")
        _LOGGER.info("self.configuration_loaded = %s", self.configuration_loaded)
        _LOGGER.info("self.cfg_pump_array = %s", self.cfg_pump_array)
        _LOGGER.info("self.cfg_light_array = %s", self.cfg_light_array)
        _LOGGER.info("self.cfg_circ_pump_array = %s", self.cfg_circ_pump_array)
        _LOGGER.info("self.cfg_blower_array = %s", self.cfg_blower_array)
        _LOGGER.info("self.cfg_mister_array = %s", self.cfg_mister_array)
        _LOGGER.info("self.cfg_aux_array = %s", self.cfg_aux_array)

        _LOGGER.info("")
        _LOGGER.info("=====================================")
        _LOGGER.info("<< Module identification variables >>")
        _LOGGER.info("=====================================")
        _LOGGER.info("self.module_identification_loaded = %s", self.module_identification_loaded)
        _LOGGER.info("self.id_macaddr = %s", self.id_macaddr)
        _LOGGER.info("self.id_mac_oui = %s", self.id_mac_oui)
        _LOGGER.info("self.id_mac_nic = %s", self.id_mac_nic)

        _LOGGER.info("")
        _LOGGER.info("=============================")
        _LOGGER.info("<< Filter cycles variables >>")
        _LOGGER.info("=============================")
        _LOGGER.info("self.filter_cycles_loaded = %s", self.filter_cycles_loaded)
        _LOGGER.info("self.filter_1_begins_hour = %s", self.filter_1_begins_hour)
        _LOGGER.info("self.filter_1_begins_minute = %s", self.filter_1_begins_minute)
        _LOGGER.info("self.filter_1_runs_hour = %s", self.filter_1_runs_hour)
        _LOGGER.info("self.filter_1_runs_minute = %s", self.filter_1_runs_minute)
        _LOGGER.info("self.filter_2_enabled = %s", self.filter_2_enabled)
        _LOGGER.info("self.filter_2_begins_hour = %s", self.filter_2_begins_hour)
        _LOGGER.info("self.filter_2_begins_minute = %s", self.filter_2_begins_minute)
        _LOGGER.info("self.filter_2_runs_hour = %s", self.filter_2_runs_hour)
        _LOGGER.info("self.filter_2_runs_minute = %s", self.filter_2_runs_minute)

        _LOGGER.info("")
        _LOGGER.info("======================================")
        _LOGGER.info("<< Additional information variables >>")
        _LOGGER.info("======================================")
        _LOGGER.info("self.additional_information_loaded = %s", self.additional_information_loaded)
        _LOGGER.info("self.add_info_low_range_min = %s", self.add_info_low_range_min)
        _LOGGER.info("self.add_info_low_range_max = %s", self.add_info_low_range_max)
        _LOGGER.info("self.add_info_high_range_min = %s", self.add_info_high_range_min)
        _LOGGER.info("self.add_info_high_range_max = %s", self.add_info_high_range_max)
        _LOGGER.info("self.add_info_nb_of_pumps = %s", self.add_info_nb_of_pumps)

        _LOGGER.info("")
        _LOGGER.info("===========================")
        _LOGGER.info("<< Preferences variables >>")
        _LOGGER.info("===========================")
        _LOGGER.info("self.preferences_loaded = %s", self.preferences_loaded)
        _LOGGER.info("self.pref_reminder = %s", self.pref_reminder)
        _LOGGER.info("self.pref_temp_scale = %s", self.pref_temp_scale)
        _LOGGER.info("self.pref_clock_mode = %s", self.pref_clock_mode)
        _LOGGER.info("self.pref_clean_up_cycle = %s", self.pref_clean_up_cycle)
        _LOGGER.info("self.pref_dolphin_address = %s", self.pref_dolphin_address)
        _LOGGER.info("self.pref_m8_ai = %s", self.pref_m8_ai)

        _LOGGER.info("")
        _LOGGER.info("=========================")
        _LOGGER.info("<< Fault log variables >>")
        _LOGGER.info("=========================")
        _LOGGER.info("self.fault_log_loaded = %s", self.fault_log_loaded)
        _LOGGER.info("self.fault_log_total_entries = %s", self.fault_log_total_entries)
        _LOGGER.info("self.fault_log_entry_nb = %s", self.fault_log_entry_nb)
        _LOGGER.info("self.fault_log_msg_code = %s", self.fault_log_msg_code)
        _LOGGER.info("self.fault_log_days_ago = %s", self.fault_log_days_ago)
        _LOGGER.info("self.fault_log_msg_hour = %s", self.fault_log_msg_hour)
        _LOGGER.info("self.fault_log_msg_minute = %s", self.fault_log_msg_minute)
        _LOGGER.info("self.fault_log_todo = %s", self.fault_log_todo)
        _LOGGER.info("self.fault_log_set_temp = %s", self.fault_log_set_temp)
        _LOGGER.info("self.fault_log_sensor_a_temp = %s", self.fault_log_sensor_a_temp)
        _LOGGER.info("self.fault_log_sensor_b_temp = %s", self.fault_log_sensor_b_temp)

        _LOGGER.info("")
        _LOGGER.info("=========================")
        _LOGGER.info("<< GFCI test variables >>")
        _LOGGER.info("=========================")
        _LOGGER.info("self.gfci_test_loaded = %s", self.gfci_test_loaded)
        _LOGGER.info("self.gfci_test_result = %s", self.gfci_test_result)
        _LOGGER.info("")
