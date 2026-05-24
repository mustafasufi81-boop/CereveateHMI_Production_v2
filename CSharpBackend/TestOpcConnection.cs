using System;
using System.Runtime.InteropServices;
using OpcRcw.Da;
using OpcRcw.Comn;

namespace OpcConnectionTest
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.WriteLine("==========================================================");
            Console.WriteLine("           OPC DA CONNECTION & BROWSE TEST");
            Console.WriteLine("==========================================================");
            Console.WriteLine();

            // Test parameters
            string serverProgID = "MCS.OPCServer.1";
            string host = "172.16.160.16";
            string clsid = "{0FB6CC70-85B2-11d4-9126-0060976C6068}";

            Console.WriteLine($"Target Server: {serverProgID}");
            Console.WriteLine($"Remote Host: {host}");
            Console.WriteLine($"CLSID: {clsid}");
            Console.WriteLine();
            Console.WriteLine("----------------------------------------------------------");
            Console.WriteLine("STEP 1: Creating COM Connection");
            Console.WriteLine("----------------------------------------------------------");

            IOPCServer? opcServer = null;

            try
            {
                // Clean and parse CLSID
                string cleanClsid = clsid.Trim().Trim('{', '}');
                Guid clsidGuid = Guid.Parse(cleanClsid);
                Console.WriteLine($"✓ CLSID parsed: {clsidGuid}");

                // Get type from CLSID
                Type? serverType = Type.GetTypeFromCLSID(clsidGuid, host);
                if (serverType == null)
                {
                    Console.WriteLine($"✗ ERROR: Cannot get type from CLSID on host {host}");
                    return;
                }
                Console.WriteLine($"✓ Type retrieved from CLSID");

                // Create instance
                opcServer = (IOPCServer)Activator.CreateInstance(serverType)!;
                Console.WriteLine($"✓ OPC Server instance created successfully");
                Console.WriteLine();

                // Test browsing interface
                Console.WriteLine("----------------------------------------------------------");
                Console.WriteLine("STEP 2: Testing Browse Interface");
                Console.WriteLine("----------------------------------------------------------");

                IOPCBrowseServerAddressSpace? browser = opcServer as IOPCBrowseServerAddressSpace;
                if (browser == null)
                {
                    Console.WriteLine("✗ ERROR: Server does not support IOPCBrowseServerAddressSpace");
                    return;
                }
                Console.WriteLine("✓ Browse interface available");
                Console.WriteLine();

                // Change to root
                Console.WriteLine("----------------------------------------------------------");
                Console.WriteLine("STEP 3: Navigating to Root");
                Console.WriteLine("----------------------------------------------------------");
                browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_TO, "");
                Console.WriteLine("✓ Changed to root position");
                Console.WriteLine();

                // Browse for branches
                Console.WriteLine("----------------------------------------------------------");
                Console.WriteLine("STEP 4: Browsing for BRANCHES (folders)");
                Console.WriteLine("----------------------------------------------------------");
                string[] branches = GetBrowseItems(browser, OPCBROWSETYPE.OPC_BRANCH);
                Console.WriteLine($"Found {branches.Length} branches:");
                foreach (string branch in branches)
                {
                    Console.WriteLine($"  📁 {branch}");
                }
                Console.WriteLine();

                // Browse for leaves
                Console.WriteLine("----------------------------------------------------------");
                Console.WriteLine("STEP 5: Browsing for LEAVES (tags)");
                Console.WriteLine("----------------------------------------------------------");
                string[] leaves = GetBrowseItems(browser, OPCBROWSETYPE.OPC_LEAF);
                Console.WriteLine($"Found {leaves.Length} leaf items:");
                
                int displayCount = 0;
                foreach (string leaf in leaves)
                {
                    // Try to get full ItemID
                    string itemID = leaf;
                    try
                    {
                        browser.GetItemID(leaf, out string fullItemID);
                        if (!string.IsNullOrEmpty(fullItemID))
                            itemID = fullItemID;
                    }
                    catch { }

                    Console.WriteLine($"  🏷️  {leaf}");
                    if (itemID != leaf)
                        Console.WriteLine($"      ItemID: {itemID}");
                    
                    displayCount++;
                    if (displayCount >= 20 && leaves.Length > 20)
                    {
                        Console.WriteLine($"  ... and {leaves.Length - 20} more tags");
                        break;
                    }
                }
                Console.WriteLine();

                // If we have branches, explore first one
                if (branches.Length > 0)
                {
                    Console.WriteLine("----------------------------------------------------------");
                    Console.WriteLine($"STEP 6: Exploring First Branch: {branches[0]}");
                    Console.WriteLine("----------------------------------------------------------");
                    
                    try
                    {
                        browser.ChangeBrowsePosition(OPCBROWSEDIRECTION.OPC_BROWSE_DOWN, branches[0]);
                        Console.WriteLine($"✓ Moved into branch: {branches[0]}");
                        
                        string[] subLeaves = GetBrowseItems(browser, OPCBROWSETYPE.OPC_LEAF);
                        Console.WriteLine($"Found {subLeaves.Length} tags in this branch:");
                        
                        displayCount = 0;
                        foreach (string leaf in subLeaves)
                        {
                            Console.WriteLine($"  🏷️  {leaf}");
                            displayCount++;
                            if (displayCount >= 10 && subLeaves.Length > 10)
                            {
                                Console.WriteLine($"  ... and {subLeaves.Length - 10} more tags");
                                break;
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"✗ ERROR exploring branch: {ex.Message}");
                    }
                    Console.WriteLine();
                }

                Console.WriteLine("==========================================================");
                Console.WriteLine("                    TEST COMPLETED");
                Console.WriteLine("==========================================================");
            }
            catch (COMException comEx)
            {
                Console.WriteLine();
                Console.WriteLine("✗✗✗ COM ERROR ✗✗✗");
                Console.WriteLine($"Error Code: 0x{comEx.ErrorCode:X8}");
                Console.WriteLine($"Message: {comEx.Message}");
                
                string errorDetail = comEx.ErrorCode switch
                {
                    unchecked((int)0x80070005) => "Access Denied - Check DCOM permissions",
                    unchecked((int)0x800706BA) => "RPC Server Unavailable - Host unreachable or firewall blocking",
                    unchecked((int)0x80080005) => "Server Execution Failed - OPC server cannot start",
                    unchecked((int)0x800401F0) => "Class Not Registered - OPC server not installed on remote host",
                    _ => "Unknown COM error"
                };
                Console.WriteLine($"Likely cause: {errorDetail}");
            }
            catch (Exception ex)
            {
                Console.WriteLine();
                Console.WriteLine("✗✗✗ ERROR ✗✗✗");
                Console.WriteLine($"Type: {ex.GetType().Name}");
                Console.WriteLine($"Message: {ex.Message}");
                Console.WriteLine($"Stack: {ex.StackTrace}");
            }
            finally
            {
                if (opcServer != null)
                {
                    try
                    {
                        Marshal.ReleaseComObject(opcServer);
                        Console.WriteLine();
                        Console.WriteLine("✓ COM objects released");
                    }
                    catch { }
                }
            }

            Console.WriteLine();
            Console.WriteLine("Press any key to exit...");
            Console.ReadKey();
        }

        static string[] GetBrowseItems(IOPCBrowseServerAddressSpace browser, OPCBROWSETYPE browseType)
        {
            try
            {
                browser.BrowseOPCItemIDs(browseType, "", 0, 0, out OpcRcw.Da.IEnumString? enumString);
                
                if (enumString == null)
                {
                    Console.WriteLine($"  ℹ️  BrowseOPCItemIDs returned null for type {browseType}");
                    return Array.Empty<string>();
                }

                List<string> items = new();
                string[] buffer = new string[100];
                int totalFetched = 0;

                while (true)
                {
                    enumString.RemoteNext(100, buffer, out int fetched);
                    totalFetched += fetched;
                    
                    if (fetched == 0) break;

                    for (int i = 0; i < fetched; i++)
                    {
                        if (!string.IsNullOrEmpty(buffer[i]))
                            items.Add(buffer[i]);
                    }

                    if (fetched < 100) break;
                }

                Marshal.ReleaseComObject(enumString);
                Console.WriteLine($"  ℹ️  Retrieved {items.Count} items ({totalFetched} total fetched)");
                return items.ToArray();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ ERROR in GetBrowseItems: {ex.Message}");
                return Array.Empty<string>();
            }
        }
    }
}
