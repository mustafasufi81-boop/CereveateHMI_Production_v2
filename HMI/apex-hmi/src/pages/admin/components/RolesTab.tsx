import { useState } from "react";
import api from "@/services/api";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    DialogFooter,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Trash2, Shield, Plus } from "lucide-react";
import { toast } from "sonner";

interface RolesTabProps {
    roles: any[];
    onRefresh: () => void;
    onSelectRoleForPermissions: (roleId: number) => void;
}

const RolesTab = ({ roles, onRefresh, onSelectRoleForPermissions }: RolesTabProps) => {
    const [isCreateOpen, setIsCreateOpen] = useState(false);
    const [newRole, setNewRole] = useState({ name: '', description: '', isAdmin: false });
    const [creating, setCreating] = useState(false);

    const createRole = async () => {
        if (!newRole.name.trim()) return;
        setCreating(true);
        try {
            await api.post('/admin/roles', newRole);
            toast.success("Role created successfully");
            setNewRole({ name: '', description: '', isAdmin: false });
            setIsCreateOpen(false);
            onRefresh();
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to create role");
        } finally {
            setCreating(false);
        }
    };

    const deleteRole = async (roleId: number) => {
        if (!confirm('Are you sure you want to delete this role? This cannot be undone.')) return;
        try {
            await api.delete(`/admin/roles/${roleId}`);
            toast.success("Role deleted successfully");
            onRefresh();
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to delete role");
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-medium">Role Management</h3>
                <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
                    <DialogTrigger asChild>
                        <Button>
                            <Plus className="h-4 w-4 mr-2" />
                            Create New Role
                        </Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Create New Role</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                            <div className="space-y-2">
                                <Label>Role Name</Label>
                                <Input
                                    value={newRole.name}
                                    onChange={(e) => setNewRole(p => ({ ...p, name: e.target.value }))}
                                    placeholder="e.g. Operator"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Description</Label>
                                <Input
                                    value={newRole.description}
                                    onChange={(e) => setNewRole(p => ({ ...p, description: e.target.value }))}
                                    placeholder="Role description"
                                />
                            </div>
                            <div className="flex items-center space-x-2">
                                <Checkbox
                                    id="isAdmin"
                                    checked={newRole.isAdmin}
                                    onCheckedChange={(checked) => setNewRole(p => ({ ...p, isAdmin: checked === true }))}
                                />
                                <Label htmlFor="isAdmin" className="font-normal cursor-pointer">
                                    Has Administrator Privileges
                                </Label>
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>Cancel</Button>
                            <Button onClick={createRole} disabled={creating}>{creating ? "Creating..." : "Create Role"}</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            </div>

            <Card>
                <CardContent className="p-0">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Role Name</TableHead>
                                <TableHead>Description</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {roles.map((role) => (
                                <TableRow key={role.id}>
                                    <TableCell className="font-medium">
                                        <div className="flex items-center gap-2">
                                            {role.name}
                                            {role.is_admin && (
                                                <Badge variant="secondary" className="bg-violet-500/10 text-violet-500 border-violet-500/20 text-[10px] px-1 py-0 h-5">
                                                    Admin
                                                </Badge>
                                            )}
                                        </div>
                                    </TableCell>
                                    <TableCell className="text-muted-foreground">{role.description || '-'}</TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex items-center justify-end gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="text-blue-500 border-blue-500/20 hover:bg-blue-500/10"
                                                onClick={() => onSelectRoleForPermissions(role.id)}
                                            >
                                                <Shield className="h-4 w-4 mr-2" />
                                                Permissions
                                            </Button>
                                            {role.name !== 'Admin' && (
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="text-destructive hover:text-destructive hover:bg-destructive/10 h-8 w-8"
                                                    onClick={() => deleteRole(role.id)}
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            )}
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
};

export default RolesTab;
