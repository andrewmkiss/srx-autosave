"""
SRX Autosave APIs

Helper functions for SRX Autosave

Andy Kiss
-----------------------------------------------------------------------
"""


# %% Import packages
import numpy as np
import time as ttime

from databroker import Broker
# from pyxrf.api import *


# Register the data broker
db = Broker.named('srx')


# ----------------------------------------------------------------------
def echo(s):
    """
    Test function

    Parameters
    ----------
    s : string
        string to return (echo)
    
    Returns
    -------
    s : string

    Examples
    --------
    >>>echo('This was a triumph!')
    This was a triumph!'
    """

    print(s)
    return s


def get_current_scanid():
    """
    Function to return the current scan ID

    Parameters
    ----------
    None

    Returns
    -------
    scanid : int
        The current scan ID
    """

    return _get_current_scanid_db()


def _get_current_scanid_db():
    """
    Function to return the current scan ID using the last scan from the
    data broker.

    Parameters
    ----------
    None

    Returns
    -------
    scanid : int
        The current scan ID
    """

    return db[-1].start['scan_id']


def _get_current_scanid_pv():
    """
    Function to return the current scan ID using the scan broker PV

    Parameters
    ----------
    None

    Returns
    -------
    scanid : int
        The current scan ID
    """
    
    scanid = caget('XF:05IDA-CT{IOC:ScanBroker01}Scan:CUR_ID')
    return scanid


# def update_scanlist(saf='', cycle=''):
#     # Perform a search on the databroker to get scan list
#     # Can filter by SAF, cycle, scan_type
#     # Also look into adding filters to search
#     # db.add_filter(user='Andy')
#     hdr = db(saf, cycle)
#     return hdr
