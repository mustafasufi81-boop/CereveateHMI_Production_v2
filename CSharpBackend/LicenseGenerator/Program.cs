using System;
using System.IO;
using System.Management;
using System.Net.NetworkInformation;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace LicenseGenerator
{
    class Program
    {
        private const string EncryptionKey = "CereveateOPC2025SecureKey!@#$%^";
        
        static void Main(string[] args)
        {
            Console.WriteLine("========================================");
            Console.WriteLine("Cereveate_Praxis OPC Server");
            Console.WriteLine("License Generator Tool");
            Console.WriteLine("========================================");
            Console.WriteLine();

            try
            {
                // Get hardware ID
                string hardwareId = GetHardwareId();
                Console.WriteLine($"Hardware ID: {hardwareId}");
                Console.WriteLine();

                // Set license expiry (4 months from now)
                DateTime expiryDate = DateTime.Now.AddMonths(4);
                Console.WriteLine($"License will expire on: {expiryDate:yyyy-MM-dd HH:mm:ss}");
                Console.WriteLine();

                // Create license data
                var licenseData = new LicenseData
                {
                    HardwareId = hardwareId,
                    ExpiryDate = expiryDate,
                    IssuedDate = DateTime.Now,
                    CompanyName = "Cereveate_Praxis",
                    ProductName = "OPC Server Professional"
                };

                // Serialize and encrypt
                string json = JsonSerializer.Serialize(licenseData);
                string encrypted = Encrypt(json);

                // Create signature
                string signature = CreateSignature(encrypted);

                // Combine encrypted data and signature
                string licenseContent = encrypted + "|" + signature;

                // Save to file
                string outputPath = "license.dat";
                File.WriteAllText(outputPath, licenseContent);

                Console.WriteLine("========================================");
                Console.WriteLine("LICENSE GENERATED SUCCESSFULLY!");
                Console.WriteLine("========================================");
                Console.WriteLine($"File: {Path.GetFullPath(outputPath)}");
                Console.WriteLine();
                Console.WriteLine("Copy this file to the application folder.");
                Console.WriteLine();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERROR: {ex.Message}");
                Console.WriteLine();
            }

            Console.WriteLine("Press any key to exit...");
            Console.ReadKey();
        }

        private static string GetHardwareId()
        {
            try
            {
                string cpuId = GetCpuId();
                string motherboardSerial = GetMotherboardSerial();
                string macAddress = GetMacAddress();

                return $"{cpuId}-{motherboardSerial}-{macAddress}";
            }
            catch (Exception ex)
            {
                throw new Exception($"Failed to get hardware ID: {ex.Message}");
            }
        }

        private static string GetCpuId()
        {
            try
            {
                using var searcher = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor");
                foreach (ManagementObject obj in searcher.Get())
                {
                    return obj["ProcessorId"]?.ToString() ?? "UNKNOWN_CPU";
                }
            }
            catch { }
            return "UNKNOWN_CPU";
        }

        private static string GetMotherboardSerial()
        {
            try
            {
                using var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard");
                foreach (ManagementObject obj in searcher.Get())
                {
                    return obj["SerialNumber"]?.ToString() ?? "UNKNOWN_MB";
                }
            }
            catch { }
            return "UNKNOWN_MB";
        }

        private static string GetMacAddress()
        {
            try
            {
                foreach (NetworkInterface nic in NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (nic.OperationalStatus == OperationalStatus.Up &&
                        nic.NetworkInterfaceType != NetworkInterfaceType.Loopback)
                    {
                        return nic.GetPhysicalAddress().ToString();
                    }
                }
            }
            catch { }
            return "UNKNOWN_MAC";
        }

        private static string Encrypt(string plainText)
        {
            using var aes = Aes.Create();
            var key = new Rfc2898DeriveBytes(EncryptionKey, Encoding.UTF8.GetBytes("CereveateOPCSalt"), 10000, HashAlgorithmName.SHA256);
            aes.Key = key.GetBytes(32);
            aes.IV = new byte[16];

            using var encryptor = aes.CreateEncryptor();
            var plainBytes = Encoding.UTF8.GetBytes(plainText);
            var encryptedBytes = encryptor.TransformFinalBlock(plainBytes, 0, plainBytes.Length);
            return Convert.ToBase64String(encryptedBytes);
        }

        private static string CreateSignature(string data)
        {
            using var sha256 = SHA256.Create();
            var hashBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(data + EncryptionKey));
            return Convert.ToBase64String(hashBytes);
        }

        private class LicenseData
        {
            public string HardwareId { get; set; } = string.Empty;
            public DateTime ExpiryDate { get; set; }
            public DateTime IssuedDate { get; set; }
            public string CompanyName { get; set; } = string.Empty;
            public string ProductName { get; set; } = string.Empty;
        }
    }
}
