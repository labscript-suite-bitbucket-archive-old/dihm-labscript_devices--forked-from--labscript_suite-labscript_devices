#####################################################################
#                                                                   #
# /TekScope.py                                                      #
#                                                                   #
#                                                                   #
#####################################################################

import numpy as np
from labscript_devices import labscript_device, BLACS_tab, BLACS_worker
from labscript_devices.VISA import VISATab, VISAWorker
from labscript import Device, TriggerableDevice, AnalogIn, config, LabscriptError, set_passed_properties
import labscript_utils.properties

class ScopeChannel(AnalogIn):
    """Labscript device that handles acquisition stuff.
    Connection should be in list of TekScope channels list."""
    description = 'Scope Acquisition Channel Class'
    def __init__(self, name, parent_device, connection):
        Device.__init__(self,name,parent_device,connection)
        self.acquisitions = []
        
    def acquire(self,label,start_time):
        if self.acquisitions:
            raise LabscriptError('Scope Channel %s:%s can only have one acquisition!' % (self.parent_device.name,self.name))
        else:
            self.acquisitions.append({'start_time': start_time,
                                    'label': label})
      
@labscript_device              
class TekScope(TriggerableDevice):
    description = 'Tektronics Digital Oscilliscope'
    allowed_children = [ScopeChannel]
    trigger_duration = 1e-3
    
    @set_passed_properties()
    def __init__(self, name,VISA_name, trigger_device, trigger_connection, **kwargs):
        '''VISA_name can be full VISA connection string or NI-MAX alias.
        Trigger Device should be fast clocked device. '''
        self.BLACS_connection = VISA_name
        TriggerableDevice.__init__(self,name,trigger_device,trigger_connection,**kwargs)
        
        
    def generate_code(self, hdf5_file):
            
        Device.generate_code(self, hdf5_file)
        
        acquisitions = []
        for channel in self.child_devices:
            if channel.acquisitions:
                acquisitions.append((channel.connection,channel.acquisitions[0]['label'],
                channel.acquisitions[0]['start_time']))
        acquisition_table_dtypes = [('connection','a256'),('label','a256'),
                                        ('start_time',float)]
        acquisition_table = np.empty(len(self.child_devices),dtype=acquisition_table_dtypes)
        for i, acq in enumerate(acquisitions):
            acquisition_table[i] = acq   
        
        grp = self.init_device_group(hdf5_file)
        # write table to h5file if non-empty
        if len(acquisition_table):
            grp.create_dataset('ACQUISITIONS',compression=config.compression,
                                data=acquisition_table)
                                
    def acquire(self,start_time):
        '''Call to define time when trigger will happen for scope.'''
        if not self.child_devices:
            raise LabscriptError('No channels acquiring for trigger %s'%self.name)
        else:
            self.parent_device.trigger(start_time,self.trigger_duration)
            for channel in self.child_devices:
                channel.acquire(channel.name,start_time)

@BLACS_tab
class TekScopeTab(VISATab):
    # Status Byte Label Definitions for TDS200/1000/2000 series scopes
    status_byte_labels = {'bit 7':'Unused', 
                          'bit 6':'MSS',
                          'bit 5':'ESB',
                          'bit 4':'MAV',
                          'bit 3':'Unused',
                          'bit 2':'Unused',
                          'bit 1':'Unused',
                          'bit 0':'Unused'}
    
    def __init__(self,*args,**kwargs):
        if not hasattr(self,'device_worker_class'):
            self.device_worker_class = TekScopeWorker
        VISATab.__init__(self,*args,**kwargs)
    
    def initialise_GUI(self):
        # Call the VISATab parent to initialise the STB ui and set the worker
        VISATab.initialise_GUI(self)

        # Set the capabilities of this device
        self.supports_remote_value_check(False)
        self.supports_smart_programming(True) 
        self.statemachine_timeout_add(5000, self.status_monitor)        
       
import h5py
@BLACS_worker
class TekScopeWorker(VISAWorker):   
    # define instrument specific read and write strings
    setup_string = ':HEADER OFF;*ESE 60;*SRE 32; *CLS;'
    read_setup_string = ':DATA:SOURCE CH%d;:DAT:ENC RPB;WID 2;'
    read_waveform_parameters_string = ':WFMPRE:XZE?;XIN?;YZE?;YMU?;YOFF?;'
    read_waveform_string = 'CURV?'
    
    # define result parsers, if necessary
    def waveform_parser(self,raw_waveform_array,y0,dy,yoffset):
        '''Parses the numpy array from the CURV? query.'''
        return (raw_waveform_array - yoffset)*dy + y0
    
    def init(self):
        # call the h5py lock and import
        #global h5py; import labscript_utils.h5_lock, h5py
        # Call the VISA init to initialise the VISA connection
        VISAWorker.init(self)
        # Override the timeout for longer scope waits
        self.connection.timeout = 10000
        
        # initialization stuff would go here
        self.connection.write(self.setup_string)
        
        # Query device name to ensure supported scope
        ident_string = self.connection.query('*IDN?')
        if ('TEKTRONIX,TDS 2' in ident_string) or ('TEKTRONIX,TDS 1' in ident_string):
            # Scope supported!
            return
        else:
            raise LabscriptError('Device %s with VISA name %s not supported!' % (ident_string,self.VISA_name))        
            
    def transition_to_manual(self,abort = False):
        if not abort:         
            with h5py.File(self.h5_file,'r') as hdf5_file:
                try:
                    # get acquisitions table values so we can close the file
                    acquisitions = hdf5_file['/devices/'+self.device_name+'/ACQUISITIONS'].value
                except:
                        # No acquisitions!
                        return
            # close lock on h5 to read from scope, it takes a while            
            data = {}
            for connection,label,start_time in acquisitions:
                channel_num = int(connection.split(' ')[-1])
                [t0,dt,y0,dy,yoffset] = self.connection.query_ascii_values(self.read_setup_string % channel_num +
                self.read_waveform_parameters_string, container=np.array, separator=';')
                raw_data = self.connection.query_binary_values(self.read_waveform_string,
                datatype='H', is_big_endian=True)
                data[connection] = self.waveform_parser(raw_data,y0,dy,yoffset)
            # Need to calculate the time array
            num_points = len(raw_data)
            tarray = np.arange(0,num_points,1,dtype=np.float64)*dt - t0
            data['time'] = tarray  
            # define the dtypes for the h5 arrays
            dtypes = [('t', np.float64),('values', np.float32)]          
            
            # re-open lock on h5file to save data
            with h5py.File(self.h5_file,'a') as hdf5_file:
                try:
                    measurements = hdf5_file['/data/traces']
                except:
                    # Group doesn't exist yet, create it
                    measurements = hdf5_file.create_group('/data/traces')
                # write out the data to the h5file
                for connection,label,start_time in acquisitions:
                    values = np.empty(num_points,dtype=dtypes)
                    values['t'] = tarray
                    values['values'] = data[connection]
                    measurements.create_dataset(label, data=values)
                    # and save some timing info for reference to labscript time
                    measurements[label].attrs['start_time'] = start_time
            
            
        return True

