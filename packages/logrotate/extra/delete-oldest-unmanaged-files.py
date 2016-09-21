#!/opt/mesosphere/bin/python3

import logging
import os
import sys


def main(directory, max_files, managed_file):
    '''
    Finds all files under the given `directory` and checks if the number
    of files exceeds the `max_files`.  If so, deletes files starting from
    the oldest (except for the `managed_file`) until the `max_files` is
    no longer exceeded.

    @type directory: str, absolute path of the directory to clean up
    @type max_files: int, maximum number of files to keep
    @type managed_file: str, one file (i.e. leading log) to excempt from cleanup
    '''
    logging.basicConfig(format='%(levelname)-4s ] %(message)s',
                        level=logging.INFO)

    # For simplicity, convert all paths to absolute paths.
    directory = os.path.abspath(directory)
    managed_file = os.path.abspath(managed_file)

    # Build a list of all files.
    # TODO(josephw): Do we want to delete directories too?
    all_files = []
    for root, subdirectories, files in os.walk(directory):
        all_files += [os.path.join(root, name) for name in files]

    # Exempt the one managed file.  This is presumably the leading log file.
    all_files.remove(managed_file)

    logging.info("Found {0} files in log directory (max {1})".format(len(all_files), max_files))
    if len(all_files) <= max_files:
        return

    oldest_first = sorted(all_files, key=lambda x: os.stat(x).st_mtime)
    to_delete = oldest_first[0:len(all_files) - max_files]

    for path in to_delete:
        logging.info("Deleting unmanaged file inside log directory: {0}".format(path))
        os.remove(path)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: delete-oldest-unmanaged-files.py <directory> <max-files> <managed-file>")
        sys.exit(1)

    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
