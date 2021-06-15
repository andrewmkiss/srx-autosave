import h5py
import numpy as np
import pyxrf
from pyxrf.model.scan_metadata import *
from pyxrf.core.utils import *
from pyxrf.model.load_data_from_db import _get_fpath_not_existing, helper_encode_list
#from databroker import Broker
#db = Broker.named("srx")
try:
    from databroker.v0 import Broker
except ModuleNotFoundError:
    from databroker import Broker

if not db:
    # Register the data broker
    try:
        db = Broker.named("srx")
    except AttributeError:
        db = Broker.named("temp")
        print("Using temporary databroker.")

pyxrf_version = pyxrf.__version__


def _extract_metadata_from_header(hdr):
    """
    Extract metadata from start and stop document. Metadata extracted from other document
    in the scan are beamline specific and added to dictionary at later time.
    """
    start_document = hdr.start

    mdata = ScanMetadataXRF()

    data_locations = {
        "scan_id": ["scan_id"],
        "scan_uid": ["uid"],
        "scan_instrument_id": ["beamline_id"],
        "scan_instrument_name": [],
        "scan_time_start": ["time"],
        "scan_time_start_utc": ["time"],

        "instrument_mono_incident_energy": ["scan/energy"],
        "instrument_beam_current": [],
        "instrument_detectors": ["detectors"],

        "sample_name": ["scan/sample_name"],

        "experiment_plan_name": ["plan_name"],
        "experiment_plan_type": ["plan_type"],
        "experiment_fast_axis": ["scan/fast_axis/motor_name"],
        "experiment_slow_axis": ["scan/slow_axis/motor_name"],

        "proposal_num": ["proposal/proposal_num"],
        "proposal_title": ["proposal/proposal_title"],
        "proposal_PI_lastname": ["proposal/PI_lastname"],
        "proposal_saf_num": ["proposal/saf_num"],
        "proposal_cycle": ["proposal/cycle"]
    }

    for key, locations in data_locations.items():
        # Go to the next key if no location is defined for the current key.
        #   No locations means that the data is not yet defined in start document on any beamline
        #   Multiple locations point to locations at different beamlines
        if not locations:
            continue

        # For each metadata key there could be none, one or multiple locations in the start document
        for loc in locations:
            path = loc.split('/')  #
            ref = start_document
            for n, p in enumerate(path):
                if n >= len(path) - 1:
                    break
                # 'ref' must always point to dictionary
                if not isinstance(ref, dict):
                    ref = None
                    break
                if p in ref:
                    ref = ref[p]
                else:
                    ref = None
                    break
            # At this point 'ref' must be a dictionary
            value = None
            if ref is not None and isinstance(ref, dict):
                if path[-1] in ref:
                    value = ref[path[-1]]
            # Now we finally arrived to the end of the path: the 'value' must be a scalar or a list
            if value is not None and not isinstance(value, dict):
                if path[-1] == 'time':
                    if key.endswith("_utc"):
                        value = convert_time_to_nexus_string(ttime.gmtime(value))
                    else:
                        value = convert_time_to_nexus_string(ttime.localtime(value))
                mdata[key] = value
                break

    stop_document = hdr.stop

    if stop_document:

        if "time" in stop_document:
            t = stop_document["time"]
            mdata["scan_time_stop"] = convert_time_to_nexus_string(ttime.localtime(t))
            mdata["scan_time_stop_utc"] = convert_time_to_nexus_string(ttime.gmtime(t))

        if "exit_status" in stop_document:
            mdata["scan_exit_status"] = stop_document["exit_status"]

    else:

        mdata["scan_exit_status"] = "incomplete"

    # Add full beamline name (if available, otherwise don't create the entry).
    #   Also, don't overwrite the existing name if it was read from the start document
    if "scan_instrument_id" in mdata and "scan_instrument_name" not in mdata:
        instruments = {
            "srx": "Submicron Resolution X-ray Spectroscopy",
            "hxn": "Hard X-ray Nanoprobe",
            "tes": "Tender Energy X-ray Absorption Spectroscopy",
            "xfm": "X-ray Fluorescence Microprobe"
        }
        iname = instruments.get(mdata["scan_instrument_id"].lower(), "")
        if iname:
            mdata["scan_instrument_name"] = iname

    return mdata


