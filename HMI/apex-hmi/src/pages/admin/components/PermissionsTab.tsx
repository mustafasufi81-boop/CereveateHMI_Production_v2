import { useState, useEffect, useCallback } from "react";
import api from "@/services/api";
import { Button } from "@/components/ui/button";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";

import { ShieldCheck, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";

// ── module-permission matrix types ──────────────────────────────────────────
const MODULES = ['hmi', 'reports', 'analytics', 'alarms', 'admin'] as const;
type ModuleName = typeof MODULES[number];
const ACTIONS = ['can_view', 'can_operate', 'can_generate', 'can_configure'] as const;
type Action = typeof ACTIONS[number];
const ACTION_LABELS: Record<Action, string> = {
    can_view: 'View', can_operate: 'Operate', can_generate: 'Generate', can_configure: 'Configure'
};
const MODULE_LABELS: Record<ModuleName, string> = {
    hmi: 'HMI', reports: 'Reports', analytics: 'Analytics', alarms: 'Alarms', admin: 'Admin'
};
type ModuleRow = Record<Action, boolean> & { module: ModuleName };
type ModuleMatrix = Record<ModuleName, Record<Action, boolean>>;

const defaultMatrix = (): ModuleMatrix =>
    Object.fromEntries(MODULES.map(m => [m, { can_view: false, can_operate: false, can_generate: false, can_configure: false }])) as ModuleMatrix;

// ── Module Permissions Matrix subcomponent ───────────────────────────────────
function ModulePermissionsMatrix({ roleId }: { roleId: string }) {
    const [matrix, setMatrix] = useState<ModuleMatrix>(defaultMatrix());
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get(`/admin/roles/${roleId}/module-permissions`);
            const m = defaultMatrix();
            for (const row of (res.data.permissions as ModuleRow[])) {
                m[row.module] = { can_view: row.can_view, can_operate: row.can_operate, can_generate: row.can_generate, can_configure: row.can_configure };
            }
            setMatrix(m);
        } catch { toast.error("Failed to load module permissions"); }
        finally { setLoading(false); }
    }, [roleId]);

    useEffect(() => { load(); }, [load]);

    const toggle = (mod: ModuleName, action: Action) =>
        setMatrix(prev => ({ ...prev, [mod]: { ...prev[mod], [action]: !prev[mod][action] } }));

    const save = async () => {
        setSaving(true);
        try {
            const permissions = MODULES.map(m => ({ module: m, ...matrix[m] }));
            await api.put(`/admin/roles/${roleId}/module-permissions`, { permissions });
            toast.success("Module permissions saved — affected users must re-login");
        } catch { toast.error("Failed to save module permissions"); }
        finally { setSaving(false); }
    };

    return (
        <Card className="mb-6">
            <CardContent className="p-6 space-y-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <ShieldCheck className="h-5 w-5 text-emerald-500" />
                        <h3 className="font-semibold text-lg">Module Permissions</h3>
                        <span className="text-xs text-muted-foreground ml-1">(what this role can do in each section)</span>
                    </div>
                    <Button size="sm" onClick={save} disabled={saving || loading}>
                        {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                        Save
                    </Button>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground">
                        <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b">
                                    <th className="text-left py-2 pr-4 font-medium text-muted-foreground w-28">Module</th>
                                    {ACTIONS.map(a => (
                                        <th key={a} className="text-center py-2 px-3 font-medium text-muted-foreground">{ACTION_LABELS[a]}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {MODULES.map((mod, i) => (
                                    <tr key={mod} className={i % 2 === 0 ? 'bg-muted/20' : ''}>
                                        <td className="py-3 pr-4 font-medium capitalize">{MODULE_LABELS[mod]}</td>
                                        {ACTIONS.map(action => {
                                            const checked = matrix[mod][action];
                                            return (
                                                <td key={action} className="text-center py-3 px-3">
                                                    <button
                                                        type="button"
                                                        onClick={() => toggle(mod, action)}
                                                        className={`w-6 h-6 rounded border-2 transition-all flex items-center justify-center mx-auto
                                                            ${checked
                                                                ? 'bg-emerald-500 border-emerald-500 text-white'
                                                                : 'border-muted-foreground/40 hover:border-emerald-400'}`}
                                                    >
                                                        {checked && <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                                                    </button>
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
                <p className="text-xs text-muted-foreground pt-1">
                    ⚠️ Changes take effect on the user's <strong>next login</strong>.
                </p>
            </CardContent>
        </Card>
    );
}

interface PermissionsTabProps {
    roles: any[];
    initialRoleId?: number | null;
}

const PermissionsTab = ({ roles, initialRoleId }: PermissionsTabProps) => {
    const [selectedRoleId, setSelectedRoleId] = useState<string>(initialRoleId?.toString() || "");

    useEffect(() => {
        if (initialRoleId) {
            setSelectedRoleId(initialRoleId.toString());
        }
    }, [initialRoleId]);

    return (
        <div className="space-y-6">
            <div className="flex items-center gap-4 p-4 border rounded-lg bg-card text-card-foreground shadow-sm">
                <span className="text-sm font-medium whitespace-nowrap">Manage permissions for:</span>
                <Select value={selectedRoleId} onValueChange={setSelectedRoleId}>
                    <SelectTrigger className="w-[200px]">
                        <SelectValue placeholder="Select a role" />
                    </SelectTrigger>
                    <SelectContent>
                        {roles.map((role) => (
                            <SelectItem key={role.id} value={role.id.toString()}>
                                {role.name}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {selectedRoleId && (
                <>
                    {/* ── Module Permissions Matrix ── */}
                    <ModulePermissionsMatrix roleId={selectedRoleId} />
                </>
            )}

            {/* Note: Plant & Area Access and Specific Tag Access panels removed — */}
            {/* area assignment is managed in the dedicated Area Access tab.      */}


            {!selectedRoleId && (
                <div className="text-center py-12 text-muted-foreground">
                    Please select a role to view and manage permissions.
                </div>
            )}
        </div>
    );
};

export default PermissionsTab;
