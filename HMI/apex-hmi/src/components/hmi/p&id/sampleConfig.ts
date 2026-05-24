import { ProcessGraphicConfig } from "./types";

// Sample P&ID Configuration for Compressor Station
export const sampleCompressorConfig: ProcessGraphicConfig = {
  id: "pid-compressor-001",
  name: "COMPRESSOR STATION C-101 - PROCESS OVERVIEW",
  width: 1200,
  height: 700,
  equipment: [
    // Compressor C-101
    {
      id: "eq-comp-101",
      name: "C-101",
      type: "compressor",
      x: 400,
      y: 350,
      rotation: 0,
      scale: 1,
      status: "running",
      linkedTags: ["TT-101", "ST-101", "VT-101", "CT-101"],
      statusTag: "ST-101",
    },
    // Motor M-101
    {
      id: "eq-motor-101",
      name: "M-101",
      type: "motor",
      x: 300,
      y: 350,
      rotation: 0,
      scale: 1,
      status: "running",
      linkedTags: ["TT-101", "CT-101"],
    },
    // Inlet Valve V-101
    {
      id: "eq-valve-101",
      name: "V-101",
      type: "valve",
      x: 200,
      y: 350,
      rotation: 0,
      scale: 0.7,
      status: "running",
      linkedTags: ["PT-101"],
    },
    // Discharge Valve V-102
    {
      id: "eq-valve-102",
      name: "V-102",
      type: "valve",
      x: 600,
      y: 350,
      rotation: 0,
      scale: 0.7,
      status: "running",
      linkedTags: ["PT-102"],
    },
    // Cooler E-101
    {
      id: "eq-exchanger-101",
      name: "E-101",
      type: "exchanger",
      x: 800,
      y: 350,
      rotation: 0,
      scale: 1,
      status: "running",
      linkedTags: ["TT-102"],
    },
    // Discharge Tank T-101
    {
      id: "eq-tank-101",
      name: "T-101",
      type: "tank",
      x: 1000,
      y: 350,
      rotation: 0,
      scale: 0.8,
      status: "running",
      linkedTags: ["LT-101", "PT-103"],
      statusTag: "LT-101",
    },
  ],
  pipes: [
    // Inlet pipe to V-101
    {
      id: "pipe-001",
      points: [
        { x: 100, y: 350 },
        { x: 175, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-101",
      color: "#00C851",
      width: 4,
      animated: true,
    },
    // V-101 to Motor
    {
      id: "pipe-002",
      points: [
        { x: 225, y: 350 },
        { x: 275, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-101",
      color: "#00C851",
      width: 4,
      animated: true,
    },
    // Motor to Compressor
    {
      id: "pipe-003",
      points: [
        { x: 325, y: 350 },
        { x: 370, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-101",
      color: "#00C851",
      width: 4,
      animated: true,
    },
    // Compressor to V-102
    {
      id: "pipe-004",
      points: [
        { x: 430, y: 350 },
        { x: 575, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-102",
      color: "#FFB300",
      width: 4,
      animated: true,
    },
    // V-102 to Cooler
    {
      id: "pipe-005",
      points: [
        { x: 625, y: 350 },
        { x: 770, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-102",
      color: "#FFB300",
      width: 4,
      animated: true,
    },
    // Cooler to Tank
    {
      id: "pipe-006",
      points: [
        { x: 830, y: 350 },
        { x: 960, y: 350 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-102",
      color: "#00C851",
      width: 4,
      animated: true,
    },
  ],
  tags: [
    // Inlet Pressure
    {
      id: "tag-pt-101",
      tagId: "PT-101",
      x: 150,
      y: 300,
      label: "PT-101",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    // Motor Temperature
    {
      id: "tag-tt-101",
      tagId: "TT-101",
      x: 300,
      y: 280,
      label: "TT-101",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    // Compressor Speed
    {
      id: "tag-st-101",
      tagId: "ST-101",
      x: 400,
      y: 280,
      label: "ST-101",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    // Discharge Pressure
    {
      id: "tag-pt-102",
      tagId: "PT-102",
      x: 650,
      y: 300,
      label: "PT-102",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    // Cooler Outlet Temp
    {
      id: "tag-tt-102",
      tagId: "TT-102",
      x: 800,
      y: 280,
      label: "TT-102",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    // Tank Level
    {
      id: "tag-lt-101",
      tagId: "LT-101",
      x: 1000,
      y: 280,
      label: "LT-101",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
  ],
};

// Sample P&ID for Pump Station
export const samplePumpConfig: ProcessGraphicConfig = {
  id: "pid-pump-001",
  name: "PUMP STATION P-201 - PROCESS OVERVIEW",
  width: 1000,
  height: 600,
  equipment: [
    // Source Tank
    {
      id: "eq-tank-201",
      name: "T-201",
      type: "tank",
      x: 150,
      y: 300,
      rotation: 0,
      scale: 0.8,
      status: "running",
      linkedTags: ["LT-201"],
      statusTag: "LT-201",
    },
    // Pump P-201
    {
      id: "eq-pump-201",
      name: "P-201",
      type: "pump",
      x: 400,
      y: 300,
      rotation: 0,
      scale: 1,
      status: "running",
      linkedTags: ["PT-201", "FT-201"],
    },
    // Discharge Valve
    {
      id: "eq-valve-201",
      name: "V-201",
      type: "valve",
      x: 600,
      y: 300,
      rotation: 0,
      scale: 0.7,
      status: "running",
      linkedTags: ["PT-202"],
    },
    // Destination Tank
    {
      id: "eq-tank-202",
      name: "T-202",
      type: "tank",
      x: 850,
      y: 300,
      rotation: 0,
      scale: 0.8,
      status: "running",
      linkedTags: ["LT-202"],
      statusTag: "LT-202",
    },
  ],
  pipes: [
    {
      id: "pipe-201",
      points: [
        { x: 190, y: 300 },
        { x: 370, y: 300 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-201",
      color: "#00C851",
      width: 4,
      animated: true,
    },
    {
      id: "pipe-202",
      points: [
        { x: 430, y: 300 },
        { x: 575, y: 300 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-201",
      color: "#00C851",
      width: 4,
      animated: true,
    },
    {
      id: "pipe-203",
      points: [
        { x: 625, y: 300 },
        { x: 810, y: 300 },
      ],
      flowDirection: "forward",
      flowRateTag: "FT-201",
      color: "#00C851",
      width: 4,
      animated: true,
    },
  ],
  tags: [
    {
      id: "tag-lt-201",
      tagId: "LT-201",
      x: 150,
      y: 200,
      label: "LT-201",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    {
      id: "tag-pt-201",
      tagId: "PT-201",
      x: 400,
      y: 240,
      label: "PT-201",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    {
      id: "tag-ft-201",
      tagId: "FT-201",
      x: 500,
      y: 280,
      label: "FT-201",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
    {
      id: "tag-lt-202",
      tagId: "LT-202",
      x: 850,
      y: 200,
      label: "LT-202",
      showValue: true,
      showUnit: true,
      fontSize: 12,
    },
  ],
};
