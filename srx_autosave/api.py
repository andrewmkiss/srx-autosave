# Import packages
import numpy as np
import time as ttime
import os
import sys
import glob
import h5py
import traceback
import logging
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Table, Spacer
import reportlab.lib.pagesizes
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from PIL import Image as pImage
from skimage import exposure
from PyPDF2 import PdfFileMerger
from tifffile import imsave

from databroker import Broker
# try:
#     from databroker.v0 import Broker
# except ModuleNotFoundError:
#     from databroker import Broker

import logging
from pyxrf.api import *
#from new_makehdf import new_makehdf

try:
   from pyxrf.api_dev import db
except ImportError:
    db = None
    print("Error importing pyXRF. Continuing without import.")

if not db:
    # Register the data broker
    try:
         db = Broker.named("srx")
    except AttributeError:
         db = Broker.named("temp")
         print("Using temporary databroker.")


try:
    from epics import caget
except ImportError:
    print("Error importing caget. Continuing without import.")

from tiled.client import from_profile
import time as ttime


tiled_client = from_profile("nsls2")["srx"]
tiled_client_raw = tiled_client["raw"]


# Set logging level to WARNING in order to prevent a flood of messages from 'epics'
#   Feel free to change the logging level as needed.
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

#FLAG for auto_roi and create_pdf
auto_roi_flag = False
"""
SRX Autosave APIs

Helper functions for SRX Autosave

Andy Kiss
"""


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


def autoroi_xrf(scanid, auto_dir):
    """
    SRX auto_roi

    Automatic generate roi based on the specified elements

    Parameters
    ----------
    scanid : int
        Scan ID
    auto_dir : string
        Folder to save the automatic processing
   
    Returns
    -------
    None

    Examples
    --------
    Start generating rois from the saved h5 files and saving them into the user's directory
    >>> autoroi_xrf(1234)

    """
    # Load h5 file (autosaved)
    element_roi = {"K_k" : [316, 346],
                   "Mn_k" : [215, 245],
                   "Ni_k" : [730, 770],
                   "Cu_k" : [780, 820],
                   "Bi_l" : [1069, 1099]}
##     element_roi = {"Si_k" : [159, 189],
##                    "S_k" : [215, 245],
##                    "P_k" : [186, 206],
##                    "Al_k" : [134, 164],
##                    "Mn_k" : [575, 605],
##                    "Cu_k" : [790, 820],
##                    "Cl_k" : [247, 277], 
##                    "Ca_k" : [350, 390],
##                    "Fe_k" : [620, 660],
##                    "Zn_k" : [780, 820],
##                    "Au_l" : [950, 990]}
##     
    print("Start exporting ROIs")
    h5file = glob.glob(f"scan2D_{scanid}_*.h5")

    #save the tif and png in local home dir to avoid the eviction
    save_dir = '/home/xf05id1/auto_rois/'
    if not len(h5file) == 0:
        f = h5py.File(h5file[0])

        try:
            os.makedirs(os.path.join(save_dir, f"scan_{scanid}_rois"), exist_ok=True)
        except Exception as e:
            print(e)
            raise OSError(f'Cannot create scan_{scanid} directory')

        sclr_I0 = f['xrfmap/scalers/val'][:, :, 0]
        sclr_IM = f['xrfmap/scalers/val'][:, :, 3]
        imsave(os.path.join(save_dir, f'scan_{scanid}_rois', f'{scanid}_I0.tif'),
               sclr_I0.astype("float32"),
               dtype=np.float32)
 
        for x in element_roi:
            roi = np.sum(f['xrfmap/detsum/counts'][:, :, element_roi[x][0]:element_roi[x][1]], axis=2)
            roi_norm = roi / sclr_I0
            imsave(os.path.join(save_dir, f'scan_{scanid}_rois', f'roi_{scanid}_{x}.tif'),
                   roi.astype("float32"),
                   dtype=np.float32)
            imsave(os.path.join(save_dir, f'scan_{scanid}_rois', f'roi_{scanid}_{x}_norm.tif'),
                   roi_norm.astype("float32"),
                   dtype=np.float32)
            # imsave(f'scan_{scanid}_rois/roi_{scanid}_{x}.tiff', roi_norm.astype("float32"), dtype=np.float32)
            percentiles = np.percentile(roi_norm, (0.5, 99.5))
            scaled = exposure.rescale_intensity(roi_norm,in_range=tuple(percentiles))
            min=np.min(scaled)    
            max=np.max(scaled)    
            roi_scaled = ((scaled-min)/(max-min))*255
            imsave(os.path.join(save_dir, f'scan_{scanid}_rois', f'roi_{scanid}_{x}_norm.png'),
                   roi_scaled.astype("uint8"),
                   dtype=np.uint8)
            # imsave(f'{auto_dir}scan_{scanid}_rois/roi_{scanid}_{x}.png', roi_scaled.astype("uint8"), dtype=np.uint8)
        print("Finished exporting ROIs")
    else:
        print(f"scan2D_{scanid} can not be found!")
        pass

