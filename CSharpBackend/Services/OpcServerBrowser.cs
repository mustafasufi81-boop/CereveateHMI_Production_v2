using System.Runtime.InteropServices;

namespace OpcDaWebBrowser.Services;

// OPC Server Browser (OPCEnum) - Works with minimal DCOM settings
[ComImport]
[Guid("13486D51-4821-11D2-A494-3CB306C10000")]
public class OpcServerList { }

[ComImport]
[Guid("13486D50-4821-11D2-A494-3CB306C10000")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IOPCServerList
{
    void EnumClassesOfCategories(
        [In] int cImplemented,
        [In, MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 0)] Guid[] catidImpl,
        [In] int cRequired,
        [In, MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 2)] Guid[] catidReq,
        [Out, MarshalAs(UnmanagedType.IUnknown)] out object ppUnk);

    void GetClassDetails(
        [In] ref Guid clsid,
        [Out, MarshalAs(UnmanagedType.LPWStr)] out string ppszProgID,
        [Out, MarshalAs(UnmanagedType.LPWStr)] out string ppszUserType);

    void CLSIDFromProgID(
        [In, MarshalAs(UnmanagedType.LPWStr)] string szProgId,
        [Out] out Guid clsid);
}

[ComImport]
[Guid("00000100-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IEnumGUID
{
    void Next(
        [In] int celt,
        [Out, MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 0)] Guid[] rgelt,
        [Out] out int pceltFetched);

    void Skip([In] int celt);
    void Reset();
    void Clone([Out, MarshalAs(UnmanagedType.Interface)] out IEnumGUID ppenum);
}

public class RemoteServerInfo
{
    public string ProgID { get; set; } = "";
    public string Description { get; set; } = "";
    public Guid CLSID { get; set; }
    public string Host { get; set; } = "";
}
