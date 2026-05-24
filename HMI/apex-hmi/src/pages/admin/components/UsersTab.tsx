import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/auth-context";
import api from "@/services/api";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Shield, UserX, CheckCircle, ShieldAlert, KeyRound } from "lucide-react";
import { toast } from "sonner";

interface UsersTabProps {
    roles: any[];
}

const UsersTab = ({ roles }: UsersTabProps) => {
    const { user: currentUser } = useAuth();
    const [users, setUsers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchUsers = useCallback(async () => {
        setLoading(true);
        try {
            const response = await api.get('/admin/users');
            setUsers(response.data.users || []);
        } catch (error) {
            console.error("Failed to fetch users", error);
            toast.error("Failed to load users");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchUsers();
    }, [fetchUsers]);

    const approveUser = async (userId: string, roleId: number) => {
        try {
            await api.post(`/admin/users/${userId}/approve`, { roleId });
            toast.success("User approved successfully");
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to approve user");
        }
    };

    const revokeUser = async (userId: string) => {
        if (!confirm('Are you sure you want to revoke this user?')) return;
        try {
            await api.post(`/admin/users/${userId}/revoke`);
            toast.success("User revoked successfully");
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to revoke user");
        }
    };

    const resetUserPassword = async (userId: string, username: string) => {
        if (!confirm(`Reset password for "${username}"? They will be required to set a new password on next login.`)) return;
        try {
            await api.post(`/admin/users/${userId}/reset-password`);
            toast.success(`Password reset for ${username}. They will be prompted on next login.`);
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to reset password");
        }
    };

    const assignRole = async (userId: string, roleId: number) => {
        try {
            await api.post(`/admin/users/${userId}/role`, { roleId });
            toast.success("Role assigned successfully");
            fetchUsers();
        } catch (error: any) {
            toast.error(error.response?.data?.message || "Failed to assign role");
        }
    };

    const getStatusBadge = (status: string) => {
        switch (status) {
            case 'approved':
                return <Badge className="bg-green-500/10 text-green-500 border-green-500/20 hover:bg-green-500/20">Approved</Badge>;
            case 'revoked':
                return <Badge variant="destructive">Revoked</Badge>;
            default:
                return <Badge variant="secondary" className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 hover:bg-yellow-500/20">Pending</Badge>;
        }
    };

    if (loading) {
        return <div className="flex justify-center p-8"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h3 className="text-lg font-medium">User Management</h3>
                <Button variant="outline" size="sm" onClick={fetchUsers}>
                    Refresh
                </Button>
            </div>

            <Card>
                <CardContent className="p-0">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>User</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Role</TableHead>
                                <TableHead>MFA</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {users.map((user) => (
                                <TableRow key={user.id}>
                                    <TableCell>
                                        <div className="flex items-center gap-3">
                                            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-medium">
                                                {user.username?.[0]?.toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="font-medium flex items-center gap-2">
                                                    {user.username}
                                                    {user.is_admin && <Shield className="h-3 w-3 text-violet-500" />}
                                                </div>
                                            </div>
                                        </div>
                                    </TableCell>
                                    <TableCell>{getStatusBadge(user.status)}</TableCell>
                                    <TableCell>{user.role_name || <span className="text-muted-foreground italic">No Role</span>}</TableCell>
                                    <TableCell>
                                        {user.mfa_enabled ? (
                                            <Badge variant="outline" className="text-green-500 border-green-500/20">Enabled</Badge>
                                        ) : (
                                            <Badge variant="outline" className="text-muted-foreground">Disabled</Badge>
                                        )}
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <div className="flex items-center justify-end gap-2">
                                            {user.status === 'pending' && (
                                                <div className="flex items-center gap-2">
                                                    <Select onValueChange={(value) => approveUser(user.id, parseInt(value))}>
                                                        <SelectTrigger className="w-[140px] h-8">
                                                            <SelectValue placeholder="Approve as..." />
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
                                            )}

                                            {user.status === 'approved' && user.id !== currentUser?.id && (
                                                <>
                                                    <Select
                                                        value={user.role_id?.toString() || ""}
                                                        onValueChange={(value) => assignRole(user.id, parseInt(value))}
                                                    >
                                                        <SelectTrigger className="w-[130px] h-8">
                                                            <SelectValue placeholder="Role" />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            <SelectItem value="0">No Role</SelectItem>
                                                            {roles.map((role) => (
                                                                <SelectItem key={role.id} value={role.id.toString()}>
                                                                    {role.name}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>

                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        title="Reset Password"
                                                        onClick={() => resetUserPassword(user.id, user.username)}
                                                        className="text-yellow-600 hover:text-yellow-700 hover:bg-yellow-500/10 h-8 w-8"
                                                    >
                                                        <KeyRound className="h-4 w-4" />
                                                    </Button>

                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        onClick={() => revokeUser(user.id)}
                                                        className="text-destructive hover:text-destructive hover:bg-destructive/10 h-8 w-8"
                                                    >
                                                        <UserX className="h-4 w-4" />
                                                    </Button>
                                                </>
                                            )}

                                            {user.status === 'revoked' && (
                                                <Select onValueChange={(value) => approveUser(user.id, parseInt(value))}>
                                                    <SelectTrigger className="w-[140px] h-8">
                                                        <SelectValue placeholder="Reactivate..." />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {roles.map((role) => (
                                                            <SelectItem key={role.id} value={role.id.toString()}>
                                                                {role.name}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            )}
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ))}
                            {users.length === 0 && (
                                <TableRow>
                                    <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                        No users found
                                    </TableCell>
                                </TableRow>
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
};

export default UsersTab;