def create_pdf(scanid, auto_dir):
    """
    Automatic generate pdf report montaging all the saved png

    Parameters
    ----------
    scanid : int
        Starting scan ID
    auto_dir : string
        Folder to save the automatic processing

    Returns
    -------
    None

    """

    elements = []
    item_tbl_data = []
    item_tbl_row = []
        
    save_dir = '/home/xf05id1/auto_rois/'    
    img_list = glob.glob(os.path.join(save_dir, f'scan_{scanid}_rois', 'roi_*.png'))
    
    for i, file in enumerate(img_list):
        last_item = len(img_list) - 1
        if ".png" in file:
            img = Image((file))
            img_name = file.replace(".png", "")
            img_name = str(scanid) + '_' + img_name[-9::]
            #grab scan info
            scaninfo = str(db[scanid].start['scan']['scan_input'])

            if len(item_tbl_row) == 2:
                item_tbl_data.append(item_tbl_row)
                item_tbl_row = []
            elif i == last_item:
                item_tbl_data.append(item_tbl_row)
                      
            i_tbl = Table([[img], [Paragraph(img_name + '     SCANINFO:'+ scaninfo, ParagraphStyle("item name style", wordWrap='CJK', fontSize = 10))]])
            item_tbl_row.append(i_tbl)    
                    
    if len(item_tbl_data) > 0:
        item_tbl = Table(item_tbl_data, colWidths=225)
        elements.append(item_tbl)
        elements.append(Spacer(1, inch * 0.5))

    pdf_save_loc = "XRF_RoiMaps_log.pdf"
    pdf_save_rename = "XRF_RoiMaps_log_bk.pdf"
    pdf_save_tmp = 'tmp.pdf'
    doc = SimpleDocTemplate(pdf_save_loc, pagesize = reportlab.lib.pagesizes.A4)
    doc_tmp = SimpleDocTemplate(pdf_save_tmp, pagesize = reportlab.lib.pagesizes.A4)
    if not os.path.exists(pdf_save_loc):
        try:
            doc.build(elements)
        except PermissionError:
            logging.error("Missing Permission to write. File open in system editor or missing "
                          "write permissions.") 
    else:
       try:
            doc_tmp.build(elements)
            os.rename(pdf_save_loc, pdf_save_rename)
            pdf_merger = PdfFileMerger()
            pdf_merger.append(pdf_save_rename)
            pdf_merger.append(pdf_save_tmp)
            pdf_merger.write(pdf_save_loc)
            pdf_merger.close()
            os.remove(pdf_save_tmp)
            os.remove(pdf_save_rename)
       except PermissionError:
            logging.error("Missing Permission to write. File open in system editor or missing "
                          "write permissions.") 

    #os.system(f'cp /home/xf05id1/XRF_RoiMaps_log.pdf {auto_dir}.')
    
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




