using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace OpcDaWebBrowser.Pages
{
    public class TestConnectionModel : PageModel
    {
        [BindProperty]
        public string Host { get; set; } = "172.16.160.16";

        [BindProperty]
        public string ProgId { get; set; } = "MCS.OPCServer.1";

        [BindProperty]
        public string Clsid { get; set; } = "";

        public string ResultMessage { get; set; } = "";
        public bool IsSuccess { get; set; } = false;

        public void OnGet()
        {
        }

        public void OnPost(string action)
        {
            try
            {
                if (action == "progid")
                {
                    // Test ProgID connection
                    TestProgIdConnection();
                }
                else if (action == "clsid")
                {
                    // Test CLSID connection
                    TestClsidConnection();
                }
            }
            catch (Exception ex)
            {
                IsSuccess = false;
                ResultMessage = $"Error: {ex.Message}\n\nStack Trace:\n{ex.StackTrace}";
            }
        }

        private void TestProgIdConnection()
        {
            try
            {
                // Get type from ProgID (old method - fails on XP)
                Type? serverType = Type.GetTypeFromProgID(ProgId, Host);
                
                if (serverType == null)
                {
                    throw new Exception($"Cannot find ProgID '{ProgId}' on remote host '{Host}'");
                }

                dynamic? server = Activator.CreateInstance(serverType);
                
                if (server == null)
                {
                    throw new Exception("Failed to create server instance");
                }

                IsSuccess = true;
                ResultMessage = $"✅ ProgID Connection Successful!\n\n" +
                              $"Host: {Host}\n" +
                              $"ProgID: {ProgId}\n" +
                              $"Type: {serverType.FullName}\n" +
                              $"Server Instance Created: Yes";

                System.Runtime.InteropServices.Marshal.ReleaseComObject(server);
            }
            catch (Exception ex)
            {
                IsSuccess = false;
                ResultMessage = $"❌ ProgID Connection Failed\n\n" +
                              $"Host: {Host}\n" +
                              $"ProgID: {ProgId}\n\n" +
                              $"Error: {ex.Message}\n\n" +
                              $"This is expected on Windows XP - use CLSID instead.";
            }
        }

        private void TestClsidConnection()
        {
            try
            {
                if (string.IsNullOrWhiteSpace(Clsid))
                {
                    throw new Exception("CLSID is required. Get it from XP server using:\nreg query \"HKCR\\MCS.OPCServer.1\\CLSID\"");
                }

                // Remove curly braces if present
                string cleanClsid = Clsid.Trim().Trim('{', '}');
                
                // Parse CLSID
                Guid clsidGuid = Guid.Parse(cleanClsid);

                // Get type from CLSID (recommended for XP)
                Type? serverType = Type.GetTypeFromCLSID(clsidGuid, Host);
                
                if (serverType == null)
                {
                    throw new Exception($"Cannot create type from CLSID '{clsidGuid}' on host '{Host}'");
                }

                dynamic? server = Activator.CreateInstance(serverType);
                
                if (server == null)
                {
                    throw new Exception("Failed to create server instance from CLSID");
                }

                IsSuccess = true;
                ResultMessage = $"✅ CLSID Connection Successful!\n\n" +
                              $"Host: {Host}\n" +
                              $"CLSID: {{{clsidGuid}}}\n" +
                              $"Type: {serverType.FullName}\n" +
                              $"Server Instance Created: Yes\n\n" +
                              $"🎯 This method works on Windows XP!";

                System.Runtime.InteropServices.Marshal.ReleaseComObject(server);
            }
            catch (Exception ex)
            {
                IsSuccess = false;
                ResultMessage = $"❌ CLSID Connection Failed\n\n" +
                              $"Host: {Host}\n" +
                              $"CLSID: {Clsid}\n\n" +
                              $"Error: {ex.Message}";
            }
        }
    }
}
