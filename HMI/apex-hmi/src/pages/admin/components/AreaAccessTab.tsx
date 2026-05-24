import { useState, useEffect, useCallback } from "react";
import api from "@/services/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, MapPin, Save, RefreshCw, Building2, LayoutGrid, CheckSquare, Square, Info, Database, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface PlantArea {
    id: number;
    plant_code: string;
    area_code: string;
    plant: string;
    area: string;
    display_name: string;
    description?: string;
    is_active: boolean;
    tag_count: number;
    server_progid?: string;   // OPC server ProgID / MQTT topic
}

interface UserRow {
    id: number;
    username: string;
    status: string;
    role_name: string;
    is_admin: boolean;
}

interface AccessMatrixRow {
    user_id: number;
    username: string;
    status: string;
    role_name: string;
    is_admin: boolean;
    assigned_areas: string | null;
    area_count: number;
    max_areas_per_user: number | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-component: Area assignment dialog for a single user
// ─────────────────────────────────────────────────────────────────────────────

interface AssignDialogProps {
    user: UserRow | null;
    onClose: () => void;
    onSaved: () => void;
}

const AssignDialog = ({ user, onClose, onSaved }: AssignDialogProps) => {
    const [allAreas, setAllAreas] = useState<PlantArea[]>([]);
    const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set());
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        if (!user) return;
        setLoading(true);
        api.get(`/admin/users/${user.id}/areas`)
            .then(res => {
                setAllAreas(res.data.all_plants_areas || []);
                setCheckedIds(new Set(res.data.assigned_plant_area_ids || []));
            })
            .catch(() => toast.error("Failed to load area assignments"))
            .finally(() => setLoading(false));
    }, [user]);

    const toggle = (id: number) => {
        setCheckedIds(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });
    };

    const selectAll = () => setCheckedIds(new Set(allAreas.filter(a => a.is_active).map(a => a.id)));
    const clearAll = () => setCheckedIds(new Set());

    const save = async () => {
        if (!user) return;
        setSaving(true);
        try {
            await api.put(`/admin/users/${user.id}/areas`, {
                plant_area_ids: Array.from(checkedIds),
            });
            toast.success(`Area access updated for ${user.username}`);
            onSaved();
            onClose();
        } catch (err: any) {
            toast.error(err.response?.data?.message || "Failed to save area assignments");
        } finally {
            setSaving(false);
        }
    };

    // Group by OPC Server → Plant → Area (full hierarchy)
    const byServer: Record<string, Record<string, PlantArea[]>> = {};
    for (const pa of allAreas) {
        const srv = pa.server_progid || 'Unknown OPC Server';
        if (!byServer[srv]) byServer[srv] = {};
        if (!byServer[srv][pa.plant]) byServer[srv][pa.plant] = [];
        byServer[srv][pa.plant].push(pa);
    }

    return (
        <Dialog open={!!user} onOpenChange={open => !open && onClose()}>
            <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <MapPin className="h-5 w-5 text-primary" />
                        Area Access — {user?.username}
                    </DialogTitle>
                    <DialogDescription>
                        {user?.is_admin
                            ? "This user is an Admin — they bypass all area filters and see all data."
                            : "Select which Plant/Area combinations this user can access. Each area must be assigned explicitly — being in a Plant does NOT grant access to all its areas."}
                    </DialogDescription>
                </DialogHeader>

                {user?.is_admin && (
                    <div className="flex items-center gap-2 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg text-blue-400 text-sm">
                        <Info className="h-4 w-4 flex-shrink-0" />
                        Admin users bypass area filters. Area assignments below have no effect on data visibility.
                    </div>
                )}

                {loading ? (
                    <div className="flex justify-center py-8">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Select all / clear all */}
                        <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={selectAll}
                                disabled={user?.is_admin}>
                                <CheckSquare className="h-4 w-4 mr-1" /> Select All
                            </Button>
                            <Button size="sm" variant="outline" onClick={clearAll}
                                disabled={user?.is_admin}>
                                <Square className="h-4 w-4 mr-1" /> Clear All
                            </Button>
                            <span className="ml-auto text-xs text-muted-foreground self-center">
                                {checkedIds.size > 0
                                    ? <><span className="text-emerald-400 font-semibold">{checkedIds.size}</span> / {allAreas.filter(a => a.is_active).length} selected</>
                                    : "Check areas to assign"}
                            </span>
                        </div>

                        {/* OPC Server → Plant → Area hierarchy */}
                        {Object.entries(byServer).sort().map(([server, plants]) => (
                            <div key={server} className="space-y-2">
                                {/* OPC Server level */}
                                <div className="flex items-center gap-2 px-2 py-1 bg-muted/30 rounded text-xs font-semibold text-primary uppercase tracking-wide">
                                    <Database className="h-3.5 w-3.5" />
                                    {server}
                                </div>

                                {Object.entries(plants).sort().map(([plant, areas]) => (
                                    <Card key={plant} className="border-border/60 ml-3">
                                        <CardHeader className="py-2 px-4">
                                            <CardTitle className="text-sm flex items-center gap-2">
                                                <Building2 className="h-4 w-4 text-primary" />
                                                {plant}
                                            </CardTitle>
                                        </CardHeader>
                                        <CardContent className="px-4 py-2">
                                            <div className="space-y-1">
                                                {areas.map(pa => (
                                                    <label
                                                        key={pa.id}
                                                        className={`flex items-center gap-3 p-2 rounded-md cursor-pointer transition-colors
                                                            ${!pa.is_active ? 'opacity-40 cursor-not-allowed' : 'hover:bg-muted/50'}
                                                            ${checkedIds.has(pa.id) ? 'bg-primary/5 border border-primary/20' : ''}
                                                        `}
                                                    >
                                                        <input
                                                            type="checkbox"
                                                            className="h-4 w-4 accent-primary"
                                                            checked={checkedIds.has(pa.id)}
                                                            disabled={!pa.is_active || user?.is_admin}
                                                            onChange={() => toggle(pa.id)}
                                                        />
                                                        <div className="flex-1 min-w-0">
                                                            <div className="flex items-center gap-2">
                                                                <LayoutGrid className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                                                                <span className="text-sm font-medium">{pa.area}</span>
                                                                {!pa.is_active && (
                                                                    <Badge variant="secondary" className="text-xs py-0">Inactive</Badge>
                                                                )}
                                                            </div>
                                                            <div className="flex items-center gap-2 mt-0.5">
                                                                <span className="text-xs text-muted-foreground">
                                                                    {server} › {plant} › {pa.area}
                                                                </span>
                                                                <span className="text-xs text-muted-foreground">·</span>
                                                                <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                                    <Database className="h-3 w-3" /> {pa.tag_count} tags
                                                                </span>
                                                            </div>
                                                        </div>
                                                    </label>
                                                ))}
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        ))}

                        {allAreas.length === 0 && (
                            <div className="text-center py-6 text-muted-foreground text-sm">
                                No plant/area entries found. Use "Sync from Tags" to populate.
                            </div>
                        )}
                    </div>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancel</Button>
                    <Button onClick={save} disabled={saving || loading || user?.is_admin === true}>
                        {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                        Save Assignments
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
};

// ─────────────────────────────────────────────────────────────────────────────
// Main: AreaAccessTab
// ─────────────────────────────────────────────────────────────────────────────

const AreaAccessTab = () => {
    const [matrix, setMatrix] = useState<AccessMatrixRow[]>([]);
    const [loading, setLoading] = useState(true);
    const [syncing, setSyncing] = useState(false);
    const [selectedUser, setSelectedUser] = useState<UserRow | null>(null);

    const fetchMatrix = useCallback(async () => {
        setLoading(true);
        try {
            const res = await api.get('/admin/access-matrix');
            setMatrix(res.data.matrix || []);
        } catch {
            toast.error("Failed to load access matrix");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchMatrix(); }, [fetchMatrix]);

    const syncFromTags = async () => {
        setSyncing(true);
        try {
            const res = await api.post('/admin/plants-areas/sync');
            toast.success(res.data.message || "Sync complete");
            fetchMatrix();
        } catch (err: any) {
            toast.error(err.response?.data?.message || "Sync failed");
        } finally {
            setSyncing(false);
        }
    };

    const openAssignDialog = (row: AccessMatrixRow) => {
        setSelectedUser({
            id: row.user_id,
            username: row.username,
            status: row.status,
            role_name: row.role_name,
            is_admin: row.is_admin,
        });
    };

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-medium">Plant / Area Access Control</h3>
                    <p className="text-sm text-muted-foreground mt-0.5">
                        Role defines what users can do. Area defines what data they see.
                        Same role, different areas = completely different data.
                    </p>
                </div>
                <div className="flex gap-2">
                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <Button variant="outline" size="sm" onClick={syncFromTags} disabled={syncing}>
                                    {syncing
                                        ? <Loader2 className="h-4 w-4 animate-spin mr-1" />
                                        : <RefreshCw className="h-4 w-4 mr-1" />}
                                    Sync from Tags
                                </Button>
                            </TooltipTrigger>
                            <TooltipContent>
                                Adds any new plant/area combinations found in tag_master to the registry
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                    <Button variant="outline" size="sm" onClick={fetchMatrix}>
                        <RefreshCw className="h-4 w-4 mr-1" /> Refresh
                    </Button>
                </div>
            </div>

            {/* Key rule callout */}
            <div className="flex items-start gap-2 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg text-amber-400 text-sm">
                <Info className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>
                    <strong>Key Rule:</strong> Being in a plant does NOT grant access to all its areas.
                    Plant1/Area1 and Plant1/Area-2 are independent assignments.
                    A user sees ONLY the exact areas explicitly assigned to them.
                </span>
            </div>

            {/* Access Matrix Table */}
            {loading ? (
                <div className="flex justify-center p-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base">Access Matrix</CardTitle>
                        <CardDescription>Click "Assign Areas" to edit a user's plant/area access</CardDescription>
                    </CardHeader>
                    <CardContent className="p-0">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>User</TableHead>
                                    <TableHead>Role</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Assigned Areas</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {matrix.map(row => (
                                    <TableRow key={row.user_id}>
                                        <TableCell className="font-medium">{row.username}</TableCell>
                                        <TableCell>
                                            <Badge variant={row.is_admin ? "default" : "secondary"}>
                                                {row.role_name}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            <Badge
                                                className={
                                                    row.status === 'approved'
                                                        ? 'bg-green-500/10 text-green-500 border-green-500/20'
                                                        : row.status === 'revoked'
                                                        ? 'bg-red-500/10 text-red-500 border-red-500/20'
                                                        : 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20'
                                                }
                                                variant="outline"
                                            >
                                                {row.status}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            {row.is_admin ? (
                                                /* Admin: cyan pill — bypasses all filters */
                                                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                                                    <MapPin className="h-3 w-3" /> ALL — admin bypass
                                                </span>
                                            ) : Number(row.area_count) === 0 ? (
                                                /* 0 areas: red alarm pill — user sees NOTHING */
                                                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
                                                    <AlertCircle className="h-3 w-3" />
                                                    No areas assigned — user sees nothing
                                                </span>
                                            ) : (
                                                /* Has areas: show list + count pill */
                                                <div className="flex flex-col gap-0.5">
                                                    <span className="text-xs text-foreground leading-snug">
                                                        {row.assigned_areas || '—'}
                                                    </span>
                                                    <span className={`inline-flex items-center gap-1 text-xs font-semibold w-fit px-1.5 py-0 rounded-full border
                                                        ${row.max_areas_per_user != null && row.area_count >= row.max_areas_per_user
                                                            ? 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                                                            : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                                                        }`}>
                                                        {row.area_count} area{row.area_count !== 1 ? 's' : ''}
                                                        {row.max_areas_per_user != null && (
                                                            <span className="opacity-70"> / {row.max_areas_per_user} max</span>
                                                        )}
                                                    </span>
                                                </div>
                                            )}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button
                                                size="sm"
                                                variant="outline"
                                                onClick={() => openAssignDialog(row)}
                                            >
                                                <MapPin className="h-3.5 w-3.5 mr-1" />
                                                Assign Areas
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            )}

            {/* Assignment Dialog */}
            <AssignDialog
                user={selectedUser}
                onClose={() => setSelectedUser(null)}
                onSaved={fetchMatrix}
            />
        </div>
    );
};

export default AreaAccessTab;
