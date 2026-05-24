using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Handles user authentication with encrypted credential storage
/// </summary>
public class AuthenticationService
{
    private readonly string _credentialsPath;
    private readonly ILogger<AuthenticationService> _logger;
    private readonly byte[] _encryptionKey;
    private List<UserCredentials> _users = new();

    public AuthenticationService(ILogger<AuthenticationService> logger)
    {
        _logger = logger;
        _credentialsPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".credentials");
        
        // Use hardware-specific key for encryption (same as license)
        _encryptionKey = DeriveEncryptionKey();
        
        LoadCredentials();
    }

    public (bool IsValid, string Role) ValidateUser(string username, string password)
    {
        var user = _users.FirstOrDefault(u => u.Username == username);
        if (user == null)
        {
            _logger.LogWarning($"User not found: '{username}'");
            return (false, string.Empty);
        }

        // Check if user is enabled
        if (!user.IsEnabled)
        {
            _logger.LogWarning($"User account is disabled: '{username}'");
            return (false, string.Empty);
        }

        var hashedPassword = HashPassword(password);
        var isValid = user.PasswordHash == hashedPassword;
        
        if (isValid)
        {
            _logger.LogInformation($"User '{username}' logged in successfully (Role: {user.Role})");
            return (true, user.Role);
        }
        else
        {
            _logger.LogWarning($"Failed login attempt for user '{username}'");
            return (false, string.Empty);
        }
    }

    public void SetCredentials(string username, string password, string role = "Viewer")
    {
        var hashedPassword = HashPassword(password);
        var existingUser = _users.FirstOrDefault(u => u.Username == username);
        
        if (existingUser != null)
        {
            existingUser.PasswordHash = hashedPassword;
            existingUser.Role = role;
        }
        else
        {
            _users.Add(new UserCredentials
            {
                Username = username,
                PasswordHash = hashedPassword,
                Role = role
            });
        }
        
        SaveCredentials();
        _logger.LogInformation($"Credentials updated for user '{username}' with role '{role}'");
    }

    public bool ChangePassword(string username, string oldPassword, string newPassword)
    {
        var user = _users.FirstOrDefault(u => u.Username == username);
        if (user == null)
        {
            _logger.LogWarning($"User not found for password change: '{username}'");
            return false;
        }

        // Verify old password
        var oldHashedPassword = HashPassword(oldPassword);
        if (user.PasswordHash != oldHashedPassword)
        {
            _logger.LogWarning($"Invalid old password provided for user '{username}'");
            return false;
        }

        // Set new password
        user.PasswordHash = HashPassword(newPassword);
        SaveCredentials();
        _logger.LogInformation($"Password changed successfully for user '{username}'");
        return true;
    }

    public bool ChangeUserPassword(string targetUsername, string newPassword, string adminUsername)
    {
        // Only opcadmin can change other users' passwords
        var admin = _users.FirstOrDefault(u => u.Username == adminUsername);
        if (admin == null || admin.Role != "Administrator" || adminUsername != "opcadmin")
        {
            _logger.LogWarning($"Unauthorized password change attempt by '{adminUsername}' for user '{targetUsername}'");
            return false;
        }

        var targetUser = _users.FirstOrDefault(u => u.Username == targetUsername);
        if (targetUser == null)
        {
            _logger.LogWarning($"Target user not found for password change: '{targetUsername}'");
            return false;
        }

        targetUser.PasswordHash = HashPassword(newPassword);
        SaveCredentials();
        _logger.LogInformation($"Password changed for user '{targetUsername}' by admin '{adminUsername}'");
        return true;
    }

    public bool ToggleUserEnabled(string targetUsername, bool enabled, string adminUsername)
    {
        // Only opcadmin can enable/disable users
        var admin = _users.FirstOrDefault(u => u.Username == adminUsername);
        if (admin == null || admin.Role != "Administrator" || adminUsername != "opcadmin")
        {
            _logger.LogWarning($"Unauthorized user toggle attempt by '{adminUsername}' for user '{targetUsername}'");
            return false;
        }

        // Cannot disable opcadmin
        if (targetUsername == "opcadmin")
        {
            _logger.LogWarning($"Attempt to disable opcadmin account");
            return false;
        }

        var targetUser = _users.FirstOrDefault(u => u.Username == targetUsername);
        if (targetUser == null)
        {
            _logger.LogWarning($"Target user not found: '{targetUsername}'");
            return false;
        }

        targetUser.IsEnabled = enabled;
        SaveCredentials();
        _logger.LogInformation($"User '{targetUsername}' {(enabled ? "enabled" : "disabled")} by admin '{adminUsername}'");
        return true;
    }

    public List<UserInfo> GetAllUsers(string adminUsername)
    {
        // Only opcadmin can view all users
        var admin = _users.FirstOrDefault(u => u.Username == adminUsername);
        if (admin == null || admin.Role != "Administrator" || adminUsername != "opcadmin")
        {
            return new List<UserInfo>();
        }

        return _users.Select(u => new UserInfo
        {
            Username = u.Username,
            Role = u.Role,
            IsEnabled = u.IsEnabled
        }).ToList();
    }

    public bool HasCredentials()
    {
        return _users.Any();
    }

    private void LoadCredentials()
    {
        try
        {
            if (!File.Exists(_credentialsPath))
            {
                _logger.LogInformation("No credentials file found - creating default users");
                _users = new List<UserCredentials>();
                // Create default users
                SetCredentials("opcadmin", "admin", "Administrator");
                SetCredentials("admin", "admin", "Administrator");
                return;
            }

            var encryptedData = File.ReadAllText(_credentialsPath);
            var decryptedJson = Decrypt(encryptedData);
            _users = JsonSerializer.Deserialize<List<UserCredentials>>(decryptedJson) ?? new List<UserCredentials>();

            // Ensure required default accounts exist with requested roles/passwords
            SetCredentials("opcadmin", "admin", "Administrator");
            SetCredentials("admin", "admin", "Administrator");
            _logger.LogInformation($"Loaded {_users.Count} user(s) successfully");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error loading credentials - creating default users");
            _users = new List<UserCredentials>();
            SetCredentials("opcadmin", "admin", "Administrator");
            SetCredentials("admin", "admin", "Administrator");
        }
    }

    private void SaveCredentials()
    {
        try
        {
            var json = JsonSerializer.Serialize(_users);
            var encryptedData = Encrypt(json);
            
            File.WriteAllText(_credentialsPath, encryptedData);
            File.SetAttributes(_credentialsPath, FileAttributes.Hidden);
            
            _logger.LogInformation("Credentials saved successfully");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error saving credentials");
        }
    }

    private string HashPassword(string password)
    {
        using var sha256 = SHA256.Create();
        var hashBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(password + GetHardwareSalt()));
        return Convert.ToBase64String(hashBytes);
    }

    private byte[] DeriveEncryptionKey()
    {
        var hardwareId = GetHardwareId();
        var salt = Encoding.UTF8.GetBytes("CereveateOPC_Salt_2025");
        using var deriveBytes = new Rfc2898DeriveBytes(
            Encoding.UTF8.GetBytes(hardwareId),
            salt,
            10000,
            HashAlgorithmName.SHA256
        );
        return deriveBytes.GetBytes(32); // 256-bit key
    }

    private string Encrypt(string plainText)
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

    private string Decrypt(string encryptedText)
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
            return "DEFAULT_HARDWARE_ID";
        }
    }

    private string GetHardwareSalt()
    {
        // Add hardware-specific salt to password hash
        return GetHardwareId().Substring(0, Math.Min(16, GetHardwareId().Length));
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

public class UserCredentials
{
    public string Username { get; set; } = string.Empty;
    public string PasswordHash { get; set; } = string.Empty;
    public string Role { get; set; } = "Viewer";
    public bool IsEnabled { get; set; } = true;
}

public class UserInfo
{
    public string Username { get; set; } = string.Empty;
    public string Role { get; set; } = string.Empty;
    public bool IsEnabled { get; set; } = true;
}
