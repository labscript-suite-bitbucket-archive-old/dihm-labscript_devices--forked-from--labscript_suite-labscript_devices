#####################################################################
#                                                                   #
# /labscript_devices/PylonCamera/blacs_tabs.py                      #
#                                                                   #
# Copyright 2019, Monash University and contributors                #
#                                                                   #
# This file is part of labscript_devices, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

from labscript_devices.IMAQdxCamera.blacs_tabs import IMAQdxCameraTab

class PylonCameraTab(IMAQdxCameraTab):
    
    # override worker class
    worker_class = 'labscript_devices.PylonCamera.blacs_workers.PylonCameraWorker'

    device_properties={'ExposureTime':{'default':9000,
                                       'type':'num',
                                       'min':0,
                                       'max':35000,
                                       'base_unit':'us',
                                       'step':1,
                                       'decimals':0},
                        'CenterX':{'default':False, # for demonstration, remove before merge
                                   'type':'bool'},
                        'TestImageSelector':{'default':'Off',
                        			    'type':'enum',
                        			    'options':{'Off':0,
                        			    		   'Testimage1':{'index':1,'tooltip':'Angled Stripes'},
                        			    		   'Testimage2':{'index':2,'tooltip':'Offset Angled Stripes'}
                        			    		   }
                        			    	},
                        'PixelFormat':{'default':'Mono12',
                        			   'type':'enum',
                        			   'options':['Mono8','Mono12','Mono12p']}
                        }
                        			    # enum options can be list or dict of strings
                        			    # if dict, only uses keys for enum labels 
