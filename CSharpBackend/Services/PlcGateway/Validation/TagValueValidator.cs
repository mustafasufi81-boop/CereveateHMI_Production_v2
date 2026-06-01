using PlcGateway.Interfaces;

namespace PlcGateway.Validation;

/// <summary>
/// PLC value sanity validator — Phase 1 of PLC_DATA_INTEGRITY_STUDY_AND_FIX_PLAN.md.
///
/// PURE &amp; STATELESS. No I/O, no logging, no caching. Given a freshly decoded raw
/// value and its tag definition, it returns a verdict: is this number itself sane?
///
/// Scope (intentionally narrow — see §3 R3/R4 and §4.1 of the plan):
///   • R3 — numeric sanity for floats: NaN, ±Infinity, denormal/sub-normal.
///   • R4 — type integrity: an unknown/empty data_type is NOT silently treated as
///          REAL; it is reported Bad("TYPE_UNCONFIGURED").
///
/// EXPLICITLY NOT here (by design, to avoid over-engineering):
///   • No min/max engineering-range check — that is the existing alarm limits' job.
///   • No deep element-type comparison against libplctag (R4b, deferred §4.1).
///
/// The validator never substitutes a value. It only judges the value handed to it;
/// the caller carries the ACTUAL value through, flagged with this verdict.
/// </summary>
public static class TagValueValidator
{
    // ── IEEE-754 smallest NORMAL positive magnitudes ─────────────────────────
    // NOTE: float.Epsilon / double.Epsilon are the smallest DENORMAL values, not
    // the smallest normal — so we use explicit constants here. Any non-zero value
    // whose magnitude is below these is a denormal (sub-normal) number, which in a
    // process plant almost always means a misread / type-mismatched bit pattern
    // (e.g. an integer decoded as REAL → 1.22e-43), never a real measurement.
    public const float  RealMinNormal  = 1.17549435e-38f;          // 2^-126
    public const double LRealMinNormal = 2.2250738585072014e-308;  // 2^-1022

    /// <summary>Verdict for a single decoded value.</summary>
    public readonly record struct ValidationResult(bool Ok, PlcQuality Quality, string? Reason)
    {
        public static ValidationResult Good() => new(true, PlcQuality.Good, null);
        public static ValidationResult Bad(string reason) => new(false, PlcQuality.Bad, reason);
    }

    /// <summary>
    /// Judge a freshly decoded value against its declared data type.
    /// Returns (Ok, Quality, Reason). Reason is null when Ok.
    /// </summary>
    public static ValidationResult Validate(object? raw, PlcTagDefinition tag)
    {
        // A null here means the decode produced nothing for an otherwise-OK read.
        if (raw is null)
            return ValidationResult.Bad("NULL_VALUE");

        var type = (tag?.DataType ?? string.Empty).Trim().ToUpperInvariant();

        switch (type)
        {
            // ── Integral & boolean: no NaN/Infinity concept ──────────────────
            // Read status was already OK upstream; an integer bit pattern is always
            // a valid integer. (Deep type-mismatch detection for ints is R4b/deferred.)
            case "BOOL":
            case "SINT":
            case "INT":
            case "INT32":
            case "DINT":
            case "LINT":
            case "BYTE":
            case "UINT":
            case "UDINT":
            case "ULINT":
                return ValidationResult.Good();

            // ── 32-bit float (Rockwell REAL; "FLOAT" alias for config default) ─
            case "REAL":
            case "FLOAT":
                return raw switch
                {
                    float f  => ValidateFloat(f,  RealMinNormal),
                    double d => ValidateFloat(d,  RealMinNormal),
                    _        => ValidationResult.Bad("TYPE_MISMATCH")
                };

            // ── 64-bit float (Rockwell LREAL; "DOUBLE" alias) ────────────────
            case "LREAL":
            case "DOUBLE":
                return raw switch
                {
                    double d => ValidateFloat(d, LRealMinNormal),
                    float f  => ValidateFloat(f, LRealMinNormal),
                    _        => ValidationResult.Bad("TYPE_MISMATCH")
                };

            // ── Strings are carried as-is (no numeric sanity applies) ─────────
            case "STRING":
                return ValidationResult.Good();

            // ── R4: unknown or empty data type ⇒ Bad, never forced to REAL ────
            case "":
                return ValidationResult.Bad("TYPE_UNCONFIGURED");
            default:
                return ValidationResult.Bad("TYPE_UNCONFIGURED");
        }
    }

    /// <summary>
    /// R3 float sanity: NaN, ±Infinity, denormal. <paramref name="minNormal"/> selects
    /// the precision-appropriate smallest-normal threshold (REAL vs LREAL).
    /// </summary>
    private static ValidationResult ValidateFloat(double v, double minNormal)
    {
        if (double.IsNaN(v))
            return ValidationResult.Bad("NAN");
        if (double.IsInfinity(v))
            return ValidationResult.Bad("INFINITY");
        if (v != 0.0 && Math.Abs(v) < minNormal)
            return ValidationResult.Bad("DENORMAL");
        return ValidationResult.Good();
    }
}
