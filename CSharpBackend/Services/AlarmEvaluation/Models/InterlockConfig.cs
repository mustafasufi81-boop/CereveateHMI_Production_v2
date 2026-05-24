namespace OpcDaWebBrowser.Services.AlarmEvaluation.Models;

/// <summary>
/// Immutable interlock configuration for a single tag.
/// Loaded from historian_meta.tag_master. Never written to.
/// </summary>
public sealed class InterlockConfig
{
    /// <summary>OPC tag identifier — primary key in tag_master.</summary>
    public required string TagId { get; init; }

    /// <summary>
    /// Interlock type from tag_master.
    /// Valid values: PERMISSIVE, CONDITIONAL, SEQUENTIAL, PROTECTIVE.
    /// </summary>
    public required string InterlockType { get; init; }

    /// <summary>
    /// Equipment label (tag_master.equipment or tag_master.tag_name prefix).
    /// Written to interlock_state_tracking.affected_equipment.
    /// </summary>
    public string? AffectedEquipment { get; init; }
}
