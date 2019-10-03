
""" 
Download and unpack use example

from utils import *

url = "https://wintesting.s3.amazonaws.com/testing/packages/adminrouter/adminrouter--19c887e02f1a8325cabd980f039015b70ab19cee.tar.xz"
path = "./tmp/"
if is_downloadable(url):
  archive =  download(url, path)
else:
    print("{} \nis not downloadable!!!".format(url))

print("this is {}".format(archive))
unpack(archive, "./tmp/Arc/")

"""

import requests
from pySmartDL import SmartDL
import os
import tarfile
from pprint import pprint as pp

def is_downloadable(url):
    """
    Does the url contain a downloadable resource
    """
    h = requests.head(url, allow_redirects=True)
    header = h.headers
    content_type = header.get('content-type')
    if 'text' in content_type.lower():
        return False
    if 'html' in content_type.lower():
        return False
    return True

def download(url, location):
    """
    Downloads from url to location
    uses  pySmartDL from https://pypi.org/project/pySmartDL/
    """
    _location = os.path.abspath(location)
    dl = SmartDL(url, _location)
    dl.start()
    path = os.path.abspath(dl.get_dest())
    print ("Downloaded to {} ".format(path), " from {}".format(url),sep='\n')
    return path

def unpack(tarpath, location):
    """
    unpacks tar.xz to  location
    """
    
    _location = os.path.abspath(location)

    if  not os.path.exists(_location):
        print("no Directory exist creating...\n{}".format(_location))
        os.mkdir(_location)

    with tarfile.open(tarpath) as tar:
        tar.extractall(_location)
        print("extracted to {}".format(_location)) 
        pp({tarinfo.name:tarinfo.size for tarinfo in tar})
    return _location

