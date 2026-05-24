using System.Security.Cryptography;
using System.Text;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Handles encryption/decryption of sensitive data like OPC server IPs and credentials
/// Uses hardware-locked AES-256 encryption
/// </summary>
public class CredentialEncryptionService
{
    private readonly byte[] _encryptionKey;
    private readonly ILogger<CredentialEncryptionService> _logger;

    public CredentialEncryptionService(ILogger<CredentialEncryptionService> logger)
    {
        _logger = logger;
        _encryptionKey = DeriveEncryptionKey();
    }

    /// <summary>
    /// Encrypts a plain text string (e.g., IP address, server name)
    /// </summary>
    public string Encrypt(string plainText)
    {
        if (string.IsNullOrEmpty(plainText))
            return plainText;

        try
        {
            using var aes = Aes.Create();
            aes.Key = _encryptionKey;
            aes.GenerateIV();

            using var encryptor = aes.CreateEncryptor(aes.Key, aes.IV);
            using var msEncrypt = new MemoryStream();
            
            // Prepend IV to encrypted data
            msEncrypt.Write(aes.IV, 0, aes.IV.Length);
            
            using (var csEncrypt = new CryptoStream(msEncrypt, encryptor, CryptoStreamMode.Write))
            using (var swEncrypt = new StreamWriter(csEncrypt))
            {
                swEncrypt.Write(plainText);
            }

            return Convert.ToBase64String(msEncrypt.ToArray());
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error encrypting data");
            return plainText; // Fallback to plain text if encryption fails
        }
    }

    /// <summary>
    /// Decrypts an encrypted string back to plain text
    /// </summary>
    public string Decrypt(string encryptedText)
    {
        if (string.IsNullOrEmpty(encryptedText))
            return encryptedText;

        try
        {
            var fullData = Convert.FromBase64String(encryptedText);
            
            using var aes = Aes.Create();
            aes.Key = _encryptionKey;

            // Extract IV from beginning of data
            var iv = new byte[aes.IV.Length];
            Array.Copy(fullData, 0, iv, 0, iv.Length);
            aes.IV = iv;

            using var decryptor = aes.CreateDecryptor(aes.Key, aes.IV);
            using var msDecrypt = new MemoryStream(fullData, iv.Length, fullData.Length - iv.Length);
            using var csDecrypt = new CryptoStream(msDecrypt, decryptor, CryptoStreamMode.Read);
            using var srDecrypt = new StreamReader(csDecrypt);
            
            return srDecrypt.ReadToEnd();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error decrypting data - may be plain text");
            return encryptedText; // Return as-is if decryption fails (might be legacy plain text)
        }
    }

    /// <summary>
    /// Masks a string for display (shows first and last 2 chars, rest as asterisks)
    /// </summary>
    public string MaskForDisplay(string text)
    {
        if (string.IsNullOrEmpty(text))
            return "****";

        if (text.Length <= 4)
            return new string('*', text.Length);

        return $"{text.Substring(0, 2)}{new string('*', text.Length - 4)}{text.Substring(text.Length - 2)}";
    }

    /// <summary>
    /// Checks if a string is already encrypted (Base64 format)
    /// </summary>
    public bool IsEncrypted(string text)
    {
        if (string.IsNullOrEmpty(text))
            return false;

        try
        {
            Convert.FromBase64String(text);
            // Additional check: encrypted data should be longer than original
            return text.Length > 20; // Minimum length for encrypted data
        }
        catch
        {
            return false;
        }
    }

    private byte[] DeriveEncryptionKey()
    {
        var hardwareId = GetHardwareId();
        var salt = Encoding.UTF8.GetBytes("CereveateOPC_Credentials_2025");
        using var deriveBytes = new Rfc2898DeriveBytes(
            Encoding.UTF8.GetBytes(hardwareId),
            salt,
            10000,
            HashAlgorithmName.SHA256
        );
        return deriveBytes.GetBytes(32); // 256-bit key
    }

    private string GetHardwareId()
    {
        try
        {
            var cpuId = GetCpuId();
            var boardSerial = GetMotherboardSerial();
            return $"{cpuId}-{boardSerial}";
        }
        catch
        {
            return "DEFAULT_HARDWARE_ID_CREDENTIALS";
        }
    }

    private string GetCpuId()
    {
        try
        {
            using var searcher = new System.Management.ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor");
            foreach (System.Management.ManagementObject obj in searcher.Get())
            {
                return obj["ProcessorId"]?.ToString() ?? "UNKNOWN_CPU";
            }
        }
        catch { }
        return "UNKNOWN_CPU";
    }

    private string GetMotherboardSerial()
    {
        try
        {
            using var searcher = new System.Management.ManagementObjectSearcher("SELECT SerialNumber FROM Win32_BaseBoard");
            foreach (System.Management.ManagementObject obj in searcher.Get())
            {
                return obj["SerialNumber"]?.ToString() ?? "UNKNOWN_BOARD";
            }
        }
        catch { }
        return "UNKNOWN_BOARD";
    }
}
