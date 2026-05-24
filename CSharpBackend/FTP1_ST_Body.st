(* ----------------------------------------------------
 * FTP-1 POTLINE Simulation
 * Same pattern as welding sim: one sim_step, SIN-based
 * Runs in main task. Set Sim_Enable := 1 to activate.
 * ----------------------------------------------------*)

IF Sim_Enable THEN

    (* Advance shared angle — same as welding sim_step *)
    sim_step := sim_step + 0.07;
    IF sim_step > 6.28 THEN sim_step := 0.0; END_IF;

    (* PY1101A [KPA] base=1.135 ±0.5938 range 0.51..1.76 *)
    PY1101A := 1.135 + (SIN(sim_step + 0.0) * 0.5938);

    (* PY1101B [KPA] base=1.11 ±0.4085 range 0.68..1.54 *)
    PY1101B := 1.11 + (SIN(sim_step + 0.39) * 0.4085);

    (* PY1103A [KPA] base=17.2 ±6.65 range 10.2..24.2 *)
    PY1103A := 17.2 + (SIN(sim_step + 0.78) * 6.65);

    (* PY1103B [KPA] base=16.4 ±4.275 range 11.9..20.9 *)
    PY1103B := 16.4 + (SIN(sim_step + 1.17) * 4.275);

    (* TY1101A [°C] base=58.725 ±19.4513 range 38.25..79.2 *)
    TY1101A := 58.725 + (SIN(sim_step + 1.56) * 19.4513);

    (* PY1104 [KPA] base=7.2 ±3.61 range 3.4..11.0 *)
    PY1104 := 7.2 + (SIN(sim_step + 1.95) * 3.61);

    (* PY1105A [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105A := 0.3938 + (SIN(sim_step + 2.34) * 0.2529);

    (* PY1105B [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105B := 0.3938 + (SIN(sim_step + 2.73) * 0.2529);

    (* PY1105C [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105C := 0.3938 + (SIN(sim_step + 3.12) * 0.2529);

    (* PY1105D [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105D := 0.3938 + (SIN(sim_step + 3.51) * 0.2529);

    (* PY1105E [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105E := 0.3938 + (SIN(sim_step + 3.9) * 0.2529);

    (* PY1105F [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105F := 0.3938 + (SIN(sim_step + 4.29) * 0.2529);

    (* PY1105G [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105G := 0.3938 + (SIN(sim_step + 4.68) * 0.2529);

    (* PY1105H [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105H := 0.3938 + (SIN(sim_step + 5.07) * 0.2529);

    (* PY1105I [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105I := 0.3938 + (SIN(sim_step + 5.46) * 0.2529);

    (* PY1105J [KPA] base=0.3938 ±0.2529 range 0.1275..0.66 *)
    PY1105J := 0.3938 + (SIN(sim_step + 5.85) * 0.2529);

    (* TY1101B [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101B := 75.0 + (SIN(sim_step + 0.0) * 42.75);

    (* TY1101C [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101C := 75.0 + (SIN(sim_step + 0.39) * 42.75);

    (* TY1101D [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101D := 75.0 + (SIN(sim_step + 0.78) * 42.75);

    (* TY1101E [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101E := 75.0 + (SIN(sim_step + 1.17) * 42.75);

    (* TY1101F [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101F := 75.0 + (SIN(sim_step + 1.56) * 42.75);

    (* TY1101G [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101G := 75.0 + (SIN(sim_step + 1.95) * 42.75);

    (* TY1101H [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1101H := 75.0 + (SIN(sim_step + 2.34) * 42.75);

    (* TY1102A [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102A := 75.0 + (SIN(sim_step + 2.73) * 42.75);

    (* TY1102B [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102B := 75.0 + (SIN(sim_step + 3.12) * 42.75);

    (* TY1102C [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102C := 75.0 + (SIN(sim_step + 3.51) * 42.75);

    (* TY1102D [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102D := 75.0 + (SIN(sim_step + 3.9) * 42.75);

    (* TY1102E [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102E := 75.0 + (SIN(sim_step + 4.29) * 42.75);

    (* TY1102F [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102F := 75.0 + (SIN(sim_step + 4.68) * 42.75);

    (* TY1102G [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102G := 75.0 + (SIN(sim_step + 5.07) * 42.75);

    (* TY1102H [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1102H := 75.0 + (SIN(sim_step + 5.46) * 42.75);

    (* TY1103A [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103A := 75.0 + (SIN(sim_step + 5.85) * 42.75);

    (* TY1103B [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103B := 75.0 + (SIN(sim_step + 0.0) * 42.75);

    (* TY1103C [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103C := 75.0 + (SIN(sim_step + 0.39) * 42.75);

    (* TY1103D [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103D := 75.0 + (SIN(sim_step + 0.78) * 42.75);

    (* TY1103E [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103E := 75.0 + (SIN(sim_step + 1.17) * 42.75);

    (* TY1103F [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103F := 75.0 + (SIN(sim_step + 1.56) * 42.75);

    (* TY1103G [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103G := 75.0 + (SIN(sim_step + 1.95) * 42.75);

    (* TY1103H [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1103H := 75.0 + (SIN(sim_step + 2.34) * 42.75);

    (* TY1104A [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104A := 75.0 + (SIN(sim_step + 2.73) * 42.75);

    (* TY1104B [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104B := 75.0 + (SIN(sim_step + 3.12) * 42.75);

    (* TY1104C [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104C := 75.0 + (SIN(sim_step + 3.51) * 42.75);

    (* TY1104D [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104D := 75.0 + (SIN(sim_step + 3.9) * 42.75);

    (* TY1104E [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104E := 75.0 + (SIN(sim_step + 4.29) * 42.75);

    (* TY1104F [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104F := 75.0 + (SIN(sim_step + 4.68) * 42.75);

    (* TY1104G [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104G := 75.0 + (SIN(sim_step + 5.07) * 42.75);

    (* TY1104H [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1104H := 75.0 + (SIN(sim_step + 5.46) * 42.75);

    (* IYAN1101 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYAN1101 := 45.0 + (SIN(sim_step + 5.85) * 33.25);

    (* IYAN1102 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYAN1102 := 45.0 + (SIN(sim_step + 0.0) * 33.25);

    (* IYAN1103 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYAN1103 := 45.0 + (SIN(sim_step + 0.39) * 33.25);

    (* IYAN1104 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYAN1104 := 45.0 + (SIN(sim_step + 0.78) * 33.25);

    (* IYFBR1101 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYFBR1101 := 45.0 + (SIN(sim_step + 1.17) * 33.25);

    (* IYFBR1102 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYFBR1102 := 45.0 + (SIN(sim_step + 1.56) * 33.25);

    (* IYFBC1101 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYFBC1101 := 45.0 + (SIN(sim_step + 1.95) * 33.25);

    (* IYFBC1102 [Amp] base=45.0 ±33.25 range 10.0..80.0 *)
    IYFBC1102 := 45.0 + (SIN(sim_step + 2.34) * 33.25);

    (* HZ1101A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1101A := 50.0 + (SIN(sim_step + 2.73) * 28.5);

    (* HZ1102A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1102A := 50.0 + (SIN(sim_step + 3.12) * 28.5);

    (* HZ1103A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1103A := 50.0 + (SIN(sim_step + 3.51) * 28.5);

    (* HZ1104A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1104A := 50.0 + (SIN(sim_step + 3.9) * 28.5);

    (* AY1101 [mg/m3] base=42.5 ±35.625 range 5.0..80.0 *)
    AY1101 := 42.5 + (SIN(sim_step + 4.29) * 35.625);

    (* AY1102 [mg/m3] base=42.5 ±35.625 range 5.0..80.0 *)
    AY1102 := 42.5 + (SIN(sim_step + 4.68) * 35.625);

    (* TY1105A [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1105A := 75.0 + (SIN(sim_step + 5.07) * 42.75);

    (* TY1105B [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY1105B := 75.0 + (SIN(sim_step + 5.46) * 42.75);

    (* PDY1101 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1101 := 1.8625 + (SIN(sim_step + 5.85) * 1.3656);

    (* PDY1102 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1102 := 1.8625 + (SIN(sim_step + 0.0) * 1.3656);

    (* PDY1104 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1104 := 1.8625 + (SIN(sim_step + 0.39) * 1.3656);

    (* PDY1105 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1105 := 1.8625 + (SIN(sim_step + 0.78) * 1.3656);

    (* PDY1106A [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1106A := 1.8625 + (SIN(sim_step + 1.17) * 1.3656);

    (* PDY1107A [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1107A := 1.8625 + (SIN(sim_step + 1.56) * 1.3656);

    (* PDY1108 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1108 := 1.8625 + (SIN(sim_step + 1.95) * 1.3656);

    (* PDY1109 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1109 := 1.8625 + (SIN(sim_step + 2.34) * 1.3656);

    (* PDY1110 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PDY1110 := 1.8625 + (SIN(sim_step + 2.73) * 1.3656);

    (* FY1100 [Nm3/Hr] base=2250.0 ±1662.5 range 500.0..4000.0 *)
    FY1100 := 2250.0 + (SIN(sim_step + 3.12) * 1662.5);

    (* VYAN1101A [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101A := 3.75 + (SIN(sim_step + 3.51) * 3.0875);

    (* VYAN1101B [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101B := 3.75 + (SIN(sim_step + 3.9) * 3.0875);

    (* VYAN1101C [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101C := 3.75 + (SIN(sim_step + 4.29) * 3.0875);

    (* VYAN1101D [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101D := 3.75 + (SIN(sim_step + 4.68) * 3.0875);

    (* VYAN1102A [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102A := 3.75 + (SIN(sim_step + 5.07) * 3.0875);

    (* VYAN1102B [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102B := 3.75 + (SIN(sim_step + 5.46) * 3.0875);

    (* VYAN1102C [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102C := 3.75 + (SIN(sim_step + 5.85) * 3.0875);

    (* VYAN1102D [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102D := 3.75 + (SIN(sim_step + 0.0) * 3.0875);

    (* VYAN1103A [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103A := 3.75 + (SIN(sim_step + 0.39) * 3.0875);

    (* VYAN1103B [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103B := 3.75 + (SIN(sim_step + 0.78) * 3.0875);

    (* VYAN1103C [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103C := 3.75 + (SIN(sim_step + 1.17) * 3.0875);

    (* VYAN1103D [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103D := 3.75 + (SIN(sim_step + 1.56) * 3.0875);

    (* VYAN1104A [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104A := 3.75 + (SIN(sim_step + 1.95) * 3.0875);

    (* VYAN1104B [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104B := 3.75 + (SIN(sim_step + 2.34) * 3.0875);

    (* VYAN1104C [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104C := 3.75 + (SIN(sim_step + 2.73) * 3.0875);

    (* VYAN1104D [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104D := 3.75 + (SIN(sim_step + 3.12) * 3.0875);

    (* PY1102A [KPA] base=22.5 ±16.625 range 5.0..40.0 *)
    PY1102A := 22.5 + (SIN(sim_step + 3.51) * 16.625);

    (* PY1102B [KPA] base=22.5 ±16.625 range 5.0..40.0 *)
    PY1102B := 22.5 + (SIN(sim_step + 3.9) * 16.625);

    (* PY1102C [KPA] base=22.5 ±16.625 range 5.0..40.0 *)
    PY1102C := 22.5 + (SIN(sim_step + 4.29) * 16.625);

    (* PY1102D [KPA] base=22.5 ±16.625 range 5.0..40.0 *)
    PY1102D := 22.5 + (SIN(sim_step + 4.68) * 16.625);

    (* LY3101 [M] base=3.6 ±1.805 range 1.7..5.5 *)
    LY3101 := 3.6 + (SIN(sim_step + 5.07) * 1.805);

    (* PY3101 [KPA] base=1.8625 ±1.3656 range 0.425..3.3 *)
    PY3101 := 1.8625 + (SIN(sim_step + 5.46) * 1.3656);

    (* LY1101 [M] base=4.5 ±3.325 range 1.0..8.0 *)
    LY1101 := 4.5 + (SIN(sim_step + 5.85) * 3.325);

    (* LY1102 [M] base=4.5 ±3.325 range 1.0..8.0 *)
    LY1102 := 4.5 + (SIN(sim_step + 0.0) * 3.325);

    (* FY3101 [m3/h] base=225.0 ±166.25 range 50.0..400.0 *)
    FY3101 := 225.0 + (SIN(sim_step + 0.39) * 166.25);

    (* VY1101A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    VY1101A := 50.0 + (SIN(sim_step + 0.78) * 28.5);

    (* FY1101 [Ton/h] base=90.0 ±66.5 range 20.0..160.0 *)
    FY1101 := 90.0 + (SIN(sim_step + 1.17) * 66.5);

    (* CV1101 [Hz] base=52.5 ±2.375 range 50.0..55.0 *)
    CV1101 := 52.5 + (SIN(sim_step + 1.56) * 2.375);

    (* TY3101 [°C] base=75.0 ±42.75 range 30.0..120.0 *)
    TY3101 := 75.0 + (SIN(sim_step + 1.95) * 42.75);

    (* VYAN1101E [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101E := 3.75 + (SIN(sim_step + 2.34) * 3.0875);

    (* VYAN1101F [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101F := 3.75 + (SIN(sim_step + 2.73) * 3.0875);

    (* VYAN1101G [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101G := 3.75 + (SIN(sim_step + 3.12) * 3.0875);

    (* VYAN1101H [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1101H := 3.75 + (SIN(sim_step + 3.51) * 3.0875);

    (* VYAN1102E [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102E := 3.75 + (SIN(sim_step + 3.9) * 3.0875);

    (* VYAN1102F [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102F := 3.75 + (SIN(sim_step + 4.29) * 3.0875);

    (* VYAN1102G [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102G := 3.75 + (SIN(sim_step + 4.68) * 3.0875);

    (* VYAN1102H [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1102H := 3.75 + (SIN(sim_step + 5.07) * 3.0875);

    (* VYAN1103E [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103E := 3.75 + (SIN(sim_step + 5.46) * 3.0875);

    (* VYAN1103F [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103F := 3.75 + (SIN(sim_step + 5.85) * 3.0875);

    (* VYAN1103G [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103G := 3.75 + (SIN(sim_step + 0.0) * 3.0875);

    (* VYAN1103H [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1103H := 3.75 + (SIN(sim_step + 0.39) * 3.0875);

    (* VYAN1104E [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104E := 3.75 + (SIN(sim_step + 0.78) * 3.0875);

    (* VYAN1104F [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104F := 3.75 + (SIN(sim_step + 1.17) * 3.0875);

    (* VYAN1104G [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104G := 3.75 + (SIN(sim_step + 1.56) * 3.0875);

    (* VYAN1104H [mm/s] base=3.75 ±3.0875 range 0.5..7.0 *)
    VYAN1104H := 3.75 + (SIN(sim_step + 1.95) * 3.0875);

    (* MV1101A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    MV1101A := 50.0 + (SIN(sim_step + 2.34) * 28.5);

    (* MV1102A [%] base=50.0 ±28.5 range 20.0..80.0 *)
    MV1102A := 50.0 + (SIN(sim_step + 2.73) * 28.5);

    (* HZ1101B [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1101B := 50.0 + (SIN(sim_step + 3.12) * 28.5);

    (* HZ1102B [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1102B := 50.0 + (SIN(sim_step + 3.51) * 28.5);

    (* HZ1103B [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1103B := 50.0 + (SIN(sim_step + 3.9) * 28.5);

    (* HZ1104B [%] base=50.0 ±28.5 range 20.0..80.0 *)
    HZ1104B := 50.0 + (SIN(sim_step + 4.29) * 28.5);

    (* VT1101B [%] base=50.0 ±28.5 range 20.0..80.0 *)
    VT1101B := 50.0 + (SIN(sim_step + 4.68) * 28.5);

    (* CV1101B [Hz] base=52.5 ±2.375 range 50.0..55.0 *)
    CV1101B := 52.5 + (SIN(sim_step + 5.07) * 2.375);

    (* Fresh_SILO_MT [MT] base=450.0 ±332.5 range 100.0..800.0 *)
    Fresh_SILO_MT := 450.0 + (SIN(sim_step + 5.46) * 332.5);

    (* Enrich_SILO_MT [MT] base=450.0 ±332.5 range 100.0..800.0 *)
    Enrich_SILO_MT := 450.0 + (SIN(sim_step + 5.85) * 332.5);

ELSE

    (* Sim OFF — reset step only, keep last values *)
    sim_step := 0.0;

END_IF;