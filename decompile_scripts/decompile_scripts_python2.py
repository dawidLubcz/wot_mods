#!/usr/bin/env python2
"""
Module for decompiling .pyc files in the World of Tanks game directory for python2.
Use python2.7 to run this script.
"""

import os
import uncompyle6


def try_to_decompile_rest_of_files(log_file):
    with open(log_file, 'r') as f_log:
        for line in f_log:
            file_path = line
            decompiled_file_path = os.path.splitext(file_path)[0] + ".py"
            with open(decompiled_file_path, 'w') as f_decompiled:
                try:
                    uncompyle6.decompile_file(str(file_path.strip()), f_decompiled)
                except Exception as e:
                    print("Failed to decompile file: %s, error: %s".format(file_path, str(e)))


def main():
    path = os.path.join(os.getcwd(), '.tmp/failed.log')
    try_to_decompile_rest_of_files(path)


if __name__ == '__main__':
    main()