def xanes_textout(
    scanid=-1,
    header=[],
    userheader={},
    column=[],
    usercolumn={},
    usercolumnname=[],
    output=True,
):
    """
    scan: can be scan_id (integer) or uid (string). default=-1 (last scan run)
    header: a list of items that exist in the event data to be put into
            the header
    userheader: a dictionary defined by user to put into the header
    column: a list of items that exist in the event data to be put into
            the column data
    output: print all header fileds. if output = False, only print the ones
            that were able to be written
            default = True

    """

    h = tiled_client_raw[scanid]
    # filepath = f"/nsls2/data/srx/proposals/{h.start['cycle']}/{h.start['data_session']}/scan_{h.start['scan_id']}_xanes.txt"  # noqa: E501
    filepath = f"scan_{h.start['scan_id']}_xanes.txt"  # noqa: E501

    with open(filepath, "w") as f:
        dataset_client = h["primary"]["data"]

        staticheader = (
            "# XDI/1.0 MX/2.0\n"
            + "# Beamline.name: "
            + h.start["beamline_id"]
            + "\n"
            + "# Facility.name: NSLS-II\n"
            + "# Facility.ring_current:"
            + str(dataset_client["ring_current"][0])
            + "\n"
            + "# Scan.start.uid: "
            + h.start["uid"]
            + "\n"
            + "# Scan.start.time: "
            + str(h.start["time"])
            + "\n"
            + "# Scan.start.ctime: "
            + ttime.ctime(h.start["time"])
            + "\n"
            + "# Mono.name: Si 111\n"
        )

        f.write(staticheader)

        for item in header:
            if item in dataset_client.keys():
                f.write("# " + item + ": " + str(dataset_client[item]) + "\n")
                if output is True:
                    print(f"{item} is written")
            else:
                print(f"{item} is not in the scan")

        for key in userheader:
            f.write("# " + key + ": " + str(userheader[key]) + "\n")
            if output is True:
                print(f"{key} is written")

        file_data = {}
        for idx, item in enumerate(column):
            if item in dataset_client.keys():
                # retrieve the data from tiled that is going to be used
                # in the file
                file_data[item] = dataset_client[
                    item
                ].read()
                f.write("# Column." + str(idx + 1) + ": " + item + "\n")

        f.write("# ")
        for item in column:
            if item in dataset_client.keys():
                f.write(str(item) + "\t")

        for item in usercolumnname:
            f.write(item + "\t")

        f.write("\n")
        f.flush()

        offset = False
        for idx in range(len(file_data[column[0]])):
            for item in column:
                if item in file_data:
                    f.write("{0:8.6g}  ".format(file_data[item][idx]))
            for item in usercolumnname:
                if item in usercolumn:
                    if offset is False:
                        try:
                            f.write("{0:8.6g}  ".format(usercolumn[item][idx]))
                        except KeyError:
                            offset = True
                            f.write("{0:8.6g}  ".format(
                                usercolumn[item][idx + 1]))
                    else:
                        f.write("{0:8.6g}  ".format(usercolumn[item][idx + 1]))
            f.write("\n")


def xanes_afterscan_plan(scanid, roinum=1):
    logger = get_run_logger()

    # Custom header list
    headeritem = []
    # Load header for our scan
    h = tiled_client_raw[scanid]

    if h.start["scan"].get("type") != "XAS_STEP":
        logger.info(
            "Incorrect document type. Not running exporter on this document."
        )
        return
    # Construct basic header information
    userheaderitem = {}
    userheaderitem["uid"] = h.start["uid"]
    userheaderitem["sample.name"] = h.start["scan"]["sample_name"]

    # Create columns for data file
    columnitem = ["energy_energy", "energy_bragg", "energy_c2_x"]
    # Include I_M, I_0, and I_t from the SRS
    if "sclr1" in h.start["detectors"]:
        if "sclr_i0" in h["primary"].descriptors[0]["object_keys"]["sclr1"]:
            columnitem.extend(["sclr_im", "sclr_i0", "sclr_it"])
        else:
            columnitem.extend(["sclr1_mca3", "sclr1_mca2", "sclr1_mca4"])

    else:
        raise KeyError("SRS not found in data!")
    # Include fluorescence data if present, allow multiple rois
    if "xs" in h.start["detectors"]:
        if type(roinum) is not list:
            roinum = [roinum]
        logger.info(roinum)
        for i in roinum:
            logger.info(f"Current roinumber: {i}")
            roi_name = "roi{:02}".format(i)
            roi_key = []

            xs_channels = h["primary"].descriptors[0]["object_keys"]["xs"]
            for xs_channel in xs_channels:
                logger.info(f"Current xs_channel: {xs_channel}")
                if "mca" + roi_name in xs_channel and "total_rbv" in xs_channel:  # noqa: E501
                    roi_key.append(xs_channel)

            columnitem.extend(roi_key)

    # if ('xs2' in h.start['detectors']):
    #     if (type(roinum) is not list):
    #         roinum = [roinum]
    #     for i in roinum:
    #         roi_name = 'roi{:02}'.format(i)
    #         roi_key = []
    #         roi_key.append(getattr(xs2.channel1.rois, roi_name).value.name)

    # [columnitem.append(roi) for roi in roi_key]

    # Construct user convenience columns allowing prescaling of ion chamber,
    # diode and fluorescence detector data
    usercolumnitem = {}
    datatablenames = []

    if "xs" in h.start["detectors"]:
        datatablenames.extend(roi_key)
    if "xs2" in h.start["detectors"]:
        datatablenames.extend(roi_key)
    if "sclr1" in h.start["detectors"]:
        if "sclr_im" in h["primary"].descriptors[0]["object_keys"]["sclr1"]:
            datatablenames.extend(["sclr_im", "sclr_i0", "sclr_it"])
            datatable = h["primary"].read(datatablenames)
        else:
            datatablenames.extend(["sclr1_mca2", "sclr1_mca3", "sclr1_mca4"])
            datatable = h["primary"].read(datatablenames)
    else:
        raise KeyError
    # Calculate sums for xspress3 channels of interest
    if "xs" in h.start["detectors"]:
        for i in roinum:
            roi_name = "roi{:02}".format(i)
            roi_key = []
            for xs_channel in xs_channels:
                if "mca" + roi_name in xs_channel and "total_rbv" in xs_channel:  # noqa: E501
                    roi_key.append(xs_channel)
            roisum = sum(datatable[roi_key].to_array()).to_series()
            roisum = roisum.rename_axis("seq_num").rename(lambda x: x + 1)
            usercolumnitem["If-{:02}".format(i)] = roisum
            # usercolumnitem['If-{:02}'.format(i)].round(0)

    # if 'xs2' in h.start['detectors']:
    #     for i in roinum:
    #         roi_name = 'roi{:02}'.format(i)
    #         roisum=datatable[getattr(xs2.channel1.rois,roi_name).value.name]
    #         usercolumnitem['If-{:02}'.format(i)] = roisum
    #         usercolumnitem['If-{:02}'.format(i)].round(0)

    xanes_textout(
        scanid=scanid,
        header=headeritem,
        userheader=userheaderitem,
        column=columnitem,
        usercolumn=usercolumnitem,
        usercolumnname=usercolumnitem.keys(),
        output=False,
    )