def new_makehdf(scanid=-1, create_each_det=False):

    # Get scan header
    h = db[int(scanid)]
    scanid = int(h.start['scan_id'])

    #if h.stop["exit_status"] == "success"

    start_doc = h.start
    scan_doc = h.start['scan']
    
    # Check if new type of metadata
    if 'md_version' not in h.start:
        print('Please use old make_hdf.')
        return

    # Check for detectors
    dets = []
    try:
        if 'xs' in h.start['scan']['detectors']:
            dets.append('xs')
        elif 'xs2' in h.start['scan']['detectors']:
            dets.append('xs2')
    except KeyError:
        # AMK forgot to add detectors to step scans
        if scan_doc['type'] == 'XRF_STEP':
            dets.append('xs')

    if dets == []:
        print('No detectors found!')
        return

    # Get metadata
    mdata = _extract_metadata_from_header(h)

    # Get position data from scan
    c, r = h.start['scan']['shape']
    if scan_doc['type'] == 'XRF_FLY':
        fast_motor = scan_doc['fast_axis']['motor_name']
        if (fast_motor == 'nano_stage_sx'):
            fast_key = 'enc1'
        elif (fast_motor == 'nano_stage_sy'):
            fast_key = 'enc2'
        elif (fast_motor == 'nano_stage_sz'):
            fast_key = 'enc3'
        else:
            print(f'{fast_motor} not found!')
            return

        slow_motor = scan_doc['slow_axis']['motor_name']
        if (slow_motor == 'nano_stage_sx'):
            slow_key = 'enc1'
        elif (slow_motor == 'nano_stage_sy'):
            slow_key = 'enc2'
        elif (slow_motor == 'nano_stage_sz'):
            slow_key = 'enc3'
        else:
            slow_key = slow_motor
    
        fast_pos = h.data(fast_key, stream_name='stream0', fill=True)
        fast_pos = np.array(list(fast_pos))
        if 'enc' in slow_key:
            slow_pos = h.data(slow_key, stream_name='stream0', fill=True)
            slow_pos = np.array(list(slow_pos))
        else:
            slow_pos = h.data(slow_key, stream_name='primary', fill=True)
            slow_pos = np.array(list(slow_pos))
            slow_pos = np.array([slow_pos,]*c).T

        pos_pos = np.zeros((2, r, c))
        if 'x' in slow_key:
            pos_pos[1, :, :] = fast_pos
            pos_pos[0, :, :] = slow_pos
        else:
            pos_pos[0, :, :] = fast_pos
            pos_pos[1, :, :] = slow_pos
        pos_name = ['x_pos', 'y_pos']

        # Get detector data
        if 'xs' in dets:
        # if 'fluor' in h.table('stream0').keys():
            d_xs = np.array(list(h.data('fluor', stream_name='stream0', fill=True)))
            N_xs = d_xs.shape[2]
            d_xs_sum = np.squeeze(np.sum(d_xs, axis=2))
        if 'xs2' in dets:
        # if 'fluor_xs2' in h.table('stream0').keys():
            d_xs2 = np.array(list(h.data('fluor_xs2', stream_name='stream0', fill=True)))
            N_xs2 = d_xs2.shape[2]
            d_xs2_sum = np.squeeze(np.sum(d_xs2, axis=2))

        
        # Scaler list
        sclr_list = ['i0', 'i0_time', 'time', 'im', 'it']
        sclr = []
        sclr_name = []
        for s in sclr_list:
            if s in h.table('stream0').keys():
                tmp = np.array(list(h.data(s, stream_name='stream0', fill=True)))
                sclr.append(tmp)
                sclr_name.append(s)
        sclr = np.array(sclr)
        sclr = np.moveaxis(sclr, 0, -1)
    if scan_doc['type'] == 'XRF_STEP':
        # Define keys for motor data
        fast_motor = scan_doc['fast_axis']['motor_name']
        fast_key = fast_motor + '_user_setpoint'
        slow_motor = scan_doc['slow_axis']['motor_name']
        slow_key = slow_motor + '_user_setpoint'

        # Collect motor positions
        fast_pos = h.data(fast_key, stream_name='primary', fill=True)
        fast_pos = np.array(list(fast_pos))
        slow_pos = h.data(slow_key, stream_name='primary', fill=True)
        slow_pos = np.array(list(slow_pos))

        # Reshape motor positions
        r, c = scan_doc['shape']
        fast_pos = np.reshape(fast_pos, (r, c))
        slow_pos = np.reshape(slow_pos, (r, c))

        # Put into one array for h5 file
        pos_pos = np.zeros((2, r, c))
        if 'x' in slow_key:
            pos_pos[1, :, :] = fast_pos
            pos_pos[0, :, :] = slow_pos
        else:
            pos_pos[0, :, :] = fast_pos
            pos_pos[1, :, :] = slow_pos
        pos_name = ['x_pos', 'y_pos']


        # Get detector data
        keys = h.table().keys()
        MAX_DET_ELEMENTS = 7
        for i in np.arange(1, MAX_DET_ELEMENTS+1):
            if f'xs_channel{i}' in keys:
                N_xs = i
            else:
                break
        N_pts = r * c
        N_bins= 4096
        if 'xs' in dets:
            d_xs = np.empty((N_xs, N_pts, N_bins))
            for i in np.arange(0, N_xs):
                d = h.data(f'xs_channel{i+1}', fill=True)
                d = np.array(list(d))
                d_xs[i, :, :] = np.copy(d)
            del d
            # Reshape data
            d_xs = np.reshape(d_xs, (N_xs, r, c, N_bins))
            # Sum data
            d_xs_sum = np.squeeze(np.sum(d_xs, axis=0))

        # Scaler list
        sclr_list = ['sclr_i0', 'sclr_im', 'sclr_it']
        sclr_name = []
        for s in sclr_list:
            if s in keys:
                sclr_name.append(s)
        sclr = np.array(h.table()[sclr_name].values)
        # sclr = np.moveaxis(sclr, 0, 1)
        sclr = np.reshape(sclr, (r, c, len(sclr_name)))

        # Consider snake
        # pos_pos, d_xs, d_xs_sum, sclr
        if scan_doc['snake'] == 1:
            pos_pos[:, 1::2, :] = pos_pos[:, 1::2, ::-1]
            d_xs[:, 1::2, :, :] = d_xs[:, 1::2, ::-1, :]
            d_xs_sum[1::2, :, :] = d_xs_sum[1::2, ::-1, :]
            sclr[1::2, :, :] = sclr[1::2, ::-1, :]
            

    # Write file
    interpath = 'xrfmap'
    for d in dets:
        if d == 'xs':
            tmp_data = d_xs
            tmp_data_sum = d_xs_sum
            N = N_xs
        elif d == 'xs2':
            tmp_data = d_xs2
            tmp_data_sum = d_xs2_sum
            N = N_xs2
 
        if (create_each_det):
            fn = f'scan2D_{scanid}_{d}_{N}ch.h5'
        else:
            fn = f'scan2D_{scanid}_{d}_sum{N}ch.h5'
        
        file_open_mode = 'a'
        fname_add_version = True
        file_overwrite_existing = False
        if fname_add_version:
            fpath = _get_fpath_not_existing(fn)
        else:
            if file_overwrite_existing:
                file_open_mode = 'w'
            else:
                print('File already exists!')
                return
 
        with h5py.File(fn, file_open_mode) as f:
             # Create metadata group
            metadata_grp = f.create_group(f"{interpath}/scan_metadata")
            # This group of attributes are always created. It doesn't matter if metadata
            #   is provided to the function.
            metadata_grp.attrs["file_type"] = "XRF-MAP"
            metadata_grp.attrs["file_format"] = "NSLS2-XRF-MAP"
            metadata_grp.attrs["file_format_version"] = "1.0"
            metadata_grp.attrs["file_software"] = "PyXRF"
            metadata_grp.attrs["file_software_version"] = pyxrf_version
            # Present time in NEXUS format (should it be UTC time)?
            metadata_grp.attrs["file_created_time"] = ttime.strftime("%Y-%m-%dT%H:%M:%S+00:00", ttime.localtime())
    
            # Now save the rest of the scan metadata if metadata is provided
            if mdata:
                # We assume, that metadata does not contain repeated keys. Otherwise the
                #   entry with the last occurrence of the key will override the previous ones.
                for key, value in mdata.items():
                    metadata_grp.attrs[key] = value
    
            if create_each_det is True:
                for i in range(N_xs):
                    grp = f.create_group(interpath+f'/det{i+1}')
                    grp.create_dataset('counts', data=np.squeeze(tmp_data[:, :, i, :]), compression='gzip')
 
            # summed data
            dataGrp = f.create_group(interpath+'/detsum')
            ds_data = dataGrp.create_dataset('counts', data=tmp_data_sum,
                                                 compression='gzip')
    
            # add positions
            dataGrp = f.create_group(interpath+'/positions')
            dataGrp.create_dataset('name', data=helper_encode_list(pos_name))
            dataGrp.create_dataset('pos', data=pos_pos)
    
            # scaler data
            dataGrp = f.create_group(interpath+'/scalers')
            dataGrp.create_dataset('name', data=helper_encode_list(sclr_name))
            dataGrp.create_dataset('val', data=sclr)


def add_ydata(fn):
    # This is for old metadata style and flyscans in x only

    # Get scan ID
    _, scanid, _, _ = fn.split('_')
    scanid = int(scanid)

    # Get scan header
    h = db[int(scanid)]
    scanid = int(h.start['scan_id'])
    start_doc = h.start
    
    # Get position data from scan
    y_pos = h.data('enc2', stream_name='stream0', fill=True)
    y_pos = np.array(list(y_pos))

    # Write to file
    with h5py.File(fn, 'a') as f:
        # pos = f['/xrfmap/positions/pos']
        pos = np.array(f['/xrfmap/positions/pos'])
        pos_name = f['/xrfmap/positions/name']

        ind = list(pos_name).index(b'y_pos')  # This should be 1, but good to verify
        pos[ind, :, :] = y_pos
        # pos[ind, :, :] = y_pos[np.newaxis, ...]
        f['/xrfmap/positions/pos'][...] = pos

