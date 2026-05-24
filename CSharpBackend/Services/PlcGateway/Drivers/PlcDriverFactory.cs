using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;
using PlcGateway.Models;

namespace PlcGateway.Drivers;

/// <summary>
/// Driver Factory - creates appropriate driver based on protocol type
/// </summary>
public class PlcDriverFactory
{
    private readonly ILoggerFactory _loggerFactory;

    public PlcDriverFactory(ILoggerFactory loggerFactory)
    {
        _loggerFactory = loggerFactory;
    }

    /// <summary>
    /// Create driver instance for given protocol
    /// </summary>
    public IPlcDriver CreateDriver(PlcProtocol protocol)
    {
        return protocol switch
        {
            PlcProtocol.SiemensS7 => new SiemensS7Driver(
                _loggerFactory.CreateLogger<SiemensS7Driver>()),
            
            PlcProtocol.ModbusTcp => new ModbusTcpDriver(
                _loggerFactory.CreateLogger<ModbusTcpDriver>()),
            
            // EtherNetIP protocol is NOT IMPLEMENTED
            // For Rockwell/Allen-Bradley PLCs, use PlcProtocol.Rockwell instead
            PlcProtocol.EtherNetIP => throw new NotImplementedException(
                "EtherNetIP protocol driver is not implemented. " +
                "For Rockwell/Allen-Bradley PLCs, use protocol='Rockwell' which uses libplctag. " +
                "DO NOT create placeholder/simulation code - this violates company policy."),
            
            // Rockwell/Allen-Bradley - uses libplctag (REAL IMPLEMENTATION)
            PlcProtocol.Rockwell => new RockwellDriver(
                _loggerFactory.CreateLogger<RockwellDriver>()),
            
            PlcProtocol.ABB => new AbbDriver(
                _loggerFactory.CreateLogger<AbbDriver>(),
                _loggerFactory.CreateLogger<ModbusTcpDriver>()),
            
            PlcProtocol.Mitsubishi => new MitsubishiDriver(
                _loggerFactory.CreateLogger<MitsubishiDriver>(),
                _loggerFactory.CreateLogger<ModbusTcpDriver>()),
            
            PlcProtocol.Omron => new OmronDriver(
                _loggerFactory.CreateLogger<OmronDriver>()),
            
            _ => throw new ArgumentException($"Unsupported protocol: {protocol}")
        };
    }

    /// <summary>
    /// Get list of supported protocols
    /// </summary>
    public static IEnumerable<(PlcProtocol Protocol, string Description)> GetSupportedProtocols()
    {
        yield return (PlcProtocol.SiemensS7, "Siemens S7-300/400/1200/1500 via S7Comm (port 102)");
        yield return (PlcProtocol.ModbusTcp, "Generic Modbus TCP (port 502)");
        yield return (PlcProtocol.EtherNetIP, "Allen Bradley / Rockwell via EtherNet/IP CIP (port 44818)");
        yield return (PlcProtocol.Rockwell, "Rockwell ControlLogix/CompactLogix/Micro800 via libplctag");
        yield return (PlcProtocol.ABB, "ABB AC500/PM5xx via Modbus TCP");
        yield return (PlcProtocol.Mitsubishi, "Mitsubishi MELSEC via MC Protocol or Modbus TCP");
        yield return (PlcProtocol.Omron, "Omron via FINS TCP (port 9600)");
    }
}