# def exporter(ref):
#     logger = get_run_logger()
#     logger.info("Start writing file...")
#     xanes_afterscan_plan(ref, roinum=1)
#     logger.info("Finish writing file.")

def xrf_loop(start_id, N, gui=None):
    auto_dir = "auto_rois/"
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
        try:
            print(h.start['scan']['type'], end="\t\t", flush=True)  # This might change
        except:
            print('UNKNOWN SCAN TYPE. SKIPPING')
            continue

        # Check if fly scan
        # Should be more generic, if XRF scan
        if h.start['scan']['type'] == 'XRF_FLY':
            # fname = filelist_h5[i]
            # Check if the file noes not exist
            # if not os.path.isfile(fname):
            if not glob.glob(f"scan2D_{scanid}_*.h5") and not os.path.isfile(
                f"scan2D_{scanid}.h5"
            ):
                # Check if the scan is done
                try:
                    db[scanid].stop['time']
                    make_hdf(scanid, completed_scans_only=True)
                    ttime.sleep(1)
                    if auto_roi_flag is True:
                        autoroi_xrf(scanid, auto_dir=auto_dir)
                        ttime.sleep(1)
                        create_pdf(scanid, auto_dir=auto_dir)
                except KeyError:
                    print('Scan not complete...')
                    pass
                except Exception:
                    traceback.print_exc()
                    pass
            else:   
                print(f"XRF HDF5 already created.")
        elif h.start['scan']['type'] == 'XAS_STEP':
            # Check if file exists
            # filepath = f"scan_{h.start['scan_id']}_xanes.txt"  # noqa: E501
            if not glob.glob(f"scan_{scanid}_xanes.txt") and not os.path.isfile(f"scan_{scanid}_xanes.txt"):
                # Check if scan is done
                try:
                    db[scanid].stop['time']
                    # Make file
                    # xanes_afterscan_plan(scanid, filename, roinum)
                    # xanes_afterscan_plan(scanid, f"scan{scanid}.xdi", [1])
                    xanes_afterscan_plan(ref, roinum=1)
                except KeyError:
                    print("Scan not complete...")
                    pass
                except Exception:
                    traceback.print_exc()
                    pass
            else:
                print("XDI already created")
        else:
            print()

        # Clear the db cache then return
        db._catalog._entries.cache_clear()

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

