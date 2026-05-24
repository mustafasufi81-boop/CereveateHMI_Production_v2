import { useState, useEffect, useCallback } from "react";
import api from "@/services/api";
import { AlertTriangle, ShieldCheck, ShieldOff, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface LicenseStatus {
    is_valid: boolean;
    key_label: string | null;
    max_users: number;
    current_users: number;
    valid_until: string | null;   // ISO string
    issued_to: string | null;
    activated_at: string | null;
    error?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function daysUntil(isoDate: string | null): number | null {
    if (!isoDate) return null;
    const diff = new Date(isoDate).getTime() - Date.now();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function formatDate(isoDate: string | null): string {
    if (!isoDate) return "—";
    return new Date(isoDate).toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

const LicenseBanner = () => {
    const [status, setStatus] = useState<LicenseStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [activateOpen, setActivateOpen] = useState(false);
    const [activateKey, setActivateKey] = useState("");
    const [activating, setActivating] = useState(false);

    const fetchStatus = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get("/admin/license/status");
            setStatus(res.data);
        } catch (err: any) {
            // Non-admin or network error — hide banner silently
            setStatus(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchStatus();
    }, [fetchStatus]);

    const handleActivate = async () => {
        if (!activateKey.trim()) {
            toast.error("Paste the activation key first.");
            return;
        }
        setActivating(true);
        try {
            const res = await api.post("/admin/license/activate", { activation_key: activateKey.trim() });
            toast.success(`License activated — ${res.data.max_users} seats, issued to ${res.data.issued_to}`);
            setActivateOpen(false);
            setActivateKey("");
            fetchStatus();
        } catch (err: any) {
            const msg = err.response?.data?.error || err.message || "Activation failed";
            toast.error(msg);
        } finally {
            setActivating(false);
        }
    };

    // Don't render while loading or when status is null (non-admin, error)
    if (loading || !status) return null;

    // Never activated — hide banner entirely (fresh/unlicensed system).
    // Only surface the banner once a license key has been attempted or is active.
    if (!status.is_valid && !status.key_label) return null;

    const days = daysUntil(status.valid_until);
    const expiringSoon = days !== null && days <= 30 && days > 0;
    const expired = days !== null && days <= 0;
    const noLicense = !status.is_valid;

    // Determine banner style
    let variant: "error" | "warning" | "ok" = "ok";
    if (noLicense || expired) variant = "error";
    else if (expiringSoon) variant = "warning";

    const seatPct = status.max_users > 0
        ? Math.round((status.current_users / status.max_users) * 100)
        : 0;
    const seatsNearLimit = seatPct >= 90;

    const bannerClass =
        variant === "error"
            ? "border border-destructive/50 bg-destructive/10 text-destructive"
            : variant === "warning"
            ? "border border-yellow-500/50 bg-yellow-500/10 text-yellow-700 dark:text-yellow-400"
            : "border border-green-500/30 bg-green-500/5 text-green-700 dark:text-green-400";

    return (
        <>
            <div className={`rounded-lg px-4 py-3 flex items-center justify-between gap-4 ${bannerClass}`}>
                <div className="flex items-center gap-3 min-w-0">
                    {variant === "error" ? (
                        <ShieldOff className="h-5 w-5 shrink-0" />
                    ) : variant === "warning" ? (
                        <AlertTriangle className="h-5 w-5 shrink-0" />
                    ) : (
                        <ShieldCheck className="h-5 w-5 shrink-0" />
                    )}

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                        {/* Key label / status */}
                        <span className="font-medium">
                            {noLicense
                                ? "No active license"
                                : status.key_label ?? "License active"}
                        </span>

                        {/* Seat count */}
                        {status.is_valid && (
                            <span className={seatsNearLimit ? "font-semibold" : ""}>
                                Seats:&nbsp;
                                <span className={seatsNearLimit ? "text-orange-600 dark:text-orange-400" : ""}>
                                    {status.current_users} / {status.max_users}
                                </span>
                                {seatsNearLimit && (
                                    <Badge variant="outline" className="ml-2 text-xs border-orange-400 text-orange-500">
                                        Near limit
                                    </Badge>
                                )}
                            </span>
                        )}

                        {/* Expiry */}
                        {status.valid_until && (
                            <span>
                                {expired
                                    ? <span className="font-semibold">Expired {formatDate(status.valid_until)}</span>
                                    : expiringSoon
                                    ? <span className="font-semibold">Expires in {days} day{days !== 1 ? "s" : ""} ({formatDate(status.valid_until)})</span>
                                    : <span>Valid until {formatDate(status.valid_until)}</span>
                                }
                            </span>
                        )}

                        {/* Issued to */}
                        {status.issued_to && (
                            <span className="text-muted-foreground">— {status.issued_to}</span>
                        )}
                    </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 shrink-0">
                    <Button
                        size="sm"
                        variant="outline"
                        className="h-7 px-2 text-xs"
                        onClick={fetchStatus}
                        title="Refresh license status"
                    >
                        <RefreshCw className="h-3 w-3" />
                    </Button>
                    <Button
                        size="sm"
                        variant={variant === "ok" ? "outline" : "default"}
                        className="h-7 px-3 text-xs"
                        onClick={() => setActivateOpen(true)}
                    >
                        {noLicense || expired ? "Activate License" : "Renew"}
                    </Button>
                </div>
            </div>

            {/* Activate / Renew dialog */}
            <Dialog open={activateOpen} onOpenChange={setActivateOpen}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle>Activate License Key</DialogTitle>
                        <DialogDescription>
                            Paste the activation key provided by Cereveate. The key is verified
                            cryptographically — it cannot be forged or reused across installations.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-3 py-2">
                        <label className="text-sm font-medium">Activation Key</label>
                        <Input
                            placeholder="Paste key here (base64url.signature format)"
                            value={activateKey}
                            onChange={e => setActivateKey(e.target.value)}
                            className="font-mono text-xs"
                        />
                        <p className="text-xs text-muted-foreground">
                            Keys are valid for up to 1 year from issue date. Contact Cereveate
                            to request a renewal key before your current license expires.
                        </p>
                    </div>

                    <DialogFooter>
                        <Button variant="outline" onClick={() => setActivateOpen(false)} disabled={activating}>
                            Cancel
                        </Button>
                        <Button onClick={handleActivate} disabled={activating || !activateKey.trim()}>
                            {activating ? "Verifying…" : "Activate"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};

export default LicenseBanner;
