# Import packages
import numpy as np
import time as ttime
import os
import glob


# %% Main loop for XRF maps -> HDF5
def autosave_xrf(start_id, wd="", N=1000, dt=60):
    """
    SRX Autosave

    Setup the main loop to automatically download and make the HDF5s

    Parameters
    ----------
    start_id : int
        Starting scan ID
    wd : string
        Path to write the HDF5 files
    N : int
        Number of scan IDs to search for, start_id + N
    dt : int
        Time, in seconds, to wait before trying to make more files

    Returns
    -------
    None

    Examples
    --------
    Start downloading and creating HDF5 files and saving them into the user's directory
    >>> autosave_xrf(1234, wd='/home/xf05id1/current_user_data/, N=1000, dt=60)

    """

    # Check the input parameters
    if start_id < 0:
        # Need to add 1 to scan ID
        # Otherwise it will grab the current value (which would be from the previous user)
        start_id = get_current_scanid() + 1
        print(f"Using startind scan ID: {start_id}")
    if wd == "":
        wd = os.getcwd()
        print(f"Using current directory.\n{wd}")
    os.chdir(wd)
    if N < 1:
        # Add logic later that if N < 1, then always use current scan ID
        print("Warning: N changed to 100.")
        N = 100
    if dt < 1:
        print("Warning: dt changed to 1 second.")
        dt = 1

    print("--------------------------------------------------")

    # Build the possible list of scan IDs and filenames
    num = np.arange(start_id, start_id + N, 1)
    # Maybe a function for this
    # make_XRF_fn(scan_id) -> return 'scan2D_{scanid}.h5'
    # filelist_h5 = ['scan2D_' + str(n) + '.h5' for n in num]

    # Enter the main loop
    def mainloop():
        for i in range(N):
            # Check if the scan ID exists
            # We could make a function to check if current scan ID
            # >= this value. Or same thing but return True/False
            scanid = int(num[i])
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
                    except Exception:
                        pass
                else:
                    print("XRF HDF5 already created.")
            else:
                print()

        print("\nSleeping for %d seconds...Press Ctrl-C to exit" % (dt), flush=True)
        t0 = ttime.monotonic()
        del_t = 0.0
        while del_t < dt:
            print("   %02d seconds remaining..." % (dt - del_t), end="\r", flush=True)
            ttime.sleep(0.5)
            del_t = ttime.monotonic() - t0
        print("--------------------------------------------------")

    try:
        while True:
            mainloop()
    except KeyboardInterrupt:
        print("\n\nExiting SRX AutoSave.")
        pass
