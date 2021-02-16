# Import packages
import numpy as np
import time as ttime
import os
import sys
import glob
import h5py
from databroker import Broker
from tifffile import imsave
import logging

try:
    from pyxrf.api_dev import *
except ImportError:
    print("Error importing pyXRF. Continuing without import.")


try:
    from epics import caget
except ImportError:
    print("Error importing caget. Continuing without import.")


# Set logging level to WARNING in order to prevent a flood of messages from 'epics'
#   Feel free to change the logging level as needed.
logger = logging.getLogger()
logger.setLevel(logging.WARNING)


"""
SRX Autosave APIs

Helper functions for SRX Autosave

Andy Kiss
"""


# Register the data broker
try:
    db = Broker.named("srx")
except AttributeError:
    db = Broker.named("temp")
    print("Using temporary databroker.")


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

    try:
        x = db[-1].start["scan_id"]
    except IndexError:
        x = 1
    return x


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

    scanid = caget("XF:05IDA-CT{IOC:ScanBroker01}Scan:CUR_ID")
    return scanid


# def update_scanlist(saf='', cycle=''):
#     # Perform a search on the databroker to get scan list
#     # Can filter by SAF, cycle, scan_type
#     # Also look into adding filters to search
#     # db.add_filter(user='Andy')
#     hdr = db(saf, cycle)
#     return hdr


def check_inputs(start_id, wd, N, dt):
    # Check the input parameters
    if start_id < 0:
        # Need to add 1 to scan ID
        # Otherwise it will grab the current value (which would be from the previous user)
        start_id = get_current_scanid() + 1
        print(f"Using starting scan ID: {start_id}")

    if wd == "":
        wd = os.getcwd()
        print(f"Using current directory.\n{wd}")

    if N < 1:
        # Add logic later that if N < 1, then always use current scan ID
        print("Warning: N changed to 100.")
        N = 100

    if dt < 1:
        print("Warning: dt changed to 1 second.")
        dt = 1

    return (start_id, wd, N, dt)


def autoroi_xrf(scanid):
    """
    SRX auto_roi

    Automatic generate roi based on the specified elements

    Parameters
    ----------
    scanid : int
        Scan ID
   
    Returns
    -------
    None

    Examples
    --------
    Start generating rois from the saved h5 files and saving them into the user's directory
    >>> autoroi_xrf(1234)

    """
    #load h5 file (autosaved)
    element_roi = {'Ca_k':[350,390], "Fe_k": [620,660], "Ni_k": [730,770], "Cu_k": [780, 820], "Zn_k": [780, 820], "Pt_l": [920,960], "Au_l": [1140, 1180]};
    
    print("start exporting rois: Ca, Fe, Ni, Cu, Zn, Pt, Au.")
    h5file = glob.glob(f"scan2D_{scanid}_*.h5")
    if not len(h5file) == 0:
        f = h5py.File(h5file[0])
        if not os.path.exists(f"scan_{scanid}"):
            try:
                os.mkdir(f"scan_{scanid}_rois")
            except OSError:
                print(f"creation of folder scan_{scanid}_rois failed.")
            else:
                print(f"folder scan_{scanid}_rois created.")
        for x in element_roi:
            roi = np.sum(f['xrfmap/detsum/counts'][:,:,element_roi[x][0]:element_roi[x][1]], axis=2)
            sclr_I0 = f['xrfmap/scalers/val'][:,:,0]
            roi_norm = roi/sclr_I0
            imsave(f'scan_{scanid}_rois/roi_{scanid}_{x}.tiff', roi_norm.astype("float32"), dtype=np.float32)
        print("finish exporting rois")
    else:
        print(f"scan2D_{scanid} can not be found!")
        pass


def add_encoder_data(scanid):
    # This is for old metadata style and flyscans in x only
    # Get scan ID
    # _, scanid, _, _ = fn.split('_')
    scanid = int(scanid)
    ls_fn = glob.glob(f'scan2D_{scanid}*.h5')
    if len(ls_fn) == 1:
        fn = ls_fn[0]
    else:
        print('Cannot identify which file to add encoder data.')
        return

    # Get scan header
    h = db[int(scanid)]
    scanid = int(h.start['scan_id'])
    start_doc = h.start
    
    # Get position data from scan
    y_pos = h.data('enc2', stream_name='stream0', fill=True)
    y_pos = np.array(list(y_pos))

    # Write to file
    try:
        with h5py.File(fn, 'a') as f:
            # pos = f['/xrfmap/positions/pos']
            pos = np.array(f['/xrfmap/positions/pos'])
            pos_name = f['/xrfmap/positions/name']

            ind = list(pos_name).index(b'y_pos')  # This should be 1, but good to verify
            pos[ind, :, :] = y_pos
            # pos[ind, :, :] = y_pos[np.newaxis, ...]
            f['/xrfmap/positions/pos'][...] = pos
    except:
        print(f'Error writing to file: {fn}')


def xrf_loop(start_id, N, gui=None):
    num = np.arange(start_id, start_id + N, 1)
    for i in range(N):
        # Check if the scan ID exists
        # We could make a function to check if current scan ID
        # >= this value. Or same thing but return True/False
        scanid = int(num[i])

        if gui is not None:
            gui.signal_update_status.emit(f"Making {scanid}...")

            if gui.isRunning is False:
                gui.signal_update_status.emit(f"SRX Autosave stopped.")
                gui.signal_update_progressBar.emit(0)
                return

        try:
            h = db[scanid]
        except Exception:
            print(f"{scanid} does not exist!")
            break

        # Output to command line that we are on a given scan
        print(scanid, end="\t", flush=True)
        print(h.start["plan_name"], end="\t", flush=True)  # This might change

        # Check if fly scan
        # Should be more generic, if XRF scan
        if h.start["plan_name"] == "scan_and_fly":
            # fname = filelist_h5[i]
            # Check if the file noes not exist
            # if not os.path.isfile(fname):
            if not glob.glob(f"scan2D_{scanid}_*.h5") and not os.path.isfile(
                f"scan2D_{scanid}.h5"
            ):
                # Check if the scan is done
                try:
                    # db[scanid].stop['time']
                    make_hdf(scanid, completed_scans_only=True)
                    ttime.sleep(1)
                    add_encoder_data(scanid)
                    ttime.sleep(1)
                    autoroi_xrf(scanid)
                except Exception as ex:
                    print(ex)
                    pass
            else:   
                print(f"XRF HDF5 already created.")

        else:
            print()
    return


def loop_sleep(dt, gui=None):
    if gui is not None:
        DT = gui.DT
    else:
        DT = 0.5

    print("\nSleeping for %d seconds...Press Ctrl-C to exit" % (dt), flush=True)
    t0 = ttime.monotonic()
    del_t = 0.0
    while del_t < dt:
        str_status = "%02d seconds remaining..." % (dt - del_t)
        print("   %s" % str_status, end="\r", flush=True)
        if gui is not None:
            gui.signal_update_progressBar.emit(100 * del_t / dt)
            gui.signal_update_status.emit(str_status)
            if gui.isRunning is False:
                print('SRX Autosave stopped.')
                gui.signal_update_status.emit('SRX Autosave stopped.')
                gui.signal_update_progressBar.emit(0)
                break
        ttime.sleep(DT)
        del_t = ttime.monotonic() - t0
    print("--------------------------------------------------")
    return

