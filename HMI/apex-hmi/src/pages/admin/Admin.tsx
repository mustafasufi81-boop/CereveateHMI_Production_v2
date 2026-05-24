import { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/services/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ArrowLeft, Shield } from "lucide-react";
import UsersTab from "./components/UsersTab";
import RolesTab from "./components/RolesTab";
import PermissionsTab from "./components/PermissionsTab";
import AlertsTab from "./components/AlertsTab";
import AreaAccessTab from "./components/AreaAccessTab";
import LicenseBanner from "./components/LicenseBanner";
import { AuditLogViewer } from "@/components/rbac/AuditLogViewer";
import { SessionManager } from "@/components/rbac/SessionManager";
import { ApprovalDashboard } from "@/components/rbac/ApprovalDashboard";
import { toast } from "sonner";
import { UserHeader } from "@/components/hmi/UserHeader";

const Admin = () => {
    const navigate = useNavigate();
    const [roles, setRoles] = useState<any[]>([]);
    const [loadingRoles, setLoadingRoles] = useState(true);
    const [activeTab, setActiveTab] = useState("users");
    const [selectedRoleForPermissions, setSelectedRoleForPermissions] = useState<number | null>(null);

    const fetchRoles = useCallback(async () => {
        setLoadingRoles(true);
        try {
            const response = await api.get('/admin/roles');
            setRoles(response.data.roles || []);
        } catch (error) {
            console.error("Failed to fetch roles", error);
            toast.error("Failed to load roles");
        } finally {
            setLoadingRoles(false);
        }
    }, []);

    useEffect(() => {
        fetchRoles();
    }, [fetchRoles]);

    const handleRoleSelectForPermissions = (roleId: number) => {
        setSelectedRoleForPermissions(roleId);
        setActiveTab("permissions");
    };

    return (
        <div className="min-h-screen bg-background p-6">
            <div className="max-w-7xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-xl text-primary">
                            <Shield className="h-6 w-6" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold tracking-tight">Admin Console</h1>
                            <p className="text-muted-foreground text-sm">Manage users, roles, and system security</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <Button variant="outline" onClick={() => navigate('/')}>
                            <ArrowLeft className="mr-2 h-4 w-4" />
                            Back to Dashboard
                        </Button>
                        <UserHeader />
                    </div>
                </div>

                {/* License Status Banner */}
                <LicenseBanner />

                {/* Main Content */}
                <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
                    <TabsList className="bg-muted/50 p-1">
                        <TabsTrigger value="users" className="px-6">Users</TabsTrigger>
                        <TabsTrigger value="roles" className="px-6">Roles</TabsTrigger>
                        <TabsTrigger value="permissions" className="px-6">Permissions</TabsTrigger>
                        <TabsTrigger value="area-access" className="px-6">Area Access</TabsTrigger>
                        <TabsTrigger value="sessions" className="px-6">Sessions</TabsTrigger>
                        <TabsTrigger value="audit" className="px-6">Audit Logs</TabsTrigger>
                        <TabsTrigger value="approvals" className="px-6">Approvals</TabsTrigger>
                        <TabsTrigger value="alerts" className="px-6">System Alerts</TabsTrigger>
                    </TabsList>

                    <TabsContent value="users" className="space-y-4">
                        <UsersTab roles={roles} />
                    </TabsContent>

                    <TabsContent value="roles" className="space-y-4">
                        <RolesTab
                            roles={roles}
                            onRefresh={fetchRoles}
                            onSelectRoleForPermissions={handleRoleSelectForPermissions}
                        />
                    </TabsContent>

                    <TabsContent value="permissions" className="space-y-4">
                        <PermissionsTab roles={roles} initialRoleId={selectedRoleForPermissions} />
                    </TabsContent>

                    <TabsContent value="area-access" className="space-y-4">
                        <AreaAccessTab />
                    </TabsContent>

                    <TabsContent value="sessions" className="space-y-4">
                        <SessionManager />
                    </TabsContent>

                    <TabsContent value="audit" className="space-y-4">
                        <AuditLogViewer />
                    </TabsContent>

                    <TabsContent value="approvals" className="space-y-4">
                        <ApprovalDashboard />
                    </TabsContent>

                    <TabsContent value="alerts" className="space-y-4">
                        <AlertsTab />
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    );
};

export default Admin;
