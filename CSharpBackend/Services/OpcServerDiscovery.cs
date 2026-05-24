using System.Runtime.InteropServices;
using OpcRcw.Comn;

namespace OpcDaWebBrowser.Services;

public class OpcServerDiscovery
{
    public List<ServerInfo> DiscoverServersOnRemoteHost(string hostname)
    {
        List<ServerInfo> servers = new List<ServerInfo>();

        try
        {
            // Use OpcEnum to browse remote OPC servers
            Type? enumType = Type.GetTypeFromProgID("OPC.ServerList.1", hostname);
            
            if (enumType == null)
            {
                // Fallback: Try known server ProgIDs on remote host
                return DiscoverKnownServersOnHost(hostname);
            }

            object enumObj = Activator.CreateInstance(enumType)!;
            IOPCServerList serverList = (IOPCServerList)enumObj;

            // Get all DA 2.0 servers
            Guid catid = new Guid("63D5F432-CFE4-11d1-B2C8-0060083BA1FB"); // CATID_OPCDAServer20
            
            serverList.EnumClassesOfCategories(
                1,
                new Guid[] { catid },
                0,
                null!,
                out object enumObj2);

            IEnumGUID enumGuid = (IEnumGUID)enumObj2;
            
            Guid[] guids = new Guid[100];
            
            while (true)
            {
                enumGuid.Next(100, guids, out int fetched);
                if (fetched == 0) break;

                for (int i = 0; i < fetched; i++)
                {
                    try
                    {
                        serverList.GetClassDetails(ref guids[i], out string progID, out string description);
                        
                        servers.Add(new ServerInfo
                        {
                            ProgID = progID,
                            Description = description,
                            CLSID = guids[i].ToString(),
                            Hostname = hostname
                        });
                    }
                    catch { }
                }

                if (fetched < 100) break;
            }

            Marshal.ReleaseComObject(enumGuid);
            Marshal.ReleaseComObject(serverList);
        }
        catch
        {
            // If OpcEnum fails, try known servers
            return DiscoverKnownServersOnHost(hostname);
        }

        return servers;
    }

    private List<ServerInfo> DiscoverKnownServersOnHost(string hostname)
    {
        List<ServerInfo> servers = new List<ServerInfo>();

        string[] knownServers = new[]
        {
            "Matrikon.OPC.Simulation.1",
            "Kepware.KEPServerEX.V6",
            "OPC.SimaticNet",
            "RSLinx OPC Server",
            "Iconics.OPCServer",
            "MCS.OPCServer.1",
            "OPC.DeltaV.1",
            "Matrikon.OPC.Universal.1",
            "OPC.Honeywell.HDA",
            "Wonderware.OPCServer"
        };

        foreach (string progID in knownServers)
        {
            try
            {
                Type? serverType = Type.GetTypeFromProgID(progID, hostname);
                if (serverType != null)
                {
                    servers.Add(new ServerInfo
                    {
                        ProgID = progID,
                        Description = progID,
                        CLSID = serverType.GUID.ToString(),
                        Hostname = hostname
                    });
                }
            }
            catch { }
        }

        return servers;
    }

    public List<ServerInfo> DiscoverLocalServers()
    {
        return DiscoverServersOnRemoteHost(Environment.MachineName);
    }
}

public class ServerInfo
{
    public string ProgID { get; set; } = "";
    public string Description { get; set; } = "";
    public string CLSID { get; set; } = "";
    public string Hostname { get; set; } = "";
}
