-- Update hierarchical data for Matrikon OPC signals in the tag_master table

-- Update for Boiler FD Fan Speed
UPDATE tag_master
SET 
    description = 'Forced draft fan speed',
    plant = 'Plant1',
    area = 'Area1',
    equipment = 'Boiler1',
    sub_equipment = 'FD Fan',
    components = 'ST-602 FD Fan Speed Transmitter'
WHERE tag_id = 'BOILER_FD_FAN_SPEED_RPM';

-- Update for Random.UInt2
UPDATE tag_master
SET 
    description = 'Random Unsigned Integer 2',
    plant = 'Plant1',
    area = 'Area1',
    equipment = 'Equipment1',
    sub_equipment = NULL,
    components = NULL
WHERE tag_id = 'Random.UInt2';